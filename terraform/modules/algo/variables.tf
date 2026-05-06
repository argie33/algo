variable "project_name" { type = string }
variable "environment" { type = string }
variable "aws_account_id" { type = string; sensitive = true }
variable "aws_region" { type = string }
variable "lambda_memory" { type = number }
variable "lambda_timeout" { type = number }
variable "algo_artifacts_bucket_name" { type = string }
variable "code_bucket_name" { type = string }
variable "db_secret_arn" { type = string; sensitive = true }
variable "common_tags" { type = map(string) }
