/**
 * Pipeline Module - Step Functions EOD Data Loading Pipeline
 *
 * Replaces 13 individual EventBridge cron rules with a dependency-driven
 * Step Functions state machine. Guarantees the orchestrator only runs when
 * all signal data is actually ready, not on a fixed timer.
 *
 * Pipeline DAG:
 *   eod_bulk_refresh
 *     → technicals_daily
 *       → [parallel] trend_template_data + stock_scores + factor_metrics
 *         → [parallel] signals_daily + signals_weekly + signals_monthly
 *                     + signals_etf_daily + signals_etf_weekly + signals_etf_monthly
 *           → algo_metrics_daily
 *             → Invoke algo orchestrator Lambda
 */

locals {
  # Network config injected into every ECS task launched by Step Functions
  network_config = {
    AwsvpcConfiguration = {
      Subnets         = var.private_subnet_ids
      SecurityGroups  = [var.ecs_tasks_sg_id]
      AssignPublicIp  = "DISABLED"
    }
  }
}

# ============================================================
# IAM Role for Step Functions
# ============================================================

resource "aws_iam_role" "sfn_pipeline" {
  name = "${var.project_name}-sfn-eod-pipeline-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "states.amazonaws.com" }
    }]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy" "sfn_pipeline" {
  name = "${var.project_name}-sfn-eod-pipeline-policy"
  role = aws_iam_role.sfn_pipeline.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "RunECSTasks"
        Effect = "Allow"
        Action = [
          "ecs:RunTask",
          "ecs:StopTask",
          "ecs:DescribeTasks"
        ]
        Resource = "*"
      },
      {
        Sid    = "PassRoleToECS"
        Effect = "Allow"
        Action = "iam:PassRole"
        Resource = [
          var.task_execution_role_arn,
          var.task_role_arn
        ]
      },
      {
        # Required for ecs:runTask.sync — Step Functions uses EventBridge internally
        Sid    = "EventBridgeSync"
        Effect = "Allow"
        Action = [
          "events:PutTargets",
          "events:PutRule",
          "events:DescribeRule"
        ]
        Resource = "arn:aws:events:${var.aws_region}:${var.aws_account_id}:rule/StepFunctionsGetEventsForECSTaskRule"
      },
      {
        Sid      = "InvokeOrchestratorLambda"
        Effect   = "Allow"
        Action   = "lambda:InvokeFunction"
        Resource = var.algo_lambda_arn
      },
      {
        Sid      = "PublishFailureAlert"
        Effect   = "Allow"
        Action   = "sns:Publish"
        Resource = var.sns_alert_topic_arn != "" ? var.sns_alert_topic_arn : "*"
      },
      {
        Sid    = "CloudWatchLogs"
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
      }
    ]
  })
}

# ============================================================
# CloudWatch Log Group for Step Functions execution history
# ============================================================

resource "aws_cloudwatch_log_group" "sfn_pipeline" {
  name              = "/aws/states/${var.project_name}-eod-pipeline-${var.environment}"
  retention_in_days = 30
  tags              = var.common_tags
}

# ============================================================
# Step Functions State Machine
# ============================================================

