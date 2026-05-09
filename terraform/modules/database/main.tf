# ============================================================
# Database Module - RDS PostgreSQL + Secrets Manager
# ============================================================

# ============================================================
# 0. KMS Key for RDS Encryption (Production)
# ============================================================

resource "aws_kms_key" "rds" {
  count                   = var.enable_rds_kms_encryption ? 1 : 0
  description             = "KMS key for RDS encryption in ${var.environment}"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-rds-kms"
  })
}

resource "aws_kms_alias" "rds" {
  count         = var.enable_rds_kms_encryption ? 1 : 0
  name          = "alias/${var.project_name}-rds"
  target_key_id = aws_kms_key.rds[0].key_id
}

# ============================================================
# 1. RDS Subnet Group (Private Subnets)
# ============================================================

resource "aws_db_subnet_group" "main" {
  name        = "${var.project_name}-db-subnet-group"
  description = "Private subnet group for ${var.project_name} RDS"
  subnet_ids  = var.private_subnet_ids
  tags        = var.common_tags

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
  db_name               = var.rds_db_name
  engine                = "postgres"
  engine_version        = "14" # PostgreSQL 14
  instance_class        = var.db_instance_class
  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage > 0 ? var.db_max_allocated_storage : null

  username               = var.db_master_username
  password               = var.db_master_password
  parameter_group_name   = data.aws_db_parameter_group.main.name
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.rds_security_group_id]

  # Backup & Recovery
  backup_retention_period = var.db_backup_retention_days
  backup_window           = var.rds_backup_window
  maintenance_window      = var.rds_maintenance_window
  copy_tags_to_snapshot   = true

  # Performance & Optimization
  multi_az            = var.db_multi_az
  storage_type        = "gp2"
  publicly_accessible = false # Private subnet, no public endpoint

  # Encryption
  storage_encrypted                   = true
  kms_key_id                          = var.enable_rds_kms_encryption ? aws_kms_key.rds[0].id : null
  iam_database_authentication_enabled = true

  # Monitoring & Logs
  enabled_cloudwatch_logs_exports = ["postgresql"] # Query logs to CloudWatch
  monitoring_interval             = 60
  monitoring_role_arn             = aws_iam_role.rds_monitoring.arn
  performance_insights_enabled    = false # Additional cost, disable for dev

  # Deletion Protection
  deletion_protection = var.environment == "prod" ? true : false
  skip_final_snapshot = var.environment != "prod" # prod=false (takes snapshot), dev=true (skips)

  # CRITICAL: Always explicitly name final snapshots to prevent accidental loss
  final_snapshot_identifier = var.environment == "prod" ? "${var.project_name}-db-final-snapshot-${formatdate("YYYY-MM-DD-hhmm", timestamp())}" : null

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
# 3. RDS Parameter Group (PostgreSQL 14 + TimescaleDB optimization)
# ============================================================

# Use data source to reference existing parameter group (created in previous deployment)
# This avoids conflicts when re-running terraform
data "aws_db_parameter_group" "main" {
  name = "${var.project_name}-pg14-params"
}

# Local to use either existing or new parameter group
locals {
  db_parameter_group_name = try(data.aws_db_parameter_group.main.name, aws_db_parameter_group.main[0].name)
}

# Conditionally create parameter group only if it doesn't exist
resource "aws_db_parameter_group" "main" {
  count       = 0 # Disabled - managed via data source to avoid conflicts
  name        = "${var.project_name}-pg14-params"
  description = "PostgreSQL 14 parameter group for ${var.project_name} (TimescaleDB-enabled)"
  family      = "postgres14"

  tags = var.common_tags

  lifecycle {
    create_before_destroy = true
  }
}

# ============================================================
# 4. RDS Monitoring Role (CloudWatch Enhanced Monitoring)
# ============================================================

