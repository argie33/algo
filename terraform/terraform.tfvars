environment  = "dev"
aws_region   = "us-east-1"
project_name = "algo"
# CORS origin for frontend (set to CloudFront domain in production, localhost in dev)
frontend_origin = "http://localhost:3000"
# Frontend deployment
cloudfront_enabled = true  # Enable S3 + CloudFront distribution for frontend assets
# ENABLED: Orchestrator runs daily at market open (9:30am ET)
# This ensures fresh data is loaded and signals evaluated before market opens
algo_schedule_enabled = true
algo_schedule_expression  = "cron(30 22 ? * MON-FRI *)"  # 10:30 PM UTC = 5:30 PM ET
enable_morning_orchestrator = true
cognito_enabled = true # API Gateway requires Cognito JWT authentication on all routes except /health

# Orchestrator configuration (moved from GitHub Secrets)
execution_mode         = "auto"
orchestrator_dry_run   = false
orchestrator_log_level = "info"
data_patrol_enabled    = true
data_patrol_timeout_ms = 30000
alpaca_paper_trading   = true   # Paper trading mode (not real money)
api_lambda_timeout     = 60    # VPC cold start (15-20s) + DB init requires >30s default

# NOTE: rds_password is set via TF_VAR_rds_password environment variable
# For local development, export: export TF_VAR_rds_password="YourSecurePasswordHere"
# Or create terraform.tfvars.local (gitignored) with: rds_password = "..."

# Dev cost savings: shorter backup retention (30d default is overkill in dev)
rds_backup_retention_period = 7
