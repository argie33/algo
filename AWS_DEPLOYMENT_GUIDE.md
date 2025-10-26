# AWS Deployment Guide - Stock Analysis Dashboard

## Current Status
- ✅ Frontend built and ready (React + Vite)
- ✅ Backend API created (Express.js Lambda-compatible)
- ✅ Database migration scripts ready
- ✅ Local data pipeline fully functional
- ✅ Stock scores populated (5,278 stocks)
- ⏳ AWS deployment pending

## Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                     AWS Infrastructure                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐     ┌────────────────┐   ┌────────────┐ │
│  │  CloudFront  │────▶│  S3 (Static)   │   │ API Gateway│ │
│  └──────────────┘     └────────────────┘   └─────┬──────┘ │
│       Frontend               Frontend              │         │
│                                                    │         │
│  ┌──────────────────────────────────────────────┐ │         │
│  │  Lambda (Express.js Backend)                 │◀┘         │
│  ├──────────────────────────────────────────────┤           │
│  │ • /api/scores                                │           │
│  │ • /api/momentum/*                            │           │
│  │ • /api/positioning/*                         │           │
│  └──────────────┬───────────────────────────────┘           │
│                 │                                            │
│  ┌──────────────▼──────────────────────────────┐            │
│  │    RDS PostgreSQL Database                  │            │
│  ├──────────────────────────────────────────────┤            │
│  │ • stock_scores (5,278 stocks)               │            │
│  │ • momentum_metrics                          │            │
│  │ • positioning_metrics                       │            │
│  │ • quality_metrics, growth_metrics, etc.     │            │
│  └──────────────────────────────────────────────┘            │
│                                                              │
│  ┌──────────────────────────────────────────────┐            │
│  │    Lambda (Data Pipeline)                   │            │
│  ├──────────────────────────────────────────────┤            │
│  │ • EventBridge (scheduled triggers)          │            │
│  │ • loadmomentum, loadpositioning, etc.       │            │
│  └──────────────────────────────────────────────┘            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Deployment Steps

### Phase 1: Frontend Deployment
```bash
cd /home/stocks/algo/webapp/frontend

# Build is already complete in dist/
# Deploy to AWS S3
aws s3 sync dist/ s3://stocks-dashboard-frontend/ --delete

# Configure CloudFront distribution (one-time setup)
# Origin: S3 bucket
# Default root object: index.html
# Error pages: 404 → /index.html (for SPA routing)
```

### Phase 2: Backend Deployment (Express → Lambda)
```bash
cd /home/stocks/algo/webapp/lambda

# Install dependencies
npm install

# Create Lambda deployment package
zip -r lambda-deployment.zip . -x "node_modules/*" "dist/*"

# Upload to AWS Lambda
# Function name: stocks-api
# Runtime: Node.js 20.x
# Handler: index.handler
```

### Phase 3: Database Setup
```bash
# Create RDS PostgreSQL instance
# Instance class: db.t3.medium
# Storage: 100 GB
# Multi-AZ: Yes

# Import data
psql -h <rds-endpoint> -U postgres < aws_data_dump.sql
```

### Phase 4: API Gateway Configuration
```bash
# Create REST API
# Resource: /api (proxy all traffic to Lambda)
# Methods: ANY
# Integration: Lambda Function (stocks-api)
# CORS: Enable
```

## Quick Start for AWS Deployment

### What's Ready Now:
✅ Frontend dist/ folder (1.8 MB bundled)
✅ Backend lambda code with all routes
✅ Database schema + 5,278 stock scores
✅ Docker images for data loaders

### Next Actions:
1. Get AWS credentials (Lambda, RDS, S3, CloudFront)
2. Run: `bash /home/stocks/algo/deploy-to-aws.sh`
3. Monitor deployment progress
4. Test endpoints

