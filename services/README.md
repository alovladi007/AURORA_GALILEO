# GALILEO Microservices Architecture

Production-ready microservices architecture with gRPC communication, distributed tracing, and service mesh support.

## Architecture Overview

```
┌─────────────────┐
│   API Gateway   │ ◄─── REST/GraphQL (External)
│   (FastAPI)     │
└────────┬────────┘
         │ gRPC
         ├──────────────┬──────────────┬──────────────┬──────────────┐
         │              │              │              │              │
         ▼              ▼              ▼              ▼              ▼
    ┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐
    │  Data  │    │   ML   │    │Inversion│   │Control │    │  Ops   │
    │Service │    │Service │    │Service  │   │Service │    │Service │
    └────────┘    └────────┘    └────────┘    └────────┘    └────────┘
         │              │              │              │              │
         └──────────────┴──────────────┴──────────────┴──────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
              ┌──────────┐      ┌────────┐      ┌────────┐
              │PostgreSQL│      │ Redis  │      │MinIO/S3│
              │TimescaleDB│     │ Cache  │      │Storage │
              └──────────┘      └────────┘      └────────┘
```

## Services

### 1. API Gateway (Port 8000)
**Purpose**: Entry point for all external requests, handles authentication, rate limiting, and request routing.

**Features**:
- REST API endpoints
- JWT authentication
- Rate limiting per user/IP
- Request/response transformation
- Load balancing across services
- Circuit breaker pattern
- OpenAPI documentation

**Technology**: FastAPI, gRPC clients

**Endpoints**:
- `/api/v1/data/*` → Data Service
- `/api/v1/models/*` → ML Service
- `/api/v1/inversions/*` → Inversion Service
- `/api/v1/satellites/*` → Control Service
- `/api/v1/ops/*` → Operations Service

### 2. Data Service (Port 50051)
**Purpose**: Manages satellite telemetry and gravity measurements.

**Features**:
- Ingest satellite telemetry data
- Store gravity measurements
- Query time-series data
- Export data in multiple formats (CSV, NetCDF, Parquet)
- Stream real-time telemetry
- Data validation and quality checks

**Technology**: Python, gRPC, TimescaleDB, asyncio

**Database Schema**:
- `satellite_telemetry` - Hypertable for telemetry
- `gravity_measurements` - Hypertable for measurements
- Continuous aggregates for hourly/daily summaries

### 3. ML Service (Port 50052)
**Purpose**: Machine learning model training, deployment, and inference.

**Features**:
- Model training (PyTorch, JAX)
- Hyperparameter tuning
- Model versioning and registry
- Batch and real-time inference
- Model evaluation and metrics
- A/B testing support
- AutoML capabilities

**Technology**: Python, gRPC, PyTorch, JAX, MLflow

**Model Types**:
- Gravity field inversion models
- Anomaly detection
- Time series forecasting
- Satellite trajectory prediction

### 4. Inversion Service (Port 50053)
**Purpose**: Gravity field inversion computations.

**Features**:
- Multiple inversion algorithms (Least Squares, Bayesian, Neural Network)
- Distributed computation with Celery
- Progress tracking and streaming
- Result caching
- Grid-based density models
- Uncertainty quantification

**Technology**: Python, gRPC, JAX, Celery, Redis

**Algorithms**:
- Least squares inversion
- Bayesian inversion with priors
- Neural network-based inversion
- Regularized inversion

### 5. Control Service (Port 50054)
**Purpose**: Satellite operations and mission planning.

**Features**:
- Send commands to satellites
- Monitor satellite status
- Orbit prediction and propagation
- Mission planning and scheduling
- Emergency operations
- Telemetry correlation

**Technology**: Python, gRPC, Kafka (event streaming)

**Command Types**:
- Maneuver commands
- Calibration procedures
- Data collection tasks
- Power mode changes

### 6. Operations Service (Port 50055)
**Purpose**: System operations, monitoring, and administration.

**Features**:
- User management and RBAC
- API key management
- System health monitoring
- Audit logging
- Configuration management
- Backup and restore

**Technology**: Python, gRPC, PostgreSQL

## Communication

### gRPC Protocol Buffers

All inter-service communication uses gRPC with Protocol Buffers for:
- Type safety
- Automatic code generation
- Efficient serialization
- Bidirectional streaming
- Built-in load balancing

**Proto Files**:
- `proto/common.proto` - Shared types
- `proto/data_service.proto` - Data service API
- `proto/ml_service.proto` - ML service API
- `proto/inversion_service.proto` - Inversion service API
- `proto/control_service.proto` - Control service API

### Generating Code

```bash
# Generate all protobuf code
make proto

# Generate Python only
make proto-python

# Lint proto files
make proto-lint

# Check for breaking changes
make proto-breaking
```

## Development

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Buf CLI (for proto generation)
- kubectl (for Kubernetes deployment)

### Local Development

1. **Copy environment file**:
```bash
cp .env.microservices.example .env.microservices
```

2. **Start all services**:
```bash
docker-compose -f docker-compose.microservices.yaml up
```

3. **Access services**:
- API Gateway: http://localhost:8000
- Jaeger UI: http://localhost:16686
- Grafana: http://localhost:3001
- MinIO Console: http://localhost:9001
- MLflow: http://localhost:5000

4. **View logs**:
```bash
# All services
docker-compose -f docker-compose.microservices.yaml logs -f

# Specific service
docker-compose -f docker-compose.microservices.yaml logs -f data-service
```

