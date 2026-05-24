# Istio Service Mesh for GALILEO

Complete Istio configuration for GALILEO microservices with mTLS, traffic management, and security policies.

## Overview

Istio provides:
- **mTLS**: Mutual TLS between all services
- **Traffic Management**: Intelligent routing, retries, timeouts
- **Security**: JWT validation, RBAC, network policies
- **Observability**: Distributed tracing, metrics, logs
- **Resilience**: Circuit breaking, outlier detection, fault injection

## Architecture

```
Internet
    │
    ▼
┌─────────────────┐
│ Istio Gateway   │ (TLS termination)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  VirtualService │ (Routing rules)
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌─────┐   ┌─────┐
│API  │   │API  │ (Load balanced)
│GW v1│   │GW v2│
└──┬──┘   └──┬──┘
   │  mTLS   │
   └─────┬───┘
         │
    ┌────┴────┬───────┬───────┐
    ▼         ▼       ▼       ▼
  Data       ML    Invers  Control
  Service   Svc    Svc     Svc
  (gRPC)   (gRPC) (gRPC)  (gRPC)
    │         │       │       │
    └─────────┴───────┴───────┘
              │
         ┌────┴────┬────┐
         ▼         ▼    ▼
       Postgres  Redis S3
```

## Installation

### 1. Install Istio CLI

```bash
curl -L https://istio.io/downloadIstio | sh -
cd istio-*
export PATH=$PWD/bin:$PATH
```

### 2. Install Istio

```bash
# Production profile with HA
istioctl install --set profile=production -y

# Verify installation
kubectl get pods -n istio-system
```

### 3. Enable Sidecar Injection

```bash
# Label namespace for automatic injection
kubectl label namespace default istio-injection=enabled

# Verify label
kubectl get namespace -L istio-injection
```

### 4. Deploy GALILEO with Istio

```bash
# Apply Istio configurations
kubectl apply -f deploy/istio/

# Deploy application
helm install galileo deploy/helm/galileo \
  --namespace default \
  --set serviceMesh.enabled=true \
  --set serviceMesh.provider=istio
```

## Configuration Files

### gateway.yaml
- **Ingress Gateway**: TLS termination, HTTP→HTTPS redirect
- **Egress Gateway**: Controlled external access

**Features**:
- TLS 1.3 enforcement
- SNI-based routing
- Multiple hostnames support

### virtualservices.yaml
- **Routing Rules**: Path-based, header-based routing
- **Retries**: Automatic retry on failures
- **Timeouts**: Per-route timeout configuration
- **CORS**: Cross-origin resource sharing
- **Canary Deployments**: Gradual rollout with traffic splitting

**Example - ML Service Canary**:
- 90% traffic → v1
- 10% traffic → v2
- Header-based override: `x-version: v2` → 100% v2

### destinationrules.yaml
- **Load Balancing**: LEAST_REQUEST, ROUND_ROBIN, CONSISTENT_HASH
- **Connection Pooling**: TCP and HTTP/2 limits
- **Circuit Breaking**: Outlier detection and ejection
- **mTLS**: ISTIO_MUTUAL mode

**Circuit Breaker Settings**:
- Data Service: 3 consecutive errors, 20s interval
- ML Service: 5 consecutive errors, 30s interval
- Inversion Service: 2 consecutive errors, 60s interval

### security.yaml
- **PeerAuthentication**: Enforce mTLS (STRICT mode)
- **RequestAuthentication**: JWT validation
- **AuthorizationPolicy**: RBAC and access control
- **NetworkPolicy**: Kubernetes network segmentation

**Security Layers**:
1. Istio mTLS (service-to-service)
2. JWT authentication (external→API Gateway)
3. RBAC (role-based access)
4. Network policies (pod-level firewall)

## Traffic Management

### Canary Deployments

Deploy new version gradually:

