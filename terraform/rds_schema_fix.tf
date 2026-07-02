# Migration 0044: Complete - Add quality_score and unavailable_reason columns to quality_metrics table
# CRITICAL FIX: Original Terraform was incomplete (only added quality_score + debt_to_assets)
# Missing 9 unavailable_reason columns caused BulkInsertManager to silently drop data
# This complete version adds all 11 columns required by load_quality_metrics.py

terraform {
  required_providers {
    postgresql = {
      source  = "cyrilgdn/postgresql"
      version = "~> 1.15"
    }
  }
}

provider "postgresql" {
  host            = "algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com"
  port            = 5432
  database        = "algo_prod"
  username        = "algo_admin"
  password        = var.rds_password
  sslmode         = "require"
  connect_timeout = 15
}

variable "rds_password" {
  description = "AWS RDS password for algo_admin user"
  type        = string
  sensitive   = true
}

# Add missing columns to quality_metrics table
# COMPLETE migration includes all columns that load_quality_metrics.py writes

resource "postgresql_query" "add_debt_to_assets" {
  query = "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS debt_to_assets DECIMAL(8, 4);"
}

resource "postgresql_query" "add_quality_score" {
  query = "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS quality_score DECIMAL(5, 2);"
  depends_on = [postgresql_query.add_debt_to_assets]
}

resource "postgresql_query" "add_operating_margin_unavailable_reason" {
  query = "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS operating_margin_unavailable_reason VARCHAR(255);"
  depends_on = [postgresql_query.add_quality_score]
}

resource "postgresql_query" "add_net_margin_unavailable_reason" {
  query = "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS net_margin_unavailable_reason VARCHAR(255);"
  depends_on = [postgresql_query.add_operating_margin_unavailable_reason]
}

resource "postgresql_query" "add_roe_unavailable_reason" {
  query = "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS roe_unavailable_reason VARCHAR(255);"
  depends_on = [postgresql_query.add_net_margin_unavailable_reason]
}

resource "postgresql_query" "add_roa_unavailable_reason" {
  query = "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS roa_unavailable_reason VARCHAR(255);"
  depends_on = [postgresql_query.add_roe_unavailable_reason]
}

resource "postgresql_query" "add_debt_to_equity_unavailable_reason" {
  query = "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS debt_to_equity_unavailable_reason VARCHAR(255);"
  depends_on = [postgresql_query.add_roa_unavailable_reason]
}

resource "postgresql_query" "add_current_ratio_unavailable_reason" {
  query = "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS current_ratio_unavailable_reason VARCHAR(255);"
  depends_on = [postgresql_query.add_debt_to_equity_unavailable_reason]
}

resource "postgresql_query" "add_quick_ratio_unavailable_reason" {
  query = "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS quick_ratio_unavailable_reason VARCHAR(255);"
  depends_on = [postgresql_query.add_current_ratio_unavailable_reason]
}

resource "postgresql_query" "add_interest_coverage_unavailable_reason" {
  query = "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS interest_coverage_unavailable_reason VARCHAR(255);"
  depends_on = [postgresql_query.add_quick_ratio_unavailable_reason]
}

resource "postgresql_query" "add_debt_to_assets_unavailable_reason" {
  query = "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS debt_to_assets_unavailable_reason VARCHAR(255);"
  depends_on = [postgresql_query.add_interest_coverage_unavailable_reason]
}

resource "postgresql_query" "create_quality_score_index" {
  query = "CREATE INDEX IF NOT EXISTS idx_quality_metrics_quality_score ON quality_metrics(quality_score DESC);"
  depends_on = [postgresql_query.add_debt_to_assets_unavailable_reason]
}

output "migration_0044_status" {
  value = "Migration 0044 COMPLETE - All 11 columns added to quality_metrics (quality_score, debt_to_assets, 9x unavailable_reason)"
}

output "migration_0044_columns_added" {
  value = [
    "quality_score",
    "debt_to_assets",
    "operating_margin_unavailable_reason",
    "net_margin_unavailable_reason",
    "roe_unavailable_reason",
    "roa_unavailable_reason",
    "debt_to_equity_unavailable_reason",
    "current_ratio_unavailable_reason",
    "quick_ratio_unavailable_reason",
    "interest_coverage_unavailable_reason",
    "debt_to_assets_unavailable_reason"
  ]
}
