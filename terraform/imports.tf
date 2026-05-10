# ============================================================
# Terraform Import Blocks
# Resources that already exist in AWS from prior deployments
# and need to be adopted into Terraform state.
# ============================================================

# Bootstrap resources
import {
  to = module.bootstrap.aws_s3_bucket.terraform_state
  id = "stocks-terraform-state"
}

import {
  to = module.bootstrap.aws_dynamodb_table.terraform_locks
  id = "stocks-terraform-locks"
}

import {
  to = module.bootstrap.aws_iam_openid_connect_provider.github
  id = "arn:aws:iam::626216981288:oidc-provider/token.actions.githubusercontent.com"
}

# Compute
import {
  to = module.compute.aws_ecr_repository.main
  id = "algo-registry"
}

import {
  to = module.compute.aws_cloudwatch_log_group.ecs
  id = "/ecs/algo-cluster"
}

# IAM roles
import {
  to = module.iam.aws_iam_role.ecs_task_execution
  id = "algo-ecs-task-execution-dev"
}

import {
  to = module.iam.aws_iam_role.ecs_task
  id = "algo-ecs-task-dev"
}

import {
  to = module.iam.aws_iam_role.github_actions
  id = "algo-svc-github-actions-dev"
}

import {
  to = module.iam.aws_iam_role.lambda_api
  id = "algo-lambda-api-dev"
}

import {
  to = module.iam.aws_iam_role.lambda_algo
  id = "algo-lambda-algo-dev"
}

import {
  to = module.iam.aws_iam_role.eventbridge_scheduler
  id = "algo-eventbridge-scheduler-dev"
}

# Database
import {
  to = module.database.aws_iam_role.rds_monitoring
  id = "algo-svc-rds-monitoring-dev"
}

import {
  to = module.database.aws_secretsmanager_secret.db_credentials
  id = "arn:aws:secretsmanager:us-east-1:626216981288:secret:algo-db-credentials-dev-naPanX"
}

import {
  to = module.database.aws_secretsmanager_secret.rds_credentials
  id = "arn:aws:secretsmanager:us-east-1:626216981288:secret:algo/rds-db-credentials-dev-2hv7Gk"
}

import {
  to = module.database.aws_secretsmanager_secret.algo_secrets
  id = "arn:aws:secretsmanager:us-east-1:626216981288:secret:algo-algo-secrets-dev-36hejT"
}

import {
  to = module.database.aws_secretsmanager_secret.email_config
  id = "arn:aws:secretsmanager:us-east-1:626216981288:secret:algo-email-config-dev-cCR257"
}

# Storage buckets
import {
  to = module.storage.aws_s3_bucket.code
  id = "algo-code-626216981288"
}

import {
  to = module.storage.aws_s3_bucket.data_loading
  id = "algo-data-loading-626216981288"
}

import {
  to = module.storage.aws_s3_bucket.frontend
  id = "algo-frontend-626216981288"
}

import {
  to = module.storage.aws_s3_bucket.lambda_artifacts
  id = "algo-lambda-artifacts-626216981288"
}

import {
  to = module.storage.aws_s3_bucket.log_archive
  id = "algo-log-archive-626216981288"
}

# Batch
import {
  to = module.batch.aws_cloudwatch_log_group.batch
  id = "/aws/batch/algo"
}

import {
  to = module.batch.aws_iam_role.batch_service_role
  id = "algo-batch-service-role"
}

import {
  to = module.batch.aws_iam_role.batch_ecs_instance_role
  id = "algo-batch-ecs-instance-role"
}

import {
  to = module.batch.aws_iam_role.batch_job_role
  id = "algo-batch-job-role"
}

import {
  to = module.batch.aws_iam_role.batch_spot_fleet_role
  id = "algo-batch-spot-fleet-role"
}

import {
  to = module.batch.aws_iam_instance_profile.batch_ecs_instance_profile
  id = "algo-batch-ecs-instance-profile"
}

# Loaders IAM role
import {
  to = module.loaders.aws_iam_role.eventbridge_run_task
  id = "algo-svc-eventbridge-run-task-dev"
}

