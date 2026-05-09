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

# GitHub Actions deployment role - LEAST PRIVILEGE
# Scoped to: this repository only, no wildcard actions
resource "aws_iam_role" "github_actions" {
  name               = "${var.project_name}-svc-github-actions-${var.environment}"
  description        = "GitHub Actions deployment role for ${var.project_name}"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume.json

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-svc-github-actions-${var.environment}"
  })
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

# GitHub Actions policy - CloudFormation & state management only
resource "aws_iam_role_policy" "github_actions" {
  name   = "${var.project_name}-github-actions-policy"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_actions.json
}

data "aws_iam_policy_document" "github_actions" {
  # Terraform resource management - EC2, VPC, Security Groups (read-only - requires wildcard)
  statement {
    sid    = "TerraformEC2Describe"
    effect = "Allow"

    actions = [
      "ec2:Describe*"
    ]

    resources = ["*"]  # AWS requires wildcard for Describe* actions
  }

  # Terraform resource management - EC2, VPC, Security Groups (modifications - scoped to project)
  statement {
    sid    = "TerraformEC2Modify"
    effect = "Allow"

    actions = [
      "ec2:CreateVpc",
      "ec2:DeleteVpc",
      "ec2:CreateSubnet",
      "ec2:DeleteSubnet",
      "ec2:CreateSecurityGroup",
      "ec2:DeleteSecurityGroup",
      "ec2:AuthorizeSecurityGroupIngress",
      "ec2:AuthorizeSecurityGroupEgress",
      "ec2:RevokeSecurityGroupIngress",
      "ec2:RevokeSecurityGroupEgress",
      "ec2:CreateNetworkInterface",
      "ec2:DeleteNetworkInterface",
      "ec2:ModifyNetworkInterfaceAttribute",
      "ec2:CreateRoute",
      "ec2:DeleteRoute",
      "ec2:CreateRouteTable",
      "ec2:DeleteRouteTable",
      "ec2:AssociateRouteTable",
      "ec2:DisassociateRouteTable",
      "ec2:CreateInternetGateway",
      "ec2:DeleteInternetGateway",
      "ec2:AttachInternetGateway",
      "ec2:DetachInternetGateway",
      "ec2:CreateNatGateway",
      "ec2:DeleteNatGateway",
      "ec2:AllocateAddress",
      "ec2:ReleaseAddress",
      "ec2:CreateTags",
      "ec2:DeleteTags"
    ]

    resources = [
      "arn:aws:ec2:${var.aws_region}:${var.aws_account_id}:vpc/${var.project_name}-*",
      "arn:aws:ec2:${var.aws_region}:${var.aws_account_id}:subnet/${var.project_name}-*",
      "arn:aws:ec2:${var.aws_region}:${var.aws_account_id}:security-group/${var.project_name}-*",
      "arn:aws:ec2:${var.aws_region}:${var.aws_account_id}:network-interface/*",
      "arn:aws:ec2:${var.aws_region}:${var.aws_account_id}:route-table/${var.project_name}-*",
      "arn:aws:ec2:${var.aws_region}:${var.aws_account_id}:internet-gateway/${var.project_name}-*",
      "arn:aws:ec2:${var.aws_region}:${var.aws_account_id}:nat-gateway/*",
      "arn:aws:ec2:${var.aws_region}:${var.aws_account_id}:elastic-ip/*"
    ]
  }

  # Terraform resource management - RDS (scoped to project databases)
  statement {
    sid    = "TerraformRDS"
    effect = "Allow"

    actions = [
      "rds:CreateDBInstance",
      "rds:DeleteDBInstance",
      "rds:ModifyDBInstance",
      "rds:DescribeDBInstances",
      "rds:DescribeDBParameterGroups",
      "rds:CreateDBParameterGroup",
      "rds:DeleteDBParameterGroup",
      "rds:ModifyDBParameterGroup",
      "rds:DescribeDBSubnetGroups",
      "rds:CreateDBSubnetGroup",
      "rds:DeleteDBSubnetGroup",
      "rds:AddTagsToResource",
      "rds:ListTagsForResource",
      "rds-db:connect"
    ]

    resources = [
      "arn:aws:rds:${var.aws_region}:${var.aws_account_id}:db/${var.project_name}-*",
      "arn:aws:rds:${var.aws_region}:${var.aws_account_id}:pg:${var.project_name}-*",
      "arn:aws:rds:${var.aws_region}:${var.aws_account_id}:subgrp:${var.project_name}-*"
    ]
  }

  # Terraform resource management - Lambda (scoped to project functions)
  statement {
    sid    = "TerraformLambda"
    effect = "Allow"

    actions = [
      "lambda:CreateFunction",
      "lambda:DeleteFunction",
      "lambda:UpdateFunctionCode",
      "lambda:UpdateFunctionConfiguration",
      "lambda:GetFunction",
      "lambda:ListFunctions",
      "lambda:AddPermission",
      "lambda:RemovePermission",
      "lambda:TagResource",
      "lambda:UntagResource",
      "lambda:ListTags",
      "apigateway:*"
    ]

    resources = [
      "arn:aws:lambda:${var.aws_region}:${var.aws_account_id}:function:${var.project_name}-*"
    ]
  }

  # Terraform resource management - ECS (scoped to project clusters)
  statement {
    sid    = "TerraformECS"
    effect = "Allow"

    actions = [
      "ecs:CreateCluster",
      "ecs:DeleteCluster",
      "ecs:DescribeClusters",
      "ecs:RegisterTaskDefinition",
      "ecs:DeregisterTaskDefinition",
      "ecs:DescribeTaskDefinition",
      "ecs:CreateService",
      "ecs:DeleteService",
      "ecs:UpdateService",
      "ecs:DescribeServices",
      "ecs:TagResource",
      "ecs:UntagResource",
      "ecs:ListTagsForResource",
      "autoscaling:CreateAutoScalingGroup",
      "autoscaling:DeleteAutoScalingGroup",
      "autoscaling:UpdateAutoScalingGroup",
      "autoscaling:DescribeAutoScalingGroups",
      "autoscaling:CreateLaunchConfiguration",
      "autoscaling:DeleteLaunchConfiguration",
      "autoscaling:DescribeLaunchConfigurations",
      "autoscaling:TagResource",
      "autoscaling:UntagResource"
    ]

    resources = [
      "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:cluster/${var.project_name}-*",
      "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:task-definition/${var.project_name}-*:*",
      "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:service/${var.project_name}-*/*",
      "arn:aws:autoscaling:${var.aws_region}:${var.aws_account_id}:autoScalingGroup:*:autoScalingGroupName/${var.project_name}-*",
      "arn:aws:autoscaling:${var.aws_region}:${var.aws_account_id}:launchConfiguration:*:launchConfigurationName/${var.project_name}-*"
    ]
  }

  # Terraform resource management - IAM (scoped to project roles)
  statement {
    sid    = "TerraformIAM"
    effect = "Allow"

    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:GetRole",
      "iam:ListRoles",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:GetRolePolicy",
      "iam:ListRolePolicies",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:ListRoleTags",
      "iam:CreateInstanceProfile",
      "iam:DeleteInstanceProfile",
      "iam:AddRoleToInstanceProfile",
      "iam:RemoveRoleFromInstanceProfile",
      "iam:GetInstanceProfile",
      "iam:ListInstanceProfiles"
    ]

    resources = [
      "arn:aws:iam::${var.aws_account_id}:role/${var.project_name}-*",
      "arn:aws:iam::${var.aws_account_id}:instance-profile/${var.project_name}-*"
    ]
  }

  # Terraform resource management - Cognito (scoped to project pools)
  statement {
    sid    = "TerraformCognito"
    effect = "Allow"

    actions = [
      "cognito-idp:CreateUserPool",
      "cognito-idp:DeleteUserPool",
      "cognito-idp:DescribeUserPool",
      "cognito-idp:UpdateUserPool",
      "cognito-idp:CreateUserPoolClient",
      "cognito-idp:DeleteUserPoolClient",
      "cognito-idp:DescribeUserPoolClient",
      "cognito-idp:UpdateUserPoolClient",
      "cognito-idp:CreateResourceServer",
      "cognito-idp:DeleteResourceServer",
      "cognito-idp:DescribeResourceServer",
      "cognito-idp:UpdateResourceServer",
      "cognito-idp:TagResource",
      "cognito-idp:UntagResource",
      "cognito-idp:ListTagsForResource",
      "cognito-identity:CreateIdentityPool",
      "cognito-identity:DeleteIdentityPool",
      "cognito-identity:DescribeIdentityPool",
      "cognito-identity:UpdateIdentityPool",
      "cognito-identity:TagResource",
      "cognito-identity:UntagResource",
      "cognito-identity:ListTagsForResource"
    ]

    resources = [
      "arn:aws:cognito-idp:${var.aws_region}:${var.aws_account_id}:userpool/${var.aws_region}_*",
      "arn:aws:cognito-identity:${var.aws_region}:${var.aws_account_id}:identitypool/*"
    ]
  }

  # Terraform resource management - CloudFront & ACM (scoped)
  statement {
    sid    = "TerraformCloudFront"
    effect = "Allow"

    actions = [
      "cloudfront:CreateDistribution",
      "cloudfront:DeleteDistribution",
      "cloudfront:DescribeDistribution",
      "cloudfront:GetDistribution",
      "cloudfront:GetDistributionConfig",
      "cloudfront:UpdateDistribution",
      "cloudfront:ListDistributions",
      "cloudfront:TagResource",
      "cloudfront:UntagResource",
      "cloudfront:ListTagsForResource",
      "cloudfront:CreateInvalidation",
      "cloudfront:GetInvalidation",
      "cloudfront:ListInvalidations",
      "cloudfront:CreateOriginAccessControl",
      "cloudfront:DeleteOriginAccessControl",
      "cloudfront:GetOriginAccessControl",
      "cloudfront:ListOriginAccessControls",
      "acm:RequestCertificate",
      "acm:DeleteCertificate",
      "acm:DescribeCertificate",
      "acm:ListCertificates",
      "acm:AddTagsToCertificate",
      "acm:RemoveTagsFromCertificate",
      "acm:ListTagsForCertificate"
    ]

    resources = ["*"]
  }

  # Terraform state management (S3 + DynamoDB)
  statement {
    sid    = "TerraformStateS3"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket"
    ]

    resources = [
      "arn:aws:s3:::${var.project_name}-terraform-state-${var.environment}",
      "arn:aws:s3:::${var.project_name}-terraform-state-${var.environment}/*"
    ]
  }

  statement {
    sid    = "TerraformStateLocking"
    effect = "Allow"

    actions = [
      "dynamodb:DescribeTable",
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:DeleteItem"
    ]

    resources = [
      "arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/${var.project_name}-terraform-locks"
    ]
  }

  # Required for passing roles to services
  statement {
    sid    = "IAMPassRole"
    effect = "Allow"

    actions = [
      "iam:PassRole"
    ]

    resources = [
      aws_iam_role.ecs_task_execution.arn,
      aws_iam_role.ecs_task.arn,
      aws_iam_role.lambda_api.arn,
      aws_iam_role.lambda_algo.arn,
      aws_iam_role.eventbridge_scheduler.arn
    ]
  }

  # RDS operations (specific DB instance)
  statement {
    sid    = "RDSManagement"
    effect = "Allow"

    actions = [
      "rds:DescribeDBInstances",
      "rds:DescribeDBClusters",
      "rds:ListTagsForResource"
    ]

    resources = [
      "arn:aws:rds:${var.aws_region}:${var.aws_account_id}:db:${var.project_name}-*"
    ]
  }

  # ECS cluster operations
  statement {
    sid    = "ECSManagement"
    effect = "Allow"

    actions = [
      "ecs:DescribeCluster",
      "ecs:DescribeServices",
      "ecs:ListTasks",
      "ecs:DescribeTaskDefinition",
      "ecs:DescribeTasks"
    ]

    resources = [
      "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:cluster/${var.project_name}-*",
      "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:service/${var.project_name}-*/*",
      "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:task/${var.project_name}-*/*",
      "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:task-definition/${var.project_name}-*:*"
    ]
  }

  # Lambda operations
  statement {
    sid    = "LambdaManagement"
    effect = "Allow"

    actions = [
      "lambda:GetFunction",
      "lambda:ListFunctions",
      "lambda:GetFunctionCodeSigningConfig",
      "lambda:ListVersionsByFunction"
    ]

    resources = [
      "arn:aws:lambda:${var.aws_region}:${var.aws_account_id}:function:${var.project_name}-*"
    ]
  }

  # S3 bucket operations
  statement {
    sid    = "S3BucketManagement"
    effect = "Allow"

    actions = [
      "s3:GetBucketVersioning",
      "s3:ListBucket",
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject"
    ]

    resources = [
      "arn:aws:s3:::${var.project_name}-*",
      "arn:aws:s3:::${var.project_name}-*/*"
    ]
  }

  # ECR operations
  statement {
    sid    = "ECRAccess"
    effect = "Allow"

    actions = [
      "ecr:GetAuthorizationToken",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:DescribeImages",
      "ecr:ListImages"
    ]

    resources = ["*"] # ECR auth token requires wildcard

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.aws_account_id]
    }
  }

  # Secrets Manager access (read-only for deployment secrets)
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

  # KMS for secret encryption
  statement {
    sid    = "KMSDecrypt"
    effect = "Allow"

    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
      "kms:GenerateDataKey"
    ]

    resources = [
      "arn:aws:kms:${var.aws_region}:${var.aws_account_id}:key/*",
      "arn:aws:kms:${var.aws_region}:${var.aws_account_id}:alias/${var.project_name}-*"
    ]
  }

  # CloudWatch Logs for monitoring
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams"
    ]

    resources = [
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/*",
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/ecs/*"
    ]
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
  # Secrets Manager (read task secrets from Secrets Manager)
  statement {
    sid    = "SecretsManager"
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ]

    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}-*"
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
  # Secrets Manager (read DB credentials)
  statement {
    sid    = "SecretsManager"
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue"
    ]

    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}-*"
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

  # Secrets Manager (read DB credentials)
  statement {
    sid    = "SecretsManager"
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue"
    ]

    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}-*"
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

  # Secrets Manager
  statement {
    sid    = "SecretsManager"
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue"
    ]

    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}-*"
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

  # SNS (publish alerts)
  statement {
    sid    = "SNSPublish"
    effect = "Allow"

    actions = [
      "sns:Publish"
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
