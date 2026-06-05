#!/usr/bin/env bash
#
# Generate Python gRPC stubs for all services
# ===========================================
#
# Generates protobuf stubs into each service's src/gen/ directory so that
# `from src.gen import data_service_pb2` works. The generated stubs use flat
# internal imports (import common_pb2), which resolve because src/gen is added
# to sys.path by each service's main.py / conftest.py.
#
# Usage: ./scripts/generate_protos.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROTO_DIR="${REPO_ROOT}/proto"

echo "Generating protobuf stubs from ${PROTO_DIR}"

# Services that need the generated stubs
SERVICES=(
    "data-service"
    "ml-service"
    "inversion-service"
    "control-service"
)

# API Gateway uses a different gen path (gen/python/proto)
GATEWAY_GEN="${REPO_ROOT}/services/api-gateway/src/gen/python/proto"

generate_for_dir() {
    local out_dir="$1"
    mkdir -p "${out_dir}"

    python3 -m grpc_tools.protoc \
        -I "${PROTO_DIR}" \
        --python_out="${out_dir}" \
        --grpc_python_out="${out_dir}" \
        "${PROTO_DIR}"/common.proto \
        "${PROTO_DIR}"/data_service.proto \
        "${PROTO_DIR}"/ml_service.proto \
        "${PROTO_DIR}"/inversion_service.proto \
        "${PROTO_DIR}"/control_service.proto

    # Ensure package init
    touch "${out_dir}/__init__.py"
}

for svc in "${SERVICES[@]}"; do
    out_dir="${REPO_ROOT}/services/${svc}/src/gen"
    echo "  -> ${svc}: ${out_dir}"
    generate_for_dir "${out_dir}"
done

# API Gateway
echo "  -> api-gateway: ${GATEWAY_GEN}"
generate_for_dir "${GATEWAY_GEN}"
# Make the intermediate packages importable
touch "${REPO_ROOT}/services/api-gateway/src/gen/__init__.py"
touch "${REPO_ROOT}/services/api-gateway/src/gen/python/__init__.py"

echo "Protobuf stubs generated successfully"