### Testing Services

#### Health Checks

```bash
# API Gateway
curl http://localhost:8000/health

# Data Service (requires grpc_cli)
grpc_cli call localhost:50051 galileo.data.DataService.HealthCheck ""

# ML Service
grpc_cli call localhost:50052 galileo.ml.MLService.HealthCheck ""
```

#### Example Requests

**Ingest Telemetry**:
```bash
curl -X POST http://localhost:8000/api/v1/data/telemetry \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "satellite_id": "SAT-001",
    "timestamp": "2024-01-15T12:00:00Z",
    "location": {"latitude": 45.0, "longitude": -75.0, "altitude": 500000},
    "temperature": 25.5,
    "battery_level": 95.2
  }'
```

**Train Model**:
```bash
curl -X POST http://localhost:8000/api/v1/models/train \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "model_name": "gravity-inversion-v1",
    "model_type": "gravity_inversion",
    "dataset_id": "dataset-001",
    "num_epochs": 100,
    "batch_size": 32
  }'
```

## Deployment

### Kubernetes with Helm

```bash
# Install all services
helm install galileo deploy/helm/galileo \
  --namespace galileo \
  --create-namespace

# Check status
kubectl get pods -n galileo

# View logs
kubectl logs -n galileo -l app=data-service -f
```

### Istio Service Mesh

```bash
# Install Istio
istioctl install --set profile=default

# Label namespace for injection
kubectl label namespace galileo istio-injection=enabled

# Deploy with Istio
helm install galileo deploy/helm/galileo \
  --namespace galileo \
  --set serviceMesh.enabled=true
```

## Monitoring & Observability

### Distributed Tracing (Jaeger)

All services emit OpenTelemetry traces:
- HTTP/gRPC request spans
- Database query spans
- External API call spans
- Custom business logic spans

**View traces**: http://localhost:16686

### Metrics (Prometheus + Grafana)

**Prometheus scrapes**:
- Service metrics (request rate, latency, errors)
- System metrics (CPU, memory, disk)
- Business metrics (inversions/hour, models trained)

**Grafana dashboards**:
- Service overview
- gRPC performance
- Database performance
- ML model metrics
- Infrastructure health

### Logging

**Structured logging** with:
- Timestamp
- Service name
- Trace ID (for correlation)
- Log level
- Message
- Contextual metadata

**Log aggregation**: Centralized in CloudWatch/Loki

## Performance

### Benchmarks

| Operation | Latency (p50) | Latency (p99) | Throughput |
|-----------|---------------|---------------|------------|
| Ingest Telemetry | 5ms | 20ms | 10,000 req/s |
| Query Data | 15ms | 50ms | 5,000 req/s |
| Model Prediction | 25ms | 100ms | 2,000 req/s |
| Start Inversion | 100ms | 500ms | 50 req/s |

### Optimization

1. **Caching**:
   - Redis for hot data
   - Query result caching
   - Model prediction caching

2. **Connection Pooling**:
   - Database connection pools
   - gRPC channel reuse
   - HTTP connection pooling

3. **Batching**:
   - Batch telemetry ingestion
   - Batch predictions
   - Batch database writes

4. **Async Processing**:
   - Celery for long-running tasks
   - Kafka for event streaming
   - asyncio for I/O operations

## Security

### Authentication & Authorization

- JWT tokens for external API
- mTLS for service-to-service (Istio)
- API keys for programmatic access
- RBAC with fine-grained permissions

### Network Security

- Private subnets for services
- Network policies (Kubernetes)
- VPC endpoints for AWS services
- TLS 1.3 for all communication

### Data Security

- Encryption at rest (KMS)
- Encryption in transit (TLS)
- Data masking for sensitive fields
- Audit logging for all operations

## Troubleshooting

### Service Not Starting

```bash
# Check logs
docker-compose -f docker-compose.microservices.yaml logs <service-name>

# Check health
docker-compose -f docker-compose.microservices.yaml ps

# Restart service
docker-compose -f docker-compose.microservices.yaml restart <service-name>
```

### Database Connection Issues

```bash
# Test connection
docker-compose -f docker-compose.microservices.yaml exec postgres psql -U galileo

# Check TimescaleDB extension
docker-compose -f docker-compose.microservices.yaml exec postgres \
  psql -U galileo -d galileo -c "SELECT * FROM pg_extension WHERE extname='timescaledb';"
```

### gRPC Communication Issues

```bash
# Test gRPC service
grpcurl -plaintext localhost:50051 list
grpcurl -plaintext localhost:50051 describe galileo.data.DataService

# Check network
docker-compose -f docker-compose.microservices.yaml exec api-gateway ping data-service
```

## Future Enhancements

- [ ] GraphQL API gateway
- [ ] WebSocket support for real-time updates
- [ ] Service mesh with Linkerd
- [ ] Chaos engineering with Chaos Mesh
- [ ] Multi-region deployment
- [ ] Advanced caching with Varnish
- [ ] Stream processing with Apache Flink
- [ ] Data lake with Apache Iceberg

## References

- [gRPC Documentation](https://grpc.io/docs/)
- [Protocol Buffers](https://protobuf.dev/)
- [Buf CLI](https://buf.build/)
- [Istio Service Mesh](https://istio.io/)
- [OpenTelemetry](https://opentelemetry.io/)
