# Staging Terraform Configuration
# ============================================================
# Staging environment: balanced between dev and production
# - Production-like infrastructure for realistic testing
# - Cost-optimized where not critical to testing
# - Reduced monitoring/alerting vs production
# ============================================================

# Core Configuration
environment  = "staging"
aws_region   = "us-east-1"
project_name = "algo"

# ============================================================
# FRONTEND & API CONFIGURATION (STAGING)
# ============================================================

# Frontend origin: set by CI/CD to staging CloudFront domain
frontend_origin = ""

# CloudFront: enabled for production-like testing
cloudfront_enabled = true

# API CORS: set by CI/CD pipeline
api_cors_allowed_origins = []

# CloudFront domain: set via TF_VAR_cloudfront_domain at deploy time
cloudfront_domain = ""

# ============================================================
# COGNITO AUTHENTICATION (STAGING)
# ============================================================

cognito_enabled               = true
cognito_test_user_email       = "staging-test@example.com"  # Test user for staging
cognito_custom_email_enabled  = false
cognito_sender_email          = ""
cognito_mfa_configuration     = "OPTIONAL"   # Less strict than prod for faster testing
cognito_advanced_security_mode = "AUDIT"     # Monitor but don't enforce

# ============================================================
# ORCHESTRATOR SCHEDULE (STAGING)
# ============================================================

# Staging: 2x daily, same as production for realistic testing
algo_schedule_enabled         = true
algo_schedule_expression      = "cron(30 9 ? * MON-FRI *)"
algo_schedule_timezone        = "America/New_York"
enable_morning_orchestrator   = true
enable_afternoon_orchestrator = false
enable_preclose_orchestrator  = false
enable_premarket_orchestrator = false

# ============================================================
# DATABASE CONFIGURATION (STAGING)
# ============================================================

# Production-like database for realistic testing
rds_instance_class = "db.t4g.small"
rds_multi_az       = false                    # Cost optimization: single AZ okay for staging
rds_backup_retention_period = 7               # Reduced retention for cost: 7 days
enable_rds_kms_encryption   = false           # Skip KMS for staging cost savings (~$100/month)
enable_rds_proxy    = false                   # Skip RDS Proxy for staging cost savings (~$150/month)

# DB SSL mode: require for security testing
db_ssl_mode = "require"

# ============================================================
# DATA FRESHNESS & MONITORING (STAGING)
# ============================================================

enable_data_freshness_monitoring = true       # Same as prod for realistic testing
enable_execution_monitor          = false     # Cost optimization: not needed for staging
enable_execution_monitor_schedule = false

# Data patrol: same as prod for testing
data_patrol_enabled    = true
data_patrol_timeout_ms = 60000

# ============================================================
# SECURITY & COMPLIANCE (STAGING)
# ============================================================

# Deletion protection: ON for staging database integrity
db_deletion_protection = true

# IaC enforcement: enabled for staging
enforce_iac_only     = true
require_terraform_tag = true

# Audit logging: enabled
cloudtrail_enabled = true

# Threat detection: disabled to save costs (~$5-10/month)
guardduty_enabled = false

# Compliance monitoring: disabled to save costs (~$1/month)
aws_config_enabled = false

# Network monitoring: disabled to save costs (~$5-10/month)
vpc_flow_logs_enabled = false

# Security log retention: 14 days (reduced vs prod for cost)
security_log_retention_days = 14

# ============================================================
# OBSERVABILITY & ALERTING (STAGING)
# ============================================================

# CloudWatch logs: 7 days (reduced for cost optimization)
cloudwatch_log_retention_days  = 7
api_gateway_log_retention_days = 7

# RDS monitoring: enabled
enable_rds_cloudwatch_logs = true
enable_rds_alarms         = true

# Performance alarms: disabled for cost (~$2/month)
enable_performance_alarms = false

# Resource alarms: disabled for cost (~$3/month)
enable_resource_alarms = false

