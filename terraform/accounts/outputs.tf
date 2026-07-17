# ============================================================
# Account Creation Outputs
# ============================================================

output "account_migration_summary" {
  description = "Summary of new account and migration setup"
  value = {
    old_account_id                   = var.old_account_id
    old_account_email                = "edgebrookecapital@gmail.com"
    new_account_id                   = try(aws_organizations_account.edgebrookelabs.id, "pending")
    new_account_email                = var.new_account_email
    rds_snapshot_id                  = try(aws_db_snapshot.final_backup.id, "pending")
    rds_snapshot_status              = try(aws_db_snapshot.final_backup.status, "pending")
    cross_account_role_arn           = try(aws_iam_role.cross_account_deployment.arn, "pending")
    new_account_terraform_state      = try(aws_s3_bucket.new_account_terraform_state.id, "pending")
    terraform_lock_table             = try(aws_dynamodb_table.new_account_lock_table.name, "pending")
    status                           = try(aws_organizations_account.edgebrookelabs.status, "pending")
  }

  depends_on = [
    aws_organizations_account.edgebrookelabs,
    aws_db_snapshot.final_backup,
    aws_iam_role.cross_account_deployment
  ]
}

output "next_steps" {
  description = "Steps to complete the migration"
  value = <<-EOT
    MIGRATION WORKFLOW - Next Steps:

    1. VERIFY NEW ACCOUNT CREATION
       - Account ID: ${try(aws_organizations_account.edgebrookelabs.id, "PENDING")}
       - Status: ${try(aws_organizations_account.edgebrookelabs.status, "PENDING")}
       - Wait for status to be "ACTIVE" (10-15 seconds)

    2. VERIFY RDS SNAPSHOT
       - Snapshot ID: ${try(aws_db_snapshot.final_backup.id, "PENDING")}
       - Status: ${try(aws_db_snapshot.final_backup.status, "pending")}
       - Wait for status to be "available" (5-15 minutes depending on size)

    3. RESTORE SNAPSHOT IN NEW ACCOUNT
       - Copy snapshot to new account using shared access
       - Restore as "algo-db" in new account RDS
       - Update terraform/new-account/terraform.tfvars with new account ID

    4. DEPLOY INFRASTRUCTURE TO NEW ACCOUNT
       - cd terraform/new-account
       - terraform init
       - terraform apply -var-file=terraform.tfvars

    5. VERIFY NEW ACCOUNT FUNCTIONALITY
       - Test all loaders, Lambda, ECS tasks
       - Verify data freshness
       - Run dashboard in AWS mode

    6. CLOSE OLD ACCOUNT
       - aws ec2 disable-fast-snapshot-restores  (cleanup)
       - aws organizations close-account --account-id 626216981288
       - Account marked for deletion after 90 days

    Timeline: ~30-45 minutes total
  EOT
}
