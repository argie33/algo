# ============================================================
# Secrets Manager Module - Environment Credentials
# ============================================================


# Alpaca Trading API Credentials
resource "aws_secretsmanager_secret" "alpaca" {
  name                    = "algo/alpaca"
  description             = "Alpaca paper trading API credentials"
  recovery_window_in_days = 7

  tags = var.common_tags
}

resource "aws_secretsmanager_secret_version" "alpaca" {
  secret_id = aws_secretsmanager_secret.alpaca.id
  secret_string = jsonencode({
    api_key    = var.alpaca_api_key
    api_secret = var.alpaca_api_secret
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# FRED Economic Data API Key
resource "aws_secretsmanager_secret" "fred" {
  name                    = "algo/fred"
  description             = "Federal Reserve Economic Data (FRED) API key"
  recovery_window_in_days = 7

  tags = var.common_tags
}

resource "aws_secretsmanager_secret_version" "fred" {
  secret_id = aws_secretsmanager_secret.fred.id
  secret_string = jsonencode({
    api_key = var.fred_api_key
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# PostgreSQL Database Credentials
resource "aws_secretsmanager_secret" "database" {
  name                    = "algo/database"
  description             = "PostgreSQL RDS database credentials"
  recovery_window_in_days = 7

  tags = var.common_tags
}

resource "aws_secretsmanager_secret_version" "database" {
  secret_id = aws_secretsmanager_secret.database.id
  secret_string = jsonencode({
    host     = var.db_host
    port     = var.db_port
    dbname   = var.db_name
    username = var.db_user
    password = var.db_password
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# JWT Secret
resource "aws_secretsmanager_secret" "jwt" {
  name                    = "algo/jwt"
  description             = "JWT secret key for token signing"
  recovery_window_in_days = 7

  tags = var.common_tags
}

resource "aws_secretsmanager_secret_version" "jwt" {
  secret_id = aws_secretsmanager_secret.jwt.id
  secret_string = jsonencode({
    jwt_secret = var.jwt_secret
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# Output secret ARNs for Lambda IAM policies
output "alpaca_secret_arn" {
  value = aws_secretsmanager_secret.alpaca.arn
}

output "fred_secret_arn" {
  value = aws_secretsmanager_secret.fred.arn
}

output "database_secret_arn" {
  value = aws_secretsmanager_secret.database.arn
}

output "jwt_secret_arn" {
  value = aws_secretsmanager_secret.jwt.arn
}
