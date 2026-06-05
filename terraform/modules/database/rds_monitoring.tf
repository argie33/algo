# ============================================================
# RDS Connection Pool Monitoring and Alerting
# ============================================================

# CloudWatch Alarm: RDS Connection Pool Early Warning (50 connections)
resource "aws_cloudwatch_metric_alarm" "rds_connection_warning" {
  alarm_name          = "${var.project_name}-rds-connection-warning-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2  # Alert after 10 minutes of sustained high load
  metric_name         = "DatabaseConnections"
  namespace           = "AWS/RDS"
  period              = 300  # 5-minute windows
  statistic           = "Maximum"
  threshold           = 50   # Early warning at 50 connections (1/10 of max 500)
  alarm_description   = "RDS connection pool usage reaching 50 connections. Monitor for potential contention."
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.identifier
  }

  alarm_actions = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-rds-connection-warning"
  })
}

# CloudWatch Alarm: RDS Connection Pool Critical (100 connections)
resource "aws_cloudwatch_metric_alarm" "rds_connection_critical" {
  alarm_name          = "${var.project_name}-rds-connection-critical-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1  # Alert immediately
  metric_name         = "DatabaseConnections"
  namespace           = "AWS/RDS"
  period              = 60  # 1-minute windows
  statistic           = "Maximum"
  threshold           = 100  # Critical alert at 100 connections (1/5 of max 500)
  alarm_description   = "RDS connection pool critical usage. Potential connection exhaustion risk."
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.identifier
  }

  alarm_actions = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-rds-connection-critical"
  })
}

# CloudWatch Alarm: RDS CPU Utilization (prevent cascading failures)
resource "aws_cloudwatch_metric_alarm" "rds_cpu_high" {
  alarm_name          = "${var.project_name}-rds-cpu-high-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 70  # Alert at 70% CPU
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

# CloudWatch Alarm: RDS Disk Queue Depth (I/O contention)
resource "aws_cloudwatch_metric_alarm" "rds_disk_queue_high" {
  alarm_name          = "${var.project_name}-rds-disk-queue-high-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2
  metric_name         = "DiskQueueDepth"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 5  # Alert if >5 I/O operations queued
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
