// Step Functions state machines for dependency-driven data loading pipelines.
// Replaces EventBridge cron rules with guaranteed ordering: orchestrator runs only when
// all signal data is ready. Timeout strategy: expected + 2-3x safety margin, fail fast on real failures.

locals {
  network_config = {
    AwsvpcConfiguration = {
      Subnets        = var.public_subnet_ids
      SecurityGroups = [var.ecs_tasks_sg_id]
      AssignPublicIp = "ENABLED"
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
      },
      {
        # Self-concurrency check (CheckConcurrency state, all 4 pipelines): each pipeline
        # lists its own RUNNING executions before doing any real work, so a retried/
        # overlapping trigger skips instead of launching a second set of ECS loader tasks
        # in parallel with an already-running execution.
        Sid      = "ListOwnExecutions"
        Effect   = "Allow"
        Action   = "states:ListExecutions"
        Resource = "arn:aws:states:${var.aws_region}:${var.aws_account_id}:stateMachine:${var.project_name}-*-pipeline-${var.environment}"
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
      # ── StartAt: Direct to stock symbols loading ──
      # FIXED (Session 192): Removed aggressive concurrency check that was blocking all executions.
      # Previous logic: checked if ANY other run was RUNNING, causing even scheduled runs to skip.
      # ECS loaders use DynamoDB distributed locks (LOADER_DISTRIBUTED_LOCK) to prevent true conflicts.
      # Morning (2 AM) and EOD (4 PM ET) runs don't overlap, and manual triggers override scheduled.
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
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
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
          Overrides = {
            ContainerOverrides = [{
              Name = "algo-stock_prices_daily"
              Environment = [
                { Name = "LOADER_INTERVALS", Value = "1d" },
                { Name = "LOADER_ASSET_CLASSES", Value = "stock,etf" },
                { Name = "LOADER_PARALLELISM", Value = "1" },
                { Name = "LOADER_CHUNK_SIZE", Value = "5000" }
              ]
            }]
          }
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

      # ── Step 2: Trend template (parallel enrichment) ─
      # REFACTORED: Removed technical_data_daily (90 min) — orchestrator Phase 5 computes signals on-the-fly.
      # FIXED: Moved market_health_daily to run AFTER technical_data_daily (Step 8b) to ensure breadth_data dependencies complete.
      # FIXED: Moved market_exposure_daily to run AFTER sector_ranking (Step 8c) to ensure all dependencies complete.
      # Now only trend_template runs in parallel for maximum speed.
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
                Next = "SuccessTrendTemplate"
              }
              SuccessTrendTemplate = {
                Type = "Succeed"
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
        Next = "TechnicalDataDaily"
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
          Next        = "TechnicalDataDaily"
          ResultPath  = "$.logError"
        }]
        Next = "TechnicalDataDaily"
      }

      # ── Step 8: Technical Data Daily (depends on prices) ──────────────
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
          Overrides = {
            ContainerOverrides = [{
              Name = "algo-technical_data_daily"
              Environment = [
                { Name = "LOADER_PARALLELISM", Value = "1" }
              ]
            }]
          }
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogTechDataFailure"
          ResultPath  = "$.loaderError"
        }]
        # FIX 2026-07-20: was "MarketHealthDaily", a state removed by commit 60bccc14b
        # (Phase 2 consolidation into MarketStatusDaily) without updating this transition -
        # a dangling Next reference AWS Step Functions rejects at deploy time. BuySellDaily
        # is the actual next step in the pipeline (Step 8b was consolidated away; see comment
        # below). MarketStatusDaily still runs later, after FredEconomicData.
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

      # ── Step 8b: PHASE 2 - CONSOLIDATED (removed MarketHealthDaily) ──────────────
      # OPTIMIZATION: Moved market_health_daily from early path to consolidated MarketStatusDaily
      # which runs later in pipeline (after SectorRanking, FredEconomicData).
      # MarketStatusDaily is atomic: outputs to market_health_daily, market_exposure_daily,
      # market_sentiment all together, with all dependencies met.
      # Saves: 1 ECS task, 10-15 min pipeline time, better error handling

      # ── Step 8c: Buy/Sell Daily Signals (depends on prices + scores + technical data) ──────────────
      # CRITICAL FOR PHASE 5: Must provide fresh buy_sell_daily BUY signals.
      # Phase 5 signal generation uses these signals as primary path (with composite_score ranking).
      # Depends on: stock_prices_daily (completed), swing_trader_scores (completed), technical_data_daily (completed)
      # NOTE: market_health_daily now runs atomically as MarketStatusDaily (late in pipeline)
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
        Next = "AlgoMetricsAfterSignals"
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
          Next        = "AlgoMetricsAfterSignals"
          ResultPath  = "$.logError"
        }]
        Next = "SignalQualityScores"
      }

      # ── NEW: Signal Quality Scores (Session 307 restoration) ──────────────────────────
      # Computes signal quality scores from buy_sell_daily and technical data
      # Non-critical: fails gracefully; NULL values show in dashboard
      # Timeout: 7200s (120 min)
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
          IntervalSeconds = 30
          MaxAttempts     = 1
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogSQSFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "AlgoMetricsAfterSignals"
      }

      LogSQSFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name        = "signal_quality_scores"
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
          Next        = "AlgoMetricsAfterSignals"
          ResultPath  = "$.logError"
        }]
        Next = "AlgoMetricsAfterSignals"
      }

      # ── NEW: AlgoMetrics moved to non-critical path ──────────────────────────
      # OPTIMIZATION: Dashboard-only loader (computes portfolio stats from audit log)
      # Moved from Step 5 (blocking) to here (after signals generated)
      # No impact on trading; Phase 7 signal generation already complete
      # Timeout: 7200s (120 min) for full portfolio stat computation
      AlgoMetricsAfterSignals = {
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
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogMetricsFailureAfterSignals"
          ResultPath  = "$.loaderError"
        }]
        # FIX 2026-07-20: was "SectorRanking", a state removed by commit 5bc60bb97 (Phase 4
        # consolidation into SectorIndustryDaily) without updating this transition - a
        # dangling Next reference AWS Step Functions rejects at deploy time.
        Next = "SectorIndustryDaily"
      }

      LogMetricsFailureAfterSignals = {
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
          Next        = "SectorIndustryDaily"
          ResultPath  = "$.logError"
        }]
        Next = "SectorIndustryDaily"
      }

      # ── Step 8c: PHASE 4 - Sector Industry Daily (CONSOLIDATED) ──
      # CONSOLIDATION: Merges 3 separate sector loaders into 1 atomic operation:
      # - sector_ranking (sector rankings by metric)
      # - industry_ranking (industry rankings)
      # - sector_performance (daily sector returns)
      #
      # Benefits:
      # - 1 ECS task instead of 3 (saves ~$0.01-0.02/run)
      # - All sector/industry data computed together
      # - Atomic operation (all 3 outputs succeed/fail together)
      # - Unified OptimalLoader framework (consistent error handling)
      # - Simpler maintenance (one loader, one failure path)
      #
      # Outputs atomically to:
      # - sector_ranking (sector rankings)
      # - industry_ranking (industry rankings)
      # - sector_performance (daily sector returns)
      #
      # Depends on: stock_scores (completed), swing_trader_scores
      # Timeout: 900s (15 min - sufficient for all 3 operations)
      SectorIndustryDaily = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 900
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["sector_industry_daily"]
          NetworkConfiguration = local.network_config
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogSectorIndustryFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "FredEconomicData"
      }

      LogSectorIndustryFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "sector_industry_daily"
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
          Next        = "FredEconomicData"
          ResultPath  = "$.logError"
        }]
        Next = "FredEconomicData"
      }

      # ── Step 8c-bis: FRED economic data loader ──
      # Fetches Treasury yields (T10Y2Y), Fed rate, credit spreads, jobless claims
      # Used by market_exposure_daily for regime detection
      FredEconomicData = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 600
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["economic_data"]
          NetworkConfiguration = local.network_config
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 60
          MaxAttempts     = 1
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogFredFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "NaaimSentiment"
      }

      LogFredFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name        = "economic_data"
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
          Next        = "NaaimSentiment"
          ResultPath  = "$.logError"
        }]
        Next = "NaaimSentiment"
      }

      # ── Step 8c-ter: NAAIM + AAII sentiment loaders (Session 301 restoration) ──
      # Feed algo/risk/factors/naaim_factor.py + aaii_sentiment_factor.py, 2 of the Core 12
      # market-exposure factors computed by MarketStatusDaily below. Both were deleted
      # 2026-07-03 (mislabeled "unused") while the factors kept silently scoring off the
      # resulting stale tables (3-4 weeks old, no freshness check anywhere in the read
      # path). Fail-open like FredEconomicData: a missed weekly survey degrades the
      # regime score by 2 of ~20 factor inputs, not worth halting the whole EOD pipeline.
      NaaimSentiment = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 300
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["naaim"]
          NetworkConfiguration = local.network_config
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 60
          MaxAttempts     = 1
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogNaaimFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "AaiiSentiment"
      }

      LogNaaimFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name        = "naaim"
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
          Next        = "AaiiSentiment"
          ResultPath  = "$.logError"
        }]
        Next = "AaiiSentiment"
      }

      AaiiSentiment = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 300
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["aaii_sentiment"]
          NetworkConfiguration = local.network_config
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 60
          MaxAttempts     = 1
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogAaiiFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "AnalystUpgradeDowngrade"
      }

      LogAaiiFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name        = "aaii_sentiment"
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
          Next        = "AnalystUpgradeDowngrade"
          ResultPath  = "$.logError"
        }]
        Next = "AnalystUpgradeDowngrade"
      }

      # ── Step 8c-quater: Analyst upgrade/downgrade ratings (Session 2026-07-27) ──
      # Feeds algo/signals/advanced_filters.py::_analyst_score(), one of 5 catalyst subscore
      # components. AUXILIARY tier, restores a loader deleted with load_yfinance_snapshot.py
      # (see steering/DATA_LOADERS.md's GAP note). Fail-open like NaaimSentiment/AaiiSentiment:
      # a missed run degrades the catalyst score by one of its components, not worth halting
      # the whole EOD pipeline.
      AnalystUpgradeDowngrade = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 900
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["analyst_upgrade_downgrade"]
          NetworkConfiguration = local.network_config
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 60
          MaxAttempts     = 1
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogAnalystUpgradeDowngradeFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "AnalystSentimentAnalysis"
      }

      LogAnalystUpgradeDowngradeFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name        = "analyst_upgrade_downgrade"
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
          Next        = "AnalystSentimentAnalysis"
          ResultPath  = "$.logError"
        }]
        Next = "AnalystSentimentAnalysis"
      }

      # ── Step 8c-quinquies: Analyst sentiment analysis (Session 2026-07-27) ──
      # Same gap class as AnalystUpgradeDowngrade above, separate table - feeds
      # lambda/api/routes/sentiment.py's /api/sentiment/analyst/* endpoints (which correctly
      # fail-fast on stale data rather than serve it, per steering/DATA_LOADERS.md). AUXILIARY
      # tier, fail-open like its sibling above - both this state's own success Next AND its
      # failure handler's Next point at MarketStatusDaily (matching the pattern every other
      # state in this chain uses - see the SecCashFlowMetrics/SecSegmentInfo fix earlier in
      # this file for what happens when they don't).
      AnalystSentimentAnalysis = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 900
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["analyst_sentiment_analysis"]
          NetworkConfiguration = local.network_config
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 60
          MaxAttempts     = 1
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogAnalystSentimentAnalysisFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "MarketStatusDaily"
      }

      LogAnalystSentimentAnalysisFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name        = "analyst_sentiment_analysis"
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
          Next        = "MarketStatusDaily"
          ResultPath  = "$.logError"
        }]
        Next = "MarketStatusDaily"
      }

      # ── Step 8d: PHASE 2 - Market Status Daily (CONSOLIDATED) ──
      # CONSOLIDATION: Merges 3 separate loaders into 1 atomic operation:
      # - market_health_daily (VIX, put/call, breadth, new highs/lows)
      # - market_exposure_daily (regime, exposure %, critical for Phase 1 freshness check)
      # - market_sentiment (fear/greed index)
      #
      # Benefits:
      # - 1 ECS task instead of 3 (saves ~$0.02-0.03/run)
      # - VIX/breadth/yields fetched once, used 3 ways
      # - Atomic operation (all market metrics succeed/fail together)
      # - All dependencies met: technical_data_daily (breadth), sector_ranking, economic_data
      # - Cleaner error handling (single failure point)
      # - 10-15 min faster pipeline (fewer tasks + atomic writes)
      #
      # Outputs atomically to:
      # - market_health_daily (VIX, put/call, breadth, yields)
      # - market_exposure_daily (regime, exposure %, factors)
      # - market_sentiment (fear/greed, bull/bear %)
      #
      # Timeout: 1800s (30 min - combined 1200+600+300 from old loaders)
      MarketStatusDaily = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1800
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["market_status_daily"]
          NetworkConfiguration = local.network_config
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogMarketStatusFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "InsiderTransactionVelocity"
      }

      LogMarketStatusFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "market_status_daily"
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
          Next        = "InsiderTransactionVelocity"
          ResultPath  = "$.logError"
        }]
        Next = "InsiderTransactionVelocity"
      }

      # ── Step 8e-bis: Insider Transaction Velocity Loader ──
      # Tracks insider buying/selling patterns for confidence signals
      # Non-critical: data feed for composite scoring, doesn't block trading
      # Lightweight: processes SEC bulk data (already cached locally)
      InsiderTransactionVelocity = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 600
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["insider_transaction_velocity"]
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
          Next        = "LogInsiderVelocityFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "DataPatrol"
      }

      LogInsiderVelocityFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name        = "insider_transaction_velocity"
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
          Next        = "ValidationFailureHalt"
          ResultPath  = "$.logError"
        }]
        Next = "ValidationFailureHalt"
      }

      ValidationFailureHalt = {
        Type  = "Fail"
        Error = "PIPELINE_VALIDATION_FAILED"
        Cause = "Orchestrator validation failed - data quality check failed. Check CloudWatch logs for details."
      }

      PipelineSuccess = {
        Type = "Succeed"
      }
    }
  })

  tags = var.common_tags
}

