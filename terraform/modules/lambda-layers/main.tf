# ============================================================
# Lambda Layers Module
# ============================================================
# Centralized management of Lambda layer configurations.
#
# Design: Terraform manages layer definitions and references.
# Layers are built by scripts/build-lambda-layers.py (called by GitHub Actions).
# Terraform then publishes and manages versions.

locals {
  shared_deps = {
    name              = "${var.project_name}-shared-deps-${var.environment}"
    requirements_file = "${path.root}/lambda-layer-requirements.txt"
    compatible_runtimes = ["python3.12"]
    description       = "Shared dependencies: numpy (scipy fails-open)"
  }

  orchestrator = {
    name              = "${var.project_name}-orchestrator-layer-${var.environment}"
    requirements_file = "${path.root}/../lambda/algo_orchestrator/requirements.txt"
    compatible_runtimes = ["python3.11", "python3.12"]
    description       = "Orchestrator dependencies + config + algo + utils + monitoring"
  }

  api = {
    name              = "${var.project_name}-api-layer-${var.environment}"
    requirements_file = "${path.root}/../lambda/api/requirements.txt"
    compatible_runtimes = ["python3.12"]
    description       = "API dependencies only"
  }
}

# Shared Dependencies Layer (committed to repo)
resource "aws_lambda_layer_version" "shared_deps" {
  count                    = fileexists("${path.root}/lambda/shared-deps-layer.zip") ? 1 : 0
  filename                 = "${path.root}/lambda/shared-deps-layer.zip"
  layer_name               = local.shared_deps.name
  compatible_runtimes      = local.shared_deps.compatible_runtimes
  source_code_hash         = filebase64sha256("${path.root}/lambda/shared-deps-layer.zip")
  compatible_architectures = ["x86_64"]

  lifecycle {
    create_before_destroy = true
  }
}

# API Layer (published by GitHub Actions, reference via data source)
data "aws_lambda_layer_version" "api_deps" {
  layer_name         = local.api.name
  compatible_runtime = "python3.12"
}

# Orchestrator Layer (published by GitHub Actions, reference via data source)
data "aws_lambda_layer_version" "orchestrator_deps" {
  count              = var.orchestrator_layer_enabled ? 1 : 0
  layer_name         = local.orchestrator.name
  compatible_runtime = "python3.12"
}
