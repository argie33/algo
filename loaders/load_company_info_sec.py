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
from datetime import date, datetime, timedelta
from typing import Any

from loaders.helpers.company_info_sec_reason_cleanup import clear_stale_shares_outstanding_reason
from loaders.helpers.sec_base import SecLoaderBase
from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.db.context import DatabaseContext
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
        # FIX 2026-08-21 (goal session - digging into a live SEC XBRL loading run): same bug
        # class already fixed for load_financial_statements.py (see
        # utils/bulk_insert_manager.py's preserve_on_missing_fields docstring) but never
        # applied here. primary_key=("symbol",) means this loader's every run does an
        # ON CONFLICT DO UPDATE against the SAME row per symbol - without this, a single
        # transient/point-in-time miss (e.g. the ticker cache's live-verified 149-symbol SEC
        # data-completeness gap, or SEC's browse-edgar fallback endpoint returning a
        # no-results page for a ticker it's inconsistent about) writes an all-NULL
        # _unavailable_record() that unconditionally overwrites real entity_name/sic_code/
        # shares_outstanding this symbol already had on file. Live-confirmed: AXIA, BNZI,
        # BRNX, FRBA, GRAF, GV, HIFS, IA all have 5-12 real annual_income_statement rows
        # (proving a CIK was resolved before) but got their entity_name/sic_code wiped to
        # NULL mid-run today by exactly this path. data_unavailable/reason/data_source/
        # filing_date are excluded - those must always reflect the CURRENT run's real
        # assessment, never a stale one, matching load_financial_statements.py's own carve-out.
        self._bulk_insert_mgr.preserve_on_missing_fields = frozenset(
            {
                "entity_name",
                "sic_code",
                "sic_description",
                "entity_type",
                "shares_outstanding",
                "shares_outstanding_unavailable_reason",
                "has_annual_report_filing",
            }
        )

    def post_run(self) -> None:
        """Self-heal: see company_info_sec_reason_cleanup.py's docstring."""
        clear_stale_shares_outstanding_reason()

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
            #
            # FIXED 2026-08-30 (goal: full-data audit): the original `any(...)` check had no
            # recency bound - a filer that permanently converted FROM a foreign private issuer
            # TO a domestic filer stays misclassified forever, since its old 20-F/6-K history
            # never leaves SEC's "recent" filings array. Live-confirmed via AKTX (Akari
            # Therapeutics): its last 6-K was filed 2023-12-01, and every annual/quarterly
            # report since (10-K filed 2024-03-29 through the current 10-Q filed 2026-08-13)
            # is domestic-form - it stopped being an FPI over two years ago, yet `any()` still
            # returned True. DEF 14A and Form 4 filings in that same recent history are
            # independent confirmation: FPIs are exempt from both, so their presence alone
            # proves current non-FPI status. FPI status is determined by the MOST RECENT
            # annual report on file (10-K/10-K-A vs 20-F/20-F-A/40-F/40-F-A), not by whether a
            # foreign form ever appeared historically - recent_forms is newest-first (same
            # ordering assumption _fetch_shares_outstanding_from_filing_text already relies
            # on). Falls back to the original any-6-K behavior only when no annual report of
            # either kind exists yet in the recent window (a genuinely new/recently-registered
            # filer), matching the prior conservative default for that edge case.
            annual_report_forms_recent_first = [
                f for f in recent_forms if f in ("10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A")
            ]
            if annual_report_forms_recent_first:
                is_foreign_private_issuer = annual_report_forms_recent_first[0] in (
                    "20-F",
                    "20-F/A",
                    "40-F",
                    "40-F/A",
                )
            else:
                is_foreign_private_issuer = any(f in ("20-F", "20-F/A", "40-F", "40-F/A", "6-K") for f in recent_forms)

            # Get shares outstanding from DEI facts (if available)
            shares_outstanding = None
            shares_outstanding_end_date: str | None = None
            facts_obj: dict[str, Any] | None = None
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
                        dei_entry = self._latest_shares_entry(
                            dei_facts.get("EntityCommonStockSharesOutstanding"), restrict_to_domestic_forms=True
                        )
                        if dei_entry:
                            shares_outstanding = dei_entry["rounded_val"]
                            shares_outstanding_end_date = dei_entry["end"]
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
                    # FIXED 2026-08-19 (migration 1211 follow-up, goal: "no SEC data"/missing
                    # factor inputs audit): this fallback was assumed safe without the
                    # domestic-forms restriction ("a different, already-separately-verified
                    # pathway" - see load_sec_valuations.py's shares_out tier-gating comment,
                    # written before this was checked). Live-confirmed WRONG via AEM (Agnico
                    # Eagle Mines): its only us-gaap:CommonStockSharesOutstanding fact anywhere
                    # in its real companyfacts history is a single, 14-YEAR-STALE value
                    # (170,880,330, filed under a 6-K in 2012 - AEM tags nothing under this
                    # concept since, having moved fully to ifrs-full) - independently cross-
                    # checked against yfinance's live sharesOutstanding (506,364,864, ~3x
                    # higher, not even a clean ratio, just genuinely stale pre-merger data).
                    # This concept isn't ADR-ratio-specific like the dei case above (some
                    # foreign filers, e.g. AEM/SHOP/WIX, list directly with no ADS wrapper at
                    # all, so a CURRENT foreign-form fact would actually be fine) - the real
                    # risk demonstrated here is a stale historical fact never refreshed once a
                    # filer stopped tagging us-gaap concepts, which the same restriction
                    # incidentally also guards against.
                    if shares_outstanding is None:
                        gaap_facts = facts_obj.get("us-gaap") if isinstance(facts_obj, dict) else None
                        if isinstance(gaap_facts, dict):
                            gaap_entry = self._latest_shares_entry(
                                gaap_facts.get("CommonStockSharesOutstanding"), restrict_to_domestic_forms=True
                            )
                            if gaap_entry:
                                shares_outstanding = gaap_entry["rounded_val"]
                                shares_outstanding_end_date = gaap_entry["end"]

                    # Reverse-split/stale-instant-concept override - see
                    # _weighted_average_shares_override's own docstring for the FUBO/AMRN
                    # evidence. Only applies when we have both a candidate AND its end date
                    # (i.e. it came from the dei/us-gaap tiers above, not the filing-text
                    # fallback below, which has no comparable per-fact end date).
                    if shares_outstanding is not None and shares_outstanding_end_date:
                        override = self._weighted_average_shares_override(
                            facts_obj, shares_outstanding, shares_outstanding_end_date, symbol
                        )
                        if override is not None:
                            shares_outstanding = override
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

            # ADDED 2026-09-02 (SEC/XBRL missing-data sweep): us-gaap:WeightedAverageNumber
            # OfSharesOutstandingBasic as a genuine last-resort SOURCE - not just the
            # staleness-override comparator _weighted_average_shares_override uses above -
            # when this filer tags NEITHER dei:EntityCommonStockSharesOutstanding NOR
            # us-gaap:CommonStockSharesOutstanding at all (so the two tiers above never even
            # produce a candidate to override), AND the raw-filing-text fallback just above
            # also found nothing. Live-confirmed real, previously-unrecovered gap via AMRC
            # (Ameresco) and MWH: both have zero entries for either instant concept in their
            # entire companyfacts history, but a fresh, real WeightedAverageNumberOfShares
            # OutstandingBasic exists every quarter - a DURATION concept every filer needs for
            # its own EPS calc, so it's tagged far more reliably than the instant concepts
            # (same reasoning _weighted_average_shares_override's own docstring already
            # documents for FUBO/AMRN, just applied here as a primary source instead of an
            # override). Only trusted when this CIK has exactly one non-preferred registered
            # ticker (same ambiguity guard _fetch_shares_outstanding_from_filing_text's
            # multi_ticker_cik check above already uses) - a dual/multi-class filer's combined
            # total can't be safely assigned to one specific class without per-class
            # dimensional data, which companyfacts doesn't expose (see that function's own
            # BRK.A/BRK.B/HEI comment) - live-confirmed this correctly still excludes MKC/MKC.V,
            # TR, DDS, RUM, and every other dual-class symbol checked, leaving them on the
            # existing conservative "cannot determine which class" behavior, unchanged.
            if shares_outstanding is None and isinstance(facts_obj, dict):
                raw_tickers = submissions.get("tickers") or []
                common_tickers = [
                    t
                    for t in raw_tickers
                    if not self._PREFERRED_TICKER_SUFFIX_RE.search(t)
                    and t not in self._NON_COMMON_SECURITY_TICKERS
                    and not self._is_spac_unit_warrant_right_ticker(t, raw_tickers)
                ]
                if len(common_tickers) <= 1:
                    gaap_facts = facts_obj.get("us-gaap")
                    if isinstance(gaap_facts, dict):
                        wavg_entry = self._latest_shares_entry(
                            gaap_facts.get("WeightedAverageNumberOfSharesOutstandingBasic"),
                            restrict_to_domestic_forms=True,
                        )
                        if wavg_entry:
                            shares_outstanding = wavg_entry["rounded_val"]
                            logger.info(
                                f"[{symbol}] Recovered shares_outstanding={shares_outstanding:,} from "
                                "WeightedAverageNumberOfSharesOutstandingBasic - neither dei nor "
                                "us-gaap instant concept nor filing text had a usable value"
                            )

            shares_outstanding_unavailable_reason = None
            if shares_outstanding is None:
                # FIX 2026-09-04 (goal: "Missing SEC/XBRL data" reduction to zero,
                # inconsistent-preserved-pair bug class): `shares_outstanding` is one of this
                # loader's `preserve_on_missing_fields` columns (see __init__'s comment) - when
                # THIS run's fetch comes back None, the bulk insert's COALESCE preserves
                # whatever real value the symbol already had on file, so the row's actual
                # `shares_outstanding` stays non-NULL. But this reason column is ALSO in that
                # preserve set, and unlike `shares_outstanding` it was never None going into the
                # insert (a real string gets computed unconditionally right below) - so it does
                # NOT get COALESCE-preserved, it overwrites the old (correctly NULL) reason with
                # a fresh "unavailable" label. Live-confirmed 66 active-universe rows (DDS, MKC,
                # WLY, WSO, AGM, AMH, ARTNA, ATRO among them) carry a REAL, non-NULL
                # shares_outstanding value (correctly preserved) sitting next to this
                # contradictory "not found" reason (freshly overwritten) - every one of these
                # counts as a live "Missing SEC/XBRL data" gap on the coverage dashboard despite
                # having real data. Checking the existing DB value first and leaving the reason
                # None (so it gets COALESCE-preserved too, back to whatever it correctly was)
                # keeps the pair consistent instead of re-deriving a reason for a value this run
                # never actually re-examined.
                with DatabaseContext("read") as cur:
                    cur.execute(
                        "SELECT shares_outstanding FROM company_info_sec WHERE symbol = %s",
                        (symbol,),
                    )
                    _existing_row = cur.fetchone()
                _existing_shares_outstanding = _existing_row[0] if _existing_row else None
                if _existing_shares_outstanding is not None:
                    shares_outstanding_unavailable_reason = None
                # Live audit (goal session, "Ownership data unresolved" bucket
                # investigation, 2026-08-23) decomposed 1,237 active-universe NULL
                # shares_outstanding rows into exactly these 3 buckets by hand - surface it
                # directly instead of requiring the same manual SQL archaeology next time.
                # See migration 1201's own comment for the full live evidence per bucket.
                elif is_foreign_private_issuer:
                    shares_outstanding_unavailable_reason = "fpi_shares_excluded_domestic_only"
                elif not has_annual_report_filing:
                    shares_outstanding_unavailable_reason = "no_annual_report_filing"
                else:
                    shares_outstanding_unavailable_reason = "shares_outstanding_not_in_xbrl_or_filing_text"

            return [
                {
                    "symbol": symbol,
                    "filing_date": now_et.date(),
                    "entity_name": entity_name,
                    "sic_code": sic_code,
                    "sic_description": sic_description,
                    "entity_type": entity_type,
                    "shares_outstanding": shares_outstanding,
                    "shares_outstanding_unavailable_reason": shares_outstanding_unavailable_reason,
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

    # Shared with _latest_shares_value's identical cutoff below (FIXED 2026-08-20, AEM/AI
    # stale-fact case) - a share-count fact more than 2 years old may reflect a capital
    # structure (dilution, reverse split, FPI conversion) that no longer holds today.
    _STALENESS_CUTOFF_DAYS = 730

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
    _IX_CONTEXTREF_ATTR_RE = re.compile(r'contextRef="([^"]+)"', re.IGNORECASE)

    # ADDED 2026-08-22 (goal session - "BRK.B and those types" follow-up): the
    # multi_ticker_cik guard just above (2026-08-21) correctly stops guessing when a filing
    # tags shares_outstanding once per share class with no visible label - but SEC's inline
    # XBRL DOES carry the class label, just not in the plain-text-converted view this
    # function's plaintext regex sees: each <ix:nonFraction> has a contextRef pointing at an
    # <xbrli:context> block whose <xbrldi:explicitMember dimension="...ClassOfStockAxis">
    # names the exact class (e.g. "us-gaap:CommonClassAMember"). Live-confirmed this is the
    # real, standard US-GAAP taxonomy convention SEC filers use for this - verified directly
    # against Berkshire Hathaway's (CIK 1067983) and Lennar's (CIK 920760) real, current 10-Q
    # inline XBRL: both tag exactly one context per class under
    # us-gaap:StatementClassOfStockAxis with us-gaap:CommonClass{A,B}Member, and the values
    # match the real, independently-known share counts for each class (Berkshire ~488K
    # Class A / ~1.4B Class B; Lennar ~210.5M Class A / ~30.4M Class B). Resolving via this
    # dimension - not a per-filer naming guess - lets a dot-suffixed ticker (BRK.A, BRK.B,
    # LEN.B, ...) claim its OWN class's real value instead of being permanently left NULL
    # alongside its sibling.
    # FIXED 2026-09-04 (SEC/XBRL missing-data sweep, DGICA/DGICB shares_outstanding
    # investigation): hardcoded `id="{}"` immediately after `<xbrli:context` assumed `id` is
    # always the tag's only/first attribute - live-confirmed via Donegal Group's real, current
    # 10-K (CIK 800457, accession 0001140361-26-008268) inline XBRL: its embedded contexts are
    # tagged `<xbrli:context xmlns="" id="c4">` (an extra `xmlns=""` reset attribute some
    # filing agents inject before `id` when a context is embedded inline in the HTML body
    # rather than as a separate XBRL exhibit) - the exact-match template never found context
    # "c4"/"c5", so `_class_letter_for_context` always returned None here and both DGICA and
    # DGICB fell through to the ambiguous-reject path despite the filing actually tagging
    # Class A (31,426,189) and Class B (5,576,775) shares distinctly under
    # us-gaap:StatementClassOfStockAxis, same shape as the already-working BRK/LEN case. Now
    # tolerates any attributes before AND after `id="..."`.
    _CONTEXT_BLOCK_RE_TEMPLATE = r'<xbrli:context\b[^>]*\bid="{}"[^>]*>.*?</xbrli:context>'
    _CLASS_OF_STOCK_MEMBER_RE = re.compile(r'dimension="[^"]*ClassOfStockAxis"[^>]*>\s*([\w:.-]+)\s*<', re.IGNORECASE)
    _CLASS_LETTER_FROM_MEMBER_RE = re.compile(r"Class([A-Z])(?:Member)?\b")
    # FIXED 2026-09-04 (same sweep, continued): Liberty Media family tracking-stock spinoffs
    # (FWONA/FWONK Liberty Formula One, GLIBA/GLIBK Liberty Capital/GCI, LLYVA/LLYVK Liberty
    # Live, BATRA/BATRK Atlanta Braves Holdings) all name their security "Series {LETTER}",
    # never "Class {LETTER}", in stock_symbols.security_name - live-confirmed each ticker's
    # real security_name (e.g. "Liberty Media Corporation - Series A Liberty Formula One
    # Common Stock") - so the Class-only pattern always returned None for every one of these,
    # blocking `_target_class_letter` before it could even attempt dimensional resolution.
    # Their underlying XBRL member is still the standard "CommonClass{A,B,C}Member" shape
    # (live-confirmed via Liberty Media's real 10-K, CIK 1560385: contextRef ids embed
    # "...LibertyFormulaOneGroupCommonClassBMember..."), so once the letter is recovered from
    # "Series {LETTER}" it lines up correctly with the same class-letter matching used for
    # Class-labeled filers.
    _CLASS_LETTER_FROM_SECURITY_NAME_RE = re.compile(r"\b(?:Class|Series)\s+([A-Z])\b")
    # FIXED 2026-09-04 (same sweep): some filers (Liberty Media family, via Workiva-style
    # generators) embed the full dimension/member name directly in the contextRef id string
    # itself (e.g. "As_Of_1_31_2026_us-gaap_StatementClassOfStockAxis_lmca_
    # LibertyFormulaOneGroupCommonClassBMember_Se1lZdhv3k...") rather than defining a separate
    # short <xbrli:context id="c4"> block elsewhere with a nested explicitMember - live-
    # confirmed via Liberty Media's real 10-K. `_class_letter_for_context` below tries this
    # cheap direct match on the id string first (avoids a full-document context-block search
    # entirely when the id is already self-describing) before falling back to the
    # <xbrli:context> block lookup for filers with opaque short ids like Donegal's "c4"/"c5".
    # Anchored to "CommonClass...Member" specifically (not the looser Class-letter pattern
    # above) so it can't false-match "StatementClassOfStockAxis" itself, which is always
    # present in the same id string and would otherwise wrongly yield letter "O".
    _COMMON_CLASS_MEMBER_IN_ID_RE = re.compile(r"CommonClass([A-Z])Member")

    # ADDED 2026-09-02 (goal: SEC/XBRL missing-data sweep). multi_ticker_cik below exists to
    # detect genuine multi-COMMON-class ambiguity (BRK-A/BRK-B, HEI/HEI-A), but was counting
    # EVERY registered ticker on the CIK - including preferred-stock series, which use the
    # standard exchange convention BASE-P<letter> (e.g. F-PB/F-PC/F-PD, AGM-PD..PI, AMH-PG/PH,
    # SF-PB/PC/PD) and never carry their own dei:EntityCommonStockSharesOutstanding fact
    # competing with the common ticker's. Live-confirmed this falsely triggered the "cannot
    # determine which class" reject for F and AMH even though each has exactly one real common
    # class in the filing text (F: us-gaap:CommonStockMember 3,918,623,149 vs the non-traded
    # us-gaap:CommonClassBMember 70,852,076 - the existing "take the max" logic already handles
    # that correctly once the false ambiguity signal is removed) - both live-verified against
    # their actual, current 10-K inline XBRL and submissions.json ticker lists.
    _PREFERRED_TICKER_SUFFIX_RE = re.compile(r"-P[A-Z]+$", re.IGNORECASE)

    # FIXED 2026-09-03 (SEC/XBRL missing-data sweep, interest_expense_not_itemized
    # investigation follow-up): same false-ambiguity bug class as the preferred-suffix regex
    # above, for exchange-traded DEBT securities (baby bonds/subordinated notes) registered
    # on the same CIK as a common stock - these never carry a competing
    # dei:EntityCommonStockSharesOutstanding fact either, but don't follow the preferred
    # stock "-P<letter>" naming convention so the regex above doesn't catch them. Unlike
    # preferred stock, exchange-traded notes have no consistent ticker-spelling convention
    # (SFB has no dash, no "P", nothing that generalizes to a regex) - live-confirmed via
    # SF's (Stifel Financial) real submissions.json ticker list (['SF', 'SF-PB', 'SFB',
    # 'SF-PC', 'SF-PD']) and its own dei:EntityCommonStockSharesOutstanding history (real
    # data through 2019-08-01, nothing since - SF simply stopped tagging the DEI cover-page
    # instant fact, same pattern as ATRO/GTN below) that SFB is Stifel's 6.25% Subordinated
    # Notes due 2054, not a second common share class - SF's real, current
    # WeightedAverageNumberOfSharesOutstandingBasic (154.9M as of FY2026 Q2) was sitting
    # unused because `multi_ticker_cik` saw ['SF', 'SFB'] (2 entries after the preferred
    # filter) and conservatively refused to pick a class. An explicit, individually-verified
    # set rather than a pattern match, same "don't guess, only add what's been checked"
    # discipline as SHARED_ISSUER_OR_TRUST_CIK_SYMBOLS in load_financial_statements.py - add
    # to this set only after confirming via real submissions.json + dei history that the
    # extra ticker is a bond/note, not an untracked common class.
    #
    # ADDED 2026-09-03 (same sweep, continued bucket walk): DDT (Dillard's 7.5% Cumulative
    # Preferred Stock, same CIK as DDS) is the same false-ambiguity shape but for PREFERRED
    # stock spelled without the "-P<letter>" convention the regex expects - live-confirmed
    # via DDS's real companyfacts JSON (CIK 28917): zero dei:EntityCommonStockSharesOutstanding
    # or us-gaap:CommonStockSharesOutstanding facts under EITHER ticker (consistent with a
    # single consolidated CIK reporting one real common class), but a real, current
    # WeightedAverageNumberOfSharesOutstandingBasic (~15.6-15.65M across 2025 Q3/2026 Q1 10-Qs)
    # that `multi_ticker_cik` was blocking because it saw ['DDS', 'DDT'] (2 entries). This set's
    # name is "non-COMMON-security", not "non-debt" - preferred stock belongs here too, same as
    # SFB.
    _NON_COMMON_SECURITY_TICKERS: frozenset[str] = frozenset({"SFB", "DDT"})

    # ADDED 2026-09-04 (SEC/XBRL missing-data sweep): same false-ambiguity bug class as
    # _PREFERRED_TICKER_SUFFIX_RE/_NON_COMMON_SECURITY_TICKERS above, for SPAC unit/warrant/
    # rights tickers sharing a CIK with the underlying common stock (e.g. TWLV/TWLVU/TWLVR,
    # SVCC/SVCCU/SVCCW, JACS/JACS-UN/JACS-RI, BEBE/BEBE-UN/BEBE-WT) - live-confirmed via
    # submissions.json for TWLV/SVCC/JACS/HVMC/CHEC/BEBE, all pre-merger 2026-vintage SPAC
    # shells with exactly one real common class but 2-3 registered tickers, all currently
    # blocked from shares_outstanding recovery by the `len(common_tickers) <= 1` /
    # `multi_ticker_cik` guards. Matched relative to another ticker already in the same CIK's
    # list (never a bare suffix heuristic) so a real standalone ticker that happens to end in
    # U/W/R can't be misclassified - it only fires when stripping a known SPAC suffix from one
    # ticker yields another ticker also registered on the same CIK.
    _SPAC_UNIT_WARRANT_RIGHT_SUFFIXES: frozenset[str] = frozenset({"U", "W", "R", "WS", "RT", "UN", "WT", "RI"})

    @classmethod
    def _is_spac_unit_warrant_right_ticker(cls, ticker: str, all_tickers: list[str]) -> bool:
        """True if `ticker` is a SPAC unit/warrant/rights ticker derived from another
        common-stock ticker in `all_tickers` (e.g. "TWLVU" derived from "TWLV",
        "JACS-UN" derived from "JACS")."""
        base, _, dash_suffix = ticker.partition("-")
        if dash_suffix and dash_suffix.upper() in cls._SPAC_UNIT_WARRANT_RIGHT_SUFFIXES and base in all_tickers:
            return True
        for other in all_tickers:
            if other == ticker or not ticker.upper().startswith(other.upper()):
                continue
            bare_suffix = ticker[len(other) :]
            if bare_suffix.upper() in cls._SPAC_UNIT_WARRANT_RIGHT_SUFFIXES:
                return True
        return False

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
        #
        # FIXED 2026-08-20 (goal: finance-accuracy audit): the AEM comment above ("the real
        # risk demonstrated here is a stale historical fact never refreshed once a filer
        # stopped tagging us-gaap concepts") was only ever addressed via
        # restrict_to_domestic_forms - which does nothing for a DOMESTIC filer whose OWN dei
        # concept goes stale. Live-confirmed via AI (C3.ai): its dei:
        # EntityCommonStockSharesOutstanding history's newest entry is {"end": "2021-...",
        # "val": 3499992} - a real, once-valid, now 5-year-stale filing (C3.ai IPO'd
        # Dec 2020) - while annual_income_statement.shares_outstanding_basic (a different
        # concept, refreshed every fiscal year) correctly shows 140,513,000 for FY2026, ~40x
        # higher. This function had no notion of "the latest entry I found might itself be
        # too old to trust" - it only ever compared candidates against EACH OTHER, never
        # against today. The stale 3.5M value then propagated into sec_valuations (via its
        # company_info_sec cross-check, since both agreed - the same shared-root-cause blind
        # spot as the ONC/BeOne Medicines case) and into short_interest_finra, where it
        # inflated short_pct to 1323% for a stock with genuinely single-digit-to-teens real
        # short interest. A stale entry now correctly falls through to the us-gaap fallback
        # (or ultimately shares_outstanding=None) instead of being trusted just because it
        # was the newest entry within its own narrow concept's history.
        entry = CompanyInfoSECLoader._latest_shares_entry(fact, restrict_to_domestic_forms)
        return int(entry["rounded_val"]) if entry else None

    @staticmethod
    def _latest_shares_entry(
        fact: dict[str, Any] | None, restrict_to_domestic_forms: bool = False
    ) -> dict[str, Any] | None:
        """Same selection as `_latest_shares_value` (latest-end-date-within-staleness-cutoff,
        above the plausibility floor) but returns the winning candidate itself (`end` date +
        `rounded_val`), not just the bare value - added 2026-08-31 (goal: data-coverage sweep,
        reverse-split follow-up to
        [[sec_valuations_frozen_yfinance_snapshot_live_recheck_fixed_20260831]]) so callers can
        compare this candidate's recency against a DIFFERENT concept's candidate (see
        `_weighted_average_shares_override` below) - `_latest_shares_value` alone throws the
        `end` date away, so nothing could ever tell "this value is current" from "this value is
        the newest thing an otherwise-stale concept happens to have".
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
        staleness_cutoff = (date.today() - timedelta(days=CompanyInfoSECLoader._STALENESS_CUTOFF_DAYS)).isoformat()
        for candidate in sorted(pure_values, key=lambda x: x.get("end") or "", reverse=True):
            end_date = candidate.get("end")
            if not end_date or end_date < staleness_cutoff:
                continue
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
                return {"end": end_date, "rounded_val": rounded}
        return None

    # ADDED 2026-08-31 (goal: data-coverage sweep, reverse-split follow-up). Live-confirmed via
    # FUBO (1-for-12 reverse split effective 2026-03-23, confirmed via SEC filing history and
    # web search) and AMRN (1-for-20, 2025-04-11): both `dei:EntityCommonStockSharesOutstanding`
    # and `us-gaap:CommonStockSharesOutstanding` simply stopped being tagged AT ALL after the
    # split (FUBO: nothing past end=2025-09-30 despite 3 more 10-Qs filed since, confirmed via
    # SEC's own companyconcept API) - so `_latest_shares_entry` above correctly finds a "recent
    # enough" (within the 730-day cutoff) but factually stale, pre-split candidate and has no way
    # to know a fresher truth exists. `us-gaap:WeightedAverageNumberOfSharesOutstandingBasic` (a
    # DURATION concept, needed for every filer's own EPS calculation, so tagged far more
    # reliably every quarter) DOES have the fresh, correct, post-split value in both live cases
    # (FUBO: 31,055,542 for the 9mo ended 2026-06-30, filed 2026-08-05 - the real post-split
    # count is ~29-30M per Morningstar) - this override picks it up ONLY when it is BOTH
    # meaningfully fresher (>=120 days newer `end` date - ordinary quarterly cadence, not noise)
    # AND meaningfully different (>=1.3x ratio - a real split/major share-count event, not
    # routine drift) than the existing instant-concept candidate, so a filer that just doesn't
    # happen to have a recent instant-concept fact for an ordinary reason (e.g. only tags it
    # annually) is untouched. Fails closed (returns None, no override) on any missing/malformed
    # data - this only ever REPLACES an already-accepted candidate with a fresher one, never the
    # sole source of a value.
    _WEIGHTED_AVERAGE_OVERRIDE_MIN_FRESHNESS_DAYS = 120
    _WEIGHTED_AVERAGE_OVERRIDE_MIN_RATIO = 1.3

    @staticmethod
    def _weighted_average_shares_override(
        facts_obj: dict[str, Any] | None, current_value: int, current_end_date: str, symbol: str
    ) -> int | None:
        gaap_facts = facts_obj.get("us-gaap") if isinstance(facts_obj, dict) else None
        if not isinstance(gaap_facts, dict):
            return None
        wavg_entry = CompanyInfoSECLoader._latest_shares_entry(
            gaap_facts.get("WeightedAverageNumberOfSharesOutstandingBasic"), restrict_to_domestic_forms=True
        )
        if not wavg_entry:
            return None
        wavg_end = wavg_entry["end"]
        wavg_val = wavg_entry["rounded_val"]
        if wavg_end <= current_end_date:
            return None
        try:
            freshness_days = (
                datetime.strptime(wavg_end, "%Y-%m-%d").date() - datetime.strptime(current_end_date, "%Y-%m-%d").date()
            ).days
        except ValueError:
            return None
        if freshness_days < CompanyInfoSECLoader._WEIGHTED_AVERAGE_OVERRIDE_MIN_FRESHNESS_DAYS:
            return None
        larger, smaller = max(current_value, wavg_val), min(current_value, wavg_val)
        if smaller <= 0 or larger / smaller < CompanyInfoSECLoader._WEIGHTED_AVERAGE_OVERRIDE_MIN_RATIO:
            return None
        logger.warning(
            f"[{symbol}] shares_outstanding override: instant-concept candidate={current_value:,.0f} "
            f"(end={current_end_date}) is {freshness_days}d staler than a "
            f"WeightedAverageNumberOfSharesOutstandingBasic candidate={wavg_val:,.0f} (end={wavg_end}), "
            f"ratio {larger / smaller:.1f}x - likely a stock split/major share event the instant "
            "concept stopped reflecting; using the fresher weighted-average value instead"
        )
        return int(wavg_val)

    @staticmethod
    def _target_class_letter(symbol: str) -> str | None:
        """This symbol's own share class letter, if determinable with confidence.

        Two sources, both conservative (return None rather than guess):
        1. A single-letter dot suffix (BRK.A -> "A", LEN.B -> "B") - the internal symbol
           convention already encodes the class directly, no lookup needed.
        2. For a BARE ticker (no dot) with a dual-class sibling, `stock_symbols.security_name`
           sometimes states the class explicitly (live-confirmed: LEN is literally named
           "Lennar Corporation Class A Common Stock", TAP "...Class B Common Stock") - only
           trusted when that exact "Class {LETTER}" text is present, never inferred from
           context (many bare siblings, e.g. BRK's peers AGM/GTN/HVT/WSO, carry no class text
           in security_name at all and correctly stay unresolved here).
        """
        if "." in symbol:
            suffix = symbol.rsplit(".", 1)[-1]
            if len(suffix) == 1 and suffix.isalpha():
                return suffix.upper()
            return None
        try:
            with DatabaseContext("read") as cur:
                cur.execute("SELECT security_name FROM stock_symbols WHERE symbol = %s", (symbol,))
                row = cur.fetchone()
        except Exception as e:
            logger.debug(f"[{symbol}] Could not look up security_name for class-letter resolution: {e}")
            return None
        if not row or not row[0]:
            return None
        match = CompanyInfoSECLoader._CLASS_LETTER_FROM_SECURITY_NAME_RE.search(row[0])
        return match.group(1).upper() if match else None

    def _class_letter_for_context(self, filing_text: str, context_id: str) -> str | None:
        """The us-gaap:StatementClassOfStockAxis class letter for one <xbrli:context>, or
        None if this context has no such dimension (single-class filers, or an unrelated
        context reused from another fact) or the member name doesn't end in a bare letter.
        """
        id_match = self._COMMON_CLASS_MEMBER_IN_ID_RE.search(context_id)
        if id_match:
            return id_match.group(1).upper()
        context_re = re.compile(
            self._CONTEXT_BLOCK_RE_TEMPLATE.format(re.escape(context_id)), re.IGNORECASE | re.DOTALL
        )
        context_match = context_re.search(filing_text)
        if not context_match:
            return None
        member_match = self._CLASS_OF_STOCK_MEMBER_RE.search(context_match.group(0))
        if not member_match:
            return None
        letter_match = self._CLASS_LETTER_FROM_MEMBER_RE.search(member_match.group(1))
        return letter_match.group(1).upper() if letter_match else None

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
        dates = recent.get("filingDate") or []
        # Domestic 10-K/10-K-A only, NOT 20-F/20-F-A. Live-caught: BP and TV (Grupo
        # Televisa) both 20-F filers, produced market caps of $729B and $310B respectively
        # (real values: ~$90B and ~$2B) when their cover-page share count was trusted here -
        # same foreign-filer unit-mismatch trap already documented and reverted once this
        # session for a different IFRS concept (see sec_statements.py's removed-concept
        # comment and the dei_aliases form-check in _aggregate_concepts): 20-F filers can
        # report the cover-page count in local/home-market share units with no ADS-ratio
        # conversion available anywhere in the filing text this regex can see.
        annual_forms = {"10-K", "10-K/A"}
        # FIXED 2026-08-30 (goal: full-data audit): unlike _latest_shares_value's identical
        # 730-day cutoff (2026-08-20, AEM/AI case), this fallback never checked how old the
        # 10-K it parses actually is - live-confirmed via AKTX (Akari Therapeutics): its most
        # recent 10-K predates its later conversion to a 20-F foreign-private-issuer filer by
        # years, and its cover-page share count (155,758,529,533 - 6.4x NVDA, the real largest
        # share count on file) is a stale, pre-reverse-split/pre-dilution-event figure. Nothing
        # downstream (load_sec_valuations.py's MAX_PLAUSIBLE_SHARES_OUTSTANDING ceiling gates
        # most but not all consumers - e.g. load_institutional_holdings_13f.py reads this
        # column with no ceiling at all) can catch this once it's written, so reject a stale
        # source filing here rather than downstream. `dates` is parallel to `forms`/
        # `accessionNumber` (same shape load_current_reports_8k.py already relies on) - missing
        # or malformed entries are treated as stale (skip) rather than trusted.
        staleness_cutoff = (date.today() - timedelta(days=self._STALENESS_CUTOFF_DAYS)).isoformat()
        accession = next(
            (
                accessions[i]
                for i, f in enumerate(forms)
                if f in annual_forms
                and i < len(accessions)
                and i < len(dates)
                and dates[i]
                and dates[i] >= staleness_cutoff
            ),
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
        values_with_context: list[tuple[float, str | None]] = []
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
            scaled_val = raw_val * (10**scale)
            values.append(scaled_val)
            ctx_match = self._IX_CONTEXTREF_ATTR_RE.search(attrs)
            values_with_context.append((scaled_val, ctx_match.group(1) if ctx_match else None))
        plausible = [v for v in values if v > self._MIN_PLAUSIBLE_SHARES_OUTSTANDING]
        if not plausible:
            return None

        # ADDED 2026-08-22: before falling back to the ambiguous-reject behavior below, try
        # to resolve THIS symbol's own class via the standard us-gaap:StatementClassOfStockAxis
        # dimension on each value's context (see the class-level comment above
        # _CONTEXT_BLOCK_RE_TEMPLATE for the live BRK/LEN verification). Only acts when exactly
        # one plausible value's resolved class letter matches this symbol's own, known class
        # letter - any ambiguity (0 or 2+ matches, or no determinable target letter) falls
        # through to the existing conservative reject unchanged.
        target_letter = self._target_class_letter(symbol)
        if target_letter and len(plausible) > 1:
            dimensional_matches = [
                v
                for v, ctx in values_with_context
                if v > self._MIN_PLAUSIBLE_SHARES_OUTSTANDING
                and ctx is not None
                and self._class_letter_for_context(text, ctx) == target_letter
            ]
            if len(dimensional_matches) == 1:
                result = int(dimensional_matches[0])
                logger.info(
                    f"[{symbol}] Recovered shares_outstanding={result:,.0f} for class '{target_letter}' via "
                    f"StatementClassOfStockAxis dimensional match (accession {accession})"
                )
                return result

        # Multi-class filers (e.g. PLNT: Class A 79,697,889 / Class B 316,128) tag the fact
        # once per context/class with no class label surviving into plain text - the publicly
        # traded class is virtually always the larger figure (closely-held founder/family
        # classes are the minority share count), so take the max rather than guess further.
        #
        # FIXED 2026-08-21 (goal session - "BRK.B and those types" audit): that "larger =
        # public class" assumption is BACKWARDS for filers where the dot-suffixed class
        # itself is the low-share-count, high-price class - live-confirmed BRK.A/BRK.B,
        # BF.A/BF.B, CRD.A/CRD.B, MOG.A/MOG.B all resolve to the IDENTICAL shares_outstanding
        # in company_info_sec (this function has no symbol-vs-context awareness, so both
        # tickers of a pair get whichever value max() picks, regardless of which class was
        # actually asked for). For Berkshire specifically this produced BRK.A market_cap =
        # $1.03 QUADRILLION in value_metrics (real market cap ~$1.1T) - BRK.B's real ~1.39B
        # share count applied to BRK.A's ~$744k/share price, off by the ~1,500:1 A-to-B
        # conversion ratio.
        #
        # FIXED 2026-08-21 (same session, follow-up): the first version of this guard only
        # checked `"." in symbol` - but live-confirmed HEI/HEI.A (HEICO) also share an
        # identical, wrong shares_outstanding, and HEI itself is a BARE ticker (no dot), so
        # the dot-only check let it fall straight through to the same wrong max(). The real
        # signal isn't the requesting symbol's own spelling, it's whether this CIK has more
        # than one registered ticker at all - `submissions["tickers"]` (already fetched,
        # already passed in) reliably lists every class SEC has on file for this CIK
        # (live-confirmed: CIK0001067983 -> ['BRK-B','BRK-A'], CIK0000046619 ->
        # ['HEI','HEI-A']), regardless of which specific symbol/spelling asked. A CIK with
        # only one registered ticker (PLNT) has no cross-contamination risk even when the
        # filing text itself has multiple plausible values (an untracked closely-held class),
        # so max() stays correct there. Kept the dot-suffix check as a defensive OR in case
        # `tickers` is ever missing/malformed in a submissions payload.
        raw_tickers = submissions.get("tickers") or []
        common_tickers = [
            t
            for t in raw_tickers
            if not self._PREFERRED_TICKER_SUFFIX_RE.search(t)
            and t not in self._NON_COMMON_SECURITY_TICKERS
            and not self._is_spac_unit_warrant_right_ticker(t, raw_tickers)
        ]
        multi_ticker_cik = len(common_tickers) > 1
        if len(plausible) > 1 and (multi_ticker_cik or "." in symbol):
            logger.warning(
                f"[{symbol}] {len(plausible)} plausible shares_outstanding values found in "
                f"filing text (accession {accession}) and this CIK has multiple registered "
                "tickers/classes - cannot determine which class this value belongs to, "
                "leaving unavailable rather than risk assigning the wrong sibling's share count."
            )
            return None

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
        """Helper to create a data_unavailable record.

        FIXED 2026-09-02 (SEC/XBRL missing-data sweep, live-caught via FRBA/GV/HIFS/HOS/
        NBN/NUTR/PAAI/QMMM/RCBC/SSBI/TOWN/YFOR all showing shares_outstanding IS NULL with
        shares_outstanding_unavailable_reason ALSO NULL in the active universe): this
        whole-row-failure marker (cik_not_found/submissions_not_found_404/submissions_empty/
        entity_name_not_found - the only 4 call sites) never set shares_outstanding_
        unavailable_reason at all, unlike fetch_incremental's own success-path partial-miss
        branch a few hundred lines up, which always assigns one of its 3 reason buckets
        whenever shares_outstanding comes back None. On a symbol's first-ever load (nothing
        for preserve_on_missing_fields - see __init__'s 2026-08-21 fix - to preserve) that
        left the column permanently NULL: invisible to the coverage dashboard's per-field
        shares_outstanding_unavailable_reason breakdown (a NULL reason never reaches
        _categorize_reason at all, unlike an actual mapped string) even though the row is
        indisputably missing the data. Reusing the same top-level `reason` here is correct,
        not just convenient - every one of these 4 reasons already means "we don't even know
        who this filer is", which subsumes "so we obviously don't know its share count
        either", and all 4 are already mapped to "Missing SEC/XBRL data" in scores.py's
        _COVERAGE_CATEGORY_RULES.
        """
        return [
            {
                "symbol": symbol,
                "filing_date": now_et.date(),
                "entity_name": None,
                "sic_code": None,
                "sic_description": None,
                "entity_type": None,
                "shares_outstanding": None,
                "shares_outstanding_unavailable_reason": reason,
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
