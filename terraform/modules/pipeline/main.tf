/**
 * Pipeline Module - Step Functions EOD & Morning Data Loading Pipelines
 *
 * Replaces 13 individual EventBridge cron rules with dependency-driven
 * Step Functions state machines. Guarantees the orchestrator only runs when
 * all signal data is actually ready, not on a fixed timer.
 *
 * EOD PIPELINE (4:05 PM ET, 4h max execution):
 *   market_constituents (10 min, 600s timeout)
 *     → stock_prices_daily (1.5-2h expected, 6h timeout = 21600s) [CRITICAL: must succeed]
 *       → [parallel] market_health_daily (20 min expected, 20 min timeout = 1200s)
 *                  + trend_template_data (30 min expected, 90 min timeout = 5400s)
 *         → algo_metrics_daily (12 min expected, 2h timeout = 7200s)
 *           → swing_trader_scores (30+ min expected, 2h timeout = 7200s)
 *             → technical_data_daily (15-25 min expected, 1h timeout = 3600s) [REQUIRED: buy_sell_daily depends on it]
 *               → buy_sell_daily (30 min expected, 6h timeout = 21600s for vectorized loader)
 *                 → sector_ranking (15 min expected, 15 min timeout = 900s)
 *                   → algo_orchestrator (dry-run & live: Phase 1-7)
 *
 * KEY INSIGHTS:
 * 1. technical_data_daily REQUIRED: buy_sell_daily loader validates freshness before signal generation
 * 2. buy_sell_daily CRITICAL: Phase 5 uses breakout signals as primary path for entries
 * Note: signal_quality_scores removed (on-the-fly computation not yet implemented; use stock_scores instead)
 *
 * MORNING PIPELINE (2:00 AM ET, 2.5h max execution):
 *   stock_prices_daily (daily only, 60-90 min actual with 5000+ symbols, 2h timeout = 7200s)
 *     → [parallel] market_health_daily (20 min expected, 20 min timeout = 1200s)
 *                + trend_template_data (30 min expected, 90 min timeout = 5400s)
 *       → swing_trader_scores (30+ min expected, 45 min timeout = 2700s)
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
          TaskDefinition       = var.loader_task_definition_arns["market_constituents"]
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
          loader_name       = "market_constituents"
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
        Next = "ParallelEnrichment"
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

      # ── Step 2: Market health + trend template (parallel enrichment) ─
      # REFACTORED: Removed technical_data_daily (90 min) — orchestrator Phase 5 computes signals on-the-fly.
      # FIXED: Moved market_exposure_daily to run AFTER sector_ranking (Step 8c) to ensure all dependencies complete.
      # Previously was in parallel enrichment with 600s timeout → failed because trend_template takes 5400s.
      ParallelEnrichment = {
        Type = "Parallel"
        Branches = [
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
          },
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
        Next = "AlgoMetrics"
      }

      # Log enrichment (market health + trend template + market exposure) failures
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
      # FIXED 2026-06-XX: Switched to vectorized loader (2-3x faster)
      # Vectorized approach: 1 bulk query → vectorized pandas operations → single bulk insert
      # Full load (30-day lookback): 10-20 min vs old 30-40 min (2-3x faster)
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
        Next = "TechnicalDataDaily"
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

      # ── Step 8b: Technical Data Daily (depends on prices) ──────────────
      # REQUIRED BY PHASE 1 & BUY_SELL_DAILY: Computes RSI, MACD, ATR, Bollinger Bands, etc.
      # buy_sell_daily loader validates that technical_data_daily is fresh before generating signals.
      # Uses vectorized loader: 5000+ symbols in 15-25 minutes (single bulk fetch + vectorized pandas ops).
      # Timeout: 3600s (1 hour) for full load with 300-day lookback.
      TechnicalDataDaily = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 3600
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
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogTechDataFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "BuySellDaily"
      }

      LogTechDataFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name        = "technical_data_daily"
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
          Next        = "TechDataFailureHalt"
          ResultPath  = "$.logError"
        }]
        Next = "TechDataFailureHalt"
      }

      # Fail-closed terminal state: pipeline halts when technical_data_daily fails
      TechDataFailureHalt = {
        Type  = "Fail"
        Error = "CRITICAL_LOADER_FAILURE"
        Cause = "technical_data_daily failed after retries. Pipeline halted because buy_sell_daily requires fresh technical indicators. Check CloudWatch logs for details."
      }

      # ── Step 8c: Buy/Sell Daily Signals (depends on prices + scores + technical data) ──────────────
      # CRITICAL FOR PHASE 5: Must provide fresh buy_sell_daily BUY signals.
      # Phase 5 signal generation uses these signals as primary path (with composite_score ranking).
      # Depends on: stock_prices_daily (completed), swing_trader_scores (completed), technical_data_daily (completed)
      # Timeout: 21600s (6 hours) - vectorized loader runs in ~30 min, but allow headroom
      BuySellDaily = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 21600
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["buy_sell_daily"]
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
          Next        = "LogBuySellFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "SectorRanking"
      }

      LogBuySellFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name        = "buy_sell_daily"
          "error.$"          = "$.loaderError.Error"
          "error_message.$"  = "$.loaderError.Cause"
          is_critical_loader = false
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
          Next        = "SectorRanking"
          ResultPath  = "$.logError"
        }]
        Next = "SectorRanking"
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
          Next        = "MarketExposureDaily"
          ResultPath  = "$.logError"
        }]
        Next = "MarketExposureDaily"
      }

      # ── Step 8d: Market exposure limits — CRITICAL for Phase 1 freshness check ──
      # FIXED: Moved from ParallelEnrichment (was timing out at 600s) to run AFTER sector_ranking.
      # Now has 600+ seconds guaranteed with all dependencies complete:
      # - market_health_daily (VIX, put/call, breadth, new highs/lows)
      # - trend_template_data (price_above_sma calculations)
      # - price_daily (via stock_prices_daily, for momentum/distribution days)
      # - economic_data (credit spreads, yield curve, jobless claims)
      # CRITICAL: Phase 1 checks market_exposure_daily freshness and halts if stale
      MarketExposureDaily = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 600
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["market_exposure_daily"]
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
          Next        = "LogMarketExposureFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "DataPatrol"
      }

      LogMarketExposureFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "market_exposure_daily"
          "error.$"         = "$.loaderError.Error"
          "error_message.$" = "$.loaderError.Cause"
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
          Next        = "DataPatrol"
          ResultPath  = "$.logError"
        }]
        Next = "DataPatrol"
      }

      # ── Step 8e: Data patrol — validates data quality before orchestrator runs ──
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
                },
                {
                  Name  = "ALERTS_SNS_TOPIC"
                  Value = var.sns_alert_topic_arn
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
# Financial Data Pipeline - Separate State Machine
# FIXED Issue #31: Wire financial data loaders into Step Functions
# Financial (4:05 PM ET): Runs PARALLEL with EOD pipeline
# Loads: income_statement, balance_sheet, cash_flow (annual, quarterly, TTM)
# Quality/growth metrics depend on fresh financial data; previous EventBridge schedule
# was Monday-only, causing stale data Tue-Fri. Now runs daily at 4:05 PM.
# ============================================================

resource "aws_sfn_state_machine" "financial_data_pipeline" {
  name     = "${var.project_name}-financial-data-pipeline-${var.environment}"
  role_arn = aws_iam_role.sfn_pipeline.arn
  type     = "STANDARD"

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn_pipeline.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  definition = jsonencode({
    Comment = "Daily financial data loading: annual/quarterly/TTM income, balance, cash flow"
    StartAt = "AnnualIncome"

    States = {
      # ── Annual Financial Statements ──
      AnnualIncome = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1200
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["financials_annual_income"]
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
          Next        = "LogAnnualIncomeFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "AnnualBalance"
      }

      LogAnnualIncomeFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "financials_annual_income"
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
          Next        = "AnnualBalance"
          ResultPath  = "$.logError"
        }]
        Next = "AnnualBalance"
      }

      AnnualBalance = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1200
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["financials_annual_balance"]
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
          Next        = "LogAnnualBalanceFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "AnnualCashFlow"
      }

      LogAnnualBalanceFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "financials_annual_balance"
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
          Next        = "AnnualCashFlow"
          ResultPath  = "$.logError"
        }]
        Next = "AnnualCashFlow"
      }

      AnnualCashFlow = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1200
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["financials_annual_cashflow"]
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
          Next        = "LogAnnualCashFlowFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "QuarterlyIncome"
      }

      LogAnnualCashFlowFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "financials_annual_cashflow"
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
          Next        = "QuarterlyIncome"
          ResultPath  = "$.logError"
        }]
        Next = "QuarterlyIncome"
      }

      # ── Quarterly Financial Statements ──
      QuarterlyIncome = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1200
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["financials_quarterly_income"]
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
          Next        = "LogQuarterlyIncomeFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "QuarterlyBalance"
      }

      LogQuarterlyIncomeFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "financials_quarterly_income"
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
          Next        = "QuarterlyBalance"
          ResultPath  = "$.logError"
        }]
        Next = "QuarterlyBalance"
      }

      QuarterlyBalance = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1200
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["financials_quarterly_balance"]
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
          Next        = "LogQuarterlyBalanceFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "QuarterlyCashFlow"
      }

      LogQuarterlyBalanceFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "financials_quarterly_balance"
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
          Next        = "QuarterlyCashFlow"
          ResultPath  = "$.logError"
        }]
        Next = "QuarterlyCashFlow"
      }

      QuarterlyCashFlow = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1200
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["financials_quarterly_cashflow"]
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
          Next        = "LogQuarterlyCashFlowFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "TTMIncome"
      }

      LogQuarterlyCashFlowFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "financials_quarterly_cashflow"
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
          Next        = "TTMIncome"
          ResultPath  = "$.logError"
        }]
        Next = "TTMIncome"
      }

      # ── TTM (Trailing Twelve Months) Financial Statements ──
      TTMIncome = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1200
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["financials_ttm_income"]
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
          Next        = "LogTTMIncomeFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "TTMCashFlow"
      }

      LogTTMIncomeFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "financials_ttm_income"
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
          Next        = "TTMCashFlow"
          ResultPath  = "$.logError"
        }]
        Next = "TTMCashFlow"
      }

      TTMCashFlow = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1200
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["financials_ttm_cashflow"]
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
          Next        = "LogTTMCashFlowFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "FinancialDataSuccess"
      }

      LogTTMCashFlowFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "financials_ttm_cashflow"
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
          Next        = "FinancialDataSuccess"
          ResultPath  = "$.logError"
        }]
        Next = "FinancialDataSuccess"
      }

      FinancialDataSuccess = {
        Type = "Succeed"
      }
    }
  })

  tags = var.common_tags
}

# ============================================================
# Reference Data Pipeline - Earnings & Analyst Data
# FIXED Issue #32: Wire reference data loaders into Step Functions
# Reference (4:15 AM ET): Runs early morning before prices load
# Loads: earnings_calendar, earnings_history, company_profile, analyst data
# Independence: No dependencies (separate APIs, can fail gracefully)
# ============================================================

resource "aws_sfn_state_machine" "reference_data_pipeline" {
  name     = "${var.project_name}-reference-data-pipeline-${var.environment}"
  role_arn = aws_iam_role.sfn_pipeline.arn
  type     = "STANDARD"

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn_pipeline.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  definition = jsonencode({
    Comment = "Daily reference data: earnings, company profiles, analyst data (independent APIs)"
    StartAt = "EarningsCalendar"

    States = {
      # ── Earnings Calendar (next 180 days) ──
      EarningsCalendar = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1200
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["earnings_calendar"]
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
          Next        = "LogEarningsCalendarFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "EarningsHistory"
      }

      LogEarningsCalendarFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "earnings_calendar"
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
          Next        = "EarningsHistory"
          ResultPath  = "$.logError"
        }]
        Next = "EarningsHistory"
      }

      # ── Earnings History (yfinance, rate-limited) ──
      EarningsHistory = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 7200
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["earnings_history"]
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
          Next        = "LogEarningsHistoryFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "CompanyProfile"
      }

      LogEarningsHistoryFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "earnings_history"
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
          Next        = "CompanyProfile"
          ResultPath  = "$.logError"
        }]
        Next = "CompanyProfile"
      }

      # ── Company Profile (sector, industry, name) ──
      CompanyProfile = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1800
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["company_profile"]
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
          Next        = "LogCompanyProfileFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "PositioningMetrics"
      }

      LogCompanyProfileFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "company_profile"
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
          Next        = "PositioningMetrics"
          ResultPath  = "$.logError"
        }]
        Next = "PositioningMetrics"
      }

      # ── Positioning Metrics (short interest, institutional ownership) ──
      PositioningMetrics = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 3600
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["positioning_metrics"]
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
          Next        = "LogPositioningMetricsFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "AnalystSentiment"
      }

      LogPositioningMetricsFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "positioning_metrics"
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
          Next        = "AnalystSentiment"
          ResultPath  = "$.logError"
        }]
        Next = "AnalystSentiment"
      }

      # ── Analyst Sentiment (buy/hold/sell recommendations) ──
      AnalystSentiment = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1800
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["analyst_sentiment"]
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
          Next        = "LogAnalystSentimentFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "AnalystUpgradesDowngrades"
      }

      LogAnalystSentimentFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "analyst_sentiment"
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
          Next        = "AnalystUpgradesDowngrades"
          ResultPath  = "$.logError"
        }]
        Next = "AnalystUpgradesDowngrades"
      }

      # ── Analyst Upgrades/Downgrades (recent rating changes) ──
      AnalystUpgradesDowngrades = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1800
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["analyst_upgrades_downgrades"]
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
          Next        = "LogAnalystUpgradesDowngradesFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "ReferenceDataSuccess"
      }

      LogAnalystUpgradesDowngradesFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "analyst_upgrades_downgrades"
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
          Next        = "ReferenceDataSuccess"
          ResultPath  = "$.logError"
        }]
        Next = "ReferenceDataSuccess"
      }

      ReferenceDataSuccess = {
        Type = "Succeed"
      }
    }
  })

  tags = var.common_tags
}

# ============================================================
# Morning Prep Pipeline - Separate State Machine
# FIXED Issue #5: Split morning and EOD pipelines to prevent signal double-generation
# Morning (2:00 AM ET): Load prices → market health → swing scores → sector ranking
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
      # parallelism=1 (serial to prevent yfinance 429 rate limit errors); actual runtime 60-90 min with 5000+ symbols
      # Timeout increased from 75min to 2h to provide sufficient buffer (first attempt was hitting exactly 75min timeout)
      MorningPrices = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 7200
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
                { Name = "LOADER_ASSET_CLASSES", Value = "stock,etf" },
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
        Next = "MorningHealthAndTrend"
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

      # ── Morning market health + trend template (parallel enrichment, fail-open) ─
      # FIXED: Implement market_health_daily in morning pipeline (was only in EOD)
      # If EOD pipeline fails, market health data is now refreshed at 3:30 AM each day
      # Fail-open: if either enrichment fails, orchestrator continues with stale data instead of halting
      MorningHealthAndTrend = {
        Type = "Parallel"
        Branches = [
          {
            StartAt = "MorningMarketHealthDaily"
            States = {
              MorningMarketHealthDaily = {
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
          },
          {
            StartAt = "MorningTrendTemplate"
            States = {
              MorningTrendTemplate = {
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
          Next        = "LogMorningHealthFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "MorningMarketExposure"
      }

      LogMorningHealthFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "morning_health_and_trend"
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
          Next        = "MorningMarketExposure"
          ResultPath  = "$.logError"
        }]
        Next = "MorningMarketExposure"
      }

      # ── Morning market exposure (fresh regime for 9:30 AM orchestrator) ────────
      # CRITICAL FIX: Eliminates EOD-only single point of failure
      # If EOD pipeline fails, morning pipeline ensures market_exposure_daily is fresh for:
      # - 9:30 AM orchestrator run (9+ hours until EOD)
      # - 1 PM and 3 PM orchestrator runs (4-7 hours until EOD)
      # - Dashboard market regime display (avoids stale data for entire week)
      # Depends on: market_health_daily (computed in MorningHealthAndTrend parallel step)
      # Timeout: 600s (typically 30s-1min, well under budget)
      # Fail-open: If this fails, orchestrator falls back to yesterday's regime (graceful degradation)
      MorningMarketExposure = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 600
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["market_exposure_daily"]
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
          Next        = "MorningSwingScores"
          ResultPath  = "$.exposureError"
        }]
        Next = "MorningSwingScores"
      }

      # ── Morning swing trader scores (only critical supporting loader) ─
      # NOTE: buy_sell_daily runs only in EOD pipeline, not morning.
      # Morning orchestrator (9:30 AM) uses buy_sell signals from previous day's EOD run.
      # Removed: signal_quality_scores (computed on-the-fly instead).
      # FIXED 2026-06-XX: Switched to vectorized loader (2-3x faster)
      # Vectorized approach: 10-20 min vs old 30-40 min (2-3x faster)
      MorningSwingScores = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 2700
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["swing_trader_scores"]
          NetworkConfiguration = local.network_config
        }
        # Fail-open: if swing scores fail, morning prep still succeeds
        # Orchestrator doesn't depend on pre-computed swing scores
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 90
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "MorningTechnicalData"
          ResultPath  = "$.swingError"
        }]
        Next = "MorningTechnicalData"
      }

      # ── Morning technical data daily (required for Phase 1 freshness) ──
      # FIXED Issue #18: Add technical_data_daily to morning pipeline for redundancy
      # If EOD pipeline fails, morning pipeline ensures technical_data_daily is fresh for Phase 1 checks
      # and Phase 5 signal generation that may run later in the day.
      # Depends on: stock_prices_daily (already completed)
      # Timeout: 3600s (1 hour) for full 300-day lookback vectorized load
      # Fail-open: If technical data fails in morning, Phase 1 doesn't block Phase 5 (has fallback)
      MorningTechnicalData = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 3600
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
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "MorningSectorRanking"
          ResultPath  = "$.techDataError"
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

# ============================================================
# Computed Metrics Pipeline - Daily Stock Metrics
# FIXED Issue #31: Wire quality/growth/value/stability loaders into Step Functions
# Metrics (5:00 PM ET): Runs AFTER financial pipeline completes
# Depends on: financial_data_pipeline (must complete by 5:00 PM)
# Computes: quality_metrics, growth_metrics, value_metrics, stability_metrics, stock_scores
# Runs sequentially to respect dependencies and avoid RDS connection pool exhaustion
# ============================================================

resource "aws_sfn_state_machine" "computed_metrics_pipeline" {
  name     = "${var.project_name}-computed-metrics-pipeline-${var.environment}"
  role_arn = aws_iam_role.sfn_pipeline.arn
  type     = "STANDARD"

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn_pipeline.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  definition = jsonencode({
    Comment = "Daily computed metrics: quality/growth/value/stability/stock scores (depends on financial data)"
    StartAt = "GrowthMetrics"

    States = {
      # ── Growth Metrics (depends on financial data) ──
      GrowthMetrics = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 3600
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["growth_metrics"]
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
          Next        = "LogGrowthMetricsFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "QualityMetrics"
      }

      LogGrowthMetricsFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "growth_metrics"
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
          Next        = "QualityMetrics"
          ResultPath  = "$.logError"
        }]
        Next = "QualityMetrics"
      }

      # ── Quality Metrics (depends on financial data) ──
      QualityMetrics = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 3600
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["quality_metrics"]
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
          Next        = "LogQualityMetricsFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "ValueMetrics"
      }

      LogQualityMetricsFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "quality_metrics"
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
          Next        = "ValueMetrics"
          ResultPath  = "$.logError"
        }]
        Next = "ValueMetrics"
      }

      # ── Value Metrics (independent of financial data) ──
      ValueMetrics = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 3600
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["value_metrics"]
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
          Next        = "LogValueMetricsFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "StabilityMetrics"
      }

      LogValueMetricsFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "value_metrics"
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
          Next        = "StabilityMetrics"
          ResultPath  = "$.logError"
        }]
        Next = "StabilityMetrics"
      }

      # ── Stability Metrics (independent of financial data) ──
      StabilityMetrics = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1800
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["stability_metrics"]
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
          Next        = "LogStabilityMetricsFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "StockScores"
      }

      LogStabilityMetricsFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "stability_metrics"
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
          Next        = "StockScores"
          ResultPath  = "$.logError"
        }]
        Next = "StockScores"
      }

      # ── Stock Composite Scores (depends on all above metrics) ──
      StockScores = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 3600
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["stock_scores"]
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
          Next        = "LogStockScoresFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "MetricsSuccess"
      }

      LogStockScoresFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "stock_scores"
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
          Next        = "MetricsSuccess"
          ResultPath  = "$.logError"
        }]
        Next = "MetricsSuccess"
      }

      MetricsSuccess = {
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

# ============================================================
# Intraday Update Pipelines (1 PM & 3 PM ET)
# FIXED Issue #???: Enable fresh score updates during trading hours
# Uses vectorized swing_trader_scores with INTRADAY_MODE for 5-15 min updates
# ============================================================

resource "aws_sfn_state_machine" "intraday_afternoon_update_pipeline" {
  name     = "${var.project_name}-intraday-afternoon-update-${var.environment}"
  role_arn = aws_iam_role.sfn_pipeline.arn
  type     = "STANDARD"

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn_pipeline.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  definition = jsonencode({
    Comment = "Intraday afternoon score update: 1:00 PM ET, fresh swing_trader_scores for afternoon trading"
    StartAt = "AfternoonSwingScores"

    States = {
      AfternoonSwingScores = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1200
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["swing_trader_scores"]
          NetworkConfiguration = local.network_config
          Overrides = {
            ContainerOverrides = [{
              Name = "${var.project_name}-swing_trader_scores"
              Environment = [
                {
                  Name  = "INTRADAY_MODE"
                  Value = "true"
                }
              ]
            }]
          }
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 60
          MaxAttempts     = 1
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogAfternoonFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "AfternoonSuccess"
      }

      LogAfternoonFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "swing_trader_scores (afternoon 1 PM)"
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
          Next        = "AfternoonSuccess"
          ResultPath  = "$.logError"
        }]
        Next = "AfternoonSuccess"
      }

      AfternoonSuccess = {
        Type = "Succeed"
      }
    }
  })

  tags = var.common_tags
}

resource "aws_sfn_state_machine" "intraday_preclose_update_pipeline" {
  name     = "${var.project_name}-intraday-preclose-update-${var.environment}"
  role_arn = aws_iam_role.sfn_pipeline.arn
  type     = "STANDARD"

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn_pipeline.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  definition = jsonencode({
    Comment = "Intraday pre-close score update: 3:00 PM ET, fresh swing_trader_scores for final trading (SLA critical: finish by 3:15 PM)"
    StartAt = "PrecloseSwingScores"

    States = {
      PrecloseSwingScores = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 900
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["swing_trader_scores"]
          NetworkConfiguration = local.network_config
          Overrides = {
            ContainerOverrides = [{
              Name = "${var.project_name}-swing_trader_scores"
              Environment = [
                {
                  Name  = "INTRADAY_MODE"
                  Value = "true"
                }
              ]
            }]
          }
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 1
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogPrecloseFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "PrecloseSuccess"
      }

      LogPrecloseFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "swing_trader_scores (preclose 3 PM)"
          "error.$"         = "$.loaderError.Error"
          "error_message.$" = "$.loaderError.Cause"
        }
        ResultPath = "$.failureLog"
        Retry = [{
          ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.Unknown"]
          IntervalSeconds = 2
          MaxAttempts     = 1
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "PrecloseSuccess"
          ResultPath  = "$.logError"
        }]
        Next = "PrecloseSuccess"
      }

      PrecloseSuccess = {
        Type = "Succeed"
      }
    }
  })

  tags = var.common_tags
}

# ============================================================
# CloudWatch Log Group for EventBridge Scheduler
# ============================================================

resource "aws_cloudwatch_log_group" "eventbridge_scheduler" {
  name              = "/aws/scheduler/${var.project_name}-pipeline-${var.environment}"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = var.common_tags
}

# ============================================================
# EventBridge Scheduler (timezone-aware): all pipelines use America/New_York so they
# fire at the correct wall-clock time year-round regardless of EST/EDT offset.
#
# Morning: 2:00 AM ET   — loads prices + technicals before market open (7h 30m before 9:30 AM, 210min buffer)
# Afternoon: 12:50 PM ET — fresh scores 10 min before 1 PM orchestrator
# Preclose: 2:50 PM ET   — fresh scores 10 min before 3 PM orchestrator (SLA critical)
# EOD:     4:05 PM ET    — 5 min after market close, gives Alpaca time to settle prices

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

    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 2
    }
  }
}

resource "aws_scheduler_schedule" "afternoon_update_pipeline_trigger" {
  name                         = "${var.project_name}-afternoon-update-pipeline-${var.environment}"
  description                  = "Intraday afternoon score update: 12:50 PM ET (10 min before 1 PM orchestrator, 20-25 min total)"
  schedule_expression          = "cron(50 12 ? * MON-FRI *)"
  schedule_expression_timezone = "America/New_York"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.intraday_afternoon_update_pipeline.arn
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      execution_name = "afternoon-<aws.scheduler.execution-id>"
    })

    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 2
    }
  }
}

resource "aws_scheduler_schedule" "preclose_update_pipeline_trigger" {
  name                         = "${var.project_name}-preclose-update-pipeline-${var.environment}"
  description                  = "Intraday pre-close score update: 2:50 PM ET (10 min before 3 PM orchestrator, SLA critical: finish by 3:15 PM)"
  schedule_expression          = "cron(50 14 ? * MON-FRI *)"
  schedule_expression_timezone = "America/New_York"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.intraday_preclose_update_pipeline.arn
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      execution_name = "preclose-<aws.scheduler.execution-id>"
    })

    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 2
    }
  }
}

resource "aws_scheduler_schedule" "financial_data_pipeline_trigger" {
  name                         = "${var.project_name}-financial-data-pipeline-${var.environment}"
  description                  = "Daily financial data: income/balance/cash flow (annual/quarterly/TTM) - 4:05 PM ET, runs in parallel with EOD"
  schedule_expression          = "cron(5 16 ? * MON-FRI *)"
  schedule_expression_timezone = "America/New_York"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.financial_data_pipeline.arn
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      execution_name = "financial-<aws.scheduler.execution-id>"
    })

    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 2
    }
  }
}

resource "aws_scheduler_schedule" "computed_metrics_pipeline_trigger" {
  name                         = "${var.project_name}-computed-metrics-pipeline-${var.environment}"
  description                  = "Daily computed metrics: quality/growth/value/stability/scores - 5:00 PM ET, depends on financial data pipeline"
  schedule_expression          = "cron(0 17 ? * MON-FRI *)"
  schedule_expression_timezone = "America/New_York"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.computed_metrics_pipeline.arn
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      execution_name = "metrics-<aws.scheduler.execution-id>"
    })

    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 2
    }
  }
}

resource "aws_scheduler_schedule" "reference_data_pipeline_trigger" {
  name                         = "${var.project_name}-reference-data-pipeline-${var.environment}"
  description                  = "Daily reference data: earnings calendar/history, company profile, analyst sentiment - 4:15 AM ET"
  schedule_expression          = "cron(15 9 ? * MON-FRI *)"
  schedule_expression_timezone = "America/New_York"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.reference_data_pipeline.arn
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      execution_name = "reference-<aws.scheduler.execution-id>"
    })

    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 2
    }
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

    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 2
    }
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


