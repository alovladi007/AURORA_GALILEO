# GALILEO V2.0 - Complete Production Implementation Prompt

**Purpose**: Master implementation guide for transforming GALILEO into a best-in-class production platform
**Duration**: 6 months (24 weeks)
**Team Size**: 9 FTE
**Budget**: $2.5M
**Target**: 99.99% availability, 10,000+ concurrent users, enterprise-grade security

---

## How to Use This Prompt

This document is structured as actionable prompts for each phase. You can:

1. **Use with AI agents**: Copy each phase as a prompt to Claude/GPT for implementation
2. **Use for planning**: Track progress week-by-week
3. **Use for delegation**: Assign phases to team members
4. **Use for reviews**: Verify completion criteria

Each phase includes:
- **Objective**: What you're building
- **Prerequisites**: What must be done first
- **Tasks**: Specific implementation steps
- **Deliverables**: Concrete outputs
- **Success Criteria**: How to verify completion
- **Time Estimate**: Per-task duration
- **Resources**: Required skills/tools

---

# MONTH 1: Foundation & Critical Security

## Week 1: Security Hardening (40 hours)

### Prompt 1.1: Implement Security Headers Middleware

**Objective**: Add comprehensive security headers to all API responses to prevent XSS, clickjacking, and MIME sniffing attacks.

**Prerequisites**:
- FastAPI application running
- Understanding of OWASP Top 10
- Access to api/main.py and ops/main.py

**Tasks**:
1. Create security headers middleware function
2. Add Content-Security-Policy (CSP) with strict directives
3. Configure HTTP Strict Transport Security (HSTS) with 1-year max-age
4. Set X-Frame-Options to DENY
5. Add X-Content-Type-Options: nosniff
6. Configure Referrer-Policy: strict-origin-when-cross-origin
7. Add Permissions-Policy to restrict browser features
8. Test with securityheaders.com (target: A+ rating)

**Deliverables**:
- `api/main.py` with security_headers_middleware
- `ops/main.py` with security_headers_middleware
- Security headers tests in `tests/security/test_headers.py`
- Documentation in `docs/security/HEADERS.md`

**Success Criteria**:
- All endpoints return required security headers
- securityheaders.com scan shows A+ rating
- No CSP violations in browser console
- Tests passing with 100% coverage

**Time**: 4 hours
**Skills**: Python, FastAPI, Security

---

### Prompt 1.2: Production Secrets Validation

**Objective**: Enforce strong secrets in production environment to prevent weak credentials.

**Tasks**:
1. Create `validate_production_secrets()` function
2. Define required secrets list (DATABASE_URL, JWT_SECRET_KEY, etc.)
3. Implement minimum length validation (32+ chars for keys)
4. Add startup-time validation that fails fast
5. Provide clear error messages
6. Add environment-specific behavior (production vs dev)
7. Create secret generation script

**Deliverables**:
- `validate_production_secrets()` in api/main.py and ops/main.py
- `scripts/generate-secrets.sh` for secure secret generation
- `.env.example` with all required variables
- `docs/security/SECRETS.md` documentation

**Success Criteria**:
- Application fails to start in production with weak/missing secrets
- All secrets are minimum 32 characters
- No secrets logged or exposed in errors
- Clear instructions for secret rotation

**Time**: 2 hours
**Skills**: Python, DevOps

---

### Prompt 1.3: Automated Security Scanning Pipeline

**Objective**: Set up continuous security scanning in CI/CD to catch vulnerabilities early.

**Tasks**:
1. Create `.github/workflows/security.yml`
2. Add pip-audit for Python dependency scanning
3. Add safety for additional dependency checks
4. Configure Trivy for container vulnerability scanning
5. Add Gitleaks for secret detection
6. Configure CodeQL for static analysis (Python & JS)
7. Add license compliance checking (pip-licenses)
8. Schedule daily scans + run on every PR
9. Configure SARIF upload to GitHub Security tab
10. Add Slack notifications for critical findings

**Deliverables**:
- `.github/workflows/security.yml`
- Configuration files for each scanner
- Documentation in `docs/security/SCANNING.md`
- Initial vulnerability remediation

**Success Criteria**:
- All security scans run on every PR
- Daily scheduled scans complete successfully
- Zero critical/high vulnerabilities
- Results visible in GitHub Security tab
- Slack notifications working

**Time**: 6 hours
**Skills**: GitHub Actions, Security, CI/CD

---

### Prompt 1.4: Implement Circuit Breaker Pattern

**Objective**: Prevent cascading failures with circuit breakers for external service calls.

**Tasks**:
1. Create `api/circuit_breaker.py` module
2. Implement CircuitBreaker class with CLOSED/OPEN/HALF_OPEN states
3. Add configurable failure threshold and timeout
4. Implement decorator for easy application
5. Add metrics for circuit state changes
6. Apply to database calls, Redis calls, external APIs
7. Create circuit breaker dashboard in Grafana
8. Add tests for state transitions

**Deliverables**:
- `api/circuit_breaker.py` (complete implementation)
- Unit tests in `tests/unit/test_circuit_breaker.py`
- Integration tests
- Grafana dashboard for circuit breakers
- Documentation in `docs/patterns/CIRCUIT_BREAKER.md`

**Success Criteria**:
- Circuit opens after configured failures
- Successful recovery in HALF_OPEN state
- Metrics exported to Prometheus
- Dashboard shows real-time state
- Test coverage > 90%

**Time**: 8 hours
**Skills**: Python, Distributed Systems, Design Patterns

---

### Prompt 1.5: Request Timeout & Graceful Shutdown

**Objective**: Prevent hanging requests and ensure clean service termination.

**Tasks**:
1. Add request timeout middleware (30s default)
2. Return 504 Gateway Timeout for exceeded requests
3. Implement startup event handler
4. Implement shutdown event handler
5. Close WebSocket connections gracefully on shutdown
6. Drain in-flight requests before terminating
7. Close database connections cleanly
8. Stop Celery workers gracefully
9. Add SIGTERM handler with 30s grace period
10. Test shutdown behavior

**Deliverables**:
- `timeout_middleware` in api/main.py
- `startup_event` and `shutdown_event` handlers
- Graceful shutdown for all services
- Tests for timeout and shutdown behavior

**Success Criteria**:
- Long-running requests timeout cleanly
- No data loss during shutdown
- WebSocket clients notified before disconnect
- Database connections closed properly
- Kubernetes pod termination clean

**Time**: 6 hours
**Skills**: Python, FastAPI, Async Programming

---

### Prompt 1.6: Structured JSON Logging

**Objective**: Implement structured logging with correlation IDs for distributed tracing.

**Tasks**:
1. Configure Python logging for JSON output
2. Add correlation ID middleware
3. Generate UUID for each request
4. Log request start, completion, and errors
5. Include duration, status, method, path
6. Propagate correlation ID via X-Correlation-ID header
7. Add to all downstream service calls
8. Update Celery tasks to include correlation ID
9. Configure log aggregation (Loki/ELK ready)

**Deliverables**:
- Structured JSON logging in all services
- Correlation ID middleware
- Updated Celery task logging
- Log aggregation configuration
- Documentation in `docs/observability/LOGGING.md`

**Success Criteria**:
- All logs in JSON format
- Each request has unique correlation ID
- Logs traceable across services
- Compatible with Loki/ELK queries
- Sensitive data not logged

