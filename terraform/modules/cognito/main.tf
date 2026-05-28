# Cognito User Pool for Stock Trading Platform
# Provides authentication for web and mobile apps

resource "aws_cognito_user_pool" "stocks_trading" {
  name                = "${var.project_name}-pool-${var.environment}"
  username_attributes = ["email"]

  password_policy {
    minimum_length    = 12
    require_uppercase = true
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
  }

  # MFA — OPTIONAL so users can enroll TOTP without breaking existing logins.
  # Upgrade to "ON" (required) once all users have enrolled.
  mfa_configuration = "OPTIONAL"

  software_token_mfa_configuration {
    enabled = true
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

  tags = var.common_tags
}

# User Pool Client for Web App (React/Vite frontend)
resource "aws_cognito_user_pool_client" "web_app" {
  name            = "${var.project_name}-web-app-${var.environment}"
  user_pool_id    = aws_cognito_user_pool.stocks_trading.id
  generate_secret = false # No secret for public frontend apps

  # Authentication flows
  # ALLOW_USER_SRP_AUTH: Secure Remote Password (cryptographically secure)
  # ALLOW_USER_PASSWORD_AUTH: username/password flow for web app
  # ALLOW_REFRESH_TOKEN_AUTH: refresh tokens to get new access tokens
  # ALLOW_CUSTOM_AUTH: fallback for dev auth flow
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
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

  # Callback URLs - must match deployment domains
  callback_urls = concat(
    var.environment == "dev" ? [
      "http://localhost:5173/",
      "http://localhost:5173/auth/callback",
      "http://127.0.0.1:5173/"
    ] : [],
    var.environment == "dev" && var.cloudfront_domain != "" ? [
      "https://${var.cloudfront_domain}/",
      "https://${var.cloudfront_domain}/auth/callback"
    ] : [],
    var.environment == "prod" && var.cloudfront_domain != "" ? [
      "https://${var.cloudfront_domain}/",
      "https://${var.cloudfront_domain}/auth/callback"
    ] : []
  )

  # Logout URLs
  logout_urls = concat(
    var.environment == "dev" ? [
      "http://localhost:5173/",
      "http://localhost:5173/login",
      "http://127.0.0.1:5173/"
    ] : [],
    var.environment == "dev" && var.cloudfront_domain != "" ? [
      "https://${var.cloudfront_domain}/",
      "https://${var.cloudfront_domain}/login"
    ] : [],
    var.environment == "prod" && var.cloudfront_domain != "" ? [
      "https://${var.cloudfront_domain}/",
      "https://${var.cloudfront_domain}/login"
    ] : []
  )

  # Prevent user existence errors
  prevent_user_existence_errors = "ENABLED"
}

# Cognito Domain for OAuth flows
resource "aws_cognito_user_pool_domain" "main" {
  domain       = "${var.project_name}-${var.environment}-${data.aws_caller_identity.current.account_id}"
  user_pool_id = aws_cognito_user_pool.stocks_trading.id
}

# Test user for development
resource "aws_cognito_user" "test_user" {
  count              = var.cognito_test_user_email != "" ? 1 : 0
  user_pool_id       = aws_cognito_user_pool.stocks_trading.id
  username           = var.cognito_test_user_email
  temporary_password = var.test_user_password
  attributes = {
    email          = var.cognito_test_user_email
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
