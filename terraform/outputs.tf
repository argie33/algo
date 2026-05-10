# ============================================================
# Root Module - Outputs
# ============================================================

# ============================================================
# Network Outputs
# ============================================================

output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = module.vpc.public_subnet_ids
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = module.vpc.private_subnet_ids
}

output "vpc_endpoint_ids" {
  description = "VPC endpoint IDs"
  value = {
    s3             = module.vpc.s3_endpoint_id
    dynamodb       = module.vpc.dynamodb_endpoint_id
    secretsmanager = module.vpc.secretsmanager_endpoint_id
    ecr_api        = module.vpc.ecr_api_endpoint_id
    ecr_dkr        = module.vpc.ecr_dkr_endpoint_id
    logs           = module.vpc.logs_endpoint_id
    sns            = module.vpc.sns_endpoint_id
  }
}

# ============================================================
# Storage Outputs
# ============================================================

output "storage_buckets" {
  description = "S3 bucket names"
  value = {
    code_bucket             = module.storage.code_bucket_name
    lambda_artifacts_bucket = module.storage.lambda_artifacts_bucket_name
    data_loading_bucket     = module.storage.data_loading_bucket_name
    log_archive_bucket      = module.storage.log_archive_bucket_name
    frontend_bucket         = module.storage.frontend_bucket_name
  }
}

# ============================================================
# Database Outputs
# ============================================================

output "rds_endpoint" {
  description = "RDS database endpoint (host:port)"
  value       = module.database.rds_endpoint
  sensitive   = true
}

output "rds_address" {
  description = "RDS database host address"
  value       = module.database.rds_address
  sensitive   = true
}

output "rds_port" {
  description = "RDS database port"
  value       = module.database.rds_port
}

output "rds_database_name" {
  description = "RDS database name"
  value       = module.database.rds_database_name
}

output "rds_credentials_secret_arn" {
  description = "ARN of RDS credentials secret"
  value       = module.database.rds_credentials_secret_arn
  sensitive   = true
}

# ============================================================
# Compute Outputs
# ============================================================

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = module.compute.ecs_cluster_name
}

output "ecs_cluster_arn" {
  description = "ECS cluster ARN"
  value       = module.compute.ecs_cluster_arn
}

output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = module.compute.ecr_repository_url
}

output "bastion_asg_name" {
  description = "Bastion Auto Scaling Group name"
  value       = module.compute.bastion_asg_name
}

output "bastion_shutdown_lambda_arn" {
  description = "Bastion shutdown Lambda ARN"
  value       = module.compute.bastion_shutdown_lambda_arn
}

# ============================================================
# API & Services Outputs
# ============================================================

output "api_url" {
  description = "API Gateway endpoint URL"
  value       = module.services.api_url
}

output "api_gateway_endpoint" {
  description = "API Gateway endpoint URL (for deployments)"
  value       = module.services.api_gateway_endpoint
}

output "api_lambda_arn" {
  description = "API Lambda function ARN"
  value       = module.services.api_lambda_arn
}

output "api_lambda_function_name" {
  description = "API Lambda function name"
  value       = module.services.api_lambda_function_name
}

output "algo_lambda_function_name" {
  description = "Algo Lambda function name"
  value       = module.services.algo_lambda_function_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = module.services.cloudfront_distribution_id
}

output "frontend_bucket_name" {
  description = "S3 bucket name for frontend assets"
  value       = module.storage.frontend_bucket_name
}

output "cloudfront_domain" {
  description = "CloudFront domain name"
  value       = module.services.cloudfront_domain_name
}

output "website_url" {
  description = "Frontend website URL"
  value       = module.services.website_url
}

# ============================================================
# Authentication Outputs
# NOTE: Cognito outputs now in cognito.tf (module outputs)
# See cognito.tf for: cognito_user_pool_id, cognito_user_pool_client_id, cognito_domain_url
# ============================================================

# ============================================================
# Algo Orchestrator Outputs
# ============================================================

output "algo_lambda_arn" {
  description = "Algo orchestrator Lambda ARN"
  value       = module.services.algo_lambda_arn
}

output "eventbridge_schedule_arn" {
  description = "Algo scheduler ARN"
  value       = module.services.eventbridge_schedule_arn
}

output "sns_alerts_topic_arn" {
  description = "SNS alerts topic ARN"
  value       = module.services.sns_alerts_topic_arn
}

# ============================================================
# Loaders Outputs
# ============================================================

output "loader_task_definitions" {
  description = "Task definition ARNs by loader name"
  value       = module.loaders.loader_task_definition_arns
}

output "all_loader_names" {
  description = "Configured loader names"
  value       = module.loaders.all_loader_names
}

# ============================================================
# Monitoring & Observability Outputs
# ============================================================

output "cloudwatch_dashboard_name" {
  description = "CloudWatch dashboard name for platform monitoring"
  value       = module.monitoring.dashboard_name
}

output "cloudwatch_dashboard_url" {
  description = "URL to access CloudWatch dashboard"
  value       = module.monitoring.dashboard_url
}

output "api_health_alarm_name" {
  description = "Composite alarm name for API health"
  value       = module.monitoring.api_unhealthy_alarm_name
}

output "database_health_alarm_name" {
  description = "Composite alarm name for database health"
  value       = module.monitoring.database_unhealthy_alarm_name
}

# ============================================================
# IAM Users & Credentials
# ============================================================

output "github_deployer_access_key_id" {
  description = "Access key ID for GitHub Actions deployer"
  value       = module.iam.github_deployer_access_key_id
  sensitive   = true
}

output "github_deployer_secret_access_key" {
  description = "Secret access key for GitHub Actions deployer"
  value       = module.iam.github_deployer_secret_access_key
  sensitive   = true
}

output "pipeline_user_name" {
  description = "Name of pipeline automation IAM user"
  value       = module.iam.pipeline_user_name
}

output "pipeline_access_key_id" {
  description = "Access key ID for pipeline automation"
  value       = module.iam.pipeline_access_key_id
  sensitive   = true
}

output "pipeline_secret_access_key" {
  description = "Secret access key for pipeline automation"
  value       = module.iam.pipeline_secret_access_key
  sensitive   = true
}

output "developer_user_name" {
  description = "Name of developer IAM user"
  value       = module.iam.developer_user_name
}

output "developer_console_login_url" {
  description = "AWS Console login URL for developer user"
  value       = module.iam.developer_console_login_url
}

# ============================================================
# Deployment Info
# ============================================================

output "deployment_summary" {
  description = "Deployment summary"
  value = {
    project_name  = var.project_name
    environment   = var.environment
    aws_region    = var.aws_region
    deployed_at   = timestamp()
    dashboard_url = module.monitoring.dashboard_url
  }
}
