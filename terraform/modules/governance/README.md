# Governance Module: IaC-Only Enforcement

This module enforces Infrastructure-as-Code (IaC) practices by blocking all manual AWS resource creation outside of Terraform.

## Features

- **Service Control Policies (SCPs)**: Block manual creation of S3, RDS, Lambda, ECS, EC2, and IAM resources
- **AWS Config Rules**: Verify all resources have `terraform:managed` tag
- **Terraform-Only Execution**: Allow only Terraform roles to create/modify infrastructure
- **CloudFormation Blocking**: Prevent CloudFormation stack creation (use Terraform instead)

## Deployment

### Prerequisites

- AWS Organization with SCPs enabled
- Terraform credentials with organization:* permissions
- Root account access (to attach SCPs)

### Deploy

```bash
cd terraform
terraform apply -target=module.governance
```

### Verify

```bash
# Check SCP is attached
aws organizations list-policies-for-target \
  --target-id r-xxxx \
  --filter SERVICE_CONTROL_POLICY

# Check Config rule compliance
aws configservice describe-config-rules \
  --filters Name=ConfigRuleName,Values=require-terraform-tag

# Attempt manual creation (should be blocked)
aws s3api create-bucket --bucket test-bucket
# Error: Access Denied - enforce-iac-only SCP blocks this
```

## Adding Terraform Tags

All Terraform-managed resources automatically receive the `terraform` tag with value `managed`. To add manually:

```hcl
resource "aws_s3_bucket" "example" {
  bucket = "my-bucket"

  tags = {
    terraform = "managed"
    Name      = "example"
  }
}
```

## Exemptions

Certain roles are exempt from SCPs:

- `TerraformRole` - Full access to create/modify resources
- `batch*` roles - AWS Batch internal operations
- `admin*` roles - Secrets Manager changes only

To add an exemption, update `local.terraform_principal_arns` in `main.tf`.

## Rollback

If needed, disable the SCP:

```bash
aws organizations detach-policy \
  --policy-id p-xxxxx \
  --target-id r-xxxx
```

## Costs

- SCPs: Free (part of AWS Organizations)
- Config Rules: $0.10 per rule per day = $3/month
