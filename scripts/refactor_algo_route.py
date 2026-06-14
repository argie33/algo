#!/usr/bin/env python3
"""
Refactor algo.py into modular subpackage.
This script extracts functions from the monolithic algo.py and organizes them
into domain-specific modules.
"""

import re
from pathlib import Path

# Define function mappings to modules
FUNCTION_MODULES = {
    'dashboard': [
        '_get_last_run', '_get_algo_status', '_get_algo_trades', '_get_algo_positions',
        '_get_algo_performance', '_get_circuit_breakers', '_get_equity_curve', '_get_data_status',
        '_get_dashboard_signals'
    ],
    'notifications': [
        '_get_notifications'
    ],
    'analysis': [
        '_get_swing_scores', '_get_swing_scores_history', '_get_rejection_funnel',
        '_get_sector_rotation', '_get_sector_breadth', '_get_sector_position_warnings',
        '_analyze_pre_trade_impact', '_get_sector_stage2', '_get_rejection_reason_description'
    ],
    'admin': [
        '_trigger_data_patrol', '_get_patrol_log', '_get_algo_audit_log'
    ],
    'config': [
        '_get_algo_config', '_get_algo_config_key', '_update_algo_config_key',
        '_reset_algo_config_key', '_categorize_config_key'
    ],
    'metrics': [
        '_get_algo_portfolio', '_get_algo_metrics', '_get_risk_metrics', '_get_performance_analytics'
    ],
    'market': [
        '_get_markets', '_get_market', '_get_market_factors'
    ],
    'orchestrator': [
        '_get_orchestrator_execution_recent', '_get_orchestrator_execution_failed',
        '_get_orchestrator_execution_details', '_get_orchestrator_execution_patterns',
        '_get_orchestrator_execution_stats'
    ],
    'external': [
        '_get_sentiment', '_get_economic_calendar', '_get_algo_evaluate', '_get_data_quality',
        '_get_exposure_policy'
    ]
}

# Constants that need to be extracted
TIER_CONFIG = '_TIER_CONFIG'

print("[OK] Refactoring plan created")
print(f"  - {len(FUNCTION_MODULES)} modules to create")
print(f"  - {sum(len(funcs) for funcs in FUNCTION_MODULES.values())} functions to extract")
print("\nModule breakdown:")
for module, funcs in FUNCTION_MODULES.items():
    print(f"  - {module}.py: {len(funcs)} functions")
