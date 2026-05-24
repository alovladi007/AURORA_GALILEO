# GALILEO Quick Start Guide

Get GALILEO running in 5 minutes with no port conflicts!

## Step 1: Start Infrastructure (2 minutes)

```bash
# Start all backend services
./scripts/start-infrastructure.sh
```

This starts:
- PostgreSQL (TimescaleDB) - Port **15432**
- Redis - Port **16379**
- MinIO - Ports **19000** (API), **19001** (Console)
- Kafka - Port **19092**
- Jaeger - Port **26686** (UI)
- Prometheus - Port **19090**
- Grafana - Port **13001**
- MLflow - Port **15000**

## Step 2: Check Services (30 seconds)

```bash
./scripts/check-services.sh
```

All services should show ✓ Healthy

## Step 3: Start Frontend (1 minute)

```bash
cd ui

# First time only:
npm install
cp .env.local.example .env.local
# Edit .env.local and add Cesium token (optional for 3D globe)

# Start development server
npm run dev
```

Frontend runs on: **http://localhost:13003**

## Access Points

| Service | URL | Credentials |
|---------|-----|-------------|
| **🌐 Frontend** | http://localhost:13003 | - |
| **📊 Grafana** | http://localhost:13001 | admin / admin |
| **🔍 Jaeger** | http://localhost:26686 | - |
| **💾 MinIO Console** | http://localhost:19001 | minioadmin / minioadmin123 |
| **📈 Prometheus** | http://localhost:19090 | - |
| **🤖 MLflow** | http://localhost:15000 | - |

## Database Access

```bash
# PostgreSQL
psql -h localhost -p 15432 -U galileo galileo
# Password: galileo_dev_password

# Redis
redis-cli -h localhost -p 16379
```

## Stop Everything

```bash
# Stop infrastructure
./scripts/stop-infrastructure.sh

# Stop frontend (Ctrl+C in terminal)
```

## Port Summary

**All ports use 10000+ range to avoid conflicts:**

- Frontend: **13003** (not 3000)
- PostgreSQL: **15432** (not 5432)
- Redis: **16379** (not 6379)
- MinIO: **19000/19001** (not 9000/9001)
- Kafka: **19092** (not 9092)
- Grafana: **13001** (not 3001)
- Jaeger: **26686** (not 16686)
- Prometheus: **19090** (not 9090)
- MLflow: **15000** (not 5000)

## Troubleshooting

### Port still in use?

```bash
# Find what's using the port
lsof -i :13003

# Kill it
kill -9 <PID>
```

### Docker not running?

```bash
# Start Docker
sudo systemctl start docker

# Check status
docker info
```

### Frontend won't start?

```bash
# Clear Next.js cache
cd ui
rm -rf .next
npm run dev
```

## What's Running?

```
┌─────────────────────────────────────┐
│  Frontend (localhost:13003)         │
│  - Next.js + React                  │
│  - CesiumJS 3D Globe                │
│  - Real-time dashboards             │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Infrastructure Services            │
│  - PostgreSQL + TimescaleDB         │
│  - Redis Cache                      │
│  - MinIO Object Storage             │
│  - Kafka Event Streaming            │
│  - Monitoring Stack                 │
└─────────────────────────────────────┘
```

## Next Steps

1. ✅ Open frontend: http://localhost:13003
2. ✅ Check Grafana dashboards: http://localhost:13001
3. ✅ View traces in Jaeger: http://localhost:26686
4. 📚 Read full docs: [README.md](README.md)
5. 🚀 Deploy to production: [Terraform Guide](deploy/terraform/README.md)

## Development Tips

- **Hot reload**: Frontend auto-refreshes on code changes
- **API Gateway**: Add to docker-compose when ready
- **Microservices**: See `services/README.md` for gRPC services
- **Port reference**: See [PORTS.md](PORTS.md) for all ports
