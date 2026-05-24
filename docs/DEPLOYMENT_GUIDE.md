# GALILEO V2.0 - Production Deployment Guide

## Overview

This guide provides step-by-step instructions for deploying GALILEO to production environments.

---

## Prerequisites

### Infrastructure Requirements

**Minimum (Small Deployment - 100 users)**
- 4 CPU cores, 16 GB RAM
- 200 GB SSD storage
- 100 Mbps network

**Recommended (Production - 1000+ users)**
- Kubernetes cluster (EKS, GKE, or AKS)
- 16+ CPU cores, 64+ GB RAM
- 1 TB SSD storage
- 1 Gbps network
- Load balancer
- CDN for UI assets

### Software Requirements
- Docker 24.0+
- Docker Compose 2.20+ (for standalone)
- Kubernetes 1.28+ (for cluster)
- Helm 3.12+ (for Kubernetes)
- Terraform 1.5+ (for IaC)
- AWS CLI / gcloud / az CLI

### Domain & SSL
- Registered domain name
- DNS management access
- Email for Let's Encrypt notifications

---

## Deployment Options

### Option 1: Docker Compose (Single Server)

**Best for**: Development, staging, small deployments

```bash
# 1. Clone repository
git clone https://github.com/alovladi007/AURORA_GALILEO.git
cd AURORA_GALILEO

# 2. Generate secrets
./scripts/generate-secrets.sh

# 3. Configure environment
cp .env.example .env
nano .env  # Edit with your values

# 4. Start services
docker-compose up -d

# 5. Start MLOps services (optional)
docker-compose -f mlops/mlflow/docker-compose.mlflow.yml up -d

# 6. Verify deployment
curl http://localhost:5050/health
```

### Option 2: Kubernetes with Helm

**Best for**: Production, high availability, auto-scaling

```bash
# 1. Provision infrastructure with Terraform
cd deploy/terraform
terraform init
terraform plan -out=tfplan
terraform apply tfplan

# 2. Configure kubectl
aws eks update-kubeconfig --name galileo-production-cluster --region us-west-2

# 3. Install dependencies
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# 4. Create secrets
kubectl create namespace galileo
kubectl create secret generic galileo-secrets \
  --from-literal=database-url="postgresql://..." \
  --from-literal=redis-url="redis://..." \
  --from-literal=jwt-secret-key="$(openssl rand -hex 32)" \
  --from-literal=secret-key="$(openssl rand -hex 32)" \
  -n galileo

# 5. Deploy with Helm
cd deploy/helm
helm install galileo ./galileo \
  --namespace galileo \
  --values values-production.yaml \
  --wait

# 6. Verify deployment
kubectl get pods -n galileo
kubectl get svc -n galileo
```

### Option 3: Managed Services (AWS)

**Best for**: Maximum reliability, minimal ops overhead

Uses managed services:
- Amazon EKS (Kubernetes)
- Amazon RDS (PostgreSQL)
- Amazon ElastiCache (Redis)
- Amazon S3 (Object storage)
- Amazon CloudFront (CDN)

See `deploy/terraform/main.tf` for full configuration.

---

## Environment Configuration

### Required Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:password@host:5432/dbname
DATABASE_USER=galileo
DATABASE_PASSWORD=<strong-password>
DATABASE_NAME=galileo

# Redis
REDIS_URL=redis://host:6379/0
REDIS_PASSWORD=<strong-password>

# MinIO / S3
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=<access-key>
MINIO_SECRET_KEY=<secret-key>
MINIO_SECURE=true  # HTTPS

# Application Secrets
JWT_SECRET_KEY=<32+ character random string>
SECRET_KEY=<32+ character random string>
NEXTAUTH_SECRET=<32+ character random string>

# API Configuration
ENVIRONMENT=production
LOG_LEVEL=INFO
CORS_ORIGINS=https://galileo.example.com
REQUEST_TIMEOUT_SECONDS=30
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=100

# SSL/TLS
DOMAIN=galileo.example.com
LETSENCRYPT_EMAIL=admin@example.com
LETSENCRYPT_STAGING=0  # 0 for production, 1 for testing

# Monitoring
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
GRAFANA_ADMIN_PASSWORD=<strong-password>

# ML/MLOps
MLFLOW_TRACKING_URI=http://mlflow:5000
AIRFLOW_FERNET_KEY=<generated-key>
AIRFLOW_WEBSERVER_SECRET_KEY=<generated-key>
```

### Generating Secrets

```bash
#!/bin/bash
# Generate secure random secrets

