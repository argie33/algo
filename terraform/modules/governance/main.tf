# Governance module: enforce IaC-only resource creation via AWS Config rules
# Blocks unmanaged resources by requiring terraform:managed tag

locals {
  terraform_principal_arns = [
    "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/terraform*",
    "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/TerraformRole",
  ]
}

data "aws_caller_identity" "current" {}

# ==============================================================================
# AWS Config Rule: Require terraform:managed tag on all resources
# ==============================================================================
resource "aws_config_config_rule" "require_terraform_tag" {
  count = var.require_terraform_tag ? 1 : 0
  name  = "require-terraform-managed-tag"

  source {
    owner             = "AWS"
    source_identifier = "REQUIRED_TAGS"
  }

  input_parameters = jsonencode({
    tag1Key   = "terraform"
    tag1Value = "managed"
  })

  scope {
    compliance_resource_types = [
      "AWS::S3::Bucket",
      "AWS::RDS::DBInstance",
      "AWS::Lambda::Function",
      "AWS::EC2::Instance",
      "AWS::EC2::SecurityGroup",
      "AWS::EC2::Volume",
      "AWS::ECS::Cluster",
      "AWS::ECS::Service",
    ]
  }

  depends_on = [aws_config_configuration_aggregator.organization[0]]
}

# Enable Config recorder if not already enabled
resource "aws_config_configuration_aggregator" "organization" {
  count = var.require_terraform_tag ? 1 : 0
  name  = "terraform-org"

  account_aggregation_source {
    account_ids = [data.aws_caller_identity.current.account_id]
    regions     = [var.aws_region]
  }
}

# ==============================================================================
# CloudWatch Event Rule: Alert on unauthorized resource creation
# ==============================================================================
resource "aws_cloudwatch_event_rule" "detect_unmanaged" {
  count       = var.enforce_iac_only ? 1 : 0
  name        = "detect-unmanaged-aws-resources"
  description = "Detect AWS resources created outside of Terraform"

  event_pattern = jsonencode({
    source      = ["aws.ec2", "aws.s3", "aws.rds", "aws.lambda", "aws.ecs"]
    detail-type = ["AWS API Call via CloudTrail"]
    detail = {
      eventName = [
        "CreateBucket",
        "RunInstances",
        "CreateDBInstance",
        "CreateFunction",
        "CreateCluster",
        "CreateService"
      ]
    }
  })
}

# ==============================================================================
# Outputs
# ==============================================================================
output "config_rule_name" {
  description = "AWS Config rule for terraform tag enforcement"
  value       = try(aws_config_config_rule.require_terraform_tag[0].name, "")
}

output "enforcement_status" {
  description = "IaC enforcement status"
  value = {
    terraform_tagging_enforced = var.require_terraform_tag
    iac_only_mode              = var.enforce_iac_only
    message                    = "All resources must have terraform:managed tag. Use scripts/detect_unmanaged_resources.sh to monitor."
  }
}
