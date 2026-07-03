# Terraform Database Safeguards

## Design Principle: Single Database Architecture

The RDS instance should **ONLY** contain:
- `stocks` database (production data)
- `postgres` (system database, read-only)
- `template0`, `template1` (PostgreSQL internal, read-only)

**Any other database is a misconfiguration and must be removed immediately.**

## Why Single Database?

- ✅ Simplifies routing (all loaders → stocks)
- ✅ Prevents accidental data splits
- ✅ Easier backup/restore
- ✅ Reduces complexity and maintenance burden
- ❌ No multiple isolated environments per RDS instance

## Prevention: IaC-Driven Approach

### 1. Variable Constraint (Terraform)
```hcl
# terraform/modules/database/variables.tf
variable "rds_db_name" {
  description = "Initial database name for RDS"
  type        = string
  default     = "stocks"
  
  validation {
    condition     = var.rds_db_name == "stocks"
    error_message = "Only 'stocks' database is allowed. Multi-database setups are not supported."
  }
}
```

### 2. Documentation (Code Comments)
```hcl
# In aws_db_instance resource
# CRITICAL: Single database design — only "stocks" should exist
# Extra databases indicate misconfiguration and must be dropped manually.
```

### 3. Developer Access (Security Group)
```hcl
# terraform/terraform.tfvars
dev_machine_cidr = "97.130.69.107/32"  # Your current IP for direct access
```

Update this ONLY when your IP changes. Use Terraform for all access changes.

## Response: If Extra Databases Appear

**Immediate Action:**

```bash
export DB_PASSWORD="..."
python3 scripts/cleanup_rds_databases.py --list
python3 scripts/cleanup_rds_databases.py --clean
```

**Investigation:**

1. Check CloudTrail for who created them
2. Review RDS event logs
3. Audit AWS Secrets Manager access
4. If Lambda or API created them, fix the code

**Prevention:**

- Update Terraform validation to be stricter
- Add CloudWatch alarms for database creation events
- Lock down IAM permissions for RDS creation

## Terraform Apply Checklist

Before running `terraform apply`:

- [ ] Verify `rds_db_name = "stocks"` in terraform.tfvars
- [ ] Verify `dev_machine_cidr` matches your current IP
- [ ] Review all database-related changes in `terraform plan`
- [ ] No new `aws_db_instance` resources being created

After running `terraform apply`:

- [ ] Run `scripts/cleanup_rds_databases.py --list`
- [ ] Verify ONLY `stocks` database exists
- [ ] No `algo_trading`, `temp_db`, or other extras

## GitHub Actions Workflow

Add to your deployment workflow:

```yaml
- name: Validate RDS database configuration
  run: |
    export DB_PASSWORD="${{ secrets.RDS_MASTER_PASSWORD }}"
    python3 scripts/cleanup_rds_databases.py --list
    # Fail if extra databases found
    python3 -c "import subprocess; out=subprocess.check_output('python3 scripts/cleanup_rds_databases.py --list', shell=True, text=True); \
      assert 'EXTRA' not in out, 'Extra databases found - pipeline aborted'"
```

## Summary

- ✅ Single `stocks` database by design
- ✅ Developer IP managed via Terraform
- ✅ Cleanup tools for manual intervention
- ✅ IaC-driven validation and safeguards
- ❌ No manual database creation allowed
- ❌ No extra databases permitted