**Time**: 4 hours
**Skills**: Python, Logging, Observability

---

## Week 2: Reliability & Resilience (40 hours)

### Prompt 2.1: Database Backup Automation

**Objective**: Implement automated PostgreSQL backups with retention and S3 upload.

**Tasks**:
1. Create `scripts/backup-db.sh` script
2. Add docker-compose service for backups
3. Configure pg_dump with compression
4. Implement retention policy (7 days local, 30 days S3)
5. Add S3 upload functionality
6. Create restore script
7. Schedule with cron (daily at 2 AM)
8. Add backup verification
9. Test restore procedure
10. Document RPO/RTO

**Deliverables**:
- `scripts/backup-db.sh`
- `scripts/restore-db.sh`
- Docker service in `docker-compose.yml`
- Backup verification script
- Documentation in `docs/operations/BACKUPS.md`

**Success Criteria**:
- Daily backups complete successfully
- Backups uploaded to S3
- Old backups pruned automatically
- Restore tested and working
- RPO < 24 hours, RTO < 1 hour

**Time**: 6 hours
**Skills**: Bash, PostgreSQL, AWS S3

---

### Prompt 2.2: Dead Letter Queue for Celery

**Objective**: Handle failed tasks gracefully with DLQ and retry logic.

**Tasks**:
1. Configure Celery task routing
2. Add separate queues (default, simulation, ml, dlq)
3. Implement `handle_failed_task` function
4. Configure retry policy (3 retries, exponential backoff)
5. Enable late acknowledgment
6. Add task result extended info
7. Set result expiration (24h)
8. Create monitoring dashboard for DLQ
9. Add alerts for DLQ depth
10. Document recovery procedures

**Deliverables**:
- Updated Celery configuration in `ops/tasks.py`
- DLQ handler function
- Grafana dashboard for queues
- Alert rules for DLQ
- Recovery runbook

**Success Criteria**:
- Failed tasks go to DLQ after max retries
- DLQ tasks can be replayed
- Metrics show queue depths
- Alerts fire on DLQ growth
- Recovery procedure documented

**Time**: 6 hours
**Skills**: Celery, Redis, Task Queues

---

### Prompt 2.3: Resource Limits & Quotas

**Objective**: Set CPU/memory limits on all containers to prevent resource exhaustion.

**Tasks**:
1. Audit current resource usage per service
2. Define resource requests (guaranteed)
3. Define resource limits (maximum)
4. Update docker-compose.yml with deploy.resources
5. Add Kubernetes resource specs
6. Configure HPA thresholds
7. Add resource monitoring dashboards
8. Test under load
9. Document scaling policies

**Deliverables**:
- Resource limits in `docker-compose.yml`
- Kubernetes resource specs in Helm values
- Grafana dashboard for resource usage
- Documentation in `docs/operations/RESOURCES.md`

**Success Criteria**:
- All containers have CPU/memory limits
- No OOM kills under normal load
- HPA scales based on CPU/memory
- Resource usage visible in dashboards
- Load tests show stable behavior

**Time**: 4 hours
**Skills**: Docker, Kubernetes, Performance

---

### Prompt 2.4: Prometheus AlertManager Setup

**Objective**: Configure alerting infrastructure with severity-based routing.

**Tasks**:
1. Deploy AlertManager service
2. Configure alertmanager.yml with routes
3. Set up Slack integration
4. Configure PagerDuty for critical alerts (optional)
5. Define alert severity levels (critical, high, warning)
6. Add inhibit rules to prevent alert fatigue
7. Configure email notifications
8. Test alert delivery
9. Document escalation policies

**Deliverables**:
- AlertManager deployment
- `monitoring/alertmanager/alertmanager.yml`
- Slack/PagerDuty integrations
- Escalation policy document
- Alert testing procedures

**Success Criteria**:
- AlertManager running and accessible
- Alerts route to correct channels
- No alert fatigue (inhibit rules working)
- Acknowledgment workflow defined
- 24/7 on-call rotation set up

**Time**: 6 hours
**Skills**: Prometheus, AlertManager, Monitoring

---

### Prompt 2.5: SLO-Based Alert Rules

**Objective**: Define and implement Service Level Objectives with corresponding alerts.

**Tasks**:
1. Define SLOs:
   - Availability: 99.9% (43.2 min/month)
   - Latency p99: < 500ms
   - Latency p95: < 300ms
   - Error rate: < 0.1%
2. Calculate error budgets
3. Create alert rules for SLO violations
4. Add multi-window, multi-burn-rate alerts
5. Define service health alerts
6. Add infrastructure alerts (CPU, memory, disk)
7. Create database-specific alerts
8. Add Redis alerts
9. Configure Celery worker alerts
10. Test all alerts

**Deliverables**:
- `monitoring/alertmanager/alert-rules.yml`
- SLO documentation
- Error budget calculations
- Alert runbooks

**Success Criteria**:
- All SLOs have alerts
- Multi-burn-rate alerts working
- Runbooks linked from alerts
- No false positives
- Mean time to detect < 1 min

**Time**: 8 hours
**Skills**: Prometheus, SRE, PromQL

---

### Prompt 2.6: Grafana SLO Dashboard

**Objective**: Create comprehensive dashboard showing real-time SLO compliance.

**Tasks**:
1. Design dashboard layout
2. Create availability gauge (99.9% target)
3. Add p99/p95 latency gauges
4. Show error rate
5. Add request rate graphs
6. Show response time percentiles
7. Add service health table
8. Create HTTP status distribution
9. Add resource usage panels
10. Configure auto-refresh

**Deliverables**:
- `monitoring/grafana/dashboards/galileo-slo-dashboard.json`
- Dashboard provisioning configuration
- Screenshot for documentation
- Dashboard guide

**Success Criteria**:
- Dashboard accessible in Grafana
- All panels show real data
- SLO gauges accurate
- Auto-refresh working
- Mobile responsive

**Time**: 6 hours
**Skills**: Grafana, PromQL, Visualization

---

## Week 3: Authentication & Authorization (40 hours)

### Prompt 3.1: JWT Authentication Hardening

**Objective**: Strengthen JWT-based authentication with best practices.

**Tasks**:
1. Audit current JWT implementation
2. Implement token rotation
3. Add refresh tokens (separate from access)
4. Set short access token TTL (15 min)
5. Add JWT blacklist for revocation
6. Implement secure cookie storage option
7. Add device fingerprinting
8. Log all authentication events
9. Add brute force protection
10. Implement account lockout

**Deliverables**:
- Hardened JWT in `api/auth.py`
- Refresh token endpoint
- Token blacklist (Redis-based)
- Authentication event logging
- Tests with 95%+ coverage

**Success Criteria**:
- Tokens rotate on refresh
- Revocation works immediately
- No tokens in URLs
- Failed logins tracked
- Account lockout after 5 failures

**Time**: 10 hours
**Skills**: Python, JWT, Security, OAuth2

---

### Prompt 3.2: Role-Based Access Control (RBAC)

**Objective**: Implement comprehensive RBAC with granular permissions.

