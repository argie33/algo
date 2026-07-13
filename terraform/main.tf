# ============================================================
# Root Module - Main Orchestration
# ============================================================

module "iam" {
  source = "./modules/iam"

  project_name                = var.project_name
  environment                 = var.environment
  aws_region                  = var.aws_region
  aws_account_id              = local.aws_account_id
  github_org                  = local.github_org
  github_repo                 = local.github_repo
  bastion_enabled             = var.bastion_enabled
  data_bucket_name            = module.storage.data_loading_bucket_name
  developer_key_rotation_date = var.developer_key_rotation_date
  common_tags                 = local.common_tags
}

module "vpc" {
  source = "./modules/vpc"

  project_name         = var.project_name
  environment          = var.environment
  aws_region           = var.aws_region
  aws_account_id       = local.aws_account_id
  vpc_cidr             = var.vpc_cidr
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  availability_zones   = var.availability_zones
  bastion_sg_enabled   = var.bastion_enabled
  enable_vpc_endpoints = var.enable_vpc_endpoints
  dev_machine_cidr     = var.dev_machine_cidr
  common_tags          = local.common_tags
}

module "storage" {
  source = "./modules/storage"

  project_name                             = var.project_name
  environment                              = var.environment
  aws_region                               = var.aws_region
  aws_account_id                           = local.aws_account_id
  enable_versioning                        = var.enable_s3_versioning
  code_bucket_expiration_days              = var.code_bucket_expiration_days
  data_bucket_expiration_days              = var.data_bucket_expiration_days
  log_archive_transition_ia_days           = var.log_archive_transition_ia_days
  log_archive_transition_glacier_days      = var.log_archive_transition_glacier_days
  log_archive_transition_deep_archive_days = var.log_archive_transition_deep_archive_days
  log_archive_expiration_days              = var.log_archive_expiration_days
  log_archive_intelligent_tiering_enabled  = var.log_archive_intelligent_tiering_enabled
  encryption_kms_key_id                    = var.s3_encryption_kms_key_id
  enforce_kms_encryption                   = var.enforce_s3_kms_encryption
  common_tags                              = local.common_tags
}

resource "random_password" "jwt_secret" {
  count            = var.jwt_secret == "" ? 1 : 0
  length           = 64
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
  min_upper        = 8
  min_lower        = 8
  min_numeric      = 8
  min_special      = 8

  lifecycle {
    ignore_changes = all
  }
}

# REMOVED: Dead code cleanup (2026-07-08)
# module "secrets" was creating 5 unused secrets:
# - algo/alpaca (not referenced anywhere)
# - algo/fred (not referenced anywhere)
# - algo/database (not referenced anywhere)
# - algo/jwt (not referenced anywhere)
# - algo/orchestrator (not referenced anywhere)
#
# System uses module.database secrets exclusively:
# - database.algo_secrets_arn (Alpaca API keys)
# - database.rds_credentials_secret_arn (RDS)
# - database.email_config_secret_arn (SMTP)
#
# Cost savings: $2.00/month ($0.40 × 5 secrets)
# Code cleanup: Removes unused module and terraform references

# FIXED F-07: Staging environment isolation
# Create separate database module for staging to prevent data corruption on production RDS
module "database" {
  source = "./modules/database"

