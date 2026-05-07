# ============================================================
# Storage Module - Outputs
# ============================================================

# Code Bucket
output "code_bucket_name" {
  description = "Name of code bucket"
  value       = aws_s3_bucket.code.id
}

output "code_bucket_arn" {
  description = "ARN of code bucket"
  value       = aws_s3_bucket.code.arn
}

# CloudFormation Templates Bucket
output "cf_templates_bucket_name" {
  description = "Name of CloudFormation templates bucket"
  value       = aws_s3_bucket.cf_templates.id
}

output "cf_templates_bucket_arn" {
  description = "ARN of CloudFormation templates bucket"
  value       = aws_s3_bucket.cf_templates.arn
}

# Lambda Artifacts Bucket
output "lambda_artifacts_bucket_name" {
  description = "Name of Lambda artifacts bucket"
  value       = aws_s3_bucket.lambda_artifacts.id
}

output "lambda_artifacts_bucket_arn" {
  description = "ARN of Lambda artifacts bucket"
  value       = aws_s3_bucket.lambda_artifacts.arn
}

# Data Loading Bucket
output "data_loading_bucket_name" {
  description = "Name of data loading bucket (for loaders)"
  value       = aws_s3_bucket.data_loading.id
}

output "data_loading_bucket_arn" {
  description = "ARN of data loading bucket"
  value       = aws_s3_bucket.data_loading.arn
}

# Log Archive Bucket
output "log_archive_bucket_name" {
  description = "Name of log archive bucket"
  value       = aws_s3_bucket.log_archive.id
}

output "log_archive_bucket_arn" {
  description = "ARN of log archive bucket"
  value       = aws_s3_bucket.log_archive.arn
}

# Frontend Bucket
output "frontend_bucket_name" {
  description = "Name of frontend bucket"
  value       = aws_s3_bucket.frontend.id
}

output "frontend_bucket_arn" {
  description = "ARN of frontend bucket"
  value       = aws_s3_bucket.frontend.arn
}
