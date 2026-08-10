'use client';

/**
 * Operations console — real platform state, no decorative badges.
 *
 * Every panel is backed by a live endpoint: service health from the
 * gateway's own gRPC checks, scrape targets and alert rules from
 * Prometheus, active alerts from Alertmanager, workflows from the
 * event orchestrator. Failures render as failures.
 */

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import {
  Card,
  GATEWAY,
  Icon,
  ICONS,
  okPill,
  PageHeader,
  SignIn,
  StatusPill,
  T,
  useAuthToken,
} from '@/lib/console-ui';

export default function OpsPage() {
  const { token, error: authError, login } = useAuthToken();

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
      <SignIn
        subtitle="operations console"
        onLogin={login}
        error={authError}
      />
    );
  }

  const activeAlerts = alerts?.alerts ?? [];

  return (
    <div className={`min-h-screen ${T.app} ${T.ink}`}>
      <PageHeader
        title="Operations Console"
        badge={
          activeAlerts.length > 0 ? (
            <StatusPill
              kind="serious"
              label={`${activeAlerts.length} active alert${
                activeAlerts.length > 1 ? 's' : ''
              }`}
            />
          ) : health ? (
            <StatusPill kind="good" label="all systems nominal" />
          ) : undefined
        }
        actions={
          <>
            <Link href="/dashboard" className={T.btnGhost}>
              <Icon d={ICONS.back} size={14} /> Mission Control
            </Link>
            <button onClick={refresh} className={T.btnGhost}>
              <Icon d={ICONS.refresh} size={14} /> Refresh
            </button>
          </>
        }
      />

      <div className="px-8 py-6 max-w-6xl space-y-6">
        {activeAlerts.length > 0 && (
          <Card title="Active alerts" sub="Alertmanager, live">
            {activeAlerts.map((a: any, i: number) => (
              <div key={i} className="flex items-center gap-3 text-sm mb-2">
                <StatusPill
                  kind={a.severity === 'critical' ? 'critical' : 'serious'}
                  label={a.name}
                />
                <span className={T.ink2}>{a.summary}</span>
              </div>
            ))}
          </Card>
        )}

        <div className="grid md:grid-cols-2 gap-6">
          <Card
            title="Service health"
            sub="gateway gRPC checks"
            error={healthErr}
          >
            {health ? (
              <ul className="space-y-2.5 text-sm">
                <li className="flex items-center justify-between">
                  <span className={T.ink2}>api-gateway</span>
                  {okPill(health.status === 'healthy', health.status)}
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

          <Card
            title={`Monitoring targets${
              targets ? ` — ${targets.up}/${targets.total} up` : ''
            }`}
            sub="Prometheus scrape state"
            error={targetsErr}
          >
            {targets && (
              <ul className="space-y-2.5 text-sm">
                {targets.targets.map((t: any, i: number) => (
                  <li key={i} className="flex items-center justify-between">
                    <span>
                      <span className={T.ink}>{t.job}</span>{' '}
                      <span className={`text-xs ${T.ink3}`}>
                        {t.instance}
                      </span>
                      {t.last_error && (
                        <span
                          className="text-xs ml-2"
                          style={{ color: '#ec835a' }}
                        >
                          {t.last_error}
                        </span>
                      )}
                    </span>
                    {okPill(t.health === 'up', 'up', 'down')}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title="Alert rules"
            sub="Prometheus evaluation state"
            error={alertsErr}
          >
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

          <Card
            title="Workflow engine"
            sub={`${executions.length} recorded execution${
              executions.length === 1 ? '' : 's'
            }`}
            error={workflowsErr}
          >
            {workflows ? (
              <ul className="space-y-3 text-sm">
                {(workflows.workflows || []).map((w: any) => (
                  <li key={w.name}>
                    <div className="flex items-center gap-3">
                      {okPill(w.enabled, 'enabled', 'disabled')}
                      <span className={`font-mono text-xs ${T.ink}`}>
                        {w.name}
                      </span>
                    </div>
                    <p className={`text-xs mt-1 ${T.ink3}`}>
                      on {w.trigger_event} · {w.steps?.length ?? 0} steps
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className={`text-sm ${T.ink3}`}>loading…</p>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
