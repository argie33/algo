# ============================================================
# Root Module - Local Values
# ============================================================

locals {
  # Standardized common tags for all resources
  common_tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
      Region      = var.aws_region
    },
    var.additional_tags
  )

  # Naming convention
  name_prefix = "${var.project_name}-${var.environment}"

  # Extract GitHub organization and repository from "owner/repo" format
  github_org  = split("/", var.github_repository)[0]
  github_repo = split("/", var.github_repository)[1]
}
