# ============================================================
# Database Module - RDS PostgreSQL + Secrets Manager
# ============================================================

# ============================================================
# 1. RDS Subnet Group (Private Subnets)
# ============================================================

resource "aws_db_subnet_group" "main" {
  name            = "${var.project_name}-db-subnet-group"
  description     = "Private subnet group for ${var.project_name} RDS"
  subnet_ids      = var.private_subnet_ids
  tags            = var.common_tags

  # Prevent accidental deletion
  lifecycle {
    prevent_destroy = true
  }
}

# ============================================================
# 2. RDS PostgreSQL Instance (Private, Retained)
# ============================================================

resource "aws_db_instance" "main" {
  identifier            = "${var.project_name}-db"
  db_name              = var.project_name
  engine               = "postgres"
  engine_version       = "13.7" # Widely available PostgreSQL version
  instance_class       = var.db_instance_class
  allocated_storage    = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage > 0 ? var.db_max_allocated_storage : null

  username               = var.db_master_username
  password               = var.db_master_password
  parameter_group_name   = aws_db_parameter_group.main.name
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.rds_security_group_id]

  # Backup & Recovery
  backup_retention_period = var.db_backup_retention_days
  backup_window          = "03:00-04:00"        # UTC (10 PM - 11 PM EST)
  maintenance_window     = "mon:04:00-mon:05:00" # UTC
  copy_tags_to_snapshot  = true

  # Performance & Optimization
  multi_az            = var.db_multi_az
  storage_type        = "gp3"
  iops                = 3000
  storage_throughput  = 125
  publicly_accessible = false # Private subnet, no public endpoint

  # Encryption
  storage_encrypted            = true
  kms_key_id                   = null # Use default AWS managed key
  iam_database_authentication_enabled = true

  # Monitoring & Logs
  enabled_cloudwatch_logs_exports = ["postgresql"] # Query logs to CloudWatch
  monitoring_interval             = 60
  monitoring_role_arn             = aws_iam_role.rds_monitoring.arn
  performance_insights_enabled     = false # Additional cost, disable for dev

  # Deletion Protection
  deletion_protection = false # Allow deletion, but backup is retained
  skip_final_snapshot = false
  final_snapshot_identifier = "${var.project_name}-db-final-snapshot-${var.environment}"

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-db"
  })

  # Prevent accidental destruction of data
  lifecycle {
    prevent_destroy = true
    ignore_changes = [
      password # Allow password changes outside Terraform
    ]
  }

  depends_on = [
    aws_db_subnet_group.main,
    aws_iam_role.rds_monitoring
  ]
}

# ============================================================
# 3. RDS Parameter Group (PostgreSQL 15 optimization)
# ============================================================

resource "aws_db_parameter_group" "main" {
  name        = "${var.project_name}-pg15-params"
  description = "PostgreSQL 15 parameter group for ${var.project_name}"
  family      = "postgres15"

  # Time-series optimization via BRIN indexes (CloudFormation note)
  parameter {
    name  = "log_statement"
    value = "all" # Log all statements (remove for prod)
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000" # Log queries > 1 second
  }

  tags = var.common_tags

  lifecycle {
    create_before_destroy = true
  }
}

# ============================================================
# 4. RDS Monitoring Role (CloudWatch Enhanced Monitoring)
# ============================================================

resource "aws_iam_role" "rds_monitoring" {
  name               = "${var.project_name}-rds-monitoring-role"
  assume_role_policy = data.aws_iam_policy_document.rds_monitoring_assume.json

  tags = var.common_tags
}

data "aws_iam_policy_document" "rds_monitoring_assume" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["monitoring.rds.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  role       = aws_iam_role.rds_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

# ============================================================
# 5. Secrets Manager - Database Credentials
# ============================================================

resource "aws_secretsmanager_secret" "rds_credentials" {
  name                    = "${var.project_name}-db-credentials-${var.environment}"
  description             = "RDS credentials for ${var.project_name}"
  recovery_window_in_days = 7

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-db-credentials"
  })
}

resource "aws_secretsmanager_secret_version" "rds_credentials" {
  secret_id = aws_secretsmanager_secret.rds_credentials.id
  secret_string = jsonencode({
    username = var.db_master_username
    password = var.db_master_password
    host     = aws_db_instance.main.endpoint
    port     = aws_db_instance.main.port
    dbname   = aws_db_instance.main.db_name
    engine   = "postgresql"
  })
}

# ============================================================
# 6. Secrets Manager - Email Configuration
# ============================================================

resource "aws_secretsmanager_secret" "email_config" {
  name                    = "${var.project_name}-email-config-${var.environment}"
  description             = "Email configuration for notifications"
  recovery_window_in_days = 7

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-email-config"
  })
}

resource "aws_secretsmanager_secret_version" "email_config" {
  secret_id = aws_secretsmanager_secret.email_config.id
  secret_string = jsonencode({
    contact_notification_email = var.notification_email
    email_from                = "noreply@bullseyefinancial.com"
  })
}

# ============================================================
# 7. Secrets Manager - Algo Runtime Secrets (Alpaca)
# ============================================================

resource "aws_secretsmanager_secret" "algo_secrets" {
  name                    = "${var.project_name}-algo-secrets-${var.environment}"
  description             = "Alpaca API credentials and algo runtime configuration"
  recovery_window_in_days = 7

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-algo-secrets"
  })
}

resource "aws_secretsmanager_secret_version" "algo_secrets" {
  secret_id = aws_secretsmanager_secret.algo_secrets.id
  secret_string = jsonencode({
    APCA_API_KEY_ID      = var.alpaca_api_key_id
    APCA_API_SECRET_KEY  = var.alpaca_api_secret_key
    APCA_API_BASE_URL    = var.alpaca_api_base_url
    ALPACA_PAPER_TRADING = var.alpaca_paper_trading
  })
}

# ============================================================
# 8. CloudWatch Log Groups for Database Logs
# ============================================================

resource "aws_cloudwatch_log_group" "rds_postgresql" {
  name              = "/aws/rds/instance/${aws_db_instance.main.id}/postgresql"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-rds-logs"
  })
}

# ============================================================
# 9. CloudWatch Alarms - RDS Monitoring
# ============================================================

resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  count               = var.enable_rds_alarms ? 1 : 0
  alarm_name          = "${var.project_name}-rds-cpu-high-${var.environment}"
  alarm_description   = "Alert when RDS CPU exceeds ${var.rds_cpu_alarm_threshold}%"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = "300"
  statistic           = "Average"
  threshold           = var.rds_cpu_alarm_threshold
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }

  tags = var.common_tags
}

resource "aws_cloudwatch_metric_alarm" "rds_storage" {
  count               = var.enable_rds_alarms ? 1 : 0
  alarm_name          = "${var.project_name}-rds-storage-low-${var.environment}"
  alarm_description   = "Alert when RDS free storage drops below 10GB"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = "300"
  statistic           = "Average"
  threshold           = var.rds_storage_alarm_threshold
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }

  tags = var.common_tags
}

resource "aws_cloudwatch_metric_alarm" "rds_connections" {
  count               = var.enable_rds_alarms ? 1 : 0
  alarm_name          = "${var.project_name}-rds-connections-high-${var.environment}"
  alarm_description   = "Alert when RDS active connections exceed ${var.rds_connections_alarm_threshold}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "DatabaseConnections"
  namespace           = "AWS/RDS"
  period              = "300"
  statistic           = "Average"
  threshold           = var.rds_connections_alarm_threshold
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }

  tags = var.common_tags
}
