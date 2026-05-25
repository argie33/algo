# AWS Deployment Issues Found - 2026-05-25

## Critical Issues

### 1. **Terraform Outputs Not Being Read**
**Status**: CRITICAL - Blocks frontend build
**Error**: "ERROR: Terraform outputs are empty"
**Cause**: The resolve-infra job's terraform output reading is failing
**Impact**: Cannot resolve api_gateway_endpoint, website_url, frontend_bucket_name, etc.
**Location**: `.github/workflows/deploy-code.yml`, line 87

### 2. **Frontend Build Failing**
**Status**: CRITICAL - Blocks frontend deployment
**Error**: "ERROR: Could not resolve API Gateway endpoint"
**Cause**: API_GATEWAY output from resolve-infra is empty
**Impact**: npm run build exits with error, no dist/ folder created
**Location**: `.github/workflows/deploy-code.yml`, line 981-983
**Dependency**: Requires fixing issue #1

### 3. **Frontend Dist Empty**
**Status**: CRITICAL - Blocks S3 sync
**Error**: "ERROR: dist/ is empty!"
**Cause**: Frontend build (npm run build) failed due to issue #2
**Impact**: Cannot sync frontend assets to S3
**Location**: `.github/workflows/deploy-code.yml`, line 1096-1098
**Dependency**: Requires fixing issue #2

### 4. **API Lambda Environment Variables Not Set**
**Status**: CRITICAL - API breaks without DB connection
**Error**: "ERROR: DB_HOST not set in Lambda environment"
**Cause**: Database secret not being retrieved in deployment step
**Impact**: API Lambda cannot connect to RDS database
**Location**: `.github/workflows/deploy-code.yml`, deploy-api job

### 5. **Lambda Provisioned Concurrency Missing Qualifier**
**Status**: CRITICAL - Deploy fails with exit code 252
**Error**: "the following arguments are required: --qualifier"
**Cause**: AWS CLI parameter is missing from the concurrency command
**Impact**: API Lambda deployment exits with error
**Location**: `.github/workflows/deploy-code.yml`, "Add Provisioned Concurrency" step

## Root Cause Analysis

The primary issue is **Issue #1** - the Terraform outputs are not being read from the backend.
This cascades to cause all other issues:

1. No terraform outputs → API_GATEWAY is empty
2. API_GATEWAY empty → npm build fails
3. npm build fails → no dist/ folder
4. No dist/ → cannot sync to S3
5. No terraform outputs → database secret ARN not available
6. No database secret ARN → cannot set Lambda env vars

## Solution Order

1. Fix Terraform output reading in resolve-infra job
2. Fix frontend build step
3. Fix API Lambda environment variables
4. Fix provisioned concurrency command
5. Test full deployment

## Files to Modify

- `.github/workflows/deploy-code.yml` - Main deployment workflow
