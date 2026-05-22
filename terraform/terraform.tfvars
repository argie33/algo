environment  = "dev"
aws_region   = "us-east-1"
project_name = "algo"
# CORS origin for frontend (set to CloudFront domain in production, localhost in dev)
frontend_origin = "http://localhost:3000"
# Frontend deployment
cloudfront_enabled = true # Enable S3 + CloudFront distribution for frontend assets
# API Gateway CORS configuration - includes both local dev and AWS production origins
api_cors_allowed_origins = [
  "http://localhost:5173",
  "http://localhost:3000",
  "http://localhost:5174",
  "https://d5j1h4wzrkvw7.cloudfront.net"
]
# ENABLED: Orchestrator runs daily at market open (9:30am ET)
# This ensures fresh data is loaded and signals evaluated before market opens
algo_schedule_enabled       = true
algo_schedule_expression    = "cron(30 22 ? * MON-FRI *)" # 10:30 PM UTC = 5:30 PM ET
enable_morning_orchestrator = true
cognito_enabled             = true # Authorizer exists but not used on routes (all NONE auth)

# Orchestrator configuration (moved from GitHub Secrets)
execution_mode         = "auto"
orchestrator_dry_run   = false
orchestrator_log_level = "info"
data_patrol_enabled    = true
data_patrol_timeout_ms = 30000
alpaca_paper_trading   = false # LIVE trading mode with real Alpaca credentials
api_lambda_timeout     = 60    # VPC cold start (15-20s) + DB init requires >30s default
algo_lambda_timeout    = 600   # Orchestrator needs time to process: 7 phases, data loading, signal generation

# RDS password: set via TF_VAR_rds_password GitHub Secret in CI
# Must be stored in GitHub Secrets as RDS_PASSWORD and passed to Terraform
# This ensures single source of truth for database credentials
rds_password = "" # Empty = use env var TF_VAR_rds_password (required in CI)

# Dev cost savings: shorter backup retention (30d default is overkill in dev)
rds_backup_retention_period = 7

# Alpaca API configuration - LIVE trading
alpaca_api_base_url = "https://api.alpaca.markets" # LIVE API (not paper-api.alpaca.markets)

# Execution Monitor - queries RDS for signals and Alpaca for trades
enable_execution_monitor          = true # Deploy execution monitor Lambda
enable_execution_monitor_schedule = true # Run every 2 hours during trading hours
