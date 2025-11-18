# GALILEO V2.0 - Port Allocation Map

**Date**: 2025-11-17
**System Scan**: Complete

---

## 🔴 Currently In Use (DO NOT USE)

### Web/Frontend Ports
- **3000** - EUREKA (node) ⚠️ **RESERVED**
- **3177** - Code Helper
- **5173** - Vite Dev Server (node)

### API/Backend Ports
- **4000** - Docker Service
- **5000** - ControlCenter
- **5001** - Python Service
- **8000** - Docker/Python Service
- **8001** - Python Service
- **8002** - Python Service
- **8003** - Python Service
- **8020** - Docker Service
- **8080** - Docker Service
- **8200** - Python Service
- **8501-8504** - Streamlit Apps (Python)

### Infrastructure Ports
- **80** - HTTP (com.docker)
- **443** - HTTPS (com.docker)
- **5433** - PostgreSQL (com.docker)
- **6379** - Redis (com.docker)
- **6443** - Kubernetes API (com.docker)
- **7000** - ControlCenter
- **9000** - MinIO API (com.docker)
- **9001** - MinIO Console (com.docker)
- **9010-9011** - Docker Services

---

## ✅ AVAILABLE PORTS - Recommended Assignments

### Frontend/Web Applications (3001-3010)
- **3001** ✅ Available
- **3002** ✅ Available ← **RECOMMENDED for GALILEO UI**
- **3003** ✅ Available ← **RECOMMENDED for Grafana**
- **3004** ✅ Available
- **3005** ✅ Available
- **3006** ✅ Available
- **3007** ✅ Available
- **3008** ✅ Available
- **3009** ✅ Available
- **3010** ✅ Available

### Alternative Frontend Range (4001-4010)
- **4001** ✅ Available ← **RECOMMENDED for Ops API**
- **4002** ✅ Available
- **4003** ✅ Available
- **4004** ✅ Available
- **4005** ✅ Available
- **4006** ✅ Available
- **4007** ✅ Available
- **4008** ✅ Available
- **4009** ✅ Available
- **4010** ✅ Available

### API/Service Ports (5002-5010)
- **5002** ✅ Available
- **5003** ✅ Available
- **5004** ✅ Available
- **5005** ✅ Available
- **5006** ✅ Available
- **5007** ✅ Available
- **5008** ✅ Available
- **5009** ✅ Available
- **5010** ✅ Available
- **5050** ✅ Available ← **RECOMMENDED for Main API**

### Backend/Worker Ports (8004-8010)
- **8004** ✅ Available
- **8005** ✅ Available
- **8006** ✅ Available
- **8007** ✅ Available
- **8008** ✅ Available
- **8009** ✅ Available
- **8010** ✅ Available

### Monitoring/Metrics (9090-9100)
- **9090** ✅ Available ← **RECOMMENDED for Prometheus**
- **9091** ✅ Available
- **9092** ✅ Available
- **9093** ✅ Available
- **9094** ✅ Available
- **9095** ✅ Available

### Database Ports
- **5432** ✅ Available ← **RECOMMENDED for PostgreSQL**
- **5434** ✅ Available
- **5435** ✅ Available

---

## 🎯 GALILEO V2.0 - Official Port Assignments

### Core Services
| Service | Port | Status | Purpose |
|---------|------|--------|---------|
| **Frontend UI** | **3002** | ✅ Configured | GeoSense Platform Dashboard |
| **Main API** | **5050** | ✅ Configured | Simulation/ML/Processing API |
| **Ops API** | **4001** | ✅ Configured | Auth/Jobs/Workflows API |
| **PostgreSQL** | **5432** | ✅ Configured | TimescaleDB Database |
| **Redis** | **6380** | ✅ Configured | Cache & Message Broker (changed from 6379) |

### Monitoring Stack
| Service | Port | Status | Purpose |
|---------|------|--------|---------|
| **Prometheus** | **9090** | ✅ Configured | Metrics Collection |
| **Grafana** | **3003** | ✅ Configured | Monitoring Dashboard |
| **Jaeger** | **16686** | ✅ Configured | Distributed Tracing |
| **Flower** | **5555** | ✅ Available | Celery Monitor |

### Worker Services
| Service | Port | Status | Purpose |
|---------|------|--------|---------|
| **Celery Worker** | N/A | Internal | Async Task Processing |
| **Celery Beat** | N/A | Internal | Scheduled Tasks |

### Object Storage
| Service | Port | Status | Purpose |
|---------|------|--------|---------|
| **MinIO API** | **9002** | ✅ Configured | S3-Compatible Storage (changed from 9000) |
| **MinIO Console** | **9003** | ✅ Configured | MinIO Web UI (changed from 9001) |

---

## 📋 Port Ranges by Use Case

### Development (Safe for New Projects)
```
Frontend:     3001-3010 (except 3000)
Alternative:  4001-4010
APIs:         5002-5010, 5050-5060
Backend:      8004-8010
Monitoring:   9090-9099
Databases:    5432, 5434-5440
```

### Reserved for EUREKA
```
Port 3000 - DO NOT USE
```

### Currently Occupied
```
80, 443       - Docker HTTP/HTTPS
3000          - EUREKA (node)
4000          - Docker
5000-5001     - ControlCenter/Python
5173          - Vite Dev Server
5433          - Docker PostgreSQL
6379          - Docker Redis
6443          - Docker Kubernetes
7000          - ControlCenter
8000-8003     - Python Services
8020, 8080    - Docker Services
8200          - Python Service
8501-8504     - Streamlit Apps
9000-9001     - Docker MinIO
9010-9011     - Docker Services
```

---

## 🚀 Quick Reference

### To Start GALILEO V2.0:
```bash
cd "/Users/vladimirantoine/GALILEO V2.0/GALILEO-V2.0-1"
docker-compose up -d
```

### Access URLs:
- Frontend: http://localhost:3002
- Main API: http://localhost:5050/docs
- Ops API: http://localhost:4001/docs
- Grafana: http://localhost:3003
- Prometheus: http://localhost:9090
- Jaeger: http://localhost:16686
- MinIO Console: http://localhost:9003
- MinIO API: http://localhost:9002

---

## 📝 Notes

1. **Port 3000 is RESERVED for EUREKA** - Never use for other projects
2. All GALILEO ports have been configured to avoid conflicts
3. Redis (6379) and MinIO (9000-9001) are shared via Docker
4. If you need additional ports, use the 3001-3010 or 4001-4010 ranges
5. For production deployment, consider using reverse proxy (nginx) on port 80/443

---

**Last Updated**: 2025-11-17
**Next Review**: When adding new services
