# GALILEO Platform - Terraform Variables

# General Configuration
variable "environment" {
  description = "Environment name (dev, staging, production)"
  type        = string
  default     = "production"
}

variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-west-2"
}

variable "owner_email" {
  description = "Owner email for resource tagging"
  type        = string
}

# VPC Configuration
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones for subnets"
  type        = list(string)
  default     = ["us-west-2a", "us-west-2b", "us-west-2c"]
}

variable "private_subnets" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
}

variable "public_subnets" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]
}

# EKS Configuration
variable "eks_cluster_version" {
  description = "Kubernetes version for EKS cluster"
  type        = string
  default     = "1.28"
}

variable "eks_general_nodes_desired" {
  description = "Desired number of general worker nodes"
  type        = number
  default     = 3
}

variable "eks_general_nodes_min" {
  description = "Minimum number of general worker nodes"
  type        = number
  default     = 3
}

variable "eks_general_nodes_max" {
  description = "Maximum number of general worker nodes"
  type        = number
  default     = 10
}

variable "eks_compute_nodes_desired" {
  description = "Desired number of compute worker nodes"
  type        = number
  default     = 4
}

variable "eks_compute_nodes_min" {
  description = "Minimum number of compute worker nodes"
  type        = number
  default     = 2
}

variable "eks_compute_nodes_max" {
  description = "Maximum number of compute worker nodes"
  type        = number
  default     = 20
}

# RDS Configuration
variable "rds_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.r5.xlarge"
}

variable "rds_allocated_storage" {
  description = "Initial storage allocation (GB)"
  type        = number
  default     = 100
}

variable "rds_max_allocated_storage" {
  description = "Maximum storage for autoscaling (GB)"
  type        = number
  default     = 1000
}

variable "database_name" {
  description = "Database name"
  type        = string
  default     = "galileo"
}

variable "database_username" {
  description = "Database master username"
  type        = string
  default     = "galileo_admin"
}

# Redis Configuration
variable "redis_node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.r5.large"
}

# CloudFront Configuration
variable "cloudfront_price_class" {
  description = "CloudFront price class"
  type        = string
  default     = "PriceClass_100"  # US, Canada, Europe
}

# Feature Flags
variable "enable_monitoring" {
  description = "Enable CloudWatch monitoring"
  type        = bool
  default     = true
}

variable "enable_backup" {
  description = "Enable automated backups"
  type        = bool
  default     = true
}

variable "enable_encryption" {
  description = "Enable encryption at rest"
  type        = bool
  default     = true
}
