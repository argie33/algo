# Governance module: enforce IaC-only resource creation via SCPs and resource tagging
# Block all manual AWS API calls outside of Terraform

locals {
  terraform_principal_arns = [
    "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/terraform*",
    "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/TerraformRole",
  ]
}

data "aws_caller_identity" "current" {}
data "aws_organizations_organization" "current" {}

# ==============================================================================
# Service Control Policy: Enforce IaC + Terraform tagging requirement
# ==============================================================================
resource "aws_organizations_policy" "enforce_iac_only" {
  name        = "enforce-iac-only"
  description = "Deny all manual AWS resource creation outside of Terraform. Requires terraform:managed tag."
  type        = "SERVICE_CONTROL_POLICY"
  content = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DenyUnmanagedS3"
        Effect = "Deny"
        Action = [
          "s3:CreateBucket",
          "s3:PutBucketPolicy",
          "s3:PutBucketEncryption",
          "s3:PutBucketVersioning",
          "s3:PutBucketLogging",
        ]
        Resource = "arn:aws:s3:::*"
        Condition = {
          StringNotEquals = {
            "aws:ResourceTag/terraform" = "managed"
          }
        }
      },
      {
        Sid    = "DenyUnmanagedEC2"
        Effect = "Deny"
        Action = [
          "ec2:RunInstances",
          "ec2:CreateSecurityGroup",
          "ec2:CreateVpc",
          "ec2:CreateSubnet",
        ]
        Resource = "*"
        Condition = {
          StringNotLike = {
            "aws:PrincipalArn" = local.terraform_principal_arns
          }
        }
      },
      {
        Sid    = "DenyUnmanagedRDS"
        Effect = "Deny"
        Action = [
          "rds:CreateDBInstance",
          "rds:CreateDBCluster",
          "rds:ModifyDBInstance",
        ]
        Resource = "*"
        Condition = {
          StringNotLike = {
            "aws:PrincipalArn" = local.terraform_principal_arns
          }
        }
      },
      {
        Sid    = "DenyUnmanagedLambda"
        Effect = "Deny"
        Action = [
          "lambda:CreateFunction",
          "lambda:UpdateFunctionCode",
          "lambda:UpdateFunctionConfiguration",
        ]
        Resource = "*"
        Condition = {
          StringNotLike = {
            "aws:PrincipalArn" = local.terraform_principal_arns
          }
        }
      },
      {
        Sid    = "DenyUnmanagedECS"
        Effect = "Deny"
        Action = [
          "ecs:CreateCluster",
          "ecs:CreateService",
          "ecs:RegisterTaskDefinition",
        ]
        Resource = "*"
        Condition = {
          StringNotLike = {
            "aws:PrincipalArn" = concat(local.terraform_principal_arns, [
              "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/*batch*"
            ])
          }
        }
      },
      {
        Sid    = "DenyCloudFormation"
        Effect = "Deny"
        Action = [
          "cloudformation:CreateStack",
          "cloudformation:UpdateStack",
          "cloudformation:DeleteStack",
        ]
        Resource = "*"
      },
      {
        Sid    = "DenyManualSecretsCreation"
        Effect = "Deny"
        Action = [
          "secretsmanager:CreateSecret",
          "secretsmanager:PutSecretValue",
        ]
        Resource = "*"
        Condition = {
          StringNotLike = {
            "aws:PrincipalArn" = concat(local.terraform_principal_arns, [
              "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/admin*"
            ])
          }
        }
      },
      {
        Sid    = "DenyManualIAMChanges"
        Effect = "Deny"
        Action = [
          "iam:CreateRole",
          "iam:CreatePolicy",
          "iam:AttachRolePolicy",
          "iam:PutRolePolicy",
        ]
        Resource = "*"
        Condition = {
          StringNotLike = {
            "aws:PrincipalArn" = local.terraform_principal_arns
          }
        }
      },
    ]
  })
}

# Attach SCP to root
resource "aws_organizations_policy_target_attachment" "enforce_iac_root" {
  target_id       = data.aws_organizations_organization.current.roots[0].id
  policy_id       = aws_organizations_policy.enforce_iac_only.id
  depends_on      = [aws_organizations_policy.enforce_iac_only]
}

# ==============================================================================
# Config Rule: Ensure all resources have terraform:managed tag
# ==============================================================================
resource "aws_config_config_rule" "require_terraform_tag" {
  name = "require-terraform-tag"

  source {
    owner             = "AWS"
    source_identifier = "REQUIRED_TAGS"
  }

  input_parameters = jsonencode({
    tag1Key = "terraform"
    tag1Value = "managed"
  })

  scope {
    compliance_resource_types = [
      "AWS::S3::Bucket",
      "AWS::RDS::DBInstance",
      "AWS::Lambda::Function",
      "AWS::EC2::Instance",
      "AWS::ECS::Cluster",
    ]
  }
}

# ==============================================================================
# Outputs
# ==============================================================================
output "scp_id" {
  description = "Service Control Policy ID"
  value       = aws_organizations_policy.enforce_iac_only.id
}

output "scp_name" {
  description = "Service Control Policy name"
  value       = aws_organizations_policy.enforce_iac_only.name
}

output "config_rule_name" {
  description = "AWS Config rule name"
  value       = aws_config_config_rule.require_terraform_tag.name
}