**Tasks**:
1. Define roles: Admin, Analyst, Researcher, Viewer
2. Define permission enum with all actions
3. Create role-permission mappings
4. Implement permission decorators
5. Add permission checks to all endpoints
6. Create role management UI
7. Add permission audit log
8. Implement permission inheritance
9. Add tests for each role
10. Document RBAC model

**Deliverables**:
- `api/rbac.py` with complete RBAC implementation
- Database migration for roles/permissions
- Admin UI for role management
- Permission audit logging
- RBAC documentation

**Success Criteria**:
- All endpoints check permissions
- Users have appropriate access
- Admin can manage roles
- Audit log shows all changes
- 100% endpoint coverage

**Time**: 12 hours
**Skills**: Python, Authorization, Database

---

### Prompt 3.3: Rate Limiting Enhancement

**Objective**: Implement sophisticated rate limiting with user-based and endpoint-specific limits.

**Tasks**:
1. Configure SlowAPI with multiple strategies
2. Add per-user rate limits (authenticated)
3. Add per-IP rate limits (anonymous)
4. Set endpoint-specific limits (auth: 5/min, API: 100/min)
5. Implement sliding window algorithm
6. Add rate limit headers to responses
7. Create rate limit bypass for admins
8. Add monitoring dashboard
9. Configure alerts for abuse
10. Document limits

**Deliverables**:
- Enhanced rate limiting in api/main.py
- Per-endpoint rate limit decorators
- Rate limit dashboard
- Documentation in `docs/security/RATE_LIMITING.md`

**Success Criteria**:
- Rate limits enforced consistently
- 429 responses include retry-after
- Admins can bypass limits
- Dashboard shows top consumers
- No legitimate user impact

**Time**: 6 hours
**Skills**: Python, Redis, Rate Limiting

---

### Prompt 3.4: API Key Management

**Objective**: Add API key authentication for service-to-service communication.

**Tasks**:
1. Design API key schema (key, name, scopes, expires_at)
2. Create database migration
3. Implement key generation (cryptographically secure)
4. Add key validation middleware
5. Implement key rotation
6. Add scope-based authorization
7. Create UI for key management
8. Add usage tracking per key
9. Implement key revocation
10. Add rate limits per key

**Deliverables**:
- API key database schema
- Key generation/validation code
- Management API endpoints
- Admin UI for keys
- Usage analytics

**Success Criteria**:
- Keys are cryptographically secure
- Scope-based access enforced
- Keys can be rotated/revoked
- Usage tracked accurately
- UI intuitive for users

**Time**: 12 hours
**Skills**: Python, Cryptography, Database

---

## Week 4: HTTPS/TLS & Final Security (40 hours)

### Prompt 4.1: Production Nginx Configuration

**Objective**: Configure Nginx as production-grade reverse proxy with TLS.

**Tasks**:
1. Create `ops/nginx/nginx-tls.conf`
2. Configure TLS 1.2/1.3 only
3. Add modern cipher suite (Mozilla Intermediate)
4. Enable OCSP stapling
5. Configure SSL session caching
6. Add HTTP to HTTPS redirect
7. Configure HTTP/2
8. Set up upstream load balancing
9. Add rate limiting zones
10. Configure WebSocket support
11. Add health check endpoints
12. Configure logging (JSON format)
13. Test SSL configuration with SSLLabs

**Deliverables**:
- `ops/nginx/nginx-tls.conf`
- TLS certificates directory
- Logging configuration
- SSL Labs A+ rating

**Success Criteria**:
- All traffic uses HTTPS
- TLS 1.3 supported
- A+ rating on SSLLabs
- HSTS preload ready
- HTTP/2 active

**Time**: 8 hours
**Skills**: Nginx, TLS/SSL, Networking

---

### Prompt 4.2: Let's Encrypt Automation

**Objective**: Automate SSL certificate provisioning and renewal.

**Tasks**:
1. Create `scripts/setup-letsencrypt.sh`
2. Install certbot
3. Implement certificate request flow
4. Configure systemd timer for renewal
5. Add deploy hook to reload Nginx
6. Set up staging environment for testing
7. Configure DNS challenge (alternative)
8. Add certificate monitoring
9. Create renewal failure alerts
10. Test renewal process

**Deliverables**:
- `scripts/setup-letsencrypt.sh`
- systemd service and timer
- Certificate monitoring
- Documentation

**Success Criteria**:
- Certificates auto-renew before expiry
- Zero downtime during renewal
- Alerts on renewal failure
- 90-day rotation working
- Multi-domain support

**Time**: 6 hours
**Skills**: Bash, Let's Encrypt, systemd

---

### Prompt 4.3: CSRF Protection

**Objective**: Implement CSRF protection using double-submit cookie pattern.

**Tasks**:
1. Create `api/csrf.py` module
2. Implement CSRFProtection class
3. Generate cryptographically secure tokens
4. Sign tokens with HMAC-SHA256
5. Implement cookie setting (HttpOnly, Secure, SameSite=Strict)
6. Add validation middleware
7. Skip CSRF for safe methods (GET, HEAD, OPTIONS)
8. Skip for Bearer token requests
9. Add UI integration helpers
10. Write comprehensive tests

**Deliverables**:
- `api/csrf.py` (complete)
- Tests in `tests/security/test_csrf.py`
- UI integration documentation
- Frontend helper code

**Success Criteria**:
- CSRF tokens generated correctly
- All state-changing requests protected
- No false positives
- 100% test coverage
- UI integration documented

**Time**: 8 hours
**Skills**: Python, Web Security, HMAC

---

### Prompt 4.4: File Upload Validation

**Objective**: Implement comprehensive file upload security.

**Tasks**:
1. Create `api/file_validation.py`
2. Implement MIME type validation
3. Add magic number verification (libmagic)
4. Configure size limits (per category)
5. Blacklist dangerous extensions
6. Sanitize filenames
7. Add path traversal prevention
8. Integrate ClamAV for virus scanning
9. Create category-specific validators (image, document, data)
10. Add tests for malicious uploads

**Deliverables**:
- `api/file_validation.py` (complete)
- ClamAV integration
- Tests with malicious file samples
- Documentation

**Success Criteria**:
- All upload paths validated
- No executable uploads
- Virus scanning working
- File type spoofing prevented
- Size limits enforced

**Time**: 10 hours
**Skills**: Python, File Security, ClamAV

---

### Prompt 4.5: Penetration Testing Preparation

**Objective**: Prepare platform for external security audit.

**Tasks**:
1. Run OWASP ZAP automated scan
2. Run Burp Suite scan
3. Test all authentication flows
4. Test authorization (privilege escalation)
5. Test injection attacks (SQL, command, XSS)
6. Test CSRF protection
7. Test session management
8. Test cryptography
9. Document findings
10. Remediate critical issues

**Deliverables**:
- Penetration test report
- Remediation plan
- Updated security documentation
- Compliance evidence

**Success Criteria**:
- Zero critical vulnerabilities
- All high severity fixed
- Documentation complete
- Ready for external audit
- Security training completed

**Time**: 8 hours
**Skills**: Security Testing, OWASP, Penetration Testing

---

# MONTH 2: Infrastructure & Database

## Week 5: HashiCorp Vault Deployment (40 hours)

### Prompt 5.1: Vault Server Deployment

**Objective**: Deploy HashiCorp Vault for centralized secrets management.

