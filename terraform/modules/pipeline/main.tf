/**
 * Pipeline Module - Step Functions EOD & Morning Data Loading Pipelines
 *
 * Replaces 13 individual EventBridge cron rules with dependency-driven
 * Step Functions state machines. Guarantees the orchestrator only runs when
 * all signal data is actually ready, not on a fixed timer.
 *
 * EOD PIPELINE (4:05 PM ET, 6h max execution):
 *   stock_symbols (10 min, 600s timeout)
 *     → stock_prices_daily (1.5-2h expected, 6h timeout = 21600s)
 *       → [parallel] technical_data_daily (90 min expected, 3h timeout = 10800s)
 *                  + market_health_daily (20 min expected, 20 min timeout = 1200s)
 *         → trend_template_data (30 min expected, 90 min timeout = 5400s)
 *           → buy_sell_daily (30 min expected, 90 min timeout = 5400s)
 *             → signal_quality_scores (15 min expected, 2h timeout = 7200s)
 *               → algo_metrics_daily (12 min expected, 2h timeout = 7200s)
 *                 → swing_trader_scores (30+ min expected, 2h timeout = 7200s)
 *                   → sector_ranking (15 min expected, 15 min timeout = 900s)
 *                     → algo_orchestrator dry-run (20 min expected, 20 min timeout = 1200s)
 *
 * MORNING PIPELINE (2:15 AM ET, 5.5h max execution):
 *   stock_prices_daily (daily only, 15 min expected, 75 min timeout = 4500s)
 *     → [parallel] technical_data_daily (90 min expected, 90 min timeout = 5400s)
 *                + market_health_daily (20 min expected, 20 min timeout = 1200s)
 *       → buy_sell_daily (30 min expected, 45 min timeout = 2700s)
 *         → [parallel] signal_quality_scores (15 min expected, 45 min timeout = 2700s)
 *                    + swing_trader_scores (30+ min expected, 45 min timeout = 2700s)
 *           → sector_ranking (15 min expected, 15 min timeout = 900s)
 *
 * TIMEOUT STRATEGY: Expected + 2-3x safety margin to catch slow queries without being excessive.
 * - Fail fast on real failures (RDS unavailable, API errors) within 2-3x expected time
 * - Don't mask failures with 8-10h timeouts (previous anti-pattern)
 * - Monitor CloudWatch alarms if pipelines approach >80% of timeout (slow queries)
 * - If consistently slow, check: RDS CPU/connections, yfinance API status, network latency
 */

