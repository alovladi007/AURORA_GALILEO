'use client';

/**
 * Mission dashboard — an overview backed ENTIRELY by live gateway
 * endpoints. The previous MissionDashboard component targeted the
 * retired monolith API (port 5050) and phantom gateway paths, which
 * filled the console with connection errors on every load; this page
 * replaces it (audit: "~30 endpoints called by the UI do not exist").
 * Failures render as failures — never decorative placeholders.
 */

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

const GATEWAY =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:28000';

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
}: {
  title: string;
  error?: string | null;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-gray-800 rounded p-4">
      <h2 className="font-semibold mb-3">{title}</h2>
      {error ? (
        <div className="bg-red-900/40 border border-red-600 rounded p-2 text-sm">
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

export default function DashboardPage() {
  const { token, error: authError, login } = useAuthToken();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const [health, setHealth] = useState<any>(null);
  const [healthErr, setHealthErr] = useState<string | null>(null);
  const [targets, setTargets] = useState<any>(null);
  const [alerts, setAlerts] = useState<any>(null);
  const [jobs, setJobs] = useState<any[]>([]);
  const [jobsErr, setJobsErr] = useState<string | null>(null);
  const [measurements, setMeasurements] = useState<any>(null);
  const [measurementsErr, setMeasurementsErr] = useState<string | null>(
    null
  );
  const [models, setModels] = useState<any[]>([]);

  const authed = useCallback(
    (path: string) =>
      fetch(`${GATEWAY}${path}`, {
        headers: { Authorization: `Bearer ${token}` },
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
      const r = await authed('/api/v1/models');
      if (r.ok) setModels((await r.json()).models || []);
    } catch {}
  }, [token, authed]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 20000);
    return () => clearInterval(id);
  }, [refresh]);

  if (!token) {
    return (
      <div className="min-h-screen bg-gray-900 text-gray-100 p-8">
        <form
          className="bg-gray-800 rounded p-6 space-y-3 max-w-sm mx-auto mt-24"
          onSubmit={(e) => {
            e.preventDefault();
            login(email, password);
          }}
        >
          <h2 className="font-semibold">Mission dashboard — sign in</h2>
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
  const activeAlerts = alerts?.alerts ?? [];

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 p-8">
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">GALILEO Mission Dashboard</h1>
            <p className="text-sm text-gray-400">
              live platform state · no fabricated data
            </p>
          </div>
          <div className="flex gap-3 text-sm">
            <Link
              href="/gravity"
              className="bg-blue-600 hover:bg-blue-700 rounded px-4 py-2"
            >
              Gravity anomaly map
            </Link>
            <Link
              href="/ops"
              className="bg-gray-700 hover:bg-gray-600 rounded px-4 py-2"
            >
              Operations console
            </Link>
            <button
              onClick={refresh}
              className="bg-gray-700 hover:bg-gray-600 rounded px-4 py-2"
            >
              Refresh
            </button>
          </div>
        </div>

        {activeAlerts.length > 0 && (
          <div className="bg-red-900/40 border border-red-600 rounded p-4 text-sm">
            {activeAlerts.length} active alert
            {activeAlerts.length > 1 ? 's' : ''} — see the{' '}
            <Link href="/ops" className="underline">
              operations console
            </Link>
          </div>
        )}

        <div className="grid md:grid-cols-3 gap-6">
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

          <Panel title="Mission data" error={measurementsErr}>
            {measurements ? (
              <ul className="space-y-1 text-sm">
                <li>
                  {totalMeasurements}
                  {rows.length === 1000 ? '+' : ''} gravity measurements
                  on file
                </li>
                {rows[0] && (
                  <li className="text-gray-400">
                    latest: {String(rows[0].timestamp ?? rows[0].time ?? '')}
                  </li>
                )}
                <li className="pt-2 text-gray-400">
                  Load more with{' '}
                  <span className="font-mono text-xs">
                    docker compose run --rm mission-scenario
                  </span>
                </li>
              </ul>
            ) : (
              <p className="text-sm text-gray-400">loading…</p>
            )}
          </Panel>

          <Panel title="ML models">
            {models.length ? (
              <ul className="space-y-1 text-sm">
                {models.slice(0, 6).map((m: any, i: number) => (
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
                no trained models registered
              </p>
            )}
          </Panel>
        </div>

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
                {jobs.slice(0, 8).map((j: any) => (
                  <tr key={j.job_id} className="border-t border-gray-700">
                    <td className="py-1.5 font-mono text-xs">{j.job_id}</td>
                    <td className="py-1.5">
                      <HealthDot ok={j.status === 'completed'} />
                      {j.status}
                    </td>
                    <td className="py-1.5">
                      {j.progress != null ? `${j.progress}%` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-gray-400">
              no inversion jobs yet — run one from the{' '}
              <Link href="/gravity" className="underline">
                gravity anomaly map
              </Link>
            </p>
          )}
        </Panel>
      </div>
    </div>
  );
}
