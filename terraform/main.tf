# ============================================================
# Root Module - Main Orchestration
# ============================================================

module "iam" {
  source = "./modules/iam"

  project_name    = var.project_name
  environment     = var.environment
  aws_region      = var.aws_region
  aws_account_id  = data.aws_caller_identity.current.account_id
  github_org      = local.github_org
  github_repo     = local.github_repo
  bastion_enabled = var.bastion_enabled
  common_tags     = local.common_tags
}

module "vpc" {
  source = "./modules/vpc"

  project_name         = var.project_name
  environment          = var.environment
  aws_region           = var.aws_region
  aws_account_id       = data.aws_caller_identity.current.account_id
  vpc_cidr             = var.vpc_cidr
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  availability_zones   = var.availability_zones
  bastion_sg_enabled   = var.bastion_enabled
  common_tags          = local.common_tags
}

module "storage" {
  source = "./modules/storage"

  project_name                = var.project_name
  environment                 = var.environment
  aws_region                  = var.aws_region
  aws_account_id              = data.aws_caller_identity.current.account_id
  enable_versioning           = var.enable_s3_versioning
  code_bucket_expiration_days = var.code_bucket_expiration_days
  data_bucket_expiration_days = var.data_bucket_expiration_days
  common_tags                 = local.common_tags
}

module "database" {
  source = "./modules/database"

  project_name                    = var.project_name
  environment                     = var.environment
  aws_region                      = var.aws_region
  aws_account_id                  = data.aws_caller_identity.current.account_id
  vpc_id                          = module.vpc.vpc_id
  private_subnet_ids              = module.vpc.private_subnet_ids
  rds_security_group_id           = module.vpc.rds_security_group_id
  db_instance_class               = var.rds_instance_class
  db_allocated_storage            = var.rds_allocated_storage
  db_max_allocated_storage        = var.rds_max_allocated_storage
  db_backup_retention_days        = var.rds_backup_retention_period
  db_master_username              = var.rds_username
  db_master_password              = var.rds_password
  rds_db_name                     = var.rds_db_name
  db_multi_az                     = false
  enable_rds_kms_encryption       = false
  rds_kms_key_id                  = null
  enable_rds_alarms               = var.environment != "dev"
  alarm_sns_topic_arn             = null
  rds_cpu_alarm_threshold         = 80
  rds_storage_alarm_threshold     = 10737418240
  rds_connections_alarm_threshold = 50
  notification_email              = var.notification_email
  cloudwatch_log_retention_days   = var.cloudwatch_log_retention_days
  common_tags                     = local.common_tags
}

module "compute" {
  source = "./modules/compute"

  project_name                           = var.project_name
  environment                            = var.environment
  aws_region                             = var.aws_region
  aws_account_id                         = data.aws_caller_identity.current.account_id
  vpc_id                                 = module.vpc.vpc_id
  public_subnet_ids                      = module.vpc.public_subnet_ids
  private_subnet_ids                     = module.vpc.private_subnet_ids
  bastion_security_group_id              = module.vpc.bastion_security_group_id
  ecs_tasks_security_group_id            = module.vpc.ecs_tasks_security_group_id
  bastion_instance_profile_name          = module.iam.bastion_instance_profile_name
  ecs_task_execution_role_arn            = module.iam.ecs_task_execution_role_arn
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

module "batch" {
  source = "./modules/batch"

  project_name                  = var.project_name
  environment                   = var.environment
  aws_region                    = var.aws_region
  aws_account_id                = data.aws_caller_identity.current.account_id
  vpc_id                        = module.vpc.vpc_id
  private_subnet_ids            = module.vpc.private_subnet_ids
  ecs_tasks_security_group_id   = module.vpc.ecs_tasks_security_group_id
  data_bucket_name              = module.storage.data_loading_bucket_name
  ecr_repository_uri            = module.compute.ecr_repository_url
  db_host                       = module.database.rds_endpoint
  db_port                       = 5432
  db_name                       = var.rds_db_name
  db_user                       = var.rds_username
  rds_secret_arn                = module.database.rds_credentials_secret_arn
  cloudwatch_log_retention_days = var.cloudwatch_log_retention_days
  batch_max_vcpus               = var.batch_max_vcpus
  batch_instance_types          = var.batch_instance_types
  batch_spot_bid_percentage     = var.batch_spot_bid_percentage
  common_tags                   = local.common_tags
}

module "loaders" {
  source = "./modules/loaders"

