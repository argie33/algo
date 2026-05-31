# ============================================================
# IAM Module - Least-Privilege Roles & Policies
# ============================================================

# ============================================================
# 1. GitHub Actions OIDC Provider & Role
# ============================================================

# OIDC Provider for GitHub Actions trust
# Note: GitHub OIDC provider is a singleton - created and managed by bootstrap module
# This module references the provider created by bootstrap
data "aws_iam_openid_connect_provider" "github" {
  arn = "arn:aws:iam::${var.aws_account_id}:oidc-provider/token.actions.githubusercontent.com"
}

# Trust policy: ONLY this repository, ONLY GitHub Actions
data "aws_iam_policy_document" "github_actions_assume" {
  statement {
    effect = "Allow"

    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }

    # CRITICAL: Scope to THIS repository only
    # Format: repo:OWNER/REPO:ref:refs/heads/BRANCH
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_org}/${var.github_repo}:ref:refs/heads/main"]
    }

    actions = ["sts:AssumeRoleWithWebIdentity"]
  }
}

# GitHub Actions deployment role - Create the role with OIDC trust
resource "aws_iam_role" "github_actions" {
  name               = "${var.project_name}-svc-github-actions-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume.json

  tags = var.common_tags
}

# GitHub Actions policy - Split into multiple policies to avoid 10KB limit
# Part 1: Terraform compute resources (EC2, VPC, Lambda, ECS)
resource "aws_iam_role_policy" "github_actions_compute" {
  name   = "${var.project_name}-github-actions-compute"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_actions_compute.json
}

# Part 2: Terraform data/database resources (RDS, S3, DynamoDB)
resource "aws_iam_role_policy" "github_actions_data" {
  name   = "${var.project_name}-github-actions-data"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_actions_data.json
}

# Part 3: Terraform identity/security resources (IAM, Cognito, KMS, Secrets)
resource "aws_iam_role_policy" "github_actions_identity" {
  name   = "${var.project_name}-github-actions-identity"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_actions_identity.json
}

# Part 4: Terraform observability resources (CloudFront, EventBridge, CloudWatch)
resource "aws_iam_role_policy" "github_actions_observability" {
  name   = "${var.project_name}-github-actions-observability"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_actions_observability.json
}

data "aws_iam_policy_document" "github_actions_compute" {
  statement {
    sid    = "Compute"
    effect = "Allow"
    actions = [
      "ec2:Describe*", "ec2:CreateVpc", "ec2:DeleteVpc", "ec2:CreateSubnet",
      "ec2:DeleteSubnet", "ec2:CreateSecurityGroup", "ec2:DeleteSecurityGroup",
      "ec2:AuthorizeSecurityGroupIngress", "ec2:AuthorizeSecurityGroupEgress",
      "ec2:RevokeSecurityGroupIngress", "ec2:RevokeSecurityGroupEgress",
      "ec2:CreateNetworkInterface", "ec2:DeleteNetworkInterface",
      "ec2:ModifyNetworkInterfaceAttribute", "ec2:CreateRoute", "ec2:DeleteRoute",
      "ec2:CreateRouteTable", "ec2:DeleteRouteTable",
      "ec2:AssociateRouteTable", "ec2:DisassociateRouteTable",
      "ec2:CreateInternetGateway", "ec2:DeleteInternetGateway",
      "ec2:AttachInternetGateway", "ec2:DetachInternetGateway",
      "ec2:CreateNatGateway", "ec2:DeleteNatGateway",
      "ec2:AllocateAddress", "ec2:ReleaseAddress",
      "ec2:CreateTags", "ec2:DeleteTags",
      "lambda:CreateFunction", "lambda:DeleteFunction", "lambda:UpdateFunctionCode",
      "lambda:UpdateFunctionConfiguration", "lambda:GetFunction",
      "lambda:GetFunctionConfiguration", "lambda:ListFunctions",
      "lambda:AddPermission", "lambda:RemovePermission",
      "lambda:TagResource", "lambda:UntagResource",
      "apigateway:GET", "apigatewayv2:*", "ecs:*", "autoscaling:*"
    ]
    resources = ["*"]
  }
}

