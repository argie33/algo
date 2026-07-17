# ============================================================
# PHASE 1-4 VALIDATION STATE MACHINE
# ============================================================
# Runs new consolidated loaders in parallel with old loaders
# for 2-week validation before production switch-over
#
# Purpose: Validate data quality of new yfinance-elimination loaders
# Timeline: 2 weeks (2026-07-17 → 2026-07-31)
# Metrics: Compare sec_valuations vs value_metrics, etc.
#
# Once validation passes, merge Phase 1-4 loaders into main EOD pipeline

resource "aws_sfn_state_machine" "phases_1_4_validation_pipeline" {
  name     = "${var.project_name}-phases-1-4-validation-${var.environment}"
  role_arn = aws_iam_role.sfn_pipeline.arn
  type     = "STANDARD"

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn_pipeline.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  definition = jsonencode({
    Comment = "Phases 1-4 Validation: Run new consolidated loaders in parallel (validation mode)"
    StartAt = "ValidateMarketOpen"

    States = {
      # ── MARKET OPEN CHECK ──
      ValidateMarketOpen = {
        Type = "Pass"
        Next = "ParallelPhase1To4"
      }

      # ── PARALLEL: New Phase 1-4 Loaders + Old Loaders ──
      ParallelPhase1To4 = {
        Type = "Parallel"
        Next = "ValidationComplete"
        Branches = [
          # ── BRANCH 1: Phase 1 - SEC Valuations (NEW) ──
          {
            StartAt = "Phase1SecValuations"
            States = {
              Phase1SecValuations = {
                Type = "Task"
                Resource = "arn:aws:states:::ecs:runTask.sync"
                Parameters = {
                  LaunchType = "FARGATE"
                  Cluster = var.ecs_cluster_arn
                  TaskDefinition = var.loader_task_definition_arns["sec_valuations"]
                  NetworkConfiguration = {
                    AwsvpcConfiguration = {
                      Subnets = var.public_subnet_ids
                      SecurityGroups = [var.ecs_tasks_sg_id]
                      AssignPublicIp = "ENABLED"
                    }
                  }
                  Overrides = {
                    ContainerOverrides = [
                      {
                        Name = "${var.project_name}-sec_valuations"
                        Environment = [
                          { Name = "ENVIRONMENT", Value = var.environment }
                          { Name = "LOADER_PARALLELISM", Value = "2" }
                          { Name = "VALIDATION_MODE", Value = "true" }
                        ]
                      }
                    ]
                  }
                }
                TimeoutSeconds = 2100  # 35 min
                Catch = [
                  {
                    ErrorEquals = ["States.TaskFailed"]
                    Next = "Phase1Failed"
                    ResultPath = "$.phase1_error"
                  }
                ]
                End = true
              }
              Phase1Failed = {
                Type = "Fail"
                Error = "PHASE_1_FAILED"
                Cause = "Phase 1 (sec_valuations) loader failed. Check logs at /ecs/algo-sec_valuations-loader"
              }
            }
          }

          # ── BRANCH 2: Phase 2 - Market Status (NEW) ──
          {
            StartAt = "Phase2MarketStatus"
            States = {
              Phase2MarketStatus = {
                Type = "Task"
                Resource = "arn:aws:states:::ecs:runTask.sync"
                Parameters = {
                  LaunchType = "FARGATE"
                  Cluster = var.ecs_cluster_arn
                  TaskDefinition = var.loader_task_definition_arns["market_status_daily"]
                  NetworkConfiguration = {
                    AwsvpcConfiguration = {
                      Subnets = var.public_subnet_ids
                      SecurityGroups = [var.ecs_tasks_sg_id]
                      AssignPublicIp = "ENABLED"
                    }
                  }
                  Overrides = {
                    ContainerOverrides = [
                      {
                        Name = "${var.project_name}-market_status_daily"
                        Environment = [
                          { Name = "ENVIRONMENT", Value = var.environment }
                          { Name = "LOADER_PARALLELISM", Value = "1" }
                        ]
                      }
                    ]
                  }
                }
                TimeoutSeconds = 2100  # 35 min
                Catch = [
                  {
                    ErrorEquals = ["States.TaskFailed"]
                    Next = "Phase2Failed"
                    ResultPath = "$.phase2_error"
                  }
                ]
                End = true
              }
              Phase2Failed = {
                Type = "Fail"
                Error = "PHASE_2_FAILED"
                Cause = "Phase 2 (market_status_daily) loader failed. Outputs: market_health_daily + market_exposure_daily + market_sentiment"
              }
            }
          }

          # ── BRANCH 3: Phase 3 - Value/Quality/Growth (NEW) ──
          {
            StartAt = "Phase3ValueQualityGrowth"
            States = {
              Phase3ValueQualityGrowth = {
                Type = "Task"
                Resource = "arn:aws:states:::ecs:runTask.sync"
                Parameters = {
                  LaunchType = "FARGATE"
                  Cluster = var.ecs_cluster_arn
                  TaskDefinition = var.loader_task_definition_arns["value_quality_growth_metrics"]
                  NetworkConfiguration = {
                    AwsvpcConfiguration = {
                      Subnets = var.public_subnet_ids
                      SecurityGroups = [var.ecs_tasks_sg_id]
                      AssignPublicIp = "ENABLED"
                    }
                  }
                  Overrides = {
                    ContainerOverrides = [
                      {
                        Name = "${var.project_name}-value_quality_growth_metrics"
                        Environment = [
                          { Name = "ENVIRONMENT", Value = var.environment }
                          { Name = "LOADER_PARALLELISM", Value = "2" }
                          { Name = "VALIDATION_MODE", Value = "true" }
                        ]
                      }
                    ]
                  }
                }
                TimeoutSeconds = 5100  # 85 min
                Catch = [
                  {
                    ErrorEquals = ["States.TaskFailed"]
                    Next = "Phase3Failed"
                    ResultPath = "$.phase3_error"
                  }
                ]
                End = true
              }
              Phase3Failed = {
                Type = "Fail"
                Error = "PHASE_3_FAILED"
                Cause = "Phase 3 (value_quality_growth_metrics) loader failed. Depends on: sec_valuations + yfinance_snapshot"
              }
            }
          }

          # ── BRANCH 4: Phase 4 - Sector/Industry (NEW) ──
          {
            StartAt = "Phase4SectorIndustry"
            States = {
              Phase4SectorIndustry = {
                Type = "Task"
                Resource = "arn:aws:states:::ecs:runTask.sync"
                Parameters = {
                  LaunchType = "FARGATE"
                  Cluster = var.ecs_cluster_arn
                  TaskDefinition = var.loader_task_definition_arns["sector_industry_daily"]
                  NetworkConfiguration = {
                    AwsvpcConfiguration = {
                      Subnets = var.public_subnet_ids
                      SecurityGroups = [var.ecs_tasks_sg_id]
                      AssignPublicIp = "ENABLED"
                    }
                  }
                  Overrides = {
                    ContainerOverrides = [
                      {
                        Name = "${var.project_name}-sector_industry_daily"
                        Environment = [
                          { Name = "ENVIRONMENT", Value = var.environment }
                          { Name = "LOADER_PARALLELISM", Value = "1" }
                        ]
                      }
                    ]
                  }
                }
                TimeoutSeconds = 2100  # 35 min
                Catch = [
                  {
                    ErrorEquals = ["States.TaskFailed"]
                    Next = "Phase4Failed"
                    ResultPath = "$.phase4_error"
                  }
                ]
                End = true
              }
              Phase4Failed = {
                Type = "Fail"
                Error = "PHASE_4_FAILED"
                Cause = "Phase 4 (sector_industry_daily) loader failed. Consolidates: sector_performance + sector_ranking + industry_ranking"
              }
            }
          }
        ]
      }

      # ── VALIDATION COMPLETE ──
      ValidationComplete = {
        Type = "Pass"
        Next = "NotifyValidationComplete"
      }

      NotifyValidationComplete = {
        Type = "Task"
        Resource = var.sns_alert_topic_arn != "" ? "arn:aws:states:::sns:publish" : "arn:aws:states:::states:pass"
        Parameters = {
          Message = "Phases 1-4 validation pipeline completed successfully. Run validation metrics queries to compare new vs old loader data."
          TopicArn = var.sns_alert_topic_arn
        }
        End = true
      }
    }
  })

  tags = merge(var.common_tags, {
    Phase = "ValidationPipeline"
    Purpose = "Parallel validation of Phase 1-4 consolidated loaders"
  })
}

