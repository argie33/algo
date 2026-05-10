# CRITICAL: Loaders Container Image Missing

**Severity:** CRITICAL - Blocks all loader deployment  
**Impact:** ECS tasks will fail to start because the container image doesn't exist  
**Status:** ⚠️ BLOCKING ISSUE - Requires implementation before deployment

---

## Problem

The Terraform configuration is set up to deploy 40 data loaders as ECS Fargate tasks:
```terraform
image = "${var.ecr_repository_uri}:${var.environment}-latest"
```

**However:**
- ❌ No Dockerfile exists to build the loaders container image
- ❌ ECR repository is empty or has placeholder image
- ❌ 40 Python loader scripts exist locally but aren't containerized
- ❌ No build pipeline to push loaders image to ECR

**Result:** When ECS tries to run `aws ecs run-task`, it will fail with image not found error.

---

## What Needs to Be Built

### 1. **Dockerfile for Loaders Container**
Location: `Dockerfile.loaders` (in repo root)

```dockerfile
# Dockerfile.loaders - Data loaders container
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all loader scripts
COPY load*.py .
COPY loadbuysell*.py .
COPY load_*.py .
COPY algo_*.py .

# Copy database schema/init scripts if needed
COPY *.sql ./

# Entry point: detect loader type from LOADER_TYPE env var
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
```

### 2. **Docker Entrypoint Script**
Location: `docker-entrypoint.sh`

```bash
#!/bin/bash
# Map LOADER_TYPE env var to actual Python script

LOADER_TYPE=${LOADER_TYPE:-"stock_symbols"}

# Map loader names to Python files
case "$LOADER_TYPE" in
  stock_symbols)           exec python3 loadstocksymbols.py ;;
  stock_prices_daily)      exec python3 loadpricedaily.py ;;
  stock_prices_weekly)     exec python3 loadpriceweekly.py ;;
  # ... 37 more mappings ...
  algo_metrics_daily)      exec python3 load_algo_metrics_daily.py ;;
  *)
    echo "Unknown LOADER_TYPE: $LOADER_TYPE"
    exit 1
    ;;
esac
```

### 3. **Build & Push Pipeline**
Location: `.github/workflows/build-loaders-image.yml`

```yaml
name: Build & Push Loaders Image

on:
  push:
    paths:
      - 'load*.py'
      - 'Dockerfile.loaders'
      - 'docker-entrypoint.sh'
      - '.github/workflows/build-loaders-image.yml'
    branches:
      - main

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      
      - name: Login to ECR
        run: aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_REGISTRY
        env:
          ECR_REGISTRY: ${{ secrets.AWS_ACCOUNT_ID }}.dkr.ecr.us-east-1.amazonaws.com
      
      - name: Build & Push
        run: |
          docker build -f Dockerfile.loaders -t stocks-loaders:latest .
          docker tag stocks-loaders:latest $ECR_REGISTRY/stocks-loaders:dev-latest
          docker push $ECR_REGISTRY/stocks-loaders:dev-latest
```

---

## Current Architecture Gap

```
┌─────────────────────────────────────────────────┐
│  Terraform Configuration (READY)                │
│  - 40 ECS task definitions ✓                    │
│  - 33 EventBridge schedules ✓                   │
│  - IAM roles & networking ✓                     │
│  - ECS cluster & ECR repository ✓               │
└─────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────┐
│  Container Image (MISSING) ❌                   │
│  - No Dockerfile                                │
│  - No build pipeline                            │
│  - ECR repository empty                         │
└─────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────┐
│  Loader Scripts (READY)                         │
│  - 40 Python scripts exist locally ✓            │
│  - Run correctly on local/Docker ✓              │
└─────────────────────────────────────────────────┘
```

---

## Deployment Flow (After Image is Built)

```
1. Developer pushes loader script changes
   ↓
2. GitHub Actions build-loaders-image.yml
   - Builds Dockerfile.loaders
   - Tags image as stocks-loaders:dev-latest
   - Pushes to ECR
   ↓
3. (Optional) Deploy terraform/modules/loaders
   - Creates task definitions referencing the image
   - Creates EventBridge schedules
   ↓
4. EventBridge triggers at scheduled time
   - Starts ECS task with loaders:dev-latest image
   - Maps LOADER_TYPE to Python script
   - Loader runs and loads data
```

---

## How to Fix (Priority: HIGH)

### Step 1: Create Dockerfile.loaders
```bash
cat > Dockerfile.loaders << 'EOF'
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY load*.py .
COPY loadbuysell*.py .
COPY load_*.py .
COPY algo_*.py .
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
EOF
```

### Step 2: Create docker-entrypoint.sh
Map all 40 LOADER_TYPE values to their Python files

### Step 3: Create GitHub workflow to build & push image
Use AWS ECR login + Docker build + push

### Step 4: Test locally
```bash
docker build -f Dockerfile.loaders -t stocks-loaders:latest .
docker run -e LOADER_TYPE=stock_symbols stocks-loaders:latest
```

### Step 5: Deploy to AWS
```bash
gh workflow run build-loaders-image.yml
# Wait for image to push to ECR
gh workflow run deploy-loaders.yml
```

