# Variables for S3 Buckets Module

variable "name_prefix" {
  description = "Prefix for all resource names"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

# KMS Encryption
variable "create_kms_key" {
  description = "Create KMS key for S3 encryption"
  type        = bool
  default     = true
}

variable "kms_deletion_window" {
  description = "KMS key deletion window in days"
  type        = number
  default     = 30
}

# Lifecycle Policies
variable "logs_retention_days" {
  description = "Days to retain logs before deletion"
  type        = number
  default     = 365
}

variable "backups_retention_days" {
  description = "Days to retain backups before deletion"
  type        = number
  default     = 2555  # 7 years
}

# Logging
variable "enable_logging" {
  description = "Enable S3 access logging"
  type        = bool
  default     = true
}

# Replication
variable "enable_backup_replication" {
  description = "Enable cross-region replication for backups"
  type        = bool
  default     = false
}

variable "backup_replication_destination" {
  description = "Destination bucket ARN for backup replication"
  type        = string
  default     = null
}

variable "replication_role_arn" {
  description = "IAM role ARN for S3 replication"
  type        = string
  default     = null
}

# Static Assets
variable "create_static_bucket" {
  description = "Create bucket for static assets"
  type        = bool
  default     = true
}

variable "cors_allowed_origins" {
  description = "Allowed origins for CORS on static bucket"
  type        = list(string)
  default     = ["*"]
}

# CloudWatch Alarms
variable "data_bucket_size_alarm_gb" {
  description = "Alarm threshold for data bucket size in GB"
  type        = number
  default     = 5000
}

variable "alarm_actions" {
  description = "List of ARNs to notify when alarms trigger"
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
