"""Tests for scripts/xbrl_yfinance_quarterly_crosscheck.py (added 2026-09-17: quarterly
counterpart to scripts/xbrl_yfinance_crosscheck.py - the annual crosscheck never covered
quarterly_income_statement/quarterly_balance_sheet/quarterly_cash_flow, a real blind spot
found while working the 2026-09-16 divergence-repair incident). Mirrors
tests/unit/test_xbrl_yfinance_crosscheck_20260910.py's patterns, adapted for the extra
fiscal_quarter dimension and calendar-quarter ("fiscal_period": "Qn") matching.
"""

from unittest.mock import MagicMock, patch

from scripts.xbrl_yfinance_quarterly_crosscheck import _our_all_values, run


def _make_cur(is_fpi: bool, our_values: dict[tuple[str, str], tuple[int, int, float]]):
    """our_values: {(table, field): (fiscal_year, fiscal_quarter, value)}."""
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
            if f", {field}\n" in query or f"({field} + COALESCE(" in query:
                return [value]
        return []

    cur.fetchone.side_effect = _fetchone
    cur.fetchall.side_effect = _fetchall
    return cur


def _yf_side_effect(income=None, balance=None, cashflow=None):
    mapping = {"income": income, "balance": balance, "cashflow": cashflow}

    def _fetch(symbol, statement_type, period, is_known_foreign_issuer=False):
        assert period == "quarterly"
        return mapping[statement_type]

    return _fetch


class TestOurAllValuesComposite:
    def test_depreciation_expense_sums_amortization_expense(self):
        cur = MagicMock()
        cur.fetchall.return_value = [(2025, 3, 150.0)]

        result = _our_all_values(cur, "quarterly_income_statement", "depreciation_expense", "AAA")

        query = cur.execute.call_args[0][0]
        assert "amortization_expense" in query
        assert "COALESCE" in query
        assert result == [(2025, 3, 150.0)]

    def test_other_fields_are_not_summed(self):
        cur = MagicMock()
        cur.fetchall.return_value = [(2025, 3, 100.0)]

        _our_all_values(cur, "quarterly_income_statement", "revenue", "AAA")

        query = cur.execute.call_args[0][0]
        assert "amortization_expense" not in query
        assert "COALESCE" not in query


class TestXbrlYfinanceQuarterlyCrosscheck:
    def test_flags_diverging_field_and_leaves_matching_fields_clean(self):
        cur = _make_cur(
            is_fpi=False,
            our_values={
                ("quarterly_income_statement", "revenue"): (2025, 3, 100_000_000.0),  # diverges 3x vs yfinance
                ("quarterly_income_statement", "net_income"): (2025, 3, 10_000_000.0),  # matches
            },
        )
        conn = MagicMock()
        conn.cursor.return_value = cur

        fetch_fn = _yf_side_effect(
            income=[
                {"fiscal_year": 2025, "fiscal_period": "Q3", "revenues": 300_000_000.0, "net_income_loss": 10_000_000.0}
            ],
        )

        with (
            patch("utils.db.connection.get_db_connection", return_value=conn),
            patch("utils.external.yfinance_financials.fetch_financial_statement", side_effect=fetch_fn),
        ):
            summary = run(limit=25, symbols_override=["AAA"], dry_run=True, delay_seconds=0)

        results_by_check = {r["check"]: r for r in summary["results"]}
        revenue_result = results_by_check["yfinance_independent_quarterly_crosscheck_revenue"]
        assert revenue_result["severity"] == "warn"
        assert revenue_result["details"]["flagged"] == 1
        assert revenue_result["details"]["examples"][0]["fiscal_quarter"] == 3

        net_income_result = results_by_check["yfinance_independent_quarterly_crosscheck_net_income"]
        assert net_income_result["severity"] == "info"

    def test_mismatched_quarter_number_is_not_compared(self):
        # Our Q3 vs yfinance's Q1 for the same fiscal_year must not be treated as a match OR a
        # divergence - they're simply not the same period, so no comparison should be recorded.
        cur = _make_cur(
            is_fpi=False,
            our_values={("quarterly_income_statement", "revenue"): (2025, 3, 100_000_000.0)},
        )
        conn = MagicMock()
        conn.cursor.return_value = cur

        fetch_fn = _yf_side_effect(income=[{"fiscal_year": 2025, "fiscal_period": "Q1", "revenues": 100_000_000.0}])

        with (
            patch("utils.db.connection.get_db_connection", return_value=conn),
            patch("utils.external.yfinance_financials.fetch_financial_statement", side_effect=fetch_fn),
        ):
            summary = run(limit=25, symbols_override=["AAA"], dry_run=True, delay_seconds=0)

        revenue_result = next(
            r for r in summary["results"] if r["check"] == "yfinance_independent_quarterly_crosscheck_revenue"
        )
        assert revenue_result["severity"] == "info"

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

    def test_live_run_writes_period_type_quarterly_and_advances_its_own_cursor(self):
        cur = _make_cur(
            is_fpi=False,
            our_values={("quarterly_income_statement", "revenue"): (2025, 3, 100_000_000.0)},
        )
        conn = MagicMock()
        conn.cursor.return_value = cur

        fetch_fn = _yf_side_effect(income=[{"fiscal_year": 2025, "fiscal_period": "Q3", "revenues": 100_000_000.0}])

        with (
            patch("utils.db.connection.get_db_connection", return_value=conn),
            patch("utils.external.yfinance_financials.fetch_financial_statement", side_effect=fetch_fn),
            patch("algo.monitoring.data_patrol.logger.PatrolLogger") as mock_logger_cls,
        ):
            run(limit=25, symbols_override=["AAA"], dry_run=False, sweep=True, delay_seconds=0)

        insert_calls = [
            c for c in cur.execute.call_args_list if "INSERT INTO xbrl_yfinance_line_item_report" in c[0][0]
        ]
        assert insert_calls, "expected at least one recorded comparison"
        assert "'quarterly'" in insert_calls[0][0][0]

        cursor_calls = [c for c in cur.execute.call_args_list if "xbrl_yfinance_crosscheck_progress" in c[0][0]]
        assert cursor_calls
        # Quarterly sweep must advance cursor id=2, never id=1 (the annual sweep's cursor).
        assert cursor_calls[-1][0][1] == (2, "AAA")

        mock_logger_cls.return_value.log_results.assert_called_once()
        conn.commit.assert_called_once()

    def test_aborts_batch_after_consecutive_shared_ip_ban_errors(self):
        cur = _make_cur(is_fpi=False, our_values={("quarterly_income_statement", "revenue"): (2025, 3, 100.0)})
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

        assert call_count["n"] == 3
