# Dashboard Setup: Local Development vs AWS Production

## Quick Start

### LOCAL DEVELOPMENT MODE
Best for testing with local database:

```bash
# Terminal 1: Start development API server
python3 dev_api_server.py

# Terminal 2: Start dashboard (connects to http://localhost:8000)
python3 -m dashboard
```

### AWS PRODUCTION MODE
Connect dashboard to AWS Lambda API Gateway:

```bash
# Set AWS API Gateway endpoint
export DASHBOARD_API_URL="https://<api-id>.execute-api.us-east-1.amazonaws.com/dev"

# Start dashboard (connects to AWS)
python3 -m dashboard
```

## How to Find AWS API Gateway Endpoint

```bash
# Option 1: From Terraform output
cd terraform
terraform output api_gateway_endpoint

# Option 2: From AWS CLI
aws apigateway get-rest-apis \
  --query 'items[?name==`algo-api-dev`].{id:id,name:name}' \
  --region us-east-1
  
# Then: https://<api-id>.execute-api.us-east-1.amazonaws.com/dev
```

## Environment Variables

| Variable | Local Development | AWS Production | Purpose |
|----------|-------------------|-----------------|---------|
| `DASHBOARD_API_URL` | Not needed (defaults to localhost:8000) | Required | Where dashboard reaches API |
| `FORCE_AWS` | Not set | `true` (in Lambda) | Use AWS Secrets Manager for credentials |
| `DB_HOST` | `localhost` | From AWS Secrets Manager | Database host |
| `DB_SECRET_ARN` | Not set | Set in Lambda env | AWS Secrets Manager ARN for credentials |

## How Dashboard Connects to Data

### Local Development Flow
```
Dashboard (localhost:8000) 
  → dev_api_server.py (localhost:8000/api/...)
    → PostgreSQL (localhost:5432)
      → Real data from local database
```

### AWS Production Flow
```
Dashboard 
  → AWS API Gateway (https://<api-id>.execute-api.us-east-1.amazonaws.com/dev)
    → AWS Lambda (algo-api-dev function)
      → AWS RDS (via Secrets Manager credentials)
        → Real data from AWS production database
```

## Troubleshooting

**Dashboard shows "Connecting to database..." but never loads:**
- Local mode: Check dev_api_server.py is running on port 8000
- AWS mode: Check DASHBOARD_API_URL is set correctly
  ```bash
  echo $DASHBOARD_API_URL
  curl -I $DASHBOARD_API_URL/api/algo/scores
  ```

**API endpoint returns 5xx error:**
- Check Lambda CloudWatch logs
- Verify database credentials in AWS Secrets Manager
- Verify Lambda has VPC/RDS access

**Growth scores not showing:**
- Check database has stock_scores table populated
- Verify orchestrator Phase 7 has run recently
- Check growth_metrics loader ran (Phase 6 prerequisite)

## Deployment Checklist

For AWS production to work:

✅ API Lambda deployed (`deploy-api-lambda.yml`)
✅ Orchestrator Lambda deployed (`deploy-orchestrator-lambda.yml`)  
✅ Terraform outputs API Gateway endpoint
✅ GitHub Actions workflow exports endpoint
✅ Dashboard DASHBOARD_API_URL environment variable configured
✅ Lambda environment variables set (DB_SECRET_ARN, FORCE_AWS)

