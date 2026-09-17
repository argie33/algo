"""Tests for scripts/xbrl_yfinance_crosscheck.py (goal session 2026-09-10: periodic
independent-second-opinion cross-check of SEC-XBRL-derived financial statement values
against yfinance's own, independently-parsed financials).

EXPANDED 2026-09-16 (goal session: full line-item coverage) alongside the script itself:
_FIELDS grew from 5 to 29 entries, so a fixed-length fetchone() side_effect list is no longer
maintainable here - _make_cur now dispatches on the executed SQL text instead, keyed by
table/field, and returns None (no row) for any field a test doesn't care about. This is more
robust to future _FIELDS changes than counting exact call positions.
"""

from unittest.mock import MagicMock, patch

from scripts.xbrl_yfinance_crosscheck import _our_all_values, run


def _make_cur(is_fpi: bool, our_values: dict[tuple[str, str], tuple[int, float]]):
    """our_values: {(table, field): (fiscal_year, value)} - any (table, field) not present
    behaves as "no comparable row for this symbol/field", same as a real NULL/missing row.

    _our_all_values (CHANGED 2026-09-17 - compares every fiscal year on file, not just the
    latest) reads via fetchall(), not fetchone() - is_foreign_private_issuer still uses
    fetchone() so both need wiring here.
    """
    cur = MagicMock()

    def _fetchone():
        query = cur.execute.call_args[0][0]
        if "is_foreign_private_issuer" in query:
            return (is_fpi,)
        return None

    def _fetchall():
        query = cur.execute.call_args[0][0]
        for (table, field), value in our_values.items():
            if f"FROM {table}" not in query:
                continue
            # Composite fields (e.g. depreciation_expense + amortization_expense) select
            # "(field + COALESCE(extra, 0))" instead of a bare "field" - match either shape.
            if f", {field}\n" in query or f"({field} + COALESCE(" in query:
                return [value]
        return []

    cur.fetchone.side_effect = _fetchone
    cur.fetchall.side_effect = _fetchall
    return cur


def _yf_side_effect(income=None, balance=None, cashflow=None):
    mapping = {"income": income, "balance": balance, "cashflow": cashflow}

    def _fetch(symbol, statement_type, period, is_known_foreign_issuer=False):
        return mapping[statement_type]

    return _fetch


class TestOurLatestValueComposite:
    # ADDED 2026-09-16 (real batch on live data): yfinance's "depreciation" concept is the
    # cashflow-statement's combined D&A add-back, not pure depreciation - live-confirmed on
    # ABT/ABBV/ADI, whose depreciation_expense + amortization_expense summed to yfinance's
    # value to the exact dollar. Comparing depreciation_expense alone produced a ~48%
    # false-divergence rate on the first real batch.
    def test_depreciation_expense_sums_amortization_expense(self):
        cur = MagicMock()
        cur.fetchall.return_value = [(2025, 150.0), (2024, 140.0)]

        result = _our_all_values(cur, "annual_income_statement", "depreciation_expense", "AAA")

        query = cur.execute.call_args[0][0]
        assert "amortization_expense" in query
        assert "COALESCE" in query
        assert result == [(2025, 150.0), (2024, 140.0)]

    def test_other_fields_are_not_summed(self):
        cur = MagicMock()
        cur.fetchall.return_value = [(2025, 100.0)]

        _our_all_values(cur, "annual_income_statement", "revenue", "AAA")

        query = cur.execute.call_args[0][0]
        assert "amortization_expense" not in query
        assert "COALESCE" not in query


