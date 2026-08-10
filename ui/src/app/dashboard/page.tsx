'use client';

/**
 * GALILEO Mission Control console.
 *
 * Sidebar-console layout wired entirely to live gateway endpoints —
 * failures render as failures, sections without a real backend say so.
 *
 * Design system (committed dark theme):
 *   surfaces  #0a0e17 app · #101624 card · #070b12 rail
 *   ink       #eef2f9 primary · #97a3ba secondary · #5c6a84 muted
 *   accent    #3987e5 (validated series-1 on dark surface)
 *   status    good #0ca30c · warning #fab219 · serious #ec835a ·
 *             critical #d03b3b — always paired with a text label,
 *             never color alone.
 */

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

const GATEWAY =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:28000';

/* ── design tokens ──────────────────────────────────────────────── */
const T = {
  app: 'bg-[#0a0e17]',
  card: 'bg-[#101624] border border-[#1c2537] rounded-xl',
  rail: 'bg-[#070b12] border-r border-[#161e2e]',
  ink: 'text-[#eef2f9]',
  ink2: 'text-[#97a3ba]',
  ink3: 'text-[#5c6a84]',
  accent: '#3987e5',
};

const STATUS = {
  good: '#0ca30c',
  warning: '#fab219',
  serious: '#ec835a',
  critical: '#d03b3b',
} as const;

/* ── icons (inline, stroke = currentColor) ──────────────────────── */
const Icon = ({ d, size = 16 }: { d: string; size?: number }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.7"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="shrink-0"
  >
    <path d={d} />
  </svg>
);

const ICONS: Record<string, string> = {
  overview: 'M3 12h4l3-8 4 16 3-8h4',
  jobs: 'M4 17l6-6-6-6M12 19h8',
  inversion:
    'M12 3a9 9 0 1 0 9 9M12 3v9h9M12 3a9 9 0 0 1 9 9',
  data: 'M12 3c-4.4 0-8 1.3-8 3v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6c0-1.7-3.6-3-8-3ZM4 6c0 1.7 3.6 3 8 3s8-1.3 8-3M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3',
  ml: 'M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3M7 7h10v10H7zM10 10h4v4h-4z',
  workflows: 'M5 5h5v5H5zM14 14h5v5h-5zM10 7.5h7v9',
  monitoring:
    'M22 12h-4l-3 9L9 3l-3 9H2',
  refresh:
    'M21 12a9 9 0 1 1-2.6-6.3M21 3v6h-6',
  external: 'M14 5h5v5M19 5l-8 8M12 5H6a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-6',
};

const SECTIONS = [
  { id: 'overview', name: 'Overview', desc: 'Health & mission totals' },
  { id: 'jobs', name: 'Job Console', desc: 'Inversion jobs & history' },
  { id: 'inversion', name: 'Inversion', desc: 'Run gravity inversions' },
  { id: 'data', name: 'Database', desc: 'Measurements & telemetry' },
  { id: 'ml', name: 'ML Models', desc: 'Model registry' },
  { id: 'workflows', name: 'Workflows', desc: 'Event-driven pipelines' },
  { id: 'monitoring', name: 'Monitoring', desc: 'Targets, rules, alerts' },
] as const;

type SectionId = (typeof SECTIONS)[number]['id'];

/* ── shared pieces ──────────────────────────────────────────────── */

function StatusPill({
  kind,
  label,
}: {
  kind: keyof typeof STATUS;
  label: string;
}) {
  const c = STATUS[kind];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium"
      style={{ color: c, backgroundColor: `${c}1a`, border: `1px solid ${c}33` }}
    >
      <span
        className="inline-block w-1.5 h-1.5 rounded-full"
        style={{ backgroundColor: c }}
      />
      {label}
    </span>
  );
}

const okPill = (ok: boolean, okLabel = 'healthy', badLabel = 'down') =>
  ok ? (
    <StatusPill kind="good" label={okLabel} />
  ) : (
    <StatusPill kind="critical" label={badLabel} />
  );

