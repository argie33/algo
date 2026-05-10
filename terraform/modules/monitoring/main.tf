# ============================================================
# Monitoring Module - CloudWatch Dashboards & Insights
# ============================================================

# ============================================================
# Main Platform Dashboard
# ============================================================

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project_name}-${var.environment}"

  dashboard_body = jsonencode({
    widgets = [
      # ============================================================
      # API Lambda Metrics (Top Row)
      # ============================================================
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/Lambda", "Invocations", { stat = "Sum" }],
            [".", "Errors", { stat = "Sum" }],
            [".", "Duration", { stat = "Average" }],
            [".", "ConcurrentExecutions", { stat = "Maximum" }],
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "API Lambda - Invocations & Errors"
          yAxis = {
            left = {
              min = 0
            }
          }
          dimensions = {
            FunctionName = var.api_lambda_name
          }
        }
        width  = 12
        height = 6
        x      = 0
        y      = 0
      },

      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/Lambda", "Duration", { stat = "Average" }],
            ["...", { stat = "p99" }],
            ["...", { stat = "Maximum" }],
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "API Lambda - Response Time (Duration)"
          dimensions = {
            FunctionName = var.api_lambda_name
          }
        }
        width  = 12
        height = 6
        x      = 12
        y      = 0
      },

      # ============================================================
      # API Gateway Metrics
      # ============================================================
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/ApiGateway", "4XXError", { stat = "Sum" }],
            [".", "5XXError", { stat = "Sum" }],
            [".", "Count", { stat = "Sum" }],
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "API Gateway - Request Errors"
          dimensions = {
            ApiName = var.api_gateway_name
          }
        }
        width  = 12
        height = 6
        x      = 0
        y      = 6
      },

      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/ApiGateway", "Latency", { stat = "Average" }],
            ["...", { stat = "p99" }],
            ["...", { stat = "Maximum" }],
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "API Gateway - Latency"
          dimensions = {
            ApiName = var.api_gateway_name
          }
        }
        width  = 12
        height = 6
        x      = 12
        y      = 6
      },

      # ============================================================
      # Algo Orchestrator Lambda
      # ============================================================
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/Lambda", "Invocations", { stat = "Sum" }],
            [".", "Errors", { stat = "Sum" }],
            [".", "Duration", { stat = "Maximum" }],
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "Algo Lambda - Execution Status"
          dimensions = {
            FunctionName = var.algo_lambda_name
          }
        }
        width  = 12
        height = 6
        x      = 0
        y      = 12
      },

      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/Lambda", "Duration", { stat = "Maximum" }],
          ]
          period    = 300
          stat      = "Maximum"
          region    = var.aws_region
          title     = "Algo Lambda - Max Duration (4 min timeout)"
          threshold = 240000
          dimensions = {
            FunctionName = var.algo_lambda_name
          }
        }
        width  = 12
        height = 6
        x      = 12
        y      = 12
      },

      # ============================================================
      # Database Metrics
      # ============================================================
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/RDS", "CPUUtilization", { stat = "Average" }],
            [".", "DatabaseConnections", { stat = "Average" }],
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "RDS - CPU & Connections"
          yAxis = {
            left = {
              min = 0
              max = 100
            }
          }
          dimensions = {
            DBInstanceIdentifier = var.rds_identifier
          }
        }
        width  = 12
        height = 6
        x      = 0
        y      = 18
      },

      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/RDS", "FreeableMemory", { stat = "Average" }],
            [".", "FreeStorageSpace", { stat = "Average" }],
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "RDS - Memory & Storage"
          dimensions = {
            DBInstanceIdentifier = var.rds_identifier
          }
        }
        width  = 12
        height = 6
        x      = 12
        y      = 18
      },

      # ============================================================
      # CloudWatch Logs Insights (Recent Errors)
      # ============================================================
      {
        type = "log"
        properties = {
          query  = "fields @timestamp, @message, @duration | filter @message like /ERROR/ | stats count() as error_count by bin(5m)"
          region = var.aws_region
          title  = "Recent API Errors (5 min buckets)"
        }
        width  = 24
        height = 6
        x      = 0
        y      = 24
      },
    ]
  })
}

# ============================================================
# Composite Alarms
# ============================================================

# Composite alarm: API is unhealthy (5xx + errors)
# NOTE: Disabled - alarms referenced don't exist yet
# TODO: Re-enable once underlying CloudWatch alarms are created for API Gateway and Lambda
# This alarm will trigger when either 5xx errors OR Lambda errors exceed thresholds
# alarm_rule = "ALARM(${var.apigw_5xx_alarm_name}) OR ALARM(${var.api_lambda_errors_alarm_name})"
# For now, disabled to allow initial deployment without dependency on non-existent alarms
# resource "aws_cloudwatch_composite_alarm" "api_unhealthy" {
#   count = 0
# }

# Composite alarm: Database is unhealthy (high CPU + connection issues)
# NOTE: Disabled until RDS alarms are created
resource "aws_cloudwatch_composite_alarm" "database_unhealthy" {
  count             = 0 # Disabled - no RDS alarms yet
  alarm_name        = "${var.project_name}-database-unhealthy-${var.environment}"
  alarm_description = "Composite alarm: RDS CPU high OR connection errors detected"
  actions_enabled   = var.sns_alerts_topic_arn != "" ? true : false
  alarm_actions     = var.sns_alerts_topic_arn != "" ? [var.sns_alerts_topic_arn] : []

  alarm_rule = "OK"

  tags = var.common_tags
}