  project_name                    = var.project_name
  environment                     = var.environment
  aws_region                      = var.aws_region
  aws_account_id                  = local.aws_account_id
  vpc_id                          = module.vpc.vpc_id
  private_subnet_ids              = module.vpc.private_subnet_ids
  public_subnet_ids               = module.vpc.public_subnet_ids
  rds_security_group_id           = module.vpc.rds_security_group_id
  db_instance_class               = var.rds_instance_class
  db_allocated_storage            = var.rds_allocated_storage
  db_max_allocated_storage        = var.rds_max_allocated_storage
  db_backup_retention_days        = var.rds_backup_retention_period
  db_master_username              = var.rds_username
  rds_password                    = var.rds_password
  rds_db_name                     = var.rds_db_name
  db_multi_az                     = var.rds_multi_az
  enable_rds_kms_encryption       = var.enable_rds_kms_encryption
  rds_kms_key_id                  = var.rds_kms_key_alias != null ? "alias/${var.rds_kms_key_alias}" : null
  enable_rds_alarms               = var.enable_rds_alarms
  enable_resource_alarms          = var.enable_resource_alarms
  db_deletion_protection          = var.db_deletion_protection
  alarm_sns_topic_arn             = module.services.sns_alerts_topic_arn
  rds_cpu_alarm_threshold         = var.rds_cpu_alarm_threshold
  rds_storage_alarm_threshold     = var.rds_storage_alarm_threshold
  rds_connections_alarm_threshold = var.rds_connections_alarm_threshold
  rds_backup_window               = var.rds_backup_window
  rds_maintenance_window          = var.rds_maintenance_window
  notification_email              = var.notification_email
  alpaca_api_key_id               = var.alpaca_api_key_id
  alpaca_api_secret_key           = var.alpaca_api_secret_key
  alpaca_api_base_url             = var.alpaca_api_base_url
  alpaca_paper_trading            = var.alpaca_paper_trading
  cloudwatch_log_retention_days   = var.cloudwatch_log_retention_days
  jwt_secret                      = var.jwt_secret
  fred_api_key                    = var.fred_api_key
  execution_mode                  = var.execution_mode
  orchestrator_dry_run            = var.orchestrator_dry_run
  orchestrator_log_level          = var.orchestrator_log_level
  data_patrol_enabled             = var.data_patrol_enabled
  data_patrol_timeout_ms          = var.data_patrol_timeout_ms
  notification_email_from         = var.notification_email_from
  secrets_rotation_days           = var.secrets_rotation_days
  postgres_major_version          = var.postgres_major_version
  ecs_tasks_security_group_id     = module.vpc.ecs_tasks_security_group_id
  common_tags                     = local.common_tags
}

resource "aws_cloudwatch_log_group" "redis_cache" {
  name              = "/aws/elasticache/${var.project_name}-price-cache-${var.environment}"
  retention_in_days = 7

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-price-cache-logs"
  })
}

module "cache" {
  source = "./modules/cache"

  project_name                 = var.project_name
  environment                  = var.environment
  vpc_id                       = module.vpc.vpc_id
  private_subnet_ids           = module.vpc.private_subnet_ids
  ecs_task_security_group_id   = module.vpc.ecs_tasks_security_group_id
  cloudwatch_log_group_name    = aws_cloudwatch_log_group.redis_cache.name
  sns_alerts_enabled           = var.sns_alerts_enabled
  sns_alerts_topic_arn         = var.sns_alerts_topic_arn
  kms_key_id                   = var.s3_encryption_kms_key_id
  common_tags                  = local.common_tags

  depends_on = [module.vpc]
}

module "compute" {
  source = "./modules/compute"

  project_name                           = var.project_name
  environment                            = var.environment
  aws_region                             = var.aws_region
  aws_account_id                         = local.aws_account_id
  vpc_id                                 = module.vpc.vpc_id
  public_subnet_ids                      = module.vpc.public_subnet_ids
  private_subnet_ids                     = module.vpc.private_subnet_ids
  bastion_security_group_id              = module.vpc.bastion_security_group_id
  ecs_tasks_security_group_id            = module.vpc.ecs_tasks_security_group_id
  bastion_instance_profile_name          = module.iam.bastion_instance_profile_name
  ecs_task_execution_role_arn            = module.iam.ecs_task_execution_role_arn
  ecs_task_role_arn                      = module.iam.ecs_task_role_arn
  lambda_api_role_arn                    = module.iam.lambda_api_role_arn
  lambda_algo_role_arn                   = module.iam.lambda_algo_role_arn
  ecs_cluster_name                       = var.ecs_cluster_name
  ecs_capacity_providers                 = var.ecs_capacity_providers
  ecs_default_capacity_provider_strategy = var.ecs_default_capacity_provider_strategy
  bastion_enabled                        = var.bastion_enabled
  bastion_instance_type                  = var.bastion_instance_type
  bastion_shutdown_hour_utc              = var.bastion_shutdown_hour_utc
  bastion_shutdown_minute_utc            = var.bastion_shutdown_minute_utc
  ecr_repository_name                    = var.ecr_repository_name
  ecr_image_scan_enabled                 = var.ecr_image_scan_enabled
  ecr_image_tag_mutability               = var.ecr_image_tag_mutability
  cloudwatch_log_retention_days          = var.cloudwatch_log_retention_days
  enable_bastion_cloudwatch_logs         = var.enable_bastion_cloudwatch_logs
  common_tags                            = local.common_tags
}

