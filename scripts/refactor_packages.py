#!/usr/bin/env python3
"""
Comprehensive package reorganization script.
Reorganizes algo/ and utils/ into submodules with proper __init__.py files.
"""

import shutil
from pathlib import Path

# File mappings: (old_path, new_path, submodule)
ALGO_FILES_TO_MOVE = [
    # signals
    ("algo/algo_signals.py", "algo/signals/core.py", "signals"),
    ("algo/algo_signals_vectorized.py", "algo/signals/vectorized.py", "signals"),
    ("algo/algo_swing_score.py", "algo/signals/swing_score.py", "signals"),
    ("algo/algo_advanced_filters.py", "algo/signals/advanced_filters.py", "signals"),
    ("algo/algo_trendline_support.py", "algo/signals/trendline.py", "signals"),
    ("algo/algo_signal_attribution.py", "algo/signals/attribution.py", "signals"),
    (
        "algo/algo_signal_trade_performance.py",
        "algo/signals/trade_performance.py",
        "signals",
    ),
    ("algo/algo_sector_rotation.py", "algo/signals/sector_rotation.py", "signals"),
    # risk
    ("algo/algo_var.py", "algo/risk/var.py", "risk"),
    ("algo/algo_circuit_breaker.py", "algo/risk/circuit_breaker.py", "risk"),
    ("algo/algo_position_sizer.py", "algo/risk/position_sizer.py", "risk"),
    ("algo/algo_market_exposure.py", "algo/risk/market_exposure.py", "risk"),
    ("algo/algo_market_exposure_policy.py", "algo/risk/exposure_policy.py", "risk"),
    ("algo/algo_liquidity_checks.py", "algo/risk/liquidity_checks.py", "risk"),
    ("algo/algo_earnings_blackout.py", "algo/risk/earnings_blackout.py", "risk"),
    # trading
    ("algo/algo_trade_executor.py", "algo/trading/executor.py", "trading"),
    ("algo/algo_exit_engine.py", "algo/trading/exit_engine.py", "trading"),
    ("algo/algo_pyramid.py", "algo/trading/pyramid.py", "trading"),
    ("algo/algo_pretrade_checks.py", "algo/trading/pretrade_checks.py", "trading"),
    ("algo/algo_tca.py", "algo/trading/tca.py", "trading"),
    # monitoring
    (
        "algo/algo_position_monitor.py",
        "algo/monitoring/position_monitor.py",
        "monitoring",
    ),
    (
        "algo/algo_pipeline_health.py",
        "algo/monitoring/pipeline_health.py",
        "monitoring",
    ),
    (
        "algo/algo_connection_monitor.py",
        "algo/monitoring/connection_monitor.py",
        "monitoring",
    ),
    ("algo/algo_data_patrol.py", "algo/monitoring/data_patrol.py", "monitoring"),
    # reporting
    ("algo/algo_alerts.py", "algo/reporting/alerts.py", "reporting"),
    ("algo/algo_notifications.py", "algo/reporting/notifications.py", "reporting"),
    ("algo/algo_metrics.py", "algo/reporting/metrics.py", "reporting"),
    ("algo/algo_performance.py", "algo/reporting/performance.py", "reporting"),
    ("algo/algo_daily_report.py", "algo/reporting/daily_report.py", "reporting"),
    # orchestration
    (
        "algo/algo_orchestrator.py",
        "algo/orchestration/orchestrator.py",
        "orchestration",
    ),
    (
        "algo/algo_regime_manager.py",
        "algo/orchestration/regime_manager.py",
        "orchestration",
    ),
    (
        "algo/algo_weight_optimizer.py",
        "algo/orchestration/weight_optimizer.py",
        "orchestration",
    ),
    # infrastructure
    ("algo/algo_config.py", "algo/infrastructure/config.py", "infrastructure"),
    (
        "algo/algo_trade_audit_logger.py",
        "algo/infrastructure/audit_logger.py",
        "infrastructure",
    ),
    (
        "algo/algo_daily_reconciliation.py",
        "algo/infrastructure/reconciliation.py",
        "infrastructure",
    ),
    (
        "algo/algo_market_calendar.py",
        "algo/infrastructure/market_calendar.py",
        "infrastructure",
    ),
    (
        "algo/algo_market_events.py",
        "algo/infrastructure/market_events.py",
        "infrastructure",
    ),
    (
        "algo/algo_realtime_prices.py",
        "algo/infrastructure/realtime_prices.py",
        "infrastructure",
    ),
]