locals {
  # Network config injected into every ECS task launched by Step Functions
  network_config = {
    AwsvpcConfiguration = {
      Subnets        = var.private_subnet_ids
      SecurityGroups = [var.ecs_tasks_sg_id]
      AssignPublicIp = "DISABLED"
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
        Sid      = "InvokeOrchestratorECS"
        Effect   = "Allow"
        Action   = "ecs:RunTask"
        Resource = var.algo_orchestrator_task_definition_arn
      },
      {
        # Required for LogXxxFailure states that invoke the loader-failure-handler Lambda
        # directly (Resource = var.loader_failure_handler_arn in state machine definition).
        # The aws_lambda_permission resource-based policy allows states.amazonaws.com but
        # the execution role identity also needs lambda:InvokeFunction.
        Sid      = "InvokeFailureHandler"
        Effect   = "Allow"
        Action   = "lambda:InvokeFunction"
        Resource = var.loader_failure_handler_arn
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
  retention_in_days = var.cloudwatch_log_retention_days
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
    level                  = "ALL"
  }

  definition = jsonencode({
    Comment = "EOD data loading pipeline: symbols → prices → technicals → scores → signals → orchestrator"
    StartAt = "CheckTradingDay"

    States = {
      # ── Pre-flight: Skip pipeline on non-trading days (weekends, holidays) ──
      CheckTradingDay = {
        Type = "Pass"
        Parameters = {
          "today.$" = "$$.State.EnteredTime"
        }
        Next    = "StockSymbols"
        Comment = "On non-trading days (weekends/holidays), EventBridge won't trigger. If it does, pipeline succeeds harmlessly."
      }

      # ── Step 0: Load reference data (symbols) first ──────────
      # Must run before prices to ensure new symbols are included
      StockSymbols = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 600
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["stock_symbols"]
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
          Next        = "LogSymbolLoadFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "EodBulkPrices"
      }

      LogSymbolLoadFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "stock_symbols"
          "error.$"         = "$.loaderError.Error"
          "error_message.$" = "$.loaderError.Cause"
        }
        ResultPath = "$.failureLog"
        Retry = [{
          ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.Unknown"]
          IntervalSeconds = 2
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "EodBulkPrices"
          ResultPath  = "$.logError"
        }]
        Next = "EodBulkPrices"
      }

      # ── Step 1: Load today's close prices for all 5000+ symbols ──────────
      # CRITICAL LOADER (FAIL-CLOSED): Must succeed or entire pipeline halts.
      # parallelism=1, batch=100, cpu=2048: ~5.5min expected (serial execution to prevent rate limiting)
      # Timeout hierarchy: ECS container timeout (25200=7h) < Step Functions state timeout (21600=6h)
      #
      # ISSUE #1 FIX: Removed graceful degradation. If stock_prices_daily fails after retries,
      # the entire pipeline halts loudly so we know about the failure and can fix it,
      # rather than masking it and proceeding with stale data.
      #
      # Root causes addressed in production:
      # - yfinance rate limiting: Reduced parallelism from 6 to 1 (serial execution)
      # - RDS pool exhaustion: Enabled RDS Proxy (multiplexes 24 loaders → 20-30 connections)
      # - Market close data lag: Market close polling added (15s timeouts, rapid checks)
      EodBulkPrices = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 21600
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["stock_prices_daily"]
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
          Next        = "LogPriceLoadFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "ParallelTechnicals"
      }

      LogPriceLoadFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name        = "stock_prices_daily"
          "error.$"          = "$.loaderError.Error"
          "error_message.$"  = "$.loaderError.Cause"
          is_critical_loader = true
        }
        ResultPath = "$.failureLog"
        Retry = [{
          ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.Unknown"]
          IntervalSeconds = 2
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "PriceLoadFailureHalt"
          ResultPath  = "$.handlerError"
        }]
        Next = "PriceLoadFailureHalt"
      }

      # Fail-closed terminal state: pipeline halts when critical loader fails
      PriceLoadFailureHalt = {
        Type  = "Fail"
        Error = "CRITICAL_LOADER_FAILURE"
        Cause = "stock_prices_daily failed after retries. Pipeline halted to prevent trading on stale data. Check CloudWatch logs for details."
      }

      # ── Step 2: Technical indicators + market health (both read price_daily) ─
      ParallelTechnicals = {
        Type = "Parallel"
        Branches = [
          {
            StartAt = "TechnicalDataDaily"
            States = {
              TechnicalDataDaily = {
                Type           = "Task"
                Resource       = "arn:aws:states:::ecs:runTask.sync"
                TimeoutSeconds = 10800
                Parameters = {
                  Cluster              = var.ecs_cluster_arn
                  LaunchType           = "FARGATE"
                  TaskDefinition       = var.loader_task_definition_arns["technical_data_daily"]
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
            StartAt = "MarketHealthDaily"
            States = {
              MarketHealthDaily = {
                Type           = "Task"
                Resource       = "arn:aws:states:::ecs:runTask.sync"
                TimeoutSeconds = 1200
                Parameters = {
                  Cluster              = var.ecs_cluster_arn
                  LaunchType           = "FARGATE"
                  TaskDefinition       = var.loader_task_definition_arns["market_health_daily"]
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
        ResultPath = null
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogLoaderFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "ParallelEnrichment"
      }

      # FIXED Issue #4: Log loader failures and continue with available data (graceful degradation)
      LogLoaderFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "parallel_technicals"
          "error.$"         = "$.loaderError.Error"
          "error_message.$" = "$.loaderError.Cause"
        }
        ResultPath = "$.failureLog"
        Retry = [{
          ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.Unknown"]
          IntervalSeconds = 2
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "ParallelEnrichment"
          ResultPath  = "$.logError"
        }]
        Next = "ParallelEnrichment"
      }

      # ── Step 3: Parallel enrichment (trend template only — stock_scores moved after signals) ────────
      # FIXED Issue #2: Task definition timeout increased from 2700s to 5400s to match SF timeout
      # FIXED Issue #4b: Added ResultPath = null to discard parallel output and preserve original input
      ParallelEnrichment = {
        Type = "Parallel"
        Branches = [
          {
            StartAt = "TrendTemplate"
            States = {
              TrendTemplate = {
                Type           = "Task"
                Resource       = "arn:aws:states:::ecs:runTask.sync"
                TimeoutSeconds = 5400
                Parameters = {
                  Cluster              = var.ecs_cluster_arn
                  LaunchType           = "FARGATE"
                  TaskDefinition       = var.loader_task_definition_arns["trend_template_data"]
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
        ResultPath = null
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogEnrichmentFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "SignalGeneration"
      }

      LogEnrichmentFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "parallel_enrichment"
          "error.$"         = "$.loaderError.Error"
          "error_message.$" = "$.loaderError.Cause"
        }
        ResultPath = "$.failureLog"
        Retry = [{
          ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.Unknown"]
          IntervalSeconds = 2
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "SignalGeneration"
          ResultPath  = "$.logError"
        }]
        Next = "SignalGeneration"
      }

      # ── Step 5: Generate daily signals ──────────────────────────
      # parallelism=4: ~8 min expected, 1.5h timeout for safety.
      # FIXED Issue #4: Graceful degradation — if signals fail, continue with available data
      SignalGeneration = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 5400
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["buy_sell_daily"]
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
          Next        = "LogSignalGenerationFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "SignalQualityScores"
      }

      LogSignalGenerationFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "buy_sell_daily"
          "error.$"         = "$.loaderError.Error"
          "error_message.$" = "$.loaderError.Cause"
        }
        ResultPath = "$.failureLog"
        Retry = [{
          ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.Unknown"]
          IntervalSeconds = 2
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "SignalQualityScores"
          ResultPath  = "$.logError"
        }]
        Next = "SignalQualityScores"
      }

      # ── Step 6: Signal quality scores (depends on signals_daily populating buy_sell_daily) ──
      # parallelism=8: ~15 min expected, 2h timeout ensures full dataset processing.
      # FIXED Issue #4: Graceful degradation — if quality scoring fails, continue with available data
      # FIXED 2026-06-02: Increased parallelism 4→8, timeout 3600→7200 to handle full 10k+ symbol dataset
      SignalQualityScores = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 7200
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["signal_quality_scores"]
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
          Next        = "LogQualityScoresFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "AlgoMetrics"
      }

      LogQualityScoresFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "signal_quality_scores"
          "error.$"         = "$.loaderError.Error"
          "error_message.$" = "$.loaderError.Cause"
        }
        ResultPath = "$.failureLog"
        Retry = [{
          ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.Unknown"]
          IntervalSeconds = 2
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "AlgoMetrics"
          ResultPath  = "$.logError"
        }]
        Next = "AlgoMetrics"
      }

      # ── Step 7: Summarize signal quality metrics ──────────────────────────
      # parallelism=4: ~12 min expected, 2h timeout for safety.
      # FIXED Issue #4: Graceful degradation — if metrics fail, continue with available data
      AlgoMetrics = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 7200
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["algo_metrics_daily"]
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
          Next        = "LogMetricsFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "SwingScores"
      }

      LogMetricsFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "algo_metrics_daily"
          "error.$"         = "$.loaderError.Error"
          "error_message.$" = "$.loaderError.Cause"
        }
        ResultPath = "$.failureLog"
        Retry = [{
          ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.Unknown"]
          IntervalSeconds = 2
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "SwingScores"
          ResultPath  = "$.logError"
        }]
        Next = "SwingScores"
      }

      # ── Step 8: Swing trader scores (depends on signals + metrics) ───────
      # FIXED Issue #4: Graceful degradation — if scoring fails, continue with available data
      # FIXED 2026-06-02: Increased parallelism 4→8, timeout 3600→7200 to handle full 10k+ symbol dataset
      # 5000+ symbols at parallelism=8 with DB joins can take 30+ min under RDS load.
      SwingScores = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 7200
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["swing_trader_scores"]
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
          Next        = "LogSwingScoresFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "SectorRanking"
      }

      LogSwingScoresFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name        = "swing_trader_scores"
          "error.$"          = "$.loaderError.Error"
          "error_message.$"  = "$.loaderError.Cause"
          is_critical_loader = true
        }
        ResultPath = "$.failureLog"
        Retry = [{
          ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.Unknown"]
          IntervalSeconds = 2
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "SwingScoresFailureHalt"
          ResultPath  = "$.handlerError"
        }]
        Next = "SwingScoresFailureHalt"
      }

      # Fail-closed terminal state: pipeline halts when swing_trader_scores fails
      SwingScoresFailureHalt = {
        Type  = "Fail"
        Error = "CRITICAL_LOADER_FAILURE"
        Cause = "swing_trader_scores failed after retries. Pipeline halted because signals cannot be generated without trader scores. Check CloudWatch logs for details."
      }

      # ── Step 8c: Sector ranking (depends on stock_scores) ──────────────
      # CRITICAL: Must run before orchestrator to ensure Phase 3 and Phase 5 have current sector data.
      # Runs after swing_trader_scores completes. Timeout 900 seconds (15 minutes).
      SectorRanking = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 900
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["sector_ranking"]
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
          Next        = "LogSectorRankingFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "DataPatrol"
      }

      LogSectorRankingFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "sector_ranking"
          "error.$"         = "$.loaderError.Error"
          "error_message.$" = "$.loaderError.Cause"
        }
        ResultPath = "$.failureLog"
        Retry = [{
          ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.Unknown"]
          IntervalSeconds = 2
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "DataPatrol"
          ResultPath  = "$.logError"
        }]
        Next = "DataPatrol"
      }

      # ── Step 8b: Data patrol — validates data quality before orchestrator runs ──
      # Runs algo/algo_data_patrol.py, writes findings to data_patrol_log.
      # Orchestrator Phase 1 reads data_patrol_log; CRITICAL findings block trading.
      # Fail-open: if patrol itself errors, pipeline continues (Phase 1 passes vacuously).
      DataPatrol = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 600
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.patrol_task_definition_arn
          NetworkConfiguration = local.network_config
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 1
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogPatrolFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "TriggerOrchestrator"
      }

      LogPatrolFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "data_patrol"
          "error.$"         = "$.loaderError.Error"
          "error_message.$" = "$.loaderError.Cause"
        }
        ResultPath = "$.failureLog"
        Retry = [{
          ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.Unknown"]
          IntervalSeconds = 2
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "TriggerOrchestrator"
          ResultPath  = "$.logError"
        }]
        Next = "TriggerOrchestrator"
      }

      # ── Step 9: Validate pipeline completion (dry-run only) ──────────────
      # The Lambda orchestrator (EventBridge at 9:30 AM ET) is the trading trigger.
      # This ECS step runs dry_run=true: validates all data loaded, logs phase results,
      # but does NOT place orders. Prevents double-execution vs. the 9:30 AM Lambda.
      # FIXED Issue #15: Container overrides are intentionally STATIC for EOD pipeline
      # (execution_mode=paper, dry_run=true). Dynamic overrides not needed since this
      # is always a dry-run validation step, not a trading decision step.
      # FIXED Issue #4: Graceful degradation — if validation fails, pipeline succeeds anyway
      # (actual trading logic runs at 9:30 AM Lambda, this is just an early check)
      TriggerOrchestrator = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1200
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.algo_orchestrator_task_definition_arn
          NetworkConfiguration = local.network_config
          Overrides = {
            ContainerOverrides = [{
              Name = var.algo_orchestrator_container_name
              Environment = [
                # Base environment variables (required for orchestrator to run)
                {
                  Name  = "AWS_REGION"
                  Value = var.aws_region
                },
                {
                  Name  = "DB_HOST"
                  Value = var.db_host
                },
                {
                  Name  = "DB_PORT"
                  Value = tostring(var.db_port)
                },
                {
                  Name  = "DB_NAME"
                  Value = var.db_name
                },
                {
                  Name  = "ALPACA_PAPER_TRADING"
                  Value = tostring(var.alpaca_paper_trading)
                },
                {
                  Name  = "ORCHESTRATOR_LOG_LEVEL"
                  Value = var.orchestrator_log_level
                },
                {
                  Name  = "SEC_USER_AGENT"
                  Value = "algo-trading argeropolos@gmail.com"
                },
                # Overrides for EOD dry-run execution (these differ from regular execution)
                {
                  Name  = "ORCHESTRATOR_EXECUTION_MODE"
                  Value = "paper"
                },
                {
                  Name  = "ORCHESTRATOR_DRY_RUN"
                  Value = "true"
                },
                {
                  Name  = "ORCHESTRATOR_LOCK_TABLE"
                  Value = var.orchestrator_locks_table_name
                }
              ]
            }]
          }
        }
        Retry = [{
          ErrorEquals     = ["States.TaskFailed"]
          IntervalSeconds = 120
          MaxAttempts     = 1
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogOrchestratorFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "PipelineSuccess"
      }

      LogOrchestratorFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "algo_orchestrator_validation"
          "error.$"         = "$.loaderError.Error"
          "error_message.$" = "$.loaderError.Cause"
        }
        ResultPath = "$.failureLog"
        Retry = [{
          ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.Unknown"]
          IntervalSeconds = 2
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "PipelineSuccess"
          ResultPath  = "$.logError"
        }]
        Next = "PipelineSuccess"
      }

      PipelineSuccess = {
        Type = "Succeed"
      }
    }
  })

  tags = var.common_tags
}

