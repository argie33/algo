environment               = "dev"
aws_region                = "us-east-1"
project_name              = "algo"
algo_schedule_expression  = "cron(30 21 ? * MON-FRI *)"  # 5:30pm ET (21:30 UTC)
cognito_enabled           = false  # Public API access (no authentication required) — API Gateway route auth disabled

# Orchestrator configuration (moved from GitHub Secrets)
execution_mode              = "auto"
orchestrator_dry_run        = false
orchestrator_log_level      = "info"
data_patrol_enabled         = true
data_patrol_timeout_ms      = 30000

# NOTE: rds_password is set via TF_VAR_rds_password environment variable
# For local development, export: export TF_VAR_rds_password="YourSecurePasswordHere"
# Or create terraform.tfvars.local (gitignored) with: rds_password = "..."
