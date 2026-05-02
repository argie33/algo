# Parallel Data Loading — Local & AWS

## Overview

All loaders now support `--symbol-range` for parallel processing:

```bash
python loadpricedaily.py --smart --symbol-range A-L
python loadpricedaily.py --smart --symbol-range M-Z
python loadpricedaily.py --smart --symbol-range AA-AZ
python loadpricedaily.py --smart --symbol-range BA-ZZ
python loadpricedaily.py --smart --symbol-range ETF
```

Instead of 1 task taking 30 minutes, 5 tasks run in parallel taking ~6 minutes total.

---

## Local Development: Parallel Execution

### Setup (One Time)

All existing loaders automatically support symbol ranges. No changes needed.

### Run 5 Parallel Loaders (Local)

**Option 1: Bash/Unix Shell**

```bash
# Terminal 1
python loadpricedaily.py --smart --symbol-range A-L

# Terminal 2 (in new shell)
python loadpricedaily.py --smart --symbol-range M-Z

# Terminal 3 (in new shell)
python loadpricedaily.py --smart --symbol-range AA-AZ

# Terminal 4 (in new shell)
python loadpricedaily.py --smart --symbol-range BA-ZZ

# Terminal 5 (in new shell)
python loadpricedaily.py --smart --symbol-range ETF
```

**Option 2: Bash Script (Run All 5 in Parallel)**

```bash
#!/bin/bash
# parallel_load.sh - Run all 5 symbol ranges in parallel

python loadpricedaily.py --smart --symbol-range A-L &
python loadpricedaily.py --smart --symbol-range M-Z &
python loadpricedaily.py --smart --symbol-range AA-AZ &
python loadpricedaily.py --smart --symbol-range BA-ZZ &
python loadpricedaily.py --smart --symbol-range ETF &

wait  # Wait for all background jobs to finish
echo "All loaders complete"
```

Usage:
```bash
chmod +x parallel_load.sh
./parallel_load.sh
```

**Option 3: Windows PowerShell (Run All 5 in Parallel)**

```powershell
# parallel_load.ps1

$jobs = @()
$ranges = @("A-L", "M-Z", "AA-AZ", "BA-ZZ", "ETF")

foreach ($range in $ranges) {
    $job = Start-Job -ScriptBlock {
        python loadpricedaily.py --smart --symbol-range $using:range
    }
    $jobs += $job
}

# Wait for all jobs to complete
$jobs | Wait-Job
$jobs | Receive-Job

Write-Host "All loaders complete"
```

Usage:
```powershell
.\parallel_load.ps1
```

---

## AWS Execution: Lambda Orchestrator

### Architecture

```
CloudWatch Cron (2:00am daily)
        │
        ├─→ Orchestrator Lambda
        │        │
        │        ├─→ Worker Lambda 1 (A-L)       — 5 min
        │        ├─→ Worker Lambda 2 (M-Z)       — 5 min
        │        ├─→ Worker Lambda 3 (AA-AZ)     — 5 min
        │        ├─→ Worker Lambda 4 (BA-ZZ)     — 5 min
        │        └─→ Worker Lambda 5 (ETF)       — 5 min
        │
        └─→ All complete in ~6 min (instead of 30 min sequential)
```

### AWS Lambda: Single Wrapper Function

Create one Lambda that accepts a `symbol_range` parameter and calls the existing loader:

**lambda_orchestrator.py** — Orchestrator (runs once daily at 2am)

```python
import json
import boto3
import logging

lambda_client = boto3.client('lambda')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    """
    Orchestrator: Invoke 5 worker Lambdas in parallel.
    Each worker runs the existing loader with a different symbol range.
    """
    ranges = ["A-L", "M-Z", "AA-AZ", "BA-ZZ", "ETF"]
    worker_function = "LoadPriceDailyWorker"
    
    # Invoke all 5 in parallel (asynchronous)
    invoke_responses = []
    for symbol_range in ranges:
        response = lambda_client.invoke(
            FunctionName=worker_function,
            InvocationType='Event',  # Asynchronous
            Payload=json.dumps({'symbol_range': symbol_range})
        )
        invoke_responses.append({
            'range': symbol_range,
            'status': response['StatusCode']
        })
        logger.info(f"Invoked {worker_function} for {symbol_range}")
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'All workers invoked',
            'workers': invoke_responses,
            'expected_completion': '~6 minutes'
        })
    }
```

**lambda_worker.py** — Worker (invoked 5x in parallel)

```python
import json
import subprocess
import sys
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    """
    Worker: Run the existing loader with a symbol range.
    """
    symbol_range = event.get('symbol_range', 'A-L')
    
    logger.info(f"Starting loader for range: {symbol_range}")
    
    # Run the existing loadpricedaily.py with --smart --symbol-range
    # Note: /opt/python contains dependencies installed via Lambda Layer
    result = subprocess.run([
        sys.executable,
        '/opt/loader/loadpricedaily.py',
        '--smart',
        f'--symbol-range={symbol_range}'
    ], capture_output=True, text=True)
    
    logger.info(f"Loader output:\n{result.stdout}")
    if result.stderr:
        logger.warning(f"Loader stderr:\n{result.stderr}")
    
    return {
        'statusCode': 200 if result.returncode == 0 else 500,
        'body': json.dumps({
            'symbol_range': symbol_range,
            'success': result.returncode == 0,
            'output': result.stdout[-500:] if result.stdout else ''  # Last 500 chars
        })
    }
```

