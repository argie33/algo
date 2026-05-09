# ============================================================
# Root Module - Local Values
# ============================================================

locals {
  common_tags = merge(
    var.additional_tags,
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  )

  # GitHub repository components for OIDC trust
  github_org  = split("/", var.github_repository)[0]
  github_repo = split("/", var.github_repository)[1]
}
