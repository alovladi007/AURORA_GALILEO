#!/usr/bin/env bash
#
# Generate development mTLS certificates
# ======================================
#
# Creates a local CA plus server and client certificates for testing mutual
# TLS between GALILEO services. FOR DEVELOPMENT ONLY — use a real PKI / cert
# manager (e.g. cert-manager, Vault PKI) in production.
#
# Output: certs/ca.pem, certs/server.{key,pem}, certs/client.{key,pem}
#
# Usage: ./scripts/generate_dev_certs.sh [output_dir]

set -euo pipefail

OUT_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/certs}"
mkdir -p "${OUT_DIR}"
cd "${OUT_DIR}"

DAYS=365
SUBJECT_BASE="/C=US/O=GALILEO/OU=Platform"

echo "Generating dev mTLS certs in ${OUT_DIR}"

# 1. Certificate Authority
openssl genrsa -out ca.key 4096 2>/dev/null
openssl req -x509 -new -nodes -key ca.key -sha256 -days ${DAYS} \
    -subj "${SUBJECT_BASE}/CN=GALILEO-Dev-CA" -out ca.pem 2>/dev/null

# Helper to issue a cert signed by the CA.
issue_cert() {
    local name="$1"
    local cn="$2"
    openssl genrsa -out "${name}.key" 2048 2>/dev/null
    openssl req -new -key "${name}.key" \
        -subj "${SUBJECT_BASE}/CN=${cn}" -out "${name}.csr" 2>/dev/null
    # SAN so clients can connect via service DNS names.
    cat > "${name}.ext" <<EOF
subjectAltName = DNS:${cn}, DNS:localhost, IP:127.0.0.1
EOF
    openssl x509 -req -in "${name}.csr" -CA ca.pem -CAkey ca.key \
        -CAcreateserial -days ${DAYS} -sha256 \
        -extfile "${name}.ext" -out "${name}.pem" 2>/dev/null
    rm -f "${name}.csr" "${name}.ext"
}

# 2. Server cert (used by each gRPC service)
issue_cert server "galileo-service"

# 3. Client cert (used by the API Gateway / other callers)
issue_cert client "galileo-client"

# Cleanup serial file.
rm -f ca.srl

echo ""
echo "Generated:"
ls -1 "${OUT_DIR}"/*.pem "${OUT_DIR}"/*.key
echo ""
echo "Configure services with:"
echo "  export GALILEO_TLS_CA=${OUT_DIR}/ca.pem"
echo "  export GALILEO_TLS_SERVER_CERT=${OUT_DIR}/server.pem"
echo "  export GALILEO_TLS_SERVER_KEY=${OUT_DIR}/server.key"
echo "  export GALILEO_TLS_CLIENT_CERT=${OUT_DIR}/client.pem"
echo "  export GALILEO_TLS_CLIENT_KEY=${OUT_DIR}/client.key"
echo "  export GALILEO_SERVICE_TOKEN=\$(openssl rand -hex 32)"
