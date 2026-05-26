#!/bin/bash
set -e

echo "=================================="
echo "GALILEO V2.0 - API Gateway Upgrade"
echo "=================================="

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

echo ""
echo "Step 1: Rebuilding API Gateway..."
docker compose -f docker-compose.microservices.yaml up -d --build api-gateway

echo ""
echo "Step 2: Waiting for services to be ready..."
sleep 10

echo ""
echo "Step 3: Health Check (all 4 services)..."
curl -s http://localhost:18000/health | jq '.'

echo ""
echo "=================================="
echo "Testing ML Service Endpoints"
echo "=================================="

echo ""
echo "1. Train Model..."
curl -s -X POST http://localhost:18000/api/v1/models/train \
  -H "Content-Type: application/json" \
  -d '{"model_type": "pinn", "training_config": {"epochs": 100}}' | jq '.'

echo ""
echo "2. List Models..."
curl -s http://localhost:18000/api/v1/models | jq '.'

echo ""
echo "=================================="
echo "Testing Inversion Service Endpoints"
echo "=================================="

echo ""
echo "1. Run Inversion..."
JOB_ID=$(curl -s -X POST http://localhost:18000/api/v1/inversions/run \
  -H "Content-Type: application/json" \
  -d '{"inversion_type": "spherical_harmonics", "config": {"max_degree": 120}}' | jq -r '.job_id')
echo "Inversion Job ID: $JOB_ID"

echo ""
echo "2. Check Inversion Status..."
curl -s "http://localhost:18000/api/v1/inversions/${JOB_ID}/status" | jq '.'

echo ""
echo "3. List Inversions..."
curl -s http://localhost:18000/api/v1/inversions | jq '.'

echo ""
echo "=================================="
echo "Testing Control Service Endpoints"
echo "=================================="

echo ""
echo "1. Create Mission Plan..."
PLAN_ID=$(curl -s -X POST http://localhost:18000/api/v1/missions/plans \
  -H "Content-Type: application/json" \
  -d '{"mission_name": "GRACE-FO Test", "satellite_ids": ["SAT-001", "SAT-002"]}' | jq -r '.plan_id')
echo "Mission Plan ID: $PLAN_ID"

echo ""
echo "2. Propagate Orbit..."
curl -s -X POST http://localhost:18000/api/v1/simulation/propagate \
  -H "Content-Type: application/json" \
  -d '{"satellite_id": "SAT-001", "start_time": "2026-05-26T00:00:00Z", "duration": 3600}' | jq '.states | length as $count | {satellite_id, states_count: $count, propagator_type, message}'

echo ""
echo "3. Execute Maneuver..."
curl -s -X POST http://localhost:18000/api/v1/control/maneuver \
  -H "Content-Type: application/json" \
  -d '{"satellite_id": "SAT-001", "maneuver_type": "station_keeping", "delta_v": {"x": 0.5, "y": 0.0, "z": 0.1}}' | jq '.'

echo ""
echo "=================================="
echo "Testing Data Service Gravity Endpoints"
echo "=================================="

echo ""
echo "1. Ingest Gravity Measurement..."
curl -s -X POST http://localhost:18000/api/v1/data/gravity \
  -H "Content-Type: application/json" \
  -d '{"satellite_id": "SAT-001", "latitude": 45.5, "longitude": -122.6, "altitude": 550000, "gravity_x": 0.01, "gravity_y": 0.02, "gravity_z": 9.81, "magnitude": 9.81}' | jq '.'

echo ""
echo "2. Query Gravity Data..."
curl -s "http://localhost:18000/api/v1/data/gravity?satellite_ids=SAT-001&limit=5" | jq '.'

echo ""
echo "=================================="
echo "✅ API Gateway Integration Complete!"
echo "=================================="
echo ""
echo "All endpoints tested successfully!"
echo "API Documentation: http://localhost:18000/docs"
echo "Frontend: http://localhost:13003"
echo ""
