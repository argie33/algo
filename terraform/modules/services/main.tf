# ============================================================
# Services Module - REST API, CloudFront, Cognito, Algo
# ============================================================

locals {
  api_lambda_name  = "${var.project_name}-api-${var.environment}"
  algo_lambda_name = "${var.project_name}-algo-${var.environment}"
  
  api_cors_origins = concat(
    var.api_cors_allowed_origins,
    var.cloudfront_enabled ? ["https://${aws_cloudfront_distribution.frontend[0].domain_name}"] : []
  )
}

# ============================================================
# IAM Role for API Lambda
# ============================================================

resource "aws_iam_role" "api_lambda" {
  name = "${local.api_lambda_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(var.common_tags, {
    Name = "${local.api_lambda_name}-role"
  })
}

resource "aws_iam_role_policy_attachment" "api_lambda_vpc" {
  role       = aws_iam_role.api_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy" "api_lambda_secrets" {
  name = "${local.api_lambda_name}-secrets"
  role = aws_iam_role.api_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          var.rds_credentials_secret_arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "kms:ViaService" = "secretsmanager.${var.aws_region}.amazonaws.com"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "api_lambda_s3" {
  name = "${local.api_lambda_name}-s3"
  role = aws_iam_role.api_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject"
        ]
        Resource = [
          "arn:aws:s3:::${var.data_loading_bucket_name}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "api_lambda_logs" {
  role       = aws_iam_role.api_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ============================================================
# CloudWatch Log Group for API Lambda
# ============================================================

resource "aws_cloudwatch_log_group" "api_lambda" {
  name              = "/aws/lambda/${local.api_lambda_name}"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge(var.common_tags, {
    Name = "${local.api_lambda_name}-logs"
  })
}

# ============================================================
# API Lambda Function (placeholder)
# ============================================================

# Use data archive to avoid requiring file existence during validation
data "archive_file" "api_lambda" {
  type        = "zip"
  output_path = "${path.module}/.terraform_generated_api_lambda.zip"

  source {
    content  = "import json\ndef handler(event, context):\n    return {'statusCode': 200, 'body': json.dumps({'message': 'API Lambda placeholder'})}"
    filename = "index.py"
  }
}

resource "aws_lambda_function" "api" {
  filename         = data.archive_file.api_lambda.output_path
  function_name   = local.api_lambda_name
  role            = aws_iam_role.api_lambda.arn
  handler         = "index.handler"
  runtime         = "python3.11"
  timeout         = var.api_lambda_timeout
  memory_size     = var.api_lambda_memory
  source_code_hash = data.archive_file.api_lambda.output_base64sha256

  ephemeral_storage {
    size = var.api_lambda_ephemeral_storage
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.ecs_tasks_security_group_id]
  }

  environment {
    variables = {
      DB_SECRET_ARN = var.rds_credentials_secret_arn
      DB_ENDPOINT   = var.rds_endpoint
      DB_NAME       = var.rds_database_name
      AWS_REGION    = var.aws_region
    }
  }

  depends_on = [
    aws_iam_role_policy.api_lambda_secrets,
    aws_iam_role_policy.api_lambda_s3,
    aws_cloudwatch_log_group.api_lambda
  ]

  tags = merge(var.common_tags, {
    Name = local.api_lambda_name
  })
}

# ============================================================
# API Gateway HTTP API
# ============================================================

resource "aws_apigatewayv2_api" "main" {
  name          = "${var.project_name}-api-${var.environment}"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = local.api_cors_origins
    allow_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization", "Accept", "X-Requested-With"]
    expose_headers = ["Content-Length", "Content-Type", "X-Request-Id"]
    max_age       = 3600
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-api-${var.environment}"
  })
}

resource "aws_apigatewayv2_integration" "api_lambda" {
  api_id           = aws_apigatewayv2_api.main.id
  integration_type = "AWS_PROXY"
  integration_method = "POST"
  payload_format_version = "2.0"
  target = aws_lambda_function.api.arn
}

resource "aws_apigatewayv2_route" "api_default" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
}

resource "aws_apigatewayv2_stage" "api" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = var.api_gateway_stage_name
  auto_deploy = true

  dynamic "access_log_settings" {
    for_each = var.api_gateway_logging_enabled ? [1] : []
    content {
      destination_arn = aws_cloudwatch_log_group.api_gateway[0].arn
      format = jsonencode({
        requestId      = "$context.requestId"
        ip             = "$context.identity.sourceIp"
        requestTime    = "$context.requestTime"
        httpMethod     = "$context.httpMethod"
        resourcePath   = "$context.resourcePath"
        status         = "$context.status"
        protocol       = "$context.protocol"
        responseLength = "$context.responseLength"
        integrationLatency = "$context.integration.latency"
        error          = "$context.error.message"
      })
    }
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-api-stage-${var.environment}"
  })
}

