#!/usr/bin/env python3
"""
Full package reorganization: algo/ and utils/ into submodules.
This script handles the complete refactoring in one pass.
"""

import shutil
from pathlib import Path


def get_file_mapping():
    """Return (old_path, new_path) tuples for all files to move."""
    mapping = {
        # algo/ files
        "algo/algo_signals.py": "algo/signals/core.py",
        "algo/algo_signals_vectorized.py": "algo/signals/vectorized.py",
        "algo/algo_swing_score.py": "algo/signals/swing_score.py",
        "algo/algo_advanced_filters.py": "algo/signals/advanced_filters.py",
        "algo/algo_trendline_support.py": "algo/signals/trendline.py",
        "algo/algo_signal_attribution.py": "algo/signals/attribution.py",
        "algo/algo_signal_trade_performance.py": "algo/signals/trade_performance.py",
        "algo/algo_sector_rotation.py": "algo/signals/sector_rotation.py",
        "algo/algo_var.py": "algo/risk/var.py",
        "algo/algo_circuit_breaker.py": "algo/risk/circuit_breaker.py",
        "algo/algo_position_sizer.py": "algo/risk/position_sizer.py",
        "algo/algo_market_exposure.py": "algo/risk/market_exposure.py",
        "algo/algo_market_exposure_policy.py": "algo/risk/exposure_policy.py",
        "algo/algo_liquidity_checks.py": "algo/risk/liquidity_checks.py",
        "algo/algo_earnings_blackout.py": "algo/risk/earnings_blackout.py",
        "algo/algo_trade_executor.py": "algo/trading/executor.py",
        "algo/algo_exit_engine.py": "algo/trading/exit_engine.py",
        "algo/algo_pyramid.py": "algo/trading/pyramid.py",
        "algo/algo_pretrade_checks.py": "algo/trading/pretrade_checks.py",
        "algo/algo_tca.py": "algo/trading/tca.py",
        "algo/algo_position_monitor.py": "algo/monitoring/position_monitor.py",
        "algo/algo_pipeline_health.py": "algo/monitoring/pipeline_health.py",
        "algo/algo_connection_monitor.py": "algo/monitoring/connection_monitor.py",
        "algo/algo_data_patrol.py": "algo/monitoring/data_patrol.py",
        "algo/algo_alerts.py": "algo/reporting/alerts.py",
        "algo/algo_notifications.py": "algo/reporting/notifications.py",
        "algo/algo_metrics.py": "algo/reporting/metrics.py",
        "algo/algo_performance.py": "algo/reporting/performance.py",
        "algo/algo_daily_report.py": "algo/reporting/daily_report.py",
        "algo/algo_orchestrator.py": "algo/orchestration/orchestrator.py",
        "algo/algo_regime_manager.py": "algo/orchestration/regime_manager.py",
        "algo/algo_weight_optimizer.py": "algo/orchestration/weight_optimizer.py",
        "algo/algo_config.py": "algo/infrastructure/config.py",
        "algo/algo_trade_audit_logger.py": "algo/infrastructure/audit_logger.py",
        "algo/algo_daily_reconciliation.py": "algo/infrastructure/reconciliation.py",
        "algo/algo_market_calendar.py": "algo/infrastructure/market_calendar.py",
        "algo/algo_market_events.py": "algo/infrastructure/market_events.py",
        "algo/algo_realtime_prices.py": "algo/infrastructure/realtime_prices.py",
        "algo/algo_retry.py": "algo/infrastructure/retry.py",
        "algo/algo_sql_safety.py": "algo/infrastructure/sql_safety.py",
        # utils/ files
        "utils/db_connection.py": "utils/db/connection.py",
        "utils/database_context.py": "utils/db/context.py",
        "utils/db_retry_helper.py": "utils/db/retry.py",
        "utils/dynamodb_lock_manager.py": "utils/db/dynamo_lock.py",
        "utils/dynamodb_health_check.py": "utils/db/dynamo_health.py",
        "utils/rds_pool_monitor.py": "utils/db/pool_monitor.py",
        "utils/query_cache.py": "utils/db/query_cache.py",
        "utils/structured_logger.py": "utils/logging/logger.py",
        "utils/monitoring_context.py": "utils/logging/monitoring.py",
        "utils/sla_monitor.py": "utils/logging/sla.py",
        "utils/loader_failure_tracker.py": "utils/logging/loader_failure.py",
        "utils/orchestrator_execution_tracker.py": "utils/logging/execution_tracker.py",
        "utils/loader_history_tracker.py": "utils/logging/history_tracker.py",
        "utils/validation_framework.py": "utils/validation/framework.py",
        "utils/validation_integration.py": "utils/validation/integration.py",
        "utils/data_validation_registry.py": "utils/validation/registry.py",
        "utils/domain_validators.py": "utils/validation/domain.py",
        "utils/freshness_validator.py": "utils/validation/freshness.py",
        "utils/data_freshness_config.py": "utils/validation/freshness_config.py",
        "utils/schema_validator.py": "utils/validation/schema.py",
        "utils/financial_data_validator.py": "utils/validation/financial.py",
        "utils/alpaca_response_validator.py": "utils/validation/alpaca.py",
        "utils/rate_limit_validator.py": "utils/validation/rate_limit.py",
        "utils/parallelism_validator.py": "utils/validation/parallelism.py",
        "utils/aws_production_config_validator.py": "utils/validation/aws_config.py",
        "utils/data_ops.py": "utils/data/ops.py",
        "utils/data_tick_validator.py": "utils/data/tick_validator.py",
        "utils/data_watermark_manager.py": "utils/data/watermark.py",
        "utils/data_provenance_tracker.py": "utils/data/provenance.py",
        "utils/data_source_router.py": "utils/data/source_router.py",
        "utils/signal_scorer.py": "utils/signals/scorer.py",
        "utils/signal_query_builder.py": "utils/signals/query_builder.py",
        "utils/grade_classifier.py": "utils/signals/grade_classifier.py",
        "utils/metrics_calculator.py": "utils/signals/metrics.py",
        "utils/algo_metrics_fetcher.py": "utils/signals/metrics_fetcher.py",
        "utils/trade_status.py": "utils/trading/status.py",
        "utils/trade_recorder.py": "utils/trading/recorder.py",
        "utils/filter_rejection_tracker.py": "utils/trading/rejection_tracker.py",
        "utils/admin_rate_limiter.py": "utils/trading/rate_limiter.py",
        "utils/optimal_loader.py": "utils/loaders/base.py",
        "utils/loader_config.py": "utils/loaders/config.py",
        "utils/loader_helpers.py": "utils/loaders/helpers.py",
        "utils/loader_conflict_detector.py": "utils/loaders/conflict_detector.py",
        "utils/sec_edgar_client.py": "utils/external/sec_edgar.py",
        "utils/yfinance_wrapper.py": "utils/external/yfinance.py",
        "utils/safe_data_conversion.py": "utils/infrastructure/conversion.py",
        "utils/timezone_utils.py": "utils/infrastructure/timezone.py",
        "utils/url_validator.py": "utils/infrastructure/url_validator.py",
        "utils/csv_sanitizer.py": "utils/infrastructure/csv_sanitizer.py",
        "utils/execution_timeout.py": "utils/infrastructure/timeout.py",
        "utils/correlation_context.py": "utils/infrastructure/correlation.py",
        "utils/market_timing_constants.py": "utils/infrastructure/market_timing.py",
        "utils/feature_flags.py": "utils/infrastructure/feature_flags.py",
        "utils/fallback_registry.py": "utils/infrastructure/fallback_registry.py",
        "utils/api_endpoints.py": "utils/infrastructure/api_endpoints.py",
        "utils/production_readiness_check.py": "utils/ops/production_readiness.py",
        "utils/position_sync_checker.py": "utils/ops/position_sync.py",
        "utils/orchestrator_query.py": "utils/ops/orchestrator_query.py",
    }
    return mapping


def move_files(mapping):
    """Move all files to new locations."""
    for old_path, new_path in mapping.items():
        old = Path(old_path)
        new = Path(new_path)
        if old.exists():
            new.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old), str(new))
            print(f"[+] {old_path} -> {new_path}")
        else:
            print(f"[-] {old_path} not found")


if __name__ == "__main__":
    mapping = get_file_mapping()
    print(f"[*] Moving {len(mapping)} files to new submodule locations...")
    move_files(mapping)
    print("[*] Done!")
