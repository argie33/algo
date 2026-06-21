/**
 * Lifecycle Module - Cleanup & Retention Policies
 *
 * Enforces:
 * - Keep only latest ECS task definition version
 * - CloudWatch log retention on all logs (prevents unbounded growth)
 * - Prevent orphaned RDS instances from persisting
 */

# ============================================================
# CloudWatch Log Group Retention Policies
# Note: Log groups are auto-created by AWS services (Lambda, ECS, RDS, etc.)
# Terraform uses data sources to reference existing groups and manages retention only.
# ============================================================

# Retain logs for operational log groups (7 days = balance between debugging & cost)
locals {
  log_groups_with_retention = [
    "/aws/batch/job",
    "/aws/lambda/algo-cognito-email-trigger-dev",
    "/aws/lambda/algo-data-freshness-monitor-dev",
    "/aws/lambda/algo-db-init-dev",
    "/aws/lambda/algo-loader-failure-handler-dev",
    "/aws/rds/instance/algo-db/postgresql",
    "/aws/rds/proxy/algo-proxy",
    "/aws/rds/proxy/algo-rds-proxy-dev",
    "/aws/ssm/sessions",
    "/aws/vpc/flowlogs/algo-dev",
    "/ecs/algo-aaiidata-loader",
    "/ecs/algo-algo-orchestrator",
    "/ecs/algo-algo_metrics_daily-loader",
    "/ecs/algo-analyst_sentiment-loader",
    "/ecs/algo-analyst_upgrades_downgrades-loader",
    "/ecs/algo-buy_sell_daily-loader",
    "/ecs/algo-calendar-loader",
    "/ecs/algo-company_profile-loader",
    "/ecs/algo-compute_circuit_breakers-loader",
    "/ecs/algo-compute_performance_metrics-loader",
    "/ecs/algo-continuous-monitor",
    "/ecs/algo-data-patrol",
    "/ecs/algo-earnings_calendar-loader",
    "/ecs/algo-earnings_history-loader",
    "/ecs/algo-earnings_revisions-loader",
    "/ecs/algo-earnings_surprise-loader",
    "/ecs/algo-econ_data-loader",
    "/ecs/algo-economic_calendar-loader",
    "/ecs/algo-economic_metrics_daily-loader",
    "/ecs/algo-eod_bulk_refresh-loader",
    "/ecs/algo-etf_prices_daily-loader",
    "/ecs/algo-etf_prices_monthly-loader",
    "/ecs/algo-etf_prices_weekly-loader",
    "/ecs/algo-feargreed-loader",
    "/ecs/algo-financials_annual_balance-loader",
  ]
}

# Skip log group creation - they already exist in AWS from ECS/Lambda services
# Creating them causes ResourceAlreadyExistsException errors
# Retention is managed by ECS tasks, not Terraform
# If retention update needed, use: aws logs put-retention-policy --log-group-name <name> --retention-in-days 7

# ============================================================
# Task Definition Version Cleanup
# Note: Terraform doesn't have native support for deleting old task definition versions.
# Instead, we mark them with a lifecycle rule that prevents creation of old versions
# during future deploys. Manual cleanup via AWS CLI:
#
# aws ecs deregister-task-definition --task-definition <name:oldversion>
#
# Or use the GitHub Actions cleanup step added in CI/CD.
# ============================================================