resource "aws_sfn_state_machine" "eod_pipeline" {
  name     = "${var.project_name}-eod-pipeline-${var.environment}"
  role_arn = aws_iam_role.sfn_pipeline.arn
  type     = "STANDARD"

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn_pipeline.arn}:*"
    include_execution_data = true
    level                  = "ERROR"
  }

  definition = jsonencode({
    Comment = "EOD data loading pipeline: prices → technicals → scores → signals → orchestrator"
    StartAt = "EodBulkPrices"

    States = {
      # ── Step 1: Load today's close prices for all 5000+ symbols ──────────
      EodBulkPrices = {
        Type     = "Task"
        Resource = "arn:aws:states:::ecs:runTask.sync"
        Parameters = {
          Cluster        = var.ecs_cluster_arn
          LaunchType     = "FARGATE"
          TaskDefinition = var.loader_task_definition_arns["eod_bulk_refresh"]
          NetworkConfiguration = local.network_config
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 120
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "PipelineFailed"
          ResultPath  = "$.error"
        }]
        Next = "TechnicalsDaily"
      }

      # ── Step 2: Compute RSI / MACD / ATR / ADX from today's prices ───────
      TechnicalsDaily = {
        Type     = "Task"
        Resource = "arn:aws:states:::ecs:runTask.sync"
        Parameters = {
          Cluster        = var.ecs_cluster_arn
          LaunchType     = "FARGATE"
          TaskDefinition = var.loader_task_definition_arns["technicals_daily"]
          NetworkConfiguration = local.network_config
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 120
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "PipelineFailed"
          ResultPath  = "$.error"
        }]
        Next = "ParallelEnrichment"
      }

      # ── Step 3: Parallel enrichment (all depend on technicals) ───────────
      ParallelEnrichment = {
        Type = "Parallel"
        Branches = [
          {
            StartAt = "TrendTemplate"
            States = {
              TrendTemplate = {
                Type     = "Task"
                Resource = "arn:aws:states:::ecs:runTask.sync"
                Parameters = {
                  Cluster        = var.ecs_cluster_arn
                  LaunchType     = "FARGATE"
                  TaskDefinition = var.loader_task_definition_arns["trend_template_data"]
                  NetworkConfiguration = local.network_config
                }
                Retry = [{
                  ErrorEquals     = ["States.ALL"]
                  IntervalSeconds = 60
                  MaxAttempts     = 2
                  BackoffRate     = 2.0
                }]
                End = true
              }
            }
          },
          {
            StartAt = "StockScores"
            States = {
              StockScores = {
                Type     = "Task"
                Resource = "arn:aws:states:::ecs:runTask.sync"
                Parameters = {
                  Cluster        = var.ecs_cluster_arn
                  LaunchType     = "FARGATE"
                  TaskDefinition = var.loader_task_definition_arns["stock_scores"]
                  NetworkConfiguration = local.network_config
                }
                Retry = [{
                  ErrorEquals     = ["States.ALL"]
                  IntervalSeconds = 60
                  MaxAttempts     = 2
                  BackoffRate     = 2.0
                }]
                End = true
              }
            }
          },
          {
            StartAt = "FactorMetrics"
            States = {
              FactorMetrics = {
                Type     = "Task"
                Resource = "arn:aws:states:::ecs:runTask.sync"
                Parameters = {
                  Cluster        = var.ecs_cluster_arn
                  LaunchType     = "FARGATE"
                  TaskDefinition = var.loader_task_definition_arns["factor_metrics"]
                  NetworkConfiguration = local.network_config
                }
                Retry = [{
                  ErrorEquals     = ["States.ALL"]
                  IntervalSeconds = 60
                  MaxAttempts     = 2
                  BackoffRate     = 2.0
                }]
                End = true
              }
            }
          }
        ]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "PipelineFailed"
          ResultPath  = "$.error"
        }]
        Next = "SignalGeneration"
      }

      # ── Step 4: Generate all signals in parallel ──────────────────────────
      SignalGeneration = {
        Type = "Parallel"
        Branches = [
          {
            StartAt = "SignalsDaily"
            States = {
              SignalsDaily = {
                Type     = "Task"
                Resource = "arn:aws:states:::ecs:runTask.sync"
                Parameters = {
                  Cluster        = var.ecs_cluster_arn
                  LaunchType     = "FARGATE"
                  TaskDefinition = var.loader_task_definition_arns["signals_daily"]
                  NetworkConfiguration = local.network_config
                }
                Retry = [{
                  ErrorEquals     = ["States.ALL"]
                  IntervalSeconds = 60
                  MaxAttempts     = 1
                  BackoffRate     = 2.0
                }]
                End = true
              }
            }
          },
          {
            StartAt = "SignalsWeekly"
            States = {
              SignalsWeekly = {
                Type     = "Task"
                Resource = "arn:aws:states:::ecs:runTask.sync"
                Parameters = {
                  Cluster        = var.ecs_cluster_arn
                  LaunchType     = "FARGATE"
                  TaskDefinition = var.loader_task_definition_arns["signals_weekly"]
                  NetworkConfiguration = local.network_config
                }
                Retry = [{
                  ErrorEquals     = ["States.ALL"]
                  IntervalSeconds = 60
                  MaxAttempts     = 1
                  BackoffRate     = 2.0
                }]
                End = true
              }
            }
          },
          {
            StartAt = "SignalsMonthly"
            States = {
              SignalsMonthly = {
                Type     = "Task"
                Resource = "arn:aws:states:::ecs:runTask.sync"
                Parameters = {
                  Cluster        = var.ecs_cluster_arn
                  LaunchType     = "FARGATE"
                  TaskDefinition = var.loader_task_definition_arns["signals_monthly"]
                  NetworkConfiguration = local.network_config
                }
                Retry = [{
                  ErrorEquals     = ["States.ALL"]
                  IntervalSeconds = 60
                  MaxAttempts     = 1
                  BackoffRate     = 2.0
                }]
                End = true
              }
            }
          },
          {
            StartAt = "SignalsEtfDaily"
            States = {
              SignalsEtfDaily = {
                Type     = "Task"
                Resource = "arn:aws:states:::ecs:runTask.sync"
                Parameters = {
                  Cluster        = var.ecs_cluster_arn
                  LaunchType     = "FARGATE"
                  TaskDefinition = var.loader_task_definition_arns["signals_etf_daily"]
                  NetworkConfiguration = local.network_config
                }
                Retry = [{
                  ErrorEquals     = ["States.ALL"]
                  IntervalSeconds = 60
                  MaxAttempts     = 1
                  BackoffRate     = 2.0
                }]
                End = true
              }
            }
          },
          {
            StartAt = "SignalsEtfWeekly"
            States = {
              SignalsEtfWeekly = {
                Type     = "Task"
                Resource = "arn:aws:states:::ecs:runTask.sync"
                Parameters = {
                  Cluster        = var.ecs_cluster_arn
                  LaunchType     = "FARGATE"
                  TaskDefinition = var.loader_task_definition_arns["signals_etf_weekly"]
                  NetworkConfiguration = local.network_config
                }
                Retry = [{
                  ErrorEquals     = ["States.ALL"]
                  IntervalSeconds = 60
                  MaxAttempts     = 1
                  BackoffRate     = 2.0
                }]
                End = true
              }
            }
          },
          {
            StartAt = "SignalsEtfMonthly"
            States = {
              SignalsEtfMonthly = {
                Type     = "Task"
                Resource = "arn:aws:states:::ecs:runTask.sync"
                Parameters = {
                  Cluster        = var.ecs_cluster_arn
                  LaunchType     = "FARGATE"
                  TaskDefinition = var.loader_task_definition_arns["signals_etf_monthly"]
                  NetworkConfiguration = local.network_config
                }
                Retry = [{
                  ErrorEquals     = ["States.ALL"]
                  IntervalSeconds = 60
                  MaxAttempts     = 1
                  BackoffRate     = 2.0
                }]
                End = true
              }
            }
          },
        ]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "PipelineFailed"
          ResultPath  = "$.error"
        }]
        Next = "AlgoMetrics"
      }

      # ── Step 5: Summarize signal quality metrics ──────────────────────────
      AlgoMetrics = {
        Type     = "Task"
        Resource = "arn:aws:states:::ecs:runTask.sync"
        Parameters = {
          Cluster        = var.ecs_cluster_arn
          LaunchType     = "FARGATE"
          TaskDefinition = var.loader_task_definition_arns["algo_metrics_daily"]
          NetworkConfiguration = local.network_config
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 60
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "PipelineFailed"
          ResultPath  = "$.error"
        }]
        Next = "TriggerOrchestrator"
      }

      # ── Step 6: Fire the trading orchestrator ─────────────────────────────
      TriggerOrchestrator = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = var.algo_lambda_arn
          Payload = {
            source   = "step-functions-eod-pipeline"
            run_date = "now"
          }
        }
        Retry = [{
          ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"]
          IntervalSeconds = 30
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "PipelineFailed"
          ResultPath  = "$.error"
        }]
        Next = "PipelineSuccess"
      }

      PipelineSuccess = {
        Type = "Succeed"
      }

      # ── Error handler: alert and fail ─────────────────────────────────────
      PipelineFailed = {
        Type     = "Task"
        Resource = "arn:aws:states:::sns:publish"
        Parameters = {
          TopicArn = var.sns_alert_topic_arn != "" ? var.sns_alert_topic_arn : "arn:aws:sns:${var.aws_region}:${var.aws_account_id}:placeholder"
          Message  = "EOD pipeline FAILED. Check Step Functions console: https://${var.aws_region}.console.aws.amazon.com/states/home?region=${var.aws_region}#/statemachines"
          Subject  = "ALERT: EOD Pipeline Failed - Orchestrator did not run"
        }
        Next = "PipelineFailedEnd"
      }

      PipelineFailedEnd = {
        Type  = "Fail"
        Error = "PipelineFailed"
        Cause = "One or more pipeline steps failed. Check Step Functions execution history."
      }
    }
  })

  tags = var.common_tags
}

