variable "identifier" {
  description = "RDS instance identifier"
  type        = string
}

variable "engine_version" {
  description = "PostgreSQL version"
  type        = string
  default     = "15.4"
}

variable "parameter_group_family" {
  description = "Parameter group family"
  type        = string
  default     = "postgres15"
}

variable "instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.r5.large"
}

variable "allocated_storage" {
  description = "Initial storage allocation (GB)"
  type        = number
  default     = 100
}

variable "max_allocated_storage" {
  description = "Maximum storage for autoscaling (GB)"
  type        = number
  default     = 1000
}

variable "storage_type" {
  description = "Storage type (gp3, gp2, io1, io2)"
  type        = string
  default     = "gp3"
}

variable "iops" {
  description = "IOPS for io1/io2 storage"
  type        = number
  default     = 3000
}

variable "database_name" {
  description = "Initial database name"
  type        = string
}

variable "master_username" {
  description = "Master username"
  type        = string
  default     = "postgres"
}

variable "master_password" {
  description = "Master password (auto-generated if null)"
  type        = string
  default     = null
  sensitive   = true
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs (private)"
  type        = list(string)
}

variable "allowed_security_groups" {
  description = "Security group IDs allowed to connect"
  type        = list(string)
}

variable "multi_az" {
  description = "Enable Multi-AZ deployment"
  type        = bool
  default     = true
}

variable "backup_retention_period" {
  description = "Backup retention in days"
  type        = number
  default     = 30
}

variable "backup_window" {
  description = "Daily backup window (UTC)"
  type        = string
  default     = "03:00-04:00"
}

variable "maintenance_window" {
  description = "Maintenance window"
  type        = string
  default     = "mon:04:00-mon:05:00"
}

variable "auto_minor_version_upgrade" {
  description = "Enable automatic minor version upgrades"
  type        = bool
  default     = true
}

variable "performance_insights_enabled" {
  description = "Enable Performance Insights"
  type        = bool
  default     = true
}

variable "performance_insights_retention_period" {
  description = "Performance Insights retention (days)"
  type        = number
  default     = 7
}

variable "monitoring_interval" {
  description = "Enhanced monitoring interval (0 to disable)"
  type        = number
  default     = 60
}

variable "enabled_cloudwatch_logs_exports" {
  description = "Log types to export to CloudWatch"
  type        = list(string)
  default     = ["postgresql", "upgrade"]
}

variable "deletion_protection" {
  description = "Enable deletion protection"
  type        = bool
  default     = true
}

variable "apply_immediately" {
  description = "Apply changes immediately"
  type        = bool
  default     = false
}

variable "max_connections" {
  description = "Maximum connections"
  type        = string
  default     = "200"
}

variable "create_read_replica" {
  description = "Create read replicas"
  type        = bool
  default     = false
}

variable "read_replica_count" {
  description = "Number of read replicas"
  type        = number
  default     = 0
}

variable "read_replica_instance_class" {
  description = "Read replica instance class (defaults to primary)"
  type        = string
  default     = null
}

variable "enable_alarms" {
  description = "Enable CloudWatch alarms"
  type        = bool
  default     = true
}

variable "alarm_actions" {
  description = "ARNs for alarm actions (SNS topics)"
  type        = list(string)
  default     = []
}

variable "secret_recovery_window_days" {
  description = "Days to retain secret after deletion"
  type        = number
  default     = 7
}

variable "tags" {
  description = "Tags"
  type        = map(string)
  default     = {}
}