module "loaders" {
  source = "./modules/loaders"

  project_name                = var.project_name
  environment                 = var.environment
  aws_region                  = var.aws_region
  aws_account_id              = local.aws_account_id
  ecs_cluster_name            = module.compute.ecs_cluster_name
  redis_endpoint_address      = module.cache.redis_endpoint_address
  redis_port                  = module.cache.redis_port
  ecs_cluster_arn             = module.compute.ecs_cluster_arn
  task_execution_role_arn     = module.iam.ecs_task_execution_role_arn
  task_role_arn               = module.iam.ecs_task_role_arn
  private_subnet_ids          = module.vpc.private_subnet_ids
  ecs_tasks_sg_id             = module.vpc.ecs_tasks_security_group_id
  db_secret_arn               = module.database.rds_credentials_secret_arn
  db_host                     = module.database.rds_proxy_address
  db_port                     = local.db_port
  db_ssl_mode                 = local.db_ssl_mode
  db_name                     = var.rds_db_name
  db_user                     = module.database.rds_username
  ecr_repository_uri          = module.compute.ecr_repository_url
  vpc_id                      = module.vpc.vpc_id
  common_tags                 = local.common_tags
  sns_alert_topic_arn         = coalesce(module.services.sns_alerts_topic_arn, "")
  fred_api_key                = var.fred_api_key
  algo_secrets_arn            = module.database.algo_secrets_arn
  alpaca_paper_trading        = var.alpaca_paper_trading
  alpaca_api_base_url         = var.alpaca_api_base_url
  execution_mode              = var.execution_mode
  orchestrator_dry_run        = var.orchestrator_dry_run
  orchestrator_log_level      = var.orchestrator_log_level
  backfill_days               = var.backfill_days
  disable_provenance_tracking = var.disable_provenance_tracking
  alert_email_to              = var.alert_email_to
  alert_webhook_url           = var.alert_webhook_url
  db_security_group_id        = module.vpc.rds_security_group_id
}

module "lambda_layers" {
  source = "./modules/lambda-layers"

  project_name               = var.project_name
  environment                = var.environment
  orchestrator_layer_enabled = false # Layers built but NOT published to AWS (would need separate publish step)
  api_layer_enabled          = false # Layers built but NOT published to AWS (would need separate publish step)
  common_tags                = local.common_tags
}

module "services" {
  source = "./modules/services"

