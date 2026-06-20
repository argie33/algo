# ⚠️  WARNING: environment = "dev" — paper trading enabled (alpaca_paper_trading = true, line 54).
# All resources named "-dev" suffix. Paper trades only — no real money.
# See steering/algo.md for full context.
# See steering/algo.md for full context.
environment  = "dev"
aws_region   = "us-east-1"
project_name = "algo"
# Frontend origin for authentication redirects
# Dynamically set from deployment environment via TF_VAR_frontend_origin environment variable
# Terraform module uses this for Cognito redirect URIs and similar CORS configurations
# Default value: http://localhost:3000 (for local dev); overridden by TF_VAR_frontend_origin in GitHub Actions
# GitHub Actions workflow sets this to the CloudFront domain at deployment time
frontend_origin = "http://localhost:3000" # Default for local dev; overridden by TF_VAR_frontend_origin in CI
# Frontend deployment
cloudfront_enabled = true # Enable CloudFront for AWS deployment (CORS origins include base API Gateway)
# API Gateway CORS configuration - Dynamically set from deployment environment
# The CloudFront domain is discovered at deployment time and passed via TF_VAR_api_cors_allowed_origins
# environment variable. This avoids hardcoding and ensures CORS always works with the current domain.
# See .github/workflows/deploy-all-infrastructure.yml "Discover CloudFront domain for CORS configuration" step
# Fallback: If no environment variable is set, this default is used (empty list is a safe fallback)
api_cors_allowed_origins = [
  "https://d2u93283nn45h2.cloudfront.net",
  "http://localhost:5173",
  "http://localhost:3000"
]
# ORCHESTRATOR SCHEDULE: 3 runs during market hours
# Goal: Keep signals computed overnight, execute multiple times to catch opportunities + meet 4 PM ET close SLA
# All runs use signals from previous night's EOD computation (no intraday signal recalc yet)
# Pre-market (4:30 AM ET): DISABLED - not during market hours
# Morning (9:30 AM ET): PRIMARY execution at market open [enabled]
# Afternoon (1:00 PM ET): Mid-day rebalance, catch missed opportunities [enabled]
# Pre-close (3:00 PM ET): FINAL execution before 4 PM ET market close, SLA finish by 3:15 PM ET [enabled]
# Evening (5:30 PM ET): AFTER CLOSE - signal prep for next day only, no trading [managed separately]
algo_schedule_enabled         = true
algo_schedule_expression      = "cron(30 17 ? * MON-FRI *)" # 5:30 PM ET (signal prep, not trading)
enable_premarket_orchestrator = false                       # Disabled: not during market hours
enable_morning_orchestrator   = true                        # PRIMARY: 9:30 AM ET market open
enable_afternoon_orchestrator = true                        # 1:00 PM ET mid-day rebalance
enable_preclose_orchestrator  = true                        # FINAL: 3:00 PM ET last trades before close
cognito_enabled               = true                        # REQUIRED: Protects /api/algo, /api/signals, /api/scores, /api/audit, /api/trades, /api/admin, /api/settings endpoints.
cognito_test_user_email       = "argeropolos@gmail.com"     # Primary/Admin user — created by Terraform, added to 'admin' group by deployment
cognito_custom_email_enabled  = true                        # Cognito custom message Lambda for professional emails via SES
cognito_sender_email          = "argeropolos@gmail.com"     # SES sender email for password reset codes (must be verified in SES)

# AWS Config - disabled due to S3 bucket state corruption
aws_config_enabled = false # Disable AWS Config to resolve Terraform state issues with legacy S3 buckets

# Database configuration
rds_instance_class = "db.t4g.small" # REQUIRED for loader parallelism: Graviton t4g.small (2 vCPU, 2GB, ~100 max_connections) supports concurrent loader execution. With tuned parallelism (2-3 for critical loaders), connection pool remains well below limit. Cost ~$25-30/month.
dev_mode           = false          # Disable dev mode safety gates - enables normal testing with orchestrator_dry_run=false

# Data Freshness Monitoring (F-02 CRITICAL: Must be enabled for live trading)
enable_data_freshness_monitoring = true # Monitor loader data freshness and alert if stale before 9:30 AM trading window

# Orchestrator configuration (moved from GitHub Secrets)
execution_mode                      = "auto"
orchestrator_dry_run                = false
orchestrator_log_level              = "info"
data_patrol_enabled                 = true
data_patrol_timeout_ms              = 30000
alpaca_paper_trading                = true # Paper trading — live keys not yet configured in algo/alpaca secret
api_lambda_timeout                  = 25   # Validation requires max 25s (API Gateway enforces 29s hard limit, but terraform validation stricter). VPC cold start risk: 15-40s, so retry on client side.
api_lambda_reserved_concurrency     = 50   # MarketsHealth fires 26 concurrent calls on load (4 indices + 11 sector tiles + 4 VIX + 5 main + 2 extras). 50 gives headroom for 2 simultaneous users.
api_lambda_provisioned_concurrency  = 1    # Keep 1 instance warm to avoid 15-40s VPC cold start 502 errors. Cost: ~$12/month
algo_lambda_timeout                 = 600
algo_lambda_provisioned_concurrency = 0 # Orchestrator runs on schedule, cold start is acceptable
# COST OPTIMIZED: Reserved concurrency removed (saves $170+/month). Provisioned concurrency for API only (~$12/month) worth the 502 error fix.

