# ============================================================
# Root Module - Local Values
# ============================================================

locals {
  # Standardized common tags for all resources
  common_tags = merge(
    {
      Project   = var.project_name
      Environment = var.environment
      ManagedBy = "terraform"
      CreatedAt = timestamp()
      Region    = var.aws_region
    },
    var.additional_tags
  )

  # Naming convention
  name_prefix = "${var.project_name}-${var.environment}"
}
