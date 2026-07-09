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
cloudfront_enabled = true # ENABLED: Dashboard now publicly accessible via CloudFront CDN
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
# ORCHESTRATOR SCHEDULE: 2X DAILY (TESTING PHASE)
# Goal: Minimize execution until system is fully verified and stable
# Current configuration: Morning (9:30 AM ET) + Evening (5:30 PM ET)
# Testing phase: No afternoon/pre-close runs (reduce costs and operational complexity)
#
# Pre-market (4:30 AM ET): DISABLED - not during market hours
# Morning (9:30 AM ET): PRIMARY execution at market open [ENABLED]
# Afternoon (1:00 PM ET): Mid-day rebalance [DISABLED for testing]
# Pre-close (3:00 PM ET): Before market close [DISABLED for testing]
# Evening (5:30 PM ET): After close - signal prep for next day [ENABLED]
algo_schedule_enabled         = true                         # Enable 5:30 PM evening run (after loaders, for next day prep)
algo_schedule_expression      = "cron(30 17 ? * MON-FRI *)" # 5:30 PM ET (signal prep for next trading day)
enable_premarket_orchestrator = false                       # Disabled: not during market hours
enable_morning_orchestrator   = true                        # PRIMARY: 9:30 AM ET market open, primary execution
enable_afternoon_orchestrator = true                        # ENABLED: 1:00 PM ET mid-day rebalance (3 hours till close)
enable_preclose_orchestrator  = false                       # DISABLED: 3:00 PM too close to 4 PM close, insufficient time for trade execution
cognito_enabled               = true                        # REQUIRED: Protects /api/algo, /api/signals, /api/scores, /api/audit, /api/trades, /api/admin, /api/settings endpoints.
cognito_test_user_email       = "argeropolos@gmail.com"     # Primary/Admin user — created by Terraform, added to 'admin' group by deployment
cognito_custom_email_enabled  = false                       # OPTIMIZED: Disabled in dev (Lambda not needed for dev testing). Cost: saves $0.50/month
cognito_sender_email          = "argeropolos@gmail.com"     # SES sender email for password reset codes (must be verified in SES)

# AWS Config - disabled due to S3 bucket state corruption
aws_config_enabled = false # Disable AWS Config to resolve Terraform state issues with legacy S3 buckets

# Database configuration
rds_instance_class = "db.t4g.small" # REQUIRED for loader parallelism: Graviton t4g.small (2 vCPU, 2GB, ~100 max_connections) supports concurrent loader execution. With tuned parallelism (2-3 for critical loaders), connection pool remains well below limit. Cost ~$25-30/month.
dev_mode           = false          # Disable dev mode safety gates - enables normal testing with orchestrator_dry_run=false

# Data Freshness Monitoring (F-02 CRITICAL: Must be enabled for live trading)
enable_data_freshness_monitoring = true # Monitor loader data freshness and alert if stale before 9:30 AM trading window

