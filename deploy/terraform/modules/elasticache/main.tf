# ElastiCache Redis Cluster for GALILEO
# Provides high-performance caching, session storage, and rate limiting

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Security Group for Redis
resource "aws_security_group" "redis" {
  name_prefix = "${var.name_prefix}-redis-"
  description = "Security group for ElastiCache Redis cluster"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Redis from application"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = var.allowed_security_groups
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.name_prefix}-redis-sg"
    }
  )

  lifecycle {
    create_before_destroy = true
  }
}

# Subnet Group for Redis
resource "aws_elasticache_subnet_group" "redis" {
  name       = "${var.name_prefix}-redis-subnet-group"
  subnet_ids = var.subnet_ids

  tags = merge(
    var.tags,
    {
      Name = "${var.name_prefix}-redis-subnet-group"
    }
  )
}

# Parameter Group for Redis
resource "aws_elasticache_parameter_group" "redis" {
  name   = "${var.name_prefix}-redis-params"
  family = var.parameter_group_family

  # Memory management
  parameter {
    name  = "maxmemory-policy"
    value = var.maxmemory_policy
  }

  # Persistence configuration
  dynamic "parameter" {
    for_each = var.snapshot_retention_limit > 0 ? [1] : []
    content {
      name  = "appendonly"
      value = "yes"
    }
  }

  # Timeout for idle connections (5 minutes)
  parameter {
    name  = "timeout"
    value = "300"
  }

  # Enable keyspace notifications for expired keys
  parameter {
    name  = "notify-keyspace-events"
    value = "Ex"
  }

  # Slowlog configuration (queries > 10ms)
  parameter {
    name  = "slowlog-log-slower-than"
    value = "10000"
  }

  parameter {
    name  = "slowlog-max-len"
    value = "128"
  }

  tags = var.tags
}

# Replication Group (Cluster Mode Disabled)
resource "aws_elasticache_replication_group" "redis" {
  count = var.cluster_mode_enabled ? 0 : 1

  replication_group_id       = "${var.name_prefix}-redis"
  replication_group_description = "Redis cluster for ${var.name_prefix}"

  engine               = "redis"
  engine_version       = var.engine_version
  port                 = 6379
  parameter_group_name = aws_elasticache_parameter_group.redis.name
  subnet_group_name    = aws_elasticache_subnet_group.redis.name
  security_group_ids   = [aws_security_group.redis.id]

  node_type            = var.node_type
  num_cache_clusters   = var.num_cache_clusters

  # High Availability
  automatic_failover_enabled = var.automatic_failover_enabled
  multi_az_enabled          = var.multi_az_enabled

  # Maintenance and Backups
  maintenance_window       = var.maintenance_window
  snapshot_window         = var.snapshot_window
  snapshot_retention_limit = var.snapshot_retention_limit
  final_snapshot_identifier = var.create_final_snapshot ? "${var.name_prefix}-redis-final-${formatdate("YYYY-MM-DD-hhmm", timestamp())}" : null

  # Encryption
  at_rest_encryption_enabled = var.at_rest_encryption_enabled
  kms_key_id                = var.kms_key_id
  transit_encryption_enabled = var.transit_encryption_enabled
  auth_token                = var.transit_encryption_enabled ? var.auth_token : null

  # Auto minor version upgrades
  auto_minor_version_upgrade = var.auto_minor_version_upgrade

  # Notification topic for events
  notification_topic_arn = var.notification_topic_arn

  # Logging
  log_delivery_configuration {
    destination      = aws_cloudwatch_log_group.redis_slow_log.name
    destination_type = "cloudwatch-logs"
    log_format      = "json"
    log_type        = "slow-log"
  }

  log_delivery_configuration {
    destination      = aws_cloudwatch_log_group.redis_engine_log.name
    destination_type = "cloudwatch-logs"
    log_format      = "json"
    log_type        = "engine-log"
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.name_prefix}-redis"
    }
  )

  lifecycle {
    ignore_changes = [final_snapshot_identifier]
  }
}

