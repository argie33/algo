# Manual AWS Deployment Checklist
**For users without AWS CLI installed**

Use this checklist to manually deploy via AWS Console.

---

## Phase 1: Deploy CloudFormation Stacks

### Stack 1: stocks-core (VPC and Networking)

1. Go to: https://console.aws.amazon.com/cloudformation
2. Click "Create Stack"
3. Choose "Upload a template file"
4. Upload: `template-core.yml`
5. Stack name: `stocks-core`
6. Click through defaults
7. Capabilities: Check ✓ "I acknowledge..."
8. Click "Create stack"
9. **Wait for completion** (status: CREATE_COMPLETE)

**Expected time:** 5-10 minutes

---

### Stack 2: stocks-app (RDS Database)

1. Go to: https://console.aws.amazon.com/cloudformation
2. Click "Create Stack"
3. Choose "Upload a template file"
4. Upload: `template-app-stocks.yml`
5. Stack name: `stocks-app`
6. Parameters:
   - RDSUsername: `stocks`
   - RDSPassword: `bed0elAn`
   - RDSPort: `5432`
7. Click through defaults
8. Capabilities: Check ✓ "I acknowledge..."
9. Click "Create stack"
10. **Wait for completion** (status: CREATE_COMPLETE)

**Expected time:** 15-20 minutes (database creation takes time)

---

### Stack 3: stocks-app-ecs-tasks (ECS Task Definitions)

1. Go to: https://console.aws.amazon.com/cloudformation
2. Click "Create Stack"
3. Choose "Upload a template file"
4. Upload: `template-app-ecs-tasks.yml`
5. Stack name: `stocks-app-ecs-tasks`
6. Parameters:
   - QuarterlyIncomeImageTag: `latest`
   - AnnualIncomeImageTag: `latest`
   - QuarterlyBalanceImageTag: `latest`
   - AnnualBalanceImageTag: `latest`
   - QuarterlyCashflowImageTag: `latest`
   - AnnualCashflowImageTag: `latest`
   - RDSUsername: `stocks`
   - RDSPassword: `bed0elAn`
7. Click through defaults
8. Capabilities: Check ✓ "I acknowledge..."
9. Click "Create stack"
10. **Wait for completion** (status: CREATE_COMPLETE)

**Expected time:** 5-10 minutes

**Total CloudFormation time:** 25-40 minutes

---

## Phase 2: Configure Security Groups

### Find RDS Security Group

1. Go to: https://console.aws.amazon.com/rds/home
2. Click "Databases"
3. Find: `stocks-prod-db`
4. Click it to open details
5. Scroll to "Connectivity & security"
6. Note the **Security group ID** (starts with `sg-`)
7. Example: `sg-0123456789abcdef0`

### Find ECS Security Group

1. Go to: https://console.aws.amazon.com/ec2/v2/home
2. Click "Security Groups"
3. Search for: `stocks-ecs-tasks`
4. Click it to open details
5. Note the **Security group ID** (starts with `sg-`)
6. Example: `sg-abcdef0123456789`

### Configure Inbound Rule

1. Go to: https://console.aws.amazon.com/ec2/v2/home
2. Click "Security Groups"
3. Click on **RDS security group** (from above)
4. Scroll to "Inbound Rules"
5. Click "Edit Inbound Rules"
6. Click "Add Rule"
7. Fill in:
   - Type: `PostgreSQL`
   - Protocol: `TCP`
   - Port: `5432`
   - Source: Type the **ECS security group ID** (sg-abc123...)
   - Description: `Allow ECS tasks to connect to RDS`
8. Click "Save Rules"

**Result:** ECS tasks can now connect to RDS on port 5432

---

## Phase 3: Verify Docker Images

### Check ECR for Latest Images

1. Go to: https://console.aws.amazon.com/ecr/repositories
2. For each of these repositories, check if latest images exist:
   - `loadquarterlyincomestatement`
   - `loadannualincomestatement`
   - `loadquarterlybalancesheet`
   - `loadannualbalancesheet`
   - `loadquarterlycashflow`
   - `loadannualcashflow`
3. If not found:
   - Go to: https://github.com/argie33/algo/actions
   - Wait for "Docker Build" workflow to complete
   - Images will automatically push to ECR

**Expected:** All 6 repositories have images tagged `latest` (or recent commit SHA)

---

## Phase 4: Test First Loader

### Start loadquarterlyincomestatement Task

