# ============================================================
# RDS Connection Pool Monitoring and Alerting
# ============================================================

# Note: RDS connection pool alarms are configured in main.tf (aws_cloudwatch_metric_alarm.rds_connections)
# with configurable threshold via rds_connections_alarm_threshold variable (default 80 connections).
# This consolidates monitoring to a single configurable location.

# CloudWatch Alarm: RDS CPU Utilization (prevent cascading failures) — prod only
resource "aws_cloudwatch_metric_alarm" "rds_cpu_high" {
  count               = var.enable_resource_alarms ? 1 : 0
  alarm_name          = "${var.project_name}-rds-cpu-high-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 70 # Alert at 70% CPU
  alarm_description   = "RDS CPU utilization high. Queries may be slow or rate-limited."
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.identifier
  }

  alarm_actions = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-rds-cpu-high"
  })
}

# CloudWatch Alarm: RDS Disk Queue Depth (I/O contention) — prod only
resource "aws_cloudwatch_metric_alarm" "rds_disk_queue_high" {
  count               = var.enable_resource_alarms ? 1 : 0
  alarm_name          = "${var.project_name}-rds-disk-queue-high-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2
  metric_name         = "DiskQueueDepth"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 5 # Alert if >5 I/O operations queued
  alarm_description   = "RDS disk I/O queue depth high. Potential storage contention."
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.identifier
  }

  alarm_actions = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-rds-disk-queue-high"
  })
}

# CloudWatch Dashboard for RDS Monitoring
resource "aws_cloudwatch_dashboard" "rds_monitoring" {
  dashboard_name = "${var.project_name}-rds-monitoring-${var.environment}"

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/RDS", "DatabaseConnections", { stat = "Average", label = "Avg Connections" }],
            [".", ".", { stat = "Maximum", label = "Max Connections" }],
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "RDS Connection Pool Usage"
          yAxis = {
            left = {
              min = 0
              max = 500
            }
          }
          annotations = {
            horizontal = [
              {
                value = 50
                label = "Warning (50)"
                fill  = "above"
              },
              {
                value = 100
                label = "Critical (100)"
                fill  = "above"
              }
            ]
          }
          dimensions = {
            DBInstanceIdentifier = aws_db_instance.main.identifier
          }
        }
      },
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/RDS", "CPUUtilization", { stat = "Average" }],
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "RDS CPU Utilization"
          yAxis = {
            left = {
              min = 0
              max = 100
            }
          }
          dimensions = {
            DBInstanceIdentifier = aws_db_instance.main.identifier
          }
        }
      },
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/RDS", "DiskQueueDepth", { stat = "Average" }],
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "RDS Disk Queue Depth (I/O Contention)"
          dimensions = {
            DBInstanceIdentifier = aws_db_instance.main.identifier
          }
        }
      }
    ]
  })
}