  project_name                           = var.project_name
  environment                            = var.environment
  aws_region                             = var.aws_region
  aws_account_id                         = local.aws_account_id
  vpc_id                                 = module.vpc.vpc_id
  private_subnet_ids                     = module.vpc.private_subnet_ids
  ecs_tasks_security_group_id            = module.vpc.ecs_tasks_security_group_id
  api_lambda_security_group_id           = module.vpc.api_lambda_security_group_id
  algo_lambda_security_group_id          = module.vpc.algo_lambda_security_group_id
  rds_endpoint                           = module.database.rds_endpoint
  rds_proxy_address                      = module.database.rds_proxy_address
  rds_database_name                      = module.database.rds_database_name
  rds_credentials_secret_arn             = module.database.rds_credentials_secret_arn
  rds_password                           = module.database.rds_password
  rds_username                           = module.database.rds_username
  db_port                                = local.db_port
  db_ssl_mode                            = local.db_ssl_mode
  algo_secrets_arn                       = module.database.algo_secrets_arn
  psycopg2_layer_arn                     = module.database.psycopg2_layer_arn
  frontend_bucket_name                   = module.storage.frontend_bucket_name
  frontend_bucket_public_access_block_id = module.storage.frontend_bucket_public_access_block_id
  code_bucket_name                       = module.storage.code_bucket_name
  data_loading_bucket_name               = module.storage.data_loading_bucket_name
  lambda_artifacts_bucket_name           = module.storage.lambda_artifacts_bucket_name
  api_lambda_memory                      = var.api_lambda_memory
  api_lambda_timeout                     = var.api_lambda_timeout
  api_lambda_ephemeral_storage           = var.api_lambda_ephemeral_storage
  api_lambda_reserved_concurrency        = var.api_lambda_reserved_concurrency
  api_lambda_provisioned_concurrency     = var.api_lambda_provisioned_concurrency
  api_lambda_role_arn                    = module.iam.lambda_api_role_arn
  algo_lambda_memory                     = var.algo_lambda_memory
  algo_lambda_timeout                    = var.algo_lambda_timeout
  algo_lambda_reserved_concurrency       = var.algo_lambda_reserved_concurrency
  algo_lambda_ephemeral_storage          = var.algo_lambda_ephemeral_storage
  algo_lambda_role_arn                   = module.iam.lambda_algo_role_arn
  eventbridge_scheduler_role_arn         = module.iam.eventbridge_scheduler_role_arn
  api_gateway_stage_name                 = var.api_gateway_stage_name
  api_gateway_logging_enabled            = var.api_gateway_logging_enabled
  api_cors_allowed_origins               = local.cors_allowed_origins
  cloudfront_enabled                     = var.cloudfront_enabled
  cloudfront_cache_default_ttl           = var.cloudfront_cache_default_ttl
  cloudfront_cache_max_ttl               = var.cloudfront_cache_max_ttl
  cloudfront_waf_enabled                 = var.cloudfront_waf_enabled
  cognito_enabled                        = var.cognito_enabled
  cognito_user_pool_name                 = var.cognito_user_pool_name
  cognito_password_min_length            = var.cognito_password_min_length
  cognito_mfa_configuration              = var.cognito_mfa_configuration
  cognito_session_duration_hours         = var.cognito_session_duration_hours
  cognito_user_pool_id                   = module.cognito.user_pool_id
  cognito_client_id                      = module.cognito.user_pool_client_id
  algo_schedule_expression               = var.algo_schedule_expression
  algo_schedule_enabled                  = var.algo_schedule_enabled
  algo_schedule_timezone                 = var.algo_schedule_timezone
  enable_morning_orchestrator            = var.enable_morning_orchestrator
  sns_alerts_enabled                     = var.sns_alerts_enabled
  sns_alert_email                        = var.sns_alert_email
  cloudwatch_log_retention_days          = var.cloudwatch_log_retention_days
  api_gateway_log_retention_days         = var.api_gateway_log_retention_days
  api_lambda_code_file                   = var.api_lambda_code_file
  algo_lambda_code_file                  = var.algo_lambda_code_file
  alpaca_api_key_id                      = var.alpaca_api_key_id
  alpaca_api_secret_key                  = var.alpaca_api_secret_key
  alpaca_api_base_url                    = var.alpaca_api_base_url
  alpaca_paper_trading                   = var.alpaca_paper_trading
  jwt_secret                             = var.jwt_secret
  fred_api_key                           = var.fred_api_key
  execution_mode                         = var.execution_mode
  orchestrator_dry_run                   = var.orchestrator_dry_run
  orchestrator_log_level                 = var.orchestrator_log_level
  orchestrator_locks_table_name          = module.loaders.orchestrator_locks_table_name
  data_patrol_enabled                    = var.data_patrol_enabled
  data_patrol_timeout_ms                 = var.data_patrol_timeout_ms
  ecs_cluster_arn                        = module.compute.ecs_cluster_arn
  patrol_task_definition_arn             = module.loaders.data_patrol_task_definition_arn
  patrol_task_container_name             = "${var.project_name}-data-patrol"
  private_subnet_ids_for_patrol          = module.vpc.private_subnet_ids
  ecs_tasks_sg_id                        = module.vpc.ecs_tasks_security_group_id
  rds_port                               = module.database.rds_port
  rds_master_username                    = module.database.rds_username
  rds_subnet_ids                         = module.vpc.private_subnet_ids
  rds_security_group_id                  = module.vpc.rds_security_group_id
  enable_execution_monitor               = var.enable_execution_monitor
  enable_execution_monitor_schedule      = var.enable_execution_monitor_schedule
  algo_lambda_sg_id                      = module.vpc.algo_lambda_security_group_id
  node_env                               = local.node_env
  dev_mode                               = local.dev_mode
  alert_email_to                         = var.alert_email_to
  alert_webhook_url                      = var.alert_webhook_url
  alert_smtp_host                        = var.alert_smtp_host
  alert_smtp_port                        = var.alert_smtp_port
  alert_smtp_user                        = var.alert_smtp_user
  alert_smtp_password                    = var.alert_smtp_password
  alert_smtp_from                        = var.alert_smtp_from
  task_execution_role_arn                = module.iam.ecs_task_execution_role_arn
  task_role_arn                          = module.iam.ecs_task_role_arn
  api_lambda_layer_enabled               = false # Layers built but NOT published to AWS (would need separate publish step)
  allow_dev_tokens_test                  = var.allow_dev_tokens_test
  common_tags                            = local.common_tags
}

