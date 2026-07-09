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
    APCA_API_KEY_ID     = var.alpaca_api_key
    APCA_API_SECRET_KEY = var.alpaca_api_secret
  })
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
}

# Orchestrator State (Circuit Breaker Halt Flag)
# Used by circuit breaker Lambda to signal orchestrator to halt trading
resource "aws_secretsmanager_secret" "orchestrator" {
  name                    = "algo/orchestrator"
  description             = "Orchestrator state: circuit breaker halt flag and control state"
  recovery_window_in_days = 7

  tags = var.common_tags
}

resource "aws_secretsmanager_secret_version" "orchestrator" {
  secret_id = aws_secretsmanager_secret.orchestrator.id
  secret_string = jsonencode({
    orchestrator_dry_run = false,
    halt_reason          = "",
    last_updated         = "bootstrap"
  })
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
