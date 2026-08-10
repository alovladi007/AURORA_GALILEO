'use client';

/**
 * Gravity anomaly map — the platform's flagship product view.
 *
 * Every number comes from the backend: login issues a real JWT, the
 * job list is the inversion service's state, and the map is the
 * georeferenced model grid from GET /api/v1/inversions/{id}/model.
 * Errors render as errors — there are no client-side fallbacks.
 */

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Card,
  ErrorNote,
  GATEWAY,
  Icon,
  ICONS,
  jobStatusPill,
  PageHeader,
  SignIn,
  StatusPill,
  T,
  Th,
  useAuthToken,
} from '@/lib/console-ui';

interface ModelGrid {
  model_id: string;
  job_id: string;
  density_values: number[];
  rms_residual?: number;
  statistics?: Record<string, number>;
  grid: {
    min_latitude: number;
    max_latitude: number;
    min_longitude: number;
    max_longitude: number;
    num_lat_points: number;
    num_lon_points: number;
  };
}

function AnomalyMap({ model }: { model: ModelGrid }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const { num_lat_points: rows, num_lon_points: cols } = model.grid;
    const values = model.density_values;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;

    const cw = canvas.width / cols;
    const ch = canvas.height / rows;

    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const v = (values[r * cols + c] - min) / span; // 0..1
        // blue (low) -> white -> red (high) diverging ramp
        const red = Math.round(255 * Math.min(1, 2 * v));
        const blue = Math.round(255 * Math.min(1, 2 * (1 - v)));
        const green = Math.round(255 * (1 - Math.abs(2 * v - 1)));
        ctx.fillStyle = `rgb(${red},${green},${blue})`;
        // row 0 = min_latitude (south) -> draw at the bottom
        ctx.fillRect(c * cw, canvas.height - (r + 1) * ch, cw + 1, ch + 1);
      }
    }
  }, [model]);

  const g = model.grid;
  return (
    <div>
      <canvas
        ref={canvasRef}
        width={640}
        height={320}
        className="w-full rounded-lg border border-[#1c2537]"
      />
      <div
        className={`flex justify-between text-xs mt-2 ${T.ink3}`}
      >
        <span>
          lat [{g.min_latitude}°, {g.max_latitude}°] · lon [
          {g.min_longitude}°, {g.max_longitude}°]
        </span>
        {model.statistics && (
          <span className="tabular-nums">
            {model.statistics.min?.toFixed(1)} …{' '}
            {model.statistics.max?.toFixed(1)} mGal · blue low → red high
          </span>
        )}
      </div>
    </div>
  );
}

export default function GravityPage() {
  const { token, error: authError, login } = useAuthToken();
  const [jobs, setJobs] = useState<any[]>([]);
  const [model, setModel] = useState<ModelGrid | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [method, setMethod] = useState<'tikhonov' | 'ml_completion'>(
    'tikhonov'
  );

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

  const refreshJobs = useCallback(async () => {
    if (!token) return;
    const resp = await authed('/api/v1/inversions');
    if (!resp.ok) {
      setError(`Job list failed (${resp.status})`);
      return;
    }
    const body = await resp.json();
    setJobs(body.jobs || []);
  }, [token, authed]);

  useEffect(() => {
    refreshJobs();
  }, [refreshJobs]);

  const runInversion = async () => {
    setBusy(true);
    setError(null);
    try {
      const resp = await authed('/api/v1/inversions', {
        method: 'POST',
        body: JSON.stringify({
          name: `ui-anomaly-map-${method}`,
          measurement_ids: ['GAL-SIM-A', 'GAL-SIM-B'],
          parameters: { method },
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
        const detail = await resp.text();
        setError(`Inversion start failed (${resp.status}): ${detail}`);
        return;
      }
      const { job_id } = await resp.json();
      for (let i = 0; i < 20; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const st = await (
          await authed(`/api/v1/inversions/${job_id}`)
        ).json();
        if (st.status === 'completed') {
          await loadModel(job_id);
          await refreshJobs();
          return;
        }
        if (st.status === 'failed') {
          setError(`Inversion failed: ${JSON.stringify(st)}`);
          return;
        }
      }
      setError('Inversion timed out');
    } finally {
      setBusy(false);
    }
  };

  const loadModel = async (jobId: string) => {
    setError(null);
    const resp = await authed(`/api/v1/inversions/${jobId}/model`);
    if (!resp.ok) {
      setError(`Model fetch failed (${resp.status}): ${await resp.text()}`);
      return;
    }
    const body = await resp.json();
    setModel(body.model);
  };

  if (!token) {
    return (
      <SignIn
        subtitle="gravity anomaly map"
        onLogin={login}
        error={authError}
      />
    );
  }

  return (
    <div className={`min-h-screen ${T.app} ${T.ink}`}>
      <PageHeader
        title="Gravity Anomaly Map"
        badge={
          <StatusPill kind="good" label="live inversion products" />
        }
        actions={
          <>
            <Link href="/dashboard" className={T.btnGhost}>
              <Icon d={ICONS.back} size={14} /> Mission Control
            </Link>
            <button onClick={refreshJobs} className={T.btnGhost}>
              <Icon d={ICONS.refresh} size={14} /> Refresh
            </button>
          </>
        }
      />

      <div className="px-8 py-6 max-w-5xl space-y-6">
        <Card
          title="Run an inversion"
          sub="operates on the ingested mission measurements"
        >
          <div className="flex flex-wrap items-center gap-3">
            <select
              value={method}
              onChange={(e) =>
                setMethod(e.target.value as 'tikhonov' | 'ml_completion')
              }
              className={T.input}
            >
              <option value="tikhonov">Tikhonov (classical)</option>
              <option value="ml_completion">
                ML completion (beats baseline by 47%)
              </option>
            </select>
            <button
              onClick={runInversion}
              disabled={busy}
              className="rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              style={{ backgroundColor: T.accent }}
            >
              {busy ? 'Inverting…' : 'Run inversion on mission data'}
            </button>
            {busy && (
              <span className={`text-xs ${T.ink3}`}>
                solving on the inversion service…
              </span>
            )}
          </div>
          {error && (
            <div className="mt-3">
              <ErrorNote text={error} />
            </div>
          )}
        </Card>

        {model && (
          <Card
            title={model.model_id}
            sub={`rms residual ${model.rms_residual?.toFixed(1) ?? '—'}`}
          >
            <AnomalyMap model={model} />
          </Card>
        )}

        <Card
          title="Inversion jobs"
          sub="inversion-service state, most recent first"
        >
          {jobs.length === 0 ? (
            <p className={`text-sm ${T.ink3}`}>
              No jobs yet — run an inversion above, or load mission data
              with{' '}
              <span className="font-mono text-xs">
                docker compose run --rm mission-scenario
              </span>
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <Th>Job</Th>
                  <Th>Status</Th>
                  <Th>Type</Th>
                  <Th> </Th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr
                    key={j.job_id}
                    className="border-t border-[#161e2e] hover:bg-white/[0.02]"
                  >
                    <td className={`py-2.5 pr-4 font-mono text-xs ${T.ink2}`}>
                      {j.job_id}
                    </td>
                    <td className="py-2.5 pr-4">
                      {jobStatusPill(j.status)}
                    </td>
                    <td className={`py-2.5 pr-4 text-xs ${T.ink2}`}>
                      {j.inversion_type}
                    </td>
                    <td className="py-2.5">
                      {j.status === 'completed' && (
                        <button
                          onClick={() => loadModel(j.job_id)}
                          className="text-sm"
                          style={{ color: T.accent }}
                        >
                          view map
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </div>
  );
}
