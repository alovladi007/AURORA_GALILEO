#!/bin/bash
# GALILEO Services Health Check Script

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  GALILEO Services Health Check${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to check service
check_service() {
    local name=$1
    local check_cmd=$2

    echo -n "$name: "
    if eval $check_cmd &>/dev/null; then
        echo -e "${GREEN}✓ Healthy${NC}"
        return 0
    else
        echo -e "${RED}✗ Unhealthy${NC}"
        return 1
    fi
}

# Check Docker daemon
check_service "Docker Daemon" "docker info"

echo ""
echo -e "${YELLOW}Infrastructure Services:${NC}"

# Check PostgreSQL
check_service "PostgreSQL (5432)" "docker compose -f docker-compose.infrastructure.yaml exec -T postgres pg_isready -U galileo"

# Check Redis
check_service "Redis (6379)" "docker compose -f docker-compose.infrastructure.yaml exec -T redis redis-cli ping"

# Check MinIO
check_service "MinIO API (9000)" "curl -sf http://localhost:9000/minio/health/live"
check_service "MinIO Console (9001)" "curl -sf http://localhost:9001"

# Check Kafka
check_service "Kafka (9092)" "docker compose -f docker-compose.infrastructure.yaml exec -T kafka kafka-topics --bootstrap-server localhost:9092 --list"

# Check Jaeger
check_service "Jaeger UI (16686)" "curl -sf http://localhost:16686"

# Check Prometheus
check_service "Prometheus (9090)" "curl -sf http://localhost:9090/-/healthy"

# Check Grafana
check_service "Grafana (3001)" "curl -sf http://localhost:3001/api/health"

# Check MLflow
check_service "MLflow (5000)" "curl -sf http://localhost:5000/health"

echo ""
echo -e "${BLUE}Container Status:${NC}"
docker compose -f docker-compose.infrastructure.yaml ps

echo ""
echo -e "${BLUE}Resource Usage:${NC}"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" \
    $(docker compose -f docker-compose.infrastructure.yaml ps -q 2>/dev/null) 2>/dev/null || echo "No containers running"

echo ""
echo -e "${BLUE}Recent Logs (last 5 lines per service):${NC}"
for service in postgres redis minio kafka jaeger prometheus grafana mlflow; do
    echo -e "\n${YELLOW}$service:${NC}"
    docker compose -f docker-compose.infrastructure.yaml logs --tail=5 $service 2>/dev/null || echo "Service not running"
done
