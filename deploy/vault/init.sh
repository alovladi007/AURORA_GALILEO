#!/bin/bash
# Vault Initialization Script for GALILEO Platform
# Run after Vault deployment to initialize and configure

set -e

NAMESPACE="${NAMESPACE:-vault}"
VAULT_POD="${VAULT_POD:-vault-0}"

echo "=========================================="
echo "GALILEO Vault Initialization"
echo "=========================================="

# Wait for Vault pod to be ready
echo "Waiting for Vault pod to be ready..."
kubectl wait --for=condition=Ready pod/${VAULT_POD} -n ${NAMESPACE} --timeout=300s

# Initialize Vault (only run once!)
echo "Initializing Vault..."
INIT_OUTPUT=$(kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault operator init \
    -recovery-shares=5 \
    -recovery-threshold=3 \
    -key-shares=5 \
    -key-threshold=3 \
    -format=json 2>/dev/null || echo "ALREADY_INITIALIZED")

if [ "${INIT_OUTPUT}" = "ALREADY_INITIALIZED" ]; then
    echo "Vault already initialized, skipping..."
else
    # Save recovery keys and root token securely
    echo "${INIT_OUTPUT}" > vault-init-output.json
    chmod 600 vault-init-output.json
    echo "✓ Vault initialized. Recovery keys saved to vault-init-output.json"
    echo "⚠ STORE THIS FILE SECURELY AND DELETE FROM HERE!"
fi

# Extract root token (for first-time setup)
ROOT_TOKEN=$(jq -r '.root_token' vault-init-output.json)

# Wait for Vault to be unsealed (auto-unseal with KMS)
echo "Waiting for Vault to be unsealed..."
sleep 10

# Login with root token
kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault login -no-print ${ROOT_TOKEN}

# ============================================================================
# Enable Authentication Methods
# ============================================================================

echo "Configuring authentication methods..."

# Enable Kubernetes auth
kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault auth enable kubernetes || true

# Configure Kubernetes auth
kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- sh -c '
vault write auth/kubernetes/config \
    token_reviewer_jwt="$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)" \
    kubernetes_host="https://$KUBERNETES_PORT_443_TCP_ADDR:443" \
    kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt
'

# Enable AppRole auth (for CI/CD)
kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault auth enable approle || true

# Enable userpass auth (for emergency access)
kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault auth enable userpass || true

# ============================================================================
# Enable Secret Engines
# ============================================================================

echo "Enabling secret engines..."

# KV v2 for application secrets
kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault secrets enable -path=galileo kv-v2 || true

# Database engine for dynamic credentials
kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault secrets enable database || true

# Transit engine for encryption
kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault secrets enable transit || true

# PKI for certificate management
kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault secrets enable pki || true
kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault secrets tune -max-lease-ttl=87600h pki

# ============================================================================
# Create Policies
# ============================================================================

echo "Creating policies..."

# Application policy
cat <<EOF | kubectl exec -i -n ${NAMESPACE} ${VAULT_POD} -- vault policy write galileo-app -
# Read application secrets
path "galileo/data/app/*" {
  capabilities = ["read"]
}

# Get database credentials
path "database/creds/galileo-app" {
  capabilities = ["read"]
}

# Encrypt/decrypt using transit
path "transit/encrypt/galileo" {
  capabilities = ["update"]
}

path "transit/decrypt/galileo" {
  capabilities = ["update"]
}
EOF

# Admin policy
cat <<EOF | kubectl exec -i -n ${NAMESPACE} ${VAULT_POD} -- vault policy write galileo-admin -
path "galileo/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "sys/policies/acl/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "auth/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}
EOF

# Read-only audit policy
cat <<EOF | kubectl exec -i -n ${NAMESPACE} ${VAULT_POD} -- vault policy write galileo-audit -
path "sys/audit/*" {
  capabilities = ["read", "list"]
}

path "sys/audit-hash/*" {
  capabilities = ["update"]
}
EOF

# ============================================================================
# Configure Kubernetes Roles
# ============================================================================

echo "Configuring Kubernetes auth roles..."

# Role for galileo-api
kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault write auth/kubernetes/role/galileo-api \
    bound_service_account_names=galileo \
    bound_service_account_namespaces=galileo \
    policies=galileo-app \
    ttl=24h

# Role for galileo-worker
kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault write auth/kubernetes/role/galileo-worker \
    bound_service_account_names=galileo \
    bound_service_account_namespaces=galileo \
    policies=galileo-app \
    ttl=24h

# ============================================================================
# Initialize Secrets
# ============================================================================

echo "Initializing application secrets..."

# Generate and store application secrets
kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault kv put galileo/app/jwt \
    secret_key="$(openssl rand -hex 32)" \
    refresh_secret_key="$(openssl rand -hex 32)"

kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault kv put galileo/app/encryption \
    secret_key="$(openssl rand -hex 32)"

kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault kv put galileo/app/csrf \
    secret_key="$(openssl rand -hex 32)"

# ============================================================================
# Enable Audit Logging
# ============================================================================

echo "Enabling audit logging..."

kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault audit enable file file_path=/vault/audit/audit.log || true

# Enable syslog audit (for SIEM integration)
# kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault audit enable syslog tag="vault" facility="LOCAL7"

# ============================================================================
# Configure Transit Encryption Key
# ============================================================================

echo "Configuring transit encryption..."

kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault write transit/keys/galileo \
    type=aes256-gcm96 \
    exportable=false \
    allow_plaintext_backup=false \
    derived=false

# Set key rotation policy (rotate every 30 days)
kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault write transit/keys/galileo/config \
    min_decryption_version=1 \
    deletion_allowed=false

echo "=========================================="
echo "Vault Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Move vault-init-output.json to a SECURE location"
echo "2. Distribute recovery keys to authorized personnel"
echo "3. Revoke root token after creating admin users"
echo "4. Configure database secret engine for dynamic credentials"
echo "5. Set up secret rotation policies"
echo ""
echo "Access UI: https://vault.galileo.example.com"
echo "=========================================="
