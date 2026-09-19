#!/usr/bin/env python3
"""Periodic independent cross-check: our SEC-XBRL-derived financial statement values vs
yfinance's own, independently-parsed financials, across every mappable line item on the
income statement, balance sheet, and cash flow statement.

Added 2026-09-10 (goal session: institution-grade XBRL data-quality architecture). Real
vendors validate XBRL preparation with three layers, none of which require paying for
another data vendor: (1) a filing's own calculation-linkbase arithmetic ties within that
same document (see scripts/xbrl_calculation_linkbase_check.py), (2) same-filer time-series
continuity and cross-sectional peer statistics (already covered by algo/monitoring/
data_patrol/checks/statistical_anomaly.py and tie_out.py), and (3) an independently-*parsed*
second read of the same underlying filing to catch extraction/mapping bugs that are
internally self-consistent (so tie_out.py's identity checks pass) and don't stand out
against peers/history either (so statistical_anomaly.py doesn't fire). This script is #3.

yfinance is not a truly independent SOURCE - it likely also derives from XBRL, probably
through a data vendor between the SEC feed and Yahoo's site. But it goes through completely
different extraction/tagging/mapping code than ours, so it catches a different bug class:
wrong-concept-picked, scale/unit errors, fiscal-period misalignment, sign errors. It's the
same "second opinion, not ground truth" role sec_valuations already gives it for market_cap/
shares_outstanding (see loaders/helpers/sec_valuations_checks.py) and the same fallback-only
fetch (utils/external/yfinance_financials.py) - REUSED here, not reimplemented.

EXPANDED 2026-09-16 (goal session: "validate all line items in the prepared statement vs
yahoo ... for full transparency into the exact place where we still have a data issue"):
previously only 5 headline fields (revenue, net_income, total_assets, stockholders_equity,
operating_cash_flow) were compared, and only flagged/divergent examples were persisted, capped
at 15 per field, as a JSONB blob inside data_patrol_log. Now every field mappable between our
schema and utils/external/yfinance_financials.py's own field maps is compared (_FIELDS below -
29 fields across the three statements as of 2026-09-16, expanded to 39 on 2026-09-17 after
live-verifying 10 more line items against real AAPL/JPM/KO yfinance DataFrames - see
utils/external/yfinance_financials.py's field-map comments for what's covered and why a couple
of tempting-looking yfinance labels were deliberately NOT used), driven off
_INCOME_FIELD_MAP/_BALANCE_FIELD_MAP/_CASHFLOW_FIELD_MAP so this can't silently drift from what
the fallback fetch actually supports, and EVERY comparison - match or divergence - is upserted into
xbrl_yfinance_line_item_report (migration 1300), not just the flagged ones. That gives a
durable, queryable, per-symbol/per-field/per-fiscal-year record of exactly where our SEC data
and yfinance's independent parse agree or disagree - see scripts/xbrl_line_item_report.py for
the read side. data_patrol_log still gets the aggregate WARN/info rollup per field, unchanged
in spirit, just now covering every field instead of 5.

Deliberately NOT part of every DataPatrol run (unlike statistical_anomaly.py, which is pure
SQL and cheap): this makes live yfinance network calls per symbol through the same
rate-limited/circuit-broken worker every other yfinance call in this codebase shares
(utils/external/yfinance_circuit_breaker.py) - see MEMORY.md's
yfinance_validation_calls_self_triggered_ban_during_reload_20260903 for why a naive
"check everything, every run" version of this would risk self-triggering the shared-IP ban
that live loader runs also depend on. Still NOT a full-universe-in-one-pass tool even after
the 2026-09-16 expansion - that constraint didn't change, only field coverage did. Two sampling
modes:
  - default (no --sweep): daily-rotating pseudo-random sample, good for ad hoc/manual checks.
  - --sweep: walks the active universe alphabetically using a persistent cursor
    (xbrl_yfinance_crosscheck_progress, migration 1300 - same "accumulate over many small,
    rate-limit-safe runs" posture as tiingo_backfill_status), so a low-frequency schedule
    (e.g. daily) provably covers every symbol exactly once per full lap instead of relying on
    random resampling to eventually touch everyone. Use --sweep on the scheduled/periodic
    invocation; leave it off for spot-checking specific symbols.

Findings are WARN severity (review queue, not a confirmed bug - same posture as
statistical_anomaly.py: a real divergence can be a genuine restatement, non-GAAP
reclassification, or fiscal-period misalignment, not necessarily an extraction bug) and flow
into the same data_patrol_log / data_patrol_review triage workflow as every other DataPatrol
check - no new review path, no new schema for "did anyone look at this". NOTE: WARN-severity
findings never reach symbol_quarantine (quarantine.apply_symbol_quarantine only fires on
error/critical + flagged_symbols, verified 2026-09-13) - a real divergence here still requires
a human to act on it via the review queue, it does not auto-quarantine the symbol.

Usage:
    python scripts/xbrl_yfinance_crosscheck.py                  # sample 25 symbols, write findings
    python scripts/xbrl_yfinance_crosscheck.py --limit 50
    python scripts/xbrl_yfinance_crosscheck.py --sweep           # next 25 symbols in the universe sweep
    python scripts/xbrl_yfinance_crosscheck.py --symbols AAPL,MSFT,KO
    python scripts/xbrl_yfinance_crosscheck.py --dry-run         # print, don't write to DB
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# (our_table, our_field, yfinance statement_type, yfinance target_key) - target_key values
# come straight from utils/external/yfinance_financials.py's own field maps
# (_INCOME_FIELD_MAP / _BALANCE_FIELD_MAP / _CASHFLOW_FIELD_MAP), not reinvented. our_field is
# this codebase's live DB column name on the corresponding annual_* table (confirmed live via
# information_schema.columns 2026-09-16) - not always the same spelling as target_key.
_FIELDS: list[tuple[str, str, str, str]] = [
    # annual_income_statement
    ("annual_income_statement", "revenue", "income", "revenues"),
    ("annual_income_statement", "cost_of_revenue", "income", "cost_of_revenue"),
    ("annual_income_statement", "gross_profit", "income", "gross_profit"),
    ("annual_income_statement", "operating_income", "income", "operating_income_loss"),
    ("annual_income_statement", "net_income", "income", "net_income_loss"),
    # NOT "eps" - that column exists on the live table but is dead/always-NULL for
    # data_source='sec_audited' rows (live-confirmed via COUNT(*) FILTER 2026-09-16); the
    # loader actually writes basic EPS to "earnings_per_share". Using "eps" here would make
    # this field silently produce zero comparisons forever, the opposite of this table's
    # "full transparency" purpose.
    ("annual_income_statement", "earnings_per_share", "income", "earnings_per_share_basic"),
    ("annual_income_statement", "diluted_eps", "income", "earnings_per_share_diluted"),
    (
        "annual_income_statement",
        "shares_outstanding_basic",
        "income",
        "weighted_average_number_of_shares_outstanding_basic",
    ),
    (
        "annual_income_statement",
        "shares_outstanding_diluted",
        "income",
        "weighted_average_number_of_diluted_shares_outstanding",
    ),
    ("annual_income_statement", "interest_expense", "income", "interest_expense"),
    ("annual_income_statement", "depreciation_expense", "income", "depreciation"),
    ("annual_income_statement", "income_tax_expense", "income", "income_tax_expense_benefit"),
    (
        "annual_income_statement",
        "pretax_income",
        "income",
        "income_loss_from_continuing_operations_before_income_taxes_extraordinary_items_noncontrolling_interest",
    ),
    # ADDED 2026-09-17 (goal: "fully thorough through all the line items" coverage push) -
    # see utils/external/yfinance_financials.py's _INCOME_FIELD_MAP comment for the live
    # AAPL/JPM/KO verification behind these three, including why operating_expenses maps to
    # yfinance's "Selling General And Administration" and NOT "Operating Expense" (the latter
    # bundles in R&D, which would make every R&D-reporting filer look divergent for a
    # definitional reason, not a bug).
    ("annual_income_statement", "research_development_expense", "income", "research_and_development_expense"),
    ("annual_income_statement", "operating_expenses", "income", "operating_expenses"),
    ("annual_income_statement", "net_income_attributable_to_common", "income", "net_income_attributable_to_common"),
    # annual_balance_sheet
    ("annual_balance_sheet", "total_assets", "balance", "assets"),
    ("annual_balance_sheet", "current_assets", "balance", "assets_current"),
    ("annual_balance_sheet", "total_liabilities", "balance", "liabilities"),
    ("annual_balance_sheet", "stockholders_equity", "balance", "stockholders_equity"),
    ("annual_balance_sheet", "current_liabilities", "balance", "liabilities_current"),
    ("annual_balance_sheet", "inventory", "balance", "inventory_net"),
    ("annual_balance_sheet", "cash_and_equivalents", "balance", "cash_and_cash_equivalents_at_carrying_value"),
    ("annual_balance_sheet", "accounts_receivable", "balance", "accounts_receivable_net_current"),
    ("annual_balance_sheet", "ppe_net", "balance", "property_plant_and_equipment_net"),
    ("annual_balance_sheet", "goodwill", "balance", "goodwill"),
    ("annual_balance_sheet", "long_term_debt", "balance", "long_term_debt"),
    # ADDED 2026-09-17 (same coverage push) - live-confirmed on AAPL/JPM/KO real balance sheets.
    ("annual_balance_sheet", "short_term_debt", "balance", "short_term_debt"),
    ("annual_balance_sheet", "retained_earnings", "balance", "retained_earnings"),
    ("annual_balance_sheet", "accounts_payable", "balance", "accounts_payable"),
    # annual_cash_flow
    ("annual_cash_flow", "operating_cash_flow", "cashflow", "net_cash_provided_by_used_in_operating_activities"),
    ("annual_cash_flow", "investing_cash_flow", "cashflow", "net_cash_provided_by_used_in_investing_activities"),
    ("annual_cash_flow", "financing_cash_flow", "cashflow", "net_cash_provided_by_used_in_financing_activities"),
    ("annual_cash_flow", "capex", "cashflow", "payments_to_acquire_property_plant_and_equipment"),
    ("annual_cash_flow", "dividends_paid", "cashflow", "payments_of_dividends"),
    # ADDED 2026-09-17 (same coverage push) - see utils/external/yfinance_financials.py's
    # _CASHFLOW_FIELD_MAP comment for the "Free Cash Flow" definitional caveat and the
    # "Repurchase Of Capital Stock" sign-flip (_ABS_MAGNITUDE_FIELDS handles it, same as
    # capex/dividends above).
    ("annual_cash_flow", "free_cash_flow", "cashflow", "free_cash_flow"),
    ("annual_cash_flow", "net_change_cash", "cashflow", "net_change_cash"),
    ("annual_cash_flow", "stock_based_compensation", "cashflow", "stock_based_compensation"),
    ("annual_cash_flow", "common_stock_repurchased", "cashflow", "common_stock_repurchased"),
]

# Per-share and share-count fields live on a completely different scale than dollar-magnitude
# fields (EPS is single digits/low tens; a $1,000,000 floor would make every EPS comparison
# vacuously "too small to check"). Keyed by our_field.
_PER_SHARE_FIELDS = frozenset({"earnings_per_share", "diluted_eps"})
_SHARE_COUNT_FIELDS = frozenset({"shares_outstanding_basic", "shares_outstanding_diluted"})

# Wide by design: two independently-parsed sources legitimately disagree by 20-40% on plenty
# of real filers (non-GAAP reclassifications, discontinued-ops treatment, fiscal-period-end
# drift). This threshold is a starting point, not tuned against a live feasibility pass the
# way statistical_anomaly.py's 20x was - tighten it once real runs show what the normal
# divergence distribution actually looks like.
_DIVERGENCE_RATIO = 2.0
_DIVERGENCE_FLOOR_DOLLARS = 1_000_000.0
_DIVERGENCE_FLOOR_PER_SHARE = 0.01
_DIVERGENCE_FLOOR_SHARE_COUNT = 100_000.0
_MAX_EXAMPLES_PER_FIELD = 15
_MAX_CONSECUTIVE_BAN_ERRORS = 3

# ADDED 2026-09-16 (goal session, user-requested after live testing): the shared-IP circuit
# breaker (utils/external/yfinance_circuit_breaker.py) is reactive-only - it backs off after
# Yahoo already returns a 429/401, it doesn't pace requests to avoid triggering one in the
# first place. Two live batches (75 then 250 symbols) ran clean with zero ban errors relying
# solely on natural per-symbol fetch latency (~2.1s/symbol, no sleep at all), but that's not a
# safety margin, just luck holding so far across a couple thousand total requests - a real
# inter-symbol pause is cheap insurance against burning through it on a longer/faster run.
_DEFAULT_INTER_SYMBOL_DELAY_SECS = 2.0


def _floor_for_field(our_field: str) -> float:
    if our_field in _PER_SHARE_FIELDS:
        return _DIVERGENCE_FLOOR_PER_SHARE
    if our_field in _SHARE_COUNT_FIELDS:
        return _DIVERGENCE_FLOOR_SHARE_COUNT
    return _DIVERGENCE_FLOOR_DOLLARS


def _select_symbols_random(cur: Any, limit: int) -> list[str]:
    """Daily-rotating pseudo-random sample of active symbols with real SEC-audited annual
    income-statement data (data_source='sec_audited' - excludes our own yfinance-fallback
    rows and unknown-source rows, so we're never comparing yfinance against itself)."""
    cur.execute(
        """
        SELECT symbol FROM (
            SELECT DISTINCT ais.symbol
            FROM annual_income_statement ais
            JOIN stock_symbols s ON s.symbol = ais.symbol AND s.active = true
            WHERE ais.data_source = 'sec_audited' AND ais.data_unavailable = FALSE
        ) candidates
        ORDER BY md5(symbol || CURRENT_DATE::text)
        LIMIT %s
        """,
        (limit,),
    )
    return [row[0] for row in cur.fetchall()]


def _eligible_universe(cur: Any) -> list[str]:
    cur.execute(
        """
        SELECT DISTINCT ais.symbol
        FROM annual_income_statement ais
        JOIN stock_symbols s ON s.symbol = ais.symbol AND s.active = true
        WHERE ais.data_source = 'sec_audited' AND ais.data_unavailable = FALSE
        ORDER BY 1
        """
    )
    return [row[0] for row in cur.fetchall()]


def _select_symbols_sweep(cur: Any, limit: int) -> list[str]:
    """Next `limit` symbols after the last cursor position, alphabetically over the full
    eligible universe, wrapping around at the end. Guarantees every symbol gets checked
    exactly once per full lap instead of relying on random resampling."""
    universe = _eligible_universe(cur)
    if not universe:
        return []

    cur.execute("SELECT last_symbol FROM xbrl_yfinance_crosscheck_progress WHERE id = 1")
    row = cur.fetchone()
    last_symbol = row[0] if row else None

    start_idx = 0
    if last_symbol is not None:
        for i, sym in enumerate(universe):
            if sym > last_symbol:
                start_idx = i
                break
        else:
            start_idx = 0  # last_symbol was >= everything - wrap to the start

    if start_idx + limit <= len(universe):
        batch = universe[start_idx : start_idx + limit]
    else:
        batch = universe[start_idx:] + universe[: (start_idx + limit) - len(universe)]
    return batch


def _advance_sweep_cursor(cur: Any, last_symbol_checked: str) -> None:
    cur.execute(
        """
        INSERT INTO xbrl_yfinance_crosscheck_progress (id, last_symbol, updated_at)
        VALUES (1, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (id) DO UPDATE SET last_symbol = EXCLUDED.last_symbol, updated_at = EXCLUDED.updated_at
        """,
        (last_symbol_checked,),
    )


# our_field -> extra column to ADD before comparing against yfinance. Live-confirmed 2026-09-16
# (ABT/ABBV/ADI all matched yfinance's "depreciation" value to the dollar once summed): yfinance's
# "Reconciled Depreciation" is the CASH-FLOW STATEMENT'S non-cash D&A add-back line, i.e. combined
# depreciation + amortization, not pure depreciation - our depreciation_expense column alone
# excludes amortization_expense (a separate column). Comparing depreciation_expense alone against
# it was producing a ~48% false-divergence rate on the very first real batch, drowning out any
# genuine signal in this field. Without this, "depreciation_expense" would look like our worst
# data-quality field when it's actually a crosscheck mapping bug, not a data bug.
_COMPOSITE_SUM_FIELDS: dict[tuple[str, str], str] = {
    ("annual_income_statement", "depreciation_expense"): "amortization_expense",
    # ADDED 2026-09-18 (goal: data-issue-reduction session): ppe_net was the largest
    # unreviewed-divergent field (746 rows), ~730 clustered at ratio 0.1-0.5x. Live-confirmed
    # via real SEC companyfacts JSON (AAP, AMPG - see migration 1310's own comment) that
    # yfinance's larger figure is our PropertyPlantAndEquipmentNet plus
    # OperatingLeaseRightOfUseAsset summed - same post-ASC-842 definitional shape as the
    # depreciation_expense/amortization_expense composite above. operating_lease_right_of_use_
    # asset (migration 1310) is a fresh column that needs a reload to populate for existing
    # symbols - rows will still show divergent=true until reloaded, this only fixes the
    # comparison basis going forward.
    ("annual_balance_sheet", "ppe_net"): "operating_lease_right_of_use_asset",
}


def _our_all_values(cur: Any, table: str, field: str, symbol: str) -> list[tuple[int, float]]:
    """Every fiscal year on file for this (table, field, symbol), not just the latest.

    CHANGED 2026-09-17: previously LIMIT 1 / ORDER BY fiscal_year DESC - only ever compared each
    symbol's single newest filing. Live-confirmed this meant the accumulated report table averaged
    only 1.26 distinct fiscal years per symbol despite most symbols having 4-5+ years of annual
    statements loaded - a "per-fiscal-year matrix" that in practice never audited history, just a
    repeatedly-reconfirmed snapshot of the newest year. No extra yfinance network calls result from
    this - fetch_financial_statement already returns every available annual period in one call
    (cached per statement_type per symbol below); this just stops throwing away all but one of them
    on our side of the comparison.
    """
    extra = _COMPOSITE_SUM_FIELDS.get((table, field))
    # GUARD added 2026-09-18 (goal session, live-confirmed via ALAB/CPSS/BEAM/ARMP/BCYC and
    # ~15 more symbols): the plain sum above double-counts whenever `amortization_expense`
    # was itself populated via financial_statements_income_config.py's
    # "depreciation_and_amortization"/"depreciation_depletion_and_amortization" fallback -
    # those hold a COMBINED D&A total (per that config's own docstring), not incremental
    # amortization, and for a filer whose real amortization is ~0 that fallback total lands
    # within noise of `depreciation_expense` itself (ALAB FY2023: both columns = 1,781,000,
    # SEC's real "Depreciation" concept - yfinance's combined-D&A figure is also 1,781,000,
    # not 3,562,000). Summing then double-counts the shared value. A genuinely separate
    # amortization figure (BAND/MO/POWI/etc., live-confirmed the plain sum DOES match
    # yfinance there) is never anywhere near equal to that year's depreciation_expense in
    # practice, so "within 1% of each other" cleanly separates the two populations without
    # touching the legitimate composite-sum cases this field was added for.
    extra_expr = f"CASE WHEN ABS({extra} - {field}) <= 0.01 * ABS({field}) THEN 0 ELSE {extra} END" if extra else None
    select_expr = f"({field} + COALESCE({extra_expr}, 0))" if extra_expr else field
    cur.execute(
        f"""
        SELECT fiscal_year, {select_expr}
        FROM {table}
        WHERE symbol = %s AND data_source = 'sec_audited' AND data_unavailable = FALSE AND {field} IS NOT NULL
        ORDER BY fiscal_year DESC
        """,
        (symbol,),
    )
    return [(int(fy), float(val)) for fy, val in cur.fetchall()]


def _is_foreign_private_issuer(cur: Any, symbol: str) -> bool:
    cur.execute("SELECT is_foreign_private_issuer FROM company_info_sec WHERE symbol = %s", (symbol,))
    row = cur.fetchone()
    return bool(row and row[0])


def _record_line_item(
    cur: Any,
    symbol: str,
    table: str,
    field: str,
    fiscal_year: int,
    our_value: float,
    yfinance_value: float,
    ratio: float,
    divergent: bool,
) -> None:
    # review_status (migration 1302) tracks a human's verdict on a row, independent of this
    # script's own divergent flag - only reset it back to 'unreviewed' when the underlying
    # comparison actually changed (our_value/yfinance_value moved since it was last reviewed).
    # A re-upsert that reproduces the exact same numbers (e.g. a routine re-sweep) must NOT wipe
    # out prior review work just because the row got touched again.
    cur.execute(
        """
        INSERT INTO xbrl_yfinance_line_item_report
            (symbol, our_table, our_field, fiscal_year, fiscal_quarter, period_type,
             our_value, yfinance_value, ratio, divergent, checked_at)
        VALUES (%s, %s, %s, %s, 0, 'annual', %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (symbol, our_table, our_field, fiscal_year, fiscal_quarter) DO UPDATE SET
            our_value = EXCLUDED.our_value,
            yfinance_value = EXCLUDED.yfinance_value,
            ratio = EXCLUDED.ratio,
            divergent = EXCLUDED.divergent,
            checked_at = EXCLUDED.checked_at,
            review_status = CASE
                WHEN xbrl_yfinance_line_item_report.our_value IS DISTINCT FROM EXCLUDED.our_value
                  OR xbrl_yfinance_line_item_report.yfinance_value IS DISTINCT FROM EXCLUDED.yfinance_value
                THEN 'unreviewed'
                ELSE xbrl_yfinance_line_item_report.review_status
            END,
            review_note = CASE
                WHEN xbrl_yfinance_line_item_report.our_value IS DISTINCT FROM EXCLUDED.our_value
                  OR xbrl_yfinance_line_item_report.yfinance_value IS DISTINCT FROM EXCLUDED.yfinance_value
                THEN NULL
                ELSE xbrl_yfinance_line_item_report.review_note
            END,
            reviewed_at = CASE
                WHEN xbrl_yfinance_line_item_report.our_value IS DISTINCT FROM EXCLUDED.our_value
                  OR xbrl_yfinance_line_item_report.yfinance_value IS DISTINCT FROM EXCLUDED.yfinance_value
                THEN NULL
                ELSE xbrl_yfinance_line_item_report.reviewed_at
            END,
            reviewed_by = CASE
                WHEN xbrl_yfinance_line_item_report.our_value IS DISTINCT FROM EXCLUDED.our_value
                  OR xbrl_yfinance_line_item_report.yfinance_value IS DISTINCT FROM EXCLUDED.yfinance_value
                THEN NULL
                ELSE xbrl_yfinance_line_item_report.reviewed_by
            END
        """,
        (symbol, table, field, fiscal_year, our_value, yfinance_value, ratio, divergent),
    )


def run(  # noqa: C901
    limit: int,
    symbols_override: list[str] | None,
    dry_run: bool,
    sweep: bool = False,
    delay_seconds: float = _DEFAULT_INTER_SYMBOL_DELAY_SECS,
) -> dict[str, Any]:
    from psycopg2.extras import DictCursor

    from algo.monitoring.data_patrol.base import CheckResult
    from algo.monitoring.data_patrol.logger import PatrolLogger
    from utils.db.connection import get_db_connection
    from utils.external.yfinance_financials import fetch_financial_statement

    conn = get_db_connection(max_retries=2, timeout=30)
    cur = conn.cursor(cursor_factory=DictCursor)

    if symbols_override:
        symbols = symbols_override
    elif sweep:
        symbols = _select_symbols_sweep(cur, limit)
    else:
        symbols = _select_symbols_random(cur, limit)
    logger.info(f"[YFINANCE_CROSSCHECK] {'Sweeping' if sweep else 'Sampling'} {len(symbols)} symbol(s): {symbols}")

    # field_key ("table:field") -> list of flagged example dicts
    flagged: dict[str, list[dict[str, Any]]] = {f"{t}:{f}": [] for t, f, _, _ in _FIELDS}
    sampled_count: dict[str, int] = {f"{t}:{f}": 0 for t, f, _, _ in _FIELDS}
    consecutive_ban_errors = 0
    last_symbol_checked: str | None = None

    for i, symbol in enumerate(symbols):
        if consecutive_ban_errors >= _MAX_CONSECUTIVE_BAN_ERRORS:
            logger.warning(
                f"[YFINANCE_CROSSCHECK] {_MAX_CONSECUTIVE_BAN_ERRORS} consecutive shared-IP-ban "
                "errors - aborting the rest of this batch rather than spinning through it uselessly."
            )
            break

        is_fpi = _is_foreign_private_issuer(cur, symbol)
        statement_cache: dict[str, list[dict[str, Any]] | None] = {}

        for table, field, statement_type, target_key in _FIELDS:
            our_rows = _our_all_values(cur, table, field, symbol)
            if not our_rows:
                continue

            if statement_type not in statement_cache:
                try:
                    statement_cache[statement_type] = fetch_financial_statement(
                        symbol, statement_type, "annual", is_known_foreign_issuer=is_fpi
                    )
                    consecutive_ban_errors = 0
                except RuntimeError as e:
                    statement_cache[statement_type] = None
                    if "shared IP ban" in str(e):
                        consecutive_ban_errors += 1
                    logger.debug(f"[YFINANCE_CROSSCHECK] {symbol} {statement_type} fetch failed (non-fatal): {e}")

            yf_rows = statement_cache.get(statement_type)
            if not yf_rows:
                continue
            yf_rows_by_year = {r.get("fiscal_year"): r for r in yf_rows}

            for fiscal_year, our_value in our_rows:
                yf_row = yf_rows_by_year.get(fiscal_year)
                if yf_row is None or target_key not in yf_row:
                    continue
                yf_value = float(yf_row[target_key])

                field_key = f"{table}:{field}"
                sampled_count[field_key] += 1
                if yf_value == 0:
                    continue
                floor = _floor_for_field(field)
                if max(abs(our_value), abs(yf_value)) < floor:
                    # FIXED 2026-09-18 (goal session, live-confirmed via CPSS/ARMP
                    # depreciation_expense post the composite-sum fix): values this small are
                    # too noisy to classify as divergent (a tiny absolute difference produces a
                    # huge relative ratio), so this case must never flag - but simply `continue`-
                    # ing left any ALREADY-recorded row (from back when the value was still above
                    # the floor and wrong) permanently stuck at its last stored divergent/
                    # reviewed_needs_fix verdict, since nothing ever upserts it again once the
                    # real value drops under the floor. Still record it (forced non-divergent) so
                    # a stale prior verdict gets refreshed to the current, correct values - the
                    # ON CONFLICT clause's own change-detection already resets review_status back
                    # to 'unreviewed' whenever our_value/yfinance_value actually moved.
                    if not dry_run:
                        _record_line_item(
                            cur,
                            symbol,
                            table,
                            field,
                            fiscal_year,
                            our_value,
                            yf_value,
                            abs(our_value) / abs(yf_value),
                            False,
                        )
                    continue
                ratio = abs(our_value) / abs(yf_value)
                divergent = not (_DIVERGENCE_RATIO > ratio > (1.0 / _DIVERGENCE_RATIO))

                if not dry_run:
                    _record_line_item(cur, symbol, table, field, fiscal_year, our_value, yf_value, ratio, divergent)

                if divergent:
                    flagged[field_key].append(
                        {
                            "symbol": symbol,
                            "fiscal_year": fiscal_year,
                            "our_value": our_value,
                            "yfinance_value": yf_value,
                            "ratio": round(ratio, 4),
                        }
                    )

        last_symbol_checked = symbol

        is_last = i == len(symbols) - 1
        if delay_seconds > 0 and not is_last and consecutive_ban_errors < _MAX_CONSECUTIVE_BAN_ERRORS:
            time.sleep(delay_seconds)

    results: list[CheckResult] = []
    for table, field, _, _ in _FIELDS:
        field_key = f"{table}:{field}"
        check_name = f"yfinance_independent_crosscheck_{field}"
        examples = flagged[field_key]
        n_sampled = sampled_count[field_key]
        if examples:
            results.append(
                CheckResult(
                    check_name,
                    "warn",
                    table,
                    f"{len(examples)}/{n_sampled} symbol(s) with a yfinance-comparable {field} value "
                    f"diverge >{_DIVERGENCE_RATIO:.0f}x from our SEC-derived value - review queue, not a "
                    "confirmed bug: restatements, non-GAAP reclassification, and fiscal-period "
                    "misalignment can all produce this.",
                    {"sampled": n_sampled, "flagged": len(examples), "examples": examples[:_MAX_EXAMPLES_PER_FIELD]},
                )
            )
        else:
            results.append(
                CheckResult(
                    check_name,
                    "info",
                    table,
                    f"no >{_DIVERGENCE_RATIO:.0f}x yfinance divergence in {field} ({n_sampled} symbol(s) "
                    "had a comparable yfinance value this run)",
                )
            )

    if dry_run:
        for r in results:
            logger.info(f"[DRY-RUN] [{r.severity.upper()}] {r.check_name}: {r.message}")
    else:
        run_id = uuid.uuid4().hex
        patrol_logger = PatrolLogger(run_id)
        patrol_logger.log_results(cur, results)
        if sweep and last_symbol_checked is not None:
            _advance_sweep_cursor(cur, last_symbol_checked)
        conn.commit()
        logger.info(f"[YFINANCE_CROSSCHECK] Logged {len(results)} result(s) to data_patrol_log (run_id={run_id})")

    cur.close()
    conn.close()
    return {"sampled_symbols": len(symbols), "results": [r.to_dict() for r in results]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=25, help="How many symbols to sample this run (default 25)")
    parser.add_argument("--symbols", help="Comma-separated explicit symbol list, overrides --limit sampling")
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="Walk the active universe alphabetically via a persistent cursor instead of random daily sampling",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print findings, don't write to DB")
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=_DEFAULT_INTER_SYMBOL_DELAY_SECS,
        help=f"Pause between symbols to avoid tripping the shared-IP rate limit (default {_DEFAULT_INTER_SYMBOL_DELAY_SECS}s)",
    )
    args = parser.parse_args()

    symbols_override = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None

    started = time.monotonic()
    summary = run(
        limit=args.limit,
        symbols_override=symbols_override,
        dry_run=args.dry_run,
        sweep=args.sweep,
        delay_seconds=args.delay_seconds,
    )
    elapsed = time.monotonic() - started
    logger.info(f"[YFINANCE_CROSSCHECK] Done in {elapsed:.1f}s - {summary['sampled_symbols']} symbol(s) sampled")


if __name__ == "__main__":
    main()