# Orchestrator configuration (moved from GitHub Secrets)
execution_mode                      = "auto"  # Paper trading mode - credentials loaded from algo/alpaca secret, alpaca_paper_trading=true (line 54)
orchestrator_dry_run                = false
orchestrator_log_level              = "info"
data_patrol_enabled                 = true
data_patrol_timeout_ms              = 30000
alpaca_paper_trading                = true # Paper trading enabled (using live keys, but in paper mode via Alpaca account settings)
api_lambda_timeout                  = 120  # FIXED: Increased from 25s→60s→120s for VPC Lambda cold starts (15-40s). VPC ENI attachment takes 15-40s, so Lambda must respond within 120s to avoid API Gateway timeout cascade. Provisioned concurrency (=1) below keeps Lambda warm to eliminate cold start delays.
api_lambda_reserved_concurrency     = 100  # CRITICAL FIX: Increased from 25 to prevent 429 rate limiting. Dashboard needs reliable API access for concurrent panel loads. Concurrency bottleneck confirmed via TooManyRequestsException errors.
api_lambda_provisioned_concurrency  = 1    # RE-ENABLED 2026-07-07: was set to 0 by an earlier commit (eb4e28ae9) to dodge a
# "LIVE alias already exists" ResourceConflictException -- but that was a premature workaround written before the real
# root cause (terraform/modules/services/main.tf's provisioned-concurrency config pointing at a "LIVE" alias with no
# aws_lambda_alias resource ever creating it) was found and fixed by adding aws_lambda_alias.api_live. Verified live:
# the LIVE alias currently in AWS carries that resource's exact description text, so Terraform's state already tracks
# it from a prior successful apply this session. Leaving this at 0 would make the next apply see count drop from 1
# (in state) to 0 (per this var) and DESTROY the alias + provisioned concurrency -- reintroducing the 20-30s VPC
# cold-start problem this was added to fix in the first place.
algo_lambda_timeout                 = 300  # OPTIMIZED: Reduced from 600 to 300s (5 min max). Prevents masking slow/failing loaders. Orchestrator typically completes in 2-3 min.
algo_lambda_ephemeral_storage       = 512  # OPTIMIZED: reduced from 2048 (orchestrator doesn't write large temp files); saves $2-5/month
algo_lambda_provisioned_concurrency = 0    # Orchestrator runs on schedule, cold start is acceptable
algo_lambda_reserved_concurrency    = 10   # FIXED 2026-07-07: Increased from 5 to ensure orchestrator runs without throttling. Manual trigger + local scheduler + EventBridge (if enabled) need headroom for overlapping invocations. DB advisory lock prevents concurrent trading logic, but this prevents 429 rate limiting on Lambda invoke.
# Provisioned concurrency for API only (~$12/month) worth the 502 error fix.

# RDS password: generated by Terraform's random_password.rds_master, stored in state and Secrets Manager
# No hardcoded values — Terraform manages the full password lifecycle via IaC
# GitHub Actions fetches credentials from Secrets Manager using OIDC (no GitHub Secrets needed)

# COST OPTIMIZED: Minimal backup retention for dev
rds_backup_retention_period = 1

# Alpaca API configuration
# Credentials are stored securely in AWS Secrets Manager (algo/alpaca secret)
# Set via environment variables at deploy time, NOT in this file (security best practice)
# To enable live trading: export TF_VAR_alpaca_api_key_id and TF_VAR_alpaca_api_secret_key before terraform apply
alpaca_api_key_id     = ""  # Set via TF_VAR_alpaca_api_key_id environment variable at deploy time
alpaca_api_secret_key = ""  # Set via TF_VAR_alpaca_api_secret_key environment variable at deploy time
alpaca_api_base_url   = "https://paper-api.alpaca.markets" # Paper trading URL

# Execution Monitor - queries RDS for signals and Alpaca for trades
enable_execution_monitor          = false # OPTIMIZED: Disabled in dev (paper trading only, low value); cost: $13/month
enable_execution_monitor_schedule = false # Run every 2 hours during trading hours

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
cloudwatch_log_retention_days  = 1 # OPTIMIZED from 3: 1 day sufficient for debugging (keep only recent runs); saves $2-3/month
api_gateway_log_retention_days = 1 # OPTIMIZED from 3: 1 day sufficient (API logs rotate daily anyway); saves $0.50-1/month

# S3 Bucket Expiration (staging data retention)
code_bucket_expiration_days = 7 # OPTIMIZED from 30→7: CI/CD rebuilds ZIPs from source; old builds not needed; saves $1-2/month
data_bucket_expiration_days = 7 # OPTIMIZED from 14→7: staging data regenerable from APIs; saves $0.50-1/month

# ============================================================
# RDS Proxy Configuration
# ============================================================
enable_rds_proxy = false # OPTIMIZED: Disabled in dev (saves ~$150/month). Enabled for production with 24+ concurrent loaders. Dev loaders don't need 24/7 connection pooling.

# ============================================================
# VPC Endpoints Configuration
# ============================================================
enable_vpc_endpoints = false # OPTIMIZED: Disabled in dev (saves ~$43/month). ECS tasks pull from ECR using public endpoints. Re-enable for production security requirements.

# ============================================================
# Development Machine Access
# ============================================================
dev_machine_cidr = "97.130.69.107/32" # Allow local dev_server.py to connect to RDS directly
