# Outputs for Production Environment

# Network Outputs
output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "vpc_cidr" {
  description = "VPC CIDR block"
  value       = module.vpc.vpc_cidr_block
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = module.vpc.private_subnet_ids
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = module.vpc.public_subnet_ids
}

# EKS Outputs
output "eks_cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "EKS cluster endpoint"
  value       = module.eks.cluster_endpoint
}

output "eks_cluster_security_group_id" {
  description = "EKS cluster security group ID"
  value       = module.eks.cluster_security_group_id
}

output "eks_cluster_certificate_authority_data" {
  description = "EKS cluster certificate authority data"
  value       = module.eks.cluster_certificate_authority_data
  sensitive   = true
}

output "configure_kubectl" {
  description = "Command to configure kubectl"
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.eks.cluster_name}"
}

# Database Outputs
output "rds_endpoint" {
  description = "RDS endpoint"
  value       = module.rds.endpoint
}

output "rds_reader_endpoint" {
  description = "RDS reader endpoint"
  value       = module.rds.reader_endpoint
}

output "rds_port" {
  description = "RDS port"
  value       = module.rds.port
}

output "rds_database_name" {
  description = "RDS database name"
  value       = module.rds.database_name
}

output "rds_master_username" {
  description = "RDS master username"
  value       = module.rds.master_username
  sensitive   = true
}

output "rds_secret_arn" {
  description = "Secrets Manager ARN for RDS credentials"
  value       = module.rds.secret_arn
}

# Redis Outputs
output "redis_endpoint" {
  description = "Redis primary endpoint"
  value       = module.elasticache.primary_endpoint_address
}

output "redis_port" {
  description = "Redis port"
  value       = module.elasticache.port
}

output "redis_connection_string" {
  description = "Redis connection string"
  value       = module.elasticache.connection_string
  sensitive   = true
}

# S3 Outputs
output "s3_data_bucket" {
  description = "S3 data bucket name"
  value       = module.s3.data_bucket_id
}

output "s3_models_bucket" {
  description = "S3 models bucket name"
  value       = module.s3.models_bucket_id
}

output "s3_logs_bucket" {
  description = "S3 logs bucket name"
  value       = module.s3.logs_bucket_id
}

output "s3_backups_bucket" {
  description = "S3 backups bucket name"
  value       = module.s3.backups_bucket_id
}

output "s3_static_bucket" {
  description = "S3 static assets bucket name"
  value       = module.s3.static_bucket_id
}

output "s3_kms_key_id" {
  description = "KMS key ID for S3 encryption"
  value       = module.s3.kms_key_id
}

# CloudFront Outputs
output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = module.cloudfront.distribution_id
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name"
  value       = module.cloudfront.distribution_domain_name
}

output "cloudfront_hosted_zone_id" {
  description = "CloudFront hosted zone ID for Route 53"
  value       = module.cloudfront.distribution_hosted_zone_id
}

# IAM Outputs
output "eks_service_account_role_arn" {
  description = "IAM role ARN for EKS service accounts"
  value       = aws_iam_role.eks_service_account.arn
}

# Monitoring Outputs
output "sns_alarms_topic_arn" {
  description = "SNS topic ARN for alarms"
  value       = aws_sns_topic.alarms.arn
}

output "app_logs_log_group" {
  description = "CloudWatch log group for application logs"
  value       = aws_cloudwatch_log_group.app_logs.name
}

# Connection Information
output "connection_info" {
  description = "Connection information for all services"
  value = {
    kubernetes = {
      configure = "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.eks.cluster_name}"
      endpoint  = module.eks.cluster_endpoint
    }
    database = {
      host     = split(":", module.rds.endpoint)[0]
      port     = module.rds.port
      database = module.rds.database_name
      username = module.rds.master_username
      secret   = module.rds.secret_arn
    }
    redis = {
      endpoint = module.elasticache.primary_endpoint_address
      port     = module.elasticache.port
    }
    cdn = {
      domain = module.cloudfront.distribution_domain_name
    }
    storage = {
      data    = "s3://${module.s3.data_bucket_id}"
      models  = "s3://${module.s3.models_bucket_id}"
      backups = "s3://${module.s3.backups_bucket_id}"
    }
  }
  sensitive = true
}