**Tasks**:
1. Create Vault Helm chart configuration
2. Deploy Vault in HA mode (3 replicas)
3. Configure Raft storage backend
4. Initialize Vault and store unseal keys securely
5. Configure auto-unseal with cloud KMS
6. Set up Vault audit logging
7. Configure TLS
8. Set up backup procedures
9. Create Vault namespaces
10. Document operational procedures

**Deliverables**:
- Vault deployment in `deploy/vault/`
- Initialization scripts
- Backup procedures
- Disaster recovery plan
- Operational runbooks

**Success Criteria**:
- Vault running in HA mode
- Auto-unseal working
- Audit logs flowing
- Backups automated
- Disaster recovery tested

**Time**: 16 hours
**Skills**: HashiCorp Vault, Kubernetes, Cryptography

---

### Prompt 5.2: Vault Integration

**Objective**: Integrate Vault with all services for secret management.

**Tasks**:
1. Create Vault policies for each service
2. Configure Kubernetes auth method
3. Set up Vault Agent injector
4. Migrate secrets from environment variables
5. Implement secret rotation policies
6. Add dynamic database credentials
7. Set up transit encryption for sensitive data
8. Configure SSH certificate authority
9. Add audit logging
10. Test failover scenarios

**Deliverables**:
- Vault policies per service
- Kubernetes auth configuration
- Migration scripts
- Application code updates
- Integration tests

**Success Criteria**:
- All secrets in Vault
- Dynamic credentials working
- Secret rotation automated
- Zero secrets in code/env
- Audit trail complete

**Time**: 16 hours
**Skills**: Vault, Kubernetes, Secrets Management

---

### Prompt 5.3: Secrets Rotation Automation

**Objective**: Automate rotation of all secrets (database, API keys, JWT).

**Tasks**:
1. Identify all rotatable secrets
2. Implement rotation lambdas/jobs
3. Configure rotation schedules:
   - Database passwords: 30 days
   - API keys: 90 days
   - JWT signing keys: 60 days
   - TLS certificates: 60 days
4. Add zero-downtime rotation
5. Update applications to handle rotation
6. Add rotation monitoring
7. Test rotation procedures
8. Document recovery procedures

**Deliverables**:
- Rotation jobs/lambdas
- Application updates for rotation
- Monitoring dashboards
- Rotation runbooks

**Success Criteria**:
- All secrets rotate automatically
- Zero downtime during rotation
- Rotation success tracked
- Failed rotations alert
- Manual rotation possible

**Time**: 8 hours
**Skills**: Automation, Secrets Management, DevOps

---

## Week 6: Database High Availability (40 hours)

### Prompt 6.1: PostgreSQL Read Replicas

**Objective**: Deploy PostgreSQL with read replicas for scalability.

**Tasks**:
1. Configure primary PostgreSQL instance
2. Deploy 2 read replicas (different AZs)
3. Configure streaming replication
4. Set up replication lag monitoring
5. Configure connection pooling (PgBouncer)
6. Update application for read/write splitting
7. Add failover automation
8. Test replica promotion
9. Configure backup from replicas
10. Document operational procedures

**Deliverables**:
- PostgreSQL HA deployment
- PgBouncer configuration
- Application updates for splitting
- Failover automation
- Operational runbooks

**Success Criteria**:
- Primary + 2 replicas running
- Replication lag < 100ms
- Read queries hit replicas
- Failover < 30 seconds
- Backups not impacting primary

**Time**: 16 hours
**Skills**: PostgreSQL, Replication, HA

---

### Prompt 6.2: TimescaleDB Setup

**Objective**: Configure TimescaleDB for time-series satellite data.

**Tasks**:
1. Install TimescaleDB extension
2. Identify time-series tables
3. Create hypertables for sensor data
4. Configure chunk intervals
5. Set up compression policies
6. Configure retention policies (1 year)
7. Create continuous aggregates
8. Migrate existing data
9. Update queries to use TimescaleDB features
10. Benchmark performance

**Deliverables**:
- TimescaleDB hypertables
- Compression policies
- Continuous aggregates
- Migration scripts
- Performance benchmarks

**Success Criteria**:
- 10x query performance improvement
- 90% storage reduction (compression)
- Old data archived
- Aggregates pre-computed
- No application changes needed

**Time**: 12 hours
**Skills**: PostgreSQL, TimescaleDB, Time-Series

---

### Prompt 6.3: Database Performance Tuning

**Objective**: Optimize PostgreSQL for production workload.

**Tasks**:
1. Analyze current performance
2. Tune postgresql.conf:
   - shared_buffers (25% of RAM)
   - effective_cache_size (75% of RAM)
   - maintenance_work_mem
   - max_connections
   - random_page_cost
3. Add missing indexes
4. Optimize slow queries
5. Configure autovacuum
6. Set up query logging
7. Install pg_stat_statements
8. Create performance dashboard
9. Document tuning decisions

**Deliverables**:
- Optimized postgresql.conf
- Index migration files
- Performance dashboard
- Query optimization document
- Tuning playbook

**Success Criteria**:
- p99 query time < 50ms
- No queries > 1 second
- Cache hit ratio > 95%
- No table bloat
- Vacuum running smoothly

**Time**: 12 hours
**Skills**: PostgreSQL, Performance Tuning, SQL

---

## Week 7: OpenTelemetry & Distributed Tracing (40 hours)

### Prompt 7.1: OpenTelemetry Instrumentation

**Objective**: Add distributed tracing across all services.

**Tasks**:
1. Install OpenTelemetry SDK
2. Configure OTLP exporter
3. Add auto-instrumentation for FastAPI
4. Add auto-instrumentation for SQLAlchemy
5. Add auto-instrumentation for Redis
6. Add auto-instrumentation for Celery
7. Add custom spans for business logic
8. Configure sampling (10% in production)
9. Add baggage propagation
10. Test trace correlation

**Deliverables**:
- OpenTelemetry SDK integration
- Auto-instrumentation configured
- Custom spans in business logic
- Sampling configuration
- Trace correlation tests

**Success Criteria**:
- All services instrumented
- Traces visible in Jaeger
- Cross-service correlation
- Performance overhead < 5%
- No sensitive data in traces

**Time**: 16 hours
**Skills**: OpenTelemetry, Distributed Systems, Observability

---

### Prompt 7.2: Jaeger Deployment & Configuration

**Objective**: Deploy Jaeger for trace storage and visualization.

**Tasks**:
1. Deploy Jaeger in production mode
2. Configure Elasticsearch backend
3. Set up trace retention (7 days)
4. Configure sampling strategies
5. Create custom dashboards
6. Add service dependency graphs
7. Configure alerts for high latency
8. Set up trace search
9. Document trace analysis
10. Train team on usage

**Deliverables**:
- Jaeger production deployment
- Elasticsearch backend
- Custom dashboards
- Trace analysis guide
- Training materials

**Success Criteria**:
- Jaeger accessible
- Traces stored 7 days
- Service map auto-generated
- Search performant
- Team trained

**Time**: 12 hours
**Skills**: Jaeger, Elasticsearch, Observability

---

### Prompt 7.3: APM Integration

**Objective**: Integrate Application Performance Monitoring (DataDog or New Relic).

