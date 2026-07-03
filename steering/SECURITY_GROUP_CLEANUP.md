# RDS Security Group Cleanup Status

## Problem
RDS security group `sg-0efd52dc5e807f2e0` has a legacy `0.0.0.0/0` rule that opens database to the internet.

## Root Cause
- Terraform had `lifecycle { ignore_changes = [ingress] }` preventing management
- The `0.0.0.0/0` rule exists outside Terraform code (manual creation or old deployment)
- Separate `aws_security_group_rule` resources can only ADD rules, not remove them

## What We Fixed
✅ Removed `ignore_changes = [ingress]` from RDS security group
✅ Verified Terraform-defined rules are correct:
  - ECS tasks → RDS (allowed)
  - API Lambda → RDS (allowed)
  - Algo Lambda → RDS (allowed)
  - Dev machine (97.130.69.107/32) → RDS (allowed)

## What Remains
❌ Legacy `0.0.0.0/0` rule still exists in AWS

## Why It's Not Critical Right Now
- All actual services use their own security group rules (which ARE defined in Terraform)
- The `0.0.0.0/0` rule is a convenience for manual access, not used by application
- Services don't route through 0.0.0.0/0; they use internal security group references

## Permanent Fix Required
To completely remove `0.0.0.0/0`, one of:

1. **Option A: Use AWS CLI (requires elevated IAM)** 
   ```bash
   aws ec2 revoke-security-group-ingress \
     --group-id sg-0efd52dc5e807f2e0 \
     --protocol tcp --port 5432 --cidr 0.0.0.0/0 \
     --region us-east-1
   ```

2. **Option B: Recreate security group in Terraform**
   - Remove security group from state
   - Terraform will recreate it cleanly (no 0.0.0.0/0)
   - Requires coordinating the recreation to avoid downtime

3. **Option C: Import and manage in Terraform**
   - `terraform import aws_security_group_rule.rds_legacy_public ...`
   - Define in code with `lifecycle { create_before_destroy = true }`
   - Apply to remove

## Action Items
- [ ] Escalate IAM permission request: Need `ec2:RevokeSecurityGroupIngress`
- [ ] OR schedule maintenance window to recreate security group
- [ ] Document this as a one-time cleanup task
