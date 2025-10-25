# AWS Data Deployment Guide

## Overview
This guide explains how to deploy the local stock data to AWS RDS and expose it through AWS Lambda API routes.

## Current Status

### Local Data (READY TO SYNC)
- ✅ **stock_scores**: 5,315/5,315 (100%) - COMPLETE
- 🔄 **positioning_metrics**: 1,476/5,315 (27.77%) - Loading
- 🔄 **momentum_metrics**: 1,261/5,307 (23.75%) - Loading

### AWS Lambda Routes (LIVE NOW)
```
GET /api/momentum/stocks/:symbol
GET /api/momentum/leaders
GET /api/momentum/laggards
GET /api/momentum/metrics
GET /api/momentum/range

GET /api/positioning-metrics/stocks/:symbol
GET /api/positioning-metrics/institutional-holders
GET /api/positioning-metrics/insider-ownership
GET /api/positioning-metrics/short-interest
GET /api/positioning-metrics/metrics
GET /api/positioning-metrics/comparison
```

## Prerequisites

### Option A: AWS Secrets Manager (Recommended)
Requires AWS credentials with Secrets Manager access:
```bash
export AWS_SECRET_ARN="arn:aws:secretsmanager:us-east-1:123456789:secret:rds-stocks-xxxxx"
```

### Option B: Direct Credentials
```bash
export AWS_RDS_ENDPOINT="stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com"
export AWS_RDS_USER="postgres"
export AWS_RDS_PASSWORD="your-password-here"
export AWS_RDS_DATABASE="stocks"
```

## Deployment Steps

### Step 1: Create Data Dump (Optional but Recommended)
```bash
cd /home/stocks/algo
bash aws_data_dump.sh
```

This will:
- Verify local database connectivity
- Export positioning_metrics, momentum_metrics, and stock_scores
- Create compressed backup: `/tmp/aws_dumps/stocks_dump_*.sql.gz`
- Show deployment options

### Step 2: Sync Data to AWS RDS

**Method 1: Using Secrets Manager (Recommended)**
```bash
export AWS_SECRET_ARN="arn:aws:secretsmanager:us-east-1:123456789:secret:name"
python3 /home/stocks/algo/sync_data_to_aws.py --full
```

**Method 2: Direct Credentials**
```bash
export AWS_RDS_ENDPOINT="stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com"
export AWS_RDS_USER="postgres"
export AWS_RDS_PASSWORD="your-password"
python3 /home/stocks/algo/sync_data_to_aws.py --full
```

**Method 3: Incremental Sync (Only New/Changed Data)**
```bash
python3 /home/stocks/algo/sync_data_to_aws.py --batch-size 500
```

## API Usage Examples

All endpoints return JSON with data indexed by symbol or metric.

### Momentum Endpoints

**Get momentum for single stock:**
```bash
curl http://lambda-api.endpoint.com/api/momentum/stocks/AAPL
```

**Get top momentum stocks:**
```bash
curl "http://lambda-api.endpoint.com/api/momentum/leaders?limit=10"
```

**Get stocks in momentum range:**
```bash
curl "http://lambda-api.endpoint.com/api/momentum/range?min=-0.1&max=0.1"
```

### Positioning Metrics Endpoints

**Get positioning for single stock:**
```bash
curl http://lambda-api.endpoint.com/api/positioning-metrics/stocks/AAPL
```

**Get stocks by institutional ownership:**
```bash
curl "http://lambda-api.endpoint.com/api/positioning-metrics/institutional-holders?limit=50"
```

**Compare multiple stocks:**
```bash
curl "http://lambda-api.endpoint.com/api/positioning-metrics/comparison?symbols=AAPL,MSFT,GOOGL"
```

## Files Involved

- `/home/stocks/algo/sync_data_to_aws.py` - Main sync script
- `/home/stocks/algo/aws_data_dump.sh` - Dump utility
- `/home/stocks/algo/webapp/lambda/routes/momentum.js` - Lambda routes
- `/home/stocks/algo/webapp/lambda/routes/positioning-metrics.js` - Lambda routes

## Next Steps

1. Provide AWS credentials
2. Run `bash aws_data_dump.sh`
3. Run `python3 sync_data_to_aws.py --full`
4. Verify data in AWS RDS
