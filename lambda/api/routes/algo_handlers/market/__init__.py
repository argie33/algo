"""Algo market/health route handlers - re-exports for the former flat market.py.

Split 2026-09-05 (file-size-ratchet compliance split of the original ~1665-line
algo_handlers/market.py - see lambda/api/routes/algo_handlers/dashboard/__init__.py for the
established precedent this follows). The two big handlers that used to live in one flat
module now live in their own sibling modules: data_quality.py (`_get_data_quality`) and
data_status.py (`_get_data_status` plus its private support helpers - `_rollback_after_error`,
`_classify_loader_state_issue`, `_is_stale_by_trading_days`, `_daily_table_staleness_cutoffs`,
`_is_reaped_artifact`, `_reaped_recently`, `_row_needs_live_refresh`, and the
`ORCHESTRATOR_OWNED_TABLE_TS_COLUMNS`/`DAILY_TABLE_WEEKEND_GAP_ALLOWANCE`/
`REAPED_SELF_HEAL_GRACE` constants they use). The `PIPELINE_REMOVED_TABLES` module-level
constant moved to pipeline_tables.py. `_get_market`/`_get_market_factors`/
`_get_market_sentiment`/`_get_trend_criteria`/`_is_any_circuit_breaker_triggered`/
`_normalize_exposure`/`_normalize_market_health`/`_collect_phase2_circuit_breakers` were
already implemented in sibling modules market_health.py/market_scan.py and merely re-exported
by the old flat market.py - that re-export is preserved here unchanged.

This file re-exports every name so existing callers - notably routes/algo.py's
`from .algo_handlers.market import (_get_data_quality, _get_data_status, ...)` and
algo_handlers/monitoring.py's `from .market import PIPELINE_REMOVED_TABLES` - require zero
changes. Pure move, no logic changed anywhere; each function's body is byte-for-byte identical
to the pre-split version (only the import header at the top of each new module differs,
trimmed to that function's actual dependencies).
"""

from __future__ import annotations

from ..market_health import (
    _collect_phase2_circuit_breakers as _collect_phase2_circuit_breakers,
)
from ..market_health import (
    _get_market as _get_market,
)
from ..market_health import (
    _get_market_factors as _get_market_factors,
)
from ..market_health import (
    _get_market_sentiment as _get_market_sentiment,
)
from ..market_health import (
    _get_trend_criteria as _get_trend_criteria,
)
from ..market_health import (
    _is_any_circuit_breaker_triggered as _is_any_circuit_breaker_triggered,
)
from ..market_health import (
    _normalize_exposure as _normalize_exposure,
)
from ..market_health import (
    _normalize_market_health as _normalize_market_health,
)
from ..market_scan import _get_markets as _get_markets
from .data_quality import _get_data_quality
from .data_status import (
    DAILY_TABLE_WEEKEND_GAP_ALLOWANCE,
    ORCHESTRATOR_OWNED_TABLE_TS_COLUMNS,
    REAPED_SELF_HEAL_GRACE,
    _classify_loader_state_issue,
    _daily_table_staleness_cutoffs,
    _get_data_status,
    _is_reaped_artifact,
    _is_stale_by_trading_days,
    _reaped_recently,
    _rollback_after_error,
    _row_needs_live_refresh,
)
from .pipeline_tables import PIPELINE_REMOVED_TABLES

__all__ = [
    "DAILY_TABLE_WEEKEND_GAP_ALLOWANCE",
    "ORCHESTRATOR_OWNED_TABLE_TS_COLUMNS",
    "PIPELINE_REMOVED_TABLES",
    "REAPED_SELF_HEAL_GRACE",
    "_classify_loader_state_issue",
    "_collect_phase2_circuit_breakers",
    "_daily_table_staleness_cutoffs",
    "_get_data_quality",
    "_get_data_status",
    "_get_market",
    "_get_market_factors",
    "_get_market_sentiment",
    "_get_markets",
    "_get_trend_criteria",
    "_is_any_circuit_breaker_triggered",
    "_is_reaped_artifact",
    "_is_stale_by_trading_days",
    "_normalize_exposure",
    "_normalize_market_health",
    "_reaped_recently",
    "_rollback_after_error",
    "_row_needs_live_refresh",
]
