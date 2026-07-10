# Production Terraform Configuration
# ============================================================
# SECURITY: This file contains production-safe defaults
# Environment-specific overrides: use TF_VAR_* environment variables
# ============================================================

# Core Configuration
environment  = "prod"
aws_region   = "us-east-1"
project_name = "algo"

# ============================================================
# FRONTEND & API CONFIGURATION (PRODUCTION-SAFE DEFAULTS)
# ============================================================

# Frontend origin MUST be set via TF_VAR_frontend_origin env var
# (Set by GitHub Actions CI/CD to CloudFront domain at deployment time)
# Default: empty string (Cognito defaults to Cognito domain)
frontend_origin = ""

# CloudFront REQUIRED in production for performance, security, and API routing
cloudfront_enabled = true

# API CORS: MUST be set via TF_VAR_api_cors_allowed_origins env var
# Default: empty list (no origins allowed until CI/CD sets production domain)
api_cors_allowed_origins = []

# CloudFront domain MUST be set via TF_VAR_cloudfront_domain env var at deploy time
# Leave empty here - CI/CD discovers and passes real domain
cloudfront_domain = ""

# ============================================================
# COGNITO AUTHENTICATION (PRODUCTION)
# ============================================================

cognito_enabled               = true
cognito_test_user_email       = ""           # SECURITY: No test users in production
cognito_custom_email_enabled  = false         # Cost optimization
cognito_sender_email          = ""            # Must be SES-verified in production
cognito_mfa_configuration     = "REQUIRED"    # SECURITY: MFA mandatory in production
cognito_advanced_security_mode = "ENFORCED"   # SECURITY: Fraud detection in production

# ============================================================
# ORCHESTRATOR SCHEDULE (PRODUCTION)
# ============================================================

# Production: 2x daily execution (market open + after close)
algo_schedule_enabled         = true
algo_schedule_expression      = "cron(30 9 ? * MON-FRI *)"  # 9:30 AM ET (market open)
algo_schedule_timezone        = "America/New_York"
enable_morning_orchestrator   = true                        # Primary: 9:30 AM market open
enable_afternoon_orchestrator = false                       # Disabled: reduce complexity
enable_preclose_orchestrator  = false                       # Disabled: insufficient execution time
enable_premarket_orchestrator = false                       # Disabled: no market hours

# Evening orchestrator disabled in favor of morning-only in production
# Rationale: Paper trading doesn't need evening prep. Real trading: evaluate daily at 9:30 AM only.

# ============================================================
# DATABASE CONFIGURATION (PRODUCTION)
# ============================================================

rds_instance_class = "db.t4g.small"           # Production-grade instance
rds_multi_az       = true                     # High availability: standby replica in different AZ
rds_backup_retention_period = 30              # 30-day backup retention (production requirement)
enable_rds_kms_encryption   = true            # Customer-managed KMS for encryption at rest
enable_rds_proxy    = true                    # Connection pooling for 24+ concurrent loaders

# DB SSL mode: production always requires SSL
db_ssl_mode = "require"

# ============================================================
# DATA FRESHNESS & MONITORING (PRODUCTION)
# ============================================================

enable_data_freshness_monitoring = true       # Monitor loader data before 9:30 AM trading
enable_execution_monitor          = true      # Monitor realized vs predicted trades
enable_execution_monitor_schedule = true      # Run every 2 hours during trading hours

# Data patrol: extensive monitoring in production
data_patrol_enabled    = true
data_patrol_timeout_ms = 90000                # 90 seconds: allow full data quality scan

# ============================================================
# SECURITY & COMPLIANCE (PRODUCTION)
# ============================================================

# Deletion protection ON: prevent accidental RDS deletion
db_deletion_protection = true

# Enforce IaC-only resource creation
enforce_iac_only     = true
require_terraform_tag = true

# CloudTrail: comprehensive audit logging
cloudtrail_enabled = true

# GuardDuty: threat detection in production
guardduty_enabled = true

# AWS Config: compliance monitoring
aws_config_enabled = true

# VPC Flow Logs: network security monitoring
vpc_flow_logs_enabled = true

# Security log retention: 90 days (production compliance requirement)
security_log_retention_days = 90

# ============================================================
# OBSERVABILITY & ALERTING (PRODUCTION)
# ============================================================

# CloudWatch logs: 30-day retention (production requirement)
cloudwatch_log_retention_days  = 30
api_gateway_log_retention_days = 30

# RDS monitoring: all alarms enabled
enable_rds_cloudwatch_logs = true
enable_rds_alarms         = true

# Performance alarms: enabled in production
enable_performance_alarms = true

# Resource utilization alarms: enabled in production
enable_resource_alarms = true

# Data quality monitors: enabled in production
enable_data_quality_monitors = true

# SNS alerts: enabled for infrastructure failures
sns_alerts_enabled  = true
sns_alert_email     = ""                      # Set via TF_VAR_sns_alert_email in CI/CD

# Email alerts: SMTP configuration required
alert_email_to      = ""                      # Set via TF_VAR_alert_email_to in CI/CD
alert_email_address = ""                      # Set via TF_VAR_alert_email_address in CI/CD
alert_webhook_url   = ""                      # Set via TF_VAR_alert_webhook_url if using Slack/Teams

