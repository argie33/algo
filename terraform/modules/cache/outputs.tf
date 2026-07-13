output "redis_endpoint_address" {
  description = "Redis primary endpoint address (hostname only, no port)"
  value       = aws_elasticache_cluster.price_cache.cache_nodes[0].address
}

output "redis_port" {
  description = "Redis port (6379)"
  value       = aws_elasticache_cluster.price_cache.port
}

output "redis_endpoint_url" {
  description = "Full Redis URL for REDIS_URL environment variable (redis://host:port/0)"
  value       = "redis://${aws_elasticache_cluster.price_cache.cache_nodes[0].address}:${aws_elasticache_cluster.price_cache.port}/0"
}

output "redis_security_group_id" {
  description = "Security group ID of Redis cluster"
  value       = aws_security_group.redis_cache.id
}

output "redis_cluster_id" {
  description = "ElastiCache cluster ID"
  value       = aws_elasticache_cluster.price_cache.cluster_id
}

output "redis_engine_version" {
  description = "Redis engine version"
  value       = aws_elasticache_cluster.price_cache.engine_version
}
