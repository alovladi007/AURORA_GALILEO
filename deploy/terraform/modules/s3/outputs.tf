# Outputs for S3 Buckets Module

# KMS Key
output "kms_key_id" {
  description = "ID of the KMS key for S3 encryption"
  value       = var.create_kms_key ? aws_kms_key.s3[0].id : null
}

output "kms_key_arn" {
  description = "ARN of the KMS key for S3 encryption"
  value       = var.create_kms_key ? aws_kms_key.s3[0].arn : null
}

# Data Bucket
output "data_bucket_id" {
  description = "ID of the data bucket"
  value       = aws_s3_bucket.data.id
}

output "data_bucket_arn" {
  description = "ARN of the data bucket"
  value       = aws_s3_bucket.data.arn
}

output "data_bucket_domain_name" {
  description = "Domain name of the data bucket"
  value       = aws_s3_bucket.data.bucket_domain_name
}

output "data_bucket_regional_domain_name" {
  description = "Regional domain name of the data bucket"
  value       = aws_s3_bucket.data.bucket_regional_domain_name
}

# Models Bucket
output "models_bucket_id" {
  description = "ID of the models bucket"
  value       = aws_s3_bucket.models.id
}

output "models_bucket_arn" {
  description = "ARN of the models bucket"
  value       = aws_s3_bucket.models.arn
}

output "models_bucket_domain_name" {
  description = "Domain name of the models bucket"
  value       = aws_s3_bucket.models.bucket_domain_name
}

output "models_bucket_regional_domain_name" {
  description = "Regional domain name of the models bucket"
  value       = aws_s3_bucket.models.bucket_regional_domain_name
}

# Logs Bucket
output "logs_bucket_id" {
  description = "ID of the logs bucket"
  value       = aws_s3_bucket.logs.id
}

output "logs_bucket_arn" {
  description = "ARN of the logs bucket"
  value       = aws_s3_bucket.logs.arn
}

output "logs_bucket_domain_name" {
  description = "Domain name of the logs bucket"
  value       = aws_s3_bucket.logs.bucket_domain_name
}

# Backups Bucket
output "backups_bucket_id" {
  description = "ID of the backups bucket"
  value       = aws_s3_bucket.backups.id
}

output "backups_bucket_arn" {
  description = "ARN of the backups bucket"
  value       = aws_s3_bucket.backups.arn
}

output "backups_bucket_domain_name" {
  description = "Domain name of the backups bucket"
  value       = aws_s3_bucket.backups.bucket_domain_name
}

# Static Assets Bucket
output "static_bucket_id" {
  description = "ID of the static assets bucket"
  value       = var.create_static_bucket ? aws_s3_bucket.static[0].id : null
}

output "static_bucket_arn" {
  description = "ARN of the static assets bucket"
  value       = var.create_static_bucket ? aws_s3_bucket.static[0].arn : null
}

output "static_bucket_domain_name" {
  description = "Domain name of the static assets bucket"
  value       = var.create_static_bucket ? aws_s3_bucket.static[0].bucket_domain_name : null
}

output "static_bucket_regional_domain_name" {
  description = "Regional domain name of the static assets bucket"
  value       = var.create_static_bucket ? aws_s3_bucket.static[0].bucket_regional_domain_name : null
}

# All Bucket IDs
output "all_bucket_ids" {
  description = "Map of all bucket IDs"
  value = {
    data    = aws_s3_bucket.data.id
    models  = aws_s3_bucket.models.id
    logs    = aws_s3_bucket.logs.id
    backups = aws_s3_bucket.backups.id
    static  = var.create_static_bucket ? aws_s3_bucket.static[0].id : null
  }
}

# All Bucket ARNs
output "all_bucket_arns" {
  description = "Map of all bucket ARNs"
  value = {
    data    = aws_s3_bucket.data.arn
    models  = aws_s3_bucket.models.arn
    logs    = aws_s3_bucket.logs.arn
    backups = aws_s3_bucket.backups.arn
    static  = var.create_static_bucket ? aws_s3_bucket.static[0].arn : null
  }
}
