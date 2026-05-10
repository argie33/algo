# ============================================================
# Bootstrap Module Wrapper
# ============================================================
# This module can be run separately to set up the S3 backend
# and GitHub OIDC provider needed for the main infrastructure.
#
# One-time setup:
#   cd terraform
#   terraform init -upgrade
#   terraform plan -target=module.bootstrap
#   terraform apply -target=module.bootstrap
#
# After bootstrap completes, migrate state to S3 with:
#   terraform init -migrate-state \
#     -backend-config="bucket=stocks-terraform-state" \
#     -backend-config="key=stocks/terraform.tfstate" \
#     -backend-config="region=us-east-1" \
#     -backend-config="encrypt=true" \
#     -backend-config="dynamodb_table=stocks-terraform-locks"

module "bootstrap" {
  source = "./modules/bootstrap"

  aws_region                      = var.aws_region
  terraform_state_bucket_name     = "stocks-terraform-state"
  terraform_lock_table_name       = "stocks-terraform-locks"
}

output "bootstrap" {
  description = "Bootstrap module outputs - use for backend configuration"
  value       = module.bootstrap
  sensitive   = false
}
