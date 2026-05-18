# Terraform AWS Provider Version Constraint Issue

## Problem

Deployment fails at Terraform Init with error:
```
Error: Failed to query available provider packages

Could not retrieve the list of available versions for provider
hashicorp/aws: locked provider registry.terraform.io/hashicorp/aws 6.45.0
does not match configured version constraint >= 4.0.0, < 6.0.0; must use
terraform init -upgrade to allow selection of new versions
```

## Root Cause

- **Terraform lock file** (`terraform/.terraform.lock.hcl`) has AWS provider **v6.45.0** pinned
- **Terraform configuration** (`terraform/versions.tf`) specifies constraint **`>= 4.0.0, < 6.0.0`**
- These are incompatible: the lock file has v6.x but the config forbids v6.x

## Solution

Choose ONE of the following:

### Option A: Update Version Constraint (Recommended)
Update `terraform/versions.tf` to allow AWS provider 6.x:

```hcl
terraform {
  required_version = ">= 1.7.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0.0, < 7.0.0"  # Changed from "< 6.0.0" to "< 7.0.0"
    }
    # ... other providers
  }
}
```

### Option B: Downgrade AWS Provider
Regenerate lock file with AWS v5.x:

```bash
cd terraform
rm .terraform.lock.hcl
terraform init -upgrade  # Will select v5.x if constrained to < 6.0.0
```

### Option C: Update Lock File (Most Direct)
Just update the constraint to match the lock file:

```bash
cd terraform
terraform init -upgrade  # Let Terraform update lock file to v6.45.0
```

## Recommendation

**Use Option A** - update the version constraint to allow AWS 6.x. The lock file is already using a newer, presumably tested version of AWS provider.

## Implementation

```bash
# Edit the file
nano terraform/versions.tf
# Change line with aws version constraint
# From: version = ">= 4.0.0, < 6.0.0"
# To:   version = ">= 4.0.0, < 7.0.0"

# Then commit and push
git add terraform/versions.tf
git commit -m "fix: Update AWS provider version constraint to allow v6.x"
git push origin main
```

## Verification

After fix, deployment should progress past "Terraform Init" step.

---

**Status:** Awaiting fix to unblock deployment  
**Impact:** Blocks all infrastructure updates until resolved