echo "JWT_SECRET_KEY=$(openssl rand -hex 32)"
echo "SECRET_KEY=$(openssl rand -hex 32)"
echo "NEXTAUTH_SECRET=$(openssl rand -hex 32)"
echo "MINIO_ACCESS_KEY=$(openssl rand -hex 16)"
echo "MINIO_SECRET_KEY=$(openssl rand -hex 32)"
echo "AIRFLOW_FERNET_KEY=$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

---

## SSL/TLS Setup

### Automated with Let's Encrypt

```bash
# 1. Ensure DNS points to your server
dig galileo.example.com

# 2. Run Let's Encrypt setup script
sudo ./scripts/setup-letsencrypt.sh

# 3. Verify certificate
sudo openssl x509 -in /etc/nginx/ssl/fullchain.pem -noout -text

# 4. Test SSL configuration
curl -I https://galileo.example.com

# 5. Check SSL rating
# Visit: https://www.ssllabs.com/ssltest/
```

### Manual Certificate Installation

```bash
# 1. Copy certificates
sudo cp fullchain.pem /etc/nginx/ssl/
sudo cp privkey.pem /etc/nginx/ssl/
sudo cp chain.pem /etc/nginx/ssl/

# 2. Set permissions
sudo chmod 644 /etc/nginx/ssl/fullchain.pem
sudo chmod 644 /etc/nginx/ssl/chain.pem
sudo chmod 600 /etc/nginx/ssl/privkey.pem

# 3. Update nginx configuration
sudo cp ops/nginx/nginx-tls.conf /etc/nginx/nginx.conf
sudo nginx -t
sudo systemctl reload nginx
```

---

## Database Setup

### PostgreSQL Initialization

```bash
# 1. Create databases
psql -U postgres <<EOF
CREATE DATABASE galileo;
CREATE DATABASE mlflow;
CREATE DATABASE feast;
CREATE DATABASE airflow;

CREATE USER galileo_admin WITH PASSWORD 'strong-password';
GRANT ALL PRIVILEGES ON DATABASE galileo TO galileo_admin;
GRANT ALL PRIVILEGES ON DATABASE mlflow TO galileo_admin;
GRANT ALL PRIVILEGES ON DATABASE feast TO galileo_admin;
GRANT ALL PRIVILEGES ON DATABASE airflow TO galileo_admin;
EOF

# 2. Run migrations
cd ops
alembic upgrade head

# 3. Enable TimescaleDB (optional, for time-series data)
psql -U postgres -d galileo -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"

# 4. Create hypertables
psql -U postgres -d galileo <<EOF
SELECT create_hypertable('sensor_data', 'timestamp');
SELECT add_retention_policy('sensor_data', INTERVAL '1 year');
EOF
```

### Database Backup & Restore

```bash
# Manual backup
./scripts/backup-db.sh

# Restore from backup
gunzip -c /backups/galileo_backup_20240101_120000.sql.gz | \
  psql -U galileo -d galileo

# List backups
ls -lh /backups/

# Automated backups (already configured via docker-compose)
# Check db-backup service logs
docker logs galileo-db-backup
```

---

## Monitoring Setup

### Access Monitoring Dashboards

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3003 (admin / galileo_admin)
- **AlertManager**: http://localhost:9093
- **Jaeger**: http://localhost:16686

### Configure Alerts

```bash
# 1. Update Slack webhook
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."

# 2. Test alerts
docker exec galileo-prometheus promtool check rules \
  /etc/prometheus/alert-rules.yml

# 3. Trigger test alert
curl -X POST http://localhost:9093/api/v1/alerts \
  -H 'Content-Type: application/json' \
  -d '[{"labels": {"alertname":"TestAlert","severity":"warning"}}]'
```

### Import Grafana Dashboards

