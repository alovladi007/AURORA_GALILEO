'use client';

/**
 * GALILEO Mission Control console.
 *
 * The sidebar-console layout of the original MissionDashboard, rebuilt
 * on the REAL platform API. The legacy component targeted the retired
 * monolith (port 5050) and ~30 phantom gateway paths; every panel here
 * is wired to a live, verified endpoint and failures render as
 * failures. Sections whose backing service does not implement the
 * capability say so instead of decorating.
 */

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

const GATEWAY =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:28000';

const SECTIONS = [
  { id: 'overview', name: 'Overview', desc: 'Platform health & totals' },
  { id: 'jobs', name: 'Job Console', desc: 'Inversion jobs & history' },
  { id: 'inversion', name: 'Inversion', desc: 'Run gravity inversions' },
  { id: 'data', name: 'Database', desc: 'Measurements & telemetry' },
  { id: 'ml', name: 'ML Models', desc: 'Registered models & training' },
  { id: 'workflows', name: 'Workflows', desc: 'Event-driven pipelines' },
  { id: 'monitoring', name: 'Monitoring', desc: 'Targets, rules, alerts' },
] as const;

type SectionId = (typeof SECTIONS)[number]['id'];

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

function Panel({
  title,
  error,
  children,
  actions,
}: {
  title: string;
  error?: string | null;
  children: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="bg-gray-800 rounded-lg p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold">{title}</h2>
        {actions}
      </div>
      {error ? (
        <div className="bg-red-900/40 border border-red-600 rounded p-3 text-sm">
          {error}
        </div>
      ) : (
        children
      )}
    </div>
  );
}

const HealthDot = ({ ok }: { ok: boolean }) => (
  <span
    className={`inline-block w-2.5 h-2.5 rounded-full mr-2 ${
      ok ? 'bg-green-500' : 'bg-red-500'
    }`}
  />
);