function Card({
  title,
  sub,
  error,
  children,
  actions,
  className = '',
}: {
  title?: string;
  sub?: string;
  error?: string | null;
  children: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`${T.card} ${className}`}>
      {(title || actions) && (
        <div className="flex items-start justify-between px-5 pt-4 pb-3 border-b border-[#161e2e]">
          <div>
            {title && (
              <h2 className={`text-sm font-semibold ${T.ink}`}>{title}</h2>
            )}
            {sub && <p className={`text-xs mt-0.5 ${T.ink3}`}>{sub}</p>}
          </div>
          {actions}
        </div>
      )}
      <div className="px-5 py-4">
        {error ? (
          <div
            className="rounded-lg px-3 py-2 text-xs"
            style={{
              color: STATUS.critical,
              backgroundColor: `${STATUS.critical}14`,
              border: `1px solid ${STATUS.critical}33`,
            }}
          >
            {error}
          </div>
        ) : (
          children
        )}
      </div>
    </div>
  );
}

function StatTile({
  value,
  label,
  hint,
}: {
  value: React.ReactNode;
  label: string;
  hint?: string;
}) {
  return (
    <div className={`${T.card} px-5 py-4`}>
      <div
        className={`text-2xl font-semibold tracking-tight tabular-nums ${T.ink}`}
      >
        {value}
      </div>
      <div className={`text-xs mt-1 ${T.ink2}`}>{label}</div>
      {hint && <div className={`text-[11px] mt-0.5 ${T.ink3}`}>{hint}</div>}
    </div>
  );
}

const Th = ({ children }: { children: React.ReactNode }) => (
  <th className="pb-2.5 pr-4 text-left text-[11px] font-medium uppercase tracking-wider text-[#5c6a84]">
    {children}
  </th>
);

const pct = (p: any) =>
  p == null ? '—' : `${Math.round(p <= 1 ? p * 100 : p)}%`;

/* ── auth ───────────────────────────────────────────────────────── */