**Tasks**:
1. Evaluate APM vendors (DataDog vs New Relic)
2. Set up account and API keys
3. Install APM agents
4. Configure custom metrics
5. Set up dashboards
6. Configure alerts
7. Add real user monitoring (RUM)
8. Configure error tracking
9. Set up synthetic monitoring
10. Configure log integration

**Deliverables**:
- APM deployment
- Custom dashboards
- Alert configurations
- RUM implementation
- Synthetic checks

**Success Criteria**:
- APM showing all services
- Custom metrics flowing
- Errors tracked automatically
- Synthetic checks passing
- ROI demonstrated

**Time**: 12 hours
**Skills**: APM, Monitoring, Performance

---

## Week 8: CSRF, File Upload, Final Phase 1 (40 hours)

### Prompt 8.1: Comprehensive Integration Testing

**Objective**: End-to-end testing of all Phase 1 features.

**Tasks**:
1. Create integration test suite
2. Test authentication flows
3. Test authorization (RBAC)
4. Test rate limiting
5. Test CSRF protection
6. Test file upload validation
7. Test circuit breakers
8. Test graceful shutdown
9. Test backup/restore
10. Generate test reports

**Deliverables**:
- Comprehensive test suite
- Test reports
- Code coverage > 85%
- Bug fixes
- Documentation updates

**Success Criteria**:
- All tests passing
- > 85% coverage
- No P0/P1 bugs
- Documentation complete
- Ready for staging

**Time**: 20 hours
**Skills**: Testing, Python, Quality Assurance

---

### Prompt 8.2: Phase 1 Documentation & Review

**Objective**: Document all Phase 1 changes and review with team.

**Tasks**:
1. Update README with new features
2. Create operational runbooks
3. Document configuration options
4. Create training materials
5. Conduct team review
6. Update API documentation
7. Create migration guide
8. Update deployment guide
9. Schedule security audit
10. Plan Phase 2 kickoff

**Deliverables**:
- Updated documentation
- Operational runbooks
- Training materials
- Migration guide
- Phase 2 plan

**Success Criteria**:
- All docs updated
- Team trained
- Runbooks tested
- Audit scheduled
- Phase 2 ready

**Time**: 20 hours
**Skills**: Technical Writing, Communication

---

# MONTH 3: Kubernetes & Microservices

## Week 9-10: Kubernetes Migration (80 hours)

### Prompt 9.1: Helm Chart Development

**Objective**: Create production-ready Helm charts for all services.

**Tasks**:
1. Initialize Helm chart structure
2. Create Chart.yaml with dependencies
3. Define values.yaml for each environment
4. Create deployment templates
5. Create service templates
6. Create ingress templates
7. Create configmap templates
8. Create secret templates (External Secrets)
9. Add HPA templates
10. Add PDB templates
11. Add NetworkPolicy templates
12. Add ServiceAccount templates
13. Test with helm lint and helm template
14. Test deployment in dev cluster
15. Document chart parameters

**Deliverables**:
- Complete Helm chart in `deploy/helm/galileo/`
- Values for dev/staging/production
- Documentation in `docs/k8s/HELM.md`
- Deployment scripts

**Success Criteria**:
- helm lint passes
- Chart deploys successfully
- All services running
- Configurable per environment
- Well-documented

**Time**: 40 hours
**Skills**: Helm, Kubernetes, YAML

---

### Prompt 9.2: HorizontalPodAutoscaler

**Objective**: Configure HPA for all services with appropriate metrics.

**Tasks**:
1. Install metrics-server
2. Configure HPA for API (3-10 pods, CPU 70%)
3. Configure HPA for Workers (4-20 pods, CPU 75%)
4. Configure HPA for UI (2-6 pods, CPU 70%)
5. Add custom metrics (Prometheus adapter)
6. Configure scaling based on RPS
7. Set scale-down policies
8. Add scale events to monitoring
9. Test scaling under load
10. Document scaling policies

**Deliverables**:
- HPA configurations
- Prometheus adapter setup
- Custom metrics
- Monitoring dashboards
- Documentation

**Success Criteria**:
- HPA scales on demand
- No flapping
- Scale-down works smoothly
- Custom metrics working
- Load tested

**Time**: 16 hours
**Skills**: Kubernetes, HPA, Metrics

---

### Prompt 9.3: Ingress & TLS

**Objective**: Configure Ingress controller with cert-manager for automatic TLS.

**Tasks**:
1. Install Nginx Ingress Controller
2. Install cert-manager
3. Configure Let's Encrypt ClusterIssuer
4. Create Ingress resources
5. Configure rate limiting annotations
6. Configure WAF rules
7. Set up DNS records
8. Test certificate provisioning
9. Configure HSTS
10. Test failover

**Deliverables**:
- Ingress controller deployment
- cert-manager configuration
- Ingress resources
- DNS configuration
- Documentation

**Success Criteria**:
- TLS auto-provisioned
- All services accessible
- A+ SSL Labs rating
- Rate limiting working
- HSTS configured

**Time**: 16 hours
**Skills**: Kubernetes, Ingress, TLS, DNS

---

### Prompt 9.4: Persistent Storage

**Objective**: Configure persistent storage for stateful services.

**Tasks**:
1. Configure storage classes
2. Create PVCs for data, checkpoints, logs
3. Configure StatefulSets for databases
4. Set up backup procedures
5. Test PV recovery
6. Configure storage monitoring
7. Document storage policies
8. Test resizing

**Deliverables**:
- Storage configurations
- StatefulSets
- Backup procedures
- Documentation

**Success Criteria**:
- Persistent volumes working
- Backups automated
- Storage monitored
- Resizing tested

**Time**: 8 hours
**Skills**: Kubernetes, Storage, StatefulSets

---

## Week 11-12: Terraform & Cloud Infrastructure (80 hours)

### Prompt 11.1: Terraform Module Development

**Objective**: Create reusable Terraform modules for AWS infrastructure.

**Tasks**:
1. Set up Terraform with remote state
2. Create VPC module:
   - 3 AZs, public/private subnets
   - NAT Gateway
   - Internet Gateway
   - Route tables
   - VPC endpoints
3. Create EKS module:
   - Cluster with 2 node groups
   - IAM roles and policies
   - Security groups
   - OIDC provider
4. Create RDS module:
   - Multi-AZ PostgreSQL
   - Read replicas
   - Parameter groups
   - Backup configuration
5. Create ElastiCache module:
   - Redis cluster mode
   - Multi-AZ
   - Automatic failover
6. Create S3 module:
   - Multiple buckets
   - Lifecycle policies
   - Replication
   - Encryption
7. Create CloudFront module
8. Add IAM module
9. Add monitoring module (CloudWatch)
10. Document each module

**Deliverables**:
- Modular Terraform code in `deploy/terraform/`
- Module documentation
- Example usage
- Variable documentation

**Success Criteria**:
- Modules reusable
- terraform validate passes
- terraform plan clean
- Costs calculated
- Documentation complete

**Time**: 40 hours
**Skills**: Terraform, AWS, IaC

---

### Prompt 11.2: Multi-Environment Setup

**Objective**: Set up dev, staging, production environments.

**Tasks**:
1. Create environment configurations
2. Set up state backends per environment
3. Configure variable files
4. Create workspaces
5. Implement environment promotion
6. Configure CI/CD for Terraform
7. Add cost estimation
8. Add compliance checks
9. Document procedures
10. Train team

