# Lambda Layer Management - Centralized

**Status:** Issue #6 resolved. Layer management moved from scattered YAML scripts to Terraform + Python tool.

## Problem Solved

**Before:** Lambda layer building logic scattered across workflows
- `build-lambda-layer.yml`: 150+ lines of shell/Python
- `deploy-staging.yml`: 80+ lines duplicated layer logic
- Hard to version, test, maintain
- Changes to layer format required updating multiple workflows

**After:** Single source of truth
- `terraform/modules/lambda-layers/` defines all layer specifications
- `scripts/build-lambda-layers.py` builds layers consistently
- Workflows simply call the script and invoke Terraform
- Layer definitions are versioned and testable

## Architecture

### Three-Layer System

| Layer | Built By | Stored | Usage |
|-------|----------|--------|-------|
| **API** | `deploy-code.yml` → `build-lambda-layers.py` | S3 (if >50 MB) or inline | API Lambda function |
| **Orchestrator** | `deploy-staging.yml` → `build-lambda-layers.py` | S3 (if >50 MB) or inline | Orchestrator Lambda (staging/dev) |
| **Shared Deps** | Manual `build-lambda-layers.py --layer shared-deps` | Committed to repo | Shared numpy for API & Orchestrator |

### Key Design Decisions

1. **Python for Consistency:** Layer building is a development tool, not infrastructure. Python + subprocess handles pip, S3, AWS CLI uniformly.

2. **Terraform for Definitions:** `terraform/modules/lambda-layers/main.tf` defines layers (name, compatible runtimes, description). Single source of truth.

3. **GitHub Actions Builds:** Workflows still trigger builds (pip install needs Linux manylinux environment). Terraform doesn't build—it publishes and manages versions.

4. **S3 for Large Layers:** Layers >50 MB (inline base64 limit) are uploaded to S3 before publishing. Automatic size detection.

## Usage

### Build Locally

```bash
# Build a single layer
python scripts/build-lambda-layers.py --layer orchestrator --runtime python3.12

# Build and publish to AWS
python scripts/build-lambda-layers.py --layer orchestrator --publish --s3-bucket algo-svc-artifacts-ACCOUNT_ID

# Build all layers
python scripts/build-lambda-layers.py --all
```

### GitHub Actions

`deploy-staging.yml` (minimal example):
```yaml
- name: Build Orchestrator Lambda Layer
  run: |
    python3 scripts/build-lambda-layers.py \
      --layer orchestrator \
      --runtime python3.12 \
      --output-dir terraform

- name: Publish Orchestrator Layer & Extract ARN
  run: |
    # Publish to AWS Lambda (inline or via S3, auto-detected)
    # Extract ARN for Lambda function update
```

## Layer Specifications

Defined in `terraform/modules/lambda-layers/main.tf` → `locals.layers`:

- **shared_deps:** numpy (scipy fails-open), ~30 MB
- **orchestrator:** pip deps + config + algo + utils + monitoring, ~65 MB
- **api:** FastAPI + psycopg2, ~25 MB

Add new layers by:
1. Defining in `locals.layers` in `main.tf`
2. Adding to `LambdaLayerBuilder.LAYERS` in `build-lambda-layers.py`
3. Referencing in workflows or Terraform outputs

## Files Affected

| File | Change |
|------|--------|
| `terraform/modules/lambda-layers/` | NEW module: layer definitions + references |
| `scripts/build-lambda-layers.py` | NEW tool: builds layers consistently |
| `terraform/main.tf` | ADD `module "lambda_layers"` |
| `.github/workflows/deploy-staging.yml` | USE `build-lambda-layers.py` instead of inline script |
| `.github/workflows/build-lambda-layer.yml` | Simplified (can optionally reference the Python script) |

## Deployment Impact

- **No user impact:** Layer ARNs remain the same, versioning unchanged
- **CI/CD impact:** Workflows slightly faster (less duplicate logic)
- **Developer experience:** Can build/test layers locally without AWS access (for non-published layers)
- **Maintenance:** Easier to update layer dependencies (single file per layer)

## Testing Layers Locally

```bash
# Build orchestrator layer
python scripts/build-lambda-layers.py --layer orchestrator

# Check contents
unzip -l terraform/orchestrator-layer.zip | head -20

# Verify dependencies installed
unzip -l terraform/orchestrator-layer.zip | grep "numpy\|config\|algo"
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Layer ZIP not found | Run build script with `--output-dir terraform` |
| "Failed to install dependencies" | Check `lambda/*/requirements.txt` file exists |
| Layer too large (>500 MB) | Reduce or split requirements; scipy is deliberately excluded |
| S3 upload fails | Verify S3 bucket exists and AWS credentials have s3:PutObject permission |
| Layer ARN mismatch in Lambda | Ensure compatible runtimes (python3.11, python3.12) match function runtime |

## Future Enhancements

- [ ] Layer dependency caching (avoid rebuilding unchanged layers)
- [ ] Automated layer version tagging (git tags sync with Lambda version numbers)
- [ ] Layer size monitoring (alert if layer >100 MB)
- [ ] Dependency security scanning (CVE checks on pip install)
