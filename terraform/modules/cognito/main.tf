# Cognito User Pool for Stock Trading Platform
# Provides authentication for web and mobile apps

resource "aws_cognito_user_pool" "stocks_trading" {
  name                = "stocks-trading-pool-${var.environment}"
  username_attributes = ["email"]

  password_policy {
    minimum_length    = 12
    require_uppercase = true
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
  }

  # Email verification
  auto_verified_attributes = ["email"]

  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  # Account recovery
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = {
    Environment = var.environment
    Service     = "stocks-trading"
    IaC         = "terraform"
  }
}

# User Pool Client for Web App (React/Vite frontend)
resource "aws_cognito_user_pool_client" "web_app" {
  name            = "stocks-web-app-${var.environment}"
  user_pool_id    = aws_cognito_user_pool.stocks_trading.id
  generate_secret = false  # No secret for public frontend apps

  # Authentication flows
  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_CUSTOM_AUTH"
  ]

  # Token validity
  access_token_validity  = 1
  id_token_validity      = 1
  refresh_token_validity = 30
  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  # OAuth configuration
  allowed_oauth_flows  = ["code"]
  allowed_oauth_scopes = ["openid", "profile", "email"]

  # Callback URLs
  callback_urls = concat(
    var.environment == "dev" ? [
      "http://localhost:5173/",
      "http://localhost:5173/auth/callback",
      "http://127.0.0.1:5173/"
    ] : [],
    var.environment == "prod" ? [
      "https://app.${var.domain_name}/",
      "https://app.${var.domain_name}/auth/callback"
    ] : []
  )

  # Logout URLs
  logout_urls = concat(
    var.environment == "dev" ? [
      "http://localhost:5173/",
      "http://localhost:5173/login",
      "http://127.0.0.1:5173/"
    ] : [],
    var.environment == "prod" ? [
      "https://app.${var.domain_name}/",
      "https://app.${var.domain_name}/login"
    ] : []
  )

  # Prevent user existence errors
  prevent_user_existence_errors = "ENABLED"
}

# Cognito Domain for OAuth flows
resource "aws_cognito_user_pool_domain" "main" {
  domain       = "stocks-trading-${var.environment}-${data.aws_caller_identity.current.account_id}"
  user_pool_id = aws_cognito_user_pool.stocks_trading.id
}

# Test user for development
resource "aws_cognito_user" "test_user" {
  count             = var.environment == "dev" ? 1 : 0
  user_pool_id      = aws_cognito_user_pool.stocks_trading.id
  username          = "testuser@stocks.local"
  temporary_password = "TempPassword123!"
  attributes = {
    email          = "testuser@stocks.local"
    email_verified = true
  }

  lifecycle {
    ignore_changes = [temporary_password]
  }
}

# Note: Test user password should be set manually via AWS console or AWS CLI
# Example: aws cognito-idp admin-set-user-password --user-pool-id <id> --username testuser --password "TestPassword123!" --permanent

# Data source for current AWS account
data "aws_caller_identity" "current" {}
