# Redis Setup for Price Cache - Complete Guide

## Overview

Redis is required to share the price cache across ECS tasks. Without Redis, each ECS task maintains its own local cache, which is useless when tasks are created fresh for each orchestrator run.

**Impact**: Redis eliminates ~90% of yfinance API calls, reducing stock_prices_daily execution from 7.5+ hours to ~5-10 minutes.

---

## Local Development Setup (docker-compose)

### Step 1: Start Redis Locally ✅ DONE
Redis service added to `docker-compose.yml`:
```yaml
redis:
  image: redis:7-alpine
  container_name: algo-redis-dev
  ports:
    - "6379:6379"
  command: redis-server --appendonly yes
  volumes:
    - redis_data:/data
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 10s
    timeout: 5s
    retries: 5
  networks:
    - algo-network
```

### Step 2: Verify Redis is Working

```bash
# Start services
docker-compose up -d

# Check Redis status
docker-compose logs redis

# Test Redis connectivity
redis-cli -h localhost ping
# Expected: PONG

# Check if price cache is working
python3 -c "
from utils.cache.price_cache import PriceCache
cache = PriceCache.from_env()
print(f'Cache backend: {\"Redis\" if cache.redis else \"Local memory\"}')
"
```

### Step 3: Run Loaders with Redis Cache

```bash
# Automatically uses Redis at localhost:6379/0 (set in run_loader.py)
python3 scripts/run_loader.py prices --symbols AAPL,MSFT

# Or explicitly:
REDIS_URL=redis://localhost:6379/0 python3 scripts/run_loader.py prices

# Check cache hits in logs:
# [PRICE_CACHE] Redis hit for AAPL/1d
# [PRICE_CACHE] Local hit for MSFT/1d (age: XXXs, ttl: 82800s)
```

---

## Production Setup (AWS ElastiCache)

### Step 1: Provision Redis in AWS

Add to `terraform/modules/services/price-cache-redis.tf`:

```hcl
# ElastiCache for Redis - shared cache across all ECS tasks
resource "aws_elasticache_cluster" "price_cache" {
  cluster_id           = "${local.project_prefix}-price-cache"
  engine               = "redis"
  node_type            = "cache.t3.micro"  # Small instance for price cache only
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  engine_version       = "7.0"
  port                 = 6379
  
  # Security: Only accessible from VPC (not public)
  security_group_ids   = [aws_security_group.price_cache.id]
  
  # Automatic failover for multi-node setup (if scaling later)
  automatic_failover_enabled = false
  
  # Enable encryption at rest
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token_enabled         = false  # TODO: Add auth token for security
  
  # Snapshots for persistence
  snapshot_retention_limit = 5
  snapshot_window          = "03:00-05:00"
  
  # Multi-AZ for high availability (optional, for production)
  # automatic_failover_enabled = true
  
  tags = {
    Name        = "${local.project_prefix}-price-cache"
    Purpose     = "Price data cache to reduce yfinance API calls"
    Component   = "stock_prices_daily"
  }
}

# Security group for Redis
resource "aws_security_group" "price_cache" {
  name        = "${local.project_prefix}-price-cache-sg"
  description = "Security group for Redis price cache"
  vpc_id      = aws_vpc.main.id

  # Inbound: Allow from ECS tasks
  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks.id]
  }

  # Outbound: Allow all
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.project_prefix}-price-cache-sg"
  }
}

# Output the Redis endpoint
output "price_cache_redis_endpoint" {
  value       = aws_elasticache_cluster.price_cache.cache_nodes[0].address
  description = "Redis endpoint for price cache"
}
```

### Step 2: Set Environment Variable in ECS Tasks

Update ECS task definition to include REDIS_URL:

```hcl
# In terraform/modules/services/ecs-tasks.tf or similar

resource "aws_ecs_task_definition" "loaders" {
  # ... existing config ...

  container_definitions = jsonencode([
    {
      name  = "loader"
      image = "algo-loader:latest"
      
      environment = [
        # ... existing vars ...
        {
          name  = "REDIS_URL"
          value = "redis://${aws_elasticache_cluster.price_cache.cache_nodes[0].address}:6379/0"
        },
      ]
    }
  ])
}
```

