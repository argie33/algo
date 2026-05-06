output "db_endpoint" {
  value     = aws_db_instance.main.address
  sensitive = true
}

output "db_port" {
  value = aws_db_instance.main.port
}

output "db_name" {
  value = aws_db_instance.main.db_name
}

output "db_secret_arn" {
  value     = aws_secretsmanager_secret.db_secret.arn
  sensitive = true
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "ecs_cluster_arn" {
  value = aws_ecs_cluster.main.arn
}

output "task_execution_role_arn" {
  value = aws_iam_role.ecs_task_execution_role.arn
}

output "ecs_tasks_sg_id" {
  value = var.ecs_tasks_sg_id
}

output "sns_topic_arn" {
  value = aws_sns_topic.alerts.arn
}
