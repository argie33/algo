# ============================================================
# Database Module - Outputs
# ============================================================

# RDS Instance
output "rds_identifier" {
  description = "RDS database instance identifier"
  value       = aws_db_instance.main.identifier
}

output "rds_endpoint" {
  description = "RDS database endpoint (host:port)"
  value       = aws_db_instance.main.endpoint
}

output "rds_address" {
  description = "RDS database address only"
  value       = aws_db_instance.main.address
}

output "rds_port" {
  description = "RDS database port"
  value       = aws_db_instance.main.port
}

output "rds_database_name" {
  description = "RDS database name"
  value       = aws_db_instance.main.db_name
}

output "rds_username" {
  description = "RDS master username"
  value       = aws_db_instance.main.username
  sensitive   = true
}

output "rds_arn" {
  description = "ARN of RDS instance"
  value       = aws_db_instance.main.arn
}

# Secrets
output "rds_credentials_secret_arn" {
  description = "ARN of RDS credentials secret"
  value       = aws_secretsmanager_secret.rds_credentials.arn
}

output "rds_credentials_secret_name" {
  description = "Name of RDS credentials secret"
  value       = aws_secretsmanager_secret.rds_credentials.name
}

output "email_config_secret_arn" {
  description = "ARN of email configuration secret"
  value       = aws_secretsmanager_secret.email_config.arn
}

output "email_config_secret_name" {
  description = "Name of email configuration secret"
  value       = aws_secretsmanager_secret.email_config.name
}

output "algo_secrets_arn" {
  description = "ARN of algo runtime secrets (Alpaca)"
  value       = aws_secretsmanager_secret.algo_secrets.arn
}

output "algo_secrets_name" {
  description = "Name of algo runtime secrets"
  value       = aws_secretsmanager_secret.algo_secrets.name
}

# Monitoring
output "rds_log_group_name" {
  description = "CloudWatch log group for RDS"
  value       = aws_cloudwatch_log_group.rds_postgresql.name
}
