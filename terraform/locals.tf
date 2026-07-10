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

  # Database configuration (single source of truth)
  db_port     = var.db_port
  db_ssl_mode = var.db_ssl_mode

  # Lambda layer name (auto-computed if not provided)
  lambda_layer_name = coalesce(var.lambda_layer_name, "${var.project_name}-orchestrator-layer")

  # Node.js environment (inferred from var.environment if not provided)
  node_env = var.node_env != "" ? var.node_env : (var.environment == "dev" ? "development" : "production")

  # Dev mode flag (inferred from var.environment if not provided)
  dev_mode = var.dev_mode != "" ? var.dev_mode : tostring(var.environment == "dev")

  # CORS and Frontend configuration (dynamic, environment-aware)
  # In dev: allow localhost. In production: strict origin validation.
  cors_allowed_origins = var.environment == "dev" ? concat(
    var.api_cors_allowed_origins,
    ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]
  ) : var.api_cors_allowed_origins

  # Frontend callback URLs for Cognito (environment-aware)
  # In dev: include localhost. In production: only include CloudFront domain.
  cognito_callback_urls = var.environment == "dev" ? concat(
    ["http://localhost:5173/", "http://localhost:5173/auth/callback", "http://127.0.0.1:5173/"],
    var.cloudfront_enabled ? ["https://${var.cloudfront_domain}/", "https://${var.cloudfront_domain}/auth/callback"] : []
  ) : (
    var.cloudfront_enabled ? ["https://${var.cloudfront_domain}/", "https://${var.cloudfront_domain}/auth/callback"] : []
  )

  cognito_logout_urls = var.environment == "dev" ? concat(
    ["http://localhost:5173/", "http://127.0.0.1:5173/"],
    var.cloudfront_enabled ? ["https://${var.cloudfront_domain}/"] : []
  ) : (
    var.cloudfront_enabled ? ["https://${var.cloudfront_domain}/"] : []
  )
}