1. Open Grafana (http://localhost:3003)
2. Navigate to Dashboards → Import
3. Upload `monitoring/grafana/dashboards/galileo-slo-dashboard.json`
4. Select Prometheus datasource
5. Click Import

---

## Load Testing

### Run k6 Load Tests

```bash
# Install k6
brew install k6  # macOS
# OR
sudo apt install k6  # Ubuntu

# Baseline test (10 users, 5 minutes)
k6 run --vus 10 --duration 5m tests/load/k6-load-test.js

# Stress test
k6 run --env SCENARIO=stress tests/load/k6-load-test.js

# Spike test
k6 run --env SCENARIO=spike tests/load/k6-load-test.js

# Soak test (2 hours)
k6 run --env SCENARIO=soak tests/load/k6-load-test.js

# View results
cat summary.json | jq .
```

---

## Security Hardening

### Enable Security Features

```bash
# 1. Enable CSRF protection (already integrated in code)
# Verify in api/csrf.py

# 2. Configure file upload limits
# Edit .env:
MAX_FILE_SIZE_MB=100

# 3. Setup firewall
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable

# 4. Enable fail2ban
sudo apt install fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### Security Scanning

```bash
# Dependency scan
pip-audit -r requirements.txt

# Container scan
docker scout cves galileo-api:latest
# OR
trivy image galileo-api:latest

# Secret scan
gitleaks detect --source . --verbose

# OWASP ZAP scan
docker run -t owasp/zap2docker-stable zap-baseline.py \
  -t https://galileo.example.com
```

---

## Troubleshooting

### Common Issues

**Issue: Database connection failed**
```bash
# Check database is running
docker ps | grep postgres

# Check connection
psql -U galileo -h localhost -d galileo

# View logs
docker logs galileo-postgres
```

**Issue: High memory usage**
```bash
# Check resource usage
docker stats

# Restart specific service
docker-compose restart api

# Adjust resource limits in docker-compose.yml
```

**Issue: SSL certificate renewal failed**
```bash
# Test renewal
sudo certbot renew --dry-run

# Check timer status
sudo systemctl status galileo-cert-renew.timer

# Manual renewal
sudo certbot renew --force-renewal
```

**Issue: Slow API responses**
```bash
# Check Prometheus metrics
curl http://localhost:9090/api/v1/query?query=http_req_duration_p99

# View slow queries
docker exec galileo-postgres psql -U galileo -c \
  "SELECT * FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;"

# Enable query logging
# Edit postgresql.conf:
log_min_duration_statement = 1000  # Log queries > 1s
```

---

## Maintenance

### Regular Tasks

**Daily**
- Monitor error rates in Grafana
- Check AlertManager for active alerts
- Review backup status

**Weekly**
- Review security scan results
- Update dependencies (if needed)
- Analyze slow query logs

**Monthly**
- Database vacuum and analyze
- Review and archive old logs
- Capacity planning review
- Security updates

### Scaling

**Horizontal Scaling (Kubernetes)**
```bash
# Scale API pods
kubectl scale deployment galileo-api --replicas=10 -n galileo

# Scale workers
kubectl scale deployment galileo-worker --replicas=20 -n galileo

# Auto-scaling is configured in values.yaml
```

**Vertical Scaling**
```bash
# Edit values.yaml
api:
  resources:
    limits:
      cpu: 4000m
      memory: 8Gi

# Upgrade deployment
helm upgrade galileo ./galileo -n galileo
```

---

## Disaster Recovery

### Backup Strategy

**What to backup:**
- PostgreSQL database (daily, retain 30 days)
- Redis data (daily, retain 7 days)
- MinIO buckets (weekly, retain 90 days)
- Secrets and configuration (version controlled)

**Backup location:**
- Primary: S3 bucket with versioning
- Secondary: Offsite backup (different region)

### Recovery Procedures

**Scenario 1: Database corruption**
```bash
# 1. Stop application
docker-compose stop api ops-api worker

# 2. Restore from latest backup
gunzip -c /backups/latest.sql.gz | psql -U galileo -d galileo

# 3. Verify data integrity
psql -U galileo -d galileo -c "SELECT COUNT(*) FROM jobs;"

# 4. Restart application
docker-compose start api ops-api worker
```

**Scenario 2: Complete system failure**
```bash
# 1. Provision new infrastructure
cd deploy/terraform
terraform apply

# 2. Restore from backups
./scripts/restore-all.sh s3://galileo-backups/latest/

# 3. Deploy application
helm install galileo ./galileo -n galileo

# 4. Verify services
kubectl get pods -n galileo
```

---

## Production Checklist

### Pre-Launch

- [ ] All secrets generated and stored securely
- [ ] SSL certificates configured and tested
- [ ] Database migrations completed
- [ ] Environment variables configured
- [ ] Monitoring dashboards configured
- [ ] Alerts configured and tested
- [ ] Backups configured and tested
- [ ] Load testing passed (p99 < 500ms, error rate < 1%)
- [ ] Security scanning passed
- [ ] Documentation reviewed
- [ ] DNS configured
- [ ] Firewall rules configured

### Post-Launch

- [ ] Monitor error rates (< 0.1%)
- [ ] Monitor latency (p99 < 500ms)
- [ ] Verify backups running
- [ ] Check SSL certificate auto-renewal
- [ ] Review CloudWatch/Prometheus metrics
- [ ] Test disaster recovery procedures
- [ ] Update runbooks
- [ ] Schedule regular maintenance windows

---

## Support

- **Documentation**: /docs
- **Issues**: https://github.com/alovladi007/AURORA_GALILEO/issues
- **Email**: admin@galileo.example.com
- **Slack**: #galileo-support

---

**Last Updated**: 2026-05-24  
**Version**: 2.0.0
