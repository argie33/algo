# RDS Proxy Setup Guide

**Status:** Ready to Enable  
**Module:** `terraform/modules/rds-proxy/`  
**Benefit:** Solves Lambda connection pool exhaustion (fixes timeouts under load)

---

## Why RDS Proxy?

Lambda functions are ephemeral - each invocation creates a new database connection. With 100+ concurrent Lambda invocations, you'd hit RDS max_connections (20 by default) instantly, causing connection failures and 504 errors.

**RDS Proxy solves this by:**
- Multiplexing 1000s of Lambda connections through a single proxy
- Connection pooling + statement caching
- Automatic connection recycling
- Transparent to application code (same connection string format)

---

## Installation (One-time Setup)

### Step 1: Add to terraform/main.tf

```hcl
# After the database module definition, add:
module "rds_proxy" {
  source = "./modules/rds-proxy"

  project_name               = var.project_name
  vpc_id                     = module.vpc.vpc_id
  vpc_subnet_ids             = module.vpc.private_subnet_ids
  rds_instance_id            = module.database.rds_instance_id
  rds_security_group_id      = module.vpc.rds_security_group_id
  lambda_security_group_id   = module.compute.lambda_security_group_id
  secrets_manager_secret_arn = module.database.secrets_manager_secret_arn
  
  max_connections  = 100
  log_retention_days = 7
  sns_topic_arn    = module.services.sns_alerts_topic_arn
  
  common_tags = local.common_tags
  
  depends_on = [module.database, module.vpc]
}
```

### Step 2: Update Lambda Environment Variables

In `terraform/modules/compute/main.tf`, update Lambda functions to use proxy endpoint:

```hcl
# BEFORE:
environment {
  variables = {
    DB_HOST = module.database.rds_endpoint
    ...
  }
}

# AFTER:
environment {
  variables = {
    DB_HOST = module.rds_proxy.proxy_endpoint  # Use proxy instead
    ...
  }
}
```

### Step 3: Deploy

```bash
cd terraform/
terraform plan
terraform apply
```

**Expected output:**
- Creates: `algo-proxy` RDS Proxy
- Creates: Security group for proxy
- Creates: CloudWatch logs + alarms
- Updates: Lambda environment to use proxy endpoint

---

## Verification

### Test Proxy Connectivity

```bash
# 1. Get proxy endpoint from Terraform output
terraform output rds_proxy_endpoint

# 2. Test connection from local (if on VPC)
psql -h <proxy-endpoint> -U stocks -d stocks -c "SELECT 1"

# 3. Check CloudWatch logs
aws logs tail /aws/rds-proxy/algo --follow
```

### Monitor Connections

```bash
# CloudWatch Metrics (RDS console → Proxy tab)
# Should show:
# - ClientConnections: 1-10 (not 100+)
# - DatabaseConnections: 5-15 (pooled, not 100+)
# - ClientConnectionsClosed: gradually increasing (normal recycling)
```

---

## Configuration

### Connection Pool Tuning

If you experience timeouts after enabling proxy:

```hcl
# In main.tf module call:
connection_borrow_timeout = 120  # seconds to wait for available connection
max_connections           = 100  # increase if needed
```

### Monitoring the Proxy

Check CloudWatch dashboard:

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS/Proxy \
  --metric-name ClientConnections \
  --dimensions Name=DBProxyName,Value=algo-proxy \
  --start-time 2026-05-17T00:00:00Z \
  --end-time 2026-05-17T23:59:59Z \
  --period 300 \
  --statistics Average,Maximum
```

---

## Disabling RDS Proxy (If Needed)

```bash
# Remove from terraform/main.tf, then:
terraform plan  # Verify it shows proxy will be destroyed
terraform apply
```

---

## Production Checklist

- [ ] RDS Proxy module added to `terraform/`
- [ ] Lambda environment updated to use proxy endpoint
- [ ] Terraform plan shows RDS Proxy creation
- [ ] Terraform apply succeeds
- [ ] Proxy appears in AWS Console (RDS → Proxies)
- [ ] Lambda can connect (check logs for errors)
- [ ] CloudWatch alarms created for proxy health
- [ ] Load test: 100+ concurrent API requests complete without timeout
- [ ] Monitor for 1 week, watch for connection pool exhaustion patterns

---

## Troubleshooting

### "Unable to connect through proxy"
**Cause:** Security group rules not configured  
**Fix:** Verify inbound rule on proxy SG allows Lambda SG

### "Connection pool exhausted"
**Cause:** Legitimate high load or connection leak  
**Fix:** Increase `max_connections` in module config

### "Proxy started failing after push"
**Cause:** Lambda environment variables not updated  
**Fix:** Confirm `DB_HOST` env var points to proxy endpoint, not RDS

---

## Performance Impact

**Before Proxy:** Cold start with DB connection: 1-2 seconds  
**After Proxy:** Cold start with pooled connection: 0.5-1 second  
**Throughput:** 2-3x more requests/second before hitting connection limits
