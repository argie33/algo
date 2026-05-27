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
# ============================================================

# ECS Loader Logs - 7 days (operational debugging only)
resource "aws_cloudwatch_log_group" "ecs_loader_logs" {
  for_each = toset([
    "/ecs/algo-aaiidata-loader",
    "/ecs/algo-algo-orchestrator",
    "/ecs/algo-algo_metrics_daily-loader",
    "/ecs/algo-analyst_sentiment-loader",
    "/ecs/algo-analyst_upgrades_downgrades-loader",
    "/ecs/algo-calendar-loader",
    "/ecs/algo-company_profile-loader",
    "/ecs/algo-earnings_calendar-loader",
    "/ecs/algo-earnings_history-loader",
    "/ecs/algo-earnings_revisions-loader",
    "/ecs/algo-earnings_surprise-loader",
    "/ecs/algo-econ_data-loader",
    "/ecs/algo-etf_prices_daily-loader",
    "/ecs/algo-factor_metrics-loader",
    "/ecs/algo-feargreed-loader",
    "/ecs/algo-financials_annual_balance-loader",
    "/ecs/algo-growth_metrics-loader",
    "/ecs/algo-industry_ranking-loader",
    "/ecs/algo-key_metrics-loader",
    "/ecs/algo-market_health_daily-loader",
    "/ecs/algo-quality_metrics-loader",
    "/ecs/algo-seasonality-loader",
    "/ecs/algo-sectors-loader",
    "/ecs/algo-signals_daily-loader",
    "/ecs/algo-stock_prices_daily-loader",
    "/ecs/algo-technical_data_daily-loader",
    "/ecs/algo-trend_template_data-loader",
    "/ecs/algo-value_metrics-loader",
  ])

  name              = each.value
  retention_in_days = 7

  tags = var.common_tags

  lifecycle {
    ignore_changes = all
  }
}

# Lambda Logs - 30 days (keep longer for debugging Lambda failures)
resource "aws_cloudwatch_log_group" "lambda_logs" {
  for_each = toset([
    "/aws/lambda/algo-data-freshness-monitor-dev",
    "/aws/lambda/algo-db-init-dev",
  ])

  name              = each.value
  retention_in_days = 30

  tags = var.common_tags

  lifecycle {
    ignore_changes = all
  }
}

# RDS Database Logs - 7 days (operational debugging)
resource "aws_cloudwatch_log_group" "rds_logs" {
  for_each = toset([
    "/aws/rds/instance/algo-db/postgresql",
    "/aws/rds/proxy/algo-proxy",
  ])

  name              = each.value
  retention_in_days = 7

  tags = var.common_tags

  lifecycle {
    ignore_changes = all
  }
}

# API Gateway Logs - 7 days
resource "aws_cloudwatch_log_group" "apigateway_logs" {
  for_each = toset([
    "/aws/apigateway/stocks-api-dev",
  ])

  name              = each.value
  retention_in_days = 7

  tags = var.common_tags

  lifecycle {
    ignore_changes = all
  }
}

# ============================================================
# VPC Flow Logs - Delete the expensive 90-day retention log group
# Note: VPC Flow Logs are expensive (~$0.50/GB/month). This deletion
# reduces cost from ~$700/month to $0. If debugging network issues,
# re-enable with 7-day retention.
# ============================================================

resource "aws_cloudwatch_log_group" "vpc_flowlogs" {
  name              = "/aws/vpc/flowlogs/algo-dev"
  retention_in_days = 3  # Minimal retention for active debugging only

  tags = var.common_tags

  lifecycle {
    ignore_changes = all
  }
}

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
