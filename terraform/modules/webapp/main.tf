/**
 * Webapp Module - Lambda API, CloudFront, Cognito
 *
 * Creates:
 * - Lambda function for REST API
 * - API Gateway with CORS
 * - CloudFront distribution for frontend
 * - Cognito user pool and client
 * - S3 bucket for frontend assets
 *
 * Reference: template-webapp.yml
 */


# S3 bucket for frontend assets
resource "aws_s3_bucket" "frontend" {
  bucket = "${var.project_name}-webapp-frontend-code-${var.aws_account_id}"

  tags = merge(
    var.common_tags,
    { Name = "${var.project_name}-frontend" }
  )
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Cognito User Pool
resource "aws_cognito_user_pool" "main" {
  name = "${var.project_name}-user-pool"

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
    require_uppercase = true
  }

  auto_verified_attributes = ["email"]
  mfa_configuration        = "OPTIONAL"

  schema {
    attribute_data_type      = "String"
    developer_only_attribute = false
    mutable                  = true
    name                     = "email"
    required                 = true
  }

  tags = var.common_tags
}

# Cognito User Pool Client
resource "aws_cognito_user_pool_client" "main" {
  name                = "${var.project_name}-client"
  user_pool_id        = aws_cognito_user_pool.main.id
  generate_secret     = true
  explicit_auth_flows = ["ADMIN_NO_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]

  callback_urls = var.cognito_callback_urls
  logout_urls   = var.cognito_logout_urls

  allowed_oauth_flows          = ["code", "implicit"]
  allowed_oauth_scopes         = ["email", "openid", "profile"]
  allowed_oauth_flows_user_pool_client = true

  access_token_validity  = 1
  id_token_validity      = 1
  refresh_token_validity = 30
  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }
}