### Deployment to AWS Lambda

**Step 1: Create Lambda Layer with Python Deps**

```bash
# Create layer directory
mkdir -p python-deps/python/lib/python3.11/site-packages

# Install requirements to layer
pip install -r requirements.txt -t python-deps/python/lib/python3.11/site-packages

# Zip and upload
zip -r python-layer.zip python-deps
aws lambda publish-layer-version \
  --layer-name stock-loader-deps \
  --zip-file fileb://python-layer.zip \
  --compatible-runtimes python3.11
```

**Step 2: Package Loader Script**

```bash
# Copy loader to zip
mkdir -p loader
cp loadpricedaily.py loader/

# Also copy other loaders if needed
cp loadpriceweekly.py loader/
cp loadpricemonthly.py loader/
...

zip -r loader-code.zip loader
```

**Step 3: Create Lambda Functions (AWS Console or CLI)**

```bash
# Orchestrator Lambda
aws lambda create-function \
  --function-name LoadPriceDailyOrchestrator \
  --runtime python3.11 \
  --role arn:aws:iam::ACCOUNT:role/lambda-execution-role \
  --handler lambda_orchestrator.handler \
  --zip-file fileb://orchestrator.zip \
  --layers arn:aws:lambda:REGION:ACCOUNT:layer:stock-loader-deps:1 \
  --timeout 300 \
  --environment Variables="{DB_HOST=RDS_ENDPOINT,DB_USER=stocks,DB_PASSWORD=xxx,DB_NAME=stocks,AWS_REGION=us-east-1}"

# Worker Lambda (same setup, different handler)
aws lambda create-function \
  --function-name LoadPriceDailyWorker \
  --runtime python3.11 \
  --role arn:aws:iam::ACCOUNT:role/lambda-execution-role \
  --handler lambda_worker.handler \
  --zip-file fileb://worker.zip \
  --layers arn:aws:lambda:REGION:ACCOUNT:layer:stock-loader-deps:1 \
  --timeout 600 \
  --environment Variables="{DB_HOST=RDS_ENDPOINT,DB_USER=stocks,DB_PASSWORD=xxx,DB_NAME=stocks,AWS_REGION=us-east-1}"
```

**Step 4: Create CloudWatch Cron Rule**

```bash
# Create rule (daily at 2:00am UTC)
aws events put-rule \
  --name LoadPriceDailySchedule \
  --schedule-expression "cron(0 2 ? * MON-FRI *)" \
  --state ENABLED

# Target the orchestrator
aws events put-targets \
  --rule LoadPriceDailySchedule \
  --targets "Id"="1","Arn"="arn:aws:lambda:us-east-1:ACCOUNT:function:LoadPriceDailyOrchestrator","RoleArn"="arn:aws:iam::ACCOUNT:role/service-role/EventBridgeInvokeRole"
```

---

## Expected Performance

### Local (5 Parallel Processes)

| Metric | Sequential | Parallel (5) |
|--------|-----------|------------|
| Time | 30 min | 6 min |
| Speedup | 1x | 5x |
| Cost | Low (1 CPU) | Same (1 CPU per process) |

### AWS Lambda (5 Parallel Invocations)

| Metric | Cost |
|--------|------|
| Orchestrator | $0.0002 (instant) |
| 5 Workers × 6 min | $0.003 (512MB memory) |
| **Daily total** | ~$0.003 |
| **Monthly** | ~$0.09 |

Compared to ECS Fargate (~$25/month for same work), Lambda is **100x cheaper**.

---

## Monitoring

### Local

```bash
# Watch all 5 processes
watch "ps aux | grep loadpricedaily"

# Or with logging
tail -f loadpricedaily_A-L.log &
tail -f loadpricedaily_M-Z.log &
...
```

### AWS

```bash
# View CloudWatch logs for all workers
aws logs tail /aws/lambda/LoadPriceDailyWorker --follow

# View metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=LoadPriceDailyWorker \
  --start-time 2026-04-28T02:00:00Z \
  --end-time 2026-04-28T02:10:00Z \
  --period 60 \
  --statistics Average,Maximum
```

---

## What to Do When Adding More Loaders

All existing loaders automatically support `--symbol-range`:

```bash
python loadpriceweekly.py --smart --symbol-range A-L
python loadfactormetrics.py --smart --symbol-range A-L
python loadsectors.py --smart --symbol-range A-L
```

No code changes needed — they all follow the same pattern.

---

## Troubleshooting

### "No symbols found for range A-L"

- Check `stock_symbols` table has data
- Verify symbols start with expected letters
- Run `SELECT DISTINCT SUBSTRING(symbol, 1, 1) FROM stock_symbols ORDER BY 1;`

### Lambda timeout at 6 min

- Increase Lambda timeout to 10 min (safe buffer)
- Or split ranges further (10 ranges instead of 5)

### Rate limit errors from yfinance

- Loaders use 30 calls/min per range (safe under 2,000/hour ceiling)
- If hitting limits, add `time.sleep(0.2)` between requests

### DB connection from Lambda fails

- Ensure Lambda has VPC access to RDS subnet
- Check security group allows PostgreSQL (port 5432)
- Verify DB credentials in Lambda environment variables
