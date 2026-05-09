# ============================================================
# Monitoring Module - Outputs
# ============================================================

output "dashboard_name" {
  description = "Name of the CloudWatch dashboard"
  value       = aws_cloudwatch_dashboard.main.dashboard_name
}

output "dashboard_url" {
  description = "URL to access the CloudWatch dashboard"
  value       = "https://console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${aws_cloudwatch_dashboard.main.dashboard_name}"
}

output "api_unhealthy_alarm_name" {
  description = "Composite alarm name for API health status"
  value       = aws_cloudwatch_composite_alarm.api_unhealthy.alarm_name
}

output "database_unhealthy_alarm_name" {
  description = "Composite alarm name for database health status"
  value       = var.sns_alerts_enabled ? aws_cloudwatch_composite_alarm.database_unhealthy[0].alarm_name : null
}
