# Terraform Outputs: Version Control & Freshness Tracking

## Problem

Terraform outputs were previously stored only in AWS S3 remote state (stocks-terraform-state bucket), without git version control. This caused:

- **Staleness**: Outputs could be hours/days old if Terraform wasn't re-run
- **No History**: No way to see what outputs were at previous times
- **Sync Issues**: No way to detect if git state diverged from AWS reality
- **No Audit Trail**: Infrastructure changes weren't traceable in commit history

## Solution

Terraform outputs are now:
1. **Version-controlled in git** (`.terraform-outputs.json`)
2. **Timestamped** (includes fetch time and commit hash)
3. **Validated for freshness** (< 24 hours old)
4. **Verified against AWS** (compare git cache vs live state)

## File Structure

`.terraform-outputs.json` contains:
```json
{
  "timestamp": "2026-06-14T15:30:45Z",
  "git_commit": "abc123def456",
  "outputs": {
    "api_gateway_endpoint": { "value": "https://..." },
    "cognito_user_pool_id": { "value": "us-east-1_..." },
    ...
  }
}
```

- **timestamp**: UTC time outputs were fetched (ISO-8601 format)
- **git_commit**: Full git commit hash at time of fetch
- **outputs**: Terraform outputs object (same as `terraform output -json`)

## Scripts

### 1. `init-terraform-outputs.ps1` — First-time setup

Initialize `.terraform-outputs.json` after first Terraform deployment:

```powershell
scripts/init-terraform-outputs.ps1
```

What it does:
- Fetches current outputs from live Terraform
- Creates `.terraform-outputs.json` with timestamp
- Commits to git as baseline

**When to use**: Once after `terraform apply` succeeds for the first time

### 2. `sync-terraform-outputs.ps1` — Manual sync to git

Sync live AWS state to git-tracked file:

```powershell
scripts/sync-terraform-outputs.ps1           # Regular sync
scripts/sync-terraform-outputs.ps1 -DryRun   # Preview without committing
```

What it does:
- Fetches current outputs from live Terraform
- Updates `.terraform-outputs.json` with new timestamp
- Commits to git if changed

**When to use**:
- After major infrastructure changes
- If outputs change outside of normal GitHub Actions deployment
- To manually refresh outputs (normally automatic via CI/CD)

### 3. `verify-terraform-outputs.ps1` — Check freshness & accuracy

Validate cached outputs are fresh and match AWS:

```powershell
scripts/verify-terraform-outputs.ps1              # Default: 24h max age
scripts/verify-terraform-outputs.ps1 -MaxAgeHours 4   # Custom max age
```

What it does:
- Checks if `.terraform-outputs.json` exists and is valid JSON
- Verifies outputs are < 24 hours old (or custom threshold)
- Compares critical outputs against live AWS state
- Reports any mismatches

**Exit codes**:
- `0`: PASS - Outputs are fresh and accurate
- `1`: FAIL - Outputs are stale or inaccurate

**When to use**:
- Before deploying infrastructure changes
- In CI/CD pipelines to validate cache
- To troubleshoot configuration issues

### 4. `get-cached-terraform-outputs.ps1` — Load with fallback

Load outputs from cache with automatic fallback to live AWS:

```powershell
# Load from cache (use cached if fresh, fall back to live if stale)
. scripts/get-cached-terraform-outputs.ps1

# Force fetch from live AWS
. scripts/get-cached-terraform-outputs.ps1 -Refresh

# Custom max age threshold
. scripts/get-cached-terraform-outputs.ps1 -MaxAgeHours 4
```

What it does:
- Tries to load from `.terraform-outputs.json` cache
- Checks freshness (default: 24 hours)
- Falls back to `terraform output` if stale
- If live fetch fails, uses stale cache (with warning)
- Exports as environment variables

**Exported environment variables**:
- `ECR_REPOSITORY_URL`
- `API_LAMBDA_NAME`
- `ALGO_LAMBDA_NAME`
- `API_GATEWAY_ENDPOINT`
- `COGNITO_USER_POOL_ID`
- `COGNITO_USER_POOL_CLIENT_ID`
- `CLOUDFRONT_DOMAIN`
- `WEBSITE_URL`
- `ECS_CLUSTER_NAME`
- `AWS_REGION`

**When to use**: In shell scripts that need Terraform outputs

## Workflows

### GitHub Actions Deployment

`deploy-all-infrastructure.yml` automatically:

1. Runs `terraform apply`
2. Collects outputs via `terraform output -json`
3. Creates `.terraform-outputs.json` with timestamp
4. Commits to git after successful apply
5. Pushes commit back to repository

**No manual action needed** — outputs are automatically saved to git.

### Local Development

#### Option 1: Use cached outputs (recommended)

