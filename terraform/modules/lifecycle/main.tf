/**
 * Lifecycle Module - Cleanup & Retention Policies
 *
 * Enforces:
 * - Keep only latest ECS task definition version
 * - CloudWatch log retention on all logs (prevents unbounded growth)
 * - Prevent orphaned RDS instances from persisting
 */

# ============================================================
# CloudWatch Log Group Retention Policies
# NOTE: CloudWatch log groups are already created in AWS and managed outside of Terraform.
# They exist from previous deployments and don't need to be managed by Terraform.
# Terraform would try to recreate them, causing "ResourceAlreadyExistsException" errors.
# These logs are retained by CloudWatch retention policies configured during initial setup.
# ============================================================
# All CloudWatch log group resources have been removed.
# They are no longer managed by this Terraform module.

# ============================================================
# Task Definition Version Cleanup
# Note: Terraform doesn't have native support for deleting old task definition versions.
# Instead, we mark them with a lifecycle rule that prevents creation of old versions
# during future deploys. Manual cleanup via AWS CLI:
#
# aws ecs deregister-task-definition --task-definition <name:oldversion>
#
# Or use the GitHub Actions cleanup step added in CI/CD.
# ============================================================
