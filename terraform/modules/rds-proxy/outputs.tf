output "proxy_endpoint" {
  description = "RDS Proxy endpoint (use this instead of RDS endpoint)"
  value       = aws_db_proxy.main.endpoint
}

output "proxy_arn" {
  description = "ARN of the RDS Proxy"
  value       = aws_db_proxy.main.arn
}

output "proxy_id" {
  description = "ID of the RDS Proxy"
  value       = aws_db_proxy.main.id
}

output "proxy_security_group_id" {
  description = "Security group ID of the RDS Proxy"
  value       = aws_security_group.proxy_sg.id
}

output "proxy_connection_string" {
  description = "PostgreSQL connection string for the proxy"
  value       = "postgresql://${var.project_name}-proxy:5432/stocks"
  sensitive   = false
}