# ============================================================
# EventBridge rule: fires at 4:05pm ET = 20:05 UTC Mon-Fri
# (5 min after market close gives Alpaca time to settle EOD prices)
# ============================================================

resource "aws_iam_role" "eventbridge_sfn" {
  name = "${var.project_name}-eventbridge-sfn-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "events.amazonaws.com" }
    }]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy" "eventbridge_sfn" {
  name = "${var.project_name}-eventbridge-sfn-policy"
  role = aws_iam_role.eventbridge_sfn.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "states:StartExecution"
      Resource = aws_sfn_state_machine.eod_pipeline.arn
    }]
  })
}

resource "aws_cloudwatch_event_rule" "eod_pipeline_trigger" {
  name                = "${var.project_name}-eod-pipeline-${var.environment}"
  description         = "EOD pipeline: prices → technicals → signals → orchestrator (4:05pm ET)"
  schedule_expression = "cron(5 20 ? * MON-FRI *)"
  state               = "ENABLED"
  tags                = var.common_tags
}

resource "aws_cloudwatch_event_target" "eod_pipeline" {
  rule     = aws_cloudwatch_event_rule.eod_pipeline_trigger.name
  arn      = aws_sfn_state_machine.eod_pipeline.arn
  role_arn = aws_iam_role.eventbridge_sfn.arn
}

# ============================================================
# CloudWatch Alarm: alert if pipeline execution fails
# ============================================================

resource "aws_cloudwatch_metric_alarm" "pipeline_failed" {
  count               = var.sns_alert_topic_arn != "" ? 1 : 0
  alarm_name          = "${var.project_name}-eod-pipeline-failed-${var.environment}"
  alarm_description   = "EOD data pipeline execution failed — orchestrator may not have run"
  namespace           = "AWS/States"
  metric_name         = "ExecutionsFailed"
  dimensions          = { StateMachineArn = aws_sfn_state_machine.eod_pipeline.arn }
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  alarm_actions       = [var.sns_alert_topic_arn]
  treat_missing_data  = "notBreaching"
  tags                = var.common_tags
}