---

## Related Files That Will Change

- ✅ `terraform/modules/loaders/main.tf` - Already configured correctly
- ❌ `Dockerfile.loaders` - **MUST CREATE**
- ❌ `docker-entrypoint.sh` - **MUST CREATE**
- ❌ `.github/workflows/build-loaders-image.yml` - **MUST CREATE**
- ✓ `docker-compose.yml` - May want to add loaders service for local testing

---

## Docker Entrypoint Template

```bash
#!/bin/bash

LOADER_TYPE=${LOADER_TYPE:-"stock_symbols"}

case "$LOADER_TYPE" in
  # Stock data
  stock_symbols)           exec python3 loadstocksymbols.py ;;
  stock_prices_daily)      exec python3 loadpricedaily.py ;;
  stock_prices_weekly)     exec python3 loadpriceweekly.py ;;
  stock_prices_monthly)    exec python3 loadpricemonthly.py ;;
  etf_prices_daily)        exec python3 loadetfpricedaily.py ;;
  etf_prices_weekly)       exec python3 loadetfpriceweekly.py ;;
  etf_prices_monthly)      exec python3 loadetfpricemonthly.py ;;

  # Financial statements
  financials_annual_income)      exec python3 loadannualincomestatement.py ;;
  financials_annual_balance)     exec python3 loadannualbalancesheet.py ;;
  financials_annual_cashflow)    exec python3 loadannualcashflow.py ;;
  financials_quarterly_income)   exec python3 loadquarterlyincomestatement.py ;;
  financials_quarterly_balance)  exec python3 loadquarterlybalancesheet.py ;;
  financials_quarterly_cashflow) exec python3 loadquarterlycashflow.py ;;
  financials_ttm_income)         exec python3 loadttmincomestatement.py ;;
  financials_ttm_cashflow)       exec python3 loadttmcashflow.py ;;

  # Earnings
  earnings_history)   exec python3 loadearningshistory.py ;;
  earnings_revisions) exec python3 loadearningsrevisions.py ;;
  earnings_surprise)  exec python3 loadearningssurprise.py ;;
  earnings_sp500)     exec python3 load_sp500_earnings.py ;;

  # Market & economic
  market_overview)         exec python3 loadmarket.py ;;
  market_indices)          exec python3 loadmarketindices.py ;;
  sector_performance)      exec python3 loadsectors.py ;;
  relative_performance)    exec python3 loadrelativeperformance.py ;;
  seasonality)             exec python3 loadseasonality.py ;;
  econ_data)               exec python3 loadecondata.py ;;
  aaiidata)                exec python3 loadaaiidata.py ;;
  naaim_data)              exec python3 loadnaaim.py ;;
  feargreed)               exec python3 loadfeargreed.py ;;
  calendar)                exec python3 loadcalendar.py ;;

  # Sentiment & analysis
  analyst_sentiment)   exec python3 loadanalystsentiment.py ;;
  analyst_upgrades)    exec python3 loadanalystupgradedowngrade.py ;;
  social_sentiment)    exec python3 loadsentiment.py ;;
  factor_metrics)      exec python3 loadfactormetrics.py ;;
  stock_scores)        exec python3 loadstockscores.py ;;

  # Trading signals
  signals_daily)      exec python3 loadbuyselldaily.py ;;
  signals_weekly)     exec python3 loadbuysellweekly.py ;;
  signals_monthly)    exec python3 loadbuysellmonthly.py ;;
  signals_etf_daily)  exec python3 loadbuysell_etf_daily.py ;;
  etf_signals)        exec python3 loadetfsignals.py ;;

  # Algo metrics
  algo_metrics_daily) exec python3 load_algo_metrics_daily.py ;;

  *)
    echo "ERROR: Unknown LOADER_TYPE=$LOADER_TYPE"
    echo "Valid options:"
    echo "  - stock_symbols, stock_prices_*, etf_prices_*"
    echo "  - financials_*, earnings_*"
    echo "  - market_*, sector_*, seasonality, econ_data, etc."
    echo "  - analyst_*, social_*, factor_*, stock_scores"
    echo "  - signals_*, etf_signals"
    echo "  - algo_metrics_daily"
    exit 1
    ;;
esac
```

---

## Timeline to Production

1. **Today:** Create Dockerfile + entrypoint + build workflow
2. **Test:** Build image locally, test with `docker run`
3. **Deploy:** Push to ECR, deploy Terraform loaders module
4. **Verify:** Check EventBridge triggers loader tasks
5. **Monitor:** Verify data loads in database

---

## Status Summary

| Component | Status | What to Do |
|-----------|--------|-----------|
| Terraform Config | ✅ Complete | Nothing - ready to deploy |
| Python Loader Scripts | ✅ Complete | Already in repo |
| Docker Image | ❌ Missing | **CREATE NOW** |
| Build Pipeline | ❌ Missing | **CREATE NOW** |
| ECR Repo | ✅ Exists | Empty - will be filled by build |

**BLOCKER:** Cannot deploy loaders without Docker image.

