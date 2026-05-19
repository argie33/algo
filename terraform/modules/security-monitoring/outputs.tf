# ============================================================
# Security Monitoring Module - Outputs
# ============================================================

output "cloudtrail_bucket_arn" {
  description = "ARN of the CloudTrail S3 bucket"
  value       = var.cloudtrail_enabled ? aws_s3_bucket.cloudtrail_logs[0].arn : null
}

output "cloudtrail_trail_arn" {
  description = "ARN of the CloudTrail trail"
  value       = var.cloudtrail_enabled ? aws_cloudtrail.main[0].arn : null
}

output "guardduty_detector_id" {
  description = "ID of the GuardDuty detector"
  value       = var.guardduty_enabled ? aws_guardduty_detector.main[0].id : null
}

output "guardduty_detector_arn" {
  description = "ARN of the GuardDuty detector"
  value       = var.guardduty_enabled ? aws_guardduty_detector.main[0].arn : null
}

output "config_recorder_id" {
  description = "ID of the AWS Config recorder"
  value       = var.aws_config_enabled ? aws_config_configuration_recorder.main[0].id : null
}

output "config_bucket_arn" {
  description = "ARN of the Config S3 bucket"
  value       = var.aws_config_enabled ? aws_s3_bucket.config_bucket[0].arn : null
}

output "vpc_flow_logs_id" {
  description = "ID of the VPC Flow Logs"
  value       = var.vpc_flow_logs_enabled ? aws_flow_log.main[0].id : null
}

output "vpc_flow_logs_log_group" {
  description = "CloudWatch log group for VPC Flow Logs"
  value       = var.vpc_flow_logs_enabled ? aws_cloudwatch_log_group.vpc_flow_logs[0].name : null
}
