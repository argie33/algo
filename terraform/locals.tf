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

  # AWS account ID (used in 12+ places across modules)
  aws_account_id = data.aws_caller_identity.current.account_id

  # Database port (single source of truth)
  db_port = var.db_port

  # Lambda layer name (auto-computed if not provided)
  lambda_layer_name = coalesce(var.lambda_layer_name, "${var.project_name}-orchestrator-layer")

  # Node.js environment (inferred from var.environment if not provided)
  node_env = var.node_env != "" ? var.node_env : (var.environment == "dev" ? "development" : "production")

  # Dev mode flag (inferred from var.environment if not provided)
  dev_mode = var.dev_mode != "" ? var.dev_mode : tostring(var.environment == "dev")
}
