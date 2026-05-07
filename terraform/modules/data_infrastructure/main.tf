/**
 * Data Infrastructure Module - RDS, ECS Cluster, Secrets Manager
 *
 * Creates:
 * - RDS PostgreSQL database
 * - ECS cluster for task runners
 * - Secrets Manager for database credentials
 * - CloudWatch alarms for monitoring
 * - IAM roles for ECS task execution
 * - Security groups (if not provided from core module)
 */

# Create security groups if not provided from core module
resource "aws_security_group" "rds" {
  count       = var.rds_sg_id == null ? 1 : 0
  name        = "${var.project_name}-rds-sg"
  description = "Security group for RDS database"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
  }

  tags = merge(
    var.common_tags,
    { Name = "${var.project_name}-rds-sg" }
  )
}

resource "aws_security_group" "ecs_tasks" {
  count       = var.ecs_tasks_sg_id == null ? 1 : 0
  name        = "${var.project_name}-ecs-tasks-sg"
  description = "Security group for ECS tasks"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 0
    to_port     = 65535
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    var.common_tags,
    { Name = "${var.project_name}-ecs-tasks-sg" }
  )
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = merge(
    var.common_tags,
    { Name = "${var.project_name}-db-subnet-group" }
  )
}

resource "aws_db_instance" "main" {
  identifier            = "${var.project_name}-db"
  allocated_storage    = var.db_allocated_storage
  storage_type         = "gp2"
  engine                = "postgres"
  engine_version        = "14"
  instance_class        = var.db_instance_class
  db_name               = var.db_name
  username              = var.db_user
  password              = var.db_password
  db_subnet_group_name  = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.rds_sg_id != null ? var.rds_sg_id : aws_security_group.rds[0].id]

  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.project_name}-final-snapshot-${formatdate("YYYY-MM-DD-hhmm", timestamp())}"
  backup_retention_period   = 7
  multi_az                  = false  # Set to true for production
  publicly_accessible       = false
  storage_encrypted         = true

  tags = merge(
    var.common_tags,
    { Name = "${var.project_name}-db" }
  )
}

# Secrets Manager for database credentials
resource "aws_secretsmanager_secret" "db_secret" {
  name                    = "${var.project_name}-db-secret-${random_string.secret_suffix.result}"
  recovery_window_in_days = 7

  tags = merge(
    var.common_tags,
    { Name = "${var.project_name}-db-secret" }
  )
}

resource "random_string" "secret_suffix" {
  length  = 8
  special = false
}

resource "aws_secretsmanager_secret_version" "db_secret" {
  secret_id = aws_secretsmanager_secret.db_secret.id
  secret_string = jsonencode({
    username = var.db_user
    password = var.db_password
    engine   = "postgres"
    host     = aws_db_instance.main.address
    port     = aws_db_instance.main.port
    dbname   = var.db_name
  })
}

# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = merge(
    var.common_tags,
    { Name = "${var.project_name}-cluster" }
  )
}

# ECS Cluster Capacity Providers
resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    base              = 1
    weight            = 100
    capacity_provider = "FARGATE"
  }
}

# ECS Task Execution Role
resource "aws_iam_role" "ecs_task_execution_role" {
  name = "${var.project_name}-ecs-task-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(
    var.common_tags,
    { Name = "${var.project_name}-ecs-task-execution-role" }
  )

}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_role_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow task to read from Secrets Manager
resource "aws_iam_role_policy" "ecs_task_secrets" {
  name = "${var.project_name}-ecs-task-secrets"
  role = aws_iam_role.ecs_task_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "kms:Decrypt"
        ]
        Resource = aws_secretsmanager_secret.db_secret.arn
      }
    ]
  })
}

# CloudWatch Alarms
resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "${var.project_name}-rds-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = "300"
  statistic           = "Average"
  threshold           = "80"
  alarm_description   = "Alert when RDS CPU exceeds 80%"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.identifier
  }
}

resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-alerts"

  tags = merge(
    var.common_tags,
    { Name = "${var.project_name}-alerts" }
  )

}

resource "aws_sns_topic_subscription" "alerts" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.notification_email
}
