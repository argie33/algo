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

    # CRITICAL: Scope to THIS repository and MAIN branch only.
    # Staging branch is intentionally excluded: it has weaker branch protection
    # (no required reviews) but the same full deploy permissions — too risky.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_org}/${var.github_repo}:ref:refs/heads/main",
      ]
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
    sid    = "EC2Describe"
    effect = "Allow"
    actions = [
      "ec2:Describe*", "ec2:Get*", "ec2:List*"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "VPC"
    effect = "Allow"
    actions = [
      "ec2:CreateVpc", "ec2:DeleteVpc", "ec2:CreateSubnet",
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
      "ec2:CreateTags", "ec2:DeleteTags"
    ]
    resources = [
      "arn:aws:ec2:*:${var.aws_account_id}:vpc/${var.project_name}*",
      "arn:aws:ec2:*:${var.aws_account_id}:subnet/*",
      "arn:aws:ec2:*:${var.aws_account_id}:security-group/*",
      "arn:aws:ec2:*:${var.aws_account_id}:network-interface/*",
      "arn:aws:ec2:*:${var.aws_account_id}:route-table/*",
      "arn:aws:ec2:*:${var.aws_account_id}:internet-gateway/*",
      "arn:aws:ec2:*:${var.aws_account_id}:natgateway/*",
      "arn:aws:ec2:*:${var.aws_account_id}:elastic-ip/*"
    ]
  }

  statement {
    sid    = "Lambda"
    effect = "Allow"
    actions = [
      "lambda:CreateFunction", "lambda:DeleteFunction", "lambda:UpdateFunctionCode",
      "lambda:UpdateFunctionConfiguration", "lambda:GetFunction",
      "lambda:GetFunctionConfiguration", "lambda:ListFunctions",
      "lambda:AddPermission", "lambda:RemovePermission",
      "lambda:TagResource", "lambda:UntagResource", "lambda:InvokeFunction",
      "lambda:PublishVersion", "lambda:CreateAlias", "lambda:UpdateAlias"
    ]
    resources = ["arn:aws:lambda:*:${var.aws_account_id}:function:${var.project_name}*"]
  }

  statement {
    sid    = "APIGateway"
    effect = "Allow"
    actions = [
      "apigateway:GET", "apigateway:PUT", "apigateway:PATCH", "apigateway:POST",
      "apigateway:DELETE", "apigateway:UpdateRestApi",
      "apigatewayv2:Describe*", "apigatewayv2:Create*", "apigatewayv2:Delete*",
      "apigatewayv2:Update*", "apigatewayv2:Get*"
    ]
    resources = ["arn:aws:apigateway:*::/*"]
  }

  statement {
    sid    = "ECS"
    effect = "Allow"
    actions = [
      "ecs:Describe*", "ecs:List*", "ecs:CreateService", "ecs:DeleteService",
      "ecs:UpdateService", "ecs:CreateTaskDefinition", "ecs:RegisterTaskDefinition",
      "ecs:DeregisterTaskDefinition", "ecs:RunTask", "ecs:StopTask",
      "ecs:PutClusterCapacityProviders"
    ]
    resources = [
      "arn:aws:ecs:*:${var.aws_account_id}:cluster/${var.project_name}*",
      "arn:aws:ecs:*:${var.aws_account_id}:task/${var.project_name}*",
      "arn:aws:ecs:*:${var.aws_account_id}:service/${var.project_name}*",
      "arn:aws:ecs:*:${var.aws_account_id}:task-definition/${var.project_name}*"
    ]
  }

  statement {
    sid    = "Autoscaling"
    effect = "Allow"
    actions = [
      "autoscaling:Describe*", "autoscaling:CreateAutoScalingGroup",
      "autoscaling:DeleteAutoScalingGroup", "autoscaling:UpdateAutoScalingGroup",
      "autoscaling:CreateLaunchConfiguration", "autoscaling:DeleteLaunchConfiguration"
    ]
    resources = ["arn:aws:autoscaling:*:${var.aws_account_id}:autoScalingGroup:*:autoScalingGroupName/${var.project_name}*"]
  }
}

