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


---

## Paste-ready JSX (Atlas utility-class vocabulary)

The snippets below use the Atlas site's own Tailwind tokens
(`text-ink`, `border-rule`, `bg-paper-alt`, `tracking-label`,
`bg-accent`) exactly as they appear in the published pages, so they
drop into the page components (or their data file) unchanged.

### Status badge (platform card + detail hero)

```jsx
<span className="inline-block whitespace-nowrap rounded border px-2 py-0.5 text-[10px] font-medium uppercase tracking-label border-rule-strong bg-paper text-ink-body">
  Available
</span>
```

### Hero description (detail page)

```jsx
<p className="mt-6 max-w-2xl text-base leading-7 text-ink-body">
  GALILEO is the ATLAS platform for satellite gravimetry missions: it
  flies a GRACE-like two-satellite formation through real
  spherical-harmonic dynamics, streams the measurements through an
  authenticated microservice platform into TimescaleDB, recovers the
  orbit to 0.30&nbsp;m by dynamic orbit determination, and inverts the
  data into georeferenced gravity-anomaly maps — classical Tikhonov and
  a machine-learned completion model that beats the classical baseline
  by 47% on the held-out benchmark.
</p>
```

### Self-hosted note

```jsx
<p className="mt-6 max-w-xl text-sm leading-6 text-ink-muted">
  Self-hosted via Docker Compose — one command brings up the full
  23-container stack, verified end to end on a clean machine. The
  repository carries its own honest status audit; hosted access is
  planned.
</p>
```

### Spec-panel additions (hero right card `<dl>`)

```jsx
<div>
  <dt className="text-ink-faint">Orbit recovery</dt>
  <dd className="mt-0.5 leading-6 font-mono text-ink">0.30 m dynamic OD</dd>
</div>
<div>
  <dt className="text-ink-faint">ML inversion</dt>
  <dd className="mt-0.5 leading-6 font-mono text-ink">+47% vs classical baseline</dd>
</div>
<div>
  <dt className="text-ink-faint">API</dt>
  <dd className="mt-0.5 leading-6 text-ink-body">32 documented REST endpoints over gRPC microservices</dd>
</div>
```

### Quickstart section (insert after "What it does")

```jsx
<section className="border-b border-rule">
  <div className="mx-auto w-full max-w-6xl px-6 py-14">
    <div className="text-[11px] font-medium uppercase tracking-label text-ink-faint">
      Quickstart
    </div>
    <h2 className="mt-4 text-3xl font-semibold tracking-tight text-ink">
      Run it yourself in five commands
    </h2>
    <p className="mt-4 max-w-2xl text-base leading-7 text-ink-body">
      Requires Docker, Node 18+, and nothing else. The second command
      loads a full mission — simulation, ingestion, orbit
      determination, and a first inversion — through the live API.
    </p>
    <pre className="mt-8 max-w-2xl overflow-x-auto rounded-md border border-rule bg-surface p-5 font-mono text-sm leading-7 text-ink">
{`git clone https://github.com/alovladi007/AURORA_GALILEO.git galileo
cd galileo
docker compose up -d --build
docker compose run --rm mission-scenario
cd ui && npm install && npm run dev`}
    </pre>
    <p className="mt-4 text-sm text-ink-muted">
      Then open{' '}
      <span className="font-mono">http://localhost:13003</span> — the
      landing page, Mission Control console, gravity anomaly map, and
      operations console are all live against the running stack.
    </p>
  </div>
</section>
```

### Capability card 04 (inversion) refresh

```jsx
<p className="mt-2 text-sm leading-6 text-ink-muted">
  Tikhonov inversion and a machine-learned gravity-completion model
  against spherical-harmonic reference fields — the ML path beats the
  classical baseline by 47% on the held-out benchmark, and both are
  served live behind the same API.
</p>
```
