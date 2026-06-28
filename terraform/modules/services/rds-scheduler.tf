# ============================================================
# RDS Auto Stop/Start Scheduler (Cost Optimization)
# ============================================================
# Automatically stops RDS after market close (11pm ET)
# Automatically starts RDS before market open (7am ET)
# Saves ~$10-15/month by running DB only during trading hours

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "rds_scheduler" {
  name               = "${var.project_name}-rds-scheduler-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json

  tags = var.common_tags
}

resource "aws_iam_role_policy" "rds_scheduler" {
  name   = "${var.project_name}-rds-scheduler-policy"
  role   = aws_iam_role.rds_scheduler.id
  policy = data.aws_iam_policy_document.rds_scheduler.json
}

data "aws_iam_policy_document" "rds_scheduler" {
  statement {
    sid    = "RDSControl"
    effect = "Allow"
    actions = [
      "rds:StartDBInstance",
      "rds:StopDBInstance",
      "rds:DescribeDBInstances"
    ]
    resources = ["arn:aws:rds:${var.aws_region}:${var.aws_account_id}:db/*"]
  }
}

# Lambda: Stop RDS at 11pm ET (3am UTC next day)
resource "aws_lambda_function" "rds_stop" {
  filename      = data.archive_file.rds_stop_zip.output_path
  function_name = "${var.project_name}-rds-stop-${var.environment}"
  role          = aws_iam_role.rds_scheduler.arn
  handler       = "index.handler"
  runtime       = "python3.12"
  timeout       = 60

  source_code_hash = data.archive_file.rds_stop_zip.output_base64sha256

  environment {
    variables = {
      DB_INSTANCE = "algo-db"
    }
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-rds-stop"
  })
}

data "archive_file" "rds_stop_zip" {
  type        = "zip"
  output_path = "${path.module}/rds_stop.zip"

  source {
    content  = "import boto3\nimport os\nimport json\n\nrds = boto3.client('rds')\n\ndef handler(event, context):\n    db = os.environ['DB_INSTANCE']\n    try:\n        rds.stop_db_instance(DBInstanceIdentifier=db)\n        return {'statusCode': 200, 'body': json.dumps(f'Stopped {db}')}\n    except rds.exceptions.InvalidDBInstanceStateFault:\n        return {'statusCode': 200, 'body': json.dumps(f'{db} already stopped')}\n    except Exception as e:\n        return {'statusCode': 500, 'body': json.dumps(str(e))}\n"
    filename = "index.py"
  }
}

# Lambda: Start RDS at 7am ET (11am UTC)
resource "aws_lambda_function" "rds_start" {
  filename      = data.archive_file.rds_start_zip.output_path
  function_name = "${var.project_name}-rds-start-${var.environment}"
  role          = aws_iam_role.rds_scheduler.arn
  handler       = "index.handler"
  runtime       = "python3.12"
  timeout       = 60

  source_code_hash = data.archive_file.rds_start_zip.output_base64sha256

  environment {
    variables = {
      DB_INSTANCE = "algo-db"
    }
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-rds-start"
  })
}

data "archive_file" "rds_start_zip" {
  type        = "zip"
  output_path = "${path.module}/rds_start.zip"

  source {
    content  = "import boto3\nimport os\nimport json\n\nrds = boto3.client('rds')\n\ndef handler(event, context):\n    db = os.environ['DB_INSTANCE']\n    try:\n        rds.start_db_instance(DBInstanceIdentifier=db)\n        return {'statusCode': 200, 'body': json.dumps(f'Started {db}')}\n    except rds.exceptions.InvalidDBInstanceStateFault:\n        return {'statusCode': 200, 'body': json.dumps(f'{db} already running')}\n    except Exception as e:\n        return {'statusCode': 500, 'body': json.dumps(str(e))}\n"
    filename = "index.py"
  }
}

# EventBridge: Stop RDS at 11pm ET (4am UTC next day) — after all evening loaders (until 5pm ET)
resource "aws_cloudwatch_event_rule" "rds_stop" {
  name                = "${var.project_name}-rds-stop-${var.environment}"
  description         = "Stop RDS at 11pm ET (4am UTC) to save costs — after evening loaders complete"
  schedule_expression = "cron(0 4 * * ? *)"
  tags                = var.common_tags
}

resource "aws_cloudwatch_event_target" "rds_stop" {
  rule      = aws_cloudwatch_event_rule.rds_stop.name
  target_id = "RDSStopLambda"
  arn       = aws_lambda_function.rds_stop.arn
}

resource "aws_lambda_permission" "rds_stop_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.rds_stop.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.rds_stop.arn
}

# EventBridge: Start RDS at 2am ET (7am UTC) — before morning loaders at 3:25am ET
resource "aws_cloudwatch_event_rule" "rds_start" {
  name                = "${var.project_name}-rds-start-${var.environment}"
  description         = "Start RDS at 2am ET (7am UTC) — before morning pre-market loaders"
  schedule_expression = "cron(0 7 * * ? *)"
  tags                = var.common_tags
}

resource "aws_cloudwatch_event_target" "rds_start" {
  rule      = aws_cloudwatch_event_rule.rds_start.name
  target_id = "RDSStartLambda"
  arn       = aws_lambda_function.rds_start.arn
}

resource "aws_lambda_permission" "rds_start_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.rds_start.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.rds_start.arn
}