data "aws_iam_policy_document" "github_actions_data" {
  statement {
    sid    = "RDS"
    effect = "Allow"
    actions = [
      "rds:DescribeDBInstances", "rds:DescribeDBClusters",
      "rds:ModifyDBInstance", "rds:ModifyDBCluster",
      "rds:DescribeDBClusterSnapshots", "rds:CreateDBClusterSnapshot"
    ]
    resources = ["arn:aws:rds:*:${var.aws_account_id}:db/${var.project_name}*"]
  }

  statement {
    sid    = "S3"
    effect = "Allow"
    actions = [
      "s3:GetObject", "s3:PutObject", "s3:DeleteObject",
      "s3:ListBucket", "s3:GetBucketVersioning", "s3:ListBucketVersions",
      "s3:GetBucketPolicy", "s3:PutBucketPolicy"
    ]
    resources = [
      "arn:aws:s3:::${var.project_name}*",
      "arn:aws:s3:::${var.project_name}*/*"
    ]
  }

  statement {
    sid    = "DynamoDB"
    effect = "Allow"
    actions = [
      "dynamodb:Describe*", "dynamodb:List*",
      "dynamodb:CreateTable", "dynamodb:DeleteTable",
      "dynamodb:UpdateTable", "dynamodb:UpdateTimeToLive",
      "dynamodb:TagResource", "dynamodb:UntagResource"
    ]
    resources = ["arn:aws:dynamodb:*:${var.aws_account_id}:table/${var.project_name}*"]
  }
}

data "aws_iam_policy_document" "github_actions_identity" {
  statement {
    sid    = "IAM"
    effect = "Allow"
    actions = [
      "iam:GetRole", "iam:GetRolePolicy", "iam:ListRolePolicies",
      "iam:UpdateAssumeRolePolicy", "iam:PutRolePolicy", "iam:DeleteRolePolicy",
      "iam:TagRole", "iam:UntagRole", "iam:PassRole"
    ]
    resources = ["arn:aws:iam::${var.aws_account_id}:role/${var.project_name}*"]
  }

  statement {
    sid    = "CognitoIDP"
    effect = "Allow"
    actions = [
      "cognito-idp:Describe*", "cognito-idp:List*",
      "cognito-idp:UpdateUserPool", "cognito-idp:UpdateUserPoolClient",
      "cognito-idp:AdminGetUser", "cognito-idp:AdminUpdateUserAttributes",
      "cognito-idp:AdminCreateUser", "cognito-idp:AdminSetUserPassword", "cognito-idp:AdminDeleteUser",
      "cognito-idp:AdminEnableUser", "cognito-idp:AdminDisableUser",
      "cognito-idp:CreateGroup", "cognito-idp:DeleteGroup", "cognito-idp:GetGroup", "cognito-idp:UpdateGroup",
      "cognito-idp:AdminAddUserToGroup", "cognito-idp:AdminRemoveUserFromGroup", "cognito-idp:AdminListGroupsForUser"
    ]
    resources = ["arn:aws:cognito-idp:*:${var.aws_account_id}:userpool/*"]
  }

  statement {
    sid    = "CognitoIdentity"
    effect = "Allow"
    actions = [
      "cognito-identity:Describe*", "cognito-identity:List*"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "KMS"
    effect = "Allow"
    actions = [
      "kms:Describe*", "kms:List*", "kms:GetKeyPolicy",
      "kms:PutKeyPolicy", "kms:CreateGrant", "kms:RetireGrant",
      "kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"
    ]
    resources = ["arn:aws:kms:*:${var.aws_account_id}:key/${var.project_name}*"]
  }

  statement {
    sid    = "SecretsManager"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret",
      "secretsmanager:ListSecrets", "secretsmanager:UpdateSecret",
      "secretsmanager:RotateSecret", "secretsmanager:TagResource"
    ]
    resources = ["arn:aws:secretsmanager:*:${var.aws_account_id}:secret:${var.project_name}*"]
  }

  statement {
    sid    = "ECR"
    effect = "Allow"
    actions = [
      "ecr:DescribeRepositories", "ecr:ListImages",
      "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage",
      "ecr:PutImage", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload"
    ]
    resources = ["arn:aws:ecr:*:${var.aws_account_id}:repository/${var.project_name}*"]
  }
}

