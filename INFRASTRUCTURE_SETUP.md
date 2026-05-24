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

**Note**: Using alternative ports (10000+ range) to avoid conflicts with common services.

| Service | Internal Port | External Port | URL | Credentials |
|---------|--------------|---------------|-----|-------------|
| PostgreSQL | 5432 | **15432** | localhost:15432 | galileo / galileo_dev_password |
| Redis | 6379 | **16379** | localhost:16379 | (no auth) |
| MinIO Console | 9001 | **19001** | http://localhost:19001 | minioadmin / minioadmin123 |
| MinIO API | 9000 | **19000** | http://localhost:19000 | - |
| Grafana | 3000 | **13001** | http://localhost:13001 | admin / admin |
| Jaeger UI | 16686 | **26686** | http://localhost:26686 | (no auth) |
| Prometheus | 9090 | **19090** | http://localhost:19090 | (no auth) |
| MLflow | 5000 | **15000** | http://localhost:15000 | (no auth) |
| Kafka | 9092 | **19092** | localhost:19092 | (no auth) |

📖 **See [PORTS.md](PORTS.md) for complete port mapping and connection examples.**

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

# Direct connection (note the port!)
psql -h localhost -p 15432 -U galileo -d galileo
```

### Access Redis

```bash
# Using Docker exec
docker compose -f docker-compose.infrastructure.yaml exec redis redis-cli

# Direct connection (note the port!)
redis-cli -h localhost -p 16379
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
