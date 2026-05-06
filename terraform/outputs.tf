# ============================================================
# Outputs - Exported values for reference and integration
# ============================================================

# Bootstrap Outputs
output "oidc_provider_arn" {
  description = "ARN of the OIDC provider for GitHub Actions"
  value       = var.deploy_bootstrap ? module.bootstrap[0].oidc_provider_arn : null
}

output "github_deploy_role_arn" {
  description = "ARN of the GitHub Actions deploy role"
  value       = var.deploy_bootstrap ? module.bootstrap[0].github_deploy_role_arn : null
}

# Core Outputs
output "vpc_id" {
  description = "VPC ID"
  value       = var.deploy_core ? module.core[0].vpc_id : null
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = var.deploy_core ? module.core[0].public_subnet_ids : null
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = var.deploy_core ? module.core[0].private_subnet_ids : null
}

output "ecr_repository_uri" {
  description = "ECR repository URI"
  value       = var.deploy_core ? module.core[0].ecr_repository_uri : null
}

output "cf_templates_bucket_name" {
  description = "CloudFormation templates bucket name"
  value       = var.deploy_core ? module.core[0].cf_templates_bucket_name : null
}

output "code_bucket_name" {
  description = "Code bucket name"
  value       = var.deploy_core ? module.core[0].code_bucket_name : null
}

output "algo_artifacts_bucket_name" {
  description = "Algo artifacts bucket name"
  value       = var.deploy_core ? module.core[0].algo_artifacts_bucket_name : null
}

# Data Infrastructure Outputs
output "db_endpoint" {
  description = "RDS database endpoint"
  value       = var.deploy_data_infrastructure ? module.data_infrastructure[0].db_endpoint : null
  sensitive   = true
}

output "db_port" {
  description = "RDS database port"
  value       = var.deploy_data_infrastructure ? module.data_infrastructure[0].db_port : null
}

output "db_name" {
  description = "RDS database name"
  value       = var.deploy_data_infrastructure ? module.data_infrastructure[0].db_name : null
}

output "db_secret_arn" {
  description = "ARN of RDS secret in Secrets Manager"
  value       = var.deploy_data_infrastructure ? module.data_infrastructure[0].db_secret_arn : null
  sensitive   = true
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = var.deploy_data_infrastructure ? module.data_infrastructure[0].ecs_cluster_name : null
}

output "ecs_cluster_arn" {
  description = "ECS cluster ARN"
  value       = var.deploy_data_infrastructure ? module.data_infrastructure[0].ecs_cluster_arn : null
}

# Webapp Outputs
output "api_endpoint" {
  description = "API Gateway endpoint URL"
  value       = var.deploy_webapp ? module.webapp[0].api_endpoint : null
}

output "cloudfront_domain" {
  description = "CloudFront distribution domain name"
  value       = var.deploy_webapp ? module.webapp[0].cloudfront_domain : null
}

output "website_url" {
  description = "Website URL"
  value       = var.deploy_webapp ? module.webapp[0].website_url : null
}

# Algo Outputs
output "algo_lambda_arn" {
  description = "Algorithm orchestrator Lambda ARN"
  value       = var.deploy_algo ? module.algo[0].lambda_arn : null
}

output "algo_schedule_arn" {
  description = "Algorithm scheduler EventBridge rule ARN"
  value       = var.deploy_algo ? module.algo[0].schedule_arn : null
}