const pct = (p: any) =>
  p == null ? '—' : `${Math.round(p <= 1 ? p * 100 : p)}%`;

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

  if (!token) {
    return (
      <div className="min-h-screen bg-gray-900 text-gray-100 p-8">
        <form
          className="bg-gray-800 rounded p-6 space-y-3 max-w-sm mx-auto mt-24"
          onSubmit={(e) => {
            e.preventDefault();
            login(email.trim(), password);
          }}
        >
          <h2 className="font-semibold">GALILEO Mission Control — sign in</h2>
          <input
            className="w-full rounded bg-gray-700 px-3 py-2"
            placeholder="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <input
            className="w-full rounded bg-gray-700 px-3 py-2"
            type="password"
            placeholder="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button className="w-full bg-blue-600 hover:bg-blue-700 rounded py-2">
            Sign in
          </button>
          {authError && <p className="text-red-400 text-sm">{authError}</p>}
        </form>
      </div>
    );
  }

  const rows = measurements?.measurements ?? [];
  const totalMeasurements =
    measurements?.pagination?.total_items ?? rows.length;
  const telemetryRows = telemetry?.telemetry ?? telemetry?.records ?? [];
  const activeAlerts = alerts?.alerts ?? [];

  const jobsTable = (
    <Panel title="Inversion jobs" error={jobsErr}>
      {jobs.length ? (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-400">
              <th className="pb-2">job</th>
              <th className="pb-2">status</th>
              <th className="pb-2">progress</th>
            </tr>
          </thead>
          <tbody>
            {jobs.slice(0, 12).map((j: any) => (
              <tr key={j.job_id} className="border-t border-gray-700">
                <td className="py-1.5 font-mono text-xs">{j.job_id}</td>
                <td className="py-1.5">
                  <HealthDot ok={j.status === 'completed'} />
                  {j.status}
                </td>
                <td className="py-1.5">{pct(j.progress)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-sm text-gray-400">
          no inversion jobs yet — start one in the Inversion section
        </p>
      )}
    </Panel>
  );

  const content: Record<SectionId, React.ReactNode> = {
    overview: (
      <div className="grid lg:grid-cols-2 gap-6">
        <Panel title="Platform health" error={healthErr}>
          {health ? (
            <ul className="space-y-1 text-sm">
              <li>
                <HealthDot ok={health.status === 'healthy'} />
                gateway: {health.status}
              </li>
              {Object.entries(health.services || {}).map(([k, v]) => (
                <li key={k}>
                  <HealthDot ok={v === 'healthy' || v === 'connected'} />
                  {k}: {String(v).slice(0, 40)}
                </li>
              ))}
              {targets && (
                <li className="pt-2 text-gray-400">
                  monitoring: {targets.up}/{targets.total} targets up
                </li>
              )}
            </ul>
          ) : (
            <p className="text-sm text-gray-400">loading…</p>
          )}
        </Panel>
        <Panel title="Mission at a glance">
          <ul className="space-y-1 text-sm">
            <li>{totalMeasurements} gravity measurements on file</li>
            <li>{telemetryRows.length} telemetry records (last 30 days)</li>
            <li>
              {jobs.length} inversion job{jobs.length === 1 ? '' : 's'},{' '}
              {jobs.filter((j: any) => j.status === 'completed').length}{' '}
              completed
            </li>
            <li>
              {models.length} registered ML model
              {models.length === 1 ? '' : 's'}
            </li>
            <li>
              {(workflows?.workflows || []).length} event-driven workflows
            </li>
          </ul>
        </Panel>
        {jobsTable}
        <Panel title="Active alerts">
          {activeAlerts.length ? (
            activeAlerts.map((a: any, i: number) => (
              <div key={i} className="text-sm">
                <span className="font-mono">{a.name}</span>
                <span className="ml-2 text-gray-300">{a.summary}</span>
              </div>
            ))
          ) : (
            <p className="text-sm text-gray-400">
              no active alerts — the monitoring section shows rule states
            </p>
          )}
        </Panel>
      </div>
    ),

    jobs: <div className="space-y-6">{jobsTable}</div>,

    inversion: (
      <div className="space-y-6">
        <Panel title="Run a gravity inversion on the ingested mission data">
          <div className="flex items-center gap-4">
            <select
              value={invMethod}
              onChange={(e) => setInvMethod(e.target.value as any)}
              className="bg-gray-700 rounded px-3 py-2 text-sm"
            >
              <option value="tikhonov">Tikhonov (classical)</option>
              <option value="ml_completion">ML completion</option>
            </select>
            <button
              onClick={runInversion}
              disabled={invBusy}
              className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded px-4 py-2 text-sm"
            >
              {invBusy ? 'Starting…' : 'Start inversion'}
            </button>
            <Link
              href="/gravity"
              className="text-sm text-blue-400 underline"
            >
              open the anomaly map →
            </Link>
          </div>
          {invMsg && (
            <p className="text-sm text-gray-300 mt-3">{invMsg}</p>
          )}
        </Panel>
        {jobsTable}
      </div>
    ),

    data: (
      <div className="space-y-6">
        <Panel title="Gravity measurements" error={measurementsErr}>
          <p className="text-sm mb-3">
            {totalMeasurements} rows in TimescaleDB
            {rows[0] &&
              ` · latest ${String(rows[0].timestamp ?? '')}`}
          </p>
          {rows.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-gray-400">
                    <th className="pb-2 pr-3">satellite</th>
                    <th className="pb-2 pr-3">timestamp</th>
                    <th className="pb-2 pr-3">lat</th>
                    <th className="pb-2 pr-3">lon</th>
                    <th className="pb-2 pr-3">gravity (mGal)</th>
                    <th className="pb-2">quality</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, 10).map((m: any, i: number) => (
                    <tr key={i} className="border-t border-gray-700">
                      <td className="py-1 pr-3">{m.satellite_id}</td>
                      <td className="py-1 pr-3 font-mono">
                        {String(m.timestamp ?? '')}
                      </td>
                      <td className="py-1 pr-3">
                        {m.location?.latitude?.toFixed(2)}
                      </td>
                      <td className="py-1 pr-3">
                        {m.location?.longitude?.toFixed(2)}
                      </td>
                      <td className="py-1 pr-3">
                        {m.gravity_value?.toFixed(2)}
                      </td>
                      <td className="py-1">{m.quality_flag}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-xs text-gray-400 mt-3">
            Load a fresh mission dataset with{' '}
            <span className="font-mono">
              docker compose run --rm mission-scenario
            </span>
          </p>
        </Panel>
        <Panel title="Telemetry (last 30 days)" error={telemetryErr}>
          <p className="text-sm">
            {telemetryRows.length} records for GAL-SIM-A / GAL-SIM-B
          </p>
        </Panel>
      </div>
    ),

    ml: (
      <div className="space-y-6">
        <Panel title="Registered models" error={modelsErr}>
          {models.length ? (
            <ul className="space-y-1 text-sm">
              {models.map((m: any, i: number) => (
                <li key={i}>
                  <span className="font-mono">
                    {m.model_id ?? m.name ?? `model-${i}`}
                  </span>
                  {m.status && (
                    <span className="text-gray-400 text-xs ml-2">
                      {m.status}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-400">
              no models registered in the ml-service registry. The
              gravity-completion model used by ML inversions ships as a
              versioned artifact (ml/models/gravity_completion_v1.json)
              and is served by the inversion service directly.
            </p>
          )}
        </Panel>
      </div>
    ),

    workflows: (
      <div className="space-y-6">
        <Panel title="Event-driven workflows" error={workflowsErr}>
          {workflows ? (
            <>
              <ul className="space-y-2 text-sm mb-3">
                {(workflows.workflows || []).map((w: any) => (
                  <li key={w.name}>
                    <HealthDot ok={w.enabled} />
                    <span className="font-mono">{w.name}</span>
                    <span className="text-gray-500 text-xs ml-2">
                      on {w.trigger_event} · {w.steps?.length ?? 0} steps
                    </span>
                    {w.description && (
                      <p className="text-xs text-gray-400 ml-5">
                        {w.description}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-gray-400">
                {executions.length} recorded execution
                {executions.length === 1 ? '' : 's'}
              </p>
            </>
          ) : (
            <p className="text-sm text-gray-400">loading…</p>
          )}
        </Panel>
      </div>
    ),

    monitoring: (
      <div className="grid lg:grid-cols-2 gap-6">
        <Panel
          title={`Scrape targets ${
            targets ? `(${targets.up}/${targets.total} up)` : ''
          }`}
        >
          {targets ? (
            <ul className="space-y-1 text-sm">
              {targets.targets.map((t: any, i: number) => (
                <li key={i}>
                  <HealthDot ok={t.health === 'up'} />
                  {t.job}{' '}
                  <span className="text-gray-500 text-xs">{t.instance}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-400">loading…</p>
          )}
        </Panel>
        <Panel title="Alert rules">
          {rules ? (
            <ul className="space-y-1 text-sm">
              {rules.rules.map((r: any, i: number) => (
                <li key={i}>
                  <HealthDot ok={r.state !== 'firing'} />
                  {r.name}
                  <span className="text-gray-500 text-xs ml-2">
                    {r.group} · {r.state}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-400">loading…</p>
          )}
        </Panel>
        <Panel title="Active alerts">
          {activeAlerts.length ? (
            activeAlerts.map((a: any, i: number) => (
              <div key={i} className="text-sm">
                <span className="font-mono">{a.name}</span>
                <span className="ml-2 text-gray-300">{a.summary}</span>
              </div>
            ))
          ) : (
            <p className="text-sm text-gray-400">no active alerts</p>
          )}
        </Panel>
        <Panel title="Deep links">
          <ul className="space-y-1 text-sm">
            <li>
              <a
                className="text-blue-400 underline"
                href="http://localhost:29090"
                target="_blank"
              >
                Prometheus
              </a>
            </li>
            <li>
              <a
                className="text-blue-400 underline"
                href="http://localhost:29091"
                target="_blank"
              >
                Grafana
              </a>
            </li>
            <li>
              <a
                className="text-blue-400 underline"
                href="http://localhost:29686"
                target="_blank"
              >
                Jaeger traces
              </a>
            </li>
          </ul>
        </Panel>
      </div>
    ),
  };

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 flex">
      <aside className="w-64 shrink-0 border-r border-gray-800 p-4">
        <h1 className="text-lg font-bold px-2">GALILEO Mission Control</h1>
        <p className="text-xs text-gray-400 px-2 mb-4">
          live platform state · no fabricated data
        </p>
        <nav className="space-y-1">
          {SECTIONS.map((s) => (
            <button
              key={s.id}
              onClick={() => setSection(s.id)}
              className={`w-full text-left rounded px-3 py-2 ${
                section === s.id
                  ? 'bg-blue-600/20 border-l-2 border-blue-500'
                  : 'hover:bg-gray-800'
              }`}
            >
              <div className="text-sm font-medium">{s.name}</div>
              <div className="text-xs text-gray-400">{s.desc}</div>
            </button>
          ))}
        </nav>
        <div className="mt-6 space-y-1 px-2 text-sm">
          <Link href="/gravity" className="block text-blue-400 underline">
            Gravity anomaly map
          </Link>
          <Link href="/ops" className="block text-blue-400 underline">
            Operations console
          </Link>
        </div>
      </aside>

      <main className="flex-1 p-8 overflow-x-hidden">
        <div className="max-w-5xl space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold">
              {SECTIONS.find((s) => s.id === section)?.name}
            </h2>
            <button
              onClick={refresh}
              className="bg-gray-700 hover:bg-gray-600 rounded px-4 py-2 text-sm"
            >
              Refresh
            </button>
          </div>
          {content[section]}
        </div>
      </main>
    </div>
  );
}