resource "aws_cloudwatch_log_group" "api_gateway" {
  count             = var.api_gateway_logging_enabled ? 1 : 0
  name              = "/aws/apigateway/${var.project_name}-api-${var.environment}"
  retention_in_days = var.api_gateway_log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-api-gateway-logs"
  })
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ============================================================
# CloudFront Distribution (Frontend CDN)
# ============================================================

resource "aws_cloudfront_origin_access_control" "frontend" {
  count           = var.cloudfront_enabled ? 1 : 0
  name            = "${var.project_name}-frontend-oac-${var.environment}"
  origin_access_control_origin_type = "s3"
  signing_behavior = "always"
  signing_protocol = "sigv4"
}

resource "aws_cloudfront_distribution" "frontend" {
  count = var.cloudfront_enabled ? 1 : 0

  origin {
    domain_name            = "${var.frontend_bucket_name}.s3.${var.aws_region}.amazonaws.com"
    origin_id              = "S3Frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend[0].id
  }

  origin {
    domain_name = aws_apigatewayv2_api.main.api_endpoint
    origin_id   = "APIGateway"
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  enabled = true
  default_root_object = "index.html"

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3Frontend"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = var.cloudfront_cache_default_ttl
    max_ttl                = var.cloudfront_cache_max_ttl
    compress               = true
  }

  ordered_cache_behavior {
    path_pattern     = "/api/*"
    allowed_methods  = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "APIGateway"

    forwarded_values {
      query_string = true
      headers {
        header_names = ["Authorization", "Content-Type"]
      }
      cookies {
        forward = "all"
      }
    }

    viewer_protocol_policy = "https-only"
    min_ttl                = 0
    default_ttl            = 0
    max_ttl                = 0
    compress               = true
  }

  ordered_cache_behavior {
    path_pattern     = "/*.html"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3Frontend"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 0
    max_ttl                = 86400
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-frontend-cdn-${var.environment}"
  })
}

# ============================================================
# S3 Bucket Policy for CloudFront
# ============================================================

resource "aws_s3_bucket_policy" "frontend_cloudfront" {
  count  = var.cloudfront_enabled ? 1 : 0
  bucket = var.frontend_bucket_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontOAC"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "arn:aws:s3:::${var.frontend_bucket_name}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = "arn:aws:cloudfront::${data.aws_caller_identity.current.account_id}:distribution/${aws_cloudfront_distribution.frontend[0].id}"
          }
        }
      }
    ]
  })
}

data "aws_caller_identity" "current" {}

# ============================================================
# Cognito User Pool (Authentication)
# ============================================================

resource "aws_cognito_user_pool" "main" {
  count = var.cognito_enabled ? 1 : 0
  name  = coalesce(var.cognito_user_pool_name, "${var.project_name}-${var.environment}")

  password_policy {
    minimum_length    = var.cognito_password_min_length
    require_uppercase = true
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
  }

  mfa_configuration = var.cognito_mfa_configuration

  schema {
    name              = "email"
    attribute_data_type = "String"
    required          = true
    mutable           = false
  }

  schema {
    name              = "name"
    attribute_data_type = "String"
    mutable           = true
  }

  auto_verified_attributes = ["email"]
  email_verification_message = "Your verification code is {####}"
  email_verification_subject = "Stocks Analytics - Email Verification"

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  user_attribute_update_settings {
    attributes_require_verification_before_update = ["email"]
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-cognito-pool-${var.environment}"
  })
}

resource "aws_cognito_user_pool_client" "main" {
  count                = var.cognito_enabled ? 1 : 0
  user_pool_id        = aws_cognito_user_pool.main[0].id
  name                = "${var.project_name}-app-client-${var.environment}"
  generate_secret     = true
  explicit_auth_flows = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]

  callback_urls = var.cloudfront_enabled ? [
    "https://${aws_cloudfront_distribution.frontend[0].domain_name}/callback",
    "http://localhost:3000/callback",
    "http://localhost:5173/callback"
  ] : ["http://localhost:3000/callback", "http://localhost:5173/callback"]

  logout_urls = var.cloudfront_enabled ? [
    "https://${aws_cloudfront_distribution.frontend[0].domain_name}/logout",
    "http://localhost:3000/logout",
    "http://localhost:5173/logout"
  ] : ["http://localhost:3000/logout", "http://localhost:5173/logout"]

  allowed_oauth_flows            = ["code", "implicit"]
  allowed_oauth_scopes           = ["openid", "email", "profile"]
  allowed_oauth_flows_user_pool_client = true
  prevent_user_existence_errors   = "ENABLED"

  access_token_validity  = var.cognito_session_duration_hours
  id_token_validity      = var.cognito_session_duration_hours
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  depends_on = [aws_cognito_user_pool.main]
}

# ============================================================
# IAM Role for Algo Lambda
# ============================================================

resource "aws_iam_role" "algo_lambda" {
  name = "${local.algo_lambda_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(var.common_tags, {
    Name = "${local.algo_lambda_name}-role"
  })
}

