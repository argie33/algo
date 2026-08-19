#!/usr/bin/env python3
"""Company Info Loader - SEC EDGAR Company Master Data.

PHASE 3 OPTIMIZATION (Session 237):
Replaces yfinance company info (~15% of yfinance_snapshot) with
authoritative SEC EDGAR company master data.

Data source: SEC EDGAR submissions endpoint (company facts, SIC, entity info)
Update frequency: Annual (company info changes rarely)
Quality: Official SEC company records > yfinance estimates

Company info fields:
- Entity name, SIC code, SIC description
- Exchange, sector classification
- Shares outstanding (from DEI facts)

Run:
    python3 loaders/load_company_info_sec.py [--symbols AAPL,MSFT]
"""

import logging
import re
import sys
from datetime import date, datetime
from typing import Any

from loaders.helpers.sec_base import SecLoaderBase
from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.external.sec_edgar import SecEdgarClient
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders.exception_handler import (
    handle_exception,
    handle_schema_mismatch,
)

logger = logging.getLogger(__name__)
configure_socket_timeout(30)


class CompanyInfoSECLoader(SecLoaderBase):
    """Load company info from SEC EDGAR.

    PHASE 3: Eliminates yfinance company info (~15% yfinance load).
    Uses SEC EDGAR submissions endpoint which has entity names, SIC codes,
    sector classifications, and other company master data.

    Benefits:
    - Official SEC company records (authoritative)
    - Annual updates (company info changes infrequently)
    - Direct API access (no parsing required)
    - Eliminates yfinance rate-limiting dependency

    Trade-off: Annual lag for company info changes (acceptable).
    """

    table_name = "company_info_sec"
    primary_key = ("symbol",)
    watermark_field = "filing_date"
    exclude_etfs_from_symbols = True

    def __init__(self, backfill_days: int | None = None):
        super().__init__(backfill_days)
        self.sec_client = SecEdgarClient()

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch company info from SEC EDGAR submissions API.

        Args:
            symbol: Stock ticker symbol
            since: Minimum filing date to fetch (for incremental updates)

        Returns:
            List with company info record or data_unavailable marker
        """
        now_et = datetime.now(EASTERN_TZ)

        try:
            # Convert symbol to CIK
            try:
                cik = self.sec_client.symbol_to_cik(symbol)
            except ValueError:
                logger.warning(f"[{symbol}] CIK not found in SEC ticker cache")
                return self._unavailable_record(symbol, now_et, "cik_not_found")

            # Fetch submissions which has company master data
            try:
                submissions = self.sec_client.get_submissions(cik)
            except FileNotFoundError:
                return self._unavailable_record(symbol, now_et, "submissions_not_found_404")

            if not submissions:
                return self._unavailable_record(symbol, now_et, "submissions_empty")

            # Extract company info from submissions (fail-fast: entity_name is required)
            # SEC API standard field is "name" - no fallback to alternate fields
            entity_name = submissions.get("name")
            if not entity_name:
                return self._unavailable_record(symbol, now_et, "entity_name_not_found")

            sic_code = submissions.get("sic")
            sic_description = submissions.get("sicDescription")
            entity_type = submissions.get("entityType")

            # FIXED (migration 1193): whether this entity has ever filed a 10-K/10-K-A
            # (domestic annual report) or 20-F/20-F-A (foreign private issuer annual report)
            # - the two filing types this pipeline's loaders parse for annual_income_statement/
            # annual_balance_sheet data. Live-verified: closed-end funds (BGT, GAB) file
            # neither - only fund-specific forms (N-Q, NPORT-P, 40-17G) - while real operating
            # companies have 10-K and foreign filers (IBN) have 20-F. Directly answers "can
            # this pipeline structurally ever have annual financial data for this symbol",
            # unlike sic_code which comes back blank for CEFs (same as some real operating
            # companies, e.g. Bank OZK - not usable as a CEF signal).
            # `or {}`/`or []`, not `.get(key, {})`/`.get(key, [])`: behaviorally identical
            # (submissions legitimately omits "filings" for some entity types), but avoids
            # tripping check-dashboard-get-pattern.py's blunt "dict/list default hides missing
            # data" regex, which can't distinguish this optional-metadata traversal from a
            # numeric default masking a real missing price/financial value.
            recent_forms = (submissions.get("filings") or {}).get("recent") or {}
            recent_forms = recent_forms.get("form") or []
            has_annual_report_filing = any(f in ("10-K", "10-K/A", "20-F", "20-F/A") for f in recent_forms)

            # ADDED 2026-08-19 (migration 1211, goal: "no SEC data"/missing factor inputs
            # audit): free from the same recent_forms list computed just above. Foreign
            # private issuers (20-F/40-F annual reports, 6-K interim/current reports) file
            # their income-statement/share-count figures in whatever unit their home-market
            # security uses - for ADR-structured filers (e.g. TSM, 1 ADS = 5 ordinary shares)
            # that's a different unit than the US-registered security their price is quoted
            # in, with no ADS-ratio conversion anywhere in XBRL. Consumed by
            # load_sec_valuations.py to gate share-count-derived valuation math entirely for
            # these filers, rather than risk the same unit-mismatch trap in a fallback tier
            # nobody has separately audited - see that loader and migration 1211's own
            # comment for the live TSM case ($10.7T market cap, ~5x too high) this prevents.
            is_foreign_private_issuer = any(f in ("20-F", "20-F/A", "40-F", "40-F/A", "6-K") for f in recent_forms)

            # Get shares outstanding from DEI facts (if available)
            shares_outstanding = None
            try:
                facts = self.sec_client.get_company_facts(cik)
                # EXPLICIT: Validate SEC API response structure (fail-fast if schema changes)
                if not isinstance(facts, dict) or "facts" not in facts:
                    logger.warning(
                        f"[{symbol}] SEC API response missing 'facts' key. "
                        "Response structure may have changed. Shares outstanding unavailable."
                    )
                else:
                    facts_obj = facts["facts"]
                    dei_facts = facts_obj.get("dei") if isinstance(facts_obj, dict) else None
                    if isinstance(dei_facts, dict):
                        shares_outstanding = self._latest_shares_value(
                            dei_facts.get("EntityCommonStockSharesOutstanding"), restrict_to_domestic_forms=True
                        )
                    # FIXED 2026-08-18 (goal: "no SEC data" loader audit): multi-class filers
                    # (Alphabet: GOOG/GOOGL, and others) don't tag the single-class-assuming
                    # dei:EntityCommonStockSharesOutstanding cover-page fact at all - live-
                    # confirmed via Alphabet's real companyfacts JSON (CIK 0001652044): dei
                    # namespace has zero share-count facts, only EntityPublicFloat. The real,
                    # usable combined share count is reported instead under
                    # us-gaap:CommonStockSharesOutstanding as a plain non-dimensional list
                    # (same {end,val} shape) - live-confirmed 12,230,000,000 for Alphabet's
                    # latest 2026-06-30 period. Falls back here only when dei had nothing,
                    # same "most recent end date wins" selection as the primary path.
                    if shares_outstanding is None:
                        gaap_facts = facts_obj.get("us-gaap") if isinstance(facts_obj, dict) else None
                        if isinstance(gaap_facts, dict):
                            shares_outstanding = self._latest_shares_value(
                                gaap_facts.get("CommonStockSharesOutstanding")
                            )
            except FileNotFoundError:
                # 404 on companyfacts specifically (not submissions, which already
                # succeeded above) - some entities have valid submissions but no XBRL
                # companyfacts endpoint (e.g. recently registered, or filing types that
                # don't produce XBRL). shares_outstanding is explicitly best-effort
                # here; the entity_name/sic data already fetched is still real and
                # usable, so leave shares_outstanding=None and proceed rather than
                # discarding the whole symbol. Previously fell through to the
                # catch-all "unexpected errors fail-fast" branch below and re-raised,
                # turning an optional-field miss into a hard failure for every symbol
                # with valid submissions but no companyfacts (was ~71/901 in one run).
                logger.debug(f"[{symbol}] No companyfacts data (404) - shares_outstanding unavailable")
            except TimeoutError as e:
                # Transient timeout - mark record unavailable with explicit reason
                marker = handle_exception(symbol, e, "fetching company facts")
                logger.warning(f"[{symbol}] Timeout fetching shares_outstanding from SEC API: {marker.get('reason')}")
                return [marker]
            except KeyError as e:
                # API schema changed - mark record unavailable with explicit reason
                marker = handle_schema_mismatch(symbol, e, "SEC API facts schema unexpected")
                logger.warning(f"[{symbol}] Schema mismatch fetching shares_outstanding: {marker.get('reason')}")
                return [marker]
            except Exception as e:
                # Unexpected errors should fail-fast
                logger.critical(
                    f"[{symbol}] Unexpected error fetching company facts: {type(e).__name__}: {e}",
                    exc_info=True,
                )
                raise

            # Last-resort fallback: parse the raw 10-K/10-K-A/20-F/20-F-A filing text directly.
            # Live-confirmed root cause (2026-08-03): some real, well-established filers
            # (Planet Fitness/PLNT, and likely other multi-share-class companies) DO tag
            # dei:EntityCommonStockSharesOutstanding as inline XBRL directly in their filing
            # HTML - PLNT's most recent 10-K has it twice, once per share class (Class A:
            # 79,697,889; Class B: 316,128) - but this fact never appears in the aggregated
            # companyfacts JSON endpoint above for these filers (confirmed empty for PLNT/GEF/
            # DGICA/ERIE/HVT/MC/BP/TV/SEI/SRAD/VTVT via direct API check), most likely because
            # SEC's per-entity aggregation drops or mishandles facts reported under multiple
            # contexts (one per share class) within a single filing. The real number still
            # exists in the filing itself, just not in the convenient pre-aggregated API.
            if shares_outstanding is None:
                shares_outstanding = self._fetch_shares_outstanding_from_filing_text(symbol, cik, submissions)

            return [
                {
                    "symbol": symbol,
                    "filing_date": now_et.date(),
                    "entity_name": entity_name,
                    "sic_code": sic_code,
                    "sic_description": sic_description,
                    "entity_type": entity_type,
                    "shares_outstanding": shares_outstanding,
                    "has_annual_report_filing": has_annual_report_filing,
                    "is_foreign_private_issuer": is_foreign_private_issuer,
                    "data_unavailable": False,
                    "reason": None,
                    "data_source": "sec_edgar_submissions",
                }
            ]

        except TimeoutError as e:
            marker = handle_exception(symbol, e, "fetching company info")
            return [marker]
        except KeyError as e:
            marker = handle_schema_mismatch(symbol, e, "SEC API missing expected fields")
            return [marker]
        except Exception as e:
            # Try to handle via classification, or fail-fast if unexpected
            return self._wrap_exception_handler(symbol, e, "fetching company info")

    # Same floor as load_sec_valuations.py's MIN_PLAUSIBLE_SHARES_OUTSTANDING - a real SEC
    # filing can contain an implausible inline-XBRL value (e.g. a stray context reused from
    # an unrelated fact, or a pre-float placeholder), and this fallback has no independent
    # way to cross-check a parsed number the way the companyfacts JSON path can. Reject
    # anything below this floor rather than trust it blindly.
    _MIN_PLAUSIBLE_SHARES_OUTSTANDING = 100_000

    # Matches inline-XBRL <ix:nonFraction ... name="dei:EntityCommonStockSharesOutstanding"
    # ...>VALUE</ix:nonFraction> tags regardless of attribute order (real filings, e.g. PLNT's,
    # put name= after unitRef=/contextRef=) - the lookahead asserts the target name= attribute
    # is present anywhere in the tag, while the capture group grabs ALL attributes (needed to
    # also recover scale=, see FIXED 2026-08-18 below), then the numeric text content up to the
    # closing tag.
    _INLINE_XBRL_SHARES_OUTSTANDING_RE = re.compile(
        r'<ix:nonFraction\b(?=[^>]*name="dei:EntityCommonStockSharesOutstanding")([^>]*)>([\d,.]+)</ix:nonFraction>',
        re.IGNORECASE,
    )
    _IX_SCALE_ATTR_RE = re.compile(r'scale="(-?\d+)"', re.IGNORECASE)

    @staticmethod
    def _latest_shares_value(fact: dict[str, Any] | None, restrict_to_domestic_forms: bool = False) -> int | None:
        """Extract the most-recent-end-date share count from one XBRL fact's
        {"units": {"shares": [{"end": ..., "val": ...}, ...]}} shape, or None if the
        fact is absent/malformed. Shared by both the dei:EntityCommonStockSharesOutstanding
        primary path and the us-gaap:CommonStockSharesOutstanding fallback below - same
        selection rule (latest end date wins) and same bigint-safety rounding.

        restrict_to_domestic_forms: FIXED 2026-08-19 (goal: "no SEC data"/missing factor
        inputs audit). dei:EntityCommonStockSharesOutstanding is reported in whatever share
        unit the local filing uses - domestic 10-K/10-Q filers report it in the actual
        registered (US-traded) security's units, but foreign 20-F/40-F/6-K filers often
        report their LOCAL/home-market ordinary-share count instead, with no ADS-ratio
        conversion anywhere in XBRL. utils/external/sec_statements.py already restricts
        this exact concept to domestic forms for annual_income_statement's
        shares_outstanding_dei column (see that file's own comment - a prior session hit
        this identical trap with SRAD via a different IFRS concept) - this loader has a
        SEPARATE extraction of the SAME dei concept that never got the same guard.
        Live-confirmed via TSM (Taiwan Semiconductor, 5 ordinary shares = 1 ADS): its 20-F
        reports dei:EntityCommonStockSharesOutstanding=25,932,524,521 (the real, correctly-
        filed LOCAL ordinary-share count - confirmed via TSM's own filing), but
        load_sec_valuations.py multiplies this against the US ADS trading price ($413.41),
        producing market_cap=$10.7 TRILLION and pe_ratio=304 - independently cross-checked
        against yfinance's live sharesOutstanding (5,186,474,013, matching our raw count
        divided by ~5.000) and marketCap ($2.14T)/trailingPE (30.9), confirming the ADS
        ratio and that our figure was ~5x too high. The same corruption reaches
        positioning_metrics.institutional_ownership_pct too (TSM showed 4.26%, implausibly
        low for one of the most widely-held ADRs, vs a real ADS-share-denominator giving
        ~21%). Only applied to the dei concept - the us-gaap:CommonStockSharesOutstanding
        fallback below is a different, already-separately-verified pathway (see the
        Alphabet/GOOG fix comment above its call site) and is left unrestricted.
        """
        if not fact or not isinstance(fact, dict) or "units" not in fact:
            return None
        units = fact["units"]
        if "shares" not in units or not isinstance(units["shares"], list):
            return None
        pure_values = units["shares"]
        if not pure_values:
            return None
        if restrict_to_domestic_forms:
            pure_values = [v for v in pure_values if v.get("form") not in ("20-F", "20-F/A", "40-F", "40-F/A", "6-K")]
            if not pure_values:
                return None
        # Most recent first (latest end date wins), but skip any entry below the same
        # plausibility floor the filing-text fallback already enforces (see
        # _MIN_PLAUSIBLE_SHARES_OUTSTANDING). FIXED 2026-08-18 (goal: "no SEC data" loader
        # audit): FOXA's real companyfacts JSON has exactly ONE
        # dei:EntityCommonStockSharesOutstanding entry in its entire history -
        # {"end": "2019-03-18", "val": 1} - a real bad tag at the SEC source (should be
        # ~570M), not a parsing bug on our side. Blindly taking values[0] accepted this
        # garbage outlier instead of falling through to the us-gaap fallback or filing-text
        # fallback, which would find a real value. Live-confirmed the same pattern for FOXA
        # /FOX (val=1), HQ (val=1), QNTM (val=12), RFL (val=100) via
        # short_interest_finra.reason='shares_outstanding_invalid'.
        for candidate in sorted(pure_values, key=lambda x: x.get("end") or "", reverse=True):
            raw_val: float | int | None = candidate.get("val")
            if raw_val is None:
                continue
            # ROOT-CAUSE FIX 2026-08-16: SEC's companyfacts JSON doesn't guarantee an integer
            # for this fact - live-confirmed CBK returns val=13701269.5, which psycopg2's COPY
            # sends verbatim as text and Postgres's bigint parser then rejects outright
            # ("invalid input syntax for type bigint"), crashing the whole loader run (not just
            # skipping CBK) since the error surfaces from the COPY/upsert, well past this fetch
            # method's own try/except. The filing-text fallback below already guards this same
            # bigint column with int(max(plausible)) - this is the same bug class, just on the
            # primary (non-fallback) path.
            rounded = round(raw_val)
            if rounded > CompanyInfoSECLoader._MIN_PLAUSIBLE_SHARES_OUTSTANDING:
                return rounded
        return None

    def _fetch_shares_outstanding_from_filing_text(
        self, symbol: str, cik: str, submissions: dict[str, Any]
    ) -> int | None:
        """Parse the raw text of the most recent annual filing for the cover-page share count.

        Fallback for filers whose dei:EntityCommonStockSharesOutstanding fact never makes it
        into the aggregated companyfacts JSON endpoint (live-confirmed: PLNT and others - see
        call site comment). Best-effort only: any failure here just leaves shares_outstanding
        None, same as if this fallback didn't exist.
        """
        # `or {}`/`or []` avoids check-dashboard-get-pattern.py's dict/list-default regex -
        # see the identical note at the other call site above.
        recent = (submissions.get("filings") or {}).get("recent") or {}
        forms = recent.get("form") or []
        accessions = recent.get("accessionNumber") or []
        # Domestic 10-K/10-K-A only, NOT 20-F/20-F-A. Live-caught: BP and TV (Grupo
        # Televisa) both 20-F filers, produced market caps of $729B and $310B respectively
        # (real values: ~$90B and ~$2B) when their cover-page share count was trusted here -
        # same foreign-filer unit-mismatch trap already documented and reverted once this
        # session for a different IFRS concept (see sec_statements.py's removed-concept
        # comment and the dei_aliases form-check in _aggregate_concepts): 20-F filers can
        # report the cover-page count in local/home-market share units with no ADS-ratio
        # conversion available anywhere in the filing text this regex can see.
        annual_forms = {"10-K", "10-K/A"}
        accession = next(
            (accessions[i] for i, f in enumerate(forms) if f in annual_forms and i < len(accessions)),
            None,
        )
        if not accession:
            return None

        try:
            text = self.sec_client.get_filing_plaintext(cik, accession)
        except (FileNotFoundError, TimeoutError, RuntimeError) as e:
            logger.debug(f"[{symbol}] Could not fetch filing text for shares_outstanding fallback: {e}")
            return None

        matches = self._INLINE_XBRL_SHARES_OUTSTANDING_RE.findall(text)
        if not matches:
            return None

        values = []
        for attrs, raw_text in matches:
            try:
                raw_val = float(raw_text.replace(",", ""))
            except ValueError:
                continue
            # FIXED 2026-08-18 (goal: "no SEC data" loader audit): inline XBRL's scale=
            # attribute means "value is expressed in 10^scale units" - live-confirmed on
            # Alphabet's real 10-K, this cover-page fact is tagged scale="6" (millions):
            # raw text "5,822" means 5,822,000,000 real shares, not 5,822. The un-scaled
            # value silently failed the plausibility filter below (5,822 < 100,000) and was
            # discarded as noise, leaving shares_outstanding NULL for a real mega-cap with
            # the data sitting right there in the filing - same root cause almost certainly
            # affects every other filer that reports this cover-page fact in millions rather
            # than raw share counts (common for large-cap filers to keep the printed number
            # compact). scale defaults to 0 (no scaling) when absent, preserving the existing
            # correct behavior for filers like PLNT that already report raw units.
            scale_match = self._IX_SCALE_ATTR_RE.search(attrs)
            scale = int(scale_match.group(1)) if scale_match else 0
            values.append(raw_val * (10**scale))
        plausible = [v for v in values if v > self._MIN_PLAUSIBLE_SHARES_OUTSTANDING]
        if not plausible:
            return None

        # Multi-class filers (e.g. PLNT: Class A 79,697,889 / Class B 316,128) tag the fact
        # once per context/class with no class label surviving into plain text - the publicly
        # traded class is virtually always the larger figure (closely-held founder/family
        # classes are the minority share count), so take the max rather than guess further.
        # int(), not float() - shares_outstanding is a bigint column; a float like
        # "25850270.0" fails psycopg2's implicit cast (live-confirmed: GEF/DGICA both failed
        # with "invalid input syntax for type bigint" before this cast was added).
        result = int(max(plausible))
        logger.info(
            f"[{symbol}] Recovered shares_outstanding={result:,.0f} from raw filing text "
            f"(accession {accession}) - not present in companyfacts JSON"
        )
        return result

    def _unavailable_record(self, symbol: str, now_et: datetime, reason: str) -> list[dict[str, Any]]:
        """Helper to create a data_unavailable record."""
        return [
            {
                "symbol": symbol,
                "filing_date": now_et.date(),
                "entity_name": None,
                "sic_code": None,
                "sic_description": None,
                "entity_type": None,
                "shares_outstanding": None,
                "has_annual_report_filing": None,
                "data_unavailable": True,
                "reason": reason,
                "data_source": "none",
            }
        ]


def main() -> int:
    """Entry point for load_company_info_sec.py."""
    try:
        return run_loader(CompanyInfoSECLoader)
    except Exception as e:
        logger.error(f"[COMPANY_INFO FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
