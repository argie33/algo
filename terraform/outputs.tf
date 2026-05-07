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
  value       = module.vpc.vpc_endpoint_ids
}

# ============================================================
# Storage Outputs
# ============================================================

output "storage_buckets" {
  description = "S3 bucket names"
  value = {
    code_bucket              = module.storage.code_bucket_name
    cf_templates_bucket      = module.storage.cf_templates_bucket_name
    lambda_artifacts_bucket  = module.storage.lambda_artifacts_bucket_name
    data_loading_bucket      = module.storage.data_loading_bucket_name
    log_archive_bucket       = module.storage.log_archive_bucket_name
    frontend_bucket          = module.storage.frontend_bucket_name
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

output "api_lambda_arn" {
  description = "API Lambda function ARN"
  value       = module.services.api_lambda_arn
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
# ============================================================

output "cognito_user_pool_id" {
  description = "Cognito user pool ID"
  value       = module.services.cognito_user_pool_id
}

output "cognito_client_id" {
  description = "Cognito app client ID"
  value       = module.services.cognito_client_id
}

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
# Deployment Info
# ============================================================

output "deployment_summary" {
  description = "Deployment summary"
  value = {
    project_name = var.project_name
    environment  = var.environment
    aws_region   = var.aws_region
    deployed_at  = timestamp()
  }
}
