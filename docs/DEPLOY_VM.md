# Deploying GALILEO to a single VM

The pragmatic hosted deployment: one cloud VM, the existing compose
stack, Caddy terminating TLS. Kubernetes/Helm (master plan W2.6) is a
later scale step; this gets GALILEO on a public URL today.

## Prerequisites

- A VM with ≥ 8 GB RAM, ≥ 40 GB disk (any provider), ports 80 and
  443 open.
- Docker Engine with Compose **v2.24+** (the overlay uses `!reset`).
- A DNS A record pointing your domain (e.g. `galileo.example.com`)
  at the VM's IP.

## Steps

```bash
git clone https://github.com/alovladi007/AURORA_GALILEO.git galileo
cd galileo

cp .env.production.example .env
# Edit .env: set DOMAIN, ACME_EMAIL, and generate every secret:
#   openssl rand -hex 32

docker compose -f docker-compose.yaml -f docker-compose.prod.yaml up -d --build
```

First build takes several minutes (service images + the production
UI build). Caddy obtains the TLS certificate automatically on first
request.

Load a mission dataset and create the first account (the first
registered user gets admin):

```bash
docker compose -f docker-compose.yaml -f docker-compose.prod.yaml \
  run --rm mission-scenario
```

> The pipeline registers the dev service account. For production,
> register your own account via `https://<domain>/docs` →
> `POST /auth/register`, then treat the dev account's credentials as
> disposable.

## Verify

- `https://<domain>/` — landing page, live status pills green
- `https://<domain>/dashboard` — Mission Control (sign in)
- `https://<domain>/gravity` — run an inversion
- `https://<domain>/health` — gateway health JSON
- `https://<domain>/docs` — API reference

## What the production overlay enforces

- **AUTH_MODE=required** — no anonymous fallback on protected routes.
- **JWT_SECRET mandatory** — compose refuses to start without it.
- **No internal ports published** — Postgres, Redis, Kafka, MinIO,
  Prometheus, Grafana, Alertmanager, MLflow, and Jaeger are reachable
  only inside the compose network. For the observability UIs, tunnel:

  ```bash
  ssh -L 3000:localhost:3000 user@vm \
    docker compose exec grafana true   # or map ports ad hoc
  # simpler: ssh -L 29091:grafana:3000 via a compose-networked helper,
  # or temporarily publish the port in a local override file.
  ```

- **Same-origin UI ↔ API** — the browser talks to the gateway through
  Caddy on one domain; no CORS surface in production.

## Updating a deployment

```bash
git pull
docker compose -f docker-compose.yaml -f docker-compose.prod.yaml up -d --build
```

## Local validation (no domain needed)

Set `DOMAIN=:80` in `.env`; Caddy serves plain HTTP on
port 80. This is exactly how the overlay was verified in development.
