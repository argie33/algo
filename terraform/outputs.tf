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

output "rds_credentials_secret_name" {
  description = "Name of RDS credentials secret (for dynamic reference in workflows)"
  value       = module.database.rds_credentials_secret_name
  sensitive   = true
}

output "rds_password" {
  description = "RDS master password (from Terraform - used for GitHub Secrets)"
  value       = module.database.rds_password
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

# ============================================================
# Orchestrator Configuration
# ============================================================

output "alpaca_paper_trading" {
  description = "Whether Alpaca paper trading is enabled (false = live trading)"
  value       = var.alpaca_paper_trading
}

output "execution_mode" {
  description = "Orchestrator execution mode (auto, paper, or live)"
  value       = var.execution_mode
}

# ============================================================
# Critical Deployment Outputs (for GitHub Actions & CI)
# ============================================================

output "github_actions_role_arn" {
  description = "ARN of GitHub Actions OIDC role for deployments"
  value       = module.iam.github_actions_role_arn
}

output "rds_proxy_endpoint" {
  description = "RDS Proxy endpoint (Lambda connects here, not direct RDS)"
  value       = module.database.rds_proxy_endpoint
  sensitive   = true
}

output "api_gateway_stage_name" {
  description = "API Gateway stage name (for frontend .env)"
  value       = module.services.api_gateway_stage_name
}

output "algo_orchestrator_task_definition_arn" {
  description = "Algo orchestrator ECS task definition ARN"
  value       = module.loaders.algo_orchestrator_task_definition_arn
}

output "data_patrol_task_definition_arn" {
  description = "Data patrol ECS task definition ARN"
  value       = module.loaders.data_patrol_task_definition_arn
}

output "pipeline_state_machine_arn" {
  description = "Step Functions state machine ARN for EOD pipeline"
  value       = module.pipeline.state_machine_arn
}

output "aws_region" {
  description = "AWS region (for deployments & frontend config)"
  value       = var.aws_region
}

# ============================================================
# Lambda Layer Names (for GitHub Actions)
# ============================================================

output "algo_orchestrator_layer_name" {
  description = "Name for algo orchestrator Lambda layer"
  value       = module.services.algo_orchestrator_layer_name
}

output "api_lambda_layer_name" {
  description = "Name for API Lambda layer"
  value       = module.services.api_lambda_layer_name
}

# ============================================================
# Database Secrets Configuration
# ============================================================

output "rds_credentials_secret_name" {
  description = "Name of RDS credentials secret (for GitHub Actions)"
  value       = module.database.rds_credentials_secret_name
  sensitive   = true
}

# ============================================================
# Cognito Configuration
# ============================================================

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = module.cognito.user_pool_id
}

output "cognito_client_id" {
  description = "Cognito User Pool Client ID"
  value       = module.cognito.user_pool_client_id
}

output "cognito_domain_url" {
  description = "Cognito domain URL"
  value       = module.cognito.domain_url
}

# ============================================================
# Terraform Backend Configuration (for GitHub Actions)
# ============================================================

output "terraform_backend_bucket" {
  description = "S3 bucket for Terraform state"
  value       = module.services.terraform_backend_bucket
}

output "terraform_backend_key" {
  description = "S3 key path for Terraform state"
  value       = module.services.terraform_backend_key
}