# ============================================================
# Morning Prep Pipeline - Separate State Machine
# FIXED Issue #5: Split morning and EOD pipelines to prevent signal double-generation
# Morning (3:30 AM ET): Load prices → technicals + market health → signals → sector ranking
# FIXED Issue #13: Signals NOT generated here; orchestrator regenerates at 9:30 AM using fresh data
# FIXED 2026-06-02: Added market_health_daily to morning pipeline (was only in EOD).
# If EOD pipeline fails, market health data went stale; now refreshed daily at 3:30 AM.
# FIXED 2026-06-05: Added sector_ranking to morning pipeline to ensure Phase 3/5 have current sector data
# ============================================================

resource "aws_sfn_state_machine" "morning_prep_pipeline" {
  name     = "${var.project_name}-morning-prep-pipeline-${var.environment}"
  role_arn = aws_iam_role.sfn_pipeline.arn
  type     = "STANDARD"

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn_pipeline.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  definition = jsonencode({
    Comment = "Morning data prep: load fresh prices & technicals for 9:30 AM orchestrator run"
    StartAt = "CheckTradingDay"

    States = {
      CheckTradingDay = {
        Type = "Pass"
        Parameters = {
          "today.$" = "$$.State.EnteredTime"
        }
        Next = "MorningPrices"
      }

      # Load only daily prices (not weekly/monthly) for morning prep.
      # CRITICAL LOADER (FAIL-CLOSED): Must complete before technicals and signals can be computed.
      # Override LOADER_INTERVALS to "1d" so only daily prices are loaded (~15 min vs 6+ hours).
      # The full 1d/1wk/1mo load runs in the EOD pipeline at 4:05pm ET.
      # parallelism=1 (serial execution to prevent rate limiting, with 7.5h buffer before 9:30 AM deadline)
      MorningPrices = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 4500
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["stock_prices_daily"]
          NetworkConfiguration = local.network_config
          Overrides = {
            ContainerOverrides = [{
              Name = "${var.project_name}-stock_prices_daily"
              Environment = [
                { Name = "LOADER_INTERVALS", Value = "1d" },
                { Name = "LOADER_ASSET_CLASSES", Value = "stock" },
                { Name = "LOADER_PARALLELISM", Value = "1" }
              ]
            }]
          }
        }
        Retry = [
          {
            # Retry 1: Immediate (network/transient issues)
            ErrorEquals     = ["States.TaskStateAbortedError", "States.TaskStateTimedOut", "States.TaskFailed"]
            IntervalSeconds = 30
            MaxAttempts     = 1
            BackoffRate     = 1.0
          },
          {
            # Retry 2: Exponential backoff (rate limiting, cluster overload)
            ErrorEquals     = ["States.ALL"]
            IntervalSeconds = 90
            MaxAttempts     = 1
            BackoffRate     = 2.0
          }
        ]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogMorningPriceFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "MorningTechnicals"
      }

      LogMorningPriceFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name        = "stock_prices_daily (morning)"
          "error.$"          = "$.loaderError.Error"
          "error_message.$"  = "$.loaderError.Cause"
          is_critical_loader = true
        }
        ResultPath = "$.failureLog"
        Retry = [{
          ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.Unknown"]
          IntervalSeconds = 2
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "MorningPriceFailureHalt"
          ResultPath  = "$.handlerError"
        }]
        Next = "MorningPriceFailureHalt"
      }

      MorningPriceFailureHalt = {
        Type  = "Fail"
        Error = "CRITICAL_LOADER_FAILURE"
        Cause = "stock_prices_daily failed during morning prep. Pipeline halted to prevent trading on stale data. Morning prep needs 7.5 hours to complete before market open. Check CloudWatch logs for details (yfinance rate limiting, RDS issues, or network problems)."
      }

      MorningTechnicals = {
        Type = "Parallel"
        Branches = [
          {
            StartAt = "TechnicalsTask"
            States = {
              TechnicalsTask = {
                Type           = "Task"
                Resource       = "arn:aws:states:::ecs:runTask.sync"
                TimeoutSeconds = 5400
                Parameters = {
                  Cluster              = var.ecs_cluster_arn
                  LaunchType           = "FARGATE"
                  TaskDefinition       = var.loader_task_definition_arns["technical_data_daily"]
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
            StartAt = "MarketHealthTask"
            States = {
              MarketHealthTask = {
                Type           = "Task"
                Resource       = "arn:aws:states:::ecs:runTask.sync"
                TimeoutSeconds = 1200
                Parameters = {
                  Cluster              = var.ecs_cluster_arn
                  LaunchType           = "FARGATE"
                  TaskDefinition       = var.loader_task_definition_arns["market_health_daily"]
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
        ResultPath = null
        Catch = [{
          ErrorEquals = ["States.ALL"]
          # Fail-open: if technicals or market health fail, still regenerate signals
          # using prior data rather than hard-failing the entire morning prep.
          Next       = "MorningSignals"
          ResultPath = "$.technicalError"
        }]
        Next = "MorningSignals"
      }

      # ── Morning signal refresh (fail-open) ─────────────────────────────
      # Regenerates buy_sell_daily, signal_quality_scores, and swing_trader_scores
      # using today's fresh prices and technicals. Ensures the 9:30 AM Lambda
      # orchestrator always has up-to-date signals even if the EOD pipeline ran slow
      # or its signal steps didn't complete before midnight.
      # All signal steps are fail-open: failures don't block the pipeline.
      MorningSignals = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 2700
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["buy_sell_daily"]
          NetworkConfiguration = local.network_config
        }
        # Enhanced retry: 2 attempts with exponential backoff for resilience
        # Critical for signal generation: if it fails, all signals are stale
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 90
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "MorningSignalScores"
          ResultPath  = "$.signalError"
        }]
        Next = "MorningSignalScores"
      }

      # Parallel execution of quality scores and swing scores.
      # Both depend on buy_sell_daily completion but not on each other.
      # Reduces critical path from 180min to 60min for these two stages.
      MorningSignalScores = {
        Type = "Parallel"
        Branches = [
          {
            StartAt = "QualityScoresTask"
            States = {
              QualityScoresTask = {
                Type           = "Task"
                Resource       = "arn:aws:states:::ecs:runTask.sync"
                TimeoutSeconds = 2700
                Parameters = {
                  Cluster              = var.ecs_cluster_arn
                  LaunchType           = "FARGATE"
                  TaskDefinition       = var.loader_task_definition_arns["signal_quality_scores"]
                  NetworkConfiguration = local.network_config
                }
                # Enhanced retry: 2 attempts for critical signal scoring
                Retry = [{
                  ErrorEquals     = ["States.ALL"]
                  IntervalSeconds = 90
                  MaxAttempts     = 2
                  BackoffRate     = 2.0
                }]
                Catch = [{
                  ErrorEquals = ["States.ALL"]
                  Next        = "SkipQualityError"
                  ResultPath  = "$.qualityError"
                }]
                End = true
              }
              SkipQualityError = {
                Type = "Pass"
                End  = true
              }
            }
          },
          {
            StartAt = "SwingScoresTask"
            States = {
              SwingScoresTask = {
                Type           = "Task"
                Resource       = "arn:aws:states:::ecs:runTask.sync"
                TimeoutSeconds = 2700
                Parameters = {
                  Cluster              = var.ecs_cluster_arn
                  LaunchType           = "FARGATE"
                  TaskDefinition       = var.loader_task_definition_arns["swing_trader_scores"]
                  NetworkConfiguration = local.network_config
                }
                # Enhanced retry: 2 attempts for critical signal ranking
                Retry = [{
                  ErrorEquals     = ["States.ALL"]
                  IntervalSeconds = 90
                  MaxAttempts     = 2
                  BackoffRate     = 2.0
                }]
                Catch = [{
                  ErrorEquals = ["States.ALL"]
                  Next        = "SkipSwingError"
                  ResultPath  = "$.swingError"
                }]
                End = true
              }
              SkipSwingError = {
                Type = "Pass"
                End  = true
              }
            }
          }
        ]
        ResultPath = null
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "MorningSectorRanking"
          ResultPath  = "$.scoresError"
        }]
        Next = "MorningSectorRanking"
      }

      # ── Morning sector ranking (depends on swing_trader_scores) ──────────
      # CRITICAL: Must run before orchestrator to ensure Phase 3 and Phase 5 have current sector data.
      # Timeout 900 seconds (15 minutes) — same as EOD pipeline sector ranking.
      MorningSectorRanking = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 900
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["sector_ranking"]
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
          Next        = "LogMorningSectorRankingFailure"
          ResultPath  = "$.sectorError"
        }]
        Next = "MorningSuccess"
      }

      LogMorningSectorRankingFailure = {
        Type = "Pass"
        # Fail-open: if sector ranking fails, still complete morning prep
        # Phase 1 and Phase 5 will use previously cached sector data
        Next = "MorningSuccess"
      }

      MorningSuccess = {
        Type = "Succeed"
      }
    }
  })

  tags = var.common_tags
}

