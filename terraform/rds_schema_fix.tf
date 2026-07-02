# Migration 0044: Add quality_score columns to quality_metrics table
# This was marked complete in deployment but wasn't actually applied to RDS

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
resource "postgresql_physical_replication_slot" "migration_0044" {
  name            = "migration_0044_quality_metrics"
  plugin          = "test_decoding"
  depends_on      = [postgresql_query.add_debt_to_assets, postgresql_query.add_quality_score, postgresql_query.create_quality_score_index]
}

resource "postgresql_query" "add_debt_to_assets" {
  query = "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS debt_to_assets DECIMAL(8, 4);"
}

resource "postgresql_query" "add_quality_score" {
  query = "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS quality_score DECIMAL(5, 2);"
  depends_on = [postgresql_query.add_debt_to_assets]
}

resource "postgresql_query" "create_quality_score_index" {
  query = "CREATE INDEX IF NOT EXISTS idx_quality_metrics_quality_score ON quality_metrics(quality_score DESC);"
  depends_on = [postgresql_query.add_quality_score]
}

output "migration_0044_status" {
  value = "Migration 0044 applied - quality_metrics columns added"
}
