#!/usr/bin/env python3
"""Algo Ops Terminal Dashboard (AWS)  --  connects to RDS via AWS Secrets Manager.

Usage:
  python tools/dashboard/dashboard.py            # live view (q or Ctrl+C to exit)
  python tools/dashboard/dashboard.py -w         # watch mode, auto-refresh every 30s
  python tools/dashboard/dashboard.py -w 60      # watch mode, refresh every 60s
  python tools/dashboard/dashboard.py --compact  # narrow positions table

Requires: AWS credentials (AWS_PROFILE env var), reads DB creds from AWS Secrets Manager.
For local development, use: python tools/dashboard/dashboard-dev.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# Re-export everything from modules for backward compatibility
from utilities import (
    ET, CONSOLE, logger,
    G, R, Y, CY, DIM, MG, WH,
    TIER_COLOR, TIER_SHORT, SPARKLINE_CHARS, PHASE_NAMES,
    MASCOT_W, MASCOT_FRAMES, MASCOT_COLORS, LOAD_SEQ,
    api_call, normalize_positions_data, compute_sector_agg, extract_items_and_error,
)

from fetchers import (
    fetch_run, fetch_algo_config, fetch_market, fetch_exposure_factors,
    fetch_portfolio, fetch_perf, fetch_positions, fetch_recent_trades,
    fetch_signals, fetch_sector_ranking, fetch_activity,
    fetch_health, fetch_economic_pulse, fetch_algo_metrics,
    fetch_notifications, fetch_sentiment, fetch_economic_calendar,
    fetch_risk_metrics, fetch_perf_analytics, fetch_signal_eval,
    fetch_sector_rotation, fetch_industry_ranking, fetch_loader_status,
    fetch_exec_history, fetch_audit_log, fetch_circuit,
    _get_data_status_cached, FETCHERS, load_all,
)

from formatters import (
    fmt_age, fmt_money, fmt_money_short, grade, tier_from_pct,
    is_open, mkt_hours_str, next_run_str,
    hbar, exp_bar, mini_bar, sign, sparkline,
)

from panels import (
    mascot_pose, _best_halt_reason, _fmt_phases_halted, _error_panel,
    _extract_items, panel_orch, panel_market_full, panel_circuit,
    panel_header_market, panel_portfolio, panel_performance_spark,
    panel_positions, panel_signals_compact, panel_recent_trades,
    _rdelta, panel_sector_compact, panel_economic_pulse,
    panel_exposure_compact, panel_status, panel_algo_health,
    mascot_compact, loading_layout, _expanded_layout,
    panel_signals_expanded, panel_algo_health_expanded,
    panel_sectors_expanded,
)

from main import (
    render_dashboard, run_once, run_watch, print_legend, main,
)

if __name__ == "__main__":
    main()