# SMTP configuration (set via TF_VAR_alert_smtp_* environment variables in CI/CD)
alert_smtp_host     = ""                      # Set via GitHub Actions secrets
alert_smtp_port     = 587                     # TLS port
alert_smtp_user     = ""                      # Set via GitHub Actions secrets
alert_smtp_password = ""                      # Set via GitHub Actions secrets
alert_smtp_from     = ""                      # Set via GitHub Actions secrets

# ============================================================
# LAMBDA CONFIGURATION (PRODUCTION)
# ============================================================

# API Lambda: optimized for concurrent dashboard requests
api_lambda_memory                 = 512       # More memory for faster execution
api_lambda_timeout                = 60        # 60 seconds sufficient for API responses
api_lambda_reserved_concurrency   = 50        # Reserve capacity to prevent throttling
api_lambda_provisioned_concurrency = 5        # Pre-warm instances (costs ~$60/month)

# Algo orchestrator Lambda: sufficient for batch processing
algo_lambda_memory                = 1024      # Increased memory for complex orchestration
algo_lambda_timeout               = 900       # 15 minutes: max Lambda timeout
algo_lambda_reserved_concurrency  = 10        # Buffer for orchestrator + API requests
algo_lambda_provisioned_concurrency = 0       # Cold start acceptable for scheduled tasks

# ============================================================
# S3 & STORAGE (PRODUCTION)
# ============================================================

# Enable S3 versioning for production data protection
enable_s3_versioning = true

# Retention policies: keep artifacts longer for compliance
code_bucket_expiration_days = 90               # Keep 90 days of deployments
data_bucket_expiration_days = 30               # Keep 30 days of staging data

# S3 encryption: customer-managed KMS required for SOC2/PCI-DSS
s3_encryption_kms_key_id  = ""                 # Set via TF_VAR_s3_encryption_kms_key_id
enforce_s3_kms_encryption = true               # Only allow KMS-encrypted uploads

# Log archive lifecycle: long-term retention
log_archive_transition_ia_days           = 30   # Standard-IA after 30 days
log_archive_transition_glacier_days      = 90   # Glacier after 90 days
log_archive_transition_deep_archive_days = 365  # Deep Archive after 1 year
log_archive_expiration_days              = 2555 # Keep for 7 years (compliance)
log_archive_intelligent_tiering_enabled  = true # Auto-optimize storage costs

# ============================================================
# VPC & NETWORK (PRODUCTION)
# ============================================================

vpc_cidr             = "10.0.0.0/16"
public_subnet_cidrs  = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnet_cidrs = ["10.0.10.0/24", "10.0.11.0/24"]
availability_zones   = ["us-east-1a", "us-east-1b"]

# VPC Endpoints: required for production security (private connections to AWS services)
enable_vpc_endpoints = true

# Development machine CIDR: MUST be empty in production (no dev access)
dev_machine_cidr = ""

# ============================================================
# ALPACA TRADING (PRODUCTION)
# ============================================================

# Paper trading: set to false for live trading when ready
alpaca_paper_trading = true                    # Keep in paper mode until system fully tested

# Alpaca API credentials: Set via TF_VAR_* environment variables (GitHub Actions secrets)
alpaca_api_key_id     = ""                     # Set via TF_VAR_alpaca_api_key_id
alpaca_api_secret_key = ""                     # Set via TF_VAR_alpaca_api_secret_key
alpaca_api_base_url   = "https://api.alpaca.markets"  # Live trading URL (when ready)

# ============================================================
# EXECUTION & DRY-RUN (PRODUCTION)
# ============================================================

execution_mode      = "auto"                   # Auto-execute trades
orchestrator_dry_run = false                   # Execute real trades
orchestrator_log_level = "warning"             # Reduce CloudWatch log costs

# ============================================================
# IAM & SECURITY (PRODUCTION)
# ============================================================

# Developer credential rotation: update when keys are rotated
developer_key_rotation_date = "2026-05-29"

# Secrets Manager rotation: 30 days (production standard)
secrets_rotation_days = 30

# PostgreSQL version: maintain latest stable
postgres_major_version = "16"

# ============================================================
# AWS BATCH (HEAVY LOADER COMPUTE)
# ============================================================

batch_max_vcpus = 256                          # Allow parallel loader execution
batch_instance_types = [
  "c6i.xlarge", "c6i.2xlarge", "c7i.xlarge", "c7i.2xlarge",
  "m6i.xlarge", "m6i.2xlarge", "m7i.xlarge", "m7i.2xlarge",
  "r6i.xlarge", "r7i.xlarge"
]
batch_spot_bid_percentage = 70                 # 70% of on-demand price = 30% savings
batch_vcpus   = 4
batch_memory_mb = 4096

# ============================================================
# ECR CONTAINER REGISTRY (PRODUCTION)
# ============================================================

ecr_image_scan_enabled = true                  # Scan images for vulnerabilities
ecr_image_tag_mutability = "IMMUTABLE"         # Prevent accidental tag overwrites

# ============================================================
# TAGS & METADATA (PRODUCTION)
# ============================================================

common_tags = {
  Project     = "algo"
  Environment = "prod"
  ManagedBy   = "Terraform"
  Compliance  = "SOC2"
  BackupPolicy = "Daily"
}