```yaml
# 95% v1, 5% v2
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: ml-service
spec:
  http:
    - route:
        - destination:
            host: galileo-ml-service
            subset: v1
          weight: 95
        - destination:
            host: galileo-ml-service
            subset: v2
          weight: 5
```

Monitor metrics, then increase v2 traffic:
- 5% → 10% → 25% → 50% → 100%

### A/B Testing

Route specific users to new version:

```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: ab-test
spec:
  http:
    - match:
        - headers:
            user-group:
              exact: beta-testers
      route:
        - destination:
            host: galileo-ml-service
            subset: v2
    - route:
        - destination:
            host: galileo-ml-service
            subset: v1
```

### Fault Injection

Test resilience with fault injection:

```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: fault-injection-test
spec:
  http:
    - fault:
        delay:
          percentage:
            value: 10.0
          fixedDelay: 5s
        abort:
          percentage:
            value: 5.0
          httpStatus: 503
      route:
        - destination:
            host: galileo-data-service
```

## Security

### mTLS Configuration

**Verify mTLS is enabled**:

```bash
# Check peer authentication
kubectl get peerauthentication -n default

# Verify mTLS for a pod
istioctl authn tls-check <pod-name> -n default
```

**mTLS Modes**:
- `STRICT`: Only mTLS allowed (internal services)
- `PERMISSIVE`: Both mTLS and plaintext (API Gateway)
- `DISABLE`: No mTLS (databases)

### JWT Authentication

**Configure JWT issuer**:

1. Generate JWKS (JSON Web Key Set)
2. Host at `https://galileo.example.com/.well-known/jwks.json`
3. Update RequestAuthentication in `security.yaml`

**Test JWT authentication**:

```bash
# Valid JWT
curl -H "Authorization: Bearer $VALID_JWT" \
  https://api.galileo.example.com/api/v1/satellites

# Invalid JWT (should fail)
curl -H "Authorization: Bearer invalid" \
  https://api.galileo.example.com/api/v1/satellites
```

### Authorization Policies

**Service-to-service access control**:

```yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: data-service-policy
spec:
  selector:
    matchLabels:
      app: galileo-data-service
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - "cluster.local/ns/default/sa/galileo-api-gateway"
```

Only API Gateway can access Data Service.

## Observability

### Distributed Tracing (Jaeger)

**Enable tracing**:

```bash
# Install Jaeger addon
kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.20/samples/addons/jaeger.yaml

# Access Jaeger UI
istioctl dashboard jaeger
```

**Trace propagation**:
- Automatic with Istio sidecars
- Headers: `x-request-id`, `x-b3-traceid`, `x-b3-spanid`

### Metrics (Prometheus)

**Install Prometheus**:

```bash
kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.20/samples/addons/prometheus.yaml
```

**Key metrics**:
- `istio_requests_total`: Request count
- `istio_request_duration_milliseconds`: Latency
- `istio_tcp_connections_opened_total`: TCP connections

**Query example**:

```promql
# Request rate
rate(istio_requests_total{destination_service="galileo-data-service"}[5m])

# P95 latency
histogram_quantile(0.95, 
  rate(istio_request_duration_milliseconds_bucket[5m])
)
```

### Dashboards (Kiali)

**Install Kiali**:

```bash
kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.20/samples/addons/kiali.yaml

# Access Kiali UI
istioctl dashboard kiali
```

**Kiali features**:
- Service graph visualization
- Traffic flow analysis
- Configuration validation
- Health monitoring

## Performance

### Connection Pooling

Optimized for each service type:

**API Gateway** (high throughput):
- Max connections: 1000
- HTTP/2 max requests: 1000

**Data Service** (session affinity):
- Max connections: 500
- Consistent hash load balancing

**Inversion Service** (long-running):
- Max connections: 100
- Idle timeout: 10 minutes

### Circuit Breaking

Automatic failure detection and recovery:

```yaml
outlierDetection:
  consecutiveErrors: 5
  interval: 30s
  baseEjectionTime: 30s
  maxEjectionPercent: 50
```

