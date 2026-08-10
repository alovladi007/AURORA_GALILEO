'use client';

/**
 * Operations console — real platform state, no decorative badges.
 *
 * Every panel is backed by a live endpoint: service health from the
 * gateway's own gRPC checks, scrape targets and alert rules from
 * Prometheus, active alerts from Alertmanager, workflows from the
 * event orchestrator. Failures render as failures.
 */

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

export default function OpsPage() {
  const { token, error: authError, login } = useAuthToken();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const [health, setHealth] = useState<any>(null);
  const [healthErr, setHealthErr] = useState<string | null>(null);
  const [targets, setTargets] = useState<any>(null);
  const [targetsErr, setTargetsErr] = useState<string | null>(null);
  const [alerts, setAlerts] = useState<any>(null);
  const [alertsErr, setAlertsErr] = useState<string | null>(null);
  const [rules, setRules] = useState<any>(null);
  const [workflows, setWorkflows] = useState<any>(null);
  const [workflowsErr, setWorkflowsErr] = useState<string | null>(null);
  const [executions, setExecutions] = useState<any[]>([]);

  const authed = useCallback(
    (path: string) =>
      fetch(`${GATEWAY}${path}`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
    [token]
  );

  const refresh = useCallback(async () => {
    if (!token) return;
    // Health (unauthenticated endpoint, but fetch uniformly)
    try {
      const r = await fetch(`${GATEWAY}/health`);
      r.ok
        ? setHealth(await r.json())
        : setHealthErr(`health ${r.status}`);
    } catch (e: any) {
      setHealthErr(String(e));
    }
    try {
      const r = await authed('/api/v1/ops/targets');
      r.ok
        ? (setTargets(await r.json()), setTargetsErr(null))
        : setTargetsErr(`targets ${r.status}: ${await r.text()}`);
    } catch (e: any) {
      setTargetsErr(String(e));
    }
    try {
      const r = await authed('/api/v1/ops/alerts');
      r.ok
        ? (setAlerts(await r.json()), setAlertsErr(null))
        : setAlertsErr(`alerts ${r.status}: ${await r.text()}`);
    } catch (e: any) {
      setAlertsErr(String(e));
    }
    try {
      const r = await authed('/api/v1/ops/rules');
      if (r.ok) setRules(await r.json());
    } catch {}
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
    const id = setInterval(refresh, 15000);
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
          <h2 className="font-semibold">Operations console — sign in</h2>
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

  const activeAlerts = alerts?.alerts ?? [];

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 p-8">
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Operations Console</h1>
          <button
            onClick={refresh}
            className="bg-gray-700 hover:bg-gray-600 rounded px-4 py-2 text-sm"
          >
            Refresh
          </button>
        </div>

        {activeAlerts.length > 0 && (
          <div className="bg-red-900/40 border border-red-600 rounded p-4">
            <h2 className="font-semibold text-red-300 mb-2">
              {activeAlerts.length} active alert
              {activeAlerts.length > 1 ? 's' : ''}
            </h2>
            {activeAlerts.map((a: any, i: number) => (
              <div key={i} className="text-sm">
                <span className="font-mono">{a.name}</span>
                {a.severity && (
                  <span className="ml-2 text-xs uppercase text-red-400">
                    {a.severity}
                  </span>
                )}
                <span className="ml-2 text-gray-300">{a.summary}</span>
              </div>
            ))}
          </div>
        )}

        <div className="grid md:grid-cols-2 gap-6">
          <Panel title="Service health (gateway gRPC checks)" error={healthErr}>
            {health ? (
              <ul className="space-y-1 text-sm">
                <li>
                  <HealthDot ok={health.status === 'healthy'} />
                  gateway: {health.status}
                </li>
                {Object.entries(health.services || {}).map(([k, v]) => (
                  <li key={k}>
                    <HealthDot
                      ok={v === 'healthy' || v === 'connected'}
                    />
                    {k}: {String(v).slice(0, 60)}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-gray-400">loading…</p>
            )}
          </Panel>

          <Panel
            title={`Monitoring targets ${
              targets ? `(${targets.up}/${targets.total} up)` : ''
            }`}
            error={targetsErr}
          >
            {targets && (
              <ul className="space-y-1 text-sm">
                {targets.targets.map((t: any, i: number) => (
                  <li key={i}>
                    <HealthDot ok={t.health === 'up'} />
                    {t.job}{' '}
                    <span className="text-gray-500 text-xs">
                      {t.instance}
                    </span>
                    {t.last_error && (
                      <span className="text-red-400 text-xs ml-2">
                        {t.last_error}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel title="Alert rules" error={alertsErr}>
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

          <Panel title="Workflow engine" error={workflowsErr}>
            {workflows ? (
              <>
                <ul className="space-y-1 text-sm mb-3">
                  {(workflows.workflows || []).map((w: any) => (
                    <li key={w.name}>
                      <HealthDot ok={w.enabled} />
                      <span className="font-mono">{w.name}</span>
                      <span className="text-gray-500 text-xs ml-2">
                        on {w.trigger_event} · {w.steps?.length ?? 0} steps
                      </span>
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
      </div>
    </div>
  );
}