# CloudWatch Alarm: Morning pipeline not completed by 9:30 AM
resource "aws_cloudwatch_metric_alarm" "morning_pipeline_timeout_risk" {
  alarm_name          = "${var.project_name}-morning-pipeline-timeout-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionTime"
  namespace           = "AWS/States"
  period              = 60
  statistic           = "Maximum"
  threshold           = 16200 # 4.5 hours (270 min) — alert if running >270 min at 9:00 AM
  alarm_description   = "Morning pipeline running >4.5h (started 4:30 AM ET). May not complete before 9:30 AM orchestrator run."
  alarm_actions       = var.sns_alerts_enabled ? [var.sns_alert_topic_arn] : []

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.morning_prep_pipeline.arn
  }

  treat_missing_data = "notBreaching"

  tags = var.common_tags
}

resource "aws_lambda_permission" "loader_failure_handler_step_functions" {
  statement_id  = "AllowEODPipelineInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.loader_failure_handler_arn
  principal     = "states.amazonaws.com"
  source_arn    = aws_sfn_state_machine.eod_pipeline.arn
}

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

# IAM Role for EventBridge to invoke Lambda
resource "aws_iam_role" "eventbridge_lambda" {
  name = "${var.project_name}-eventbridge-lambda-role-${var.environment}"

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

resource "aws_iam_role_policy" "eventbridge_lambda" {
  name = "${var.project_name}-eventbridge-lambda-policy"
  role = aws_iam_role.eventbridge_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = "arn:aws:lambda:${var.aws_region}:${var.aws_account_id}:function:${var.project_name}-orchestrator-${var.environment}"
    }]
  })
}

