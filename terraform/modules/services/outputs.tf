# ============================================================
# Services Module - Outputs
# ============================================================

output "lambda_layer_arn" {
  description = "ARN of the shared dependencies Lambda layer"
  value       = local.shared_deps_layer_arn
}

output "api_lambda_arn" {
  description = "ARN of the API Lambda function"
  value       = aws_lambda_function.api.arn
}

output "api_lambda_function_name" {
  description = "Name of the API Lambda function"
  value       = aws_lambda_function.api.function_name
}

output "api_gateway_id" {
  description = "ID of the API Gateway HTTP API"
  value       = aws_apigatewayv2_api.main.id
}

output "api_gateway_endpoint" {
  description = "Endpoint URL for API Gateway"
  value       = aws_apigatewayv2_api.main.api_endpoint
}

output "api_gateway_stage_name" {
  description = "API Gateway stage name"
  value       = aws_apigatewayv2_stage.api.name
}

output "api_url" {
  description = "Full URL for API Gateway (without path)"
  value       = aws_apigatewayv2_api.main.api_endpoint
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = var.cloudfront_enabled ? aws_cloudfront_distribution.frontend[0].id : null
}

output "cloudfront_domain_name" {
  description = "CloudFront domain name"
  value       = var.cloudfront_enabled ? aws_cloudfront_distribution.frontend[0].domain_name : null
}

output "cloudfront_distribution_arn" {
  description = "CloudFront distribution ARN"
  value       = var.cloudfront_enabled ? aws_cloudfront_distribution.frontend[0].arn : null
}

output "website_url" {
  description = "Full website URL via CloudFront"
  value       = var.cloudfront_enabled ? "https://${aws_cloudfront_distribution.frontend[0].domain_name}" : null
}

# Cognito outputs moved to root cognito.tf to avoid duplication
# See cognito.tf for: cognito_user_pool_id, cognito_user_pool_client_id, cognito_domain_url

output "algo_lambda_arn" {
  description = "ARN of the algo orchestrator Lambda function"
  value       = aws_lambda_function.algo.arn
}

output "algo_lambda_function_name" {
  description = "Name of the algo orchestrator Lambda function"
  value       = aws_lambda_function.algo.function_name
}

output "eventbridge_schedule_arn" {
  description = "ARN of the EventBridge Scheduler schedule for algo orchestrator"
  value       = var.algo_schedule_enabled ? aws_scheduler_schedule.algo_orchestrator[0].arn : null
}

output "eventbridge_schedule_name" {
  description = "Name of the EventBridge Scheduler schedule"
  value       = var.algo_schedule_enabled ? aws_scheduler_schedule.algo_orchestrator[0].name : null
}

output "sns_alerts_topic_arn" {
  description = "ARN of SNS topic for algo alerts"
  value       = var.sns_alerts_enabled ? aws_sns_topic.algo_alerts[0].arn : null
}

output "sns_alerts_topic_name" {
  description = "Name of SNS topic for algo alerts"
  value       = var.sns_alerts_enabled ? aws_sns_topic.algo_alerts[0].name : null
}

output "api_lambda_log_group_name" {
  description = "CloudWatch log group for API Lambda"
  value       = aws_cloudwatch_log_group.api_lambda.name
}

output "algo_lambda_log_group_name" {
  description = "CloudWatch log group for algo Lambda"
  value       = aws_cloudwatch_log_group.algo_lambda.name
}

output "api_gateway_log_group_name" {
  description = "CloudWatch log group for API Gateway"
  value       = var.api_gateway_logging_enabled ? aws_cloudwatch_log_group.api_gateway[0].name : null
}

# ============================================================
# Lambda Layer Names (for GitHub Actions deployment)
# ============================================================
# These names are published by GitHub Actions, not created by Terraform
# But we output the canonical names so deployment scripts use the same values

output "algo_orchestrator_layer_name" {
  description = "Name for algo orchestrator Lambda layer (published by GitHub Actions)"
  value       = "${var.project_name}-orchestrator-layer"
}

output "api_lambda_layer_name" {
  description = "Name for API Lambda layer (published by GitHub Actions)"
  value       = "${var.project_name}-api-layer"
}

# ============================================================
# Deployment Configuration (for GitHub Actions)
# ============================================================

output "terraform_backend_bucket" {
  description = "S3 bucket name for Terraform state"
  value       = "${var.project_name}-terraform-state"
}

output "terraform_backend_key" {
  description = "S3 key path for Terraform state"
  value       = "${var.project_name}/terraform.tfstate"
}

# ============================================================
# Loader Failure Handler Lambda (for Step Functions integration)
# ============================================================

output "loader_failure_handler_arn" {
  description = "ARN of the Lambda function for handling loader failures in Step Functions"
  value       = var.sns_alerts_enabled ? aws_lambda_function.loader_failure_handler[0].arn : ""
}