# Loader CloudWatch log groups
import {
  to = module.loaders.aws_cloudwatch_log_group.loader["aaiidata"]
  id = "/ecs/algo-aaiidata-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["algo_metrics_daily"]
  id = "/ecs/algo-algo_metrics_daily-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["analyst_sentiment"]
  id = "/ecs/algo-analyst_sentiment-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["analyst_upgrades"]
  id = "/ecs/algo-analyst_upgrades-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["calendar"]
  id = "/ecs/algo-calendar-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["earnings_history"]
  id = "/ecs/algo-earnings_history-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["earnings_revisions"]
  id = "/ecs/algo-earnings_revisions-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["earnings_sp500"]
  id = "/ecs/algo-earnings_sp500-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["earnings_surprise"]
  id = "/ecs/algo-earnings_surprise-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["econ_data"]
  id = "/ecs/algo-econ_data-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["etf_prices_daily"]
  id = "/ecs/algo-etf_prices_daily-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["etf_prices_monthly"]
  id = "/ecs/algo-etf_prices_monthly-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["etf_prices_weekly"]
  id = "/ecs/algo-etf_prices_weekly-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["etf_signals"]
  id = "/ecs/algo-etf_signals-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["factor_metrics"]
  id = "/ecs/algo-factor_metrics-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["feargreed"]
  id = "/ecs/algo-feargreed-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["financials_annual_balance"]
  id = "/ecs/algo-financials_annual_balance-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["financials_annual_cashflow"]
  id = "/ecs/algo-financials_annual_cashflow-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["financials_annual_income"]
  id = "/ecs/algo-financials_annual_income-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["financials_quarterly_balance"]
  id = "/ecs/algo-financials_quarterly_balance-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["financials_quarterly_cashflow"]
  id = "/ecs/algo-financials_quarterly_cashflow-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["financials_quarterly_income"]
  id = "/ecs/algo-financials_quarterly_income-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["financials_ttm_cashflow"]
  id = "/ecs/algo-financials_ttm_cashflow-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["financials_ttm_income"]
  id = "/ecs/algo-financials_ttm_income-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["market_indices"]
  id = "/ecs/algo-market_indices-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["market_overview"]
  id = "/ecs/algo-market_overview-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["naaim_data"]
  id = "/ecs/algo-naaim_data-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["relative_performance"]
  id = "/ecs/algo-relative_performance-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["seasonality"]
  id = "/ecs/algo-seasonality-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["sector_performance"]
  id = "/ecs/algo-sector_performance-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["signals_daily"]
  id = "/ecs/algo-signals_daily-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["signals_etf_daily"]
  id = "/ecs/algo-signals_etf_daily-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["signals_monthly"]
  id = "/ecs/algo-signals_monthly-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["signals_weekly"]
  id = "/ecs/algo-signals_weekly-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["social_sentiment"]
  id = "/ecs/algo-social_sentiment-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["stock_prices_daily"]
  id = "/ecs/algo-stock_prices_daily-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["stock_prices_monthly"]
  id = "/ecs/algo-stock_prices_monthly-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["stock_prices_weekly"]
  id = "/ecs/algo-stock_prices_weekly-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["stock_scores"]
  id = "/ecs/algo-stock_scores-loader"
}

import {
  to = module.loaders.aws_cloudwatch_log_group.loader["stock_symbols"]
  id = "/ecs/algo-stock_symbols-loader"
}

# Services
import {
  to = module.services.aws_cloudwatch_log_group.api_lambda
  id = "/aws/lambda/algo-api-dev"
}

import {
  to = module.services.aws_cloudwatch_log_group.algo_lambda
  id = "/aws/lambda/algo-algo-dev"
}

import {
  to = module.services.aws_cloudwatch_log_group.api_gateway[0]
  id = "/aws/apigateway/algo-api-dev"
}

import {
  to = module.services.aws_cloudfront_origin_access_control.frontend[0]
  id = "EPY7BSPGY853S"
}

# module.services.aws_apigatewayv2_authorizer.cognito[0]
# Authorizer does not exist in the Terraform-managed API (2iqq1qhltj);
# it will be created fresh by Terraform.
