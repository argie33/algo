# Lambda Environment Variables Configuration
# Run: terraform apply to deploy these settings

variable "orchestrator_dry_run" {
  default = "false"
  description = "Set to 'true' for dry-run mode (no actual trades), 'false' for live execution"
}

variable "execution_mode" {
  default = "paper"
  description = "paper = paper trading (safe), live = real money (DANGER)"
}

variable "aws_region" {
  default = "us-east-1"
  description = "AWS region for Lambda and RDS"
}

# Orchestrator Lambda
resource "aws_lambda_function" "stocks_algo" {
  function_name = "stocks-algo-dev"
  role          = aws_iam_role.lambda_role.arn
  handler       = "lambda_handler.lambda_handler"
  runtime       = "python3.11"
  timeout       = 300

  environment {
    variables = {
      DB_HOST              = aws_db_instance.stocks_db.endpoint
      DB_NAME              = "stocks"
      DB_USER              = "stocks"
      DB_SECRET_ARN        = aws_secretsmanager_secret.db_credentials.arn
      
      ORCHESTRATOR_DRY_RUN = var.orchestrator_dry_run
      EXECUTION_MODE       = var.execution_mode
      
      APCA_API_KEY_ID      = "RETRIEVED_FROM_SECRETS_MANAGER"
      APCA_API_SECRET_KEY  = "RETRIEVED_FROM_SECRETS_MANAGER"
      FRED_API_KEY         = "RETRIEVED_FROM_SECRETS_MANAGER"
      
      ALERT_EMAIL_TO       = "argeropolos@gmail.com"
      ALERT_WEBHOOK_URL    = "SET_YOUR_SLACK_WEBHOOK_HERE"
      
      AWS_REGION           = var.aws_region
    }
  }

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }
}

# API Lambda
resource "aws_lambda_function" "stocks_api" {
  function_name = "stocks-api-dev"
  role          = aws_iam_role.lambda_role.arn
  handler       = "api_lambda_handler.lambda_handler"
  runtime       = "python3.11"
  timeout       = 30

  environment {
    variables = {
      DB_HOST       = aws_db_instance.stocks_db.endpoint
      DB_NAME       = "stocks"
      DB_USER       = "stocks"
      DB_SECRET_ARN = aws_secretsmanager_secret.db_credentials.arn
      AWS_REGION    = var.aws_region
    }
  }

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }
}

# Secrets Manager for sensitive credentials
resource "aws_secretsmanager_secret" "db_credentials" {
  name = "algo/database"
}

resource "aws_secretsmanager_secret" "alpaca_credentials" {
  name = "algo/alpaca"
}

resource "aws_secretsmanager_secret" "fred_credentials" {
  name = "algo/fred"
}

# EventBridge trigger for market open (9:30 AM ET)
resource "aws_cloudwatch_event_rule" "market_open" {
  name                = "market-open-trigger"
  description         = "Trigger orchestrator at market open (9:30 AM ET)"
  schedule_expression = "cron(30 13 * * MON-FRI *)"  # 9:30 AM ET = 13:30 UTC
}

resource "aws_cloudwatch_event_target" "orchestrator" {
  rule      = aws_cloudwatch_event_rule.market_open.name
  target_id = "StocksAlgoLambda"
  arn       = aws_lambda_function.stocks_algo.arn

  input = jsonencode({
    source   = "eventbridge"
    action   = "orchestrator"
    dry_run  = var.orchestrator_dry_run
  })
}

output "lambda_orchestrator_arn" {
  value = aws_lambda_function.stocks_algo.arn
}

output "lambda_api_arn" {
  value = aws_lambda_function.stocks_api.arn
}

output "secrets_manager_arns" {
  value = {
    database = aws_secretsmanager_secret.db_credentials.arn
    alpaca   = aws_secretsmanager_secret.alpaca_credentials.arn
    fred     = aws_secretsmanager_secret.fred_credentials.arn
  }
}
