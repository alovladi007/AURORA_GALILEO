# GALILEO Production Infrastructure
# Complete Terraform configuration using all modules

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }

  backend "s3" {
    bucket         = "galileo-terraform-state-prod"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "galileo-terraform-locks"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "GALILEO"
      Environment = "production"
      ManagedBy   = "Terraform"
      Owner       = "Platform Team"
    }
  }
}

# Data sources
data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

# Local variables
locals {
  name_prefix = "galileo-prod"
  vpc_cidr    = "10.0.0.0/16"

  azs = slice(data.aws_availability_zones.available.names, 0, 3)

  tags = {
    Project     = "GALILEO"
    Environment = "production"
    Terraform   = "true"
  }
}

# VPC Module
module "vpc" {
  source = "../../modules/vpc"

  name_prefix = local.name_prefix
  vpc_cidr    = local.vpc_cidr

  availability_zones = local.azs

  public_subnet_cidrs  = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  private_subnet_cidrs = ["10.0.11.0/24", "10.0.12.0/24", "10.0.13.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = false  # HA with NAT per AZ

  enable_dns_hostnames = true
  enable_dns_support   = true

  enable_flow_logs           = true
  flow_logs_retention_days   = 30

  enable_vpc_endpoints = true

  tags = local.tags
}

# EKS Module
module "eks" {
  source = "../../modules/eks"

  name_prefix = local.name_prefix
  vpc_id      = module.vpc.vpc_id
  subnet_ids  = module.vpc.private_subnet_ids

  cluster_version = "1.28"

  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true

  cluster_encryption_config_enabled = true

  # Node groups
  node_groups = {
    general = {
      desired_capacity = 3
      min_capacity     = 3
      max_capacity     = 10
      instance_types   = ["t3.xlarge", "t3a.xlarge"]
      capacity_type    = "ON_DEMAND"
      disk_size        = 100
      labels = {
        workload = "general"
      }
    }

    compute = {
      desired_capacity = 2
      min_capacity     = 2
      max_capacity     = 20
      instance_types   = ["c6i.2xlarge", "c6a.2xlarge"]
      capacity_type    = "SPOT"
      disk_size        = 200
      labels = {
        workload = "compute-intensive"
      }
      taints = [{
        key    = "workload"
        value  = "compute"
        effect = "NO_SCHEDULE"
      }]
    }
  }

  manage_aws_auth_configmap = true

  tags = local.tags
}

# RDS Module
module "rds" {
  source = "../../modules/rds"

  name_prefix = local.name_prefix
  vpc_id      = module.vpc.vpc_id
  subnet_ids  = module.vpc.private_subnet_ids

  allowed_security_groups = [module.eks.cluster_security_group_id]

  instance_class    = "db.r6g.xlarge"
  allocated_storage = 500
  max_allocated_storage = 2000

  multi_az = true

  database_name = "galileo"
  username      = "galileo_admin"

  backup_retention_period = 30
  backup_window          = "03:00-04:00"
  maintenance_window     = "sun:04:00-sun:05:00"

  deletion_protection       = true
  skip_final_snapshot      = false
  copy_tags_to_snapshot    = true

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  monitoring_interval = 60
  monitoring_role_name = "${local.name_prefix}-rds-monitoring"

  performance_insights_enabled = true
  performance_insights_retention_period = 7

  create_read_replica = true
  read_replica_count  = 2

  tags = local.tags
}

# ElastiCache Module
module "elasticache" {
  source = "../../modules/elasticache"

  name_prefix = local.name_prefix
  vpc_id      = module.vpc.vpc_id
  subnet_ids  = module.vpc.private_subnet_ids

  allowed_security_groups = [module.eks.cluster_security_group_id]

  node_type      = "cache.r7g.large"
  engine_version = "7.0"

  cluster_mode_enabled = false
  num_cache_clusters   = 3

  automatic_failover_enabled = true
  multi_az_enabled          = true

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                = var.redis_auth_token

  snapshot_retention_limit = 7
  snapshot_window         = "03:00-05:00"
  maintenance_window      = "sun:05:00-sun:07:00"

  maxmemory_policy = "allkeys-lru"

