#!/bin/bash
# Setup ElastiCache Redis for Integration Testing

set -e

REGION="us-east-1"
ENVIRONMENT="dev"
CLUSTER_ID="stocks-redis-$ENVIRONMENT"

echo "🔴 Setting up ElastiCache Redis for integration testing..."

# 1. Create Redis parameter group
echo "Creating Redis parameter group..."
aws elasticache create-cache-parameter-group \
    --region $REGION \
    --cache-parameter-group-name "stocks-redis-params-$ENVIRONMENT" \
    --cache-parameter-group-family "redis7.x" \
    --description "Redis parameters for stocks webapp $ENVIRONMENT" \
    || echo "Parameter group may already exist"

# 2. Create Redis subnet group (requires VPC setup)
echo "Creating Redis subnet group..."
# Note: This requires existing VPC and subnets
# aws elasticache create-cache-subnet-group \
#     --region $REGION \
#     --cache-subnet-group-name "stocks-redis-subnet-$ENVIRONMENT" \
#     --cache-subnet-group-description "Redis subnet group for stocks webapp" \
#     --subnet-ids subnet-12345 subnet-67890

# 3. Create Redis cache cluster
echo "Creating Redis cache cluster..."
aws elasticache create-cache-cluster \
    --region $REGION \
    --cache-cluster-id "$CLUSTER_ID" \
    --engine "redis" \
    --engine-version "7.0" \
    --cache-node-type "cache.t3.micro" \
    --num-cache-nodes 1 \
    --cache-parameter-group-name "stocks-redis-params-$ENVIRONMENT" \
    --port 6379 \
    --tags Key="Environment",Value="$ENVIRONMENT" Key="Service",Value="stocks-webapp" \
    || echo "Cache cluster may already exist"

# 4. Wait for cluster to be available
echo "Waiting for Redis cluster to be available..."
aws elasticache wait cache-cluster-available \
    --region $REGION \
    --cache-cluster-id "$CLUSTER_ID"

# 5. Get cluster endpoint
REDIS_ENDPOINT=$(aws elasticache describe-cache-clusters \
    --region $REGION \
    --cache-cluster-id "$CLUSTER_ID" \
    --show-cache-node-info \
    --query 'CacheClusters[0].CacheNodes[0].Endpoint.Address' \
    --output text)

echo "✅ ElastiCache Redis setup complete!"
echo ""
echo "📝 Redis Connection Details:"
echo "Endpoint: $REDIS_ENDPOINT:6379"
echo ""
echo "💡 Update your environment variables:"
echo "export REDIS_ENDPOINT=\"$REDIS_ENDPOINT\""
echo "export REDIS_PORT=\"6379\""