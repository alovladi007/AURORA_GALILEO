#!/bin/bash
# GALILEO Infrastructure Stop Script

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  GALILEO Infrastructure Shutdown${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if services are running
if ! docker compose -f docker-compose.infrastructure.yaml ps --services --filter "status=running" &>/dev/null; then
    echo -e "${YELLOW}No services are running${NC}"
    exit 0
fi

echo -e "${YELLOW}Stopping services...${NC}"
docker compose -f docker-compose.infrastructure.yaml down

echo ""
echo -e "${GREEN}✓ All services stopped${NC}"
echo ""

# Option to remove volumes
read -p "Remove data volumes? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Removing volumes...${NC}"
    docker volume rm galileo-postgres-data galileo-redis-data galileo-minio-data \
        galileo-kafka-data galileo-zookeeper-data galileo-zookeeper-logs \
        galileo-prometheus-data galileo-grafana-data 2>/dev/null || true
    echo -e "${GREEN}✓ Volumes removed${NC}"
fi

echo ""
echo -e "${GREEN}Shutdown complete!${NC}"
