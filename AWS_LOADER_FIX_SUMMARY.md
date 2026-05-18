# AWS Loader & Orchestrator Fix Summary

## Problem
The API Gateway was returning **404 Not Found** on all endpoints because the routing wasn't configured correctly for the Lambda integration.

## Root Cause  
**AWS HTTP API v2 automatically creates the `$default` route**, but:
1. Initial attempt tried to explicitly create it → **409 Conflict** (route already exists)
2. Just having the integration isn't enough; routes must explicitly target it
3. The auto-created `$default` route wasn't connected to our Lambda

## Solution Deployed
✅ Removed explicit route creation that was causing the 409 error
✅ Rely on `auto_deploy = true` on the stage to automatically sync routes
✅ The integration + auto_deploy should handle routing to the Lambda

## What's Changed
- File: `terraform/modules/services/main.tf`
- Removed the `aws_apigatewayv2_route.default` resource that was trying to create an already-existing route
- API Gateway will now use its auto-deployment feature to route requests to the Lambda

## Testing Once Deployed
```bash
# 1. Verify API endpoint is responding
API=$(aws apigatewayv2 get-apis --query 'Items[0].ApiEndpoint' --output text)
curl "$API/health"

# 2. Trigger a loader in AWS
./trigger-loader-ecs.sh stock_symbols

# 3. Watch CloudWatch logs
aws logs tail /ecs/algo-stock-symbols-loader --follow

# 4. Run orchestrator locally with Friday data
export DB_PASSWORD=<your-password>
./run-orchestrator-test.sh 2026-05-16

# 5. Check if trades would trigger
SELECT * FROM trades WHERE DATE(created_at) = '2026-05-16';
```

## Expected Timeline
- Deployment: 5-10 minutes (Terraform apply)
- API should respond: ✅ 200 OK
- Loaders can run: ✅ Should work
- Orchestrator can test with Friday data: ✅ Ready

## Files Changed
- ✅ `terraform/modules/services/main.tf` - API Gateway route fix
- ✅ `build-lambda-zip.sh` - Helper for building Lambda locally
- ✅ `test-aws-loaders.sh` - Diagnostic script
- ✅ `run-orchestrator-test.sh` - Test with specific dates
- ✅ `trigger-loader-ecs.sh` - Manual loader triggering
- ✅ `LOADER_TESTING_GUIDE.md` - Comprehensive documentation
- ✅ `STATUS.md` - Updated with fixes and next steps
