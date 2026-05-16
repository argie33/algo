environment               = "dev"
aws_region                = "us-east-1"
project_name              = "algo"
algo_schedule_expression  = "cron(30 22 ? * MON-FRI *)"  # 6:30pm ET fallback (22:30 UTC) — Step Functions triggers earlier when data is ready
cognito_enabled           = false  # Public API access (no authentication required)

# NOTE: rds_password is set via TF_VAR_rds_password environment variable
# For local development, export: export TF_VAR_rds_password="YourSecurePasswordHere"
# Or create terraform.tfvars.local (gitignored) with: rds_password = "..."
