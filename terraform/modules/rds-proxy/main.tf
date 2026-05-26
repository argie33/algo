# ============================================================
# RDS Proxy - Connection Pooling Layer
# ============================================================
# Solves Lambda connection pool exhaustion by multiplexing
# connections through a managed proxy.
#
# Benefits:
# - Reduces connection churn on RDS (Lambda creates many connections)
# - Supports up to 1000 applications without RDS limit
# - Automatic connection recycling
# - Query caching (optional)

resource "aws_db_proxy" "main" {
  name          = "${var.project_name}-proxy"
  engine_family = "POSTGRESQL"
  auth {
    auth_scheme = "SECRETS"
    secret_arn  = var.secrets_manager_secret_arn
  }

  role_arn                  = aws_iam_role.proxy_role.arn
  db_proxy_protocol_version = "POSTGRES"

  # Connection pooling configuration
  max_idle_connections_percent    = 50   # % of max connections available for idle
  max_connections_percent         = 100  # Don't exceed RDS max_connections
  connection_borrow_timeout       = 120  # seconds to wait for available connection
  session_pinning_filters         = []   # No pinning = full multiplexing (better for Lambdas)
  init_query                      = ""   # No startup queries needed
  max_connection_lifetime_seconds = 3600 # Recycle connections hourly

  require_tls            = true
  vpc_subnet_ids         = var.vpc_subnet_ids
  vpc_security_group_ids = [aws_security_group.proxy_sg.id]

  logging {
    cloudwatch_logs_enabled = true
    log_group_name          = "/aws/rds-proxy/${var.project_name}"
  }

  tags = merge(
    var.common_tags,
    {
      Name = "${var.project_name}-rds-proxy"
    }
  )
}

# Target group: which RDS instance(s) this proxy connects to
resource "aws_db_proxy_target_group" "main" {
  db_proxy_name           = aws_db_proxy.main.name
  name                    = "default"
  db_parameter_group_name = "default"

  connection_pool_config {
    max_idle_connections      = 50
    max_connections           = var.max_connections
    connection_borrow_timeout = 120
    session_pinning_filters   = []
  }
}

# Register the RDS instance as target
resource "aws_db_proxy_target" "main" {
  db_proxy_name          = aws_db_proxy.main.name
  target_group_name      = aws_db_proxy_target_group.main.name
  db_instance_identifier = var.rds_instance_id
}

# ============================================================
# IAM Role for RDS Proxy
# ============================================================

resource "aws_iam_role" "proxy_role" {
  name = "${var.project_name}-rds-proxy-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "rds.amazonaws.com"
        }
      }
    ]
  })

  tags = var.common_tags
}

# Allow proxy to read RDS credentials from Secrets Manager
resource "aws_iam_role_policy" "proxy_secrets" {
  name = "${var.project_name}-rds-proxy-secrets-policy"
  role = aws_iam_role.proxy_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = var.secrets_manager_secret_arn
      }
    ]
  })
}

# ============================================================
# Security Group for RDS Proxy
# ============================================================

resource "aws_security_group" "proxy_sg" {
  name        = "${var.project_name}-rds-proxy-sg"
  description = "Security group for RDS Proxy"
  vpc_id      = var.vpc_id

  # Ingress: Allow Lambda to connect to proxy on port 5432
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.lambda_security_group_id]
  }

  # Ingress: Allow other services if needed (optional)
  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  # Egress: Allow proxy to connect to RDS
  egress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.rds_security_group_id]
  }

  tags = merge(
    var.common_tags,
    {
      Name = "${var.project_name}-rds-proxy-sg"
    }
  )
}

# ============================================================
# CloudWatch Log Group for RDS Proxy
# ============================================================

resource "aws_cloudwatch_log_group" "proxy_logs" {
  name              = "/aws/rds-proxy/${var.project_name}"
  retention_in_days = var.log_retention_days

  tags = var.common_tags
}

# ============================================================
# CloudWatch Alarms for RDS Proxy
# ============================================================

resource "aws_cloudwatch_metric_alarm" "proxy_connection_errors" {
  alarm_name          = "${var.project_name}-rds-proxy-connection-errors"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2
  metric_name         = "DatabaseConnectionErrors"
  namespace           = "AWS/RDS/Proxy"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "RDS Proxy connection errors"
  alarm_actions       = var.sns_topic_arn != null ? [var.sns_topic_arn] : []

  dimensions = {
    DBProxyName = aws_db_proxy.main.name
  }

  tags = var.common_tags
}

resource "aws_cloudwatch_metric_alarm" "proxy_client_connections" {
  alarm_name          = "${var.project_name}-rds-proxy-client-connections"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ClientConnections"
  namespace           = "AWS/RDS/Proxy"
  period              = 300
  statistic           = "Average"
  threshold           = var.max_connections * 0.8
  alarm_description   = "RDS Proxy approaching max client connections"
  alarm_actions       = var.sns_topic_arn != null ? [var.sns_topic_arn] : []

  dimensions = {
    DBProxyName = aws_db_proxy.main.name
  }

  tags = var.common_tags
}
