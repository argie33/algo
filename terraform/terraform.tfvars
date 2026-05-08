# ============================================================
# Terraform Variables - Default Values
# ============================================================

project_name           = "stocks"
environment            = "dev"
aws_region             = "us-east-1"
github_repository      = "argeropolos/algo"
github_ref_path        = "refs/heads/main"
notification_email     = "argeropolos@gmail.com"

# GitHub Actions will override rds_password with secrets.RDS_PASSWORD
# Environment variable: TF_VAR_rds_password

# ============================================================
# Network
# ============================================================

vpc_cidr               = "10.0.0.0/16"
public_subnet_cidrs    = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnet_cidrs   = ["10.0.10.0/24", "10.0.11.0/24"]
availability_zones     = ["us-east-1a", "us-east-1b"]
enable_vpc_endpoints   = true

# ============================================================
# Database
# ============================================================

rds_username           = "stocks"
rds_password           = "StocksProd2024!"  # REQUIRED: Change to a unique password for production
rds_db_name            = "stocks"
rds_instance_class     = "db.t3.micro"
rds_allocated_storage  = 61
rds_max_allocated_storage = 100
rds_backup_retention_period = 30
rds_backup_window      = "03:00-04:00"
rds_maintenance_window = "sun:04:00-sun:05:00"
enable_rds_cloudwatch_logs = true
rds_log_retention_days = 30

# ============================================================
# Compute
# ============================================================

ecs_cluster_name       = null  # auto-generated: stocks-dev-cluster
ecs_capacity_providers = ["FARGATE", "FARGATE_SPOT"]
ecs_default_capacity_provider_strategy = [
  { capacity_provider = "FARGATE_SPOT", weight = 4 },
  { capacity_provider = "FARGATE", weight = 1 }
]

bastion_enabled        = false
bastion_instance_type  = "t3.micro"
bastion_shutdown_hour_utc = 4
bastion_shutdown_minute_utc = 59

ecr_repository_name    = null  # auto-generated: stocks-dev-registry
ecr_image_scan_enabled = true
ecr_image_tag_mutability = "MUTABLE"

cloudwatch_log_retention_days = 30
enable_bastion_cloudwatch_logs = true

# ============================================================
# Storage
# ============================================================

enable_s3_versioning   = true
code_bucket_expiration_days = 90
data_bucket_expiration_days = 30

# ============================================================
# Lambda
# ============================================================

api_lambda_memory     = 256
api_lambda_timeout    = 30
api_lambda_ephemeral_storage = 512
api_lambda_code_file  = "../lambda_api.zip"

algo_lambda_memory    = 512
algo_lambda_timeout   = 300
algo_lambda_ephemeral_storage = 2048
algo_lambda_code_file = "../lambda_algo.zip"

# ============================================================
# API Gateway
# ============================================================

api_gateway_stage_name = "api"
api_gateway_logging_enabled = true
api_gateway_log_retention_days = 7

api_cors_allowed_origins = [
  "http://localhost:5173",
  "http://localhost:3000"
]

# ============================================================
# CloudFront
# ============================================================

cloudfront_enabled     = true
cloudfront_cache_default_ttl = 3600
cloudfront_cache_max_ttl = 86400
cloudfront_waf_enabled = false

# ============================================================
# Cognito
# ============================================================

cognito_enabled = true
cognito_user_pool_name = null  # auto-generated
cognito_password_min_length = 12
cognito_mfa_configuration = "OPTIONAL"
cognito_session_duration_hours = 24

# ============================================================
# Algo Orchestrator
# ============================================================

algo_schedule_expression = "cron(0 22 ? * MON-FRI *)"
algo_schedule_enabled = true
algo_schedule_timezone = "UTC"

# ============================================================
# SNS Alerts
# ============================================================

sns_alerts_enabled = true
sns_alert_email = "argeropolos@gmail.com"


# ============================================================
# Tags
# ============================================================

additional_tags = {
  "Cost-Center" = "engineering"
  "Owner"       = "claude"
  "Repository"  = "argeropolos/algo"
}
