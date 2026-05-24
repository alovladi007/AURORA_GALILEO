# GALILEO Infrastructure Setup Guide

Quick guide to start GALILEO infrastructure services locally.

## Quick Start

### 1. Prerequisites Check

```bash
# Check Docker
docker --version

# Check Docker Compose
docker compose version

# Start Docker daemon (if not running)
sudo systemctl start docker
```

### 2. Start Infrastructure

```bash
# Option 1: Use startup script (recommended)
./scripts/start-infrastructure.sh

# Option 2: Manual startup
docker compose -f docker-compose.infrastructure.yaml up -d
```

### 3. Verify Services

```bash
# Check all services
./scripts/check-services.sh

# Or manually check
docker compose -f docker-compose.infrastructure.yaml ps
```

## Services Overview

| Service | Port | URL | Credentials |
|---------|------|-----|-------------|
| PostgreSQL | 5432 | localhost:5432 | galileo / galileo_dev_password |
| Redis | 6379 | localhost:6379 | (no auth) |
| MinIO Console | 9001 | http://localhost:9001 | minioadmin / minioadmin123 |
| Grafana | 3001 | http://localhost:3001 | admin / admin |
| Jaeger UI | 16686 | http://localhost:16686 | (no auth) |
| Prometheus | 9090 | http://localhost:9090 | (no auth) |
| MLflow | 5000 | http://localhost:5000 | (no auth) |
| Kafka | 9092 | localhost:9092 | (no auth) |

## Common Tasks

### View Logs

```bash
# All services
docker compose -f docker-compose.infrastructure.yaml logs -f

# Specific service
docker compose -f docker-compose.infrastructure.yaml logs -f postgres
```

### Restart Service

```bash
docker compose -f docker-compose.infrastructure.yaml restart <service-name>
```

### Stop All Services

```bash
./scripts/stop-infrastructure.sh

# Or manually
docker compose -f docker-compose.infrastructure.yaml down
```

### Access Database

```bash
# Using Docker exec
docker compose -f docker-compose.infrastructure.yaml exec postgres \
  psql -U galileo -d galileo

# Direct connection
psql -h localhost -U galileo -d galileo
```

### Access Redis

```bash
# Using Docker exec
docker compose -f docker-compose.infrastructure.yaml exec redis redis-cli

# Direct connection
redis-cli -h localhost
```

## Port Conflicts

If you get port conflict errors:

```bash
# Find what's using the port
lsof -i :5432

# Kill the process
kill -9 <PID>

# Or change ports in docker-compose.infrastructure.yaml
# Example: Change "5432:5432" to "5433:5432"
```

## Troubleshooting

### Docker Daemon Not Running

```bash
# Start Docker
sudo systemctl start docker

# Enable auto-start
sudo systemctl enable docker

# Check status
sudo systemctl status docker
```

### Service Won't Start

```bash
# Check logs
docker compose -f docker-compose.infrastructure.yaml logs <service>

# Remove and recreate
docker compose -f docker-compose.infrastructure.yaml rm -f <service>
docker compose -f docker-compose.infrastructure.yaml up -d <service>
```

### Reset Everything

```bash
# Stop and remove all containers + volumes
docker compose -f docker-compose.infrastructure.yaml down -v

# Remove all Docker data (WARNING: removes all containers/volumes)
docker system prune -a --volumes
```

## Next Steps

1. **Verify services**: `./scripts/check-services.sh`
2. **Access UIs**: Open URLs from table above
3. **Deploy microservices**: See `services/README.md`
4. **Configure Istio**: See `deploy/istio/README.md`

## Production Deployment

For production environments, use:
- **Terraform**: `deploy/terraform/`
- **Kubernetes + Helm**: `deploy/helm/`
- **Istio Service Mesh**: `deploy/istio/`

See main `DEPLOYMENT.md` for details.
