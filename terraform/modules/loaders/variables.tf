variable "project_name" { type = string }
variable "environment" { type = string }
variable "aws_account_id" {
  type = string
  sensitive = true
}
variable "aws_region" { type = string }
variable "ecr_repository_uri" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "ecs_cluster_name" { type = string }
variable "ecs_cluster_arn" { type = string }
variable "db_secret_arn" {
  type = string
  sensitive = true
}
variable "ecs_tasks_sg_id" { type = string }
variable "task_execution_role_arn" { type = string }
variable "common_tags" { type = map(string) }