# EventBridge Scheduler (timezone-aware): both pipelines use America/New_York so they
# fire at the correct wall-clock time year-round regardless of EST/EDT offset.
#
# Morning: 2:00 AM ET   — loads prices + technicals before market open (7h 30m before 9:30 AM, 210min buffer)
# EOD:     4:05 PM ET   — 5 min after market close, gives Alpaca time to settle prices

resource "aws_scheduler_schedule" "morning_pipeline_trigger" {
  name                         = "${var.project_name}-morning-pipeline-${var.environment}"
  description                  = "Morning data prep: load prices + technicals for market open (2:00 AM ET, provides 210min buffer before 9:30 AM)"
  schedule_expression          = "cron(0 2 ? * MON-FRI *)"
  schedule_expression_timezone = "America/New_York"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.morning_prep_pipeline.arn
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      execution_name = "morning-<aws.scheduler.execution-id>"
    })
  }
}

resource "aws_scheduler_schedule" "eod_pipeline_trigger" {
  name                         = "${var.project_name}-eod-pipeline-${var.environment}"
  description                  = "EOD pipeline: end-of-day analysis & swing scores (4:05 PM ET, 5 min after market close)"
  schedule_expression          = "cron(5 16 ? * MON-FRI *)"
  schedule_expression_timezone = "America/New_York"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.eod_pipeline.arn
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      execution_name = "eod-<aws.scheduler.execution-id>"
    })
  }
}