```powershell
# Verify cache is fresh
scripts/verify-terraform-outputs.ps1

# Dashboard auto-loads from cache or live AWS
python tools/dashboard/dashboard.py
```

#### Option 2: Manual sync before testing

```powershell
# Fetch latest outputs and commit
scripts/sync-terraform-outputs.ps1

# Verify accuracy
scripts/verify-terraform-outputs.ps1

# Now safe to deploy
```

#### Option 3: Force live fetch

```powershell
# Bypass cache, fetch directly from AWS
scripts/verify-terraform-outputs.ps1
scripts/get-cached-terraform-outputs.ps1 -Refresh
```

## Freshness Rules

| Scenario | Action | Max Age |
|----------|--------|---------|
| Normal use (dashboard, deploy) | Use cache | 24 hours |
| Pre-deployment check | Verify freshness | 24 hours |
| CI/CD validation | Run verify script | 24 hours |
| Manual infrastructure changes | Sync immediately | — |
| Troubleshooting | Force live fetch | — |

## Common Tasks

### I just deployed infrastructure — verify everything is tracked

```powershell
git log --oneline -5                    # See recent commits
git show .terraform-outputs.json        # View latest saved outputs
scripts/verify-terraform-outputs.ps1    # Confirm cache matches AWS
```

### I need current outputs for a script

```powershell
# In PowerShell script:
. scripts/get-cached-terraform-outputs.ps1
Write-Host $env:API_GATEWAY_ENDPOINT
```

### Outputs are stale — refresh

```powershell
scripts/sync-terraform-outputs.ps1      # Fetch and commit
git log --oneline -1                    # Verify commit
```

### I modified Terraform variables — check what changed

```powershell
# Before deploy:
git diff .terraform-outputs.json

# Or view history:
git log -p .terraform-outputs.json | head -50
```

### Dashboard won't find API endpoint — debug

```powershell
# Check what's cached:
cat .terraform-outputs.json | jq '.outputs.api_gateway_endpoint'

# Verify against AWS:
scripts/verify-terraform-outputs.ps1

# Force refresh if stale:
scripts/sync-terraform-outputs.ps1
```

## Implementation Details

### When outputs are saved

1. **GitHub Actions** — After every successful `terraform apply`
   - Runs after Terraform Plan step
   - Includes timestamp and commit hash
   - Safe for concurrent deployments (only saves if terraform apply succeeded)

2. **Manual sync** — When running `sync-terraform-outputs.ps1`
   - Fetches live Terraform outputs
   - Compares against previous version
   - Only commits if changed

3. **First-time init** — When running `init-terraform-outputs.ps1`
   - Creates baseline after initial Terraform deployment

### Freshness validation

- Outputs are parsed for `timestamp` field (ISO-8601 UTC)
- Current time is compared: `now - timestamp < MaxAge`
- Default max age: 24 hours
- Scripts automatically fall back to live AWS if cache is stale

### Sync detection

`verify-terraform-outputs.ps1` compares these critical outputs:
- `api_gateway_endpoint`
- `cognito_user_pool_id`
- `cognito_user_pool_client_id`
- `ecr_repository_url`
- `ecs_cluster_name`

If any differ between git cache and AWS, alerts that outputs are stale.

## Troubleshooting

### "No cached outputs found"
Run `init-terraform-outputs.ps1` to create the initial file.

### "Outputs are STALE"
Run `scripts/sync-terraform-outputs.ps1` to fetch fresh outputs from AWS.

### "Failed to parse git outputs"
Verify `.terraform-outputs.json` is valid JSON:
```powershell
Get-Content .terraform-outputs.json | ConvertFrom-Json
```

### "Outputs are stale but sync still fails"
Terraform access may be down. Fallback to environment variables or Secrets Manager:
```powershell
$env:API_GATEWAY_ENDPOINT = "https://..."  # Set manually if needed
```

### Git push failed in workflow
This is non-fatal (handled by `|| true`). It means another push happened concurrently. Re-run the deploy workflow to retry.

## Design Decisions

### Why git track outputs?
- Full audit trail of infrastructure changes
- One commit = one infrastructure snapshot
- Can identify when/why outputs changed
- Allows rollback to previous infrastructure state (in theory)

### Why 24-hour freshness threshold?
- Covers normal deployment cycles (typically daily)
- Catches stale caches from multi-day gaps
- Trades freshness for offline availability (can use cache without AWS access)
- Scripts auto-fallback to live AWS if stale

### Why not always fetch live?
- Faster (no API calls)
- Works offline (if AWS is unreachable)
- Reduces AWS API rate limit usage
- Cached outputs still reflect deployed state (just slightly delayed)

### Why timestamp instead of git-based freshness?
- Git timestamps don't reflect AWS state (reflect when commit happened)
- Need wall-clock time to measure actual age
- Explicit timestamp clearer for debugging