class TestXbrlYfinanceCrosscheck:
    def test_flags_diverging_field_and_leaves_matching_fields_clean(self):
        cur = _make_cur(
            is_fpi=False,
            our_values={
                ("annual_income_statement", "revenue"): (2025, 100_000_000.0),  # diverges 3x vs yfinance
                ("annual_income_statement", "net_income"): (2025, 10_000_000.0),  # matches
                ("annual_balance_sheet", "total_assets"): (2025, 500_000_000.0),  # matches
                ("annual_balance_sheet", "stockholders_equity"): (2025, 200_000_000.0),  # matches
                ("annual_cash_flow", "operating_cash_flow"): (2025, 20_000_000.0),  # matches
            },
        )
        conn = MagicMock()
        conn.cursor.return_value = cur

        fetch_fn = _yf_side_effect(
            income=[{"fiscal_year": 2025, "revenues": 300_000_000.0, "net_income_loss": 10_000_000.0}],
            balance=[{"fiscal_year": 2025, "assets": 500_000_000.0, "stockholders_equity": 200_000_000.0}],
            cashflow=[{"fiscal_year": 2025, "net_cash_provided_by_used_in_operating_activities": 20_000_000.0}],
        )

        with (
            patch("utils.db.connection.get_db_connection", return_value=conn),
            patch("utils.external.yfinance_financials.fetch_financial_statement", side_effect=fetch_fn),
        ):
            summary = run(limit=25, symbols_override=["AAA"], dry_run=True, delay_seconds=0)

        results_by_check = {r["check"]: r for r in summary["results"]}
        revenue_result = results_by_check["yfinance_independent_crosscheck_revenue"]
        assert revenue_result["severity"] == "warn"
        assert revenue_result["details"]["flagged"] == 1
        assert revenue_result["details"]["examples"][0]["symbol"] == "AAA"

        for field in ("net_income", "total_assets", "stockholders_equity", "operating_cash_flow"):
            clean_result = results_by_check[f"yfinance_independent_crosscheck_{field}"]
            assert clean_result["severity"] == "info"

    def test_compares_every_fiscal_year_on_file_not_just_the_latest(self):
        # ADDED 2026-09-17: _our_all_values replaced _our_latest_value (which was ORDER BY
        # fiscal_year DESC LIMIT 1) precisely because live data showed the report table averaged
        # only 1.26 distinct fiscal years/symbol despite 4-5+ years typically on file. A single
        # symbol with 3 years of revenue on our side and matching yfinance rows for all 3 must
        # produce 3 recorded comparisons, not 1.
        cur = _make_cur(is_fpi=False, our_values={})
        cur.fetchall.side_effect = None
        # Values must clear _DIVERGENCE_FLOOR_DOLLARS (1,000,000) or the comparison is skipped
        # as "too small to check" before a row is ever recorded.
        cur.fetchall.return_value = [(2025, 100_000_000.0), (2024, 90_000_000.0), (2023, 80_000_000.0)]
        conn = MagicMock()
        conn.cursor.return_value = cur

        fetch_fn = _yf_side_effect(
            income=[
                {"fiscal_year": 2025, "revenues": 100_000_000.0},
                {"fiscal_year": 2024, "revenues": 90_000_000.0},
                {"fiscal_year": 2023, "revenues": 80_000_000.0},
            ]
        )

        with (
            patch("utils.db.connection.get_db_connection", return_value=conn),
            patch("utils.external.yfinance_financials.fetch_financial_statement", side_effect=fetch_fn),
            patch("algo.monitoring.data_patrol.logger.PatrolLogger"),
        ):
            run(limit=25, symbols_override=["AAA"], dry_run=False, delay_seconds=0)

        record_calls = [
            c for c in cur.execute.call_args_list if "INSERT INTO xbrl_yfinance_line_item_report" in c[0][0]
        ]
        revenue_years = {c[0][1][3] for c in record_calls if c[0][1][2] == "revenue"}
        assert revenue_years == {2025, 2024, 2023}

    def test_dry_run_never_writes_to_data_patrol_log(self):
        cur = _make_cur(is_fpi=False, our_values={})
        conn = MagicMock()
        conn.cursor.return_value = cur

        with (
            patch("utils.db.connection.get_db_connection", return_value=conn),
            patch("utils.external.yfinance_financials.fetch_financial_statement", return_value=None),
            patch("algo.monitoring.data_patrol.logger.PatrolLogger") as mock_logger_cls,
        ):
            run(limit=25, symbols_override=["AAA"], dry_run=True, delay_seconds=0)

        mock_logger_cls.assert_not_called()
        conn.commit.assert_not_called()

    def test_live_run_logs_results_and_commits(self):
        cur = _make_cur(is_fpi=False, our_values={})
        conn = MagicMock()
        conn.cursor.return_value = cur

        with (
            patch("utils.db.connection.get_db_connection", return_value=conn),
            patch("utils.external.yfinance_financials.fetch_financial_statement", return_value=None),
            patch("algo.monitoring.data_patrol.logger.PatrolLogger") as mock_logger_cls,
        ):
            run(limit=25, symbols_override=["AAA"], dry_run=False, delay_seconds=0)

        mock_logger_cls.return_value.log_results.assert_called_once()
        conn.commit.assert_called_once()

    def test_aborts_batch_after_consecutive_shared_ip_ban_errors(self):
        # Every symbol has a comparable revenue row, but every yfinance fetch raises a
        # shared-IP-ban RuntimeError - after 3 consecutive such errors the batch must stop
        # calling fetch_financial_statement for later symbols rather than burning through the
        # whole sample uselessly.
        cur = _make_cur(is_fpi=False, our_values={("annual_income_statement", "revenue"): (2025, 100.0)})
        conn = MagicMock()
        conn.cursor.return_value = cur

        call_count = {"n": 0}

        def _raise_ban(symbol, statement_type, period, is_known_foreign_issuer=False):
            call_count["n"] += 1
            raise RuntimeError("yfinance shared IP ban active: still banned")

        with (
            patch("utils.db.connection.get_db_connection", return_value=conn),
            patch("utils.external.yfinance_financials.fetch_financial_statement", side_effect=_raise_ban),
        ):
            run(limit=25, symbols_override=["AAA", "BBB", "CCC", "DDD", "EEE"], dry_run=True, delay_seconds=0)

        # 3 consecutive ban errors trip the abort - only the first symbol's revenue lookup
        # (1 fetch for statement_type='income') should have fired per symbol before aborting;
        # only 3 symbols get that far before the abort kicks in.
        assert call_count["n"] == 3

    def test_delay_seconds_paces_between_symbols_but_not_after_the_last_one(self):
        # ADDED 2026-09-16 (user-requested after a live batch ran with zero inter-symbol
        # pacing): confirms run() actually sleeps between symbols by the requested amount,
        # and doesn't waste a sleep after the final symbol (nothing left to pace against).
        cur = _make_cur(is_fpi=False, our_values={})
        conn = MagicMock()
        conn.cursor.return_value = cur

        with (
            patch("utils.db.connection.get_db_connection", return_value=conn),
            patch("utils.external.yfinance_financials.fetch_financial_statement", return_value=None),
            patch("scripts.xbrl_yfinance_crosscheck.time.sleep") as mock_sleep,
        ):
            run(limit=25, symbols_override=["AAA", "BBB", "CCC"], dry_run=True, delay_seconds=5.0)

        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(5.0)

    def test_delay_seconds_skipped_after_ban_abort(self):
        cur = _make_cur(is_fpi=False, our_values={("annual_income_statement", "revenue"): (2025, 100.0)})
        conn = MagicMock()
        conn.cursor.return_value = cur

        def _raise_ban(symbol, statement_type, period, is_known_foreign_issuer=False):
            raise RuntimeError("yfinance shared IP ban active: still banned")

        with (
            patch("utils.db.connection.get_db_connection", return_value=conn),
            patch("utils.external.yfinance_financials.fetch_financial_statement", side_effect=_raise_ban),
            patch("scripts.xbrl_yfinance_crosscheck.time.sleep") as mock_sleep,
        ):
            run(limit=25, symbols_override=["AAA", "BBB", "CCC", "DDD", "EEE"], dry_run=True, delay_seconds=5.0)

        # consecutive_ban_errors only reaches the threshold (3) once the 3rd symbol's fetch
        # has already failed, so symbols 1 and 2 still sleep before it - only the sleep after
        # symbol 3 (which would immediately precede the abort) is skipped.
        assert mock_sleep.call_count == 2
