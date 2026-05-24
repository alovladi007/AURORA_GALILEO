# Outputs for ElastiCache Redis Module

output "replication_group_id" {
  description = "ID of the Redis replication group"
  value       = var.cluster_mode_enabled ? aws_elasticache_replication_group.redis_cluster[0].id : aws_elasticache_replication_group.redis[0].id
}

output "replication_group_arn" {
  description = "ARN of the Redis replication group"
  value       = var.cluster_mode_enabled ? aws_elasticache_replication_group.redis_cluster[0].arn : aws_elasticache_replication_group.redis[0].arn
}

output "primary_endpoint_address" {
  description = "Primary endpoint address (write endpoint)"
  value       = var.cluster_mode_enabled ? aws_elasticache_replication_group.redis_cluster[0].configuration_endpoint_address : aws_elasticache_replication_group.redis[0].primary_endpoint_address
}

output "reader_endpoint_address" {
  description = "Reader endpoint address (read replicas)"
  value       = var.cluster_mode_enabled ? null : aws_elasticache_replication_group.redis[0].reader_endpoint_address
}

output "configuration_endpoint_address" {
  description = "Configuration endpoint address (cluster mode only)"
  value       = var.cluster_mode_enabled ? aws_elasticache_replication_group.redis_cluster[0].configuration_endpoint_address : null
}

output "port" {
  description = "Redis port"
  value       = 6379
}

output "security_group_id" {
  description = "Security group ID for Redis cluster"
  value       = aws_security_group.redis.id
}

output "parameter_group_name" {
  description = "Name of the Redis parameter group"
  value       = aws_elasticache_parameter_group.redis.name
}

output "subnet_group_name" {
  description = "Name of the Redis subnet group"
  value       = aws_elasticache_subnet_group.redis.name
}

output "member_clusters" {
  description = "List of member cluster IDs"
  value       = var.cluster_mode_enabled ? [] : aws_elasticache_replication_group.redis[0].member_clusters
}

output "cluster_enabled" {
  description = "Whether cluster mode is enabled"
  value       = var.cluster_mode_enabled
}

output "auth_token_enabled" {
  description = "Whether auth token is enabled"
  value       = var.transit_encryption_enabled
}

output "connection_string" {
  description = "Redis connection string"
  value       = var.transit_encryption_enabled ? "rediss://${var.cluster_mode_enabled ? aws_elasticache_replication_group.redis_cluster[0].configuration_endpoint_address : aws_elasticache_replication_group.redis[0].primary_endpoint_address}:6379" : "redis://${var.cluster_mode_enabled ? aws_elasticache_replication_group.redis_cluster[0].configuration_endpoint_address : aws_elasticache_replication_group.redis[0].primary_endpoint_address}:6379"
}

# CloudWatch Log Groups
output "slow_log_group_name" {
  description = "CloudWatch log group name for slow log"
  value       = aws_cloudwatch_log_group.redis_slow_log.name
}

output "engine_log_group_name" {
  description = "CloudWatch log group name for engine log"
  value       = aws_cloudwatch_log_group.redis_engine_log.name
}

# Alarm ARNs
output "cpu_alarm_arn" {
  description = "ARN of CPU utilization alarm"
  value       = aws_cloudwatch_metric_alarm.cpu_utilization.arn
}

output "memory_alarm_arn" {
  description = "ARN of memory utilization alarm"
  value       = aws_cloudwatch_metric_alarm.memory_utilization.arn
}

output "evictions_alarm_arn" {
  description = "ARN of evictions alarm"
  value       = aws_cloudwatch_metric_alarm.evictions.arn
}

output "replication_lag_alarm_arn" {
  description = "ARN of replication lag alarm (if applicable)"
  value       = var.num_cache_clusters > 1 || var.cluster_mode_enabled ? aws_cloudwatch_metric_alarm.replication_lag[0].arn : null
}