# ============================================================
# SCHEDULED TRIGGER: Run validation pipeline daily during validation period
# ============================================================
# Runs every day at 5:00 PM ET (22:00 UTC) during 2-week validation window
# After validation completes, delete this schedule and merge loaders into main EOD pipeline

resource "aws_scheduler_schedule" "phases_1_4_validation_daily" {
  name = "${var.project_name}-phases-1-4-validation-daily"
  schedule_expression = "cron(0 22 * * ? *)"  # 10 PM UTC = 5 PM ET
  timezone = "Etc/UTC"
  state = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn = aws_iam_role.eventbridge_scheduler_role.arn
    role_arn = aws_iam_role.eventbridge_scheduler_role.arn
    dead_letter_config {
      arn = var.scheduler_dlq_arn != "" ? var.scheduler_dlq_arn : null
    }

    step_functions_parameters {
      state_machine_arn = aws_sfn_state_machine.phases_1_4_validation_pipeline.arn
    }
  }

  tags = var.common_tags
}

# ============================================================
# OUTPUT: Validation Pipeline ARN (for monitoring + manual triggers)
# ============================================================
output "phases_1_4_validation_pipeline_arn" {
  description = "ARN of Phase 1-4 validation state machine (2-week parallel testing)"
  value = aws_sfn_state_machine.phases_1_4_validation_pipeline.arn
}

output "phases_1_4_validation_schedule_arn" {
  description = "ARN of EventBridge Scheduler for daily validation runs"
  value = aws_scheduler_schedule.phases_1_4_validation_daily.arn
}
