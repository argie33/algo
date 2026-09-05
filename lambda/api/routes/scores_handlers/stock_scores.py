"""Score route handlers: the main multi-factor stock scores listing endpoint.

_get_stock_scores below delegates most of its work to stock_scores_helpers.py (2026-09
split, purely to keep this file under the file-size ratchet's new-file cap) - each helper
is a behavior-preserving, mechanical extraction of one phase of this function's body
(paginated-query construction, row/factor-input transformation, summary-metric
computation). No logic, computation, query, or control flow was changed in the process.
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.errors
from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    error_response,
    execute_with_timeout,
    handle_db_error,
    json_response,
)

from .stock_scores_helpers import (
    _build_stock_score_items,
    _build_stock_scores_query,
    _compute_stock_scores_completeness_health,
    _compute_stock_scores_summary,
    _log_stock_scores_price_quality,
)

logger = logging.getLogger(__name__)


def _get_stock_scores(
    cur: cursor,
    limit: int = 5000,
    offset: int = 0,
    sort_by: str = "composite_score",
    sort_order: str = "desc",
    sp500_only: bool = False,
    symbol: str | None = None,
    min_market_cap: float | None = None,
) -> Any:
    """Get stock scores with multi-factor ranking."""
    try:
        allowed_sorts = {
            "composite_score": "composite_score",
            "momentum_score": "momentum_score",
            "quality_score": "quality_score",
            "value_score": "value_score",
            "growth_score": "growth_score",
            "risk_score": "risk_score",
            "symbol": "symbol",
        }
        sort_col = allowed_sorts.get(sort_by, "composite_score")
        sort_direction = "DESC" if sort_order == "desc" else "ASC"

        # ETF FILTERING (GOVERNANCE compliance): Stock scores are for equity trading signals.
        # Exclude ETFs per GOVERNANCE.md: "financial data loaders and trading signals are stocks only".
        # Use etf_symbols table (definitive source). Note: ss.etf column does not exist in stock_scores.
        # This pattern is mirrored in /api/market/breadth and Phase 7 signal generation.
        #
        # SPAC-SHELL/DERIVATIVE FILTERING (2026-08-03): pre-merger SPAC common shares
        # ("... Acquisition Corp[oration] - Class A Ordinary Shares") and their Rights/
        # Warrants derivatives have no operating business, so SEC EDGAR has no income
        # statement/balance sheet for them - loaders correctly mark them
        # 'no_annual_income_data_in_sec_edgar_reit_or_special_entity', which surfaced on
        # the scores page as "No SEC data" for ~5% of the universe (279/5455 symbols,
        # verified live 2026-08-03). That's not a loader gap to fix - there is nothing to
        # load - so exclude them the same way ETFs are excluded. The Rights/Warrants
        # pattern is end-anchored ('...Rights?/Warrants?$') to avoid matching ADS
        # boilerplate like "...American Depositary Shares (each representing the right to
        # receive...)" (e.g. AMX/RLX/WDH), which are real operating companies.
        #
        # SIC-CODE SPAC FILTERING (2026-08-03, follow-up): the name regex above was
        # verified live to still miss a real, non-trivial share of SPAC shells with
        # heterogeneous naming - "General Catalyst Global Resilience Merger Corp" (GCGR,
        # "Merger" not "Acquisition"), "Iron Dome Acquisition I Corp" / "Research Alliance
        # Corp III" / "Texas Ventures Acquisition IV Corp" (IDAC/RACC/RACD/TVIV, a roman
        # numeral or ordinal breaks the "Acquisition Corp" substring match), "Yorkville
        # International Capital Corp" (YICC, no "Acquisition"/"Merger" at all). Live-verified
        # against real SEC EDGAR submissions JSON: all 6 of the above report SIC code 6770
        # ("Blank Checks") - the SEC's own official classification for pre-merger SPAC
        # shells - while real operating companies with similar naming (AAPL, MSFT, FNWB) and
        # REITs/banks previously at false-positive risk from name regexes (NREF, OZK) do not.
        # `company_info_sec.sic_code` is already fetched from this same submissions endpoint
        # by loaders/load_company_info_sec.py, just never used for this filter before - a
        # strictly more reliable, name-independent signal than pattern matching heterogeneous
        # SPAC naming conventions.
        #
        # SIC-CODE ROYALTY TRUST FILTERING (2026-08-03, same follow-up): oil/gas royalty
        # trusts (CRT, MTR, PBT, SBR, SJT - ~5 symbols) have the identical "no operating
        # business, nothing for SEC EDGAR to report" problem as SPAC shells, but with their
        # own distinct, clean SIC code: 6792 ("Oil Royalty Traders"), live-verified for all 5.
        # No false-positive risk from real oil/gas producers - XOM/CVX (2911 Petroleum
        # Refining) and OXY (1311 Crude Petroleum & Natural Gas) live-confirmed as different
        # codes. Closed-end funds/investment trusts (~60+ symbols, the largest remaining
        # bucket) were also tested this same way and do NOT have a usable SIC signal - their
        # SIC field is blank/empty via this endpoint, identical to real operating companies
        # like OZK (Bank OZK) that were already a known false-positive risk for name-based
        # filtering. Solved instead via `has_annual_report_filing` below (migration 1193).
        #
        # SIC-CODE STRUCTURED-NOTE FILTERING (2026-08-03, same follow-up): trust-preferred/
        # structured-note certificates (GJH/GJO/GJP/GJR/GJS/GJT "STRATS", KTN "CorTS", PYT
        # "PPlus Trust" - a securitization wrapper around another company's bonds, no
        # operating business of its own) live-verified with their own distinct SIC code:
        # 6189 ("Asset-Backed Securities"), consistent across all 6 checked. Note:
        # ELC/EMP/ENJ/ENO ("Entergy First Mortgage Bonds") were checked too but their ticker
        # resolves to the PARENT operating utility's own CIK/SIC (real Entergy subsidiaries
        # with real SEC filings), not a separate securitization vehicle - those are a
        # different, not-yet-understood problem, NOT fixed by this filter and not added here.
        #
        # HAS_ANNUAL_REPORT_FILING FILTERING (2026-08-03, migration 1193): closed-end funds/
        # investment trusts (~60+ symbols, the LARGEST remaining "No SEC data" bucket - real
        # 40-Act funds like BlackRock/Eaton Vance/Gabelli/Invesco/Franklin CEFs) have no
        # usable SIC signal (blank sic_code, same as some real operating companies - see
        # comment above). Different, more direct signal: whether SEC EDGAR submissions.
        # filings.recent.form has EVER included 10-K/10-K-A (domestic annual report) or
        # 20-F/20-F-A (foreign private issuer annual report) - the two filing types this
        # pipeline's loaders actually parse for annual_income_statement/annual_balance_sheet.
        # Live-verified via loaders/load_company_info_sec.py: CEFs (BGT, GAB) file NEITHER -
        # only fund-specific forms (N-Q, NPORT-P, 40-17G, N-30B-2, DEF 14A) - while real
        # operating companies (AAPL, FNWB) have 10-K and foreign filers (IBN/ICICI Bank) have
        # 20-F, so this correctly leaves foreign 20-F filers unaffected (a separate, sparser-
        # coverage problem, not "no data at all"). `has_annual_report_filing IS NOT FALSE`
        # (not `= TRUE`) deliberately includes NULL (not yet checked for this symbol, or no
        # company_info_sec row at all) - only excludes symbols explicitly confirmed to have
        # neither filing type, same "fail open on unknown" posture as the ETF/SPAC filters
        # above.
        #
        # DEBT/PREFERRED-CERTIFICATE FILTERING (2026-08-03): subordinated debentures/mortgage
        # bonds (AFGB/AFGC/AFGD/AFGE - American Financial Group; ELC/EMP/ENJ/ENO/EAI - Entergy
        # utility subsidiaries) trade under their own ticker but share the parent operating
        # company's CIK, so they inherit real revenue/net_income data yet aren't common equity
        # and structurally have no separate balance sheet of their own to compute ROE/margins
        # from. Live-verified zero false-positive risk: `security_name ~*
        # '(Subordinated Debentures?|First Mortgage Bonds?|Collateral Trust Mortgage Bonds?)'`
        # matched exactly these 5 tickers across the ENTIRE active universe, nothing else.
        # Deliberately did NOT extend this to a broader "Trust N" pattern (e.g. for SCE$L "SCE
        # TRUST VI") - live-checked and found it collides with real closed-end funds (VLT
        # "Invesco High Income Trust II"), the same false-positive trap already documented for
        # CEF name-matching above.
        # PHYSICAL COMMODITY TRUST FILTERING (2026-08-10): grantor trusts that hold physical
        # bullion (GraniteShares Gold Trust "BAR" the live example - 279 more like it exist
        # for silver/platinum/palladium under other issuers) file real 10-Ks (so they pass
        # has_annual_report_filing) and aren't ETF-registered '40 Act funds (so etf_symbols
        # doesn't have them either) - they slipped through every filter above and ranked #1
        # in the entire universe on last live check. SIC 6221 ("Commodity Contracts Brokers &
        # Dealers") alone isn't a safe filter - live-verified it also covers real operating
        # companies (AIB "Data Centers Inc", ANTA "Antalpha Platform Holding", UROY "Uranium
        # Royalty Corp"), none of which have "Trust" in their name. Requiring both SIC 6221
        # AND a commodity-Trust name pattern together matched only BAR across the entire
        # scored universe, zero false positives against the SIC-6221 operating companies above.
        #
        # ETN FILTERING (goal: "scores still including ETFs", 2026-08-20): GRN ("iPath Series B
        # Carbon Exchange-Traded Notes") ranked in the score leaderboard despite every filter
        # above - not in etf_symbols (ETNs are debt notes, not '40 Act funds), sic_code=6029
        # ("Commercial Banks") not 6770/6792/6189, and has_annual_report_filing=TRUE, because
        # an ETN's SEC filer is the issuing BANK (Barclays Bank PLC here), which has its own
        # real filing history and SIC code unrelated to the note's actual structure. No usable
        # SIC/has_annual_report_filing signal exists for this case - same root cause as
        # utils/loaders/helpers.py::get_active_symbols(exclude_etfs=True), see that function's
        # 2026-08-20 comment for the live investigation. Name-based catch, verified against the
        # live active universe to match only GRN.
        where_clause = """
            WHERE sc.composite_score > 0
            AND ss.symbol NOT IN (SELECT symbol FROM etf_symbols)
            AND ss.symbol NOT IN (SELECT symbol FROM company_info_sec WHERE sic_code IN (6770, 6792, 6189))
            AND ss.symbol NOT IN (
                SELECT symbol FROM company_info_sec WHERE has_annual_report_filing = FALSE
            )
            AND NOT (
                ss.symbol IN (SELECT symbol FROM company_info_sec WHERE sic_code = 6221)
                AND ss.security_name ~* '(Gold|Silver|Platinum|Palladium|Bullion) Trust'
            )
            AND (ss.security_name IS NULL OR (
                ss.security_name !~* '(Rights?|Warrants?)$'
                AND ss.security_name NOT ILIKE '%%Acquisition Corp%%'
                AND ss.security_name !~* '(Subordinated Debentures?|First Mortgage Bonds?|Collateral Trust Mortgage Bonds?)'
                AND ss.security_name !~* '(ETNs?|Exchange[- ]Traded Notes?)'
            ))
            """
        params_list: list[Any] = []

        if sp500_only:
            where_clause += " AND ss.is_sp500 = TRUE"
        if symbol:
            # Validate symbol format (consistent with signals.py)
            import re

            if not re.match(r"^[A-Z0-9\-\^]{1,10}$", symbol.upper()):
                return error_response(400, "bad_request", "Invalid symbol format")
            where_clause += " AND sc.symbol = %s"
            params_list.append(symbol.upper())
        else:
            # Bulk queries: filter by data availability status computed by loader.
            # Loader marks data_unavailable=false for scores with 4+/6 metrics (sufficient diversity).
            # Loader marks data_unavailable=true for scores with <4/6 metrics or data_completeness < 70%.
            # API: Return all scores where loader marked available; dashboard filters on completeness %.
            # This gives traders full visibility: completeness % shown for all scores >= 50%.
            where_clause += " AND (sc.data_unavailable = false OR sc.data_unavailable IS NULL)"

        # MARKET-CAP ELIGIBILITY FLOOR (added 2026-08-31, /goal session - "make sure the
        # results make sense" investigation). This endpoint's default sort is composite_score
        # DESC with no investability screen of any kind - live-verified the top of that
        # ranking was dominated by nano/micro-caps (SOGP $37.6M mkt cap, COHN $19.6M, CPBI
        # $79.5M, several under $200K/day dollar volume), because Size was deliberately
        # retired as a scoring PILLAR (size_pillar_retired_entirely_20260828 in memory - not
        # being re-litigated here) with nothing left to offset small-cap-favoring percentile
        # scoring. A liquidity gate already exists for real trade EXECUTION
        # (algo/risk/liquidity_checks.py, min_adv_shares/min_adv_dollars config) but only
        # fires at Phase 8 entry time - invisible to anyone just browsing this "top stocks"
        # list, so untradeable names surface as if they were the best picks. Opt-in
        # (min_market_cap query param, no default) rather than a silent behavior change for
        # existing callers/tests - single-symbol lookups are deliberately exempt (you should
        # always be able to look up any specific symbol regardless of its size). Standard
        # index-provider practice (Russell/S&P/MSCI) applies exactly this kind of investability
        # screen separately from the factor scores themselves.
        market_cap_join = ""
        if min_market_cap is not None and not symbol:
            market_cap_join = "JOIN value_metrics mcf ON mcf.symbol = sc.symbol"
            where_clause += " AND mcf.market_cap >= %s"
            params_list.append(min_market_cap)

        # Real universe count (goal: dashboard/API were reporting "only ~1000 stocks
        # screened" - traced to `estimated_total` below being a page-size heuristic instead
        # of an actual count, compounded by this endpoint's limit being capped at 1000. The
        # true filtered universe is ~5000+ symbols (live-verified). Run against the same
        # where_clause/params_list as the page query, before LIMIT/OFFSET are appended to
        # params_list below, so this reflects the full filtered result set, not one page.
        count_query = f"""
            SELECT COUNT(*)
            FROM stock_scores sc
            JOIN stock_symbols ss ON ss.symbol = sc.symbol
            {market_cap_join}
            {where_clause}
        """
        cur.execute(count_query, params_list)
        real_total = cur.fetchone()[0]

        # PERFORMANCE: filter/sort/limit to the target page FIRST in a CTE, then run the
        # per-symbol LATERAL lookups (price_daily/technical_data_daily) only against that
        # small row set. Previously the LATERAL joins ran against every row of stock_scores
        # BEFORE the WHERE clause was applied, so a page of 50 rows still paid for thousands
        # of per-symbol index scans - this was the root cause of the endpoint's 7+ second
        # latency (and the dashboard's 3s client timeout hiding it as "no data"). Query
        # construction itself lives in stock_scores_helpers.py (_build_stock_scores_query) -
        # see that function's docstring for the same detail.
        query = _build_stock_scores_query(where_clause, market_cap_join, sort_col, sort_direction)
        params_list.extend([limit, offset])

        # Try with data_unavailable columns first (preferred)
        # timeout_sec=20 ensures DB cancels before Lambda's 25s timeout, allowing proper error response
        try:
            scores = execute_with_timeout(cur, query, params_list, timeout_sec=20, max_attempts=1)
        except psycopg2.errors.UndefinedColumn as e:
            # CRITICAL: Schema mismatch on data_unavailable columns indicates migration incomplete
            # FAIL-FAST: Do not silently degrade query validation
            if "data_unavailable" in str(e):
                logger.critical(
                    f"[SCORES_API] Schema validation failed: data_unavailable columns missing from metrics tables. "
                    f"This indicates database migration (0046) has not been applied. Cannot validate score completeness. "
                    f"Error: {e}"
                )
                return error_response(
                    503,
                    "schema_mismatch",
                    "Score validation unavailable: database schema missing required data_unavailable columns. "
                    "Database migration may not have completed.",
                )
            else:
                raise

        # Row/factor-input transformation (data_unavailable-driven score nulling, factor
        # input objects, current_price data-quality flag) - see
        # stock_scores_helpers._build_stock_score_items's docstring.
        items = _build_stock_score_items(scores)

        # Check data freshness
        freshness = check_data_freshness(cur, "stock_scores", "updated_at", warning_days=7)

        _log_stock_scores_price_quality(items)

        # CRITICAL FIX: Return scores in standard paginated format
        # Dashboard/responseNormalizer expects {statusCode: 200, items: [...], pagination: {...}} format
        # This matches other paginated endpoints and works with frontend schema validation
        # real_total comes from the COUNT(*) query above (same where_clause), not a
        # page-size estimate - see comment there for why the old estimate was wrong.
        estimated_total = real_total

        # Compute summary metrics over ALL scores (not just this page) - dashboard summary
        # line needs these metrics for the full universe.
        avg_composite, grades_summary = _compute_stock_scores_summary(items)

        # TRANSPARENCY ENHANCEMENT (2026-08-05): Data health metrics for the summary -
        # shows traders overall data quality of the scores being returned.
        avg_completeness, completeness_threshold_pct = _compute_stock_scores_completeness_health(items)

        result = {
            "items": items,
            "pagination": {
                "total": estimated_total,
                "limit": limit,
                "offset": offset,
                "page": (offset // limit) + 1 if limit > 0 else 1,
                "totalPages": ((estimated_total - 1) // limit) + 1 if limit > 0 else 1,
            },
            "avg_composite": avg_composite,
            "grades": grades_summary if grades_summary else None,
            "data_health": {
                "avg_completeness": round(avg_completeness, 2) if avg_completeness is not None else None,
                "meeting_trading_gate": f"{completeness_threshold_pct:.0f}%"
                if completeness_threshold_pct is not None
                else None,
                "note": "Completeness >= 70% passes trading entry gate; < 70% filtered per GOVERNANCE",
            },
        }
        return json_response(200, result, data_freshness=freshness)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "handle scores")
        return error_response(code, error_type, message)
