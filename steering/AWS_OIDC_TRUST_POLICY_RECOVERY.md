# EMERGENCY: AWS OIDC Trust Policy Recovery (CI/CD deadlock)

**Use when:** every GitHub Actions workflow that touches AWS fails with
`Could not assume role with OIDC: Not authorized to perform sts:AssumeRoleWithWebIdentity`.
Confirmed broken continuously since 2026-07-15 (zero successful deploys since), and as of
2026-08-31 this also fails `Trigger Orchestrator (Scheduled)` - i.e. it is no longer just a
deploy problem, the production orchestrator itself is not being invoked by its schedule.

**Why this can't be fixed by pushing another commit or re-running a workflow:** the only
workflow that could run `terraform apply` to fix the broken trust policy (`deploy-all-infrastructure.yml`)
itself authenticates by assuming the SAME broken role - every one of its runs fails identically.
Nothing in GitHub Actions can break this loop. It requires one manual `aws iam` command run by
a human holding real AWS IAM admin credentials, outside GitHub Actions entirely, after which
`terraform apply` will work again and can reconcile everything else (see verification below).

## Step 1: Confirm which role and account are actually affected

You need admin AWS CLI access configured locally (not the GitHub Actions role - that's the
broken one) for this whole procedure.

```bash
# Get the account ID your admin credentials point at:
aws sts get-caller-identity --query Account --output text

# Confirm this matches the AWS_ACCOUNT_ID GitHub secret (repo Settings > Secrets and
# variables > Actions - visible to repo admins). If they don't match, you have credentials
# for the wrong AWS account - stop and find the right ones.

# Get the exact role ARN GitHub Actions is trying to assume (also a repo secret,
# AWS_GITHUB_ACTIONS_ROLE_ARN). It should look like:
#   arn:aws:iam::<ACCOUNT_ID>:role/algo-svc-github-actions-prod
# (role name pattern is `${project_name}-svc-github-actions-${environment}` from
# terraform/modules/iam/main.tf - "algo" and "prod" per terraform/prod.tfvars, but confirm
# against the actual secret value rather than assuming).
```

## Step 2: Inspect the role's current (broken) trust policy

```bash
aws iam get-role --role-name algo-svc-github-actions-prod --query 'Role.AssumeRolePolicyDocument'
```

Compare the `Condition.StringEquals` value for `token.actions.githubusercontent.com:sub`
against what it should be (Step 3). A mismatch here - wrong repo, wrong branch ref, wrong
format, or the condition/principal missing entirely - is the bug. This drift happened because
no `terraform apply` has landed since the trust-policy fix was written in Terraform (commit
`96f87041b`, 2026-08-11) - the source has been correct for 3 weeks, AWS has not.

## Step 3: Apply the correct trust policy directly (bypasses the deadlock)

This exact JSON matches `terraform/modules/iam/main.tf`'s `github_actions_assume` policy
document with this repo's real values (`github_repository` defaults to `argie33/algo`,
`github_ref_path` defaults to `refs/heads/main` - both from `terraform/variables.tf`). Applying
it manually means the next successful `terraform apply` will find no drift on this resource,
not fight your manual fix.

```bash
cat > /tmp/trust-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:sub": "repo:argie33/algo:ref:refs/heads/main"
        }
      }
    }
  ]
}
EOF
# Replace ACCOUNT_ID above with the real account ID from Step 1 before running this.

aws iam update-assume-role-policy \
  --role-name algo-svc-github-actions-prod \
  --policy-document file:///tmp/trust-policy.json
```

**If the OIDC provider itself doesn't exist yet** (`aws iam get-role` in Step 2 errors, or
`aws iam list-open-id-connect-providers` shows nothing for `token.actions.githubusercontent.com`),
the problem is one level deeper than a stale trust policy - the provider was never created or
was deleted. That's a bigger, separate fix (`terraform/modules/bootstrap/main.tf` owns it) and
this document doesn't cover it; escalate rather than guessing at a provider ARN/thumbprint by hand.

## Step 4: Verify the deadlock is actually broken

```bash
# Re-run the most recently failed run of each of these three workflows (or wait for the
# next scheduled trigger) and confirm a real success, not just "main looks right":
gh run list --workflow=validate-secrets.yml --limit 3
gh run list --workflow=trigger-orchestrator-scheduled.yml --limit 3
gh run list --workflow=deploy-all-infrastructure.yml --limit 3
gh run list --workflow=deploy-ecs-image.yml --limit 3
```

Once `deploy-all-infrastructure.yml` succeeds, a subsequent normal `terraform apply` from CI
will reconcile the rest of the account against current `main` - including the DB Multi-AZ/backup/
deletion-protection settings in `terraform/prod.tfvars`, which cannot be confirmed live from a
repo-only session either (see `ci_cd_deploy_broken_39_days_confirmed_20260824` in project memory
for the full blast-radius list: every fix merged to main since 2026-07-15 has been sitting
undeployed).

## After recovery

Delete `/tmp/trust-policy.json` (contains your real account ID). Consider whether a break-glass
IAM user/role with independent (non-OIDC) credentials should exist for exactly this failure
mode going forward, so a future OIDC break doesn't require console/CloudShell access to fix -
none currently exists in this codebase (checked 2026-08-31).
