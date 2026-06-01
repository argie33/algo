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

  mfa_configuration = var.mfa_configuration

  software_token_mfa_configuration {
    enabled = true
  }

  dynamic "user_pool_add_ons" {
    for_each = var.advanced_security_mode != "OFF" ? [1] : []
    content {
      advanced_security_mode = var.advanced_security_mode
    }
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

  # Custom message Lambda trigger for professional emails
  lambda_config {
    custom_message = var.cognito_custom_email_enabled ? try(aws_lambda_function.cognito_email_trigger[0].arn, null) : null
  }

  tags = var.common_tags
}

# User Pool Client for Web App (React/Vite frontend)
resource "aws_cognito_user_pool_client" "web_app" {
  name            = "${var.project_name}-web-app-${var.environment}"
  user_pool_id    = aws_cognito_user_pool.stocks_trading.id
  generate_secret = false # No secret for public frontend apps

  # Authentication flows (secure defaults)
  # ALLOW_USER_SRP_AUTH: Secure Remote Password (cryptographic proof of identity, immune to password spray)
  # ALLOW_REFRESH_TOKEN_AUTH: Exchange refresh token for new access token
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH"
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
  domain       = "${var.project_name}-${var.environment}"
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

# Admin group — grants access to all admin-gated API endpoints
resource "aws_cognito_user_group" "admin" {
  name         = "admin"
  user_pool_id = aws_cognito_user_pool.stocks_trading.id
  description  = "Full access to admin-gated algo dashboard and trading endpoints"
}

# Add primary user to admin group
resource "aws_cognito_user_group_attachment" "primary_admin" {
  count            = var.cognito_test_user_email != "" ? 1 : 0
  user_pool_id     = aws_cognito_user_pool.stocks_trading.id
  group_name       = aws_cognito_user_group.admin.name
  user_pool_user_name = var.cognito_test_user_email

  depends_on = [aws_cognito_user.test_user, aws_cognito_user_group.admin]
}

# ============================================================
# Cognito Custom Message Lambda (sends emails via SES)
# ============================================================

# IAM role for Lambda to call SES
resource "aws_iam_role" "cognito_email_lambda_role" {
  count = var.cognito_custom_email_enabled ? 1 : 0
  name  = "${var.project_name}-cognito-email-lambda-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = var.common_tags
}

# Policy for Lambda to write CloudWatch logs
resource "aws_iam_role_policy" "cognito_email_lambda_logs" {
  count = var.cognito_custom_email_enabled ? 1 : 0
  name  = "${var.project_name}-cognito-email-lambda-logs-${var.environment}"
  role  = aws_iam_role.cognito_email_lambda_role[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-cognito-email-trigger-${var.environment}:*"
      }
    ]
  })
}

# Policy for Lambda to send email via SES
resource "aws_iam_role_policy" "cognito_email_lambda_ses" {
  count = var.cognito_custom_email_enabled ? 1 : 0
  name  = "${var.project_name}-cognito-email-lambda-ses-${var.environment}"
  role  = aws_iam_role.cognito_email_lambda_role[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "ses:FromAddress" = var.cognito_sender_email
          }
        }
      }
    ]
  })
}

# Lambda function for Cognito custom messages
resource "aws_lambda_function" "cognito_email_trigger" {
  count            = var.cognito_custom_email_enabled ? 1 : 0
  filename         = data.archive_file.cognito_email_lambda[0].output_path
  function_name    = "${var.project_name}-cognito-email-trigger-${var.environment}"
  role             = aws_iam_role.cognito_email_lambda_role[0].arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"
  source_code_hash = data.archive_file.cognito_email_lambda[0].output_base64sha256
  timeout          = 30

  tags = var.common_tags
}

# Package Lambda code
data "archive_file" "cognito_email_lambda" {
  count       = var.cognito_custom_email_enabled ? 1 : 0
  type        = "zip"
  source_file = "${path.root}/../lambda/cognito-email-trigger/lambda_function.py"
  output_path = "/tmp/algo-cognito-email-lambda.zip"
}

# Permission for Cognito to invoke Lambda
resource "aws_lambda_permission" "cognito_invoke_email_lambda" {
  count         = var.cognito_custom_email_enabled ? 1 : 0
  statement_id  = "AllowCognitoInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.cognito_email_trigger[0].function_name
  principal     = "cognito-idp.amazonaws.com"
  source_arn    = "arn:aws:cognito-idp:${var.aws_region}:${data.aws_caller_identity.current.account_id}:userpool/*"
}

# Data source for current AWS account
data "aws_caller_identity" "current" {}