  tags = local.tags
}

# S3 Buckets Module
module "s3" {
  source = "../../modules/s3"

  name_prefix = local.name_prefix
  environment = "prod"

  create_kms_key = true

  logs_retention_days    = 365
  backups_retention_days = 2555  # 7 years

  enable_logging = true

  create_static_bucket = true
  cors_allowed_origins = ["https://galileo.example.com"]

  tags = local.tags
}

# CloudFront Module
module "cloudfront" {
  source = "../../modules/cloudfront"

  name_prefix = local.name_prefix

  s3_bucket_id                     = module.s3.static_bucket_id
  s3_bucket_regional_domain_name   = module.s3.static_bucket_regional_domain_name

  price_class = "PriceClass_All"
  aliases     = ["galileo.example.com", "www.galileo.example.com"]

  origin_shield_enabled = true
  origin_shield_region  = var.aws_region

  api_domain_name = module.eks.cluster_endpoint

  acm_certificate_arn = var.acm_certificate_arn

  logging_bucket = module.s3.logs_bucket_domain_name
  logging_prefix = "cdn-logs/"

  cors_allowed_origins = ["https://galileo.example.com"]

  tags = local.tags
}

# SNS Topic for Alarms
resource "aws_sns_topic" "alarms" {
  name              = "${local.name_prefix}-alarms"
  display_name      = "GALILEO Production Alarms"
  kms_master_key_id = module.s3.kms_key_id

  tags = local.tags
}

resource "aws_sns_topic_subscription" "alarms_email" {
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

# IAM Role for EKS Service Accounts
resource "aws_iam_role" "eks_service_account" {
  name = "${local.name_prefix}-eks-service-account"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = module.eks.oidc_provider_arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${module.eks.oidc_provider}:sub" = "system:serviceaccount:default:galileo-api"
            "${module.eks.oidc_provider}:aud" = "sts.amazonaws.com"
          }
        }
      }
    ]
  })

  tags = local.tags
}

# IAM Policy for S3 Access
resource "aws_iam_policy" "s3_access" {
  name        = "${local.name_prefix}-s3-access"
  description = "Policy for GALILEO services to access S3 buckets"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          module.s3.data_bucket_arn,
          "${module.s3.data_bucket_arn}/*",
          module.s3.models_bucket_arn,
          "${module.s3.models_bucket_arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject"
        ]
        Resource = [
          module.s3.backups_bucket_arn,
          "${module.s3.backups_bucket_arn}/*"
        ]
      }
    ]
  })

  tags = local.tags
}

resource "aws_iam_role_policy_attachment" "service_account_s3" {
  role       = aws_iam_role.eks_service_account.name
  policy_arn = aws_iam_policy.s3_access.arn
}

# Secrets Manager for Database Credentials
resource "aws_secretsmanager_secret" "db_credentials" {
  name                    = "${local.name_prefix}-db-credentials"
  description             = "Database credentials for GALILEO"
  recovery_window_in_days = 30
  kms_key_id             = module.s3.kms_key_id

  tags = local.tags
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = module.rds.master_username
    password = module.rds.master_password
    endpoint = module.rds.endpoint
    port     = module.rds.port
    database = module.rds.database_name
  })
}

# CloudWatch Log Group for Application Logs
resource "aws_cloudwatch_log_group" "app_logs" {
  name              = "/aws/eks/${local.name_prefix}/applications"
  retention_in_days = 30
  kms_key_id       = module.s3.kms_key_id

  tags = local.tags
}

# Output summary for deployment
output "deployment_summary" {
  description = "Summary of deployed infrastructure"
  value = {
    vpc_id             = module.vpc.vpc_id
    eks_cluster_name   = module.eks.cluster_name
    eks_endpoint       = module.eks.cluster_endpoint
    rds_endpoint       = module.rds.endpoint
    redis_endpoint     = module.elasticache.primary_endpoint_address
    cdn_domain         = module.cloudfront.distribution_domain_name
    s3_data_bucket     = module.s3.data_bucket_id
    s3_models_bucket   = module.s3.models_bucket_id
    s3_backups_bucket  = module.s3.backups_bucket_id
  }
}
