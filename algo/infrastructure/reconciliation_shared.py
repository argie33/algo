#!/usr/bin/env python3
"""Small shared helper used by both the broker-connected and paper-mode reconciliation
paths in algo/infrastructure/reconciliation.py, reconciliation_broker_snapshot.py, and
reconciliation_paper_mode.py.

Split out of reconciliation.py (where it was a module-level function, `_compute_adjusted_drawdown`)
purely so both mixin files can import it without creating an import cycle back into
reconciliation.py itself. reconciliation.py re-exports it as `_compute_adjusted_drawdown` for
backward compatibility (tests/unit/test_capital_flow_adjusted_drawdown.py imports it by that
name from that module). No behavior change - verbatim relocation.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

PORTFOLIO_SNAPSHOT_LOCK_ID = 2147483647


def compute_adjusted_drawdown(cur: Any, reconcile_date: Any, portfolio_value: float) -> tuple[float, float, float]:
    """Cash-flow-adjusted peak/drawdown inputs (migration 1134).

    Raw total_portfolio_value moves for two different reasons: trading performance AND
    external capital flows (deposits/withdrawals). A withdrawal looks identical to a trading
    loss in the raw series - conflating the two produced a false 32.6% "drawdown" that halted
    every orchestrator run for 8+ months (see algo_capital_flows for the incident). Every
    capital flow must be recorded there (scripts/record_capital_flow.py) or it will
    misreport here exactly the same way.

    Returns (net_capital_flow_cum, adjusted_running_peak, adjusted_drawdown_pct).
    """
    cur.execute(
        "SELECT COUNT(*) as flow_count, SUM(amount) as total_amount FROM algo_capital_flows WHERE flow_date <= %s",
        (reconcile_date,),
    )
    flow_row = cur.fetchone()
    if flow_row is None or len(flow_row) < 2:
        raise RuntimeError(
            "[RECONCILIATION] Capital flow query returned invalid result: expected 2 columns, got 0 or None"
        )

    flow_count = flow_row[0]
    sum_amount = flow_row[1]

    # Distinguish between "no records" (legitimate 0) and "records but aggregation failed" (error)
    if flow_count == 0:
        net_capital_flow_cum = 0.0
        logger.debug("[RECONCILIATION] No capital flows recorded on or before reconcile_date (net flow = 0)")
    elif sum_amount is None:
        raise RuntimeError(
            "[RECONCILIATION CRITICAL] Capital flows exist but SUM(amount) returned NULL. "
            f"Found {flow_count} flow records but aggregation failed. "
            "This indicates data corruption or a database query error. "
            "Check algo_capital_flows table for invalid amount values (NaN/NULL/type issues)."
        )
    else:
        net_capital_flow_cum = float(sum_amount)

    adjusted_equity = portfolio_value - net_capital_flow_cum

    cur.execute(
        """
        SELECT MAX(adjusted_equity) FROM algo_portfolio_snapshots WHERE snapshot_date <= %s
        """,
        (reconcile_date,),
    )
    peak_row = cur.fetchone()
    if peak_row is None or len(peak_row) < 1:
        raise RuntimeError(
            "[RECONCILIATION] Peak equity query returned invalid result: expected 1 column, got 0 or None"
        )
    prior_peak_val = peak_row[0]
    adjusted_running_peak = (
        max(float(prior_peak_val), adjusted_equity) if prior_peak_val is not None else adjusted_equity
    )

    adjusted_drawdown_pct = 0.0
    if adjusted_running_peak > 0:
        adjusted_drawdown_pct = ((adjusted_running_peak - adjusted_equity) / adjusted_running_peak) * 100

    return net_capital_flow_cum, adjusted_running_peak, adjusted_drawdown_pct