resource "aws_iam_role_policy_attachment" "algo_lambda_vpc" {
  role       = aws_iam_role.algo_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy_attachment" "algo_lambda_logs" {
  role       = aws_iam_role.algo_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "algo_lambda_secrets" {
  name = "${local.algo_lambda_name}-secrets"
  role = aws_iam_role.algo_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = "*"
        Condition = {
          StringLike = {
            "secretsmanager:Name" = "${var.project_name}-*"
          }
        }
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "kms:ViaService" = "secretsmanager.${var.aws_region}.amazonaws.com"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "algo_lambda_sns" {
  name = "${local.algo_lambda_name}-sns"
  role = aws_iam_role.algo_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = [
          aws_sns_topic.algo_alerts[0].arn
        ]
      }
    ]
  })
}

# ============================================================
# CloudWatch Log Group for Algo Lambda
# ============================================================

resource "aws_cloudwatch_log_group" "algo_lambda" {
  name              = "/aws/lambda/${local.algo_lambda_name}"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge(var.common_tags, {
    Name = "${local.algo_lambda_name}-logs"
  })
}

# ============================================================
# Algo Lambda Function (placeholder)
# ============================================================

# Use data archive to avoid requiring file existence during validation
data "archive_file" "algo_lambda" {
  type        = "zip"
  output_path = "${path.module}/.terraform_generated_algo_lambda.zip"

  source {
    content  = "import json\ndef handler(event, context):\n    return {'statusCode': 200, 'body': json.dumps({'message': 'Algo Lambda placeholder'})}"
    filename = "index.py"
  }
}

resource "aws_lambda_function" "algo" {
  filename         = data.archive_file.algo_lambda.output_path
  function_name   = local.algo_lambda_name
  role            = aws_iam_role.algo_lambda.arn
  handler         = "index.handler"
  runtime         = "python3.11"
  timeout         = var.algo_lambda_timeout
  memory_size     = var.algo_lambda_memory
  source_code_hash = data.archive_file.algo_lambda.output_base64sha256

  ephemeral_storage {
    size = var.algo_lambda_ephemeral_storage
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.ecs_tasks_security_group_id]
  }

  environment {
    variables = {
      DB_SECRET_ARN      = var.rds_credentials_secret_arn
      DB_ENDPOINT        = var.rds_endpoint
      DB_NAME            = var.rds_database_name
      AWS_REGION         = var.aws_region
      ALERTS_SNS_TOPIC   = var.sns_alerts_enabled ? aws_sns_topic.algo_alerts[0].arn : ""
    }
  }

  depends_on = [
    aws_iam_role_policy.algo_lambda_secrets,
    aws_cloudwatch_log_group.algo_lambda
  ]

  tags = merge(var.common_tags, {
    Name = local.algo_lambda_name
  })
}

# ============================================================
# SNS Topic for Algo Alerts
# ============================================================

resource "aws_sns_topic" "algo_alerts" {
  count           = var.sns_alerts_enabled ? 1 : 0
  name            = "${var.project_name}-algo-alerts-${var.environment}"
  display_name    = "Algo Trading Alerts - ${var.environment}"
  kms_master_key_id = "alias/aws/sns"

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-algo-alerts"
  })
}

resource "aws_sns_topic_subscription" "algo_alerts_email" {
  count     = var.sns_alerts_enabled && var.sns_alert_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.algo_alerts[0].arn
  protocol  = "email"
  endpoint  = var.sns_alert_email
}

# ============================================================
# EventBridge Scheduler for Algo Orchestrator
# ============================================================

resource "aws_scheduler_schedule" "algo_orchestrator" {
  count                = var.algo_schedule_enabled ? 1 : 0
  name                 = "${var.project_name}-algo-schedule-${var.environment}"
  description          = "Trigger algo orchestrator Lambda at scheduled time"
  schedule_expression  = var.algo_schedule_expression
  timezone             = var.algo_schedule_timezone
  state                = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.algo.arn
    role_arn = aws_iam_role.eventbridge_scheduler.arn

    input = jsonencode({
      source   = "eventbridge-scheduler"
      run_date = "now"
    })
  }

  depends_on = [
    aws_lambda_permission.eventbridge_scheduler,
    aws_iam_role.eventbridge_scheduler
  ]
}

resource "aws_iam_role" "eventbridge_scheduler" {
  name = "${local.algo_lambda_name}-eventbridge-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "scheduler.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(var.common_tags, {
    Name = "${local.algo_lambda_name}-eventbridge-scheduler-role"
  })
}

resource "aws_iam_role_policy" "eventbridge_scheduler_lambda" {
  name = "${local.algo_lambda_name}-eventbridge-invoke"
  role = aws_iam_role.eventbridge_scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = [
          aws_lambda_function.algo.arn
        ]
      }
    ]
  })
}

resource "aws_lambda_permission" "eventbridge_scheduler" {
  statement_id  = "AllowEventBridgeSchedulerInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.algo.function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = "arn:aws:scheduler:*:*:schedule/*/*"
}