data "aws_iam_policy_document" "github_actions_data" {
  statement {
    sid    = "Data"
    effect = "Allow"
    actions = [
      "rds:*", "s3:*", "dynamodb:*"
    ]
    resources = ["*"]
  }
}

data "aws_iam_policy_document" "github_actions_identity" {
  statement {
    sid    = "Identity"
    effect = "Allow"
    actions = [
      "iam:*", "cognito-idp:*", "cognito-identity:*", "kms:*",
      "secretsmanager:*", "ecr:*"
    ]
    resources = ["*"]
  }
}

data "aws_iam_policy_document" "github_actions_observability" {
  statement {
    sid    = "Observability"
    effect = "Allow"
    actions = [
      "scheduler:*", "events:*", "cloudfront:*", "acm:*",
      "logs:*", "cloudwatch:*", "cloudtrail:*", "config:*",
      "guardduty:*"
    ]
    resources = ["*"]
  }
}

# ============================================================
# 2. Bastion Host IAM Role
# ============================================================

resource "aws_iam_role" "bastion" {
  count              = var.bastion_enabled ? 1 : 0
  name               = "${var.project_name}-bastion-${var.environment}"
  description        = "Bastion host role for ${var.project_name}"
  assume_role_policy = data.aws_iam_policy_document.bastion_assume[0].json

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-bastion"
  })
}