# RDS password: generated by Terraform's random_password.rds_master, stored in state and Secrets Manager
# No hardcoded values — Terraform manages the full password lifecycle via IaC
# GitHub Actions fetches credentials from Secrets Manager using OIDC (no GitHub Secrets needed)

# COST OPTIMIZED: Minimal backup retention for dev
rds_backup_retention_period = 1

# Alpaca API configuration
alpaca_api_base_url = "https://paper-api.alpaca.markets" # Paper API — matches paper keys in algo/alpaca secret

# Execution Monitor - queries RDS for signals and Alpaca for trades
enable_execution_monitor          = true # Deploy execution monitor Lambda
enable_execution_monitor_schedule = true # Run every 2 hours during trading hours

# Developer IAM credential rotation - update to trigger key recreation
developer_key_rotation_date = "2026-05-29"

# Alert system configuration (for patrol, loader, position, circuit breaker failures)
# Infrastructure alerts: via SNS (already configured at line 77)
# Application alerts (from orchestrator/patrol/loaders): via SMTP email
#
# SMTP Email Alerts (Recommended):
#
# Gmail SMTP Setup:
#   1. Enable 2FA in Google Account settings
#   2. Generate app-specific password at myaccount.google.com/apppasswords
#   3. Set the variables below:
#     alert_smtp_host     = ""
#     alert_smtp_port     = 587
#     alert_smtp_user     = ""
#     alert_smtp_password = "your-app-specific-password" (NOT your regular Gmail password)
#     alert_smtp_from     = ""
#
# Other SMTP Providers:
#   Outlook/Office365: smtp.office365.com:587
#   Custom SMTP: Your email provider's SMTP hostname and port
#
sns_alerts_enabled  = true                    # Enable SNS topic for infrastructure alerts (Step Functions, RDS, CloudWatch)
sns_alert_email     = "argeropolos@gmail.com" # SNS email subscription for infrastructure alerts
alert_email_address = "argeropolos@gmail.com" # Email for circuit breaker alerts (SNS topic subscription)
alert_email_to      = "argeropolos@gmail.com" # Email recipients for direct SMTP alerts from orchestrator
alert_webhook_url   = ""                      # Leave blank (using email alerts)
# SMTP configuration for email alerts (set all)
alert_smtp_host     = ""  # SMTP hostname for Gmail
alert_smtp_port     = 587 # SMTP port (587 for TLS, 465 for SSL)
alert_smtp_user     = ""  # Gmail account for sending alerts
alert_smtp_password = ""  # SMTP password (use GitHub Secrets ALERT_SMTP_PASSWORD in CI/CD)
alert_smtp_from     = ""  # From email address for alerts

# ============================================================
# COST OPTIMIZATION: Storage & Database
# ============================================================
enable_s3_versioning = false # COST OPTIMIZED: S3 versioning disabled. Saves ~$5-10/month on storage. Not needed for dev.
rds_multi_az         = false # COST OPTIMIZED: Single-AZ. Saves ~$15/month.

# S3 Lifecycle Optimization: Reduce artifact retention
# Default: data_bucket_expiration_days = 30, code_bucket_expiration_days = 90
# Optimization: Reduce to 21 and 60 respectively (saves ~$5-8/month, staging/artifacts not needed long-term)

# ============================================================
# SECURITY: Data Encryption at Rest
# ============================================================
enable_rds_kms_encryption = false # RDS uses AWS-managed encryption key; switching to customer-managed requires instance replacement (blocked by prevent_destroy)

# ============================================================
# COST OPTIMIZATION: Logging & Observability
# ============================================================
cloudwatch_log_retention_days  = 5 # OPTIMIZED from 7: 5 days sufficient (28 orchestrator runs/week = easy to find recent logs); saves $1-2/month
api_gateway_log_retention_days = 3 # Already optimized

# S3 Bucket Expiration (staging data retention)
code_bucket_expiration_days = 60   # OPTIMIZED from 90: artifacts can be rebuilt from source; saves $3-5/month
data_bucket_expiration_days = 21   # OPTIMIZED from 30: staging data not needed long-term; saves $2-3/month

# ============================================================
# RDS Proxy Configuration
# ============================================================
enable_rds_proxy = true # CRITICAL: Enables connection pooling for 24+ concurrent loaders (multiplexes to 20-30 RDS connections). Essential for EOD and morning prep pipelines.

# ============================================================
# Development Machine Access
# ============================================================
dev_machine_cidr = "75.250.183.199/32" # Allow local dev_server.py to connect to RDS directly

