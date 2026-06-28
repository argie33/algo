# ============================================================
# Bootstrap Module - Outputs
# ============================================================

output "state_bucket_name" {
  description = "S3 bucket name for Terraform state"
  value       = aws_s3_bucket.terraform_state.id
}

output "state_bucket_arn" {
  description = "S3 bucket ARN for Terraform state"
  value       = aws_s3_bucket.terraform_state.arn
}

output "lock_table_name" {
  description = "DynamoDB table name for state locking"
  value       = aws_dynamodb_table.terraform_locks.id
}

output "github_oidc_provider_arn" {
  description = "ARN of GitHub OIDC provider"
  value       = aws_iam_openid_connect_provider.github.arn
}

output "backend_config" {
  description = "Backend configuration for root module"
  value       = <<-EOT
# Add to root terraform/backend.tf or use with: terraform init -backend-config=...

bucket         = "${aws_s3_bucket.terraform_state.id}"
key            = "stocks/terraform.tfstate"
region         = "${var.aws_region}"
encrypt        = true
dynamodb_table = "${aws_dynamodb_table.terraform_locks.id}"
EOT
}

output "setup_instructions" {
  description = "Instructions for completing bootstrap"
  value       = <<-EOT

✅ Bootstrap Infrastructure Created

Next steps:

1. Save your bootstrap state (one-time backup):
   aws s3 cp terraform.tfstate s3://${aws_s3_bucket.terraform_state.id}/bootstrap/terraform.tfstate.backup

2. Switch root module to S3 backend:
   cd ../..
   terraform init -migrate-state \
     -backend-config="bucket=${aws_s3_bucket.terraform_state.id}" \
     -backend-config="key=stocks/terraform.tfstate" \
     -backend-config="region=${var.aws_region}" \
     -backend-config="encrypt=true" \
     -backend-config="dynamodb_table=${aws_dynamodb_table.terraform_locks.id}"

3. Verify connection:
   terraform plan

4. Clean up bootstrap local state (optional):
   rm -rf .terraform terraform.tfstate*
   rm -rf bootstrap/.terraform bootstrap/terraform.tfstate*

EOT
}