resource "aws_iam_role" "rds_monitoring" {
  name               = "${var.project_name}-svc-rds-monitoring-${var.environment}"
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
    email_from                 = "noreply@bullseyefinancial.com"
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

# ============================================================
# 10. Database Initialization (PostgreSQL Schema)
# ============================================================

# Create a local file from the init.sql template
resource "local_file" "db_init_script" {
  content  = file("${path.module}/init.sql")
  filename = "${path.module}/.terraform/db_init.sql"
}

# Run SQL initialization script after RDS instance is created
# This uses null_resource + local-exec with psql
resource "null_resource" "database_initialization" {
  provisioner "local-exec" {
    command = <<-EOT
      export PGPASSWORD="${var.db_master_password}"
      psql \
        -h "${aws_db_instance.main.address}" \
        -p ${aws_db_instance.main.port} \
        -U "${var.db_master_username}" \
        -d "${var.rds_db_name}" \
        -f "${path.module}/init.sql" \
        || echo "Note: Database initialization may need manual execution if psql is not available in CI/CD environment"
    EOT
  }

  depends_on = [
    aws_db_instance.main,
    local_file.db_init_script
  ]

  triggers = {
    db_instance_id = aws_db_instance.main.id
  }
}

# ============================================================
# RDS Proxy - Connection Pooling
# ============================================================
# Multiplexes many ECS task connections (40 loaders × 8 workers)
# down to a smaller pool of actual DB connections (~20-30).
# Cost: ~$0.015/hour for db.t3.micro
# Benefit: Prevents connection limit errors, automatic failover

# RDS Proxy security group, role, and policy - DISABLED
# TODO: Re-enable when RDS Proxy is implemented

# Store DB credentials in Secrets Manager for RDS Proxy to use
resource "aws_secretsmanager_secret" "db_credentials" {
  name                    = "${var.project_name}/rds-db-credentials-${var.environment}"
  description             = "RDS database credentials for connection pooling"
  recovery_window_in_days = 7

  tags = var.common_tags
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = var.db_master_username
    password = var.db_master_password
  })
}

# RDS Proxy - DISABLED FOR INITIAL DEPLOYMENT
# TODO: Re-enable after core infrastructure is stable
# Issues: invalid resource type (aws_db_proxy_target_group) doesn't exist in Terraform AWS provider
# RDS Proxy will be implemented in a future iteration using correct resource types

# ============================================================
# 11. Credential Rotation - RDS Database Passwords
# ============================================================
# Automatically rotate database credentials every 30 days
# Rotation happens in-place via RDS security group with no downtime
# Lambda function: rotate credentials in both RDS and Secrets Manager

# IAM Role for Rotation Lambda
resource "aws_iam_role" "rds_rotation" {
  name               = "${var.project_name}-rds-rotation-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.rds_rotation_assume.json

  tags = var.common_tags
}

data "aws_iam_policy_document" "rds_rotation_assume" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

# Allow Lambda to modify RDS password and read/write Secrets Manager
resource "aws_iam_role_policy" "rds_rotation" {
  name   = "${var.project_name}-rds-rotation-policy"
  role   = aws_iam_role.rds_rotation.id
  policy = data.aws_iam_policy_document.rds_rotation_policy.json
}

data "aws_iam_policy_document" "rds_rotation_policy" {
  statement {
    sid    = "SecretsManagerAccess"
    effect = "Allow"

    actions = [
      "secretsmanager:DescribeSecret",
      "secretsmanager:GetSecretValue",
      "secretsmanager:PutSecretValue",
      "secretsmanager:UpdateSecretVersionStage"
    ]

    resources = [
      aws_secretsmanager_secret.rds_credentials.arn,
      aws_secretsmanager_secret.db_credentials.arn
    ]
  }

  statement {
    sid    = "RDSPasswordModification"
    effect = "Allow"

    actions = [
      "rds-db:connect"
    ]

    resources = [
      "arn:aws:rds-db:${var.aws_region}:${var.aws_account_id}:dbuser:${aws_db_instance.main.resource_id}/*"
    ]
  }
}

