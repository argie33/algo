# ============================================================
# Database Initialization via Lambda - DISABLED
# ============================================================
# Database initialization is now handled by GitHub Actions workflow
# (deploy-all-infrastructure.yml: build-db-init-lambda job)
#
# The workflow approach is authoritative because:
# 1. Lambda code is deployed BEFORE invocation (no race condition)
# 2. Workflow can retry initialization independently of Terraform
# 3. Separation of concerns: IaC (Terraform) vs. AppOps (Workflow)
#
# All db-init Lambda resources below are DISABLED and will be removed
# from state via "terraform state rm" if they exist from prior runs.
#
# To restore database functionality after schema deletion:
# 1. Ensure lambda/db-init/schema.sql exists and is current
# 2. Run GitHub Actions "Deploy All Infrastructure" workflow
# 3. Workflow will create and invoke Lambda automatically
