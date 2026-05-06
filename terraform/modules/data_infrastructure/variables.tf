variable "project_name" { type = string }
variable "environment" { type = string }
variable "aws_account_id" { type = string; sensitive = true }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "ecs_cluster_subnet_ids" { type = list(string) }
variable "rds_sg_id" { type = string }
variable "db_name" { type = string }
variable "db_user" { type = string }
variable "db_password" { type = string; sensitive = true }
variable "db_instance_class" { type = string }
variable "db_allocated_storage" { type = number }
variable "ecs_instance_type" { type = string }
variable "ecs_min_capacity" { type = number }
variable "ecs_max_capacity" { type = number }
variable "notification_email" { type = string }
variable "common_tags" { type = map(string) }
