# ============================================================
# AAII Sentiment Loader Lambda - Runs inside VPC for RDS access
# ============================================================

resource "aws_lambda_function" "aaii_loader" {
  filename         = data.archive_file.aaii_loader_zip.output_path
  function_name    = "${var.project_name}-aaii-loader-${var.environment}"
  role             = aws_iam_role.aaii_loader.arn
  handler          = "index.lambda_handler"
  runtime          = "python3.12"
  timeout          = 300
  memory_size      = 512

  vpc_config {
    subnet_ids            = var.private_subnet_ids
    security_group_ids    = [var.rds_security_group_id]
  }

  environment {
    variables = {
      DB_HOST     = var.db_host
      DB_PORT     = var.db_port
      DB_USER     = var.db_user
      DB_PASSWORD = var.db_password
      DB_NAME     = var.db_name
    }
  }

  depends_on = [aws_iam_role_policy.aaii_loader_logs]

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-aaii-loader"
  })
}

# IAM role for Lambda
resource "aws_iam_role" "aaii_loader" {
  name = "${var.project_name}-aaii-loader-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })

  tags = var.common_tags
}

# Permissions for VPC access
resource "aws_iam_role_policy_attachment" "aaii_loader_vpc" {
  role       = aws_iam_role.aaii_loader.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# CloudWatch logs permission
resource "aws_iam_role_policy" "aaii_loader_logs" {
  name = "${var.project_name}-aaii-loader-logs"
  role = aws_iam_role.aaii_loader.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ]
      Effect   = "Allow"
      Resource = "arn:aws:logs:*:*:*"
    }]
  })
}

# Lambda deployment package
data "archive_file" "aaii_loader_zip" {
  type        = "zip"
  output_path = "${path.module}/aaii_loader.zip"

  source {
    content  = file("${path.root}/../../scripts/aaii_loader_function.py")
    filename = "index.py"
  }
}

# Invoke Lambda during deployment
resource "null_resource" "invoke_aaii_loader" {
  provisioner "local-exec" {
    command = <<-EOT
      aws lambda invoke \
        --function-name ${aws_lambda_function.aaii_loader.function_name} \
        --region ${var.aws_region} \
        /tmp/aaii_loader_response.json
    EOT
  }

  depends_on = [aws_lambda_function.aaii_loader]
}