UTILS_FILES_TO_MOVE = [
    # db
    ("utils/db_connection.py", "utils/db/connection.py", "db"),
    ("utils/database_context.py", "utils/db/context.py", "db"),
    ("utils/db_retry_helper.py", "utils/db/retry.py", "db"),
    ("utils/dynamodb_lock_manager.py", "utils/db/dynamo_lock.py", "db"),
    ("utils/dynamodb_health_check.py", "utils/db/dynamo_health.py", "db"),
    ("utils/rds_pool_monitor.py", "utils/db/pool_monitor.py", "db"),
    ("utils/query_cache.py", "utils/db/query_cache.py", "db"),
    # logging
    ("utils/structured_logger.py", "utils/logging/logger.py", "logging"),
    ("utils/monitoring_context.py", "utils/logging/monitoring.py", "logging"),
    ("utils/sla_monitor.py", "utils/logging/sla.py", "logging"),
    ("utils/loader_failure_tracker.py", "utils/logging/loader_failure.py", "logging"),
    (
        "utils/orchestrator_execution_tracker.py",
        "utils/logging/execution_tracker.py",
        "logging",
    ),
    ("utils/loader_history_tracker.py", "utils/logging/history_tracker.py", "logging"),
    # validation
    ("utils/validation_framework.py", "utils/validation/framework.py", "validation"),
    (
        "utils/validation_integration.py",
        "utils/validation/integration.py",
        "validation",
    ),
    ("utils/data_validation_registry.py", "utils/validation/registry.py", "validation"),
    ("utils/domain_validators.py", "utils/validation/domain.py", "validation"),
    ("utils/freshness_validator.py", "utils/validation/freshness.py", "validation"),
    (
        "utils/data_freshness_config.py",
        "utils/validation/freshness_config.py",
        "validation",
    ),
    ("utils/schema_validator.py", "utils/validation/schema.py", "validation"),
    (
        "utils/financial_data_validator.py",
        "utils/validation/financial.py",
        "validation",
    ),
    ("utils/alpaca_response_validator.py", "utils/validation/alpaca.py", "validation"),
    ("utils/rate_limit_validator.py", "utils/validation/rate_limit.py", "validation"),
    ("utils/parallelism_validator.py", "utils/validation/parallelism.py", "validation"),
    (
        "utils/aws_production_config_validator.py",
        "utils/validation/aws_config.py",
        "validation",
    ),
    # data
    ("utils/data_ops.py", "utils/data/ops.py", "data"),
    ("utils/data_tick_validator.py", "utils/data/tick_validator.py", "data"),
    ("utils/data_watermark_manager.py", "utils/data/watermark.py", "data"),
    ("utils/data_provenance_tracker.py", "utils/data/provenance.py", "data"),
    ("utils/data_source_router.py", "utils/data/source_router.py", "data"),
    # signals
    ("utils/signal_scorer.py", "utils/signals/scorer.py", "signals"),
    ("utils/signal_query_builder.py", "utils/signals/query_builder.py", "signals"),
    ("utils/grade_classifier.py", "utils/signals/grade_classifier.py", "signals"),
    ("utils/metrics_calculator.py", "utils/signals/metrics.py", "signals"),
    ("utils/algo_metrics_fetcher.py", "utils/signals/metrics_fetcher.py", "signals"),
    # trading
    ("utils/trade_status.py", "utils/trading/status.py", "trading"),
    ("utils/trade_recorder.py", "utils/trading/recorder.py", "trading"),
    (
        "utils/filter_rejection_tracker.py",
        "utils/trading/rejection_tracker.py",
        "trading",
    ),
    ("utils/admin_rate_limiter.py", "utils/trading/rate_limiter.py", "trading"),
    # loaders
    ("utils/optimal_loader.py", "utils/loaders/base.py", "loaders"),
    ("utils/loader_config.py", "utils/loaders/config.py", "loaders"),
    ("utils/loader_helpers.py", "utils/loaders/helpers.py", "loaders"),
    (
        "utils/loader_conflict_detector.py",
        "utils/loaders/conflict_detector.py",
        "loaders",
    ),
    # external
    ("utils/sec_edgar_client.py", "utils/external/sec_edgar.py", "external"),
    ("utils/yfinance_wrapper.py", "utils/external/yfinance.py", "external"),
    # infrastructure
    (
        "utils/safe_data_conversion.py",
        "utils/infrastructure/conversion.py",
        "infrastructure",
    ),
    ("utils/timezone_utils.py", "utils/infrastructure/timezone.py", "infrastructure"),
    (
        "utils/url_validator.py",
        "utils/infrastructure/url_validator.py",
        "infrastructure",
    ),
    (
        "utils/csv_sanitizer.py",
        "utils/infrastructure/csv_sanitizer.py",
        "infrastructure",
    ),
    ("utils/execution_timeout.py", "utils/infrastructure/timeout.py", "infrastructure"),
    (
        "utils/correlation_context.py",
        "utils/infrastructure/correlation.py",
        "infrastructure",
    ),
    (
        "utils/market_timing_constants.py",
        "utils/infrastructure/market_timing.py",
        "infrastructure",
    ),
    (
        "utils/feature_flags.py",
        "utils/infrastructure/feature_flags.py",
        "infrastructure",
    ),
    (
        "utils/fallback_registry.py",
        "utils/infrastructure/fallback_registry.py",
        "infrastructure",
    ),
    (
        "utils/api_endpoints.py",
        "utils/infrastructure/api_endpoints.py",
        "infrastructure",
    ),
    # ops
    ("utils/production_readiness_check.py", "utils/ops/production_readiness.py", "ops"),
    ("utils/position_sync_checker.py", "utils/ops/position_sync.py", "ops"),
    ("utils/orchestrator_query.py", "utils/ops/orchestrator_query.py", "ops"),
]

def main():
    repo_root = Path(".")

    print("[*] Creating directories...")
    for _, new_path, _ in ALGO_FILES_TO_MOVE + UTILS_FILES_TO_MOVE:
        new_dir = repo_root / new_path.rsplit("/", 1)[0]
        new_dir.mkdir(parents=True, exist_ok=True)
        print(f"    Created {new_dir}")

    print("[*] Moving files...")
    for old_path, new_path, _ in ALGO_FILES_TO_MOVE + UTILS_FILES_TO_MOVE:
        old_file = repo_root / old_path
        new_file = repo_root / new_path
        if old_file.exists():
            shutil.move(str(old_file), str(new_file))
            print(f"    Moved {old_path} -> {new_path}")
        else:
            print(f"    [SKIP] {old_path} does not exist")

    print("[*] Done!")

if __name__ == "__main__":
    main()