# CloudFront domain secret removed - was causing deletion state conflicts
# CloudFront domain is now retrieved directly from Terraform outputs instead

# IAM policy for CloudFront domain secret removed along with the secret

module "security_monitoring" {
  source = "./modules/security-monitoring"

  project_name = var.project_name
  environment  = var.environment
  vpc_id       = module.vpc.vpc_id
  aws_region   = var.aws_region

  cloudtrail_enabled            = var.cloudtrail_enabled
  guardduty_enabled             = var.guardduty_enabled
  aws_config_enabled            = var.aws_config_enabled
  vpc_flow_logs_enabled         = var.vpc_flow_logs_enabled
  cloudwatch_log_retention_days = var.cloudwatch_log_retention_days
  notification_email            = var.notification_email

  common_tags = local.common_tags
}

module "pipeline" {
  source = "./modules/pipeline"

  project_name                          = var.project_name
  environment                           = var.environment
  aws_region                            = var.aws_region
  aws_account_id                        = local.aws_account_id
  ecs_cluster_arn                       = module.compute.ecs_cluster_arn
  private_subnet_ids                    = module.vpc.private_subnet_ids
  ecs_tasks_sg_id                       = module.vpc.ecs_tasks_security_group_id
  task_execution_role_arn               = module.iam.ecs_task_execution_role_arn
  task_role_arn                         = module.iam.ecs_task_role_arn
  eventbridge_scheduler_role_arn        = module.iam.eventbridge_scheduler_role_arn
  loader_task_definition_arns           = module.loaders.loader_task_definition_arns
  algo_orchestrator_task_definition_arn = module.loaders.algo_orchestrator_task_definition_arn
  algo_orchestrator_container_name      = "${var.project_name}-algo-orchestrator"
  orchestrator_locks_table_name         = module.loaders.orchestrator_locks_table_name
  sns_alert_topic_arn                   = coalesce(module.services.sns_alerts_topic_arn, "")
  sns_alerts_enabled                    = var.sns_alerts_enabled
  cloudwatch_log_retention_days         = var.cloudwatch_log_retention_days
  execution_mode                        = var.execution_mode
  orchestrator_dry_run                  = var.orchestrator_dry_run
  orchestrator_log_level                = var.orchestrator_log_level
  db_host                               = module.database.rds_proxy_address
  db_port                               = local.db_port
  db_name                               = var.rds_db_name
  alpaca_paper_trading                  = var.alpaca_paper_trading
  loader_failure_handler_arn            = coalesce(module.services.loader_failure_handler_arn, "")
  ecs_log_group_name                    = module.compute.ecs_log_group_name
  patrol_task_definition_arn            = module.loaders.data_patrol_task_definition_arn
  scheduler_dlq_arn                     = module.loaders.scheduler_dlq_arn
  scheduler_log_group_arn               = module.loaders.scheduler_log_group_arn
  common_tags                           = local.common_tags
}