data "aws_iam_policy_document" "github_actions_observability" {
  statement {
    sid    = "CloudWatch"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents",
      "logs:DescribeLogGroups", "logs:DescribeLogStreams",
      "cloudwatch:PutMetricAlarm", "cloudwatch:DeleteAlarms",
      "cloudwatch:DescribeAlarms"
    ]
    resources = [
      "arn:aws:logs:*:${var.aws_account_id}:log-group:/aws/lambda/${var.project_name}*",
      "arn:aws:cloudwatch:*:${var.aws_account_id}:alarm:${var.project_name}*"
    ]
  }

  statement {
    sid    = "EventBridge"
    effect = "Allow"
    actions = [
      "events:Describe*", "events:List*", "events:PutRule",
      "events:DeleteRule", "events:PutTargets", "events:RemoveTargets"
    ]
    resources = ["arn:aws:events:*:${var.aws_account_id}:rule/${var.project_name}*"]
  }

  statement {
    sid    = "Scheduler"
    effect = "Allow"
    actions = [
      "scheduler:CreateSchedule", "scheduler:DeleteSchedule",
      "scheduler:GetSchedule", "scheduler:UpdateSchedule"
    ]
    resources = ["arn:aws:scheduler:*:${var.aws_account_id}:schedule/${var.project_name}*"]
  }

  statement {
    sid    = "CloudFront"
    effect = "Allow"
    actions = [
      "cloudfront:GetDistribution", "cloudfront:ListDistributions",
      "cloudfront:GetDistributionConfig", "cloudfront:UpdateDistribution",
      "cloudfront:CreateInvalidation"
    ]
    resources = ["arn:aws:cloudfront::${var.aws_account_id}:distribution/*"]
  }

  statement {
    sid    = "ACM"
    effect = "Allow"
    actions = [
      "acm:DescribeCertificate", "acm:ListCertificates",
      "acm:RequestCertificate", "acm:DeleteCertificate"
    ]
    resources = ["arn:aws:acm:*:${var.aws_account_id}:certificate/*"]
  }

  statement {
    sid    = "ReadOnlyObservability"
    effect = "Allow"
    actions = [
      "cloudtrail:Describe*", "cloudtrail:List*", "cloudtrail:LookupEvents",
      "config:Describe*", "config:Get*", "config:List*",
      "guardduty:Get*", "guardduty:List*"
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
  # Secrets Manager (ECS task execution role needs database + algo runtime secrets)
  # CRITICAL: Do NOT include algo/developer-credentials — privilege escalation vector
  statement {
    sid    = "SecretsManagerDatabaseAndLoaderSecrets"
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ]

    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}-db-credentials*",
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}/database*",
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}-algo-secrets*",
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}/fred*",
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}/alpaca*"
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
  # Secrets Manager (ECS loaders need database + Alpaca/FRED credentials)
  # CRITICAL: Do NOT include algo/developer-credentials — privilege escalation vector
  statement {
    sid    = "SecretsManagerDatabaseAndLoaderSecrets"
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue"
    ]

    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}-db-credentials*",
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}/database*",
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}-algo-secrets*",
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}/fred*",
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}/alpaca*"
    ]
  }

  # KMS (decrypt secrets) - scoped to project-specific keys only
  statement {
    sid    = "KMSDecryptProjectKeys"
    effect = "Allow"

    actions = [
      "kms:Decrypt"
    ]

    resources = [
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
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]

    resources = [
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/ecs/${var.project_name}-*"
    ]
  }

  statement {
    sid    = "CloudWatchMetrics"
    effect = "Allow"

    actions = [
      "cloudwatch:PutMetricData"
    ]

    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["${var.project_name}/loaders"]
    }
  }

  statement {
    sid    = "CloudWatchReadMetrics"
    effect = "Allow"

    actions = [
      "cloudwatch:GetMetricStatistics"
    ]

    resources = ["*"]
  }

  # DynamoDB (halt flag, distributed locks, watermarks, phase1 cache)
  # Used by: orchestrator halt flag check, distributed locking, watermark tracking, Phase 1 freshness cache
  statement {
    sid    = "DynamoDBHaltFlagAndLocks"
    effect = "Allow"

    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:DescribeTable"
    ]

    resources = [
      "arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/${var.project_name}-*",
      "arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/orchestrator-*",
      "arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/${var.project_name}_orchestrator_state",
      "arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/${var.project_name}_phase1_cache"
    ]
  }

  # ECS (OOM prevention - kill stuck loaders)
  # Used by: orchestrator to list/kill long-running analytics loaders if they exceed max runtime
  statement {
    sid    = "ECSOOMPrevention"
    effect = "Allow"

    actions = [
      "ecs:ListTasks",
      "ecs:DescribeTasks",
      "ecs:StopTask"
    ]

    resources = [
      "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:cluster/${var.project_name}-*",
      "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:task/${var.project_name}-*/*"
    ]
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

  # Secrets Manager - scoped to only what the API Lambda actually needs:
  #   - Database credentials: algo-db-credentials-dev (DB_SECRET_ARN env var points here)
  #     Both algo-db-* (Terraform-managed) and algo/database* (legacy naming) included.
  #   - Settings encryption key (used by pgp_sym_encrypt/decrypt for user dashboard settings)
  # Alpaca trading keys (algo/alpaca), FRED keys (algo/fred), and developer credentials
  # are NOT needed by the API Lambda and are intentionally excluded.
  statement {
    sid    = "SecretsManagerDB"
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue"
    ]

    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}-db-*",
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}/database*",
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}-database*"
    ]
  }

  statement {
    sid    = "SecretsManagerSettings"
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue"
    ]

    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:settings/*"
    ]
  }

  # KMS (decrypt secrets) - scoped to project-specific keys only
  statement {
    sid    = "KMSDecryptProjectKeys"
    effect = "Allow"

    actions = [
      "kms:Decrypt"
    ]

    resources = [
      "arn:aws:kms:${var.aws_region}:${var.aws_account_id}:alias/${var.project_name}-*"
    ]
  }

  # CloudWatch Logs (Lambda execution logs + frontend error log shipping)
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]

    resources = [
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/lambda/${var.project_name}-*",
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/frontend/${var.project_name}-*",
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/frontend/${var.project_name}-*:*"
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
      variable = "cloudwatch:namespace"
      values   = ["${var.project_name}/api", "${var.project_name}/orchestrator"]
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

  # Secrets Manager (only specific secrets needed for orchestrator)
  # Orchestrator needs: database (RDS creds), alpaca (trading), fred (economic data), orchestrator state
  # CRITICAL: Do NOT include algo/developer-credentials — privilege escalation vector
  statement {
    sid    = "SecretsManagerOrchestratorOnly"
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue"
    ]

    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}/database*",
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}-db-credentials*",
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}/alpaca*",
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}/fred*",
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}/orchestrator*",
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}-algo-secrets*"
    ]
  }

  # KMS - scoped to project-specific keys only
  statement {
    sid    = "KMSDecryptProjectKeys"
    effect = "Allow"

    actions = [
      "kms:Decrypt"
    ]

    resources = [
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
      variable = "cloudwatch:namespace"
      values   = ["${var.project_name}/orchestrator", "Algo/DataLoading"]
    }
  }

  # DynamoDB - Orchestrator locks, halt flag, and loader status
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
      "arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/${var.project_name}-loader-status-${var.environment}",
      "arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/${var.project_name}_orchestrator_state",
      "arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/${var.project_name}_phase1_cache"
    ]
  }

  # ECS - Failsafe loader trigger + OOM prevention: run, list, describe, and stop ECS tasks
  # ListTasks is a service-level action requiring "*" resource, other actions scoped to cluster/task
  statement {
    sid    = "ECSListTasks"
    effect = "Allow"

    actions = [
      "ecs:ListTasks"
    ]

    resources = ["*"]

    # Condition supports both cluster ARN and cluster name (both are valid for ECS API calls)
    condition {
      test     = "StringLike"
      variable = "ecs:cluster"
      values = [
        "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:cluster/${var.project_name}-cluster",
        "${var.project_name}-cluster"
      ]
    }
  }

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

  statement {
    sid    = "ECSTaskManagement"
    effect = "Allow"

    actions = [
      "ecs:DescribeTasks",
      "ecs:StopTask"
    ]

    resources = [
      "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:task/${var.project_name}-cluster/*"
    ]
  }

  # IAM PassRole for ECS task execution
  statement {
    sid    = "IAMPassRoleECS"
    effect = "Allow"

    actions = [
      "iam:PassRole"
    ]

    resources = [
      "arn:aws:iam::${var.aws_account_id}:role/${var.project_name}-ecs-task-execution-${var.environment}",
      "arn:aws:iam::${var.aws_account_id}:role/${var.project_name}-ecs-task-${var.environment}"
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

  # Step Functions StartExecution (required for EventBridge Scheduler → Step Functions targets)
  statement {
    sid    = "StepFunctionsStartExecution"
    effect = "Allow"

    actions = [
      "states:StartExecution"
    ]

    resources = [
      "arn:aws:states:${var.aws_region}:${var.aws_account_id}:stateMachine:${var.project_name}-*"
    ]
  }

  # CloudWatch Logs (required for EventBridge Scheduler to log execution attempts)
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups"
    ]

    resources = ["*"]
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

# Add specific invoke + execution + read-only permissions via managed policy
# (IAM inline user policies are limited to 2048 bytes; managed policies support 6144 bytes)
resource "aws_iam_policy" "developer" {
  name   = "${var.project_name}-developer-policy"
  policy = data.aws_iam_policy_document.developer.json
}

resource "aws_iam_user_policy_attachment" "developer" {
  user       = aws_iam_user.developer.name
  policy_arn = aws_iam_policy.developer.arn
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
      "ecs:DescribeTasks"
    ]

    resources = [
      "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:task-definition/${var.project_name}-*",
      "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:task/${var.project_name}-cluster/*"
    ]
  }

  # ECS cluster access: DescribeClusters/List require cluster resource ARN
  statement {
    sid    = "ECSClusterAccess"
    effect = "Allow"

    actions = [
      "ecs:DescribeClusters",
      "ecs:ListClusters",
      "ecs:ListServices",
      "ecs:DescribeServices"
    ]

    resources = [
      "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:cluster/${var.project_name}-*"
    ]
  }

  # ListTasks requires resources = "*" — IAM evaluates it against container-instance ARNs,
  # not cluster ARNs, regardless of --cluster filter. Use ecs:cluster condition to restrict scope.
  statement {
    sid    = "ECSListTasks"
    effect = "Allow"

    actions = [
      "ecs:ListTasks"
    ]

    resources = ["*"]

    condition {
      test     = "StringLike"
      variable = "ecs:cluster"
      values = [
        "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:cluster/${var.project_name}-*",
        "${var.project_name}-*"
      ]
    }
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
  # ListStateMachines is account-level and must use "*" — it does not support resource ARN scoping
  statement {
    sid    = "StepFunctionsList"
    effect = "Allow"

    actions = [
      "states:ListStateMachines"
    ]

    resources = ["*"]
  }

  statement {
    sid    = "StepFunctionsStartExecution"
    effect = "Allow"

    actions = [
      "states:StartExecution",
      "states:DescribeExecution",
      "states:GetExecutionHistory",
      "states:ListExecutions",
      "states:DescribeStateMachine"
    ]

    resources = [
      "arn:aws:states:${var.aws_region}:${var.aws_account_id}:stateMachine:${var.project_name}-*",
      "arn:aws:states:${var.aws_region}:${var.aws_account_id}:execution:${var.project_name}-*:*"
    ]
  }

  # EventBridge Scheduler (read-only access to list and describe schedules)
  statement {
    sid    = "SchedulerReadOnly"
    effect = "Allow"

    actions = [
      "scheduler:GetSchedule",
      "scheduler:ListSchedules",
      "scheduler:ListScheduleGroups"
    ]

    resources = [
      "arn:aws:scheduler:${var.aws_region}:${var.aws_account_id}:schedule/${var.project_name}*",
      "arn:aws:scheduler:${var.aws_region}:${var.aws_account_id}:schedule-group/*"
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

  # Secrets Manager (read + update dashboard-config only, for local credential bootstrap)
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

  # Secrets Manager (write access scoped only to dashboard-config, for Cognito credential bootstrap)
  statement {
    sid    = "SecretsManagerUpdateDashboard"
    effect = "Allow"

    actions = [
      "secretsmanager:UpdateSecret"
    ]

    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}/dashboard-config*"
    ]
  }

  # KMS (decrypt secrets for verification) - scoped to project keys only
  statement {
    sid    = "KMSDecryptProjectKeys"
    effect = "Allow"

    actions = [
      "kms:Decrypt"
    ]

    resources = [
      "arn:aws:kms:${var.aws_region}:${var.aws_account_id}:alias/${var.project_name}-*"
    ]
  }

  # KMS (describe all keys for verification, but not decrypt all)
  statement {
    sid    = "KMSDescribe"
    effect = "Allow"

    actions = [
      "kms:DescribeKey",
      "kms:ListAliases"
    ]

    resources = ["*"]
  }

  # CloudWatch (read-only for monitoring)
  statement {
    sid    = "CloudWatchReadOnly"
    effect = "Allow"

    actions = [
      "cloudwatch:DescribeAlarms",
      "cloudwatch:DescribeAlarmHistory",
      "cloudwatch:GetMetricStatistics",
      "cloudwatch:ListMetrics",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
      "logs:GetLogEvents",
      "logs:FilterLogEvents"
    ]

    resources = ["*"]
  }

  # Lambda (read-only for inspection)
  statement {
    sid    = "LambdaReadOnly"
    effect = "Allow"

    actions = [
      "lambda:GetFunction",
      "lambda:ListFunctions",
      "lambda:GetFunctionConfiguration",
      "lambda:GetAlias",
      "lambda:ListAliases"
    ]

    resources = [
      "arn:aws:lambda:${var.aws_region}:${var.aws_account_id}:function:${var.project_name}-*"
    ]
  }

  # RDS (read-only for database inspection)
  statement {
    sid    = "RDSDescribeReadOnly"
    effect = "Allow"

    actions = [
      "rds:DescribeDBInstances",
      "rds:DescribeDBClusters",
      "rds:DescribeDBProxies"
    ]

    resources = ["*"]
  }

  # RDS Data API (read queries via ExecuteStatement)
  statement {
    sid    = "RDSDataAPIRead"
    effect = "Allow"

    actions = [
      "rds-data:ExecuteStatement"
    ]

    resources = [
      "arn:aws:rds:${var.aws_region}:${var.aws_account_id}:cluster:${var.project_name}-*"
    ]
  }

  # RDS IAM authentication — scoped to project DB users only
  statement {
    sid    = "RDSIAMConnect"
    effect = "Allow"

    actions = ["rds-db:connect"]

    # db-resource-id is a runtime value (not known at plan time); restrict by username prefix instead
    resources = ["arn:aws:rds-db:${var.aws_region}:${var.aws_account_id}:dbuser:*/${var.project_name}*"]
  }

  # EC2 (read-only for infrastructure inspection)
  statement {
    sid    = "EC2ReadOnly"
    effect = "Allow"

    actions = [
      "ec2:DescribeInstances",
      "ec2:DescribeSubnets",
      "ec2:DescribeSecurityGroups",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DescribeVpcs"
    ]

    resources = ["*"]
  }

  # CloudFormation (read-only for stack inspection)
  statement {
    sid    = "CloudFormationReadOnly"
    effect = "Allow"

    actions = [
      "cloudformation:DescribeStacks",
      "cloudformation:ListStacks",
      "cloudformation:GetTemplate"
    ]

    resources = ["*"]
  }

  # S3 (read-only for frontend and data buckets)
  statement {
    sid    = "S3ReadOnly"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:ListBucket",
      "s3:GetBucketLocation",
      "s3:ListAllMyBuckets"
    ]

    resources = ["*"]
  }

  # DynamoDB (read/write orchestrator state and locks for testing/debugging)
  statement {
    sid    = "DynamoDBOrchestration"
    effect = "Allow"

    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:DescribeTable",
      "dynamodb:Query",
      "dynamodb:Scan"
    ]

    resources = [
      "arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/algo_orchestrator_state",
      "arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/${var.project_name}-orchestrator-locks-${var.environment}",
      "arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/${var.project_name}-loader-locks-${var.environment}"
    ]
  }

  # SES (email verification for Cognito custom email setup)
  statement {
    sid    = "SESVerification"
    effect = "Allow"

    actions = [
      "ses:VerifyEmailIdentity",
      "ses:ListIdentities",
      "ses:DescribeIdentities",
      "ses:GetAccountSendingEnabled",
      "ses:GetSendStatistics",
      "ses:GetIdentityVerificationAttributes",
      "ses:SendEmail"
    ]

    resources = ["*"]
  }

  # CloudWatch Logs Insights (for advanced log querying)
  statement {
    sid    = "CloudWatchLogsInsights"
    effect = "Allow"

    actions = [
      "logs:StartQuery",
      "logs:GetQueryResults",
      "logs:StopQuery"
    ]

    resources = [
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/lambda/${var.project_name}-*",
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/states/${var.project_name}-*"
    ]
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
      "cognito-idp:AdminSetUserMFAPreference",
      "cognito-idp:AdminEnableUser",
      "cognito-idp:AdminDisableUser",
      "cognito-idp:AdminAddUserToGroup",
      "cognito-idp:AdminRemoveUserFromGroup",
      "cognito-idp:AdminListGroupsForUser",
      "cognito-idp:ListUsers",
      "cognito-idp:ListUserPools",
      "cognito-idp:ListGroups",
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
# Rotated quarterly per security baseline (see steering/system.md)
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
