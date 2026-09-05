"""Algo dashboard route handlers - one module per handler function.

Split 2026-09-05 (file-size-ratchet compliance split of the original 2160-line
algo_handlers/dashboard.py - see loaders/stock_scores/ and lambda/api/routes/scores_handlers/
for the established precedent this follows). Each of the 7 handlers that used to live in one
flat module now lives in its own sibling module (positions.py, status.py, trades.py,
circuit_breakers.py, signals.py, scores.py, equity_curve.py); this file re-exports all 7 names
so existing callers - notably routes/algo.py's
`from .algo_handlers.dashboard import (_get_algo_positions, ...)` - require zero changes.
Pure move, no logic changed anywhere; each function's body is byte-for-byte identical to the
pre-split version (only the import header at the top of each new module differs, trimmed to
that function's actual dependencies).
"""

from __future__ import annotations

from .circuit_breakers import _get_circuit_breakers
from .equity_curve import _get_equity_curve
from .positions import _get_algo_positions
from .scores import _get_dashboard_scores
from .signals import _get_dashboard_signals
from .status import _get_algo_status
from .trades import _get_algo_trades

__all__ = [
    "_get_algo_positions",
    "_get_algo_status",
    "_get_algo_trades",
    "_get_circuit_breakers",
    "_get_dashboard_scores",
    "_get_dashboard_signals",
    "_get_equity_curve",
]