module "monitoring" {
  source = "./modules/monitoring"

  project_name   = var.project_name
  environment    = var.environment
  aws_region     = var.aws_region
  aws_account_id = local.aws_account_id
  common_tags    = local.common_tags

  # Network configuration
  vpc_id   = module.vpc.vpc_id
  vpc_cidr = var.vpc_cidr

  # API & Lambda configuration
  api_lambda_name  = module.services.api_lambda_function_name
  algo_lambda_name = module.services.algo_lambda_function_name
  api_gateway_name = module.services.api_gateway_id

  # Database configuration
  rds_identifier        = module.database.rds_identifier
  db_host               = module.database.rds_proxy_address
  db_port               = local.db_port
  db_ssl_mode           = local.db_ssl_mode
  db_user               = module.database.rds_username
  db_name               = module.database.rds_database_name
  db_password           = module.database.rds_password
  database_secret_arn   = module.database.rds_credentials_secret_arn
  private_subnet_ids    = module.vpc.private_subnet_ids
  rds_security_group_id = module.vpc.rds_security_group_id

  # Lambda layer for psycopg2 (needed by data freshness monitor)
  python_dependencies_layer_arn = module.database.psycopg2_layer_arn

  # Alarm configuration
  apigw_5xx_alarm_name           = "${var.project_name}-apigw-5xx-${var.environment}"
  api_lambda_errors_alarm_name   = "${var.project_name}-api-${var.environment}-errors"
  sns_alerts_enabled             = var.sns_alerts_enabled
  sns_alerts_topic_arn           = coalesce(module.services.sns_alerts_topic_arn, "")
  eventbridge_scheduler_role_arn = module.iam.eventbridge_scheduler_role_arn

  # Loader monitoring (F-04: CloudWatch alarms for 28+ supporting loaders)
  ecs_log_group_name  = module.pipeline.ecs_log_group_name
  ecs_cluster_arn     = module.compute.ecs_cluster_arn
  alert_email_to      = var.alert_email_to
  alert_email_address = var.alert_email_address

  # CloudWatch logs retention
  cloudwatch_log_retention_days = var.cloudwatch_log_retention_days

  # Cost optimization: alarm and monitor gating
  enable_performance_alarms    = var.enable_performance_alarms
  enable_resource_alarms       = var.enable_resource_alarms
  enable_data_quality_monitors = var.enable_data_quality_monitors

  # Cost circuit breaker configuration
  cost_threshold_daily_usd = var.cost_threshold_daily_usd
}

module "orchestration" {
  source = "./modules/orchestration"

  project_name          = var.project_name
  environment           = var.environment
  aws_region            = var.aws_region
  ecs_cluster_arn       = module.compute.ecs_cluster_arn
  private_subnet_ids    = module.vpc.private_subnet_ids
  ecs_security_group_id = module.vpc.ecs_tasks_security_group_id
  common_tags           = local.common_tags

  depends_on = [module.compute]
}

module "lifecycle" {
  source = "./modules/lifecycle"

  common_tags = local.common_tags
}

data "aws_caller_identity" "current" {}

# ============================================================
# Governance Module - Enforce IaC-only resource creation
# ============================================================
module "governance" {
  source = "./modules/governance"

  enforce_iac_only      = var.enforce_iac_only
  require_terraform_tag = var.require_terraform_tag
  aws_region            = var.aws_region
}