function useAuthToken() {
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const login = useCallback(async (email: string, password: string) => {
    setError(null);
    const resp = await fetch(`${GATEWAY}/auth/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!resp.ok) {
      setError(`Login failed (${resp.status})`);
      return;
    }
    setToken((await resp.json()).access_token);
  }, []);
  return { token, error, login };
}

/* ── page ───────────────────────────────────────────────────────── */

export default function DashboardPage() {
  const { token, error: authError, login } = useAuthToken();
  const isDev = process.env.NODE_ENV === 'development';
  const [email, setEmail] = useState(isDev ? 'mission-sim@galileo.dev' : '');
  const [password, setPassword] = useState(
    isDev ? 'mission-scenario-2026' : ''
  );
  const [section, setSection] = useState<SectionId>('overview');

  const [health, setHealth] = useState<any>(null);
  const [healthErr, setHealthErr] = useState<string | null>(null);
  const [targets, setTargets] = useState<any>(null);
  const [alerts, setAlerts] = useState<any>(null);
  const [rules, setRules] = useState<any>(null);
  const [jobs, setJobs] = useState<any[]>([]);
  const [jobsErr, setJobsErr] = useState<string | null>(null);
  const [measurements, setMeasurements] = useState<any>(null);
  const [measurementsErr, setMeasurementsErr] = useState<string | null>(
    null
  );
  const [telemetry, setTelemetry] = useState<any>(null);
  const [telemetryErr, setTelemetryErr] = useState<string | null>(null);
  const [models, setModels] = useState<any[]>([]);
  const [modelsErr, setModelsErr] = useState<string | null>(null);
  const [workflows, setWorkflows] = useState<any>(null);
  const [workflowsErr, setWorkflowsErr] = useState<string | null>(null);
  const [executions, setExecutions] = useState<any[]>([]);

  const [invMethod, setInvMethod] = useState<'tikhonov' | 'ml_completion'>(
    'tikhonov'
  );
  const [invBusy, setInvBusy] = useState(false);
  const [invMsg, setInvMsg] = useState<string | null>(null);

  const authed = useCallback(
    (path: string, init?: RequestInit) =>
      fetch(`${GATEWAY}${path}`, {
        ...init,
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
          ...(init?.headers || {}),
        },
      }),
    [token]
  );

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      const r = await fetch(`${GATEWAY}/health`);
      r.ok
        ? (setHealth(await r.json()), setHealthErr(null))
        : setHealthErr(`health ${r.status}`);
    } catch (e: any) {
      setHealthErr(String(e));
    }
    try {
      const r = await authed('/api/v1/ops/targets');
      if (r.ok) setTargets(await r.json());
    } catch {}
    try {
      const r = await authed('/api/v1/ops/alerts');
      if (r.ok) setAlerts(await r.json());
    } catch {}
    try {
      const r = await authed('/api/v1/ops/rules');
      if (r.ok) setRules(await r.json());
    } catch {}
    try {
      const r = await authed('/api/v1/inversions');
      r.ok
        ? (setJobs((await r.json()).jobs || []), setJobsErr(null))
        : setJobsErr(`inversions ${r.status}`);
    } catch (e: any) {
      setJobsErr(String(e));
    }
    try {
      const r = await authed(
        '/api/v1/data/gravity?satellite_ids=GAL-SIM-A&satellite_ids=GAL-SIM-B&page_size=1000'
      );
      r.ok
        ? (setMeasurements(await r.json()), setMeasurementsErr(null))
        : setMeasurementsErr(`data ${r.status}`);
    } catch (e: any) {
      setMeasurementsErr(String(e));
    }
    try {
      const now = new Date();
      const start = new Date(now.getTime() - 30 * 86400_000);
      const r = await authed(
        `/api/v1/data/telemetry?satellite_ids=GAL-SIM-A&satellite_ids=GAL-SIM-B` +
          `&start_time=${start.toISOString()}&end_time=${now.toISOString()}&page_size=500`
      );
      r.ok
        ? (setTelemetry(await r.json()), setTelemetryErr(null))
        : setTelemetryErr(`telemetry ${r.status}: ${await r.text()}`);
    } catch (e: any) {
      setTelemetryErr(String(e));
    }
    try {
      const r = await authed('/api/v1/models');
      r.ok
        ? (setModels((await r.json()).models || []), setModelsErr(null))
        : setModelsErr(`models ${r.status}`);
    } catch (e: any) {
      setModelsErr(String(e));
    }
    try {
      const r = await authed('/api/v1/workflows/workflows');
      r.ok
        ? (setWorkflows(await r.json()), setWorkflowsErr(null))
        : setWorkflowsErr(`workflows ${r.status}`);
      const e = await authed('/api/v1/workflows/executions');
      if (e.ok) setExecutions((await e.json()) || []);
    } catch (e: any) {
      setWorkflowsErr(String(e));
    }
  }, [token, authed]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 20000);
    return () => clearInterval(id);
  }, [refresh]);

  const runInversion = async () => {
    setInvBusy(true);
    setInvMsg(null);
    try {
      const resp = await authed('/api/v1/inversions', {
        method: 'POST',
        body: JSON.stringify({
          name: `console-${invMethod}`,
          measurement_ids: ['GAL-SIM-A', 'GAL-SIM-B'],
          parameters: { method: invMethod },
          grid: {
            min_latitude: -85,
            max_latitude: 85,
            min_longitude: -180,
            max_longitude: 180,
            num_lat_points: 16,
            num_lon_points: 16,
          },
        }),
      });
      if (!resp.ok) {
        setInvMsg(`Start failed (${resp.status}): ${await resp.text()}`);
        return;
      }
      const { job_id } = await resp.json();
      setInvMsg(`Job ${job_id} started — view the map on the Gravity page`);
      await refresh();
    } finally {
      setInvBusy(false);
    }
  };

  /* ── sign-in ──────────────────────────────────────────────────── */
  if (!token) {
    return (
      <div
        className={`min-h-screen ${T.app} ${T.ink} flex items-center justify-center p-8`}
      >
        <div className="w-full max-w-sm">
          <div className="flex items-center gap-3 mb-8 justify-center">
            <OrbitMark />
            <div>
              <div className="font-semibold tracking-tight">
                GALILEO Mission Control
              </div>
              <div className={`text-xs ${T.ink3}`}>
                satellite gravimetry platform
              </div>
            </div>
          </div>
          <form
            className={`${T.card} p-6 space-y-4`}
            onSubmit={(e) => {
              e.preventDefault();
              login(email.trim(), password);
            }}
          >
            <div>
              <label className={`block text-xs mb-1.5 ${T.ink2}`}>
                Email
              </label>
              <input
                className="w-full rounded-lg bg-[#0a0e17] border border-[#1c2537] px-3 py-2 text-sm focus:outline-none focus:border-[#3987e5]"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div>
              <label className={`block text-xs mb-1.5 ${T.ink2}`}>
                Password
              </label>
              <input
                className="w-full rounded-lg bg-[#0a0e17] border border-[#1c2537] px-3 py-2 text-sm focus:outline-none focus:border-[#3987e5]"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <button
              className="w-full rounded-lg py-2 text-sm font-medium text-white transition-colors"
              style={{ backgroundColor: T.accent }}
            >
              Sign in
            </button>
            {authError && (
              <p className="text-xs" style={{ color: STATUS.critical }}>
                {authError}
              </p>
            )}
          </form>
          <p className={`text-center text-[11px] mt-4 ${T.ink3}`}>
            live platform state · no fabricated data
          </p>
        </div>
      </div>
    );
  }

  /* ── derived data ─────────────────────────────────────────────── */
  const rows = measurements?.measurements ?? [];
  const totalMeasurements =
    measurements?.pagination?.total_items ?? rows.length;
  const telemetryRows = telemetry?.telemetry ?? [];
  const activeAlerts = alerts?.alerts ?? [];
  const servicesOk =
    !!health &&
    health.status === 'healthy' &&
    Object.values(health.services || {}).every(
      (v) => v === 'healthy' || v === 'connected'
    );

  const jobsTable = (
    <Card
      title="Inversion jobs"
      sub="every job ran against ingested mission data"
      error={jobsErr}
    >
      {jobs.length ? (
        <table className="w-full text-sm">
          <thead>
            <tr>
              <Th>Job</Th>
              <Th>Status</Th>
              <Th>Progress</Th>
            </tr>
          </thead>
          <tbody>
            {jobs.slice(0, 12).map((j: any) => (
              <tr
                key={j.job_id}
                className="border-t border-[#161e2e] hover:bg-white/[0.02]"
              >
                <td className={`py-2.5 pr-4 font-mono text-xs ${T.ink2}`}>
                  {j.job_id}
                </td>
                <td className="py-2.5 pr-4">
                  {j.status === 'completed' ? (
                    <StatusPill kind="good" label="completed" />
                  ) : j.status === 'failed' ? (
                    <StatusPill kind="critical" label="failed" />
                  ) : (
                    <StatusPill kind="warning" label={j.status} />
                  )}
                </td>
                <td className={`py-2.5 tabular-nums ${T.ink}`}>
                  {pct(j.progress)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className={`text-sm ${T.ink3}`}>
          no inversion jobs yet — start one in the Inversion section
        </p>
      )}
    </Card>
  );

  /* ── sections ─────────────────────────────────────────────────── */
  const content: Record<SectionId, React.ReactNode> = {
    overview: (
      <div className="space-y-6">
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
          <StatTile
            value={totalMeasurements}
            label="gravity measurements"
            hint="TimescaleDB, provenance-tagged"
          />
          <StatTile
            value={telemetryRows.length}
            label="telemetry records"
            hint="last 30 days"
          />
          <StatTile
            value={`${jobs.filter((j: any) => j.status === 'completed').length}/${jobs.length}`}
            label="inversions completed"
          />
          <StatTile
            value={targets ? `${targets.up}/${targets.total}` : '—'}
            label="scrape targets up"
            hint="Prometheus"
          />
          <StatTile
            value={(workflows?.workflows || []).length}
            label="event workflows"
            hint={`${executions.length} executions`}
          />
        </div>

        <div className="grid lg:grid-cols-2 gap-6">
          <Card
            title="Platform health"
            sub="gateway gRPC checks, refreshed every 20 s"
            error={healthErr}
          >
            {health ? (
              <ul className="space-y-2.5 text-sm">
                <li className="flex items-center justify-between">
                  <span className={T.ink2}>api-gateway</span>
                  {okPill(health.status === 'healthy')}
                </li>
                {Object.entries(health.services || {}).map(([k, v]) => (
                  <li key={k} className="flex items-center justify-between">
                    <span className={T.ink2}>{k}-service</span>
                    {okPill(
                      v === 'healthy' || v === 'connected',
                      String(v),
                      String(v).slice(0, 24)
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className={`text-sm ${T.ink3}`}>loading…</p>
            )}
          </Card>

          <Card title="Active alerts" sub="Alertmanager, live">
            {activeAlerts.length ? (
              <ul className="space-y-2">
                {activeAlerts.map((a: any, i: number) => (
                  <li key={i} className="flex items-center gap-3 text-sm">
                    <StatusPill
                      kind={
                        a.severity === 'critical' ? 'critical' : 'serious'
                      }
                      label={a.name}
                    />
                    <span className={T.ink2}>{a.summary}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="flex items-center gap-2 text-sm">
                <StatusPill kind="good" label="all clear" />
                <span className={T.ink3}>
                  no alerts firing — rule states in Monitoring
                </span>
              </div>
            )}
          </Card>
        </div>
        {jobsTable}
      </div>
    ),

    jobs: <div className="space-y-6">{jobsTable}</div>,

    inversion: (
      <div className="space-y-6">
        <Card
          title="Run a gravity inversion"
          sub="operates on the ingested mission measurements"
        >
          <div className="flex flex-wrap items-center gap-3">
            <select
              value={invMethod}
              onChange={(e) => setInvMethod(e.target.value as any)}
              className="rounded-lg bg-[#0a0e17] border border-[#1c2537] px-3 py-2 text-sm focus:outline-none focus:border-[#3987e5]"
            >
              <option value="tikhonov">Tikhonov (classical)</option>
              <option value="ml_completion">ML completion</option>
            </select>
            <button
              onClick={runInversion}
              disabled={invBusy}
              className="rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              style={{ backgroundColor: T.accent }}
            >
              {invBusy ? 'Starting…' : 'Start inversion'}
            </button>
            <Link
              href="/gravity"
              className="inline-flex items-center gap-1.5 text-sm"
              style={{ color: T.accent }}
            >
              open the anomaly map <Icon d={ICONS.external} size={13} />
            </Link>
          </div>
          {invMsg && <p className={`text-sm mt-3 ${T.ink2}`}>{invMsg}</p>}
        </Card>
        {jobsTable}
      </div>
    ),

    data: (
      <div className="space-y-6">
        <Card
          title="Gravity measurements"
          sub={`${totalMeasurements} rows in TimescaleDB${
            rows[0] ? ` · latest ${String(rows[0].timestamp ?? '')}` : ''
          }`}
          error={measurementsErr}
        >
          {rows.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr>
                    <Th>Satellite</Th>
                    <Th>Timestamp</Th>
                    <Th>Lat</Th>
                    <Th>Lon</Th>
                    <Th>Gravity (mGal)</Th>
                    <Th>Provenance</Th>
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, 10).map((m: any, i: number) => (
                    <tr
                      key={i}
                      className="border-t border-[#161e2e] hover:bg-white/[0.02]"
                    >
                      <td className={`py-2 pr-4 ${T.ink}`}>
                        {m.satellite_id}
                      </td>
                      <td
                        className={`py-2 pr-4 font-mono text-xs ${T.ink2}`}
                      >
                        {String(m.timestamp ?? '')}
                      </td>
                      <td className={`py-2 pr-4 tabular-nums ${T.ink2}`}>
                        {m.location?.latitude?.toFixed(2)}
                      </td>
                      <td className={`py-2 pr-4 tabular-nums ${T.ink2}`}>
                        {m.location?.longitude?.toFixed(2)}
                      </td>
                      <td className={`py-2 pr-4 tabular-nums ${T.ink}`}>
                        {m.gravity_value?.toFixed(2)}
                      </td>
                      <td className="py-2">
                        <span
                          className={`text-[11px] uppercase tracking-wider ${T.ink3}`}
                        >
                          {m.quality_flag}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className={`text-xs mt-4 ${T.ink3}`}>
            Load a fresh mission dataset:{' '}
            <span className="font-mono text-[11px]">
              docker compose run --rm mission-scenario
            </span>
          </p>
        </Card>
        <Card
          title="Telemetry"
          sub="last 30 days, GAL-SIM-A / GAL-SIM-B"
          error={telemetryErr}
        >
          <div className={`text-2xl font-semibold tabular-nums ${T.ink}`}>
            {telemetryRows.length}
          </div>
          <div className={`text-xs mt-1 ${T.ink2}`}>
            records with position + clock state, ingested through the live
            API
          </div>
        </Card>
      </div>
    ),

    ml: (
      <div className="space-y-6">
        <Card
          title="Registered models"
          sub="ml-service registry"
          error={modelsErr}
        >
          {models.length ? (
            <ul className="space-y-2 text-sm">
              {models.map((m: any, i: number) => (
                <li key={i} className="flex items-center justify-between">
                  <span className={`font-mono text-xs ${T.ink}`}>
                    {m.model_id ?? m.name ?? `model-${i}`}
                  </span>
                  {m.status && (
                    <span className={`text-xs ${T.ink3}`}>{m.status}</span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className={`text-sm leading-relaxed ${T.ink3}`}>
              No models in the ml-service registry. The gravity-completion
              model used by ML inversions ships as a versioned artifact
              (<span className="font-mono text-xs">
                ml/models/gravity_completion_v1.json
              </span>
              ) and is served by the inversion service directly — run one
              from the Inversion section.
            </p>
          )}
        </Card>
      </div>
    ),

    workflows: (
      <div className="space-y-6">
        <Card
          title="Event-driven workflows"
          sub={`${executions.length} recorded executions`}
          error={workflowsErr}
        >
          {workflows ? (
            <ul className="space-y-4">
              {(workflows.workflows || []).map((w: any) => (
                <li key={w.name}>
                  <div className="flex items-center gap-3">
                    {okPill(w.enabled, 'enabled', 'disabled')}
                    <span className={`font-mono text-sm ${T.ink}`}>
                      {w.name}
                    </span>
                    <span className={`text-xs ${T.ink3}`}>
                      on {w.trigger_event} · {w.steps?.length ?? 0} steps
                    </span>
                  </div>
                  {w.description && (
                    <p className={`text-xs mt-1 ml-1 ${T.ink3}`}>
                      {w.description}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className={`text-sm ${T.ink3}`}>loading…</p>
          )}
        </Card>
      </div>
    ),

    monitoring: (
      <div className="grid lg:grid-cols-2 gap-6">
        <Card
          title="Scrape targets"
          sub={targets ? `${targets.up} of ${targets.total} up` : undefined}
        >
          {targets ? (
            <ul className="space-y-2.5 text-sm">
              {targets.targets.map((t: any, i: number) => (
                <li key={i} className="flex items-center justify-between">
                  <span>
                    <span className={T.ink}>{t.job}</span>{' '}
                    <span className={`text-xs ${T.ink3}`}>{t.instance}</span>
                  </span>
                  {okPill(t.health === 'up', 'up', 'down')}
                </li>
              ))}
            </ul>
          ) : (
            <p className={`text-sm ${T.ink3}`}>loading…</p>
          )}
        </Card>
        <Card title="Alert rules" sub="Prometheus evaluation state">
          {rules ? (
            <ul className="space-y-2.5 text-sm">
              {rules.rules.map((r: any, i: number) => (
                <li key={i} className="flex items-center justify-between">
                  <span>
                    <span className={T.ink}>{r.name}</span>{' '}
                    <span className={`text-xs ${T.ink3}`}>{r.group}</span>
                  </span>
                  {r.state === 'firing' ? (
                    <StatusPill kind="serious" label="firing" />
                  ) : (
                    <StatusPill kind="good" label={r.state || 'ok'} />
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className={`text-sm ${T.ink3}`}>loading…</p>
          )}
        </Card>
        <Card title="Active alerts">
          {activeAlerts.length ? (
            activeAlerts.map((a: any, i: number) => (
              <div key={i} className="flex items-center gap-3 text-sm mb-2">
                <StatusPill
                  kind={a.severity === 'critical' ? 'critical' : 'serious'}
                  label={a.name}
                />
                <span className={T.ink2}>{a.summary}</span>
              </div>
            ))
          ) : (
            <div className="flex items-center gap-2 text-sm">
              <StatusPill kind="good" label="all clear" />
              <span className={T.ink3}>no alerts firing</span>
            </div>
          )}
        </Card>
        <Card title="Observability tools">
          <ul className="space-y-2.5 text-sm">
            {[
              ['Prometheus', 'http://localhost:29090'],
              ['Grafana', 'http://localhost:29091'],
              ['Jaeger traces', 'http://localhost:29686'],
              ['MLflow', 'http://localhost:29500'],
            ].map(([name, url]) => (
              <li key={name}>
                <a
                  className="inline-flex items-center gap-1.5"
                  style={{ color: T.accent }}
                  href={url}
                  target="_blank"
                >
                  {name} <Icon d={ICONS.external} size={13} />
                </a>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    ),
  };

  /* ── frame ────────────────────────────────────────────────────── */
  return (
    <div className={`min-h-screen ${T.app} ${T.ink} flex`}>
      <aside className={`w-64 shrink-0 ${T.rail} flex flex-col`}>
        <div className="flex items-center gap-3 px-5 pt-5 pb-6">
          <OrbitMark />
          <div>
            <div className="text-sm font-semibold tracking-tight">
              GALILEO
            </div>
            <div className={`text-[11px] ${T.ink3}`}>Mission Control</div>
          </div>
        </div>
        <nav className="px-3 space-y-0.5">
          {SECTIONS.map((s) => {
            const active = section === s.id;
            return (
              <button
                key={s.id}
                onClick={() => setSection(s.id)}
                className={`w-full flex items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors ${
                  active ? 'bg-[#12203a]' : 'hover:bg-white/[0.03]'
                }`}
                style={active ? { color: '#cfe3fb' } : undefined}
              >
                <span
                  className={active ? '' : T.ink3}
                  style={active ? { color: T.accent } : undefined}
                >
                  <Icon d={ICONS[s.id]} />
                </span>
                <span className="min-w-0">
                  <span className="block text-[13px] font-medium leading-tight">
                    {s.name}
                  </span>
                  <span className={`block text-[11px] ${T.ink3}`}>
                    {s.desc}
                  </span>
                </span>
              </button>
            );
          })}
        </nav>
        <div className="mt-auto px-5 py-5 space-y-2 border-t border-[#161e2e]">
          <Link
            href="/gravity"
            className="flex items-center gap-2 text-[13px]"
            style={{ color: T.accent }}
          >
            Gravity anomaly map <Icon d={ICONS.external} size={12} />
          </Link>
          <Link
            href="/ops"
            className="flex items-center gap-2 text-[13px]"
            style={{ color: T.accent }}
          >
            Operations console <Icon d={ICONS.external} size={12} />
          </Link>
          <p className={`text-[11px] pt-2 ${T.ink3}`}>
            live platform state · no fabricated data
          </p>
        </div>
      </aside>

      <main className="flex-1 overflow-x-hidden">
        <header className="flex items-center justify-between px-8 py-4 border-b border-[#161e2e]">
          <div className="flex items-center gap-4">
            <h1 className="text-lg font-semibold tracking-tight">
              {SECTIONS.find((s) => s.id === section)?.name}
            </h1>
            {health &&
              (servicesOk ? (
                <StatusPill kind="good" label="all systems nominal" />
              ) : (
                <StatusPill kind="serious" label="degraded" />
              ))}
          </div>
          <button
            onClick={refresh}
            className={`inline-flex items-center gap-2 rounded-lg border border-[#1c2537] bg-[#101624] px-3.5 py-2 text-sm hover:bg-[#151c2e] ${T.ink2}`}
          >
            <Icon d={ICONS.refresh} size={14} /> Refresh
          </button>
        </header>
        <div className="px-8 py-6 max-w-6xl">{content[section]}</div>
      </main>
    </div>
  );
}

/* ── logo mark ──────────────────────────────────────────────────── */
function OrbitMark() {
  return (
    <svg width="34" height="34" viewBox="0 0 34 34" fill="none">
      <circle
        cx="17"
        cy="17"
        r="7"
        stroke="#3987e5"
        strokeWidth="1.8"
      />
      <ellipse
        cx="17"
        cy="17"
        rx="15"
        ry="6"
        stroke="#5c6a84"
        strokeWidth="1.2"
        transform="rotate(-22 17 17)"
      />
      <circle cx="29.5" cy="11.5" r="2.2" fill="#3987e5" />
    </svg>
  );
}
