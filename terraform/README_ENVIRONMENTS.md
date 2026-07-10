# Terraform Environment-Specific Configuration

## Overview

This Terraform infrastructure uses environment-specific variable files to ensure proper configuration across development, staging, and production environments.

## Files

- **`terraform.tfvars`** — Local development (default, no env var needed)
- **`dev.tfvars`** — Development environment (explicitly specify with `-var-file=dev.tfvars`)
- **`staging.tfvars`** — Staging/testing environment (production-like, cost-optimized)
- **`prod.tfvars`** — Production environment (full security, compliance, monitoring)

## Key Differences Between Environments

### Frontend & API Configuration

| Setting | Dev | Staging | Prod |
|---------|-----|---------|------|
| `cloudfront_enabled` | `false` (S3 direct) | `true` | `true` |
| `api_cors_allowed_origins` | localhost + computed | CloudFront domain | CloudFront domain (empty, set by CI/CD) |
| `frontend_origin` | `http://localhost:5173` | CloudFront domain (CI/CD) | CloudFront domain (CI/CD) |
| Cognito callbacks | localhost + CloudFront | CloudFront only | CloudFront only |

### Database Configuration

| Setting | Dev | Staging | Prod |
|---------|-----|---------|------|
| `rds_instance_class` | `db.t4g.small` | `db.t4g.small` | `db.t4g.small` |
| `rds_multi_az` | `false` | `false` | `true` (high availability) |
| `rds_backup_retention_period` | 1 day | 7 days | 30 days |
| `enable_rds_kms_encryption` | `false` | `false` | `true` (compliance) |
| `enable_rds_proxy` | `false` | `false` | `true` (connection pooling) |
| `db_ssl_mode` | `require` | `require` | `require` |

### Monitoring & Alerting

| Setting | Dev | Staging | Prod |
|---------|-----|---------|------|
| `enable_performance_alarms` | `false` | `false` | `true` |
| `enable_resource_alarms` | `false` | `false` | `true` |
| `enable_data_quality_monitors` | `false` | `false` | `true` |
| `cloudwatch_log_retention_days` | 1 day | 7 days | 30 days |
| `guardduty_enabled` | `false` | `false` | `true` |
| `vpc_flow_logs_enabled` | `false` | `false` | `true` |

### Security & Compliance

| Setting | Dev | Staging | Prod |
|---------|-----|---------|------|
| `db_deletion_protection` | `true` | `true` | `true` |
| `enforce_iac_only` | `true` | `true` | `true` |
| `cloudtrail_enabled` | `true` | `true` | `true` |
| `cognito_mfa_configuration` | optional | optional | **required** |
| `cognito_advanced_security_mode` | OFF | AUDIT | ENFORCED |
| `s3_encryption_kms_key_id` | none | none | customer-managed (SOC2) |

## Usage

### Local Development

```bash
# Use default terraform.tfvars (no -var-file needed)
terraform init
terraform plan
terraform apply

# OR explicitly use dev.tfvars
terraform plan -var-file=dev.tfvars
terraform apply -var-file=dev.tfvars
```

### Staging Deployment

```bash
terraform plan -var-file=staging.tfvars
terraform apply -var-file=staging.tfvars
```

### Production Deployment

```bash
# CI/CD ONLY: Do not run locally
terraform plan -var-file=prod.tfvars
terraform apply -var-file=prod.tfvars

# Environment variables set by GitHub Actions:
export TF_VAR_cloudfront_domain="d2u93283nn45h2.cloudfront.net"
export TF_VAR_api_cors_allowed_origins='["https://d2u93283nn45h2.cloudfront.net"]'
export TF_VAR_sns_alert_email="ops@company.com"
export TF_VAR_alert_smtp_host="smtp.gmail.com"
export TF_VAR_alert_smtp_user="alerts@company.com"
export TF_VAR_alert_smtp_password="<app-specific-password>"
```

## Dynamic Configuration (Computed Values)

The following values are **computed automatically** by Terraform `locals` based on the `environment` variable and module outputs. Do NOT hardcode these.

### CORS Configuration (`local.cors_allowed_origins`)

- **Dev:** Includes `localhost:5173`, `localhost:3000`, and any `api_cors_allowed_origins` from tfvars
- **Staging/Prod:** Only includes production origins from `api_cors_allowed_origins` (no localhost)

**Logic:**
```hcl
cors_allowed_origins = var.environment == "dev" ? concat(
  var.api_cors_allowed_origins,
  ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]
) : var.api_cors_allowed_origins
```

### Cognito Callback URLs (`local.cognito_callback_urls`)

- **Dev:** Includes `http://localhost:5173/` + CloudFront domain (if enabled)
- **Prod:** Only CloudFront domain

