# Variables for CloudFront CDN Module

variable "name_prefix" {
  description = "Prefix for all resource names"
  type        = string
}

variable "s3_bucket_id" {
  description = "S3 bucket ID for static assets"
  type        = string
}

variable "s3_bucket_regional_domain_name" {
  description = "S3 bucket regional domain name"
  type        = string
}

variable "default_root_object" {
  description = "Default root object for CloudFront"
  type        = string
  default     = "index.html"
}

variable "price_class" {
  description = "CloudFront price class"
  type        = string
  default     = "PriceClass_100"  # US, Canada, Europe

  validation {
    condition = contains([
      "PriceClass_All",
      "PriceClass_200",
      "PriceClass_100"
    ], var.price_class)
    error_message = "Invalid price class."
  }
}

variable "aliases" {
  description = "Alternate domain names (CNAMEs) for the distribution"
  type        = list(string)
  default     = []
}

# Origin Configuration
variable "origin_shield_enabled" {
  description = "Enable CloudFront Origin Shield"
  type        = bool
  default     = true
}

variable "origin_shield_region" {
  description = "AWS region for Origin Shield"
  type        = string
  default     = "us-east-1"
}

variable "api_domain_name" {
  description = "API domain name for API origin (optional)"
  type        = string
  default     = null
}

variable "custom_header_value" {
  description = "Custom header value for origin requests"
  type        = string
  default     = "cloudfront"
  sensitive   = true
}

# SSL/TLS
variable "acm_certificate_arn" {
  description = "ACM certificate ARN for HTTPS (must be in us-east-1)"
  type        = string
  default     = null
}

# Geographic Restrictions
variable "geo_restriction_type" {
  description = "Type of geographic restriction (none, whitelist, blacklist)"
  type        = string
  default     = "none"

  validation {
    condition = contains([
      "none",
      "whitelist",
      "blacklist"
    ], var.geo_restriction_type)
    error_message = "Invalid geo restriction type."
  }
}

variable "geo_restriction_locations" {
  description = "List of country codes for geo restriction"
  type        = list(string)
  default     = []
}

# Logging
variable "logging_bucket" {
  description = "S3 bucket for CloudFront access logs"
  type        = string
  default     = null
}

variable "logging_prefix" {
  description = "Prefix for CloudFront access logs"
  type        = string
  default     = "cdn-logs/"
}

# WAF
variable "web_acl_id" {
  description = "AWS WAF Web ACL ID"
  type        = string
  default     = null
}

# Security Headers
variable "content_security_policy" {
  description = "Content Security Policy header value"
  type        = string
  default     = "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self' https:;"
}

variable "cors_allowed_origins" {
  description = "Allowed origins for CORS"
  type        = list(string)
  default     = ["*"]
}

# CloudWatch Alarms
variable "error_rate_threshold" {
  description = "Threshold for 5xx error rate alarm (%)"
  type        = number
  default     = 5
}

variable "cache_hit_rate_threshold" {
  description = "Threshold for cache hit rate alarm (%)"
  type        = number
  default     = 80
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
