# Scoring System Migration Guide

## Overview
The scoring system has been consolidated from three separate scripts (daily, weekly, monthly) into a single unified script that handles all time periods.

## Changes Made

### 1. Unified Script
- **New**: `loadscores.py` - Single script that handles all time periods
- **Removed**: 
  - `loadscoresdaily.py`
  - `loadscoresweekly.py`
  - `loadscoresmonthly.py`

### 2. Database Schema
The unified script creates tables with a `period_type` column to differentiate between daily, weekly, and monthly scores:
- All score tables now include `period_type` and `period_ending` columns
- Old period-specific tables (e.g., `quality_scores_daily`) are dropped automatically

### 3. Infrastructure Changes
- **CloudFormation**: Updated `template-app-ecs-tasks.yml`
  - Replaced 3 task definitions with single `ScoresTaskDefinition`
  - Replaced 3 services with single `ScoresService`
  - Replaced 3 image tag parameters with single `ScoresImageTag`
- **Dockerfile**: New `Dockerfile.scores` replaces the three separate Dockerfiles
- **GitHub Actions**: Updated `deploy-infrastructure.yml` to use single image tag

### 4. Environment Variables
The unified script uses these environment variables:
- `PERIOD_TYPE`: Set to "daily", "weekly", or "monthly"
- `SYMBOL_LIMIT`: Number of symbols to process (defaults: daily=100, weekly=50, monthly=25)

## Deployment Instructions

### 1. Build and Push Docker Image
```bash
# Build the unified scores image
docker build -f Dockerfile.scores -t stocks-scores:latest .

# Tag for ECR
docker tag stocks-scores:latest <account-id>.dkr.ecr.<region>.amazonaws.com/stocks-scores:latest

# Push to ECR
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/stocks-scores:latest
```

### 2. Run Different Time Periods
To run the unified script for different periods, override the environment variables:

```bash
# Daily scores
aws ecs run-task \
  --cluster stocks-cluster \
  --task-definition scores-loader \
  --overrides '{
    "containerOverrides": [{
      "name": "scores-loader",
      "environment": [
        {"name": "PERIOD_TYPE", "value": "daily"},
        {"name": "SYMBOL_LIMIT", "value": "100"}
      ]
    }]
  }'

# Weekly scores
aws ecs run-task \
  --cluster stocks-cluster \
  --task-definition scores-loader \
  --overrides '{
    "containerOverrides": [{
      "name": "scores-loader",
      "environment": [
        {"name": "PERIOD_TYPE", "value": "weekly"},
        {"name": "SYMBOL_LIMIT", "value": "50"}
      ]
    }]
  }'

# Monthly scores
aws ecs run-task \
  --cluster stocks-cluster \
  --task-definition scores-loader \
  --overrides '{
    "containerOverrides": [{
      "name": "scores-loader",
      "environment": [
        {"name": "PERIOD_TYPE", "value": "monthly"},
        {"name": "SYMBOL_LIMIT", "value": "25"}
      ]
    }]
  }'
```

### 3. Scheduling (If Needed)
If you want to schedule these runs, create EventBridge rules that trigger the ECS task with the appropriate environment variable overrides.

## Benefits of Consolidation
1. **Single codebase**: Easier to maintain and update scoring logic
2. **Unified schema**: Simpler queries across time periods
3. **Resource efficiency**: One Docker image instead of three
4. **Flexibility**: Easy to add new time periods (e.g., "quarterly")
5. **Better analysis**: Can compare scores across different time periods in a single query

## Future Enhancements
The unified system is now ready for enhancements like:
- Period-specific scoring logic (e.g., 5-day momentum for weekly)
- Historical trend analysis across periods
- Composite scores that weight different time periods
- Dynamic period selection based on market conditions