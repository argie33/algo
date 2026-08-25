"""Regression test for the 2026-08-25 fix (goal session, financial-review audit):
pretrade_checks.py's sector/industry position caps only catch concentration within
GICS-style taxonomy - two names in different sectors/industries can still move nearly in
lockstep (e.g. high-beta growth names across sectors during a risk-off day), so a book could
clear every existing diversification check while still holding several near-duplicate return
streams.

PreTradeChecks._check_correlation_concentration() (algo/trading/pretrade_checks.py) now blocks
a new entry whose trailing daily-return correlation with any currently open position exceeds
max_position_correlation, computed over correlation_lookback_days. It fails OPEN (never
blocks) when there isn't enough overlapping real price history to trust the estimate, since
this is a supplementary control, not a replacement for the primary sector/industry caps.
"""

from datetime import date, timedelta

from algo.trading.pretrade_checks import PreTradeChecks, _pearson_correlation


def _config(**overrides):
    base = {
        "max_position_correlation": 0.85,
        "correlation_lookback_days": 60,
        "correlation_min_overlap_days": 5,
    }
    base.update(overrides)
    return base


class _FakeCursor:
    """Minimal psycopg2-cursor stand-in: execute() records the query, fetchall()/fetchone()
    return whatever the matching canned response says based on call order."""

    def __init__(self, open_symbols_row, price_rows):
        self._open_symbols_row = open_symbols_row
        self._price_rows = price_rows
        self._last_query_kind = None

    def execute(self, query, params=None):
        if "FROM algo_positions" in query:
            self._last_query_kind = "positions"
        elif "FROM price_daily" in query:
            self._last_query_kind = "prices"
        else:
            raise AssertionError(f"unexpected query: {query}")

    def fetchall(self):
        if self._last_query_kind == "positions":
            return self._open_symbols_row
        return self._price_rows


def _price_series(symbol, start, values):
    return [(symbol, start + timedelta(days=i), v) for i, v in enumerate(values)]


class TestPearsonCorrelation:
    def test_identical_series_perfectly_correlated(self):
        series = [0.01, -0.02, 0.03, 0.015, -0.01, 0.02, -0.005]
        assert _pearson_correlation(series, series) == 1.0

    def test_inverted_series_perfectly_anticorrelated(self):
        series = [0.01, -0.02, 0.03, 0.015, -0.01, 0.02, -0.005]
        inverted = [-x for x in series]
        assert round(_pearson_correlation(series, inverted), 6) == -1.0

    def test_too_short_returns_none(self):
        assert _pearson_correlation([0.01], [0.02]) is None

    def test_mismatched_lengths_returns_none(self):
        assert _pearson_correlation([0.01, 0.02], [0.01]) is None

    def test_zero_variance_series_returns_none(self):
        assert _pearson_correlation([0.0, 0.0, 0.0], [0.01, -0.02, 0.03]) is None


class TestCorrelationConcentrationCheck:
    def test_no_open_positions_passes(self):
        checks = PreTradeChecks(config=_config())
        cur = _FakeCursor(open_symbols_row=[], price_rows=[])
        ok, reason = checks._check_correlation_concentration("NEWSYM", cur)
        assert ok is True
        assert reason is None

    def test_highly_correlated_candidate_blocked(self):
        checks = PreTradeChecks(config=_config())
        start = date(2026, 1, 1)
        # Two symbols moving in lockstep - correlation should be ~1.0, well above the 0.85 cap.
        base_prices = [100 + i * 0.5 + (1 if i % 2 == 0 else -0.5) for i in range(20)]
        rows = _price_series("NEWSYM", start, base_prices) + _price_series("HELD", start, [p * 2 for p in base_prices])
        cur = _FakeCursor(open_symbols_row=[("HELD",)], price_rows=rows)

        ok, reason = checks._check_correlation_concentration("NEWSYM", cur)

        assert ok is False
        assert reason is not None
        assert "HELD" in reason
        assert "0.85" in reason

    def test_uncorrelated_candidate_passes(self):
        checks = PreTradeChecks(config=_config())
        start = date(2026, 1, 1)
        # Alternating up/down for one symbol, monotonic for the other - near-zero correlation.
        candidate_prices = [100, 102, 99, 103, 98, 104, 97, 105, 96, 106, 95, 107]
        held_prices = [50 + i * 0.1 for i in range(len(candidate_prices))]
        rows = _price_series("NEWSYM", start, candidate_prices) + _price_series("HELD", start, held_prices)
        cur = _FakeCursor(open_symbols_row=[("HELD",)], price_rows=rows)

        ok, reason = checks._check_correlation_concentration("NEWSYM", cur)

        assert ok is True
        assert reason is None

    def test_insufficient_overlap_fails_open(self):
        checks = PreTradeChecks(config=_config(correlation_min_overlap_days=30))
        start = date(2026, 1, 1)
        prices = [100, 101, 102]  # far fewer than the 30-day minimum overlap
        rows = _price_series("NEWSYM", start, prices) + _price_series("HELD", start, [p * 2 for p in prices])
        cur = _FakeCursor(open_symbols_row=[("HELD",)], price_rows=rows)

        ok, reason = checks._check_correlation_concentration("NEWSYM", cur)

        assert ok is True
        assert reason is None

    def test_missing_config_key_raises(self):
        checks = PreTradeChecks(config={})
        cur = _FakeCursor(open_symbols_row=[("HELD",)], price_rows=[])
        try:
            checks._check_correlation_concentration("NEWSYM", cur)
            raise AssertionError("expected KeyError for missing correlation config")
        except KeyError:
            pass
