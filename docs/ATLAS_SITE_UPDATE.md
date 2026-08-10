# ATLAS site update — GALILEO platform page

Prepared changes for the ATLAS corporate site repository
(`ATLAS-Advanced-Technology-Labs-for-Applied-Sciences`), which this
session cannot push to (only the GALILEO repo is attached). Apply in
the Atlas repo, or attach that repo to a Claude Code session and point
it at this file.

The GALILEO → ATLAS direction is already live: the GALILEO landing
page's eyebrow, footer platform links, and "About the platforms" link
all deep-link into the ATLAS site. The ATLAS → GALILEO direction
already links the repo; the changes below refresh its status and copy.

## 1. Platform card (`/platform/`, GALILEO card)

- Status badge: `In development` → `Available` — the platform now
  deploys end to end with one compose command and passes its full
  pipeline (verified on a clean machine).

## 2. GALILEO detail page (`/platform/aurora-galileo/`)

Replace the capability description with measured results:

> GALILEO is the ATLAS platform for satellite gravimetry missions: it
> flies a GRACE-like two-satellite formation through real
> spherical-harmonic dynamics, streams the measurements through an
> authenticated microservice platform into TimescaleDB, recovers the
> orbit to 0.30 m by dynamic orbit determination, and inverts the data
> into georeferenced gravity-anomaly maps — classical Tikhonov and a
> machine-learned completion model that beats the classical baseline
> by 47% on the held-out benchmark. The operations plane (Prometheus,
> Alertmanager, Jaeger, Grafana) ships with the stack and surfaces in
> a live operations console.

Add a quickstart block (all true of the current repo):

```bash
git clone https://github.com/alovladi007/AURORA_GALILEO.git galileo
cd galileo
docker compose up -d --build
docker compose run --rm mission-scenario
cd ui && npm install && npm run dev
# open http://localhost:13003
```

Keep the existing repository link
(`https://github.com/alovladi007/AURORA_GALILEO`).

## 3. Optional stat strip entries for the GALILEO page

| stat | label |
| --- | --- |
| `0.30 m` | orbit recovery, dynamic OD |
| `47%` | ML inversion gain over the classical baseline |
| `32` | documented API endpoints |
| `23` | containers in the deployed stack |