**Deliverables**:
- Environment-specific configs
- CI/CD pipelines
- Cost monitoring
- Documentation

**Success Criteria**:
- All environments deployable
- Promotion workflow working
- CI/CD running
- Costs tracked
- Team trained

**Time**: 16 hours
**Skills**: Terraform, DevOps, CI/CD

---

### Prompt 11.3: AWS Service Configuration

**Objective**: Configure all AWS services for production use.

**Tasks**:
1. Configure VPC with proper CIDR ranges
2. Set up NAT Gateways in each AZ
3. Configure security groups
4. Set up IAM roles and policies
5. Configure CloudWatch logging
6. Set up CloudTrail for audit
7. Configure AWS Config
8. Set up GuardDuty
9. Configure Inspector
10. Set up Macie for data classification

**Deliverables**:
- All AWS services configured
- Security configurations
- Logging and audit
- Compliance setup

**Success Criteria**:
- All services secured
- Audit logging working
- Compliance baseline met
- Security findings addressed
- Cost optimized

**Time**: 24 hours
**Skills**: AWS, Security, Compliance

---

## Week 13-14: Microservices Decomposition (80 hours)

### Prompt 13.1: Service Decomposition Planning

**Objective**: Plan and execute microservices architecture.

**Tasks**:
1. Identify service boundaries:
   - Simulation Service
   - ML Inference Service
   - Inversion Service
   - Data Pipeline Service
   - Control Service
   - Operations Service
   - API Gateway
2. Define service contracts (OpenAPI)
3. Define event schemas (Avro)
4. Plan database per service
5. Plan inter-service communication
6. Plan authentication/authorization
7. Create migration plan
8. Define rollback strategy
9. Document architecture
10. Review with team

**Deliverables**:
- Architecture document
- Service contracts
- Migration plan
- Rollback procedures

**Success Criteria**:
- Clear service boundaries
- Contracts agreed
- Migration plan approved
- Team aligned

**Time**: 24 hours
**Skills**: Architecture, Microservices, Design

---

### Prompt 13.2: API Gateway Setup

**Objective**: Deploy Kong or Traefik as API gateway.

**Tasks**:
1. Choose API gateway (Kong vs Traefik)
2. Deploy in HA mode
3. Configure routes for all services
4. Set up authentication plugins
5. Configure rate limiting
6. Add request transformation
7. Configure response caching
8. Set up monitoring
9. Add request logging
10. Document configuration

**Deliverables**:
- API gateway deployment
- Route configurations
- Plugin configurations
- Documentation

**Success Criteria**:
- Single entry point
- Authentication working
- Rate limiting active
- Monitoring in place
- Performance good

**Time**: 24 hours
**Skills**: API Gateway, Kong/Traefik, Networking

---

### Prompt 13.3: gRPC for Internal Communication

**Objective**: Implement gRPC for high-performance internal service communication.

**Tasks**:
1. Define Protocol Buffers
2. Generate Python code
3. Implement gRPC servers
4. Implement gRPC clients
5. Add interceptors for auth/logging
6. Configure load balancing
7. Add health checks
8. Configure retries
9. Add tracing
10. Performance test

**Deliverables**:
- Protocol buffer definitions
- gRPC implementations
- Interceptors
- Performance benchmarks

**Success Criteria**:
- gRPC working between services
- Better performance than REST
- Health checks working
- Tracing integrated
- Well-documented

**Time**: 32 hours
**Skills**: gRPC, Protocol Buffers, Python

---

# MONTH 4: Service Mesh & MLOps

## Week 15-16: Istio Service Mesh (80 hours)

### Prompt 15.1: Istio Installation

**Objective**: Deploy Istio service mesh on Kubernetes.

**Tasks**:
1. Install istioctl
2. Choose Istio profile (production)
3. Install Istio control plane
4. Configure ingress gateway
5. Configure egress gateway
6. Enable automatic sidecar injection
7. Configure observability addons
8. Set up Kiali for visualization
9. Test installation
10. Document configuration

**Deliverables**:
- Istio installation
- Gateway configurations
- Sidecar injection enabled
- Kiali dashboard
- Documentation

**Success Criteria**:
- Istio control plane healthy
- Sidecars injected
- Gateways working
- Kiali showing service mesh
- Performance acceptable

**Time**: 16 hours
**Skills**: Istio, Kubernetes, Service Mesh

---

### Prompt 15.2: mTLS Configuration

**Objective**: Enable mutual TLS between all services.

**Tasks**:
1. Configure PeerAuthentication (STRICT mode)
2. Configure DestinationRules
3. Test mTLS between services
4. Configure certificate rotation
5. Monitor certificate expiry
6. Set up alerts
7. Test failure scenarios
8. Document configuration

**Deliverables**:
- mTLS policies
- DestinationRules
- Monitoring
- Documentation

**Success Criteria**:
- All inter-service traffic encrypted
- No clear text traffic
- Certificates rotating
- Monitoring working
- Performance good

**Time**: 16 hours
**Skills**: Istio, mTLS, Security

---

### Prompt 15.3: Traffic Management

**Objective**: Configure advanced traffic management with Istio.

**Tasks**:
1. Configure VirtualServices
2. Set up traffic splitting (canary)
3. Configure circuit breakers
4. Add retries and timeouts
5. Configure fault injection (chaos testing)
6. Set up A/B testing
7. Configure traffic mirroring
8. Add request routing rules
9. Test all configurations
10. Document patterns

**Deliverables**:
- VirtualService configurations
- DestinationRules
- Canary deployment patterns
- Documentation

**Success Criteria**:
- Canary deployments work
- Circuit breakers active
- Retries configured
- Chaos testing possible
- Patterns documented

**Time**: 24 hours
**Skills**: Istio, Traffic Management, Service Mesh

---

### Prompt 15.4: Observability with Istio

**Objective**: Leverage Istio for enhanced observability.

**Tasks**:
1. Configure Prometheus integration
2. Set up Grafana dashboards
3. Configure Jaeger tracing
4. Set up Kiali topology
5. Add custom metrics
6. Configure access logging
7. Set up alerts
8. Create runbooks
9. Train team
10. Document patterns

**Deliverables**:
- Observability dashboards
- Custom metrics
- Access logs
- Runbooks
- Training materials

**Success Criteria**:
- Full visibility into mesh
- Custom dashboards working
- Tracing complete
- Alerts firing correctly
- Team trained

**Time**: 24 hours
**Skills**: Istio, Observability, Monitoring

---

## Week 17-18: MLOps Infrastructure (80 hours)

### Prompt 17.1: MLflow Deployment

**Objective**: Deploy MLflow for experiment tracking and model registry.

**Tasks**:
1. Deploy MLflow server (HA mode)
2. Configure PostgreSQL backend
3. Configure S3 artifact storage
4. Set up authentication
5. Configure model registry
6. Add experiment templates
7. Configure model serving
8. Set up CI/CD integration
9. Add monitoring
10. Train team

**Deliverables**:
- MLflow deployment
- PostgreSQL backend
- S3 storage
- Documentation
- Training materials

**Success Criteria**:
- MLflow accessible
- Experiments tracked
- Models registered
- Serving working
- Team trained

**Time**: 20 hours
**Skills**: MLflow, MLOps, Python

---

### Prompt 17.2: Feast Feature Store