**When 5 consecutive errors occur**:
- Pod is ejected for 30 seconds
- Traffic routed to healthy pods
- Auto-recovery after ejection period

## Troubleshooting

### Check Istio Configuration

```bash
# Validate configuration
istioctl analyze -n default

# Check proxy status
istioctl proxy-status

# View proxy config
istioctl proxy-config cluster <pod-name> -n default
```

### Debug mTLS Issues

```bash
# Check mTLS status
istioctl authn tls-check <pod-name> -n default

# View certificates
istioctl proxy-config secret <pod-name> -n default

# Check peer authentication
kubectl get peerauthentication -n default -o yaml
```

### Debug Routing Issues

```bash
# Describe virtual service
kubectl describe virtualservice api-gateway -n default

# Check destination rule
kubectl describe destinationrule data-service -n default

# View envoy config
istioctl proxy-config route <pod-name> -n default
```

### Common Issues

**1. 503 Service Unavailable**
- Check circuit breaker settings
- Verify pods are running: `kubectl get pods`
- Check outlier detection: `istioctl proxy-config endpoints`

**2. Connection Refused**
- Verify service exists: `kubectl get svc`
- Check port configuration
- Ensure sidecar is injected: `kubectl get pod -o jsonpath='{.spec.containers[*].name}'`

**3. mTLS Handshake Failure**
- Check PeerAuthentication mode
- Verify certificates: `istioctl proxy-config secret`
- Check service account permissions

## Best Practices

### 1. **Gradual Rollouts**
- Start with 5% canary traffic
- Monitor error rates and latency
- Increase gradually: 10% → 25% → 50% → 100%

### 2. **Circuit Breaker Tuning**
- Set conservative thresholds initially
- Monitor ejection metrics
- Adjust based on observed patterns

### 3. **Timeout Configuration**
- Match timeout to 95th percentile latency
- Add buffer for retries
- Set per-route based on operation

### 4. **Security Hardening**
- Use STRICT mTLS for all internal services
- Implement least-privilege authorization
- Regular certificate rotation

### 5. **Resource Limits**
- Set connection pool limits
- Configure circuit breakers
- Monitor resource usage

## Monitoring

### Health Metrics

```bash
# Service mesh health
kubectl get pods -n istio-system

# Gateway status
kubectl get gateway -n default

# Virtual service status
kubectl get virtualservice -n default
```

### Performance Metrics

Key SLIs to monitor:
- Request success rate: > 99.9%
- P95 latency: < 100ms
- Circuit breaker trips: < 1/hour
- mTLS success rate: 100%

### Alerts

Recommended Prometheus alerts:

```yaml
# High error rate
- alert: HighErrorRate
  expr: |
    rate(istio_requests_total{response_code=~"5.."}[5m]) > 0.05
  annotations:
    summary: "High error rate detected"

# High latency
- alert: HighLatency
  expr: |
    histogram_quantile(0.95, 
      rate(istio_request_duration_milliseconds_bucket[5m])
    ) > 1000
  annotations:
    summary: "P95 latency > 1s"
```

## Maintenance

### Upgrade Istio

```bash
# Download new version
istioctl upgrade --set profile=production

# Verify upgrade
istioctl version
```

### Rotate Certificates

```bash
# Check cert expiry
istioctl proxy-config secret <pod-name> -o json

# Force cert rotation
kubectl delete pod -n istio-system -l app=istiod
```

### Backup Configuration

```bash
# Export all Istio resources
kubectl get gateway,virtualservice,destinationrule,peerauthentication -n default -o yaml > istio-backup.yaml
```

## References

- [Istio Documentation](https://istio.io/latest/docs/)
- [Traffic Management](https://istio.io/latest/docs/tasks/traffic-management/)
- [Security](https://istio.io/latest/docs/tasks/security/)
- [Observability](https://istio.io/latest/docs/tasks/observability/)
