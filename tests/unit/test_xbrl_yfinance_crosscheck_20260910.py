"""Tests for scripts/xbrl_yfinance_crosscheck.py (goal session 2026-09-10: periodic
independent-second-opinion cross-check of SEC-XBRL-derived financial statement values
against yfinance's own, independently-parsed financials).
"""

from unittest.mock import MagicMock, patch

from scripts.xbrl_yfinance_crosscheck import run


def _make_cur(fetchone_sequence):
    cur = MagicMock()
    cur.fetchone.side_effect = fetchone_sequence
    return cur


def _yf_side_effect(income=None, balance=None, cashflow=None):
    mapping = {"income": income, "balance": balance, "cashflow": cashflow}

    def _fetch(symbol, statement_type, period, is_known_foreign_issuer=False):
        return mapping[statement_type]

    return _fetch


class TestXbrlYfinanceCrosscheck:
    def test_flags_diverging_field_and_leaves_matching_fields_clean(self):
        # Order matches run()'s per-symbol query sequence: is_foreign_private_issuer, then
        # one _our_latest_value lookup per _FIELDS entry (revenue, net_income, total_assets,
        # stockholders_equity, operating_cash_flow).
        cur = _make_cur(
            [
                (False,),  # is_foreign_private_issuer
                (2025, 100_000_000.0),  # revenue - will diverge 3x vs yfinance
                (2025, 10_000_000.0),  # net_income - matches
                (2025, 500_000_000.0),  # total_assets - matches
                (2025, 200_000_000.0),  # stockholders_equity - matches
                (2025, 20_000_000.0),  # operating_cash_flow - matches
            ]
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
            summary = run(limit=25, symbols_override=["AAA"], dry_run=True)

        results_by_check = {r["check"]: r for r in summary["results"]}
        revenue_result = results_by_check["yfinance_independent_crosscheck_revenue"]
        assert revenue_result["severity"] == "warn"
        assert revenue_result["details"]["flagged"] == 1
        assert revenue_result["details"]["examples"][0]["symbol"] == "AAA"

        for field in ("net_income", "total_assets", "stockholders_equity", "operating_cash_flow"):
            clean_result = results_by_check[f"yfinance_independent_crosscheck_{field}"]
            assert clean_result["severity"] == "info"

    def test_dry_run_never_writes_to_data_patrol_log(self):
        cur = _make_cur([(False,), (2025, 100.0), (2025, 100.0), (2025, 100.0), (2025, 100.0), (2025, 100.0)])
        conn = MagicMock()
        conn.cursor.return_value = cur

        with (
            patch("utils.db.connection.get_db_connection", return_value=conn),
            patch("utils.external.yfinance_financials.fetch_financial_statement", return_value=None),
            patch("algo.monitoring.data_patrol.logger.PatrolLogger") as mock_logger_cls,
        ):
            run(limit=25, symbols_override=["AAA"], dry_run=True)

        mock_logger_cls.assert_not_called()
        conn.commit.assert_not_called()

    def test_live_run_logs_results_and_commits(self):
        cur = _make_cur([(False,), (2025, 100.0), (2025, 100.0), (2025, 100.0), (2025, 100.0), (2025, 100.0)])
        conn = MagicMock()
        conn.cursor.return_value = cur

        with (
            patch("utils.db.connection.get_db_connection", return_value=conn),
            patch("utils.external.yfinance_financials.fetch_financial_statement", return_value=None),
            patch("algo.monitoring.data_patrol.logger.PatrolLogger") as mock_logger_cls,
        ):
            run(limit=25, symbols_override=["AAA"], dry_run=False)

        mock_logger_cls.return_value.log_results.assert_called_once()
        conn.commit.assert_called_once()

    def test_aborts_batch_after_consecutive_shared_ip_ban_errors(self):
        # Every symbol's is_foreign_private_issuer + 5 field lookups all return a row, but
        # every yfinance fetch raises a shared-IP-ban RuntimeError - after 3 consecutive such
        # errors the batch must stop calling fetch_financial_statement for later symbols
        # rather than burning through the whole sample uselessly.
        per_symbol_rows = [(False,), (2025, 100.0), (2025, 100.0), (2025, 100.0), (2025, 100.0), (2025, 100.0)]
        cur = _make_cur(per_symbol_rows * 5)
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
            run(limit=25, symbols_override=["AAA", "BBB", "CCC", "DDD", "EEE"], dry_run=True)

        # 3 consecutive ban errors trip the abort - only the first symbol's 5 field lookups
        # (1 fetch per distinct statement_type: income, balance, cashflow) should have fired.
        assert call_count["n"] == 3