# ============================================================
# Financial Data Pipeline - CONSOLIDATED INTO MAIN EOD PIPELINE
# REASON: Session 76 - Moved from separate state machine (was running
# sequential 9 loaders 45-90 min) into main EOD pipeline as Parallel state
# (now 20-30 min). Fixes stale financial data issue and simplifies monitoring.
# ============================================================

# ============================================================
# Reference Data Pipeline - Earnings & Analyst Data
# FIXED Issue #32: Wire reference data loaders into Step Functions
# Reference (9:15 AM ET): Runs early morning before prices load
# Loads: earnings_calendar, earnings_history, company_profile, analyst data
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
      # ── StartAt: Direct to price loading ──
      # FIXED (Session 192): Removed aggressive concurrency check that was blocking all executions.
      # Previous logic: checked if ANY other run was RUNNING, causing even scheduled runs to skip.
      # ECS loaders use DynamoDB distributed locks (LOADER_DISTRIBUTED_LOCK) to prevent true conflicts.
      CheckTradingDay = {
        Type = "Pass"
        Parameters = {
          "today.$" = "$$.State.EnteredTime"
        }
        Next = "MorningPrices"
      }

      # Load only daily prices for morning prep.
      # CRITICAL LOADER (FAIL-CLOSED): Must complete before technicals and signals can be computed.
      # Override LOADER_INTERVALS to "1d" so only daily prices are loaded (~15 min vs 6+ hours).
      # Weekly/monthly bars are DERIVED in SQL from daily bars after each 1d load
      # (derive_aggregate_prices in loaders/load_prices.py) — no interval is fetched from
      # yfinance besides 1d anywhere.
      # parallelism=1 (serial to prevent yfinance 429 rate limit errors); runtime varies 60-180 min with 5000+ symbols
      # Timeout: 6 hours (21600s), matching EOD pipeline. Morning pipeline runs 2:00-9:30 AM (450 min available).
      # FIXED 2026-07-14: Increased from 4h to 6h. Previous 4h timeout was insufficient in production, causing pipeline
      # halts every morning. Production runtime consistently exceeds 4 hours due to yfinance rate limiting and data volume.
      MorningPrices = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 21600
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
                { Name = "LOADER_PARALLELISM", Value = "1" },
                { Name = "LOADER_CHUNK_SIZE", Value = "5000" }
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
            StartAt = "MorningMarketStatusDaily"
            States = {
              MorningMarketStatusDaily = {
                Type           = "Task"
                Resource       = "arn:aws:states:::ecs:runTask.sync"
                TimeoutSeconds = 1200
                Parameters = {
                  Cluster              = var.ecs_cluster_arn
                  LaunchType           = "FARGATE"
                  TaskDefinition       = var.loader_task_definition_arns["market_status_daily"]
                  NetworkConfiguration = local.network_config
                }
                Retry = [{
                  ErrorEquals     = ["States.ALL"]
                  IntervalSeconds = 60
                  MaxAttempts     = 2
                  BackoffRate     = 2.0
                }]
                Next = "SuccessMorningMarketStatus"
              }
              SuccessMorningMarketStatus = {
                Type = "Succeed"
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
                Next = "SuccessMorningTrend"
              }
              SuccessMorningTrend = {
                Type = "Succeed"
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
      # FIXED: market_exposure_daily is now produced by consolidated market_status_daily loader
      # (runs in MorningHealthAndTrend parallel step)
      # market_status_daily is atomic: outputs to market_health_daily, market_exposure_daily,
      # and market_sentiment in a single operation (all succeed or fail together)
      # This eliminates the separate market_exposure_daily task that was previously run here
      MorningMarketExposure = {
        Type = "Pass"
        Comment = "REMOVED: market_exposure_daily now runs atomically as part of market_status_daily (Phase 2 consolidation)"
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
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "MorningSectorIndustryDaily"
          ResultPath  = "$.techDataError"
        }]
        Next = "MorningSectorIndustryDaily"
      }

      # ── Morning sector/industry consolidation (depends on technical_data_daily) ──────────
      # FIXED: sector_ranking, industry_ranking, sector_performance are now consolidated
      # into atomic sector_industry_daily loader (Phase 4 consolidation)
      # Timeout 900 seconds (15 minutes) — same as EOD pipeline.
      # This loader outputs to sector_ranking, industry_ranking, and sector_performance atomically
      MorningSectorIndustryDaily = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 900
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["sector_industry_daily"]
          NetworkConfiguration = local.network_config
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogMorningSectorIndustryFailure"
          ResultPath  = "$.sectorError"
        }]
        Next = "MorningSuccess"
      }

      LogMorningSectorIndustryFailure = {
        Type = "Pass"
        # Fail-open: if sector/industry consolidation fails, still complete morning prep
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
# FIXED 2026-07-05: Growth metrics now CRITICAL → require financial data; increased schedule buffer
#
# Timeline:
# - 4:05 PM ET: financial_data_pipeline starts (timeout 110 min → completes by ~5:55 PM)
# - 7:00 PM ET: computed_metrics_pipeline starts (175 min buffer ensures financial data ready)
#
# Why 175-min buffer: financial pipeline 6600s (110 min) + 60 min margin of safety
# Growth/quality metrics depend on annual_income_statement, balance_sheet, cash_flow
# If financial data incomplete at 7:00 PM:
# - growth_metrics → data_unavailable markers
# - Phase 1 failsafe → retries (now critical)
# - stock_scores validates 70% coverage → explicit fail-fast if insufficient
# Result: No silent degradation; missing financials = explicit data_unavailable flags
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
    StartAt = "FinancialDataLoaders"

    States = {
      # ── DEPRECATED (Session 275+): Removed yfinance_snapshot loader ──
      # yfinance_snapshot was the first step in this pipeline, but it's no longer needed:
      # - load_market_cap_computed.py: removed yfinance fallback, uses SEC only
      # - load_positioning_metrics.py: removed yfinance TIER 2 fallback, uses SEC 13F/Form4/FINRA only
      # - load_yfinance_derived_metrics.py: already migrated to SEC (company_info_sec, earnings_calendar_sec)
      # All loaders now use 100% SEC data sources. Fail-fast if SEC data unavailable (no fallbacks).

      # ── Financial Data Loaders (Consolidated) ──────────────────────────
      # OPTIMIZATION ACTIVATED (2026-07-12): Replaced 8 parallel tasks with single consolidated task
      # Single "financials_all" task loads all 8 statement/period combos sequentially
      # in one ECS container, reducing execution time from 20-30m to ~16m total (9600s execution + network overhead)
      # and saving $8-15/mo in ECS task costs. These loaders must complete before growth_metrics
      # and quality_metrics can refresh, as those loaders read from annual_income_statement and
      # annual_balance_sheet tables populated by this task.
      # Failure handling: Non-blocking (fail-open) if financial loader timeout. Quality/growth
      # metrics have graceful degradation for missing data.
      FinancialDataLoaders = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 15000
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["financials_all"]
          NetworkConfiguration = local.network_config
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogFinancialsFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "SecValuations"
      }

      LogFinancialsFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "financials_parallel"
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
          Next        = "SecValuations"
          ResultPath  = "$.logError"
        }]
        Next = "SecValuations"
      }

      # ── PHASE 5: SEC-Derived Valuations (replaces yfinance quoteSummary API calls) ──
      # Computes audited PE/PB/PS/PEG/FCF from SEC financial data + prices
      # Eliminates rate-limiting cascade (-15-20 min), $19-24/month API cost
      SecValuations = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1800
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["sec_valuations"]
          NetworkConfiguration = local.network_config
          Overrides = {
            ContainerOverrides = [{
              Name = "algo-sec_valuations"
              Environment = [
                { Name = "AWS_EXECUTION_ENV", Value = "ECS_FARGATE" },
                { Name = "LOADER_PARALLELISM", Value = "2" }
              ]
            }]
          }
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogSecValuationsFailure"
          ResultPath  = "$.loaderError"
        }]
        # FIX 2026-07-20: was "QualityMetrics", a state renamed to ValueQualityGrowthMetrics by
        # commit 0eb93ea27 (Phase 3 consolidation) without updating this transition - a
        # dangling Next reference AWS Step Functions rejects at deploy time.
        # REMOVED 2026-07-27: SecCashFlowMetrics (and its failure handler) removed from this
        # chain - audit found its 3 fields exactly duplicate quality_metrics formulas already
        # computed/scored/displayed elsewhere, real SEC API cost for zero incremental signal.
        # See steering/DATA_LOADERS.md's GAP note. Table left in place, just unscheduled.
        Next = "SecSegmentInfo"
      }

      LogSecValuationsFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "sec_valuations"
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
          Next        = "SecSegmentInfo"
          ResultPath  = "$.logError"
        }]
        Next = "SecSegmentInfo"
      }

      # ── NEW 2026-07-26 (Session 445): XBRL Segment Disclosure Extraction (ASC 280) ──
      # Parses SEC 10-K/10-Q XBRL companyfacts to extract business segment data
      # (segment counts, revenue concentration, diversification metrics).
      # Source table for load_sec_segment_metrics.py, which computes Herfindahl index
      # and feeds into quality/diversification scoring.
      # Non-critical: fails open; missing segment data defaults to data_unavailable markers.
      SecSegmentInfo = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1800
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["sec_segment_info"]
          NetworkConfiguration = local.network_config
          Overrides = {
            ContainerOverrides = [{
              Name = "algo-sec_segment_info"
              Environment = [
                { Name = "AWS_EXECUTION_ENV", Value = "ECS_FARGATE" },
                { Name = "LOADER_PARALLELISM", Value = "2" }
              ]
            }]
          }
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogSecSegmentInfoFailure"
          ResultPath  = "$.loaderError"
        }]
        # FIX 2026-07-27: same bug as SecCashFlowMetrics above, one state deeper - was
        # "ValueQualityGrowthMetrics", skipping SecSegmentMetrics on the success path even though
        # SecSegmentMetrics depends on sec_segment_info being freshly populated (only this state's
        # OWN failure handler pointed at SecSegmentMetrics, backwards - it would only ever run
        # against a run where segment info had just FAILED to write).
        Next = "SecSegmentMetrics"
      }

      LogSecSegmentInfoFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "sec_segment_info"
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
          Next        = "SecSegmentMetrics"
          ResultPath  = "$.logError"
        }]
        Next = "SecSegmentMetrics"
      }

      # ── RESTORED 2026-07-26 (Session 445): SEC Segment Metrics Diversification ──
      # Computes business segment diversification from sec_segment_info (ASC 280 data).
      # Outputs: segment_count, revenue_concentration_hhi, largest_segment_revenue_pct
      # Feeds into quality_metrics scoring for diversification component.
      # Depends on: SecSegmentInfo (must populate sec_segment_info first)
      # Non-critical: fails open; missing data defaults to data_unavailable.
      SecSegmentMetrics = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1800
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["sec_segment_metrics"]
          NetworkConfiguration = local.network_config
          Overrides = {
            ContainerOverrides = [{
              Name = "algo-sec_segment_metrics"
              Environment = [
                { Name = "AWS_EXECUTION_ENV", Value = "ECS_FARGATE" },
                { Name = "LOADER_PARALLELISM", Value = "2" }
              ]
            }]
          }
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogSecSegmentMetricsFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "AnalystEarningsEstimates"
      }

      LogSecSegmentMetricsFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "sec_segment_metrics"
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
          Next        = "AnalystEarningsEstimates"
          ResultPath  = "$.logError"
        }]
        Next = "AnalystEarningsEstimates"
      }

      # ── FIXED 2026-08-03: forward-EPS analyst estimates (registered as a loader since
      # before this pipeline existed but never scheduled anywhere - see
      # terraform/modules/loaders/main.tf's loader_file_map comment). Must run BEFORE
      # ValueQualityGrowthMetrics, which joins analyst_earnings_estimates by symbol to
      # compute forward_pe (see loaders/load_analyst_earnings_estimates.py's module
      # docstring). Without this, every symbol showed
      # forward_pe_unavailable_reason="no_analyst_estimates" regardless of real coverage. ──
      AnalystEarningsEstimates = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1200
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["analyst_earnings_estimates"]
          NetworkConfiguration = local.network_config
          Overrides = {
            ContainerOverrides = [{
              Name = "algo-analyst_earnings_estimates"
              Environment = [
                { Name = "AWS_EXECUTION_ENV", Value = "ECS_FARGATE" },
                { Name = "LOADER_PARALLELISM", Value = "2" }
              ]
            }]
          }
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogAnalystEarningsEstimatesFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "ValueQualityGrowthMetrics"
      }

      LogAnalystEarningsEstimatesFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "analyst_earnings_estimates"
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
          Next        = "ValueQualityGrowthMetrics"
          ResultPath  = "$.logError"
        }]
        Next = "ValueQualityGrowthMetrics"
      }

      # ── PHASE 3 CONSOLIDATION: Value + Quality + Growth Metrics ──
      # CONSOLIDATED (Session 208): Merges 2 separate loaders into 1 atomic operation:
      # - Old: value_metrics (yfinance quoteSummary → PE/PB/PS/dividend)
      # - Old: quality_growth_metrics (financial statements → ROE/margins/growth)
      # - New: value_quality_growth_metrics (SEC + financials → all 3 tables atomically)
      #
      # Benefits:
      # - 1 ECS task instead of 2 (saves ~$0.01-0.02/run, -5-10 min runtime)
      # - Atomic operation (all 3 outputs succeed/fail together)
      # - Uses SEC-audited valuations (Phase 1) instead of yfinance estimates
      # - Better data quality: PE/PB/PS from SEC + audited financial metrics
      # - Single validation point (one error handler)
      # - Unified OptimalLoader framework
      #
      # Depends on: FinancialDataLoaders (financial statements), SecValuations
      # Outputs atomically to: value_metrics, quality_metrics, growth_metrics
      #
      # Timeout: value_metrics was 1800s + quality_metrics was 6600s = 8400s total;
      # consolidated run expected ~6600s (still limited by financials); 20% headroom → 4500s ✓
      ValueQualityGrowthMetrics = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 4500
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["value_quality_growth_metrics"]
          NetworkConfiguration = local.network_config
          Overrides = {
            ContainerOverrides = [{
              Name = "algo-value_quality_growth_metrics"
              Environment = [
                { Name = "AWS_EXECUTION_ENV", Value = "ECS_FARGATE" },
                { Name = "LOADER_PARALLELISM", Value = "2" }
              ]
            }]
          }
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogValueQualityGrowthFailure"
          ResultPath  = "$.loaderError"
        }]
        # FIX 2026-07-20: was "PositioningMetrics", which skips InstitutionalHoldings13F and
        # InsiderHoldingsSec entirely. Commit 5327a555b (Session 294) added those two states
        # "to restore the positioning metrics pipeline" but never repointed this predecessor's
        # Next at them - they were defined but structurally unreachable (nothing transitions
        # into InstitutionalHoldings13F), so institutional_holdings_13f has never actually been
        # populated by this pipeline since. Matches the live-DB finding that
        # institutional_ownership_pct is ~0% populated (2 of 4,826 stocks).
        Next = "EnhancedQualityGrowthMetrics"
      }

      LogValueQualityGrowthFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "value_quality_growth_metrics"
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
          Next        = "EnhancedQualityGrowthMetrics"
          ResultPath  = "$.logError"
        }]
        Next = "EnhancedQualityGrowthMetrics"
      }

      # ── FIXED 2026-08-03: enhanced quality/growth metrics (earnings_surprise_avg,
      # earnings_beat_rate, consecutive_positive_quarters, earnings_growth_4q_avg,
      # eps_growth_stability) - registered as a loader but never scheduled anywhere (see
      # terraform/modules/loaders/main.tf's loader_file_map comment). Must run AFTER
      # ValueQualityGrowthMetrics - it enhances that task's output rows in quality_metrics/
      # growth_metrics rather than writing a separate table (see
      # loaders/load_enhanced_quality_growth_metrics.py's module docstring). Without this,
      # every symbol showed "No data" for these 5 fields regardless of how much real SEC/
      # yfinance data existed. ──
      EnhancedQualityGrowthMetrics = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1200
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["enhanced_quality_growth_metrics"]
          NetworkConfiguration = local.network_config
          Overrides = {
            ContainerOverrides = [{
              Name = "algo-enhanced_quality_growth_metrics"
              Environment = [
                { Name = "AWS_EXECUTION_ENV", Value = "ECS_FARGATE" },
                { Name = "LOADER_PARALLELISM", Value = "2" }
              ]
            }]
          }
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogEnhancedQualityGrowthMetricsFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "CompanyInfoSec"
      }

      LogEnhancedQualityGrowthMetricsFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "enhanced_quality_growth_metrics"
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
          Next        = "CompanyInfoSec"
          ResultPath  = "$.logError"
        }]
        Next = "CompanyInfoSec"
      }

      # ── RESTORED 2026-07-20: Company Info + Earnings Calendar + FINRA Short Interest ──
      # All 3 registered "critical" in the ECS task-def catalog since Session 274/298 but never
      # wired into any Step Functions pipeline (confirmed via grep before this fix). Root cause
      # per steering/DATA_LOADERS.md: a `reference_data_pipeline` state machine used to trigger
      # company_info_sec/earnings_calendar_sec at 9:15 AM; Session 276 deleted it believing its
      # functionality was "merged into computed_metrics_pipeline" after the yfinance Phase 3
      # consolidation - true for value/quality/growth metrics, false for these two loaders (they
      # were never actually added here). short_interest_finra (Session 298) was added to the
      # task-def catalog with a pipeline step that was scaffolded but never finished.
      # Ordering: CompanyInfoSec provides shares_outstanding (SEC DEI) that
      # load_short_interest_finra.py needs to convert FINRA's raw share counts into short_pct -
      # run it first so same-day data is available. Local dev already runs this exact sequence
      # in scripts/local_loader_scheduler.py's "reference" + "morning" pipelines.
      CompanyInfoSec = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1800
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["company_info_sec"]
          NetworkConfiguration = local.network_config
          Overrides = {
            ContainerOverrides = [{
              Name = "algo-company_info_sec"
              Environment = [
                { Name = "AWS_EXECUTION_ENV", Value = "ECS_FARGATE" },
                { Name = "LOADER_PARALLELISM", Value = "2" }
              ]
            }]
          }
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogCompanyInfoSecFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "CompanyProfile"
      }

      LogCompanyInfoSecFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "company_info_sec"
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

      # ── RESTORED 2026-07-27: sector/industry classification (SIC->GICS), sourced from
      # CompanyInfoSec above, so it must run right after it. Deleted 2026-07-26 after being
      # judged "orphaned" by checking only for terraform wiring - it was never wired here in
      # the first place, while pretrade_checks.py (hard-blocks new entries without a
      # company_profile row) and circuit_breaker.py (sector-concentration/sector-drawdown
      # checks) kept depending on the table it feeds. Same failure mode this comment block
      # already documents for CompanyInfoSec/EarningsCalendarSec above.
      CompanyProfile = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 900
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["company_profile"]
          NetworkConfiguration = local.network_config
          Overrides = {
            ContainerOverrides = [{
              Name = "algo-company_profile"
              Environment = [
                { Name = "AWS_EXECUTION_ENV", Value = "ECS_FARGATE" },
                { Name = "LOADER_PARALLELISM", Value = "2" }
              ]
            }]
          }
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogCompanyProfileFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "EarningsCalendarSec"
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
          Next        = "EarningsCalendarSec"
          ResultPath  = "$.logError"
        }]
        Next = "EarningsCalendarSec"
      }

      EarningsCalendarSec = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1800
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["earnings_calendar_sec"]
          NetworkConfiguration = local.network_config
          Overrides = {
            ContainerOverrides = [{
              Name = "algo-earnings_calendar_sec"
              Environment = [
                { Name = "AWS_EXECUTION_ENV", Value = "ECS_FARGATE" },
                { Name = "LOADER_PARALLELISM", Value = "2" }
              ]
            }]
          }
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogEarningsCalendarSecFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "EarningsCalendar"
      }

      LogEarningsCalendarSecFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "earnings_calendar_sec"
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
          Next        = "EarningsCalendar"
          ResultPath  = "$.logError"
        }]
        Next = "EarningsCalendar"
      }

      # ── RESTORED 2026-08-04: real earnings announcement dates + EPS estimates/actuals
      # (distinct from EarningsCalendarSec above, which is SEC 10-K/10-Q *filing* dates).
      # Halt-critical in algo/orchestrator/phase1_data_freshness.py (earnings-blackout
      # gating via algo/risk/earnings_blackout.py) but had no active loader since
      # load_yfinance_derived_metrics.py was deleted 2026-07-19 - "believed superseded" by
      # EarningsCalendarSec, which doesn't actually carry earnings dates/EPS data. See
      # loaders/load_earnings_calendar.py's module docstring. ──
      EarningsCalendar = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1200
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["earnings_calendar"]
          NetworkConfiguration = local.network_config
          Overrides = {
            ContainerOverrides = [{
              Name = "algo-earnings_calendar"
              Environment = [
                { Name = "AWS_EXECUTION_ENV", Value = "ECS_FARGATE" },
                { Name = "LOADER_PARALLELISM", Value = "2" }
              ]
            }]
          }
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogEarningsCalendarFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "ShortInterestFinra"
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
          Next        = "ShortInterestFinra"
          ResultPath  = "$.logError"
        }]
        Next = "ShortInterestFinra"
      }

      # short_interest_finra clamped to parallelism 1 (steering/DATA_LOADERS.md: SEC/FINRA-facing
      # loaders are clamped 1-2 to protect rate limits) - matches its task-def catalog entry.
      ShortInterestFinra = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1800
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["short_interest_finra"]
          NetworkConfiguration = local.network_config
          Overrides = {
            ContainerOverrides = [{
              Name = "algo-short_interest_finra"
              Environment = [
                { Name = "AWS_EXECUTION_ENV", Value = "ECS_FARGATE" },
                { Name = "LOADER_PARALLELISM", Value = "1" }
              ]
            }]
          }
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogShortInterestFinraFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "InstitutionalHoldings13F"
      }

      LogShortInterestFinraFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "short_interest_finra"
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
          Next        = "InstitutionalHoldings13F"
          ResultPath  = "$.logError"
        }]
        Next = "InstitutionalHoldings13F"
      }

      # ── PHASE 3b: Institutional Holdings (SEC 13F) ──
      # CRITICAL DEPENDENCY: load_positioning_metrics.py reads from institutional_holdings_13f table
      # Must run BEFORE PositioningMetrics to ensure data available (fail-open if delayed)
      InstitutionalHoldings13F = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1800
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["institutional_holdings_13f"]
          NetworkConfiguration = local.network_config
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogInstitutionalHoldingsFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "InsiderHoldingsSec"
      }

      LogInstitutionalHoldingsFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "institutional_holdings_13f"
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
          Next        = "InsiderHoldingsSec"
          ResultPath  = "$.logError"
        }]
        Next = "InsiderHoldingsSec"
      }

      # ── PHASE 3c: Insider Holdings (SEC Form 4/5) ──
      # CRITICAL DEPENDENCY: load_positioning_metrics.py reads from insider_holdings_sec table
      # Must run BEFORE PositioningMetrics to ensure data available (fail-open if delayed)
      InsiderHoldingsSec = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1800
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["insider_holdings_sec"]
          NetworkConfiguration = local.network_config
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogInsiderHoldingsFailure"
          ResultPath  = "$.loaderError"
        }]
        # FIX 2026-07-28: same structurally-unreachable-state bug already documented
        # elsewhere in this file (SecCashFlowMetrics/SecSegmentInfo) - was
        # "PositioningMetrics", skipping InsiderTransactionVelocity entirely on the
        # success path even though only this state's OWN failure handler
        # (LogInsiderHoldingsFailure.Next below) pointed at it. Net effect:
        # InsiderTransactionVelocity only ran when InsiderHoldingsSec itself FAILED -
        # practically unreachable on any normal run.
        Next = "InsiderTransactionVelocity"
      }

      LogInsiderHoldingsFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "insider_holdings_sec"
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
          Next        = "InsiderTransactionVelocity"
          ResultPath  = "$.logError"
        }]
        Next = "InsiderTransactionVelocity"
      }

      # ── PHASE 3d: Insider Transaction Velocity (Session 444+) ──
      # Extracts insider confidence score from SEC Form 3/4/5 transaction counts
      # Detects insider buying sprees, executive departures, lockup periods
      # Uses same SEC bulk datasets as insider_holdings_sec (Form 3/4/5)
      InsiderTransactionVelocity = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1800
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["insider_transaction_velocity"]
          NetworkConfiguration = local.network_config
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogInsiderTransactionVelocityFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "CurrentReports8k"
      }

      LogInsiderTransactionVelocityFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "insider_transaction_velocity"
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
          Next        = "CurrentReports8k"
          ResultPath  = "$.logError"
        }]
        Next = "CurrentReports8k"
      }

      # ── SEC Form 8-K material events (Session 444: XBRL expansion) ──
      # FIX 2026-07-28: registered in terraform/modules/loaders/main.tf's task-def catalog
      # and critical_loaders since Session 444, and present in scripts/local_loader_scheduler.py,
      # but had ZERO Step Functions wiring anywhere in this file - never ran automatically in
      # production. Same "Class 3: registered but never wired in at all" bug already found and
      # fixed for company_info_sec/earnings_calendar_sec/short_interest_finra/sec_cash_flow_metrics.
      CurrentReports8k = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1800
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["current_reports_8k"]
          NetworkConfiguration = local.network_config
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogCurrentReports8kFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "DividendData"
      }

      LogCurrentReports8kFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "current_reports_8k"
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
          Next        = "DividendData"
          ResultPath  = "$.logError"
        }]
        Next = "DividendData"
      }

      # ── Dividend ex-dates/amounts, position management (Session 444: XBRL expansion) ──
      # FIX 2026-07-28: same never-wired-at-all gap as CurrentReports8k above - registered in
      # the task-def catalog and critical_loaders, never had a Step Functions state.
      DividendData = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1800
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["dividend_data"]
          NetworkConfiguration = local.network_config
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogDividendDataFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "PositioningMetrics"
      }

      LogDividendDataFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "dividend_data"
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

      # ── Positioning Metrics (writes institutional ownership, insider ownership, short interest) ──
      # FIXED Session 294: Added upstream dependencies InstitutionalHoldings13F + InsiderHoldingsSec.
      # Short interest is now optional (FINRA source broken). Positioning metrics will populate
      # with institutional + insider data when available, mark data_unavailable only if ALL sources missing.
      PositioningMetrics = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1800
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["positioning_metrics"]
          NetworkConfiguration = local.network_config
          Overrides = {
            ContainerOverrides = [{
              Name = "algo-positioning_metrics"
              Environment = [
                { Name = "AWS_EXECUTION_ENV", Value = "ECS_FARGATE" }
              ]
            }]
          }
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogPositioningMetricsFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "StabilityMetrics"
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
          Next        = "StabilityMetrics"
          ResultPath  = "$.logError"
        }]
        Next = "StabilityMetrics"
      }

      # ── Stability Metrics (independent of financial data) ──
      # FIXED 2026-07-15: Increase timeout from 3600s (1h) to 4200s (70m) — load_risk_metrics_daily
      # computes BOTH stability AND momentum metrics for 5000+ symbols (volatility + beta + momentum calculations).
      # Expected runtime 40-60 minutes; 4200s provides safe headroom per load_stock_scores.py analysis (Session 166).
      StabilityMetrics = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 4200
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["stability_metrics"]
          NetworkConfiguration = local.network_config
          Overrides = {
            ContainerOverrides = [{
              Name = "algo-stability_metrics"
              Environment = [
                { Name = "AWS_EXECUTION_ENV", Value = "ECS_FARGATE" }
              ]
            }]
          }
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
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
      # FIXED: Realistic timeout of 60 minutes (2x expected 30 min)
      StockScores = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 3600
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["stock_scores"]
          NetworkConfiguration = local.network_config
          Overrides = {
            ContainerOverrides = [{
              Name = "algo-stock_scores"
              Environment = [
                { Name = "AWS_EXECUTION_ENV", Value = "ECS_FARGATE" },
                { Name = "LOADER_PARALLELISM", Value = "2" }
              ]
            }]
          }
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 0
          BackoffRate     = 1.0
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
# ============================================================
# DEPRECATED: Intraday Update Pipelines removed
# REASON: swing_trader_scores loader deprecated. Phase 7 uses buy_sell_daily +
#         stock_scores for signal ranking. No intraday updates needed.
# ============================================================

