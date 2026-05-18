# Fixing yfinance Data Loading in AWS ECS

**Status:** Data not loading in ECS (network issue)  
**Root Cause:** yfinance API calls fail in VPC (likely network egress blocked)  
**Solutions:** 3 approaches in order of preference

---

## Approach 1: VPC Endpoint for External APIs (RECOMMENDED)

This is the best long-term solution. Create a VPC endpoint for HTTPS so ECS tasks can reach external APIs without NAT gateway.

### Why It Works

- Direct, secure access to yfinance API (query2.finance.yahoo.com)
- No NAT gateway needed (saves ~$32/month)
- Fast (no network hops)
- Secure (stays within AWS network)

### Implementation

```bash
# 1. Create S3 gateway endpoint (required for VPC endpoints to work)
aws ec2 create-vpc-endpoint \
  --vpc-id vpc-xxxxxxxxxxxxxx \
  --service-name com.amazonaws.us-east-1.s3 \
  --route-table-ids rtb-xxxxxxxxxxxxxx rtb-yyyyyyyyyyyy

# 2. Create HTTPS VPC endpoint (for external API access)
aws ec2 create-vpc-endpoint \
  --vpc-id vpc-xxxxxxxxxxxxxx \
  --vpc-endpoint-type Interface \
  --service-name com.amazonaws.us-east-1.ec2messages \
  --subnet-ids subnet-xxxxxx subnet-yyyyyy \
  --security-group-ids sg-xxxxxxxxxxxxxx

# 3. Verify endpoint
aws ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=vpc-xxxxxxxxxxxxxx"
```

### Terraform Code

Add to `terraform/modules/vpc/main.tf`:

```hcl
# S3 Gateway Endpoint (for general VPC access)
resource "aws_vpc_endpoint" "s3" {
  vpc_id       = aws_vpc.main.id
  service_name = "com.amazonaws.${var.aws_region}.s3"
  route_table_ids = [
    aws_route_table.private.id,
  ]
  tags = {
    Name = "${var.project_name}-s3-endpoint"
  }
}

# Interface Endpoint for EC2 Systems Manager (needed for ECS tasks to reach external APIs)
resource "aws_vpc_endpoint" "ec2messages" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.aws_region}.ec2messages"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.ecs_tasks.id]
  private_dns_enabled = true
  tags = {
    Name = "${var.project_name}-ec2messages-endpoint"
  }
}
```

Then: `terraform apply`

---

## Approach 2: NAT Gateway (if VPC endpoint doesn't work)

If VPC endpoint doesn't resolve yfinance API, set up a NAT gateway for outbound internet access.

### Why It Works

- Provides full internet egress for ECS tasks
- ECS tasks can reach any external API
- Slower than VPC endpoint (more hops)
- More expensive (~$32/month + data transfer)

### Implementation

```bash
# 1. Create Elastic IP for NAT gateway
aws ec2 allocate-address --domain vpc

# Save the Allocation ID (alloc-xxxxxxxxx)

# 2. Create NAT Gateway in public subnet
aws ec2 create-nat-gateway \
  --subnet-id subnet-public-xxxxx \
  --allocation-id alloc-xxxxxxxxx

# 3. Add route to private route table
aws ec2 create-route \
  --route-table-id rtb-private-xxxxx \
  --destination-cidr-block 0.0.0.0/0 \
  --nat-gateway-id nat-xxxxxxxxx

# 4. Verify route
aws ec2 describe-route-tables --route-table-ids rtb-private-xxxxx
```

### Terraform Code

```hcl
# Elastic IP for NAT Gateway
resource "aws_eip" "nat" {
  domain = "vpc"
  tags = {
    Name = "${var.project_name}-nat-eip"
  }
}

# NAT Gateway
resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
  tags = {
    Name = "${var.project_name}-nat-gateway"
  }
}

# Add route for private subnets to egress through NAT
resource "aws_route" "private_egress" {
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.main.id
}
```

---

## Approach 3: Switch Data Source (if network fixes don't work)

If yfinance still fails, use AWS-native alternatives.

### Option A: AWS Glue for data transformation

```python
# In loaders/loadpricedaily.py, add fallback:
def fetch_incremental(self, symbol: str, since: Optional[date]):
    # Try yfinance first
    rows = self._try_fetch_yfinance(symbol, since)
    if rows:
        return rows
    
    # Fallback to Alpaca API (configured in Lambda env)
    logger.info(f"[{symbol}] yfinance failed, trying Alpaca fallback")
    rows = self._try_fetch_alpaca(symbol, since)
    return rows
```

### Option B: Use Alpaca for all price data

