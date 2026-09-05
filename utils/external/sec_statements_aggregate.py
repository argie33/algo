"""XBRL concept-aggregation helpers for utils/external/sec_statements.py, extracted from
that file (2026-09-05, file-size ratchet: it's a Tier-2 bloater flagged for decomposition).
Bodies are verbatim, no logic changed - only moved file. get_balance_sheet/get_income_statement/
get_cash_flow (now in utils/external/sec_balance_sheet.py, sec_income_statement.py,
sec_cash_flow.py respectively - sec_statements.py re-exports them for backward compat) call
_aggregate_concepts as their shared engine for turning raw SEC XBRL concept facts into
normalized statement rows.
"""

import datetime
import logging
from typing import Any

from utils.external.fx_rates import MAJOR_CURRENCIES
from utils.external.sec_statements_entry_resolution import (
    _aggregate_concepts_apply_entry_value,
    _aggregate_concepts_resolve_entry_period,
    _aggregate_concepts_should_replace_entry,
)
from utils.external.sec_statements_shared import _extract_currency_code
from utils.external.sec_statements_unit_context import _aggregate_concepts_build_unit_context

logger = logging.getLogger(__name__)


def _aggregate_concepts(
    client: Any,
    symbol: str,
    concepts: list[str],
    period: str,
    ifrs_aliases: list[tuple[str, str]] | None = None,
    dei_aliases: list[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Pivot multiple concepts into rows keyed by (fiscal_year, fiscal_period).

    Optimized: Uses get_company_facts (1 API call) instead of multiple get_concept calls.
    Gracefully skips concepts that don't exist for this company (e.g., different revenue
    reporting standards across companies).

    Args:
        client: SecEdgarClient instance
        symbol: Stock ticker
        concepts: List of us-gaap XBRL concept names (skipped if not reported by this company)
        period: "annual" or "quarterly"
        ifrs_aliases: Optional (ifrs_concept, target_key) pairs checked against the
            ifrs-full taxonomy for foreign private issuers (20-F/40-F filers) that
            report no us-gaap concepts at all. target_key is the snake_cased key the
            equivalent us-gaap concept would have produced, so callers/field_mapping
            downstream don't need to know which taxonomy a row actually came from.
        dei_aliases: Optional (dei_concept, target_key) pairs checked against the "dei"
            (Document and Entity Information) taxonomy - cover-page facts like the
            as-of-filing-date share count, reported by virtually every registrant
            regardless of accounting standard. Unlike ifrs_aliases, dei facts are present
            even for well-covered us-gaap filers, so target_key MUST be distinct from any
            us-gaap/ifrs target_key sharing a downstream db column, or a cruder cover-page
            fact could silently overwrite a better weighted-average figure - see
            load_financial_statements.py's field_mapping comment on shares_outstanding_dei.

    Returns:
        List of dicts with aggregated concept data

    Raises:
        ValueError: If no XBRL filings found (REIT, investment trust, ETF, etc.)
    """
    _cik, us_gaap_facts, ifrs_facts, dei_facts = _aggregate_concepts_load_company_facts(client, symbol)

    rows: dict[Any, dict[str, Any]] = {}
    fp_filter = "FY" if period == "annual" else ("Q1", "Q2", "Q3", "Q4")
    # See the "implausible fiscal_year" sanity-bound comment further below (BUG FOUND
    # 2026-08-19). SEC XBRL history starts ~2009; 1990 is a deliberately generous floor
    # so it never rejects a real fiscal year, only Excel-serial-style corruption
    # (43465, 43830, ...) or a stray "0". +1 allows a company whose fiscal year hasn't
    # calendar-ended yet to still file forward-looking amendments without tripping this.
    _max_plausible_fiscal_year = datetime.date.today().year + 1

    concept_specs = _aggregate_concepts_build_specs(concepts, ifrs_aliases, dei_aliases)

    for concept, target_key, source in concept_specs:
        units = _aggregate_concepts_lookup_units(concept, source, us_gaap_facts, ifrs_facts, dei_facts)
        if units is None:
            continue

        for _unit, entries in units.items():
            _currency_code = _aggregate_concepts_currency_code(_unit)
            is_major_currency = _currency_code != "USD" and _currency_code in MAJOR_CURRENCIES
            if (
                _currency_code != "USD"
                and len(_currency_code) == 3
                and _currency_code.isalpha()
                and _currency_code.isupper()
                and not is_major_currency
            ):
                continue

            (
                has_annual_report_form,
                _max_annual_report_end,
                has_december_fiscal_year_end,
                _max_end_by_accn,
                _short_span_val_by_accn,
                _fy_by_start_end_val,
            ) = _aggregate_concepts_build_unit_context(entries)

            for entry in entries:
                resolved = _aggregate_concepts_resolve_entry_period(
                    entry,
                    source,
                    period,
                    fp_filter,
                    has_annual_report_form,
                    _max_annual_report_end,
                    has_december_fiscal_year_end,
                    _max_end_by_accn,
                    _short_span_val_by_accn,
                    _fy_by_start_end_val,
                    _max_plausible_fiscal_year,
                    symbol,
                    concept,
                )
                if resolved is None:
                    continue
                fp, period_year, start_date, end_date = resolved

                key = (
                    period_year,
                    fp if period == "quarterly" else "FY",
                )
                row = rows.setdefault(
                    key,
                    {
                        "symbol": symbol,
                        "fiscal_year": period_year,
                        "fiscal_period": fp if period == "quarterly" else "FY",
                        "period_end": end_date,
                        "filed": entry.get("filed"),
                        "form": entry.get("form"),
                    },
                )
                col = target_key
                # Keep latest filing if multiple for same period, EXCEPT: never let a
                # non-primary-statement form (DEF 14A, 8-K, S-1, etc.) outrank a primary
                # annual/quarterly-report form (10-K/10-Q and their foreign-filer
                # equivalents) just because it was filed later. See
                # _aggregate_concepts_should_replace_entry for the full tiebreak history.
                entry_filed = entry.get("filed")
                if not entry_filed:
                    raise ValueError(
                        f"SEC data missing filed date for {symbol} {period}. "
                        f"Cannot determine latest filing without date information. "
                        f"Check SEC data source or API response."
                    )
                entry_form = entry.get("form")

                should_replace, entry_rank, is_instant = _aggregate_concepts_should_replace_entry(
                    entry,
                    entry_filed,
                    entry_form,
                    key,
                    row,
                    col,
                    start_date,
                    end_date,
                    period,
                )
                if should_replace:
                    _aggregate_concepts_apply_entry_value(
                        row,
                        col,
                        entry,
                        entry_rank,
                        is_instant,
                        start_date,
                        end_date,
                        period,
                        is_major_currency,
                        _currency_code,
                    )

    # period_end/filed/form are row bookkeeping set unconditionally above (not XBRL
    # concepts, no target column) - left in, they guaranteed-fire sec_base.py's
    # "Unmapped SEC field" warning on every single row of every symbol across all 6
    # statement tables, drowning real per-symbol unmapped-concept warnings in noise
    # (564,688 lines / 109MB from one 2026-08-14 run, confirmed via log analysis).
    # FIXED 2026-09-05 (migration 1256, "implausible values" sweep): quarterly_income_
    # statement.fiscal_year is the CALENDAR year of each fact's end date (see this
    # function's own "Use period end year as the fiscal year key" comment above) - for a
    # non-December-fiscal-year-end filer this scatters one real fiscal cycle's 4 quarters
    # across two different calendar-year fiscal_year values (AAPL live-confirmed: its real
    # Oct-Dec holiday quarter lands in a LOWER fiscal_year than the Jan-Mar/Apr-Jun quarters
    # that come chronologically after it), so `ORDER BY fiscal_year DESC, fiscal_quarter
    # DESC` does not reliably give true chronological order - see migration 1256's own
    # header for the full evidence. `period_end` (this key's value, already computed above
    # as this row's real end date) is kept ONLY for quarterly extraction, feeding the new
    # quarterly_income_statement.period_end column so consumers can order by a real date
    # instead of guessing from (fiscal_year, fiscal_quarter). Annual extraction still strips
    # it - annual_income_statement has no such column and no such ordering ambiguity (a
    # single fiscal_year value already identifies one row per symbol unambiguously).
    result = []
    for row in rows.values():
        result.append(
            {
                k: v
                for k, v in row.items()
                if not k.startswith("_filed_")
                and not k.startswith("_end_")
                and not k.startswith("_rank_")
                and not k.startswith("_frame_")
                and not k.startswith("_span_")
                and not k.startswith("_is_instant_")
                and k not in ("filed", "form")
                and (k != "period_end" or period == "quarterly")
            }
        )
    # Validate fiscal_year exists before sorting (critical for financial statement ordering)
    for r in result:
        if r.get("fiscal_year") is None:
            raise ValueError(
                f"SEC statements missing fiscal_year for {symbol} {period}. "
                f"Cannot sort or aggregate financial statements without year information. "
                f"Check SEC data source or API response."
            )
    result.sort(key=lambda r: (int(r["fiscal_year"]), r["fiscal_period"] or ""))
    return result


def _aggregate_concepts_load_company_facts(
    client: Any, symbol: str
) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    """Fetch SEC company facts and split out the us-gaap/ifrs/dei taxonomies.

    Extracted from _aggregate_concepts (mechanical extraction, no behavior change).
    """
    cik = client.symbol_to_cik(symbol)

    # Fetch all facts for this company in a single API call.
    # FileNotFoundError (404) means the CIK has no XBRL filings - mutual funds,
    # special-purpose vehicles, REITs, and some investment trusts never file XBRL.
    # GOVERNANCE: Fail-fast on missing data with explicit context.
    try:
        all_facts = client.get_company_facts(cik)
    except FileNotFoundError as e:
        raise ValueError(
            f"[SEC_EDGAR] No XBRL filings found for {symbol} (CIK {cik}). "
            f"Company is likely REIT, investment trust, ETF, or special-purpose vehicle "
            f"that does not file traditional SEC XBRL statements. "
            f"Downstream loaders must mark data_unavailable with this reason."
        ) from e

    # Extract concepts from all_facts. Most US domestic filers report under
    # us-gaap; foreign private issuers (20-F/40-F - ADRs like ABEV, E, AEG, ACB)
    # report under ifrs-full instead, often with ZERO us-gaap concepts present.
    # REITs and investment trusts in particular may use real-estate-focused reporting
    # that doesn't map to standard income statement concepts under either taxonomy.
    facts = all_facts.get("facts")
    if facts is None:
        raise ValueError(
            f"[SEC_EDGAR] SEC API returned no 'facts' key for {symbol} (CIK {cik}). "
            f"Likely REIT, investment trust, or special entity without traditional SEC filing data. "
            f"Downstream loaders must mark data_unavailable with this reason."
        )

    us_gaap_facts = facts.get("us-gaap")
    ifrs_facts = facts.get("ifrs-full")
    dei_facts = facts.get("dei")
    if not us_gaap_facts and not ifrs_facts:
        raise ValueError(
            f"[SEC_EDGAR] SEC API has no US-GAAP or IFRS facts for {symbol} (CIK {cik}). "
            f"Company may be a REIT, investment trust, or special entity without traditional "
            f"SEC filing data under either taxonomy. "
            f"Downstream loaders must mark data_unavailable with this reason."
        )
    return cik, us_gaap_facts, ifrs_facts, dei_facts


def _aggregate_concepts_build_specs(
    concepts: list[str],
    ifrs_aliases: list[tuple[str, str]] | None,
    dei_aliases: list[tuple[str, str]] | None,
) -> list[tuple[str, str, str]]:
    """Build the (xbrl_concept_name, target_key, source) lookup triples.

    Extracted from _aggregate_concepts (mechanical extraction, no behavior change).
    """
    # (xbrl_concept_name, target_key, source) triples to look up: "gaap" specs check
    # us-gaap first and fall back to ifrs-full only if us-gaap has nothing at all for
    # that concept name; "ifrs" alias specs go straight to ifrs-full, never through
    # us-gaap first (preserves exact prior behavior/column names for plain concepts),
    # then dei aliases (looked up only in dei_facts - see this function's dei_aliases
    # docstring for why these must never share a target_key with a us-gaap/ifrs concept).
    #
    # FIXED 2026-08-04: ifrs_aliases used to share the exact same us-gaap-first lookup
    # as plain concepts. That's a silent no-op whenever an ifrs alias's concept name is
    # spelled identically to a real us-gaap concept name ("Assets", "Liabilities",
    # "Goodwill" are valid tags in BOTH taxonomies) and the filer has ANY us-gaap entry
    # under that name - even a stale one from years before they were IFRS-only. Live-
    # confirmed via ASR (Grupo Aeroportuario del Sureste): us-gaap:Assets has exactly 2
    # entries (FY2016-2017, filed 2018), so both the plain spec AND the "Assets" ifrs
    # alias spec found that same stale us-gaap data and neither ever reached
    # ifrs-full:Assets's real 2018-2024 entries - total_assets/total_liabilities came
    # back NULL every year since 2018 despite current_assets/current_liabilities/
    # stockholders_equity (different-spelled ifrs concepts, no collision) working fine.
    # Confirmed via a live DB scan: 58 symbols affected today (HMC, TM, SONY, PBR, VALE,
    # WPP, FRO, ALC, FMS among them) - total_assets NULL for fiscal_year >= 2022 despite
    # current_assets present. IFRS alias specs must always read ifrs-full directly; the
    # existing latest-filed-wins merge per fiscal year (below) already handles combining
    # both sources correctly when a company legitimately has both.
    concept_specs: list[tuple[str, str, str]] = [(c, _to_snake(c), "gaap") for c in concepts]
    if ifrs_aliases:
        concept_specs.extend((c, k, "ifrs") for c, k in ifrs_aliases)
    if dei_aliases:
        concept_specs.extend((c, k, "dei") for c, k in dei_aliases)
    return concept_specs


def _aggregate_concepts_lookup_units(
    concept: str,
    source: str,
    us_gaap_facts: dict[str, Any] | None,
    ifrs_facts: dict[str, Any] | None,
    dei_facts: dict[str, Any] | None,
) -> Any:
    """Resolve a concept's ``units`` dict from the correct taxonomy, or None if absent.

    Extracted from _aggregate_concepts (mechanical extraction, no behavior change).
    """
    if source == "dei":
        concept_data = dei_facts.get(concept) if dei_facts is not None else None
    elif source == "ifrs":
        concept_data = ifrs_facts.get(concept) if ifrs_facts is not None else None
    else:
        concept_data = us_gaap_facts.get(concept) if us_gaap_facts is not None else None
        if concept_data is None:
            concept_data = ifrs_facts.get(concept) if ifrs_facts is not None else None
    if concept_data is None:
        return None

    units = concept_data.get("units")
    if not units:
        return None
    return units


def _aggregate_concepts_currency_code(_unit: str) -> str:
    """Extract the ISO-4217-style currency code from an XBRL unit string.

    Extracted from _aggregate_concepts (mechanical extraction, no behavior change).
    """
    # FIXED 2026-08-17 (SEC-vs-yfinance audit): foreign private issuers filing
    # 20-F/40-F often report monetary facts in home-market currency instead of
    # USD, with no separate USD-denominated fact anywhere in the filing - live-
    # confirmed via real companyfacts JSON: SHG (Shinhan) tags "Assets" only
    # under unit="KRW" ($739.76e12 raw KRW, ~$550B real), MUFG/SMFG only under
    # unit="JPY". Every dollar-value concept in this file was being pulled
    # regardless of unit, so these filers' total_assets/long_term_debt/revenue/
    # etc. landed in the DB as raw local-currency magnitudes masquerading as
    # USD - off by ~100-1000x (KRW/JPY are both ~3-4 orders of magnitude weaker
    # than USD). Live DB scan found 15 symbols with total_assets > $50 trillion
    # (BCH, BSAC, EC, KB, KEP, MFG, MUFG, NMR, PKX, SHG, SMFG, TLK, TM, VFS, WF)
    # - all real foreign banks/industrials whose true USD-equivalent assets are
    # 2-4 orders of magnitude smaller, plus an unknown number of smaller foreign
    # filers below that crude threshold that are still wrong without looking
    # absurd. No reliable per-filer FX rate is available in XBRL to convert
    # these correctly (same "can't safely correct, only detect" situation as
    # the rejected NumberOfSharesOutstanding IFRS alias above) - skip any
    # non-USD 3-letter ISO-4217-style currency unit entirely rather than fabricate
    # a converted value; "shares"/"pure"/"USD/shares" units (share counts, ratios,
    # per-share figures) don't match this 3-letter-uppercase-currency-code shape
    # and are unaffected. A filer left without a real USD fact gets an honest
    # NULL, not a silently wrong number 2-4 orders of magnitude off.
    #
    # FIXED 2026-08-17 (goal: "no SEC data" audit): that blanket rule also caught
    # CAD/GBP/EUR/AUD/CHF/JPY filers (CP, ASML, BBVA, BCS, BAP, BCE and 270+ more
    # live-confirmed via DB scan) whose currencies are NOT a 100-1000x magnitude
    # mismatch like KRW/JPY's original unit-scale bug - these are liquid,
    # developed-market currencies within roughly a 2x band of USD historically.
    # fx_rates.py fetches a REAL historical ECB rate for the filing's own period-
    # end date (never a guessed/current-day rate applied retroactively, never a
    # fallback value) - see that module's docstring for the full rationale and
    # why volatile/emerging-market currencies are deliberately excluded. A rate
    # lookup failure still leaves the value NULL, same fail-closed discipline as
    # every other currency this guard rejects outright.
    _currency_code = _extract_currency_code(_unit)
    return _currency_code


def _to_snake(name: str) -> str:
    """CamelCase → snake_case. Used for converting XBRL concept names to columns."""
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0 and not name[i - 1].isupper():
            out.append("_")
        out.append(ch.lower())
    return "".join(out)