1. Go to: https://console.aws.amazon.com/ecs/v2/clusters
2. Click cluster: `stock-analytics-cluster`
3. Click "Tasks" → "Run New Task"
4. Task Definition: `loadquarterlyincomestatement:latest`
5. Launch Type: `FARGATE`
6. VPC: Select VPC from `stocks-core` stack
7. Subnets: Select 2 subnets from `stocks-core` stack
8. Security Groups: Select the `stocks-ecs-tasks` security group
9. Public IP: `ENABLED`
10. Click "Create"
11. **Wait for task to start** (status: RUNNING)

### Monitor Execution

1. Click the task to view details
2. View logs at: CloudWatch → Logs → Log Groups → `/ecs/loadquarterlyincomestatement`
3. Expected output pattern:
   ```
   2026-04-29 14:00:00 - Starting loadquarterlyincomestatement (PARALLEL)
   2026-04-29 14:02:30 - Progress: 500/4969 (10.5/sec, ~420s remaining)
   2026-04-29 14:15:45 - [OK] Completed: 24950 rows inserted
   ```

**Expected time:** 12 minutes

### Verify Data Loaded

1. Go to: CloudFormation → `stocks-app` stack → Outputs
2. Find: `DBEndpoint` (e.g., `stocks-prod-db.xxxxxxxxxx.rds.amazonaws.com`)
3. Connect via psql or AWS RDS Query Editor:
   ```bash
   psql -h <endpoint> -U stocks -d stocks -c "SELECT COUNT(*) FROM quarterly_income_statement;"
   ```
4. Expected result: ~25,000 rows

---

## Phase 5: Run All 6 Loaders

Once first loader succeeds:

1. Go to: https://console.aws.amazon.com/ecs/v2/clusters
2. Click cluster: `stock-analytics-cluster`
3. Click "Tasks" → "Run New Task"
4. Repeat for each loader:
   - loadquarterlyincomestatement
   - loadannualincomestatement
   - loadquarterlybalancesheet
   - loadannualbalancesheet
   - loadquarterlycashflow
   - loadannualcashflow

5. Configuration for each:
   - Launch Type: `FARGATE`
   - VPC, Subnets, Security Groups: Same as above
   - Public IP: `ENABLED`

6. **Monitor all 6 in parallel:**
   - Go to: CloudWatch → Logs → `/ecs/`
   - Watch logs from all 6 loaders
   - Expected total time: ~12 minutes (all run in parallel)

---

## Troubleshooting

### If CloudFormation Stack Fails

1. Check error message in Stack Events
2. Common errors:
   - **InsufficientCapabilities:** Check ✓ "I acknowledge..." checkbox
   - **InvalidParameterValue:** Verify parameter values
   - **ServiceQuotaExceeded:** May need to request quota increase

### If RDS Connection Fails

1. Verify security group rule was added
2. Verify ECS security group ID is correct
3. Verify RDS is in the same VPC as ECS

### If ECS Task Fails to Start

1. Check task definition exists
2. Check Docker image exists in ECR
3. Check VPC/subnet/security group configuration
4. Check task logs in CloudWatch

### If No Data Appears

1. Check CloudWatch logs for errors
2. Verify RDS is accessible
3. Verify database credentials are correct
4. Check that task completed (not stopped/failed)

---

## Quick Reference: Key Resources

| Resource | URL |
|----------|-----|
| CloudFormation | https://console.aws.amazon.com/cloudformation |
| ECS | https://console.aws.amazon.com/ecs/v2/clusters |
| RDS | https://console.aws.amazon.com/rds/home |
| ECR | https://console.aws.amazon.com/ecr/repositories |
| CloudWatch Logs | https://console.aws.amazon.com/logs/home |
| EC2 Security Groups | https://console.aws.amazon.com/ec2/v2/home#SecurityGroups |
| GitHub Actions | https://github.com/argie33/algo/actions |

---

## Success Criteria

✓ All 3 CloudFormation stacks deployed (CREATE_COMPLETE)
✓ Security group rule allows ECS → RDS on port 5432
✓ Docker images exist in ECR for all 6 Batch 5 loaders
✓ First loader task completes in ~12 minutes
✓ ~25,000 rows appear in quarterly_income_statement table
✓ All 6 loaders run successfully in parallel
✓ Total time for all 6: ~12 minutes (vs 285 minutes baseline)

---

## Next Steps

1. Complete checklist items above
2. Monitor: https://console.aws.amazon.com/logs/home → `/ecs/`
3. Once all 6 complete successfully, Batch 5 is ready for production
4. Then apply same pattern to remaining 46 loaders

---

**Expected Total Time: 45-60 minutes from start to finish**