# Replication Group (Cluster Mode Enabled)
resource "aws_elasticache_replication_group" "redis_cluster" {
  count = var.cluster_mode_enabled ? 1 : 0

  replication_group_id       = "${var.name_prefix}-redis"
  replication_group_description = "Redis cluster mode enabled for ${var.name_prefix}"

  engine               = "redis"
  engine_version       = var.engine_version
  port                 = 6379
  parameter_group_name = aws_elasticache_parameter_group.redis.name
  subnet_group_name    = aws_elasticache_subnet_group.redis.name
  security_group_ids   = [aws_security_group.redis.id]

  node_type = var.node_type

  # Cluster mode configuration
  automatic_failover_enabled = true

  num_node_groups         = var.num_node_groups
  replicas_per_node_group = var.replicas_per_node_group

  # Maintenance and Backups
  maintenance_window       = var.maintenance_window
  snapshot_window         = var.snapshot_window
  snapshot_retention_limit = var.snapshot_retention_limit

  # Encryption
  at_rest_encryption_enabled = var.at_rest_encryption_enabled
  kms_key_id                = var.kms_key_id
  transit_encryption_enabled = var.transit_encryption_enabled
  auth_token                = var.transit_encryption_enabled ? var.auth_token : null

  # Auto minor version upgrades
  auto_minor_version_upgrade = var.auto_minor_version_upgrade

  # Notification topic for events
  notification_topic_arn = var.notification_topic_arn

  # Logging
  log_delivery_configuration {
    destination      = aws_cloudwatch_log_group.redis_slow_log.name
    destination_type = "cloudwatch-logs"
    log_format      = "json"
    log_type        = "slow-log"
  }

  log_delivery_configuration {
    destination      = aws_cloudwatch_log_group.redis_engine_log.name
    destination_type = "cloudwatch-logs"
    log_format      = "json"
    log_type        = "engine-log"
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.name_prefix}-redis-cluster"
    }
  )
}

# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "redis_slow_log" {
  name              = "/aws/elasticache/${var.name_prefix}/redis/slow-log"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "redis_engine_log" {
  name              = "/aws/elasticache/${var.name_prefix}/redis/engine-log"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

# CloudWatch Alarms
resource "aws_cloudwatch_metric_alarm" "cpu_utilization" {
  alarm_name          = "${var.name_prefix}-redis-cpu-utilization"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Average"
  threshold           = var.cpu_alarm_threshold
  alarm_description   = "Redis CPU utilization is too high"
  alarm_actions       = var.alarm_actions

  dimensions = {
    ReplicationGroupId = var.cluster_mode_enabled ? aws_elasticache_replication_group.redis_cluster[0].id : aws_elasticache_replication_group.redis[0].id
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "memory_utilization" {
  alarm_name          = "${var.name_prefix}-redis-memory-utilization"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "DatabaseMemoryUsagePercentage"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Average"
  threshold           = var.memory_alarm_threshold
  alarm_description   = "Redis memory utilization is too high"
  alarm_actions       = var.alarm_actions

  dimensions = {
    ReplicationGroupId = var.cluster_mode_enabled ? aws_elasticache_replication_group.redis_cluster[0].id : aws_elasticache_replication_group.redis[0].id
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "evictions" {
  alarm_name          = "${var.name_prefix}-redis-evictions"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Evictions"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Sum"
  threshold           = var.evictions_alarm_threshold
  alarm_description   = "Redis is evicting keys, consider scaling up"
  alarm_actions       = var.alarm_actions

  dimensions = {
    ReplicationGroupId = var.cluster_mode_enabled ? aws_elasticache_replication_group.redis_cluster[0].id : aws_elasticache_replication_group.redis[0].id
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "replication_lag" {
  count = var.num_cache_clusters > 1 || var.cluster_mode_enabled ? 1 : 0

  alarm_name          = "${var.name_prefix}-redis-replication-lag"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ReplicationLag"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Average"
  threshold           = var.replication_lag_alarm_threshold
  alarm_description   = "Redis replication lag is too high"
  alarm_actions       = var.alarm_actions

  dimensions = {
    ReplicationGroupId = var.cluster_mode_enabled ? aws_elasticache_replication_group.redis_cluster[0].id : aws_elasticache_replication_group.redis[0].id
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "swap_usage" {
  alarm_name          = "${var.name_prefix}-redis-swap-usage"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "SwapUsage"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Average"
  threshold           = 52428800  # 50 MB in bytes
  alarm_description   = "Redis is using swap, performance degradation likely"
  alarm_actions       = var.alarm_actions

  dimensions = {
    ReplicationGroupId = var.cluster_mode_enabled ? aws_elasticache_replication_group.redis_cluster[0].id : aws_elasticache_replication_group.redis[0].id
  }

  tags = var.tags
}