**Logic:**
```hcl
cognito_callback_urls = var.environment == "dev" ? concat(
  ["http://localhost:5173/", "http://localhost:5173/auth/callback", "http://127.0.0.1:5173/"],
  var.cloudfront_enabled ? ["https://${var.cloudfront_domain}/", "https://${var.cloudfront_domain}/auth/callback"] : []
) : (
  var.cloudfront_enabled ? ["https://${var.cloudfront_domain}/", "https://${var.cloudfront_domain}/auth/callback"] : []
)
```

## Fixed Hardcoded Values (Previously Problematic)

The following were previously hardcoded and would break when switching environments. Now they are dynamic:

### ✅ Fixed: DB_PORT
- **Before:** Hardcoded as `"5432"` string in Lambda/ECS environment variables
- **After:** Dynamic from `var.db_port` (default 5432), passed through all modules via `local.db_port`
- **Modules:** services, loaders, monitoring
- **Impact:** Allows changing database port without manual fixes in 10+ places

### ✅ Fixed: DB_SSL
- **Before:** Hardcoded as `"require"` in Lambda/ECS environment variables
- **After:** Dynamic from `var.db_ssl_mode`, computed in `local.db_ssl_mode`, passed to all modules
- **Modules:** services, loaders, monitoring
- **Impact:** Allows disabling SSL for troubleshooting without code changes

### ✅ Fixed: API CORS Origins
- **Before:** Hardcoded as `["http://localhost:5173", "http://localhost:3000"]` with CloudFront domain
- **After:** Computed by `local.cors_allowed_origins` (dev-specific, then production)
- **Modules:** services (API Gateway)
- **Impact:** Automatic handling of localhost vs production domains

### ✅ Fixed: Cognito Callback URLs
- **Before:** Hardcoded localhost URLs only, no production domain support
- **After:** Computed by `local.cognito_callback_urls` (environment-aware)
- **Modules:** cognito
- **Impact:** Production login works with CloudFront domain; dev login works with localhost

## CI/CD Integration

GitHub Actions automatically:

1. Selects correct tfvars file based on branch/tag:
   - `main` branch → uses `prod.tfvars`
   - `staging` branch → uses `staging.tfvars`
   - Pull requests → uses `dev.tfvars` (no-op plan only)

2. Discovers CloudFront domain after creation:
   ```bash
   CLOUDFRONT_DOMAIN=$(terraform output -raw cloudfront_domain)
   export TF_VAR_cloudfront_domain="$CLOUDFRONT_DOMAIN"
   export TF_VAR_api_cors_allowed_origins="[\"https://$CLOUDFRONT_DOMAIN\"]"
   ```

3. Passes environment variables for production secrets:
   ```bash
   export TF_VAR_sns_alert_email="${{ secrets.ALERT_EMAIL_ADDRESS }}"
   export TF_VAR_alert_smtp_host="${{ secrets.ALERT_SMTP_HOST }}"
   # ... etc
   ```

## Validation & Safety

All variables include validation constraints to prevent misconfiguration:

- `db_port`: must be 1-65535
- `db_ssl_mode`: must be one of `disable`, `allow`, `prefer`, `require`, `verify-ca`, `verify-full`
- `environment`: must be `dev`, `staging`, or `prod`
- `rds_instance_class`: must match valid AWS RDS instance types
- `cognito_mfa_configuration`: must be `OFF`, `OPTIONAL`, or `REQUIRED`

## Troubleshooting

### Issue: CORS errors in production

**Check:**
1. `TF_VAR_api_cors_allowed_origins` is set to CloudFront domain in CI/CD
2. `cloudfront_enabled = true` in prod.tfvars
3. CloudFront domain is available in outputs: `terraform output cloudfront_domain`

### Issue: Cognito login fails in production

**Check:**
1. `TF_VAR_cloudfront_domain` is set in CI/CD
2. Cognito callback URLs include CloudFront domain: `terraform output cognito_callback_urls`
3. Callback URL exactly matches what the frontend redirects to (https, no trailing slash)

### Issue: Database connection timeout

**Check:**
1. `db_port` matches RDS instance port (default 5432)
2. `db_ssl_mode` matches RDS SSL requirement (`require` for AWS RDS)
3. Security group allows egress to RDS on correct port

## Cost Optimization Notes

- **Dev:** Disabled CloudFront (~$7-10/month saved), no provisioned concurrency (~$13/month), no RDS Proxy (~$150/month) = ~$170/month savings
- **Staging:** No provisioned concurrency, no RDS Proxy, no KMS encryption = ~$163/month savings vs prod
- **Prod:** All features enabled for security, compliance, and performance

## See Also

- `steering/GOVERNANCE.md` — Architecture & rules
- `steering/OPERATIONS.md` — Operations & CI/CD
- `.github/workflows/deploy-all-infrastructure.yml` — CI/CD pipeline
