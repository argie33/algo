# AWS VPC Hardening Plan for Production Go-Live

## Current State (Deferred for "Dev Cost")
- RDS: Private subnets, but accepts from 0.0.0.0/0 internally
- Lambdas (webapp, algo): NOT in VPC → can't access RDS securely
- ECS Loaders: Public subnets with public IPs
- No NAT Gateway → private resources can't reach Alpaca/yfinance APIs

## Security Requirements for Production

### Tier 1: CRITICAL (Go-Live Blockers)
**Must complete before live trading with real money**

- [ ] **Add NAT Gateway** to public subnet
  - Allows private instances to call Alpaca/yfinance APIs
  - Cost: ~$32/month + data transfer
  - Update route tables for private subnets
  
- [ ] **Move Lambdas into VPC**
  - webapp-lambda: Add NetworkConfig with subnet + security group
  - algo-orchestrator: Same
  - Create Lambda security group (ingress: none needed, egress: to RDS SG)
  - Update RDS security group to accept from Lambda SG
  
- [ ] **Lock down RDS Security Group**
  - Remove any wide-open rules
  - Only allow from: ECS tasks SG + Lambda SG + Bastion SG
  - Restrict to port 5432 only
  - Test connection from Bastion via SSM Session Manager

### Tier 2: RECOMMENDED (Before scaling)
- [ ] **Move ECS loaders to private subnets**
  - Use NAT Gateway for outbound API calls
  - Cost increase: minimal (same Fargate costs, but NAT data transfer)
  
- [ ] **Add RDS read replicas** (optional)
  - For high-traffic reporting dashboards
  - Cost: ~2x RDS instance cost
  - Not needed for initial deployment
  
- [ ] **Add WAF to CloudFront** (optional)
  - Protect API endpoints from abuse
  - Cost: ~3 USD/month

### Tier 3: LATER (Post-launch)
- [ ] Enable RDS Multi-AZ for HA
- [ ] VPC Flow Logs for security monitoring
- [ ] AWS GuardDuty for threat detection

## Implementation Steps

### Step 1: Add NAT Gateway (2 hours)
```bash
# Update template-core.yml:
# 1. Create NAT Gateway in public subnet
# 2. Create Elastic IP for NAT
# 3. Update route tables for private subnets to use NAT (0.0.0.0/0 → NAT)
# 4. Redeploy via: gh workflow run deploy-core.yml
```

### Step 2: Move Lambdas into VPC (3 hours)
```bash
# Update template-webapp.yml and template-algo.yml:
# 1. Add VpcConfig to Lambda function
# 2. Reference private subnets from StocksCore
# 3. Create Lambda security group (egress to RDS only)
# 4. Update IAM role for Lambda to invoke from VPC endpoints (if needed)
# 5. Redeploy both
```

### Step 3: Lock Down RDS (1 hour)
```bash
# Update template-data-infrastructure.yml:
# 1. Remove 0.0.0.0/0 ingress rule from RDS SG
# 2. Add ingress from:
#    - EcsTasksSecurityGroup (port 5432)
#    - LambdaSecurityGroup (port 5432)
#    - BastionSecurityGroup (port 5432)
# 3. Redeploy via: gh workflow run deploy-data-infrastructure.yml
# 4. Test connection from Bastion
```

### Step 4: Test Access (1 hour)
```bash
# 1. From Bastion (via SSM Session Manager):
#    psql -h RDS_ENDPOINT -U stocks -d stocks
#
# 2. From Lambda (CloudWatch logs):
#    Check algo orchestrator / webapp Lambda logs
#    Verify successful DB connections
#
# 3. From ECS tasks:
#    Check loader logs for successful inserts
```

## Cost Impact
| Change | Cost/Month | Notes |
|--------|-----------|-------|
| NAT Gateway | +$32 | Required for private resources |
| Data transfer | +$0-5 | Minimal for API calls |
| Lambda in VPC | +$0 | No additional cost |
| **Total Additional** | **~$35** | Worth it for security |

## Timeline
- **Option 1 (Rush):** All steps in 1 day (10 hours total work)
- **Option 2 (Safe):** Spread over 1 week, test thoroughly between steps
- **Option 3 (Current):** Keep deferred for "dev cost", mitigate with IP allowlisting

## Rollback Plan
If issues arise after deploying:
1. Lambdas fail to connect → Revert VpcConfig in template, redeploy
2. RDS access denied → Check security group rules, add missing ingress
3. No internet access → Check NAT routing, ensure NAT Gateway exists
4. Keep previous templates in git for quick rollback

## Files to Modify
- `template-core.yml` — Add NAT Gateway
- `template-webapp.yml` — Add Lambda VPC config
- `template-algo.yml` — Add Lambda VPC config  
- `template-data-infrastructure.yml` — Lock down RDS SG

## Testing Checklist
- [ ] Bastion can SSH to RDS (via SSM)
- [ ] Lambdas can connect to RDS (check CloudWatch logs)
- [ ] ECS loaders run successfully (check logs for no connection errors)
- [ ] Data arrives in RDS from all sources
- [ ] Dashboard API works end-to-end
- [ ] Algo orchestrator runs without DB errors

---

**Current Status:** Deferred for cost/complexity, but production-ready when needed.  
**Recommendation:** Complete Tier 1 before first live trading with real money.
