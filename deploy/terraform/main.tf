# GALILEO Platform - Main Terraform Configuration
# Infrastructure as Code for AWS deployment

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.11"
    }
  }

  backend "s3" {
    bucket         = "galileo-terraform-state"
    key            = "production/terraform.tfstate"
    region         = "us-west-2"
    encrypt        = true
    dynamodb_table = "galileo-terraform-locks"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "GALILEO"
      Environment = var.environment
      ManagedBy   = "Terraform"
      Owner       = var.owner_email
    }
  }
}

# Local variables
locals {
  name_prefix = "galileo-${var.environment}"
  common_tags = {
    Project     = "GALILEO"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# VPC Module
module "vpc" {
  source = "./modules/vpc"

  name_prefix         = local.name_prefix
  vpc_cidr            = var.vpc_cidr
  availability_zones  = var.availability_zones
  private_subnets     = var.private_subnets
  public_subnets      = var.public_subnets
  enable_nat_gateway  = true
  single_nat_gateway  = var.environment != "production"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = local.common_tags
}

# EKS Cluster Module
module "eks" {
  source = "./modules/eks"

  cluster_name    = "${local.name_prefix}-cluster"
  cluster_version = var.eks_cluster_version
  vpc_id          = module.vpc.vpc_id
  subnet_ids      = module.vpc.private_subnets

  # Node groups
  node_groups = {
    general = {
      desired_size = var.eks_general_nodes_desired
      min_size     = var.eks_general_nodes_min
      max_size     = var.eks_general_nodes_max
      instance_types = ["t3.xlarge"]
      capacity_type  = "ON_DEMAND"
      labels = {
        workload = "general"
      }
    }

    compute = {
      desired_size = var.eks_compute_nodes_desired
      min_size     = var.eks_compute_nodes_min
      max_size     = var.eks_compute_nodes_max
      instance_types = ["c5.2xlarge"]
      capacity_type  = "SPOT"
      labels = {
        workload = "compute"
      }
      taints = [{
        key    = "workload"
        value  = "compute"
        effect = "NoSchedule"
      }]
    }
  }

  tags = local.common_tags
}

# RDS PostgreSQL Module
module "rds" {
  source = "./modules/rds"

  identifier              = "${local.name_prefix}-db"
  engine_version          = "15.4"
  instance_class          = var.rds_instance_class
  allocated_storage       = var.rds_allocated_storage
  max_allocated_storage   = var.rds_max_allocated_storage

  database_name           = var.database_name
  master_username         = var.database_username

  vpc_id                  = module.vpc.vpc_id
  subnet_ids              = module.vpc.private_subnets
  allowed_security_groups = [module.eks.cluster_security_group_id]

  backup_retention_period = var.environment == "production" ? 30 : 7
  backup_window          = "03:00-04:00"
  maintenance_window     = "mon:04:00-mon:05:00"

  multi_az               = var.environment == "production"
  deletion_protection    = var.environment == "production"

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  create_read_replica    = var.environment == "production"
  read_replica_count     = var.environment == "production" ? 2 : 0

  tags = local.common_tags
}

# ElastiCache Redis Module
module "redis" {
  source = "./modules/redis"

  cluster_id          = "${local.name_prefix}-redis"
  engine_version      = "7.0"
  node_type           = var.redis_node_type
  num_cache_nodes     = var.environment == "production" ? 3 : 1

  vpc_id              = module.vpc.vpc_id
  subnet_ids          = module.vpc.private_subnets
  allowed_security_groups = [module.eks.cluster_security_group_id]

  automatic_failover_enabled = var.environment == "production"
  multi_az_enabled           = var.environment == "production"

  snapshot_retention_limit = var.environment == "production" ? 7 : 1
  snapshot_window         = "03:00-05:00"
  maintenance_window      = "mon:05:00-mon:07:00"

  tags = local.common_tags
}

# S3 Buckets Module
module "s3" {
  source = "./modules/s3"

  name_prefix = local.name_prefix

  buckets = {
    data = {
      versioning = true
      lifecycle_rules = [
        {
          id      = "transition-old-data"
          enabled = true
          transition = [
            {
              days          = 90
              storage_class = "STANDARD_IA"
            },
            {
              days          = 180
              storage_class = "GLACIER"
            }
          ]
        }
      ]
    }

    processed = {
      versioning = true
      lifecycle_rules = [
        {
          id      = "delete-old-processed"
          enabled = true
          expiration = {
            days = 365
          }
        }
      ]
    }

    backups = {
      versioning = true
      lifecycle_rules = []
    }

    models = {
      versioning = true
      lifecycle_rules = []
    }
  }

  tags = local.common_tags
}

# CloudFront CDN for UI
resource "aws_cloudfront_distribution" "ui" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "GALILEO UI Distribution"
  default_root_object = "index.html"

  origin {
    domain_name = module.eks.cluster_endpoint
    origin_id   = "galileo-ui"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "galileo-ui"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 3600
    max_ttl                = 86400
    compress               = true
  }

  price_class = var.cloudfront_price_class

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
    # Use ACM certificate for custom domain:
    # acm_certificate_arn      = aws_acm_certificate.ui.arn
    # ssl_support_method       = "sni-only"
    # minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = local.common_tags
}

# Outputs
output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "eks_cluster_endpoint" {
  description = "EKS cluster endpoint"
  value       = module.eks.cluster_endpoint
}

output "eks_cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "rds_endpoint" {
  description = "RDS endpoint"
  value       = module.rds.endpoint
  sensitive   = true
}

output "redis_endpoint" {
  description = "Redis endpoint"
  value       = module.redis.endpoint
  sensitive   = true
}

output "s3_bucket_names" {
  description = "S3 bucket names"
  value       = module.s3.bucket_names
}

output "cloudfront_domain" {
  description = "CloudFront distribution domain"
  value       = aws_cloudfront_distribution.ui.domain_name
}