**Objective**: Deploy Feast for feature management.

**Tasks**:
1. Deploy Feast online store (Redis)
2. Configure offline store (PostgreSQL/S3)
3. Define feature views
4. Define feature services
5. Set up feature materialization
6. Configure feature serving
7. Add monitoring
8. Create example features
9. Document patterns
10. Train data scientists

**Deliverables**:
- Feast deployment
- Feature definitions
- Materialization pipelines
- Documentation

**Success Criteria**:
- Online features < 10ms
- Offline features accessible
- Materialization running
- Documentation complete
- Team trained

**Time**: 20 hours
**Skills**: Feast, Feature Engineering, MLOps

---

### Prompt 17.3: Evidently AI Monitoring

**Objective**: Deploy Evidently for model monitoring.

**Tasks**:
1. Deploy Evidently UI
2. Configure data drift detection
3. Set up model performance monitoring
4. Add data quality monitoring
5. Configure alerts
6. Create monitoring dashboards
7. Schedule monitoring jobs
8. Add reporting
9. Document procedures
10. Train team

**Deliverables**:
- Evidently deployment
- Monitoring configurations
- Dashboards
- Alerts
- Documentation

**Success Criteria**:
- Drift detected automatically
- Performance tracked
- Quality monitored
- Alerts firing
- Reports generated

**Time**: 16 hours
**Skills**: Evidently, ML Monitoring, MLOps

---

### Prompt 17.4: DVC Data Versioning

**Objective**: Implement DVC for dataset versioning.

**Tasks**:
1. Install DVC
2. Configure remote storage (S3)
3. Set up data pipelines
4. Configure stages
5. Add metrics tracking
6. Configure experiments
7. Integrate with CI/CD
8. Document workflows
9. Train team
10. Migrate existing data

**Deliverables**:
- DVC configuration
- Pipeline definitions
- CI/CD integration
- Documentation

**Success Criteria**:
- Data versioned
- Pipelines reproducible
- Metrics tracked
- Team trained

**Time**: 24 hours
**Skills**: DVC, Data Engineering, MLOps

---

## Week 19-20: Workflow Orchestration (80 hours)

### Prompt 19.1: Apache Airflow Deployment

**Objective**: Deploy Airflow for workflow orchestration.

**Tasks**:
1. Deploy Airflow on Kubernetes (HA mode)
2. Configure PostgreSQL metadata
3. Configure Celery executor
4. Set up Redis broker
5. Configure authentication
6. Set up plugins
7. Configure secrets backend (Vault)
8. Add monitoring
9. Configure logging
10. Backup procedures

**Deliverables**:
- Airflow deployment
- Configuration files
- Monitoring
- Documentation

**Success Criteria**:
- Airflow accessible
- DAGs running
- Auth working
- Monitoring in place
- Backups configured

**Time**: 24 hours
**Skills**: Airflow, Kubernetes, Python

---

### Prompt 19.2: Data Pipeline DAGs

**Objective**: Create production DAGs for satellite data processing.

**Tasks**:
1. Create satellite data ingestion DAG
2. Create data quality validation DAG
3. Create feature engineering DAG
4. Create model training DAG
5. Create model deployment DAG
6. Create monitoring DAG
7. Add error handling
8. Configure SLAs
9. Add notifications
10. Test all DAGs

**Deliverables**:
- Production DAGs in `mlops/airflow/dags/`
- Test data
- Documentation
- Runbooks

**Success Criteria**:
- DAGs running successfully
- Data flowing end-to-end
- Errors handled
- SLAs met
- Notifications working

**Time**: 32 hours
**Skills**: Airflow, Python, ETL

---

### Prompt 19.3: Apache Kafka Setup

**Objective**: Deploy Kafka for event streaming.

**Tasks**:
1. Deploy Kafka cluster (3 brokers)
2. Configure Zookeeper/KRaft
3. Set up Schema Registry
4. Configure topics
5. Add monitoring
6. Set up Kafka Connect
7. Configure consumer groups
8. Add producer/consumer examples
9. Configure retention
10. Document patterns

**Deliverables**:
- Kafka cluster deployment
- Topic configurations
- Schema Registry
- Monitoring
- Documentation

**Success Criteria**:
- Kafka cluster healthy
- Topics created
- Producers/consumers working
- Monitoring active
- Patterns documented

**Time**: 24 hours
**Skills**: Kafka, Event Streaming, Distributed Systems

---

# MONTH 5: Data Lake & Streaming

## Week 21-22: Stream Processing (80 hours)

### Prompt 21.1: Apache Flink Deployment

**Objective**: Deploy Flink for stream processing.

**Tasks**:
1. Deploy Flink cluster
2. Configure state backend
3. Set up checkpointing
4. Configure savepoints
5. Add monitoring
6. Create processing jobs
7. Configure exactly-once semantics
8. Add error handling
9. Document patterns
10. Train team

**Deliverables**:
- Flink deployment
- Processing jobs
- Configurations
- Documentation

**Success Criteria**:
- Flink running stable
- Jobs processing data
- Exactly-once working
- Monitoring in place
- Team trained

**Time**: 40 hours
**Skills**: Flink, Stream Processing, Java/Python

---

### Prompt 21.2: Apache Iceberg Data Lake

**Objective**: Set up Iceberg for data lake.

**Tasks**:
1. Configure Iceberg tables
2. Set up partitioning strategies
3. Configure compaction
4. Add time travel queries
5. Configure schema evolution
6. Set up snapshots
7. Add table maintenance
8. Configure monitoring
9. Document patterns
10. Migrate existing data

**Deliverables**:
- Iceberg tables
- Partitioning strategies
- Maintenance jobs
- Documentation

**Success Criteria**:
- Tables created
- Queries performant
- Time travel working
- Schema evolution tested
- Data migrated

**Time**: 40 hours
**Skills**: Iceberg, Data Lake, Spark

---

## Week 23-24: Final Integration & Optimization (80 hours)

### Prompt 23.1: Performance Optimization

**Objective**: Optimize platform performance for production load.

**Tasks**:
1. Profile all services
2. Identify bottlenecks
3. Optimize database queries
4. Add caching layers
5. Optimize API endpoints
6. Reduce container sizes
7. Optimize image processing
8. Add CDN for static assets
9. Configure compression
10. Run load tests

**Deliverables**:
- Performance reports
- Optimizations implemented
- Load test results
- Documentation

**Success Criteria**:
- p99 < 300ms (improvement)
- 50% memory reduction
- 2x throughput
- Costs reduced 30%
- Load tests passing

**Time**: 40 hours
**Skills**: Performance, Profiling, Optimization

---

### Prompt 23.2: Chaos Engineering

**Objective**: Implement chaos engineering with Chaos Mesh.

**Tasks**:
1. Install Chaos Mesh
2. Define chaos experiments:
   - Pod failures
   - Network delays
   - CPU stress
   - Memory stress
   - Disk failures
3. Schedule game days
4. Document findings
5. Improve resilience
6. Add to CI/CD
7. Create runbooks
8. Train team

**Deliverables**:
- Chaos Mesh deployment
- Experiment library
- Game day reports
- Runbooks

**Success Criteria**:
- System resilient to failures
- Recovery automated
- No data loss
- MTTR < 5 minutes
- Team trained

