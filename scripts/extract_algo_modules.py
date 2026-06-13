#!/usr/bin/env python3
"""Extract functions from algo_original.py and distribute to modular files."""

import re
from pathlib import Path

# Define mapping of functions to modules
FUNCTION_MAPPING = {
    'dashboard': [
        '_get_last_run', '_get_algo_status', '_get_algo_trades', '_get_algo_positions',
        '_get_algo_performance', '_get_circuit_breakers', '_get_equity_curve', '_get_data_status',
        '_get_dashboard_signals'
    ],
    'notifications': ['_get_notifications'],
    'analysis': [
        '_get_swing_scores', '_get_swing_scores_history', '_get_rejection_funnel',
        '_get_sector_rotation', '_get_sector_breadth', '_get_sector_position_warnings',
        '_analyze_pre_trade_impact', '_get_sector_stage2', '_get_rejection_reason_description'
    ],
    'admin': ['_trigger_data_patrol', '_get_patrol_log', '_get_algo_audit_log'],
    'config': [
        '_get_algo_config', '_get_algo_config_key', '_update_algo_config_key',
        '_reset_algo_config_key', '_categorize_config_key'
    ],
    'metrics': ['_get_algo_portfolio', '_get_algo_metrics', '_get_risk_metrics', '_get_performance_analytics'],
    'market': ['_get_markets', '_get_market', '_get_market_factors', '_TIER_CONFIG'],
    'orchestrator': [
        '_get_orchestrator_execution_recent', '_get_orchestrator_execution_failed',
        '_get_orchestrator_execution_details', '_get_orchestrator_execution_patterns',
        '_get_orchestrator_execution_stats'
    ],
    'external': [
        '_get_sentiment', '_get_economic_calendar', '_get_algo_evaluate',
        '_get_data_quality', '_get_exposure_policy'
    ]
}

# Handler function mapping (what gets exported)
HANDLER_MAPPING = {
    'dashboard': {
        'handle_last_run': '_get_last_run',
        'handle_status': '_get_algo_status',
        'handle_trades': '_get_algo_trades',
        'handle_positions': '_get_algo_positions',
        'handle_performance': '_get_algo_performance',
        'handle_circuit_breakers': '_get_circuit_breakers',
        'handle_equity_curve': '_get_equity_curve',
        'handle_data_status': '_get_data_status',
        'handle_dashboard_signals': '_get_dashboard_signals',
    },
    'notifications': {
        'handle_get_notifications': '_get_notifications',
        'handle_mark_read': 'notification_mark_read_handler',
        'handle_delete': 'notification_delete_handler',
    },
    'analysis': {
        'handle_swing_scores': '_get_swing_scores',
        'handle_swing_scores_history': '_get_swing_scores_history',
        'handle_rejection_funnel': '_get_rejection_funnel',
        'handle_sector_rotation': '_get_sector_rotation',
        'handle_sector_breadth': '_get_sector_breadth',
        'handle_sector_position_warnings': '_get_sector_position_warnings',
        'handle_pre_trade_impact': '_analyze_pre_trade_impact',
        'handle_sector_stage2': '_get_sector_stage2',
    },
    'admin': {
        'handle_trigger_patrol': '_trigger_data_patrol',
        'handle_patrol_log': '_get_patrol_log',
        'handle_audit_log': '_get_algo_audit_log',
    },
    'config': {
        'handle_get_config': '_get_algo_config',
        'handle_config_key': 'config_key_handler',
    },
    'metrics': {
        'handle_portfolio': '_get_algo_portfolio',
        'handle_metrics': '_get_algo_metrics',
        'handle_risk_metrics': '_get_risk_metrics',
        'handle_performance_analytics': '_get_performance_analytics',
    },
    'market': {
        'handle_markets': '_get_markets',
        'handle_market': '_get_market',
        'handle_market_factors': '_get_market_factors',
    },
    'orchestrator': {
        'handle_execution_recent': '_get_orchestrator_execution_recent',
        'handle_execution_failed': '_get_orchestrator_execution_failed',
        'handle_execution_details': '_get_orchestrator_execution_details',
        'handle_execution_patterns': '_get_orchestrator_execution_patterns',
        'handle_execution_stats': '_get_orchestrator_execution_stats',
    },
    'external': {
        'handle_sentiment': '_get_sentiment',
        'handle_economic_calendar': '_get_economic_calendar',
        'handle_evaluate': '_get_algo_evaluate',
        'handle_data_quality': '_get_data_quality',
        'handle_exposure_policy': '_get_exposure_policy',
    }
}

print("Extraction mapping created:")
for module, funcs in FUNCTION_MAPPING.items():
    print(f"  {module:15s}: {len(funcs):2d} items to extract")
print(f"\nTotal items to extract: {sum(len(v) for v in FUNCTION_MAPPING.values())}")