data "aws_iam_policy_document" "bastion_assume" {
  count = var.bastion_enabled ? 1 : 0

  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

# Bastion policy: Systems Manager + Secrets Manager (read-only)
resource "aws_iam_role_policy" "bastion" {
  count  = var.bastion_enabled ? 1 : 0
  name   = "${var.project_name}-bastion-policy"
  role   = aws_iam_role.bastion[0].id
  policy = data.aws_iam_policy_document.bastion[0].json
}

data "aws_iam_policy_document" "bastion" {
  count = var.bastion_enabled ? 1 : 0

  # Systems Manager Session Manager access
  statement {
    sid    = "SystemsManagerSSMCore"
    effect = "Allow"

    actions = [
      "ssm:UpdateInstanceInformation",
      "ssmmessages:AcknowledgeMessage",
      "ssmmessages:GetEndpoint",
      "ssmmessages:GetMessages",
      "ec2messages:AcknowledgeMessage",
      "ec2messages:GetEndpoint",
      "ec2messages:GetMessages"
    ]

    resources = ["*"]
  }

  # CloudWatch Logs for Session Manager
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams"
    ]

    resources = [
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/ssm/*"
    ]
  }

  # Read-only Secrets Manager access (for DB credentials)
  statement {
    sid    = "SecretsManagerRead"
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ]

    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}-*"
    ]
  }

  # KMS decryption for encrypted secrets
  statement {
    sid    = "KMSDecrypt"
    effect = "Allow"

    actions = [
      "kms:Decrypt",
      "kms:DescribeKey"
    ]

    resources = [
      "arn:aws:kms:${var.aws_region}:${var.aws_account_id}:key/*",
      "arn:aws:kms:${var.aws_region}:${var.aws_account_id}:alias/${var.project_name}-*"
    ]
  }
}

resource "aws_iam_instance_profile" "bastion" {
  count = var.bastion_enabled ? 1 : 0
  name  = "${var.project_name}-bastion-profile"
  role  = aws_iam_role.bastion[0].name
}

# ============================================================
# 3. ECS Task Execution Role
# ============================================================

resource "aws_iam_role" "ecs_task_execution" {
  name               = "${var.project_name}-ecs-task-execution-${var.environment}"
  description        = "ECS task execution role for ${var.project_name}"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_execution_assume.json

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-ecs-task-execution"
  })
}

data "aws_iam_policy_document" "ecs_task_execution_assume" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

# Attach AWS managed policy for basic ECS task execution
resource "aws_iam_role_policy_attachment" "ecs_task_execution_managed" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Additional permissions for Secrets Manager and logging
resource "aws_iam_role_policy" "ecs_task_execution" {
  name   = "${var.project_name}-ecs-task-execution-policy"
  role   = aws_iam_role.ecs_task_execution.id
  policy = data.aws_iam_policy_document.ecs_task_execution.json
}

data "aws_iam_policy_document" "ecs_task_execution" {
  # Secrets Manager (read task secrets from Secrets Manager, allow both patterns)
  statement {
    sid    = "SecretsManager"
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ]

    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}-*",
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}/*"
    ]
  }

  # KMS (decrypt secrets)
  statement {
    sid    = "KMSDecrypt"
    effect = "Allow"

    actions = [
      "kms:Decrypt",
      "kms:DescribeKey"
    ]

    # FIXED: Issue #8 - Scope to project KMS keys only (was Resource: "*")
    # Allow all keys in account but with conditions to restrict to project keys
    resources = [
      "arn:aws:kms:${var.aws_region}:${var.aws_account_id}:key/*"
    ]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.aws_account_id]
    }

    # Restrict to keys tagged with project name
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values = [
        "secretsmanager.${var.aws_region}.amazonaws.com"
      ]
    }
  }

  # CloudWatch Logs (create log groups and streams)
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]

    resources = [
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/ecs/*",
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/ecs/*"
    ]
  }
}

# ============================================================
# 4. ECS Task Role (permissions for running tasks)
# ============================================================

resource "aws_iam_role" "ecs_task" {
  name               = "${var.project_name}-ecs-task-${var.environment}"
  description        = "ECS task role for loaders in ${var.project_name}"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-ecs-task"
  })
}

data "aws_iam_policy_document" "ecs_task_assume" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

# ECS task permissions (loaders)
resource "aws_iam_role_policy" "ecs_task" {
  name   = "${var.project_name}-ecs-task-policy"
  role   = aws_iam_role.ecs_task.id
  policy = data.aws_iam_policy_document.ecs_task.json
}

data "aws_iam_policy_document" "ecs_task" {
  # Secrets Manager (read DB credentials, allow both patterns)
  statement {
    sid    = "SecretsManager"
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue"
    ]

    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}-*",
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}/*"
    ]
  }

  # KMS (decrypt secrets)
  statement {
    sid    = "KMSDecrypt"
    effect = "Allow"

    actions = [
      "kms:Decrypt"
    ]

    resources = [
      "arn:aws:kms:${var.aws_region}:${var.aws_account_id}:key/*",
      "arn:aws:kms:${var.aws_region}:${var.aws_account_id}:alias/${var.project_name}-*"
    ]
  }

  # S3 data bucket (for loader staging)
  dynamic "statement" {
    for_each = var.data_bucket_name != null ? [1] : []
    content {
      sid    = "S3DataBucket"
      effect = "Allow"

      actions = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ]

      resources = [
        "arn:aws:s3:::${var.data_bucket_name}",
        "arn:aws:s3:::${var.data_bucket_name}/*"
      ]
    }
  }

  # CloudWatch (publish metrics and logs)
  statement {
    sid    = "CloudWatch"
    effect = "Allow"

    actions = [
      "cloudwatch:PutMetricData",
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]

    resources = ["*"]
  }
}

# ============================================================
# 5. Lambda API Role
# ============================================================

resource "aws_iam_role" "lambda_api" {
  name               = "${var.project_name}-lambda-api-${var.environment}"
  description        = "Lambda API role for ${var.project_name}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-lambda-api"
  })
}

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

# Lambda API permissions
resource "aws_iam_role_policy" "lambda_api" {
  name   = "${var.project_name}-lambda-api-policy"
  role   = aws_iam_role.lambda_api.id
  policy = data.aws_iam_policy_document.lambda_api.json
}

data "aws_iam_policy_document" "lambda_api" {
  # VPC access (if running in VPC)
  statement {
    sid    = "VPCAccess"
    effect = "Allow"

    actions = [
      "ec2:CreateNetworkInterface",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DeleteNetworkInterface",
      "ec2:AssignPrivateIpAddresses",
      "ec2:UnassignPrivateIpAddresses"
    ]

    resources = ["*"]
  }

  # Secrets Manager (read DB credentials, allow both patterns)
  statement {
    sid    = "SecretsManager"
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue"
    ]

    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}-*",
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}/*"
    ]
  }

  # KMS (decrypt secrets)
  statement {
    sid    = "KMSDecrypt"
    effect = "Allow"

    actions = [
      "kms:Decrypt"
    ]

    resources = [
      "arn:aws:kms:${var.aws_region}:${var.aws_account_id}:key/*",
      "arn:aws:kms:${var.aws_region}:${var.aws_account_id}:alias/${var.project_name}-*"
    ]
  }

  # CloudWatch Logs
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]

    resources = [
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/lambda/${var.project_name}-*"
    ]
  }

  # CloudWatch Metrics (for custom metrics and monitoring)
  statement {
    sid    = "CloudWatchMetrics"
    effect = "Allow"

    actions = [
      "cloudwatch:PutMetricData"
    ]

    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.aws_account_id]
    }
  }

  # ECS (invoke data patrol task from /api/algo/patrol endpoint)
  statement {
    sid    = "InvokeDataPatrolTask"
    effect = "Allow"

    actions = [
      "ecs:RunTask"
    ]

    resources = [
      "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:task-definition/${var.project_name}-data-patrol:*"
    ]
  }

  # IAM PassRole (required to pass execution role to ECS task)
  statement {
    sid    = "PassRoleToECS"
    effect = "Allow"

    actions = [
      "iam:PassRole"
    ]

    resources = [
      "arn:aws:iam::${var.aws_account_id}:role/${var.project_name}-ecs-task-*"
    ]
  }
}

# ============================================================
# 6. Lambda Algo Role
# ============================================================

resource "aws_iam_role" "lambda_algo" {
  name               = "${var.project_name}-lambda-algo-${var.environment}"
  description        = "Lambda algo orchestrator role for ${var.project_name}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-lambda-algo"
  })
}

# Lambda algo permissions
resource "aws_iam_role_policy" "lambda_algo" {
  name   = "${var.project_name}-lambda-algo-policy"
  role   = aws_iam_role.lambda_algo.id
  policy = data.aws_iam_policy_document.lambda_algo.json
}

data "aws_iam_policy_document" "lambda_algo" {
  # VPC access
  statement {
    sid    = "VPCAccess"
    effect = "Allow"

    actions = [
      "ec2:CreateNetworkInterface",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DeleteNetworkInterface",
      "ec2:AssignPrivateIpAddresses",
      "ec2:UnassignPrivateIpAddresses"
    ]

    resources = ["*"]
  }

  # Secrets Manager (allow both ${project_name}-* and ${project_name}/* patterns)
  statement {
    sid    = "SecretsManager"
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue"
    ]

    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}-*",
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}/*"
    ]
  }

  # KMS
  statement {
    sid    = "KMSDecrypt"
    effect = "Allow"

    actions = [
      "kms:Decrypt"
    ]

    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.aws_account_id]
    }
  }

  # CloudWatch Logs
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]

    resources = [
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/lambda/${var.project_name}-*"
    ]
  }

  # SNS - Full management for Terraform (create topics for alarms)
  statement {
    sid    = "SNSManagement"
    effect = "Allow"

    actions = [
      "sns:CreateTopic",
      "sns:DeleteTopic",
      "sns:GetTopicAttributes",
      "sns:SetTopicAttributes",
      "sns:ListTopics",
      "sns:Subscribe",
      "sns:Unsubscribe",
      "sns:Publish",
      "sns:TagResource",
      "sns:UntagResource"
    ]

    resources = [
      "arn:aws:sns:${var.aws_region}:${var.aws_account_id}:${var.project_name}-*"
    ]
  }

  # CloudWatch Metrics (for custom metrics)
  statement {
    sid    = "CloudWatchMetrics"
    effect = "Allow"

    actions = [
      "cloudwatch:PutMetricData"
    ]

    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.aws_account_id]
    }
  }

  # DynamoDB - Orchestrator locks and loader status
  statement {
    sid    = "DynamoDatabaseOrchestration"
    effect = "Allow"

    actions = [
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:PutItem",
      "dynamodb:Query"
    ]

    resources = [
      "arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/${var.project_name}-orchestrator-locks-${var.environment}",
      "arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/${var.project_name}-loader-status-${var.environment}"
    ]
  }
}

# ============================================================
# 7. EventBridge Scheduler Role
# ============================================================

resource "aws_iam_role" "eventbridge_scheduler" {
  name               = "${var.project_name}-eventbridge-scheduler-${var.environment}"
  description        = "EventBridge Scheduler role for ${var.project_name}"
  assume_role_policy = data.aws_iam_policy_document.eventbridge_scheduler_assume.json

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-eventbridge-scheduler"
  })
}

data "aws_iam_policy_document" "eventbridge_scheduler_assume" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

# EventBridge Scheduler permissions (invoke ECS tasks and Lambda)
resource "aws_iam_role_policy" "eventbridge_scheduler" {
  name   = "${var.project_name}-eventbridge-scheduler-policy"
  role   = aws_iam_role.eventbridge_scheduler.id
  policy = data.aws_iam_policy_document.eventbridge_scheduler.json
}

data "aws_iam_policy_document" "eventbridge_scheduler" {
  # ECS RunTask
  statement {
    sid    = "ECSRunTask"
    effect = "Allow"

    actions = [
      "ecs:RunTask"
    ]

    resources = [
      "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:task-definition/${var.project_name}-*:*"
    ]
  }

  # Pass roles
  statement {
    sid    = "IAMPassRole"
    effect = "Allow"

    actions = [
      "iam:PassRole"
    ]

    resources = [
      aws_iam_role.ecs_task_execution.arn,
      aws_iam_role.ecs_task.arn
    ]
  }

  # Lambda invoke
  statement {
    sid    = "LambdaInvoke"
    effect = "Allow"

    actions = [
      "lambda:InvokeFunction"
    ]

    resources = [
      "arn:aws:lambda:${var.aws_region}:${var.aws_account_id}:function:${var.project_name}-*"
    ]
  }
}

# ============================================================
# 8. GitHub Actions Deployer IAM User
# ============================================================
# Minimal permissions for GitHub Actions to deploy code only
# (not infrastructure changes - those use Terraform via OIDC role)

# ============================================================
# 9. Developer IAM User (for local CLI access - read-only)
# ============================================================
# For the project owner to log in and manage resources
# Read-most things, invoke Lambda, read logs, but no root access

resource "aws_iam_user" "developer" {
  name = "${var.project_name}-developer"

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-developer"
  })
}

# Attach read-only policy
resource "aws_iam_user_policy_attachment" "developer_readonly" {
  user       = aws_iam_user.developer.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# Add specific invoke + execution permissions
resource "aws_iam_user_policy" "developer" {
  name   = "${var.project_name}-developer-policy"
  user   = aws_iam_user.developer.name
  policy = data.aws_iam_policy_document.developer.json
}

data "aws_iam_policy_document" "developer" {
  # Lambda invocation (for testing)
  statement {
    sid    = "LambdaInvoke"
    effect = "Allow"

    actions = [
      "lambda:InvokeFunction",
      "lambda:InvokeAsync"
    ]

    resources = [
      "arn:aws:lambda:${var.aws_region}:${var.aws_account_id}:function:${var.project_name}-*"
    ]
  }

  # ECS task invocation (for running loaders and orchestrator)
  statement {
    sid    = "ECSRunTask"
    effect = "Allow"

    actions = [
      "ecs:RunTask",
      "ecs:StopTask",
      "ecs:DescribeTasks",
      "ecs:ListTasks"
    ]

    resources = [
      "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:task-definition/${var.project_name}-*",
      "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:task/${var.project_name}-cluster/*"
    ]
  }

  # ECS cluster access
  statement {
    sid    = "ECSClusterAccess"
    effect = "Allow"

    actions = [
      "ecs:DescribeCluster",
      "ecs:ListClusters"
    ]

    resources = [
      "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:cluster/${var.project_name}-*"
    ]
  }

  # IAM pass role (needed to run ECS tasks)
  statement {
    sid    = "PassRole"
    effect = "Allow"

    actions = [
      "iam:PassRole"
    ]

    resources = [
      "arn:aws:iam::${var.aws_account_id}:role/${var.project_name}-svc-*",
      "arn:aws:iam::${var.aws_account_id}:role/${var.project_name}-ecs-*"
    ]
  }

  # Step Functions (start executions and check status for manual testing)
  statement {
    sid    = "StepFunctionsStartExecution"
    effect = "Allow"

    actions = [
      "states:StartExecution",
      "states:DescribeExecution",
      "states:GetExecutionHistory"
    ]

    resources = [
      "arn:aws:states:${var.aws_region}:${var.aws_account_id}:stateMachine:${var.project_name}-*"
    ]
  }

  # CloudWatch Logs (full write access for troubleshooting)
  statement {
    sid    = "CloudWatchLogsWrite"
    effect = "Allow"

    actions = [
      "logs:CreateLogStream",
      "logs:CreateLogGroup",
      "logs:PutLogEvents"
    ]

    resources = [
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/lambda/${var.project_name}-*",
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/ecs/*"
    ]
  }

  # CloudFront invalidation (clear cache if needed)
  statement {
    sid    = "CloudFrontInvalidate"
    effect = "Allow"

    actions = [
      "cloudfront:CreateInvalidation",
      "cloudfront:GetInvalidation"
    ]

    resources = ["*"]
  }

  # Secrets Manager (read-only, for checking configuration)
  statement {
    sid    = "SecretsManagerRead"
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ]

    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}-*",
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}/*"
    ]
  }

  # KMS (decrypt secrets for verification)
  statement {
    sid    = "KMSDecrypt"
    effect = "Allow"

    actions = [
      "kms:Decrypt",
      "kms:DescribeKey"
    ]

    resources = [
      "arn:aws:kms:${var.aws_region}:${var.aws_account_id}:key/*"
    ]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.aws_account_id]
    }
  }
}

# Managed policy for Cognito (inline policies are capped at 2048 bytes combined per user;
# managed policies bypass that limit and are the correct approach for larger permission sets)
resource "aws_iam_policy" "developer_cognito" {
  name   = "${var.project_name}-developer-cognito"
  policy = data.aws_iam_policy_document.developer_cognito.json
}

resource "aws_iam_user_policy_attachment" "developer_cognito" {
  user       = aws_iam_user.developer.name
  policy_arn = aws_iam_policy.developer_cognito.arn
}

data "aws_iam_policy_document" "developer_cognito" {
  statement {
    sid    = "CognitoUserAdmin"
    effect = "Allow"
    actions = [
      "cognito-idp:AdminCreateUser",
      "cognito-idp:AdminSetUserPassword",
      "cognito-idp:AdminDeleteUser",
      "cognito-idp:AdminGetUser",
      "cognito-idp:AdminUpdateUserAttributes",
      "cognito-idp:AdminEnableUser",
      "cognito-idp:AdminDisableUser",
      "cognito-idp:ListUsers",
      "cognito-idp:ListUserPools",
      "cognito-idp:DescribeUserPool",
      "cognito-idp:DescribeUserPoolClient"
    ]
    resources = ["arn:aws:cognito-idp:${var.aws_region}:${var.aws_account_id}:userpool/*"]
  }
}

# Mark access key for rotation on a schedule
# Terraform will invalidate old key when this value changes (via scheduled rotation workflow)
variable "developer_key_rotation_date" {
  description = "Date of last developer credential rotation (updated quarterly by automation)"
  type        = string
  default     = "2026-05-28" # Last rotation date
}

locals {
  # Key ID includes rotation marker - Terraform will create new key on every apply if this changes
  developer_key_rotation = var.developer_key_rotation_date
}

# Access key for developer user (local CLI use)
# Rotated quarterly per security baseline (see steering/algo.md)
# Rotation workflow updates var.developer_key_rotation_date, triggering key recreation on next apply
resource "aws_iam_access_key" "developer" {
  user = aws_iam_user.developer.name

  lifecycle {
    create_before_destroy = true
  }
}

# Store developer credentials in Secrets Manager (IaC-managed)
resource "aws_secretsmanager_secret" "developer_credentials" {
  name        = "${var.project_name}/developer-credentials"
  description = "Developer IAM user access keys for local CLI/automation"

  tags = var.common_tags
}

resource "aws_secretsmanager_secret_version" "developer_credentials" {
  secret_id = aws_secretsmanager_secret.developer_credentials.id
  secret_string = jsonencode({
    access_key_id     = aws_iam_access_key.developer.id
    secret_access_key = aws_iam_access_key.developer.secret
    user_name         = aws_iam_user.developer.name
  })
}
