variable "project_name" { type = string }
variable "environment" { type = string }
variable "aws_account_id" { type = string; sensitive = true }
variable "aws_region" { type = string }
variable "code_bucket_name" { type = string }
variable "db_secret_arn" { type = string; sensitive = true }
variable "cognito_callback_urls" { type = list(string) }
variable "cognito_logout_urls" { type = list(string) }
variable "common_tags" { type = map(string) }
