environment  = "dev"
aws_region   = "us-east-1"
project_name = "algo"
# CORS origin for frontend (set to CloudFront domain in production, localhost in dev)
frontend_origin = "http://localhost:3000"
# Frontend deployment
cloudfront_enabled = true  # Enable S3 + CloudFront distribution for frontend assets
# DISABLED: Step Functions EOD pipeline (4:05pm ET) is the only orchestrator trigger.
# Direct EventBridge rule at 5:30pm ET was causing double execution (one silently blocked by file lock).
algo_schedule_enabled = false
# algo_schedule_expression  = "cron(30 21 ? * MON-FRI *)"  # 5:30pm ET (21:30 UTC)
cognito_enabled = false # Public API access (no authentication required) — API Gateway route auth disabled

# Orchestrator configuration (moved from GitHub Secrets)
execution_mode         = "auto"
orchestrator_dry_run   = false
orchestrator_log_level = "info"
data_patrol_enabled    = true
data_patrol_timeout_ms = 30000
alpaca_paper_trading   = false  # REAL TRADING - set to true for paper trading during testing
api_lambda_timeout     = 60    # VPC cold start (15-20s) + DB init requires >30s default

# NOTE: rds_password is set via TF_VAR_rds_password environment variable
# For local development, export: export TF_VAR_rds_password="YourSecurePasswordHere"
# Or create terraform.tfvars.local (gitignored) with: rds_password = "..."

# Dev cost savings: shorter backup retention (30d default is overkill in dev)
rds_backup_retention_period = 7