Alpaca API is built for AWS environments and works in VPC:

```python
from utils.alpaca_client import get_alpaca_client

def _try_fetch_alpaca(self, symbol: str, start: date, end: date):
    """Fetch OHLCV from Alpaca (works in VPC without NAT)."""
    try:
        client = get_alpaca_client()
        bars = client.get_crypto_bars(symbol, '1Day', start=start, end=end)
        return [{
            'symbol': symbol,
            'date': bar.timestamp.date(),
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
            'volume': bar.volume,
        } for bar in bars]
    except Exception as e:
        logger.warning(f"[{symbol}] Alpaca fetch failed: {e}")
        return None
```

---

## Testing the Fix

After implementing one of the above solutions:

### Test 1: From ECS Task

```bash
# SSH into ECS task (via Systems Manager Session Manager)
# Or run an ad-hoc task with bash entry point

# Inside ECS task container:
curl -v https://query2.finance.yahoo.com/v10/finance/quoteSummary/AAPL

# Expected: HTTP 200 with JSON response
# If fails: "Network is unreachable" → need VPC endpoint or NAT
```

### Test 2: Run Data Loader

```bash
# Trigger loader in ECS
python3 loaders/loadpricedaily.py --symbols AAPL,MSFT --parallelism 4

# Watch logs
aws logs tail /ecs/algo-data-loaders --follow

# Expected:
# [AAPL] Fetched 250 rows from 2023-01-01 to 2026-05-18
# [MSFT] Fetched 250 rows from 2023-01-01 to 2026-05-18
# ✅ Inserted 500 rows, 0 duplicates, 0 errors
```

### Test 3: Verify Data in Database

```bash
# From local machine (with port forwarding)
psql -h localhost -U stocks -d stocks

# Inside psql:
SELECT COUNT(*) FROM price_daily WHERE date > NOW() - INTERVAL 1 DAY;

# Expected: > 10,000 (more than symbol count if recent data loaded)
```

---

## Monitoring After Fix

### CloudWatch Metrics

```bash
# Check loader success rate
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ServiceName,Value=algo-data-loaders \
  --start-time 2026-05-18T00:00:00Z \
  --end-time 2026-05-19T00:00:00Z \
  --period 3600 \
  --statistics Average
```

### Log Monitoring

```bash
# Watch for errors
aws logs filter-log-events \
  --log-group-name /ecs/algo-data-loaders \
  --filter-pattern "ERROR\|FAILED\|exception"

# Expected: No errors (or only rate-limit warnings)
```

---

## Troubleshooting

### If VPC endpoint doesn't work

```bash
# 1. Verify endpoint is created
aws ec2 describe-vpc-endpoints --filter "Name=vpc-id,Values=vpc-xxxxx"

# 2. Check DNS resolution
nslookup query2.finance.yahoo.com
# Should return IP address, not "host not found"

# 3. Test connectivity
curl -v https://query2.finance.yahoo.com/v10/finance/quoteSummary/AAPL --max-time 5

# 4. If still fails, check security group
# - Verify egress rule allows port 443 (HTTPS)
# - Verify source is ECS task security group
```

### If NAT gateway doesn't work

```bash
# 1. Verify NAT gateway is available
aws ec2 describe-nat-gateways --filter "Name=state,Values=available"

# 2. Check route table
aws ec2 describe-route-tables --filter "Name=vpc-id,Values=vpc-xxxxx" | jq '.RouteTables[].Routes'
# Should show: Destination 0.0.0.0/0 → NatGatewayId nat-xxxxx

# 3. Check ECS task route
aws ec2 describe-route-tables --filter "Name=route.nat-gateway-id,Values=nat-xxxxx"
```

---

## Cost Analysis

| Approach | Monthly Cost | Setup Time | Reliability |
|----------|------------|-----------|-------------|
| VPC Endpoint | $7-10 | 15 min | 99.99% |
| NAT Gateway | $32 | 20 min | 99.99% |
| Alpaca Fallback | Included | 30 min | 99.95% (Alpaca) |

**Recommendation:** Use VPC Endpoint (cheaper + faster)

---

## Implementation Timeline

1. **Today (5 min):** Deploy VPC endpoint via Terraform
2. **Next run (2 min):** Test with small symbol batch
3. **Monitor (ongoing):** Check logs for successful loads

If yfinance still fails after VPC endpoint, add Alpaca fallback code.

---

## References

- [AWS VPC Endpoints docs](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints.html)
- [yfinance on AWS](https://github.com/ranaroussi/yfinance/issues/1430)
- [Alpaca Data API](https://alpaca.markets/docs)