**Time**: 40 hours
**Skills**: Chaos Engineering, SRE, Kubernetes

---

# MONTH 6: Compliance & Launch

## Week 25-26: Security & Compliance (80 hours)

### Prompt 25.1: SOC 2 Type II Preparation

**Objective**: Prepare for SOC 2 Type II audit.

**Tasks**:
1. Engage auditor (Drata, Vanta, etc.)
2. Implement control framework
3. Document policies and procedures
4. Implement access controls
5. Set up audit logging
6. Configure change management
7. Implement incident response
8. Add vendor management
9. Configure data classification
10. Conduct internal audit

**Deliverables**:
- Policy documents (20+)
- Control implementations
- Audit evidence
- Internal audit report

**Success Criteria**:
- All controls implemented
- Policies documented
- Evidence collected
- Internal audit passed
- Ready for external audit

**Time**: 40 hours
**Skills**: Compliance, GRC, Security

---

### Prompt 25.2: Penetration Testing

**Objective**: Conduct comprehensive penetration testing.

**Tasks**:
1. Engage pen testing firm
2. Define scope and rules
3. Conduct external testing
4. Conduct internal testing
5. Test web application
6. Test API endpoints
7. Test infrastructure
8. Test social engineering
9. Document findings
10. Remediate vulnerabilities

**Deliverables**:
- Pen test report
- Remediation plan
- Fixed vulnerabilities
- Verification testing

**Success Criteria**:
- Zero critical vulnerabilities
- High severity fixed
- Medium remediated
- Documented
- Verified

**Time**: 40 hours
**Skills**: Security Testing, Penetration Testing

---

## Week 27-28: Production Launch (80 hours)

### Prompt 27.1: Production Migration

**Objective**: Migrate from staging to production environment.

**Tasks**:
1. Final infrastructure verification
2. Database migration
3. Data migration
4. DNS cutover
5. SSL certificate verification
6. Monitoring verification
7. Alerting verification
8. Backup verification
9. Disaster recovery test
10. Go/no-go decision

**Deliverables**:
- Migration plan
- Rollback plan
- Migration scripts
- Verification reports

**Success Criteria**:
- Zero downtime migration
- All data migrated
- Monitoring working
- Alerts firing correctly
- Team ready

**Time**: 40 hours
**Skills**: DevOps, Migration, SRE

---

### Prompt 27.2: Production Launch Preparation

**Objective**: Final preparations for production launch.

**Tasks**:
1. Final load testing
2. Final security scan
3. Documentation review
4. Team training
5. Runbook verification
6. On-call rotation setup
7. Incident response plan
8. Communication plan
9. Marketing preparation
10. Launch announcement

**Deliverables**:
- Launch checklist
- Communication plan
- Runbooks
- Training records

**Success Criteria**:
- All checks passed
- Team trained
- On-call ready
- Plan executed
- Successful launch

**Time**: 40 hours
**Skills**: Project Management, Communication

---

# Post-Launch (Ongoing)

## Continuous Improvement

### Prompt P.1: Performance Monitoring

**Daily Tasks**:
- Check Grafana dashboards
- Review AlertManager
- Verify backups
- Check error logs
- Monitor SLOs

### Prompt P.2: Weekly Tasks

- Security scan review
- Dependency updates
- Performance review
- Cost analysis
- Team standup

### Prompt P.3: Monthly Tasks

- Disaster recovery drill
- Security audit
- Capacity planning
- Cost optimization
- Roadmap review

### Prompt P.4: Quarterly Tasks

- Major version updates
- Architecture review
- Team training
- Customer feedback review
- Strategic planning

---

# Resource Requirements

## Team Composition (9 FTE)

1. **Tech Lead** (1) - Overall architecture and decisions
2. **Senior DevOps** (2) - Infrastructure and Kubernetes
3. **Backend Engineers** (2) - Service development
4. **ML Engineer** (1) - MLOps and models
5. **Security Engineer** (1) - Security and compliance
6. **SRE** (1) - Reliability and observability
7. **QA Engineer** (1) - Testing and quality

## Tools & Services

### Required Tools
- IDE: VS Code with extensions
- Source Control: Git/GitHub
- Project Management: Jira/Linear
- Documentation: Confluence/Notion
- Communication: Slack
- Design: Figma

### Required Services (Monthly Cost)
- AWS: ~$5,000
- DataDog: ~$2,000
- GitHub Enterprise: ~$500
- Slack: ~$200
- Other tools: ~$500
- **Total: ~$8,200/month**

## Budget Allocation

| Category | Budget |
|----------|--------|
| Personnel (6 months) | $1,500,000 |
| Infrastructure | $100,000 |
| Tools & Software | $50,000 |
| Security Audit | $50,000 |
| Penetration Testing | $30,000 |
| Compliance (SOC 2) | $100,000 |
| Training | $50,000 |
| Contingency (15%) | $300,000 |
| **Total** | **$2,180,000** |

---

# Success Metrics

## Technical KPIs

- **Availability**: 99.99% (4.32 min downtime/month)
- **Latency p99**: < 200ms (improved from 500ms)
- **Latency p95**: < 100ms (improved from 300ms)
- **Error rate**: < 0.01% (improved from 0.1%)
- **Throughput**: 10,000+ req/s
- **Concurrent Users**: 50,000+

## Business KPIs

- **Time to Market**: 6 months
- **Cost per User**: < $1/month
- **ROI**: 300% within 18 months
- **Customer Satisfaction**: > 90%
- **Team Velocity**: 2x increase

## Operational KPIs

- **MTTR**: < 5 minutes
- **MTBF**: > 60 days
- **Deployment Frequency**: Multiple per day
- **Change Failure Rate**: < 5%
- **Lead Time**: < 1 day

---

# Risk Management

## Top Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Technical complexity | High | Medium | Phased approach, expert team |
| Team availability | High | Low | Cross-training, documentation |
| Security incidents | Critical | Low | Defense in depth, monitoring |
| Cost overruns | Medium | Medium | Contingency budget, tracking |
| Vendor lock-in | Medium | Medium | Open standards, abstraction |
| Performance issues | High | Low | Load testing, monitoring |
| Compliance delays | Medium | Medium | Early engagement, automation |
| Data loss | Critical | Very Low | Backups, replication, DR |

---

# Communication Plan

## Weekly
- Team standup (Mon/Wed/Fri)
- Stakeholder update (Friday)
- Sprint review (every 2 weeks)

## Monthly
- Executive summary
- Budget review
- Risk review
- Customer feedback

## Quarterly
- Board update
- Roadmap review
- Strategy adjustment

---

# Conclusion

This implementation plan provides a structured approach to building GALILEO into a production-ready, enterprise-grade platform over 6 months. By following this prompt:

1. **Use each prompt** as a self-contained task
2. **Track progress** weekly against the schedule
3. **Adjust as needed** based on learnings
4. **Communicate regularly** with stakeholders
5. **Maintain quality** through testing and reviews

**Expected Outcome**: A best-in-class satellite and geophysical sensing platform with:
- 99.99% availability
- Sub-200ms p99 latency
- 50,000+ concurrent users
- SOC 2 Type II certified
- Production-ready for enterprise customers

---

**Document Version**: 1.0
**Last Updated**: 2026-05-24
**Next Review**: Monthly
**Owner**: GALILEO Platform Team