# ============================================================
# CloudWatch Alarms: Pipeline Execution & Timeout Monitoring
# ============================================================

# Alert if EOD pipeline execution fails
resource "aws_cloudwatch_metric_alarm" "eod_pipeline_failed" {
  count               = var.sns_alerts_enabled ? 1 : 0
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

# Alert if EOD pipeline takes >8 hours (approaching Step Functions timeout)
resource "aws_cloudwatch_metric_alarm" "eod_pipeline_slow" {
  count               = var.sns_alerts_enabled ? 1 : 0
  alarm_name          = "${var.project_name}-eod-pipeline-slow-${var.environment}"
  alarm_description   = "EOD pipeline running slow (>8h). May timeout or miss orchestrator window."
  namespace           = "AWS/States"
  metric_name         = "ExecutionTime"
  dimensions          = { StateMachineArn = aws_sfn_state_machine.eod_pipeline.arn }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 28800 # 8 hours
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = [var.sns_alert_topic_arn]
  treat_missing_data  = "notBreaching"
  tags                = var.common_tags
}

# Alert if morning pipeline takes >5 hours (approaching 9:30 AM orchestrator start)
resource "aws_cloudwatch_metric_alarm" "morning_pipeline_slow" {
  count               = var.sns_alerts_enabled ? 1 : 0
  alarm_name          = "${var.project_name}-morning-pipeline-slow-${var.environment}"
  alarm_description   = "Morning pipeline running slow (>5h). May not complete before 9:30 AM orchestrator."
  namespace           = "AWS/States"
  metric_name         = "ExecutionTime"
  dimensions          = { StateMachineArn = aws_sfn_state_machine.morning_prep_pipeline.arn }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 18000 # 5 hours
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = [var.sns_alert_topic_arn]
  treat_missing_data  = "notBreaching"
  tags                = var.common_tags
}


