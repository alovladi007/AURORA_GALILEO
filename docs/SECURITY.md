# GALILEO V2.0 — Security Guide

This document describes the security model for inter-service and client
communication, and how to configure it for development and production.

## Threat Model

GALILEO is a microservices platform where:
- **External clients** reach the platform through the **API Gateway** (HTTP REST + WebSocket).
- The **API Gateway** calls backend services (Data, ML, Inversion, Control) over **gRPC**.
- Backend services may call each other over gRPC and stream over Kafka.

Security controls address:
1. **Client authentication** (who is calling the gateway)
2. **Inter-service authentication** (gateway ↔ service, service ↔ service)
3. **Transport encryption** (mTLS)
4. **Authorization** (RBAC: which roles may perform which actions)
5. **Rate limiting** (abuse / DoS mitigation)

## 1. Client Authentication (Gateway)

The API Gateway authenticates external clients with **JWT bearer tokens**:

- `Authorization: Bearer <token>` header required on protected endpoints.
- Tokens are verified in `api/auth_v2.py` (`verify_token`).
- The decoded claims populate a `common.UserContext` (`user_id`, `roles`,
  `permissions`, `session_id`) that is forwarded to backend services.

In development (`NODE_ENV=development` / `AUTH_ENABLED=false`) unauthenticated
reads are permitted for convenience.

## 2. Inter-Service Authentication (gRPC)

Implemented in `services/api-gateway/src/api/grpc_security.py`. Two layers:

### Shared Service Token

A shared secret token is attached to outbound gRPC calls and validated on
inbound calls.

- **Client side**: `TokenAuthClientInterceptor` appends an
  `x-service-token` metadata entry to every call.
- **Server side**: `TokenAuthServerInterceptor` rejects calls without the
  expected token (`UNAUTHENTICATED`). Health checks are **exempt** so liveness
  probes work without credentials.

Configure with:

```bash
export GALILEO_SERVICE_TOKEN=$(openssl rand -hex 32)
```

When `GALILEO_SERVICE_TOKEN` is unset, the token layer is disabled (dev mode).

### Mutual TLS (mTLS)

`make_client_channel()` and `make_server_credentials()` build mTLS-enabled
channels/credentials from PEM files referenced by environment variables:

| Variable | Purpose |
|----------|---------|
| `GALILEO_TLS_CA` | CA certificate (verifies peer certs) |
| `GALILEO_TLS_SERVER_CERT` / `GALILEO_TLS_SERVER_KEY` | Service server identity |
| `GALILEO_TLS_CLIENT_CERT` / `GALILEO_TLS_CLIENT_KEY` | Caller (gateway) identity |

When the CA is provided to the server, **mutual** auth is required
(`require_client_auth=True`). When no TLS vars are set, services fall back to
**insecure** channels (development only).

### Generating Development Certificates

```bash
./scripts/generate_dev_certs.sh            # writes to ./certs
./scripts/generate_dev_certs.sh /tmp/certs # custom output dir
```

This creates a local CA plus server and client certs (with SANs for
`localhost` and the service DNS name). The chain verifies with:

```bash
openssl verify -CAfile certs/ca.pem certs/server.pem certs/client.pem
```

**Never commit real certificates.** `certs/`, `*.pem`, and `*.key` are
gitignored. In production, issue certificates from a managed PKI
(cert-manager, Vault PKI, or your cloud provider's CA) and rotate regularly.

## 3. Authorization (RBAC)

Role-based access control is enforced at the gateway in `api/rbac.py`:

- `PermissionChecker.has_permission(roles, permission)` gates sensitive
  operations (e.g. `MODEL_TRAIN`, `INVERSION_RUN`, `SATELLITE_CONTROL`).
- Endpoints return `403 Forbidden` when the caller's roles lack the required
  permission.

## 4. Rate Limiting

The gateway uses `slowapi` for per-endpoint rate limits, e.g.:

- `POST /api/v1/data/telemetry`: 1000/minute
- `POST /api/v1/models/train`: 10/minute
- `POST /api/v1/inversions`: 20/hour

Exceeding a limit returns `429 Too Many Requests`.

## 5. Circuit Breakers

Backend calls are wrapped in circuit breakers (`api/circuit_breaker.py`) to
prevent cascading failures and to fail fast when a service is unhealthy. State
transitions are exported as Prometheus metrics.

## Production Checklist

- [ ] `GALILEO_SERVICE_TOKEN` set (rotated via secrets manager)
- [ ] mTLS certificates issued from managed PKI, mounted read-only
- [ ] `require_client_auth=True` (CA configured on every server)
- [ ] JWT signing keys stored in Vault / KMS, not env files
- [ ] CORS `allow_origins` restricted to known frontends (not `*`)
- [ ] Rate limits tuned per environment
- [ ] TLS termination verified end-to-end (no plaintext gRPC in cluster)
- [ ] Audit logging enabled for auth failures and privileged actions

## Verifying the Auth Layer

The interceptors are covered by tests in
`services/api-gateway/tests/test_grpc_security.py`:

- Server interceptor rejects missing/invalid tokens, accepts valid tokens,
  and exempts health checks.
- Client interceptor augments call metadata with the token.
- Channel/credential helpers degrade gracefully without TLS configured.

```bash
cd services/api-gateway
PYTHONPATH=src:src/gen python3 -m pytest tests/test_grpc_security.py -v
```
