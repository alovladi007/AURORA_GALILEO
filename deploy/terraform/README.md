# GALILEO Terraform Infrastructure

Complete Infrastructure as Code for deploying GALILEO platform on AWS.

## Architecture Overview

This Terraform configuration deploys a production-ready, highly available infrastructure:

- **Network**: Multi-AZ VPC with public/private subnets, NAT gateways, VPC endpoints
- **Compute**: Amazon EKS cluster with multiple node groups (general, compute-intensive)
- **Database**: PostgreSQL RDS with Multi-AZ, read replicas, TimescaleDB support
- **Cache**: ElastiCache Redis cluster with automatic failover
- **Storage**: S3 buckets for data, models, logs, and backups with lifecycle policies
- **CDN**: CloudFront distribution with Origin Shield and security headers
- **Security**: KMS encryption, IAM roles with IRSA, network policies
- **Monitoring**: CloudWatch alarms, SNS notifications, centralized logging

## Directory Structure

```
deploy/terraform/
├── modules/
│   ├── vpc/              # VPC with subnets, NAT, endpoints
│   ├── eks/              # Kubernetes cluster with node groups
│   ├── rds/              # PostgreSQL database with replicas
│   ├── elasticache/      # Redis cache cluster
│   ├── s3/               # S3 buckets with lifecycle policies
│   └── cloudfront/       # CDN distribution
├── environments/
│   ├── prod/             # Production environment
│   ├── staging/          # Staging environment (create from prod)
│   └── dev/              # Development environment (create from prod)
└── README.md             # This file
```

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **Terraform** >= 1.5.0 ([Install](https://developer.hashicorp.com/terraform/downloads))
3. **AWS CLI** configured with credentials ([Install](https://aws.amazon.com/cli/))
4. **kubectl** for Kubernetes management ([Install](https://kubernetes.io/docs/tasks/tools/))
5. **S3 backend**: Create S3 bucket and DynamoDB table for state management

### Setting Up State Backend

```bash
# Create S3 bucket for Terraform state
aws s3 mb s3://galileo-terraform-state-prod --region us-east-1

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket galileo-terraform-state-prod \
  --versioning-configuration Status=Enabled

# Create DynamoDB table for state locking
aws dynamodb create-table \
  --table-name galileo-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5 \
  --region us-east-1
```

## Deployment Guide

### 1. Configure Variables

```bash
cd deploy/terraform/environments/prod
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

```hcl
aws_region          = "us-east-1"
redis_auth_token    = "$(openssl rand -base64 32)"
acm_certificate_arn = "arn:aws:acm:us-east-1:ACCOUNT:certificate/CERT_ID"
alarm_email         = "ops@example.com"
```

### 2. Create ACM Certificate (if needed)

CloudFront requires ACM certificate in `us-east-1`:

```bash
aws acm request-certificate \
  --domain-name galileo.example.com \
  --subject-alternative-names www.galileo.example.com \
  --validation-method DNS \
  --region us-east-1
```

### 3. Initialize Terraform

```bash
terraform init
```

### 4. Plan Deployment

```bash
terraform plan -out=tfplan
```

Review the plan carefully. Expected resources: ~150+

### 5. Apply Configuration

```bash
terraform apply tfplan
```

Deployment takes approximately 20-30 minutes.

### 6. Configure kubectl

```bash
aws eks update-kubeconfig --region us-east-1 --name galileo-prod-cluster
kubectl get nodes
```

### 7. Deploy Applications

```bash
# Deploy Helm charts
cd ../../../helm
helm install galileo ./galileo \
  --namespace default \
  --set database.host=$(terraform -chdir=../terraform/environments/prod output -raw rds_endpoint) \
  --set redis.host=$(terraform -chdir=../terraform/environments/prod output -raw redis_endpoint)
```

## Module Documentation

### VPC Module

Creates a production-ready VPC:

- Public subnets for load balancers
- Private subnets for applications
- NAT gateways (HA or single)
- VPC endpoints for S3 and DynamoDB
- VPC Flow Logs

**Usage:**

```hcl
module "vpc" {
  source = "../../modules/vpc"
  
  name_prefix            = "galileo-prod"
  vpc_cidr              = "10.0.0.0/16"
  availability_zones    = ["us-east-1a", "us-east-1b", "us-east-1c"]
  public_subnet_cidrs   = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  private_subnet_cidrs  = ["10.0.11.0/24", "10.0.12.0/24", "10.0.13.0/24"]
  enable_nat_gateway    = true
  single_nat_gateway    = false
}
```

### EKS Module

Managed Kubernetes cluster:

- Configurable node groups with labels and taints
- OIDC provider for IRSA
- KMS encryption for secrets
- CloudWatch logging
- EKS addons (VPC CNI, CoreDNS, kube-proxy, EBS CSI)

**Usage:**

```hcl
module "eks" {
  source = "../../modules/eks"
  
  name_prefix    = "galileo-prod"
  vpc_id         = module.vpc.vpc_id
  subnet_ids     = module.vpc.private_subnet_ids
  cluster_version = "1.28"
  
  node_groups = {
    general = {
      desired_capacity = 3
      min_capacity     = 3
      max_capacity     = 10
      instance_types   = ["t3.xlarge"]
    }
  }
}
```

### RDS Module

PostgreSQL with TimescaleDB:

- Multi-AZ with automatic failover
- Read replicas
- KMS encryption
- Performance Insights
- Enhanced Monitoring
- CloudWatch alarms

**Usage:**

```hcl
module "rds" {
  source = "../../modules/rds"
  
  name_prefix             = "galileo-prod"
  vpc_id                  = module.vpc.vpc_id
  subnet_ids              = module.vpc.private_subnet_ids
  instance_class          = "db.r6g.xlarge"
  allocated_storage       = 500
  multi_az               = true
  create_read_replica    = true
  read_replica_count     = 2
}
```

### ElastiCache Module

Redis cluster:

- Cluster mode enabled/disabled
- Multi-AZ with automatic failover
- Encryption at rest and in transit
- Auth token support
- CloudWatch alarms

**Usage:**

```hcl
module "elasticache" {
  source = "../../modules/elasticache"
  
  name_prefix            = "galileo-prod"
  vpc_id                 = module.vpc.vpc_id
  subnet_ids             = module.vpc.private_subnet_ids
  node_type              = "cache.r7g.large"
  cluster_mode_enabled   = false
  num_cache_clusters     = 3
  transit_encryption_enabled = true
  auth_token             = var.redis_auth_token
}
```

### S3 Module

Object storage buckets:

- Data bucket: Raw satellite data with lifecycle transitions
- Models bucket: ML artifacts with versioning
- Logs bucket: Application and access logs
- Backups bucket: Database backups with replication
- Static bucket: CDN assets

**Usage:**

```hcl
module "s3" {
  source = "../../modules/s3"
  
  name_prefix            = "galileo-prod"
  environment            = "prod"
  create_kms_key        = true
  logs_retention_days    = 365
  backups_retention_days = 2555  # 7 years
}
```

### CloudFront Module

CDN distribution:

- Origin Access Control for S3
- Custom SSL/TLS certificates
- Security headers
- CloudFront Functions for URL rewriting
- WAF integration
- CloudWatch alarms

**Usage:**

```hcl
module "cloudfront" {
  source = "../../modules/cloudfront"
  
  name_prefix                    = "galileo-prod"
  s3_bucket_id                   = module.s3.static_bucket_id
  s3_bucket_regional_domain_name = module.s3.static_bucket_regional_domain_name
  acm_certificate_arn            = var.acm_certificate_arn
  aliases                        = ["galileo.example.com"]
}
```

## Cost Estimates

### Monthly Costs (Production)

| Service | Configuration | Monthly Cost |
|---------|--------------|--------------|
| EKS Cluster | 1 cluster | $73 |
| EC2 (Nodes) | 3x t3.xlarge + 2x c6i.2xlarge | ~$800 |
| RDS | db.r6g.xlarge Multi-AZ + 2 replicas | ~$1,200 |
| ElastiCache | 3x cache.r7g.large | ~$450 |
| S3 | 5TB storage + requests | ~$150 |
| CloudFront | 1TB transfer | ~$85 |
| NAT Gateway | 3 gateways | ~$100 |
| Data Transfer | Various | ~$100 |
| **Total** | | **~$2,958/month** |

*Costs vary by region, usage, and configuration. Use AWS Cost Calculator for accurate estimates.*

## Scaling Recommendations

### Development Environment

- Single NAT gateway
- EKS: 2x t3.large nodes
- RDS: db.t3.large, no replicas
- Redis: 2x cache.t4g.medium
- **Estimated cost: ~$600/month**

### Staging Environment

- Single NAT gateway
- EKS: 2x t3.xlarge nodes
- RDS: db.r6g.large Multi-AZ, 1 replica
- Redis: 2x cache.r7g.medium
- **Estimated cost: ~$1,200/month**

### Production (High Traffic)

- Multi-AZ NAT gateways
- EKS: 5x c6i.2xlarge + autoscaling
- RDS: db.r6g.2xlarge Multi-AZ, 3 replicas
- Redis: 5x cache.r7g.xlarge cluster mode
- **Estimated cost: ~$5,000-8,000/month**

## Security Best Practices

1. **Secrets Management**
   - Store sensitive values in AWS Secrets Manager
   - Use IAM roles with IRSA instead of access keys
   - Rotate credentials regularly

2. **Network Security**
   - Deploy applications in private subnets
   - Use security groups as firewalls
   - Enable VPC Flow Logs
   - Implement network policies in Kubernetes

3. **Encryption**
   - Enable encryption at rest (KMS)
   - Enable encryption in transit (TLS)
   - Use separate KMS keys per environment

4. **Access Control**
   - Follow principle of least privilege
   - Use IAM roles for service accounts
   - Enable MFA for admin access
   - Audit access with CloudTrail

5. **Monitoring**
   - Set up CloudWatch alarms
   - Configure SNS notifications
   - Enable detailed logging
   - Use AWS Security Hub

## Maintenance

### Backup Strategy

- RDS: Automated daily backups, 30-day retention
- S3: Versioning enabled, lifecycle policies
- Redis: Daily snapshots, 7-day retention

### Update Strategy

1. **Kubernetes**: Update node groups with blue/green deployment
2. **RDS**: Apply during maintenance windows
3. **Terraform**: Test in dev → staging → production

### Disaster Recovery

- RTO: 4 hours
- RPO: 24 hours
- Multi-region replication for backups
- Documented runbooks for recovery

## Troubleshooting

### EKS Cluster Not Accessible

```bash
# Update kubeconfig
aws eks update-kubeconfig --region us-east-1 --name galileo-prod-cluster

# Verify AWS credentials
aws sts get-caller-identity

# Check cluster status
aws eks describe-cluster --name galileo-prod-cluster --region us-east-1
```

### RDS Connection Issues

```bash
# Test connectivity from EKS node
kubectl run -it --rm debug --image=postgres:15 --restart=Never -- \
  psql -h <RDS_ENDPOINT> -U galileo_admin -d galileo

# Check security groups
aws ec2 describe-security-groups --group-ids <SG_ID>
```

### Terraform State Lock

```bash
# If state is locked and stuck
aws dynamodb delete-item \
  --table-name galileo-terraform-locks \
  --key '{"LockID":{"S":"galileo-terraform-state-prod/prod/terraform.tfstate"}}'
```

## Support

- **Documentation**: `docs/`
- **Issues**: GitHub Issues
- **Slack**: #galileo-infrastructure

## License

Copyright © 2024 GALILEO Platform Team
