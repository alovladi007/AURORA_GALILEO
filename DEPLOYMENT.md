# GALILEO V2.0 - Production Deployment Guide

Complete guide for deploying GALILEO V2.0 in production environments.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Configuration](#environment-configuration)
3. [Docker Deployment](#docker-deployment)
4. [Manual Deployment](#manual-deployment)
5. [Database Setup](#database-setup)
6. [Monitoring Setup](#monitoring-setup)
7. [Security Checklist](#security-checklist)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

- **Docker** 20.10+ and **Docker Compose** 2.0+
- **Python** 3.11+
- **Node.js** 18+ (for UI)
- **PostgreSQL** 14+ with TimescaleDB extension
- **Redis** 7+

### Hardware Requirements

**Minimum (Development)**:
- 4 CPU cores
- 8 GB RAM
- 50 GB disk space

**Recommended (Production)**:
- 8+ CPU cores
- 16+ GB RAM
- 200+ GB SSD storage
- GPU (optional, for ML workloads)

---

## Environment Configuration

### Step 1: Copy Environment Template

```bash
cp .env.example .env
```

### Step 2: Generate Secrets

Generate secure secrets for production:

```bash
# Generate JWT secret key (64 characters)
python3 -c "import secrets; print(secrets.token_urlsafe(64))"

# Generate NextAuth secret
python3 -c "import secrets; print(secrets.token_hex(32))"

# Generate strong passwords
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Step 3: Configure Environment Variables

Edit `.env` with your production values:

```bash
# ============================================================================
# REQUIRED - Must be changed for production
# ============================================================================

# Database
DATABASE_PASSWORD=<your-secure-database-password>

# Security
JWT_SECRET_KEY=<64-char-secret-from-step-2>
NEXTAUTH_SECRET=<nextauth-secret-from-step-2>

# MinIO
MINIO_SECRET_KEY=<secure-random-key>

# Grafana
GRAFANA_ADMIN_PASSWORD=<secure-admin-password>

# ============================================================================
# RECOMMENDED - Adjust for your deployment
# ============================================================================

# CORS (comma-separated, NO SPACES)
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com

# Frontend URLs (use HTTPS in production)
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
NEXT_PUBLIC_OPS_API_URL=https://ops.yourdomain.com
NEXTAUTH_URL=https://yourdomain.com

# Cesium Ion Token (get from https://ion.cesium.com/tokens)
NEXT_PUBLIC_CESIUM_ION_TOKEN=<your-cesium-token>

# Environment
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO

# ============================================================================
# OPTIONAL - Keep defaults unless needed
# ============================================================================

# Database
DATABASE_USER=gravity
DATABASE_NAME=gravity_ops
DATABASE_PORT=5432

# API Ports
GALILEO_API_PORT=5050
OPS_API_PORT=8000

# Monitoring
PROMETHEUS_PORT=9090
GRAFANA_PORT=3001
```

### Step 4: Set File Permissions

```bash
chmod 600 .env  # Protect environment file
```

---

## Docker Deployment

### Quick Start

```bash
# 1. Build images
docker-compose build

# 2. Start all services
docker-compose up -d

# 3. Check status
docker-compose ps

# 4. View logs
docker-compose logs -f
```

### Services Overview

| Service | Port | Description |
|---------|------|-------------|
| **api** | 5050 | Main API (simulation, ML, processing) |
| **ops-api** | 8000 | Operations API (auth, jobs, workflows) |
| **ui** | 3000 | Next.js frontend |
| **postgres** | 5432 | PostgreSQL + TimescaleDB |
| **redis** | 6379 | Cache & message broker |
| **minio** | 9000, 9001 | Object storage |
| **celery-worker** | - | Async task processor |
| **celery-beat** | - | Scheduled tasks |
| **prometheus** | 9090 | Metrics collection |
| **grafana** | 3001 | Monitoring dashboards |
| **jaeger** | 16686 | Distributed tracing |

### Access URLs

After deployment, access services at:

- **Main Application**: http://localhost:3000
- **Main API Docs**: http://localhost:5050/docs
- **Operations API Docs**: http://localhost:8000/docs
- **Grafana Dashboards**: http://localhost:3001
- **Prometheus**: http://localhost:9090
- **MinIO Console**: http://localhost:9001
- **Jaeger UI**: http://localhost:16686

### Common Docker Commands

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (WARNING: destroys data)
docker-compose down -v

# Restart a specific service
docker-compose restart api

# View logs for specific service
docker-compose logs -f api

# Execute command in container
docker-compose exec api bash

# Scale celery workers
docker-compose up -d --scale celery-worker=4
```

---

## Manual Deployment

### 1. Install Python Dependencies

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Install UI Dependencies

```bash
cd ui
npm install
npm run build
cd ..
```

### 3. Setup PostgreSQL Database

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database and user
CREATE DATABASE gravity_ops;
CREATE USER gravity WITH PASSWORD 'your-password';
GRANT ALL PRIVILEGES ON DATABASE gravity_ops TO gravity;

# Enable extensions
\c gravity_ops
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

# Run initialization scripts
\i ops/db/init.sql
\i scripts/init-db.sql
```

### 4. Run Database Migrations

```bash
# Initialize Alembic (first time only)
alembic init alembic

# Create migration from models
alembic revision --autogenerate -m "Initial schema"

# Apply migrations
alembic upgrade head
```

### 5. Start Services

```bash
# Terminal 1: Start Redis
redis-server

# Terminal 2: Start Main API
uvicorn api.main:app --host 0.0.0.0 --port 5050 --workers 2

# Terminal 3: Start Operations API
uvicorn ops.main:app --host 0.0.0.0 --port 8000 --workers 2

# Terminal 4: Start Celery Worker
celery -A ops.tasks worker --loglevel=info --concurrency=4

# Terminal 5: Start Celery Beat
celery -A ops.tasks beat --loglevel=info

# Terminal 6: Start UI
cd ui && npm start
```

---

## Database Setup

### Database Migrations with Alembic

```bash
# Create new migration
alembic revision -m "description"

# Auto-generate migration from model changes
alembic revision --autogenerate -m "description"

# Apply all migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history

# View current version
alembic current
```

### Database Backup

```bash
# Backup database
docker-compose exec postgres pg_dump -U gravity gravity_ops > backup.sql

# Restore database
docker-compose exec -T postgres psql -U gravity gravity_ops < backup.sql
```

### TimescaleDB Configuration

```sql
-- Check TimescaleDB version
SELECT extversion FROM pg_extension WHERE extname = 'timescaledb';

-- View hypertables
SELECT * FROM timescaledb_information.hypertables;

-- View chunks
SELECT * FROM timescaledb_information.chunks;
```

---

## Monitoring Setup

### Prometheus

Access: http://localhost:9090

**Key Metrics**:
- `galileo_api_requests_total` - Total API requests
- `galileo_api_request_duration_seconds` - Request latency
- `process_cpu_seconds_total` - CPU usage
- `process_resident_memory_bytes` - Memory usage

### Grafana

Access: http://localhost:3001
Default credentials: admin / (from GRAFANA_ADMIN_PASSWORD)

**Setup Dashboards**:
1. Login to Grafana
2. Navigate to Dashboards
3. Pre-configured dashboards should load automatically
4. Import additional dashboards from `monitoring/grafana/dashboards/`

**Recommended Community Dashboards**:
- Node Exporter Full: ID 1860
- FastAPI Observability: ID 16110
- PostgreSQL Database: ID 9628

### Jaeger Tracing

Access: http://localhost:16686

View distributed traces across:
- API requests
- Database queries
- Celery tasks
- External service calls

---

## Security Checklist

### Before Production Deployment

- [ ] All secrets changed from defaults
- [ ] `.env` file has restrictive permissions (600)
- [ ] CORS origins configured (no wildcards)
- [ ] HTTPS enabled (reverse proxy)
- [ ] JWT secret keys are strong (64+ characters)
- [ ] Database passwords are strong
- [ ] MinIO access keys are rotated
- [ ] Grafana admin password changed
- [ ] Rate limiting enabled
- [ ] Authentication enabled on all APIs
- [ ] API keys configured for service-to-service auth
- [ ] Audit logging enabled
- [ ] Database backups configured
- [ ] Firewall rules configured
- [ ] SSL certificates valid
- [ ] Security headers configured (CSP, HSTS, etc.)

### Reverse Proxy Configuration (Nginx)

```nginx
# /etc/nginx/sites-available/galileo

# Main API
server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:5050;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Operations API
server {
    listen 443 ssl http2;
    server_name ops.yourdomain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Frontend UI
server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## Troubleshooting

### Container Issues

**Services won't start**:
```bash
# Check logs
docker-compose logs <service-name>

# Check service health
docker-compose ps

# Rebuild containers
docker-compose build --no-cache <service-name>
```

**Database connection errors**:
```bash
# Verify database is running
docker-compose ps postgres

# Check database logs
docker-compose logs postgres

# Test connection
docker-compose exec postgres psql -U gravity -d gravity_ops -c "SELECT 1"
```

### API Issues

**401 Unauthorized errors**:
- Check JWT_SECRET_KEY is set correctly
- Verify AUTH_ENABLED environment variable
- Check token expiration time

**CORS errors**:
- Verify CORS_ORIGINS includes your frontend URL
- Check for trailing slashes in URLs
- Ensure protocol (http/https) matches

**Rate limiting errors**:
- Adjust RATE_LIMIT_PER_MINUTE
- Check if rate limit is enabled: RATE_LIMIT_ENABLED=true

### Performance Issues

**Slow API responses**:
```bash
# Check Prometheus metrics
curl http://localhost:5050/metrics

# View request latency histogram
curl http://localhost:9090/api/v1/query?query=galileo_api_request_duration_seconds

# Scale workers
docker-compose up -d --scale celery-worker=8
```

**High memory usage**:
```bash
# Check container stats
docker stats

# Adjust worker concurrency
# In docker-compose.yml: celery worker --concurrency=2
```

### Common Errors

**"JWT_SECRET_KEY must be set"**:
- Set JWT_SECRET_KEY in .env file
- Restart services: `docker-compose restart`

**"Could not connect to database"**:
- Wait for database to be healthy
- Check DATABASE_URL format
- Verify network connectivity

**"CORS policy blocked"**:
- Add frontend URL to CORS_ORIGINS
- Restart API services

---

## Additional Resources

### Documentation
- [API Documentation](http://localhost:5050/docs)
- [Operations API](http://localhost:8000/docs)
- [Session Documentation](./README.md)

### Monitoring
- [Prometheus Queries](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Grafana Dashboards](https://grafana.com/docs/grafana/latest/dashboards/)

### Support
- GitHub Issues: https://github.com/alovladi007/GALILEO-V2.0/issues
- Documentation: See SESSION_*_README.md files

---

## Production Checklist

Before going live:

**Infrastructure**:
- [ ] Load balancer configured
- [ ] Auto-scaling rules defined
- [ ] Backup strategy implemented
- [ ] Disaster recovery plan documented
- [ ] Monitoring alerts configured
- [ ] Log aggregation setup

**Security**:
- [ ] Security audit completed
- [ ] Penetration testing done
- [ ] Rate limits tested
- [ ] Authentication flow verified
- [ ] HTTPS enforced
- [ ] Security headers configured

**Performance**:
- [ ] Load testing completed
- [ ] Database indexed optimized
- [ ] Caching strategy implemented
- [ ] CDN configured (for static assets)
- [ ] API response times acceptable (<200ms)

**Operations**:
- [ ] Deployment runbook created
- [ ] Rollback procedure tested
- [ ] On-call rotation established
- [ ] Incident response plan ready
- [ ] Team trained on deployment process

---

## License

See [LEGAL.md](LEGAL.md) for licensing and compliance information.

---

**Last Updated**: 2025-11-16
**Version**: 2.0
**Status**: Production Ready
