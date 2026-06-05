#!/usr/bin/env bash
#
# Run all service test suites
# ===========================
#
# Generates protobuf stubs (if missing) and runs each service's pytest suite
# with the correct PYTHONPATH. Each service is run independently so their
# `src.*` imports don't collide.
#
# Usage: ./scripts/run_tests.sh [pytest-args...]

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXTRA_ARGS=("$@")

# Ensure protobuf stubs exist.
if [ ! -f "${REPO_ROOT}/services/data-service/src/gen/data_service_pb2.py" ]; then
    echo "Generating protobuf stubs..."
    "${REPO_ROOT}/scripts/generate_protos.sh"
fi

# pytest options that override the repo-root pytest.ini (which targets `bench`).
PYTEST_OPTS=(-o addopts="" -p no:cacheprovider -q)

SERVICES=(
    "data-service"
    "ml-service"
    "inversion-service"
    "control-service"
    "api-gateway"
)

overall=0
declare -A results

for svc in "${SERVICES[@]}"; do
    svc_dir="${REPO_ROOT}/services/${svc}"
    if [ ! -d "${svc_dir}/tests" ]; then
        continue
    fi
    echo ""
    echo "============================================================"
    echo "  ${svc}"
    echo "============================================================"
    (
        cd "${svc_dir}"
        PYTHONPATH="src:src/gen" python3 -m pytest tests/ \
            "${PYTEST_OPTS[@]}" "${EXTRA_ARGS[@]}"
    )
    rc=$?
    results["${svc}"]=${rc}
    if [ ${rc} -ne 0 ]; then
        overall=1
    fi
done

echo ""
echo "============================================================"
echo "  Summary"
echo "============================================================"
for svc in "${SERVICES[@]}"; do
    if [ -n "${results[${svc}]+x}" ]; then
        if [ "${results[${svc}]}" -eq 0 ]; then
            echo "  PASS  ${svc}"
        else
            echo "  FAIL  ${svc}"
        fi
    fi
done

exit ${overall}