### Step 3: Deploy and Verify

```bash
# Apply Terraform
cd terraform
terraform plan -out=plan.tfplan
terraform apply plan.tfplan

# Get Redis endpoint
REDIS_ENDPOINT=$(terraform output -raw price_cache_redis_endpoint)
echo "Redis endpoint: $REDIS_ENDPOINT"

# Verify connectivity from ECS
aws ecs execute-command \
  --cluster algo-prod \
  --task <task-id> \
  --container loader \
  --interactive \
  --command "/bin/sh -c 'redis-cli -h $REDIS_ENDPOINT ping'"
# Expected: PONG
```

---

## Cost Estimate

| Tier | Monthly Cost | Use Case |
|------|------|----------|
| **cache.t3.micro** | ~$15 | Development/testing, price cache only |
| **cache.t3.small** | ~$25 | Production, with moderate load |
| **cache.t3.medium** | ~$50 | Production, high load, multi-zone failover |
| **cache.r6g.large** | ~$400+ | Large deployments, other use cases |

**Recommendation**: Start with `cache.t3.micro` for price cache only (~$15/month).

---

## Monitoring

### CloudWatch Metrics to Monitor

```hcl
# Add CloudWatch alarms for Redis
resource "aws_cloudwatch_metric_alarm" "redis_cpu" {
  alarm_name          = "${local.project_prefix}-redis-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ElastiCache"
  period              = "300"
  statistic           = "Average"
  threshold           = "80"
  alarm_description   = "Alert when Redis CPU > 80%"
  
  dimensions = {
    CacheClusterId = aws_elasticache_cluster.price_cache.cluster_id
  }
}

resource "aws_cloudwatch_metric_alarm" "redis_memory" {
  alarm_name          = "${local.project_prefix}-redis-memory"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "DatabaseMemoryUsagePercentage"
  namespace           = "AWS/ElastiCache"
  period              = "300"
  statistic           = "Average"
  threshold           = "85"
  alarm_description   = "Alert when Redis memory > 85%"
  
  dimensions = {
    CacheClusterId = aws_elasticache_cluster.price_cache.cluster_id
  }
}
```

### Expected Cache Performance

After Redis setup, monitor these metrics in logs:

```
[PRICE_CACHE] Redis hit for AAPL/1d
[PRICE_CACHE] Hit for 8500/10600 symbols (80% cache hit rate)
```

**Expected improvement**:
- First run: 7.5+ hours (all cache misses, populates Redis)
- Subsequent runs (within 23 hours): **5-10 minutes** (80%+ cache hits)

---

## Troubleshooting

### Redis Connection Refused

```bash
# Check Redis is running
docker-compose ps redis

# Check logs
docker-compose logs redis

# Test connectivity
redis-cli -h localhost:6379 ping
```

### Cache Not Being Used

```bash
# Verify REDIS_URL is set
echo $REDIS_URL

# Check logs for cache status
grep "PRICE_CACHE" loader.log | head -20

# Should see either:
# [PRICE_CACHE] Redis hit for AAPL/1d
# [PRICE_CACHE] Redis unavailable ..., using local cache only
```

### Slow Cache Hits

```bash
# Check Redis performance
redis-cli --latency

# Check memory usage
redis-cli info memory | grep used_memory
```

---

## Future Enhancements

1. **Authentication**: Add Redis AUTH token (AWS parameter store integration)
2. **Replication**: Multi-AZ failover for high availability
3. **Cluster Mode**: Handle larger deployments with Redis Cluster
4. **Data Persistence**: Enable AOF (Append-Only File) for durability
5. **Cache Invalidation**: Smart invalidation on data quality issues

---

## References

- [Redis Documentation](https://redis.io/docs/)
- [AWS ElastiCache Documentation](https://docs.aws.amazon.com/elasticache/)
- [Price Cache Implementation](utils/cache/price_cache.py)
- [Price Loader Using Cache](loaders/price_fetcher.py:45)
