// Step Functions state machines for dependency-driven data loading pipelines.
// Replaces EventBridge cron rules with guaranteed ordering: orchestrator runs only when
// all signal data is ready. Timeout strategy: expected + 2-3x safety margin, fail fast on real failures.

locals {
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
    StartAt = "CheckConcurrency"

    States = {
      # ── Mutual exclusion: skip this run if another execution of this same state ──
      # machine is already in flight (retried/overlapping trigger), instead of
      # launching a second set of ECS loader tasks in parallel with a running one.
      CheckConcurrency = {
        Type           = "Task"
        Resource       = "arn:aws:states:::aws-sdk:sfn:listExecutions"
        TimeoutSeconds = 30
        Parameters = {
          "StateMachineArn.$" = "$$.StateMachine.Id"
          StatusFilter        = "RUNNING"
        }
        ResultPath = "$.concurrencyCheck"
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 5
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        # Fail-open: if the guard itself can't run (IAM/API issue), proceed with the
        # pipeline rather than blocking all data loading over a broken safety check.
        Catch = [{
          ErrorEquals = ["States.ALL"]
          ResultPath  = "$.concurrencyCheckError"
          Next        = "CheckTradingDay"
        }]
        Next = "ConcurrencyGate"
      }

      # Own (still-running) execution always appears in the RUNNING list, so index [1]
      # being present means at least one OTHER execution is also running.
      ConcurrencyGate = {
        Type = "Choice"
        Choices = [{
          Variable  = "$.concurrencyCheck.Executions[1]"
          IsPresent = true
          Next      = "SkipAlreadyRunning"
        }]
        Default = "CheckTradingDay"
      }

      SkipAlreadyRunning = {
        Type    = "Succeed"
        Comment = "Another execution of this pipeline is already running; skipped to avoid duplicate ECS loader tasks."
      }

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
          Overrides = {
            ContainerOverrides = [{
              Name = "algo-stock_prices_daily"
              Environment = [
                { Name = "LOADER_INTERVALS", Value = "1d" },
                { Name = "LOADER_ASSET_CLASSES", Value = "stock,etf" },
                { Name = "LOADER_PARALLELISM", Value = "1" },
                { Name = "LOADER_CHUNK_SIZE", Value = "100" }
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
          IntervalSeconds = 60
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogTechDataFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "MarketHealthDaily"
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

      # ── Step 8b: Market Health Daily (depends on technical_data_daily) ──────────────
      # FIXED: Moved from ParallelEnrichment to sequential execution after TechnicalDataDaily.
      # market_health_daily._merge_breadth_data() requires technical_data_daily to be fresh.
      # Previously ran in parallel, causing "stale technical_data_daily" errors.
      # Now runs after technical_data_daily completes successfully.
      # Timeout: 1200s (20 minutes) for full data fetch.
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
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogMarketHealthFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "BuySellDaily"
      }

      LogMarketHealthFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "market_health_daily"
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
          Next        = "BuySellDaily"
          ResultPath  = "$.logError"
        }]
        Next = "BuySellDaily"
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
          IntervalSeconds = 60
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogMetricsFailureAfterSignals"
          ResultPath  = "$.loaderError"
        }]
        Next = "SectorRanking"
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
          Next        = "SectorRanking"
          ResultPath  = "$.logError"
        }]
        Next = "SectorRanking"
      }

      # ── Step 8c: Sector ranking (depends on stock_scores) ──────────────
      # CRITICAL: Must run before orchestrator to ensure Phase 3 and Phase 5 have current sector data.
      # Runs after swing_trader_scores completes. Timeout 900 seconds (15 minutes).
      # AUDIT FIX: Added industry_ranking and sector_performance loaders (2026-07-12)
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
        Next = "MarketExposureDaily"
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
        Next = "IndustryRanking"
      }

      # ── Step 8c-bis: Industry Ranking ──
      # Consolidation: sector_ranking and industry_ranking use same loader
      # Runs after sector_ranking (depends on stock_scores)
      IndustryRanking = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 900
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["industry_ranking"]
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
          Next        = "LogIndustryRankingFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "SectorPerformance"
      }

      LogIndustryRankingFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "industry_ranking"
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
          Next        = "SectorPerformance"
          ResultPath  = "$.logError"
        }]
        Next = "SectorPerformance"
      }

      # ── Step 8c-ter: Sector Performance ──
      # Calculates daily sector returns from weighted stock prices
      # Non-blocking: if timeout, continues to next stage
      SectorPerformance = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 900
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["sector_performance"]
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
          Next        = "LogSectorPerformanceFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "FredEconomicData"
      }

      LogSectorPerformanceFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "sector_performance"
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
        Next = "MarketExposureDaily"
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
          loader_name        = "market_exposure_daily"
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
        Next = "MarketSentiment"
      }

      # ── Step 8e-bis: Market Sentiment ──
      # Fear/greed index from VIX (lightweight enrichment)
      # Non-blocking: can timeout without affecting pipeline
      MarketSentiment = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 300
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["market_sentiment"]
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
          Next        = "LogMarketSentimentFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "DataPatrol"
      }

      LogMarketSentimentFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "market_sentiment"
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
# CONSOLIDATED: All 7 tables (earnings, company, analyst sentiment/upgrades) now loaded from single
# load_yfinance_derived_metrics.py loader which reads yfinance_snapshot once and writes to all 7 tables
# No dependencies (reads from cache, can fail gracefully)
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
    Comment = "Consolidated reference data: earnings, company profiles, analyst sentiment/upgrades from single yfinance_derived_metrics loader (reads snapshot once, writes to 7 tables)"
    StartAt = "CheckConcurrency"

    States = {
      # ── Mutual exclusion: skip this run if another execution of this same state ──
      # machine is already in flight (retried/overlapping trigger), instead of
      # launching a second set of ECS loader tasks in parallel with a running one.
      CheckConcurrency = {
        Type           = "Task"
        Resource       = "arn:aws:states:::aws-sdk:sfn:listExecutions"
        TimeoutSeconds = 30
        Parameters = {
          "StateMachineArn.$" = "$$.StateMachine.Id"
          StatusFilter        = "RUNNING"
        }
        ResultPath = "$.concurrencyCheck"
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 5
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        # Fail-open: if the guard itself can't run (IAM/API issue), proceed with the
        # pipeline rather than blocking all data loading over a broken safety check.
        Catch = [{
          ErrorEquals = ["States.ALL"]
          ResultPath  = "$.concurrencyCheckError"
          Next        = "YfinanceDerivedMetrics"
        }]
        Next = "ConcurrencyGate"
      }

      # Own (still-running) execution always appears in the RUNNING list, so index [1]
      # being present means at least one OTHER execution is also running.
      ConcurrencyGate = {
        Type = "Choice"
        Choices = [{
          Variable  = "$.concurrencyCheck.Executions[1]"
          IsPresent = true
          Next      = "SkipAlreadyRunning"
        }]
        Default = "YfinanceDerivedMetrics"
      }

      SkipAlreadyRunning = {
        Type    = "Succeed"
        Comment = "Another execution of this pipeline is already running; skipped to avoid duplicate ECS loader tasks."
      }

      # ── Consolidated Yfinance Derived Metrics ──
      # CONSOLIDATION: Combines 6 separate loaders into 1 that writes to all 7 tables:
      # - value_metrics (P/E, P/B, P/S, dividend yield, FCF yield, market cap)
      # - positioning_metrics (short interest)
      # - company_profile (sector, industry, country)
      # - analyst_sentiment_analysis (recommendation, analyst count)
      # - analyst_upgrade_downgrade (recommendation, analyst count)
      # - earnings_calendar (next earnings date)
      # - earnings_history (historical earnings dates)
      # Reads from yfinance_snapshot (pre-cached), parallelizes output writes
      YfinanceDerivedMetrics = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 7200
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
          Next        = "LogYfinanceDerivedMetricsFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "ReferenceDataSuccess"
      }

      LogYfinanceDerivedMetricsFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "yfinance_derived_metrics"
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
    StartAt = "CheckConcurrency"

    States = {
      # ── Mutual exclusion: skip this run if another execution of this same state ──
      # machine is already in flight (retried/overlapping trigger), instead of
      # launching a second set of ECS loader tasks in parallel with a running one.
      CheckConcurrency = {
        Type           = "Task"
        Resource       = "arn:aws:states:::aws-sdk:sfn:listExecutions"
        TimeoutSeconds = 30
        Parameters = {
          "StateMachineArn.$" = "$$.StateMachine.Id"
          StatusFilter        = "RUNNING"
        }
        ResultPath = "$.concurrencyCheck"
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 5
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        # Fail-open: if the guard itself can't run (IAM/API issue), proceed with the
        # pipeline rather than blocking all data loading over a broken safety check.
        Catch = [{
          ErrorEquals = ["States.ALL"]
          ResultPath  = "$.concurrencyCheckError"
          Next        = "CheckTradingDay"
        }]
        Next = "ConcurrencyGate"
      }

      # Own (still-running) execution always appears in the RUNNING list, so index [1]
      # being present means at least one OTHER execution is also running.
      ConcurrencyGate = {
        Type = "Choice"
        Choices = [{
          Variable  = "$.concurrencyCheck.Executions[1]"
          IsPresent = true
          Next      = "SkipAlreadyRunning"
        }]
        Default = "CheckTradingDay"
      }

      SkipAlreadyRunning = {
        Type    = "Succeed"
        Comment = "Another execution of this pipeline is already running; skipped to avoid duplicate ECS loader tasks."
      }

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
      # parallelism=1 (serial to prevent yfinance 429 rate limit errors); actual runtime 60-90 min with 5000+ symbols
      # Timeout: 4 hours (14400s). Morning pipeline runs 2:00-9:30 AM (450 min available).
      # 90min loader + 60min for technicals + 60min buffer = 210min needed; 240min timeout is safe.
      MorningPrices = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 14400
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
                { Name = "LOADER_CHUNK_SIZE", Value = "100" }
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
                Next = "SuccessMorningMarketHealth"
              }
              SuccessMorningMarketHealth = {
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
          Next        = "MorningTechnicalData"
          ResultPath  = "$.exposureError"
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

      # ── Morning sector ranking (depends on technical_data_daily) ──────────
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
    StartAt = "CheckConcurrency"

    States = {
      # ── Mutual exclusion: skip this run if another execution of this same state ──
      # machine is already in flight (retried/overlapping trigger), instead of
      # launching a second set of ECS loader tasks in parallel with a running one.
      CheckConcurrency = {
        Type           = "Task"
        Resource       = "arn:aws:states:::aws-sdk:sfn:listExecutions"
        TimeoutSeconds = 30
        Parameters = {
          "StateMachineArn.$" = "$$.StateMachine.Id"
          StatusFilter        = "RUNNING"
        }
        ResultPath = "$.concurrencyCheck"
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 5
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        # Fail-open: if the guard itself can't run (IAM/API issue), proceed with the
        # pipeline rather than blocking all data loading over a broken safety check.
        Catch = [{
          ErrorEquals = ["States.ALL"]
          ResultPath  = "$.concurrencyCheckError"
          Next        = "YFinanceSnapshot"
        }]
        Next = "ConcurrencyGate"
      }

      # Own (still-running) execution always appears in the RUNNING list, so index [1]
      # being present means at least one OTHER execution is also running.
      ConcurrencyGate = {
        Type = "Choice"
        Choices = [{
          Variable  = "$.concurrencyCheck.Executions[1]"
          IsPresent = true
          Next      = "SkipAlreadyRunning"
        }]
        Default = "YFinanceSnapshot"
      }

      SkipAlreadyRunning = {
        Type    = "Succeed"
        Comment = "Another execution of this pipeline is already running; skipped to avoid duplicate ECS loader tasks."
      }

      # ── Fetch yfinance snapshot once (all PE, PB, PS, dividend, beta, volatility for all symbols) ──
      # CRITICAL FIX 2026-07-02: Consolidated yfinance calls into single snapshot loader to fix rate limiting.
      # Fetches once per symbol, caches 24h. Eliminates 6x redundant API calls (value_metrics, positioning, stability).
      # Before: value_metrics parallelism=2 took 176 min due to rate limiting. After: 2h expected, reads from cache.
      YFinanceSnapshot = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 25200
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["yfinance_snapshot"]
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
          Next        = "LogYFinanceSnapshotFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "GrowthMetrics"
      }

      LogYFinanceSnapshotFailure = {
        Type     = "Task"
        Resource = var.loader_failure_handler_arn
        Parameters = {
          loader_name       = "yfinance_snapshot"
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
          Next        = "GrowthMetrics"
          ResultPath  = "$.logError"
        }]
        Next = "FinancialDataLoaders"
      }

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
          IntervalSeconds = 60
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "LogFinancialsFailure"
          ResultPath  = "$.loaderError"
        }]
        Next = "GrowthMetrics"
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
          Next        = "GrowthMetrics"
          ResultPath  = "$.logError"
        }]
        Next = "GrowthMetrics"
      }

      # ── Growth Metrics (depends on financial data) ──
      # FIXED: Realistic timeout of 110 minutes (2.7x expected 41 min max)
      # With parallelism=2, execution takes ~20-41 minutes; 6600s provides good detection of hangs
      GrowthMetrics = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 6600
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["growth_metrics"]
          NetworkConfiguration = local.network_config
          Overrides = {
            ContainerOverrides = [{
              Name = "algo-growth_metrics"
              Environment = [
                { Name = "LOADER_PARALLELISM", Value = "2" }
              ]
            }]
          }
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
      # FIXED: Realistic timeout of 110 minutes (2.7x expected 41 min max)
      # With parallelism=2, execution takes ~20-41 minutes; 6600s provides good detection of hangs
      QualityMetrics = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 6600
        Parameters = {
          Cluster              = var.ecs_cluster_arn
          LaunchType           = "FARGATE"
          TaskDefinition       = var.loader_task_definition_arns["quality_metrics"]
          NetworkConfiguration = local.network_config
          Overrides = {
            ContainerOverrides = [{
              Name = "algo-quality_metrics"
              Environment = [
                { Name = "LOADER_PARALLELISM", Value = "2" }
              ]
            }]
          }
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
      # FIXED 2026-07-02: Now reads from yfinance_snapshot table (consolidated fetch) instead of calling yfinance.
      # Timeout reduced from 21600s (6h) to 1800s (30m) since it's just DB reads, not API calls.
      # Previous timeout was needed because yfinance rate limiting caused ~176 min delays. That's now eliminated.
      ValueMetrics = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 1800
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
      # FIXED: Increase timeout from 1800s (30m) to 3600s (1h) to safely compute volatility and beta for all 5000+ symbols
      StabilityMetrics = {
        Type           = "Task"
        Resource       = "arn:aws:states:::ecs:runTask.sync"
        TimeoutSeconds = 3600
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
                { Name = "LOADER_PARALLELISM", Value = "2" }
              ]
            }]
          }
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

resource "aws_scheduler_schedule" "reference_data_pipeline_trigger" {
  name                         = "${var.project_name}-reference-data-pipeline-${var.environment}"
  description                  = "Daily reference data: earnings calendar/history, company profile, analyst sentiment - 9:15 AM ET"
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
