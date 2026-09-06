"""Regression test: when all 7 core quality ratios (roe, roa, operating_margin, net_margin,
debt_to_equity, debt_to_assets, current_ratio) are None, the row-level early return must reuse
the same structural gate as the per-field fixes instead of a blanket "missing_sec_data" that
discards every specific reason the rest of the function would otherwise have computed.

Found live 2026-09-02: this early return (loaders/load_value_quality_growth_metrics.py, "Mark
unavailable if all metrics are None") fires BEFORE any of the per-field reason blocks fixed
earlier this session ever run - it was the actual reason those fixes weren't reflected in most
of their live counts. Live-confirmed exactly 68 universe symbols hit this path with
data_unavailable=True, reason='missing_sec_data'; 44 (65%) have zero stockholders_equity/
total_assets/total_liabilities across all 3 recent fiscal years simultaneously (live-verified
directly against CIG.C via loader.fetch_incremental()).
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _empty_quality_row(fiscal_year=2024):
    # 34-column shape (index 33 = prior_year_gross_profit) - everything None except fiscal_year,
    # so every one of the 7 core ratios comes out None and the row-level early return fires.
    row = [None] * 34
    row[8] = fiscal_year
    return row


class _FakeCursor:
    def __init__(self, no_recent_equity_symbols, never_tagged_total_assets_symbols=frozenset()):
        self._no_recent_equity = no_recent_equity_symbols
        self._never_tagged_total_assets = never_tagged_total_assets_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if (
            "annual_balance_sheet" in self._last_query
            and "stockholders_equity" in self._last_query
            and "cash_and_equivalents" not in self._last_query
            and "etf_symbols" not in self._last_query
        ):
            return [(s,) for s in self._no_recent_equity]
        if "annual_balance_sheet" in self._last_query and "total_assets" in self._last_query:
            return [(s,) for s in self._never_tagged_total_assets]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, no_recent_equity_symbols=frozenset(), never_tagged_total_assets_symbols=frozenset()):
        self._no_recent_equity = no_recent_equity_symbols
        self._never_tagged_total_assets = never_tagged_total_assets_symbols

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._no_recent_equity, self._never_tagged_total_assets)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, no_recent_equity_symbols=frozenset(), never_tagged_total_assets_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(
        mod, "DatabaseContext", _FakeDatabaseContext(no_recent_equity_symbols, never_tagged_total_assets_symbols)
    )
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestAllCoreRatiosMissingRowLevelReason:
    def test_no_recent_balance_sheet_data_gets_specific_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_equity_symbols=frozenset({"FPICO"}))

        metrics = loader._compute_quality_metrics("FPICO", _empty_quality_row(), ev_metrics=None)

        assert metrics["data_unavailable"] is True
        assert metrics["reason"] == "no_recent_balance_sheet_data_reported"
        # Propagates to every field, not just the 7 checked in the early-return condition.
        assert metrics["roe_unavailable_reason"] == "no_recent_balance_sheet_data_reported"
        assert metrics["debt_to_equity_unavailable_reason"] == "no_recent_balance_sheet_data_reported"
        assert metrics["operating_cash_flow_unavailable_reason"] == "no_recent_balance_sheet_data_reported"

    def test_symbol_not_in_gate_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_equity_symbols=frozenset({"FPICO"}))

        metrics = loader._compute_quality_metrics("NORMALCO", _empty_quality_row(), ev_metrics=None)

        assert metrics["data_unavailable"] is True
        assert metrics["reason"] == "missing_sec_data"
        assert metrics["roe_unavailable_reason"] == "missing_sec_data"

    def test_real_zero_total_assets_gets_specific_reason_not_generic(self, monkeypatch):
        """FIXED 2026-09-05 (goal session: "SEC/XBRL missing data to zero" follow-up). A real,
        reported $0.00 total_assets/stockholders_equity (a blank-check/shell company
        pre-merger) makes every core ratio genuinely undefined (division by zero) - the
        row-level early return's own reason derivation only checked `stockholders_equity is
        None`, missing this "real zero" case entirely and defaulting to generic
        "missing_sec_data" even though a real, knowable cause was available. Live-confirmed
        OBX: real total_assets=$0.00/stockholders_equity=$0.00 (2026 anchor row, not
        data_unavailable).
        """
        loader = _make_loader(monkeypatch, never_tagged_total_assets_symbols=frozenset({"OBX"}))
        row = _empty_quality_row()
        row[0] = 0.0  # stockholders_equity (real zero, not None)
        row[2] = 0.0  # total_assets (real zero, not None)

        metrics = loader._compute_quality_metrics("OBX", row, ev_metrics=None)

        assert metrics["data_unavailable"] is True
        assert metrics["reason"] == "no_recent_balance_sheet_data_reported"
