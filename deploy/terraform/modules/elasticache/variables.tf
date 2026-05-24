# Variables for ElastiCache Redis Module

variable "name_prefix" {
  description = "Prefix for all resource names"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID where Redis cluster will be deployed"
  type        = string
}

variable "subnet_ids" {
  description = "List of subnet IDs for Redis cluster"
  type        = list(string)
}

variable "allowed_security_groups" {
  description = "List of security group IDs allowed to access Redis"
  type        = list(string)
}

variable "node_type" {
  description = "Instance type for Redis nodes"
  type        = string
  default     = "cache.r7g.large"
}

variable "engine_version" {
  description = "Redis engine version"
  type        = string
  default     = "7.0"
}

variable "parameter_group_family" {
  description = "Redis parameter group family"
  type        = string
  default     = "redis7"
}

# Cluster Configuration
variable "cluster_mode_enabled" {
  description = "Enable cluster mode (sharding) for Redis"
  type        = bool
  default     = false
}

variable "num_cache_clusters" {
  description = "Number of cache clusters (replicas) for non-cluster mode"
  type        = number
  default     = 2
}

variable "num_node_groups" {
  description = "Number of node groups (shards) for cluster mode"
  type        = number
  default     = 3
}

variable "replicas_per_node_group" {
  description = "Number of replicas per node group in cluster mode"
  type        = number
  default     = 1
}

# High Availability
variable "automatic_failover_enabled" {
  description = "Enable automatic failover"
  type        = bool
  default     = true
}

variable "multi_az_enabled" {
  description = "Enable Multi-AZ deployment"
  type        = bool
  default     = true
}

# Encryption
variable "at_rest_encryption_enabled" {
  description = "Enable encryption at rest"
  type        = bool
  default     = true
}

variable "kms_key_id" {
  description = "KMS key ID for encryption at rest (uses default AWS managed key if not specified)"
  type        = string
  default     = null
}

variable "transit_encryption_enabled" {
  description = "Enable TLS encryption in transit"
  type        = bool
  default     = true
}

variable "auth_token" {
  description = "Auth token for Redis (required when transit encryption is enabled)"
  type        = string
  default     = null
  sensitive   = true
}

# Maintenance and Backups
variable "maintenance_window" {
  description = "Maintenance window (UTC)"
  type        = string
  default     = "sun:05:00-sun:07:00"
}

variable "snapshot_window" {
  description = "Daily snapshot window (UTC)"
  type        = string
  default     = "03:00-05:00"
}

variable "snapshot_retention_limit" {
  description = "Number of days to retain snapshots"
  type        = number
  default     = 7
}

variable "create_final_snapshot" {
  description = "Create final snapshot before deletion"
  type        = bool
  default     = true
}

variable "auto_minor_version_upgrade" {
  description = "Enable automatic minor version upgrades"
  type        = bool
  default     = true
}

# Memory Management
variable "maxmemory_policy" {
  description = "Redis eviction policy (allkeys-lru, volatile-lru, etc.)"
  type        = string
  default     = "allkeys-lru"

  validation {
    condition = contains([
      "volatile-lru",
      "allkeys-lru",
      "volatile-lfu",
      "allkeys-lfu",
      "volatile-random",
      "allkeys-random",
      "volatile-ttl",
      "noeviction"
    ], var.maxmemory_policy)
    error_message = "Invalid maxmemory_policy. Must be a valid Redis eviction policy."
  }
}

# Logging
variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 7
}

# Alarms
variable "cpu_alarm_threshold" {
  description = "CPU utilization threshold for alarm (%)"
  type        = number
  default     = 75
}

variable "memory_alarm_threshold" {
  description = "Memory utilization threshold for alarm (%)"
  type        = number
  default     = 90
}

variable "evictions_alarm_threshold" {
  description = "Number of evictions to trigger alarm"
  type        = number
  default     = 1000
}

variable "replication_lag_alarm_threshold" {
  description = "Replication lag threshold in seconds"
  type        = number
  default     = 30
}

variable "alarm_actions" {
  description = "List of ARNs to notify when alarms trigger"
  type        = list(string)
  default     = []
}

variable "notification_topic_arn" {
  description = "SNS topic ARN for ElastiCache notifications"
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
