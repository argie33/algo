"""Modular panel rendering functions for dashboard display.

All panels self-register with the panel registry via @register_panel decorator
to enable dynamic discovery and extensibility.
"""

# Import all panel functions from modular subpackages
# Re-export helper functions that may be used elsewhere
from ._helpers import (
    _best_halt_reason,
    _composite_score_color,
    _error_panel,
    _fmt_phases_halted,
    _score_cell,
)
from .circuit import (
    panel_circuit,
    panel_circuit_expanded,
)
from .economic import (
    panel_economic_expanded,
    panel_economic_pulse,
)
from .exposure import (
    panel_exposure_compact,
    panel_exposure_expanded,
)
from .health import (
    panel_algo_health,
    panel_algo_health_expanded,
    panel_orch,
    panel_status,
)
from .market import (
    panel_header_market,
    panel_market_expanded,
    panel_market_full,
)
from .mascot import (
    _expanded_layout,
    loading_layout,
    mascot_compact,
    mascot_pose,
)
from .portfolio import (
    _calculate_adjusted_win_rate,
    panel_performance_spark,
    panel_portfolio,
    panel_portfolio_perf_expanded,
)
from .positions import (
    panel_positions,
)
from .sectors import (
    panel_sector_compact,
    panel_sectors_expanded,
)
from .signals import (
    panel_signals_compact,
    panel_signals_expanded,
)
from .trades import (
    _extract_items,
    panel_recent_trades,
    panel_trades_expanded,
)

__all__ = [
    "_best_halt_reason",
    "_calculate_adjusted_win_rate",
    "_composite_score_color",
    "_error_panel",
    "_expanded_layout",
    "_extract_items",
    "_fmt_phases_halted",
    # Helper functions
    "_score_cell",
    "loading_layout",
    "mascot_compact",
    # Mascot and layout panels
    "mascot_pose",
    "panel_algo_health",
    "panel_algo_health_expanded",
    # Circuit breaker panels
    "panel_circuit",
    "panel_circuit_expanded",
    "panel_economic_expanded",
    # Economic panels
    "panel_economic_pulse",
    # Exposure panels
    "panel_exposure_compact",
    "panel_exposure_expanded",
    "panel_header_market",
    "panel_market_expanded",
    # Market panels
    "panel_market_full",
    # Health and orchestration panels
    "panel_orch",
    "panel_performance_spark",
    # Portfolio panels
    "panel_portfolio",
    "panel_portfolio_perf_expanded",
    # Position panels
    "panel_positions",
    # Trade panels
    "panel_recent_trades",
    # Sector panels
    "panel_sector_compact",
    "panel_sectors_expanded",
    # Signal panels
    "panel_signals_compact",
    "panel_signals_expanded",
    "panel_status",
    "panel_trades_expanded",
]
