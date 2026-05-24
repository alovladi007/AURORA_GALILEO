# GALILEO Port Mapping

All ports have been configured to avoid common conflicts.

## Infrastructure Services

| Service | Internal Port | External Port | URL/Connection |
|---------|--------------|---------------|----------------|
| **PostgreSQL** | 5432 | **15432** | `localhost:15432` |
| **Redis** | 6379 | **16379** | `localhost:16379` |
| **MinIO API** | 9000 | **19000** | `http://localhost:19000` |
| **MinIO Console** | 9001 | **19001** | `http://localhost:19001` |
| **Kafka** | 9092 | **19092** | `localhost:19092` |
| **Zookeeper** | 2181 | 2181 | Internal only |
| **Jaeger UI** | 16686 | **26686** | `http://localhost:26686` |
| **Jaeger OTLP gRPC** | 4317 | **14317** | `localhost:14317` |
| **Jaeger OTLP HTTP** | 4318 | **14318** | `localhost:14318` |
| **Prometheus** | 9090 | **19090** | `http://localhost:19090` |
| **Grafana** | 3000 | **13001** | `http://localhost:13001` |
| **MLflow** | 5000 | **15000** | `http://localhost:15000` |

## Microservices (when deployed)

| Service | Internal Port | External Port | Protocol |
|---------|--------------|---------------|----------|
| API Gateway | 8000 | 18000 | HTTP/REST |
| Data Service | 50051 | 50051 | gRPC |
| ML Service | 50052 | 50052 | gRPC |
| Inversion Service | 50053 | 50053 | gRPC |
| Control Service | 50054 | 50054 | gRPC |
| Operations Service | 50055 | 50055 | gRPC |

## Connection Strings

### PostgreSQL
```bash
# Direct connection
psql -h localhost -p 15432 -U galileo -d galileo

# Connection string
postgresql://galileo:galileo_dev_password@localhost:15432/galileo

# Docker exec
docker exec -it galileo-postgres psql -U galileo -d galileo
```

### Redis
```bash
# redis-cli
redis-cli -h localhost -p 16379

# Connection string
redis://localhost:16379

# Docker exec
docker exec -it galileo-redis redis-cli
```

### MinIO S3
```python
import boto3

s3 = boto3.client(
    's3',
    endpoint_url='http://localhost:19000',
    aws_access_key_id='minioadmin',
    aws_secret_access_key='minioadmin123',
)
```

### Kafka
```bash
# List topics
kafka-topics --bootstrap-server localhost:19092 --list

# Produce messages
kafka-console-producer --bootstrap-server localhost:19092 --topic test

# Consume messages  
kafka-console-consumer --bootstrap-server localhost:19092 --topic test --from-beginning
```

## Web UIs

| Service | URL | Default Credentials |
|---------|-----|---------------------|
| MinIO Console | http://localhost:19001 | minioadmin / minioadmin123 |
| Grafana | http://localhost:13001 | admin / admin |
| Jaeger | http://localhost:26686 | (no auth) |
| Prometheus | http://localhost:19090 | (no auth) |
| MLflow | http://localhost:15000 | (no auth) |

## Port Conflict Resolution

If you still encounter port conflicts:

1. **Check what's using the port**:
```bash
lsof -i :15432
```

2. **Kill the process** (if safe):
```bash
kill -9 <PID>
```

3. **Use different ports** - Edit `docker-compose.infrastructure.yaml`:
```yaml
ports:
  - "25432:5432"  # Use port 25432 instead
```

## Why Alternative Ports?

Standard ports are often already in use:
- **5432** - PostgreSQL (local installation)
- **6379** - Redis (local installation)
- **9000** - Various services (PHP-FPM, SonarQube, etc.)
- **9090** - Prometheus (local installation)
- **3000/3001** - Web development servers (React, Next.js, etc.)
- **5000** - Flask development server
- **8000** - Django, FastAPI development servers

GALILEO uses **10000+ range** ports to avoid these conflicts:
- **15432** instead of 5432 (PostgreSQL)
- **16379** instead of 6379 (Redis)
- **19000** instead of 9000 (MinIO)
- **13001** instead of 3001 (Grafana)
- **15000** instead of 5000 (MLflow)

## Firewall Rules

If running on a remote server, open these ports:

```bash
# Allow infrastructure ports
sudo ufw allow 15432/tcp  # PostgreSQL
sudo ufw allow 16379/tcp  # Redis
sudo ufw allow 19001/tcp  # MinIO Console
sudo ufw allow 13001/tcp  # Grafana
sudo ufw allow 26686/tcp  # Jaeger
sudo ufw allow 19090/tcp  # Prometheus
```

## Docker Internal Network

Services communicate internally using original ports:
- PostgreSQL: `postgres:5432`
- Redis: `redis:6379`
- MinIO: `minio:9000`
- Kafka: `kafka:9092`

External port mapping only affects host → container access.
