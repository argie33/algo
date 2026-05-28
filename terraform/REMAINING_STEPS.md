# Remaining Steps to Reach Goal: "Auth Fully Stable & Working"

## Step 1: Get Valid AWS Credentials
**Current Status**: Invalid/expired credentials in ~/.aws/credentials
**Required**: Valid AWS IAM key or OIDC session for deployer role

**Actions**:
- [ ] Obtain valid AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY
- [ ] Or: Configure AWS SSO and login
- [ ] Or: Use GitHub OIDC token (if available in environment)
- [ ] Verify credentials work: `aws sts get-caller-identity`

---

## Step 2: Initialize Terraform with Credentials
**Prerequisite**: Step 1 complete
**Expected**: Terraform connects to AWS backend (S3 bucket)

**Actions**:
- [ ] Set AWS credentials in environment or ~/.aws/credentials
- [ ] `cd terraform`
- [ ] `terraform init -backend-config=backend-config.tfvars`
- [ ] Verify: `terraform state list` (should show existing resources)

---

## Step 3: Validate Infrastructure Configuration
**Prerequisite**: Step 2 complete
**Expected**: Terraform validates without errors

**Actions**:
- [ ] `terraform plan -target=module.cognito` (dry-run Cognito deploy)
- [ ] Review plan output for resources to create
- [ ] No errors or warnings

---

## Step 4: Deploy Cognito Infrastructure
**Prerequisite**: Step 3 complete
**Expected**: User Pool + Client created in AWS

**Actions**:
- [ ] `terraform apply -target=module.cognito -auto-approve`
- [ ] Wait 2-3 minutes for resources
- [ ] Verify: `aws cognito-idp list-user-pools --max-results 1`
- [ ] Capture User Pool ID and Client ID

---

## Step 5: Deploy Complete Infrastructure
**Prerequisite**: Step 4 complete
**Expected**: All infrastructure deployed (Cognito, Lambda, RDS, API Gateway, etc)

**Actions**:
- [ ] `terraform apply -auto-approve`
- [ ] Wait 10-15 minutes for full deployment
- [ ] Watch logs for db-init Lambda execution
- [ ] Verify db-init succeeded: `aws logs tail /aws/lambda/algo-db-init-dev --follow`

---

## Step 6: Verify Infrastructure Deployment
**Prerequisite**: Step 5 complete
**Expected**: All resources exist and are accessible

**Actions**:
- [ ] Verify Cognito: `aws cognito-idp describe-user-pool --user-pool-id $POOL_ID`
- [ ] Verify Lambda: `aws lambda get-function --function-name algo-api-dev`
- [ ] Verify RDS: `aws rds describe-db-instances --db-instance-identifier algo-db`
- [ ] Verify API Gateway: `aws apigatewayv2 get-apis`
- [ ] All commands should return valid output (not 404/NotFound)

---

## Step 7: Verify Lambda Environment Variables
**Prerequisite**: Step 6 complete
**Expected**: Lambda has COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID set

**Actions**:
- [ ] `aws lambda get-function-configuration --function-name algo-api-dev`
- [ ] Look for `COGNITO_USER_POOL_ID` in Environment.Variables
- [ ] Look for `COGNITO_CLIENT_ID` in Environment.Variables
- [ ] Both should be non-empty values

---

## Step 8: Verify Database Initialization
**Prerequisite**: Step 5 complete (db-init Lambda ran)
**Expected**: All tables created in RDS

**Actions**:
- [ ] Get RDS endpoint: `terraform output rds_endpoint`
- [ ] Connect to database: `psql -h $ENDPOINT -U stocks -d stocks`
- [ ] Verify tables exist: `\dt`
- [ ] Should see: `algo_notifications`, `signal_quality_scores`, `buy_sell_daily`, etc.

---

## Step 9: Test Auth Code Path
**Prerequisite**: Step 7 complete (Lambda has Cognito env vars)
**Expected**: Lambda validates tokens correctly

**Actions**:
- [ ] Invoke Lambda with test request:
  ```bash
  aws lambda invoke --function-name algo-api-dev \
    --payload '{"path":"/api/health","rawPath":"/api/health","requestContext":{"http":{"method":"GET"}}}' \
    /tmp/test.json
  ```
- [ ] Check response: `cat /tmp/test.json`
- [ ] Should return `{"status":"healthy"}` (not 503 or error)

---

## Step 10: Test Cognito Authentication Flow
**Prerequisite**: Step 4 complete (Cognito deployed)
**Expected**: Can authenticate user and get JWT token

**Actions**:
- [ ] Create test user: 
  ```bash
  aws cognito-idp admin-create-user --user-pool-id $POOL_ID \
    --username testuser --temporary-password TempPass123!
  ```
- [ ] Set permanent password:
  ```bash
  aws cognito-idp admin-set-user-password --user-pool-id $POOL_ID \
    --username testuser --password TestPass123! --permanent
  ```
- [ ] Authenticate and get token (requires OAuth2 client setup)
- [ ] Verify JWT token is valid

---

## Step 11: Test Protected API Endpoint
**Prerequisite**: Steps 9-10 complete
**Expected**: API returns data for authenticated requests, 401 for unauthenticated

**Actions**:
- [ ] Test without auth:
  ```bash
  curl https://$API_DOMAIN/api/algo/notifications
  # Should return 401 or 403 (Unauthorized)
  ```
- [ ] Test with valid JWT:
  ```bash
  curl -H "Authorization: Bearer $JWT_TOKEN" \
    https://$API_DOMAIN/api/algo/notifications
  # Should return 200 with data
  ```

---

## Step 12: Verify Frontend Can Authenticate
**Prerequisite**: Steps 4, 9 complete
**Expected**: Frontend login page works, can obtain tokens

**Actions**:
- [ ] Frontend app loads (no 403 or CORS errors)
- [ ] Can navigate to login page
- [ ] Can enter Cognito credentials
- [ ] Receives JWT token after login
- [ ] Token stored in localStorage/sessionStorage
- [ ] Can call API with token (returns 200, not 401/503)

---

## Success Criteria: Goal Reached

✅ Goal is reached when:
- [ ] Cognito User Pool exists in AWS
- [ ] API Lambda deployed with correct env vars
- [ ] Database initialized with schema
- [ ] `/api/health` returns 200 (no auth required)
- [ ] `/api/algo/*` returns 200 with valid JWT
- [ ] `/api/algo/*` returns 401 without JWT
- [ ] Frontend can login with Cognito
- [ ] No 503, 404, or auth errors in logs
- [ ] Auth flow is stable and repeatable

---

## Timeline
- Step 1: 5-10 min (get credentials)
- Step 2: 2 min (terraform init)
- Step 3: 1 min (terraform plan)
- Step 4: 3-5 min (Cognito deploy)
- Step 5: 10-15 min (full deploy + db-init)
- Steps 6-12: 10-15 min (verification + testing)

**Total: 45-60 minutes from now to fully working auth system**

