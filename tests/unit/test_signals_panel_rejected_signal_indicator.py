"""Regression test (2026-08-18): the SIGNALS panel's "ACTIVE BUY SIGNALS" table showed the
full algo_signals candidate pool (a deliberate design choice - see the REGRESSION FIX
comment in lambda/api/routes/algo_handlers/dashboard.py::_get_dashboard_signals, most
rejections are portfolio-capacity/risk-limit blocks unrelated to signal quality) but never
selected or displayed execution_status, so a viewer had no way to tell a live actionable
signal apart from one the algo had already rejected.

Live-confirmed 2026-08-17: 14/22 signals for the latest date were execution_status=
'rejected' (e.g. IOSP: "concentration_prefilter: already_entered_today: 1 existing
trade(s)"), all displayed identically under the "ACTIVE BUY SIGNALS ★" header with no
visual distinction. Fixed by having the backend select execution_status/rejection_reason
(appended, not inserted, so the existing row[1]=signal_quality_score positional index used
elsewhere in the handler stays correct) and having this panel mark rejected rows.
"""

from dashboard.panels.signals import _build_buy_signals_table


def _sig(symbol: str, execution_status: str | None = None, **overrides: object) -> dict:
    row = {
        "symbol": symbol,
        "signal_quality_score": 74,
        "close": 93.85,
        "entry_price": 93.83,
        "buylevel": 87.82,
        "stoplevel": 79.44,
        "risk_reward_ratio": 0.78,
        "execution_status": execution_status,
    }
    row.update(overrides)
    return row


class TestSignalsPanelRejectedIndicator:
    def test_rejected_signal_symbol_is_marked_not_shown_as_plain_active(self):
        rows = _build_buy_signals_table([_sig("IOSP", execution_status="rejected")])
        table = rows[1]  # rows[0] is the header Text, rows[1] is the Table
        cell = table.columns[0]._cells[0]
        assert "✗" in cell.plain

    def test_executed_signal_symbol_has_no_rejection_marker(self):
        rows = _build_buy_signals_table([_sig("AAPL", execution_status="executed")])
        table = rows[1]
        cell = table.columns[0]._cells[0]
        assert "✗" not in cell.plain
        assert cell.plain.strip() == "AAPL"

    def test_header_counts_rejected_signals_separately(self):
        rows = _build_buy_signals_table(
            [
                _sig("IOSP", execution_status="rejected"),
                _sig("WPM", execution_status="rejected"),
                _sig("AAPL", execution_status="executed"),
            ]
        )
        header_text = rows[0].plain
        assert "2 already rejected" in header_text

    def test_header_omits_rejected_count_when_none_rejected(self):
        rows = _build_buy_signals_table([_sig("AAPL", execution_status="executed")])
        header_text = rows[0].plain
        assert "rejected" not in header_text
