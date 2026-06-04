# ============================================================
# STAGING ENVIRONMENT (N+1 development)
# ============================================================
# Purpose: Develop and test the next version of the algo while
#          the current version (N) continues running in dev.
#
# Key differences from dev:
#   - All orchestrator schedules DISABLED (no automatic execution)
#   - orchestrator_dry_run = true (no trades ever execute)
#   - dev_mode = "true" (extra safety gates)
#   - CloudFront disabled (cost — use API Gateway endpoint directly)
#   - Minimal logging retention
#   - SNS alerts disabled (staging noise is not actionable)
#
# Deploy: Push to the `staging` branch.
#         deploy-staging.yml handles Lambda-only deploy automatically.
#         Full Terraform apply with these vars is NOT required for normal
#         staging development (Lambda reuses dev VPC/RDS).
#
# FIXED F-07: Separate staging RDS (prevents data corruption on production)
# Full infra deploy with isolated staging RDS:
#   terraform workspace new staging
#   terraform apply -var-file=terraform.staging.tfvars \
#     -backend-config="key=stocks/terraform-staging.tfstate"
#
# This ensures staging has its own RDS instance (algo-db-staging) instead of
# sharing production RDS. Bad migrations on staging will not affect production data.
# ============================================================

environment  = "staging"
aws_region   = "us-east-1"
project_name = "algo"

frontend_origin = "http://localhost:3000"
cloudfront_enabled = false

api_cors_allowed_origins = [
  "http://localhost:5173",
  "http://localhost:3000",
]

# ---- SCHEDULES: ALL DISABLED ----
# Staging runs only when manually invoked. Never auto-executes.
algo_schedule_enabled         = false
algo_schedule_expression      = "cron(0 12 ? * MON-FRI *)"
enable_premarket_orchestrator = false
enable_morning_orchestrator   = false
enable_afternoon_orchestrator = false
enable_preclose_orchestrator  = false

# ---- SAFETY: DRY RUN FORCED ----
orchestrator_dry_run = true
execution_mode       = "auto"
dev_mode             = "true"

# ---- LOGGING: VERBOSE FOR DEVELOPMENT ----
orchestrator_log_level = "debug"

# ---- TRADING: PAPER ONLY ----
alpaca_paper_trading  = true
alpaca_api_base_url   = "https://paper-api.alpaca.markets"

# ---- DATABASE: SAME SIZE AS DEV ----
rds_instance_class          = "db.t4g.micro"
rds_backup_retention_period = 1
rds_multi_az                = false

# ---- AUTH: DISABLED ----
cognito_enabled         = false
cognito_test_user_email = "argeropolos@gmail.com"

# ---- MONITORING ----
enable_execution_monitor          = false
enable_execution_monitor_schedule = false
data_patrol_enabled               = true
data_patrol_timeout_ms            = 30000

# ---- LOGGING RETENTION: MINIMAL ----
cloudwatch_log_retention_days  = 3
api_gateway_log_retention_days = 1

# ---- ALERTS: OFF FOR STAGING ----
sns_alerts_enabled  = false
sns_alert_email     = "argeropolos@gmail.com"
alert_email_to      = "argeropolos@gmail.com"
alert_webhook_url   = ""
alert_smtp_host     = "smtp.gmail.com"
alert_smtp_port     = 587
alert_smtp_user     = "argeropolos@gmail.com"
alert_smtp_password = ""
alert_smtp_from     = "argeropolos@gmail.com"

# ---- COST OPTIMIZATION ----
enable_s3_versioning = false

# ---- LAMBDA CONFIG ----
api_lambda_timeout              = 300
api_lambda_reserved_concurrency = 5
algo_lambda_timeout             = 600

# ---- MISC ----
developer_key_rotation_date = "2026-05-29"
