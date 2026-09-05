"""Panel: health

2026-09-05: wired to the health_*.py split (drafted 2026-09-05, orphaned uncommitted until
now, same pattern as lambda/api/routes/scores.py's scores_handlers/ wiring - see MEMORY.md
concurrent_session_scores_handlers_split_import_breakage_reconciled_20260905 note). This file
is now just a thin re-export surface; the actual panel/formatting logic lives in
dashboard/panels/health_*.py. Verified every one of the 67 top-level functions/classes
byte-for-byte against the prior monolith before wiring (57 identical, 9 differed only by an
added `# noqa: C901` comment, 1 - _format_execution_stats - had two genuinely-unused local
variables dropped in the split, confirmed dead via grep before accepting the diff). Names
below are re-exported (not just used internally) because dashboard/panels/__init__.py and
several tests still import them as `dashboard.panels.health.<name>` / `from
dashboard.panels.health import <name>` - removing any of these re-exports breaks those
call sites even though this file no longer defines them. Every re-exported name is listed in
__all__ below - without that, ruff's unused-import auto-fix strips them as dead imports the
next time any hook touches this file (confirmed live: happened once already mid-commit).
"""

from __future__ import annotations

from .health_algo import _format_run_history_summary, panel_algo_health, panel_algo_health_expanded
from .health_algo_phases import (
    _build_phase_badges_and_metrics,
    _build_phase_badges_from_audit,
    _build_phase_execution_panel,
)
from .health_freshness import panel_data_freshness, panel_data_freshness_expanded
from .health_freshness_panel import _build_freshness_panel
from .health_freshness_sections import _build_loader_health_section, _format_health_data_fresh_section
from .health_orch import panel_orch
from .health_results import _build_run_history_section
from .health_results_panel import _build_results_panel
from .health_shared import (
    ERROR_STATES,
    HALTED_STATES,
    NOTIF_SHORT_NAMES,
    PHASE_HALTED_STATES,
    SUCCESS_STATES,
    HealthFormatter,
    _format_phase_badge,
)
from .health_status import (
    _format_data_health_summary,
    _format_exec_history_summary,
    _format_loader_status,
    _format_recent_trade_events,
)
from .health_status_panel import (
    _format_audit_log_summary,
    _format_daily_metrics_summary,
    _format_notifications_summary,
    panel_status,
)

__all__ = [
    "ERROR_STATES",
    "HALTED_STATES",
    "NOTIF_SHORT_NAMES",
    "PHASE_HALTED_STATES",
    "SUCCESS_STATES",
    "HealthFormatter",
    "_build_freshness_panel",
    "_build_loader_health_section",
    "_build_phase_badges_and_metrics",
    "_build_phase_badges_from_audit",
    "_build_phase_execution_panel",
    "_build_results_panel",
    "_build_run_history_section",
    "_format_audit_log_summary",
    "_format_daily_metrics_summary",
    "_format_data_health_summary",
    "_format_exec_history_summary",
    "_format_health_data_fresh_section",
    "_format_loader_status",
    "_format_notifications_summary",
    "_format_phase_badge",
    "_format_recent_trade_events",
    "_format_run_history_summary",
    "panel_algo_health",
    "panel_algo_health_expanded",
    "panel_data_freshness",
    "panel_data_freshness_expanded",
    "panel_orch",
    "panel_status",
]