  project_name            = var.project_name
  environment             = var.environment
  aws_region              = var.aws_region
  aws_account_id          = data.aws_caller_identity.current.account_id
  ecs_cluster_name        = module.compute.ecs_cluster_name
  ecs_cluster_arn         = module.compute.ecs_cluster_arn
  task_execution_role_arn = module.iam.ecs_task_execution_role_arn
  private_subnet_ids      = module.vpc.private_subnet_ids
  ecs_tasks_sg_id         = module.vpc.ecs_tasks_security_group_id
  db_secret_arn           = module.database.rds_credentials_secret_arn
  ecr_repository_uri      = module.compute.ecr_repository_url
  vpc_id                  = module.vpc.vpc_id
  common_tags             = local.common_tags
}

module "services" {
  source = "./modules/services"

  project_name                   = var.project_name
  environment                    = var.environment
  aws_region                     = var.aws_region
  aws_account_id                 = data.aws_caller_identity.current.account_id
  vpc_id                         = module.vpc.vpc_id
  private_subnet_ids             = module.vpc.private_subnet_ids
  ecs_tasks_security_group_id    = module.vpc.ecs_tasks_security_group_id
  rds_endpoint                   = module.database.rds_endpoint
  rds_database_name              = module.database.rds_database_name
  rds_credentials_secret_arn     = module.database.rds_credentials_secret_arn
  frontend_bucket_name           = module.storage.frontend_bucket_name
  code_bucket_name               = module.storage.code_bucket_name
  data_loading_bucket_name       = module.storage.data_loading_bucket_name
  lambda_artifacts_bucket_name   = module.storage.lambda_artifacts_bucket_name
  api_lambda_memory              = var.api_lambda_memory
  api_lambda_timeout             = var.api_lambda_timeout
  api_lambda_ephemeral_storage   = var.api_lambda_ephemeral_storage
  api_lambda_role_arn            = module.iam.lambda_api_role_arn
  algo_lambda_memory             = var.algo_lambda_memory
  algo_lambda_timeout            = var.algo_lambda_timeout
  algo_lambda_ephemeral_storage  = var.algo_lambda_ephemeral_storage
  algo_lambda_role_arn           = module.iam.lambda_algo_role_arn
  eventbridge_scheduler_role_arn = module.iam.eventbridge_scheduler_role_arn
  api_gateway_stage_name         = var.api_gateway_stage_name
  api_gateway_logging_enabled    = var.api_gateway_logging_enabled
  api_cors_allowed_origins       = var.api_cors_allowed_origins
  cloudfront_enabled             = var.cloudfront_enabled
  cloudfront_cache_default_ttl   = var.cloudfront_cache_default_ttl
  cloudfront_cache_max_ttl       = var.cloudfront_cache_max_ttl
  cloudfront_waf_enabled         = var.cloudfront_waf_enabled
  cognito_enabled                = var.cognito_enabled
  cognito_user_pool_name         = var.cognito_user_pool_name
  cognito_password_min_length    = var.cognito_password_min_length
  cognito_mfa_configuration      = var.cognito_mfa_configuration
  cognito_session_duration_hours = var.cognito_session_duration_hours
  algo_schedule_expression       = var.algo_schedule_expression
  algo_schedule_enabled          = var.algo_schedule_enabled
  algo_schedule_timezone         = var.algo_schedule_timezone
  sns_alerts_enabled             = var.sns_alerts_enabled
  sns_alert_email                = var.sns_alert_email
  cloudwatch_log_retention_days  = var.cloudwatch_log_retention_days
  api_gateway_log_retention_days = var.api_gateway_log_retention_days
  api_lambda_code_file           = var.api_lambda_code_file
  algo_lambda_code_file          = var.algo_lambda_code_file
  common_tags                    = local.common_tags
}

module "monitoring" {
  source = "./modules/monitoring"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region
  common_tags  = local.common_tags

  # API & Lambda configuration
  api_lambda_name  = module.services.api_lambda_function_name
  algo_lambda_name = module.services.algo_lambda_function_name
  api_gateway_name = module.services.api_gateway_id

  # Database configuration
  rds_identifier = module.database.rds_identifier

  # Alarm configuration
  apigw_5xx_alarm_name         = "${var.project_name}-apigw-5xx-${var.environment}"
  api_lambda_errors_alarm_name = "${var.project_name}-api-${var.environment}-errors"
  sns_alerts_enabled           = var.sns_alerts_enabled
  sns_alerts_topic_arn         = coalesce(module.services.sns_alerts_topic_arn, "")
}

data "aws_caller_identity" "current" {}