# Attach VPC execution policy so Lambda can run in private subnet
resource "aws_iam_role_policy_attachment" "rds_rotation_vpc" {
  role       = aws_iam_role.rds_rotation.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# Lambda Layer for psycopg2 (PostgreSQL driver)
# Requires: python-psycopg2-layer.zip in module directory
# See LAMBDA_LAYER_SETUP.md for how to build
data "archive_file" "psycopg2_layer" {
  count       = fileexists("${path.module}/python-psycopg2-layer.zip") ? 1 : 0
  type        = "zip"
  source_dir  = "${path.module}/.psycopg2-layer"
  output_path = "${path.module}/.terraform/psycopg2-layer.zip"
}

resource "aws_lambda_layer_version" "psycopg2" {
  count                   = fileexists("${path.module}/python-psycopg2-layer.zip") ? 1 : 0
  filename                = data.archive_file.psycopg2_layer[0].output_path
  layer_name              = "${var.project_name}-psycopg2-layer-${var.environment}"
  compatible_runtimes     = ["python3.11"]
  source_code_hash        = data.archive_file.psycopg2_layer[0].output_base64sha256
  compatible_architectures = ["x86_64"]

  tags = var.common_tags
}

# Lambda function for rotating database credentials
resource "aws_lambda_function" "rds_rotation" {
  filename      = data.archive_file.rds_rotation_zip.output_path
  function_name = "${var.project_name}-rds-rotation-${var.environment}"
  role          = aws_iam_role.rds_rotation.arn
  handler       = "index.handler"
  runtime       = "python3.11"
  timeout       = 60
  layers        = try([aws_lambda_layer_version.psycopg2[0].arn], [])

  environment {
    variables = {
      SECRETS_MANAGER_ENDPOINT = "https://secretsmanager.${var.aws_region}.amazonaws.com"
    }
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.rds_security_group_id]
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-rds-rotation"
  })

  depends_on = [aws_iam_role_policy_attachment.rds_rotation_vpc]
}

# Create the Lambda function code inline
data "archive_file" "rds_rotation_zip" {
  type        = "zip"
  output_path = "${path.module}/.terraform/rds_rotation.zip"

  source {
    content  = file("${path.module}/rds_rotation_lambda.py")
    filename = "index.py"
  }
}

# Secrets Manager Rotation Configuration - RDS Credentials
resource "aws_secretsmanager_secret_rotation" "rds_credentials" {
  secret_id           = aws_secretsmanager_secret.rds_credentials.id
  rotation_lambda_arn = aws_lambda_function.rds_rotation.arn

  rotation_rules {
    automatically_after_days = 30
  }

  depends_on = [aws_lambda_permission.rds_rotation_secrets_manager]
}

# Lambda permission for Secrets Manager to invoke rotation
resource "aws_lambda_permission" "rds_rotation_secrets_manager" {
  statement_id  = "AllowSecretsManagerInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.rds_rotation.function_name
  principal     = "secretsmanager.amazonaws.com"
}

# ============================================================
# 12. Monitoring - Credential Rotation Events
# ============================================================

# CloudWatch Log Group for rotation Lambda
resource "aws_cloudwatch_log_group" "rds_rotation" {
  name              = "/aws/lambda/${aws_lambda_function.rds_rotation.function_name}"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-rds-rotation-logs"
  })
}

# Alarm for rotation failures
resource "aws_cloudwatch_metric_alarm" "rds_rotation_failure" {
  alarm_name          = "${var.project_name}-rds-rotation-failed-${var.environment}"
  alarm_description   = "Alert when RDS credential rotation fails"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "1"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Sum"
  threshold           = "1"
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  dimensions = {
    FunctionName = aws_lambda_function.rds_rotation.function_name
  }

  tags = var.common_tags
}

# Alarm for rotation duration (should complete in < 30 seconds)
resource "aws_cloudwatch_metric_alarm" "rds_rotation_duration" {
  count               = var.environment == "prod" ? 1 : 0
  alarm_name          = "${var.project_name}-rds-rotation-slow-${var.environment}"
  alarm_description   = "Alert when RDS rotation takes longer than expected"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Average"
  threshold           = "30000"  # milliseconds
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  dimensions = {
    FunctionName = aws_lambda_function.rds_rotation.function_name
  }

  tags = var.common_tags
}