# Data quality monitors: disabled for cost (~$3-4/month)
enable_data_quality_monitors = false

# SNS alerts: enabled for critical infrastructure issues
sns_alerts_enabled  = true
sns_alert_email     = ""                      # Set via TF_VAR_sns_alert_email in CI/CD

# Email alerts: SMTP configuration optional in staging
alert_email_to      = ""
alert_email_address = ""
alert_webhook_url   = ""

# SMTP: optional in staging
alert_smtp_host     = ""
alert_smtp_port     = 587
alert_smtp_user     = ""
alert_smtp_password = ""
alert_smtp_from     = ""

# ============================================================
# LAMBDA CONFIGURATION (STAGING)
# ============================================================

# API Lambda: balanced performance/cost
api_lambda_memory                 = 256
api_lambda_timeout                = 40
api_lambda_reserved_concurrency   = 8
api_lambda_provisioned_concurrency = 0        # No provisioned concurrency: cost savings

# Algo Lambda: sufficient for testing
algo_lambda_memory                = 512
algo_lambda_timeout               = 900
algo_lambda_reserved_concurrency  = 2
algo_lambda_provisioned_concurrency = 0

# ============================================================
# S3 & STORAGE (STAGING)
# ============================================================

# S3 versioning: enabled for testing rollback
enable_s3_versioning = true

# Retention: reduced for cost
code_bucket_expiration_days = 30
data_bucket_expiration_days = 14

# S3 encryption: AWS-managed (cost optimization)
s3_encryption_kms_key_id  = ""
enforce_s3_kms_encryption = false

# Log archive: shorter retention for cost
log_archive_transition_ia_days           = 14
log_archive_transition_glacier_days      = 30
log_archive_transition_deep_archive_days = 90
log_archive_expiration_days              = 365
log_archive_intelligent_tiering_enabled  = false

# ============================================================
# VPC & NETWORK (STAGING)
# ============================================================

vpc_cidr             = "10.0.0.0/16"
public_subnet_cidrs  = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnet_cidrs = ["10.0.10.0/24", "10.0.11.0/24"]
availability_zones   = ["us-east-1a", "us-east-1b"]

# VPC Endpoints: disabled to save costs (~$43/month)
enable_vpc_endpoints = false

# No dev machine access in staging (production-like environment)
dev_machine_cidr = ""

# ============================================================
# ALPACA TRADING (STAGING)
# ============================================================

# Paper trading: always in staging for safety
alpaca_paper_trading = true

# Credentials: set via CI/CD environment variables
alpaca_api_key_id     = ""
alpaca_api_secret_key = ""
alpaca_api_base_url   = "https://paper-api.alpaca.markets"

# ============================================================
# EXECUTION & DRY-RUN (STAGING)
# ============================================================

execution_mode      = "auto"
orchestrator_dry_run = false                   # Test real orchestration logic
orchestrator_log_level = "info"                # More verbose for debugging

# ============================================================
# IAM & SECURITY (STAGING)
# ============================================================

developer_key_rotation_date = "2026-05-29"
secrets_rotation_days = 30
postgres_major_version = "16"

# ============================================================
# AWS BATCH (STAGING)
# ============================================================

batch_max_vcpus = 128                          # Reduced for staging
batch_instance_types = ["c6i.xlarge", "m6i.xlarge"]  # Fewer instance types
batch_spot_bid_percentage = 70
batch_vcpus   = 2
batch_memory_mb = 2048

# ============================================================
# ECR (STAGING)
# ============================================================

ecr_image_scan_enabled = true                  # Enable scanning
ecr_image_tag_mutability = "MUTABLE"           # Allow tag updates in staging

# ============================================================
# TAGS (STAGING)
# ============================================================

common_tags = {
  Project     = "algo"
  Environment = "staging"
  ManagedBy   = "Terraform"
  Purpose     = "Integration Testing"
}
