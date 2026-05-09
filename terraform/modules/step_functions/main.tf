# ============================================================
# Step Functions Module - Massive Parallel Processing (1000x)
# ============================================================

# ============================================================
# 1. CloudWatch Log Group for Step Functions
# ============================================================

resource "aws_cloudwatch_log_group" "step_functions" {
  name              = "/aws/stepfunctions/${var.project_name}"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-stepfunctions-logs"
  })
}

# ============================================================
# 2. IAM Role for Step Functions Execution
# ============================================================

resource "aws_iam_role" "step_functions_role" {
  name = "${var.project_name}-stepfunctions-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "states.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-stepfunctions-role"
  })
}

# Allow Step Functions to invoke Lambda
resource "aws_iam_role_policy" "step_functions_lambda_policy" {
  name = "${var.project_name}-stepfunctions-lambda-policy"
  role = aws_iam_role.step_functions_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeLambda"
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = "${var.lambda_signal_worker_arn}*"
      },
      {
        Sid    = "WriteCloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups"
        ]
        Resource = "*"
      },
      {
        Sid    = "DynamoDBAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:GetItem",
          "dynamodb:Query"
        ]
        Resource = var.execution_tracker_table_arn
      }
    ]
  })
}

# ============================================================
# 3. Step Functions State Machine (Distributed Map)
# ============================================================

resource "aws_sfn_state_machine" "massive_parallel_signals" {
  name       = "${var.project_name}-massive-parallel-signals"
  role_arn   = aws_iam_role.step_functions_role.arn
  definition = jsonencode(local.state_machine_definition)

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.step_functions.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-stepfunctions-state-machine"
  })
}

# ============================================================
# 4. State Machine Definition with Distributed Map
# ============================================================

locals {
  state_machine_definition = {
    Comment = "Process 5000+ symbols in parallel using Distributed Map state"
    StartAt = "GetSymbolsList"
    States = {
      GetSymbolsList = {
        Type     = "Task"
        Resource = "arn:aws:states:::dynamodb:getItem"
        Parameters = {
          "TableName" = var.execution_tracker_table_name
          "Key" = {
            "execution_id" = {
              "S" = "$$.Execution.Id"
            }
          }
        }
        Next = "ProcessSymbolsParallel"
      }

      ProcessSymbolsParallel = {
        Type           = "Map"
        ItemsPath      = "$.symbols"
        MaxConcurrency = var.map_max_concurrency # Default: 1000 concurrent executions
        Next           = "AggregateResults"

        Iterator = {
          StartAt = "ProcessSymbol"
          States = {
            ProcessSymbol = {
              Type           = "Task"
              Resource       = "arn:aws:lambda:${var.aws_region}:${var.aws_account_id}:function:${var.lambda_signal_worker_name}"
              TimeoutSeconds = 60
              Retry = [
                {
                  ErrorEquals     = ["States.TaskFailed"]
                  IntervalSeconds = 2
                  MaxAttempts     = 3
                  BackoffRate     = 2.0
                }
              ]
              Catch = [
                {
                  ErrorEquals = ["States.ALL"]
                  Next        = "HandleSymbolError"
                }
              ]
              End = true
            }

            HandleSymbolError = {
              Type = "Pass"
              Parameters = {
                "symbol.$" = "$.symbol"
                "status"   = "error"
                "error.$"  = "$$.State.Cause"
              }
              End = true
            }
          }
        }
      }

      AggregateResults = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          "FunctionName" = var.lambda_results_aggregator_arn
          "Payload.$"    = "$"
        }
        Next = "UpdateExecutionTracker"
      }

      UpdateExecutionTracker = {
        Type     = "Task"
        Resource = "arn:aws:states:::dynamodb:updateItem"
        Parameters = {
          "TableName" = var.execution_tracker_table_name
          "Key" = {
            "execution_id" = {
              "S" = "$$.Execution.Id"
            }
          }
          "UpdateExpression" = "SET execution_status = :status, completed_at = :timestamp, total_symbols_processed = :count"
          "ExpressionAttributeValues" = {
            ":status" = {
              "S" = "COMPLETED"
            }
            ":timestamp" = {
              "N" = "$$.State.EnteredTime"
            }
            ":count" = {
              "N.$" = "$.total_processed"
            }
          }
        }
        End = true
      }
    }
  }
}

# ============================================================
# 5. DynamoDB Table for Execution Tracking (Optional)
# ============================================================

resource "aws_dynamodb_table" "execution_tracker" {
  name         = "${var.project_name}-stepfunctions-tracker"
  billing_mode = "PAY_PER_REQUEST" # On-demand pricing (cheaper for bursty workloads)
  hash_key     = "execution_id"
  stream_specification {
    stream_view_type = "NEW_AND_OLD_IMAGES"
  }

  attribute {
    name = "execution_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-execution-tracker"
  })
}

# ============================================================
# 6. CloudWatch Dashboard for Execution Monitoring
# ============================================================

resource "aws_cloudwatch_dashboard" "step_functions_monitor" {
  dashboard_name = "${var.project_name}-stepfunctions-monitor"

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/States", "ExecutionTime", { stat = "Average" }],
            [".", "ExecutionsStarted", { stat = "Sum" }],
            [".", "ExecutionsFailed", { stat = "Sum" }],
            [".", "ExecutionsSucceeded", { stat = "Sum" }]
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "Step Functions Execution Metrics"
        }
      },
      {
        type = "log"
        properties = {
          query  = "fields @timestamp, @message | filter @message like /execution|error/ | stats count() as errors by bin(5m)"
          region = var.aws_region
          title  = "Execution Errors (5-min bins)"
        }
      }
    ]
  })
}

# ============================================================
# 7. EventBridge Rule for Step Functions Execution
# ============================================================

resource "aws_cloudwatch_event_rule" "signal_execution_scheduler" {
  name                = "${var.project_name}-signal-execution-scheduler"
  description         = "Trigger massive parallel signal processing at 5:30pm ET daily"
  schedule_expression = "cron(30 21 * * ? *)" # 5:30pm ET = 21:30 UTC
  is_enabled          = var.execution_schedule_enabled

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-signal-execution-scheduler"
  })
}

resource "aws_cloudwatch_event_target" "step_functions_target" {
  rule      = aws_cloudwatch_event_rule.signal_execution_scheduler.name
  target_id = "StepFunctionsExecution"
  arn       = aws_sfn_state_machine.massive_parallel_signals.arn
  role_arn  = aws_iam_role.eventbridge_stepfunctions_role.arn

  input = jsonencode({
    symbols       = []
    backfill_days = var.backfill_days
  })

  retry_policy {
    maximum_event_age      = 3600
    maximum_retry_attempts = 2
  }

  dead_letter_config {
    arn = var.dlq_arn
  }
}

# ============================================================
# 8. IAM Role for EventBridge to invoke Step Functions
# ============================================================

resource "aws_iam_role" "eventbridge_stepfunctions_role" {
  name = "${var.project_name}-eventbridge-stepfunctions-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy" "eventbridge_stepfunctions_policy" {
  name = "${var.project_name}-eventbridge-stepfunctions-policy"
  role = aws_iam_role.eventbridge_stepfunctions_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "states:StartExecution"
        ]
        Resource = aws_sfn_state_machine.massive_parallel_signals.arn
      }
    ]
  })
}
