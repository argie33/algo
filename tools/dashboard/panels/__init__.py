"""Modular panel rendering functions for dashboard display.

All panels self-register with the panel registry via @register_panel decorator
to enable dynamic discovery and extensibility.
"""

# Import all panel functions from modular subpackages
from .market import (
    panel_market_full,
    panel_market_expanded,
    panel_header_market,
)

from .circuit import (
    panel_circuit,
    panel_circuit_expanded,
)

from .health import (
    panel_orch,
    panel_status,
    panel_algo_health,
    panel_algo_health_expanded,
)

from .trades import (
    panel_recent_trades,
    panel_trades_expanded,
    _extract_items,
)

from .signals import (
    panel_signals_compact,
    panel_signals_expanded,
)

from .sectors import (
    panel_sector_compact,
    panel_sectors_expanded,
    _rdelta,
)

from .economic import (
    panel_economic_pulse,
    panel_economic_expanded,
)

from .exposure import (
    panel_exposure_compact,
    panel_exposure_expanded,
)

from .portfolio import (
    panel_portfolio,
    panel_performance_spark,
    panel_portfolio_perf_expanded,
    _calculate_adjusted_win_rate,
)

from .positions import (
    panel_positions,
)

from .mascot import (
    mascot_pose,
    mascot_compact,
    loading_layout,
    _expanded_layout,
)

# Re-export helper functions that may be used elsewhere
from ._helpers import (
    _score_cell,
    _build_buy_sig_map,
    _swing_cell,
    _composite_score_color,
    _best_halt_reason,
    _fmt_phases_halted,
    _error_panel,
)


__all__ = [
    # Market panels
    "panel_market_full",
    "panel_market_expanded",
    "panel_header_market",
    # Circuit breaker panels
    "panel_circuit",
    "panel_circuit_expanded",
    # Health and orchestration panels
    "panel_orch",
    "panel_status",
    "panel_algo_health",
    "panel_algo_health_expanded",
    # Trade panels
    "panel_recent_trades",
    "panel_trades_expanded",
    # Signal panels
    "panel_signals_compact",
    "panel_signals_expanded",
    # Sector panels
    "panel_sector_compact",
    "panel_sectors_expanded",
    # Economic panels
    "panel_economic_pulse",
    "panel_economic_expanded",
    # Exposure panels
    "panel_exposure_compact",
    "panel_exposure_expanded",
    # Portfolio panels
    "panel_portfolio",
    "panel_performance_spark",
    "panel_portfolio_perf_expanded",
    # Position panels
    "panel_positions",
    # Mascot and layout panels
    "mascot_pose",
    "mascot_compact",
    "loading_layout",
    "_expanded_layout",
    # Helper functions
    "_score_cell",
    "_build_buy_sig_map",
    "_swing_cell",
    "_composite_score_color",
    "_best_halt_reason",
    "_fmt_phases_halted",
    "_error_panel",
    "_extract_items",
    "_rdelta",
    "_calculate_adjusted_win_rate",
]
