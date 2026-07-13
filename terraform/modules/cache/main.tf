// ElastiCache Redis cluster for price cache (90% yfinance API reduction)
// Used by: stock_prices_daily loader (and future loaders)
// Purpose: Store daily price data in Redis for 23-hour TTL

resource "aws_elasticache_cluster" "price_cache" {
  cluster_id           = "${var.project_name}-price-cache-${var.environment}"
  engine               = "redis"
  engine_version       = "7.0"
  node_type            = var.redis_node_type
  num_cache_nodes      = 1
  parameter_group_name = aws_elasticache_parameter_group.price_cache.name
  engine_version_actual = data.aws_elasticache_engine_version.redis.version

  # Security & VPC
  security_group_ids            = [aws_security_group.redis_cache.id]
  subnet_group_name             = aws_elasticache_subnet_group.redis_cache.name
  automatic_failover_enabled    = false # Single-node cluster, no failover needed

  # Maintenance
  maintenance_window = "sun:03:00-sun:04:00" # Weekly Sunday 3 AM UTC
  notification_topic_arn = var.sns_alerts_enabled ? var.sns_alerts_topic_arn : null

  # Encryption at rest (for compliance)
  at_rest_encryption_enabled = true
  kms_key_id                 = var.kms_key_id

  # Encryption in transit
  transit_encryption_enabled = false # Disabled for ECS→Redis within private VPC (add if cross-AZ)
  auth_token_enabled         = false # Not needed in private VPC

  # Logging
  log_delivery_configuration {
    destination      = var.cloudwatch_log_group_name
    destination_type = "cloudwatch-logs"
    log_format       = "json"
    enabled          = true
  }

  tags = merge(var.common_tags, {
    Name   = "${var.project_name}-price-cache"
    Module = "cache"
  })

  depends_on = [aws_elasticache_subnet_group.redis_cache]
}

# Get the actual Redis version available
data "aws_elasticache_engine_version" "redis" {
  engine  = "redis"
  version = "7.0"
}

# ElastiCache parameter group for Redis 7.0
resource "aws_elasticache_parameter_group" "price_cache" {
  family      = "redis7"
  name        = "${var.project_name}-price-cache-params-${var.environment}"
  description = "Parameter group for price cache (23h TTL, LRU eviction)"

  # Memory management
  parameter {
    name  = "maxmemory-policy"
    value = "allkeys-lru" # Evict LRU keys when max memory reached (don't evict recently-used prices)
  }

  # Persistence (optional, disabled for this cache since data can be refetched)
  parameter {
    name  = "appendonly"
    value = "no" # Disable AOF persistence for price cache (not critical data)
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-price-cache-params"
  })
}

# ElastiCache Subnet Group (required for VPC deployment)
resource "aws_elasticache_subnet_group" "redis_cache" {
  name       = "${var.project_name}-price-cache-subnet-group-${var.environment}"
  subnet_ids = var.private_subnet_ids
  description = "Private subnets for Redis price cache"

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-price-cache-subnet-group"
  })
}

# Security Group for Redis (allow ECS tasks to connect)
resource "aws_security_group" "redis_cache" {
  name        = "${var.project_name}-price-cache-sg-${var.environment}"
  description = "Security group for ElastiCache Redis (price cache)"
  vpc_id      = var.vpc_id

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-price-cache-sg"
  })
}

# Allow ECS task security group to connect to Redis
resource "aws_security_group_rule" "redis_from_ecs" {
  type                     = "ingress"
  from_port                = 6379
  to_port                  = 6379
  protocol                 = "tcp"
  source_security_group_id = var.ecs_task_security_group_id
  security_group_id        = aws_security_group.redis_cache.id
  description              = "Allow ECS loader tasks to access Redis cache"
}

# Allow outbound (should be handled by default, but explicit for clarity)
resource "aws_security_group_rule" "redis_egress" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.redis_cache.id
  description       = "Allow all outbound traffic from Redis"
}

# CloudWatch Log Group for Redis Slow Log
resource "aws_cloudwatch_log_group" "redis_cache" {
  name              = "/aws/elasticache/${var.project_name}-price-cache-${var.environment}"
  retention_in_days = 7

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-price-cache-logs"
  })
}
