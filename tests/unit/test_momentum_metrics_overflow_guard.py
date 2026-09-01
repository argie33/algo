#!/usr/bin/env python3
"""Regression test for RiskMetricsLoader._compute_momentum_row's overflow guard
(loaders/load_risk_metrics_daily.py).

momentum_metrics.momentum_{1m,3m,6m,12m} are NUMERIC(8,4) - max magnitude 9999.9999.
Live-confirmed 2026-08-19: DFNS failed this loader's write every single run with
"numeric field overflow" - an extreme micro-cap price move (reverse split / near-worthless-
to-recovered) over the lookback window produced a >=10,000% raw return, the same "extreme
micro-cap volatility" failure mode already guarded for roc_Xd via ROC_OVERFLOW_SKIP in
load_prices.py. Fixed by nulling out just the implausible period instead of letting the
whole row crash at insert time.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from loaders.load_risk_metrics_daily import RiskMetricsLoader


def _make_loader() -> RiskMetricsLoader:
    loader = RiskMetricsLoader.__new__(RiskMetricsLoader)
    return loader


def test_implausible_momentum_return_nulled_not_crashed() -> None:
    loader = _make_loader()

    today = date(2026, 8, 18)
    # 253 rows (enough for all 4 periods). Every close is a normal $20 except the exact
    # anchor day 1m momentum looks back to (21 trading days back), which is an implausibly
    # tiny fraction of a cent - produces a >=10,000% raw return for momentum_1m only, while
    # 3m/6m/12m (unaffected anchors) stay real, computable values.
    # 3-tuple (date, close, adj_close) matching _compute_momentum_row's SELECT date, close,
    # adj_close (2026-09-01 adj_close fix) - adj_close equals close here, no split to adjust for.
    rows = [(today - timedelta(days=i), 20.0, 20.0) for i in range(253)]
    rows[21] = (rows[21][0], 0.0001, 0.0001)  # 1m's price_old anchor: implausibly tiny

    with patch("loaders.load_risk_metrics_daily.DatabaseContext") as mock_ctx:
        cur = MagicMock()
        cur.fetchall.return_value = rows
        cur.fetchone.return_value = None  # technical_data_daily lookup: no row found
        mock_ctx.return_value.__enter__.return_value = cur

        row = loader._compute_momentum_row("DFNS")

    assert row["data_unavailable"] is False  # the write is NOT dropped
    assert row["momentum_1m"] is None  # implausible period nulled, not crashed
    assert row["momentum_3m"] == 0.0  # unaffected periods still computed normally
    assert row["momentum_6m"] == 0.0
    assert row["momentum_12m"] == 0.0


def test_overflow_nulled_period_records_reason_not_silent() -> None:
    """FIX 2026-08-28: momentum_metrics has only one row-level reason/reason_type pair
    (unlike stability_metrics's per-field *_unavailable_reason columns) - it stayed None on
    this success path even when a period was nulled by the overflow guard, an instance of the
    same "NULL with no reason recorded" bug class already fixed for growth_metrics/
    quality_metrics/value_metrics. Live-confirmed real case: AKTS has 2,197 days of price
    history yet momentum_12m was NULL with reason NULL - its 12mo-ago close was an unadjusted
    reverse-split artifact ($0.0372 vs today's $25.78), not a data gap.
    """
    loader = _make_loader()

    today = date(2026, 8, 18)
    # 3-tuple (date, close, adj_close) matching _compute_momentum_row's SELECT date, close,
    # adj_close (2026-09-01 adj_close fix) - adj_close equals close here, no split to adjust for.
    rows = [(today - timedelta(days=i), 20.0, 20.0) for i in range(253)]
    rows[21] = (rows[21][0], 0.0001, 0.0001)  # 1m's price_old anchor: implausibly tiny

    with patch("loaders.load_risk_metrics_daily.DatabaseContext") as mock_ctx:
        cur = MagicMock()
        cur.fetchall.return_value = rows
        cur.fetchone.return_value = None
        mock_ctx.return_value.__enter__.return_value = cur

        row = loader._compute_momentum_row("DFNS")

    assert row["reason_type"] == "partial_momentum_nulls"
    assert "momentum_1m" in row["reason"]
    assert "extreme_return_overflow" in row["reason"]


def test_insufficient_history_period_records_reason_not_silent() -> None:
    """Same bug class, the other cause: a period nulled because there isn't enough price
    history yet (target_idx < 0, e.g. a recent IPO) should also get a reason, not a silent
    NULL - distinguishing "not enough history yet" from "overflow guard fired" matters for
    anyone auditing why a symbol's momentum_12m is empty."""
    loader = _make_loader()

    today = date(2026, 8, 18)
    rows = [(today - timedelta(days=i), 20.0, 20.0) for i in range(100)]  # only 100 days: no 6m/12m

    with patch("loaders.load_risk_metrics_daily.DatabaseContext") as mock_ctx:
        cur = MagicMock()
        cur.fetchall.return_value = rows
        cur.fetchone.return_value = None
        mock_ctx.return_value.__enter__.return_value = cur

        row = loader._compute_momentum_row("NEWCO")

    assert row["momentum_12m"] is None
    assert row["reason_type"] == "partial_momentum_nulls"
    assert "momentum_12m:insufficient_price_history" in row["reason"]
    assert "momentum_6m:insufficient_price_history" in row["reason"]