# NOTE: The EventBridge Scheduler CloudWatch Log Group for this pipeline is owned by
# the loaders module (aws_cloudwatch_log_group.scheduler_logs) and passed in here via
# var.scheduler_log_group_arn. A duplicate resource used to be declared in this module
# too, with the identical log group name (/aws/scheduler/<project>-pipeline-<env>) — since
# it was never referenced by anything, it only served to collide with the loaders module's
# real resource on every terraform apply (CreateLogGroup: ResourceAlreadyExistsException).

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

    dead_letter_config {
      arn = var.scheduler_dlq_arn
    }
  }
}

# ============================================================
# DEPRECATED: Removed intraday scheduler triggers
# REASON: swing_trader_scores loader deprecated; intraday updates no longer needed
# ============================================================

# REMOVED: financial_data_pipeline_trigger scheduler
# REASON: Consolidated into main EOD pipeline (see comment above)

# ============================================================
# EventBridge Scheduler to trigger computed_metrics_pipeline
# ============================================================
# NOTE: Previously used aws_cloudwatch_event_rule with schedule_expression
# "cron(0 19 ? * MON-FRI *)". That resource type has no timezone support and
# always evaluates cron in UTC, so despite the "7:00 PM ET" comment it was
# actually firing at 19:00 UTC = 2-3 PM ET (depending on DST) -- hours before
# the EOD pipeline (4:05 PM ET) finishes writing that day's prices/technicals.
# Growth/quality/value/stability/stock_scores were therefore computed against
# stale/incomplete daily data. Fixed by using aws_scheduler_schedule, which
# supports schedule_expression_timezone, consistent with every other pipeline
# trigger in this file (morning, eod, financial-data, reference-data).

resource "aws_scheduler_schedule" "computed_metrics_pipeline_trigger" {
  name                         = "${var.project_name}-computed-metrics-pipeline-${var.environment}"
  description                  = "Daily computed metrics: quality/growth/value/stability/scores - 7:00 PM ET (after financial data completes)"
  schedule_expression          = "cron(0 19 ? * MON-FRI *)"
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

# DEPRECATED PIPELINE REMOVED (Session 276): reference_data_pipeline was empty after Phase 3 consolidation
# (yfinance_derived_metrics merged into computed_metrics_pipeline). The state machine and daily 9:15 AM
# scheduler were wasting $0.01-0.02/day in Step Functions overhead with zero functionality.

# FIXED: Force Terraform to re-create missing EOD scheduler (Session 157)
resource "aws_scheduler_schedule" "eod_pipeline_trigger" {
  name                         = "${var.project_name}-eod-pipeline-${var.environment}"
  description                  = "EOD pipeline: end-of-day analysis & swing scores (4:05 PM ET, 5 min after market close). Includes technical_data_daily loader."
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

    dead_letter_config {
      arn = var.scheduler_dlq_arn
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
