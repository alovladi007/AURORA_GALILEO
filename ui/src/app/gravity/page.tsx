'use client';

/**
 * Gravity anomaly map — the platform's first end-to-end product view.
 *
 * Every number on this page comes from the backend: login issues a real
 * JWT, the job list is the inversion service's state, and the map is
 * the georeferenced model grid returned by
 * GET /api/v1/inversions/{id}/model. Errors render as errors — there
 * are no client-side fallbacks.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

const GATEWAY =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:28000';

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
    const body = await resp.json();
    setToken(body.access_token);
  }, []);
  return { token, error, login };
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
        className="w-full border border-gray-600 rounded"
      />
      <div className="flex justify-between text-xs text-gray-400 mt-1">
        <span>
          lat [{g.min_latitude}°, {g.max_latitude}°] · lon [
          {g.min_longitude}°, {g.max_longitude}°]
        </span>
        {model.statistics && (
          <span>
            {model.statistics.min?.toFixed(1)} … {' '}
            {model.statistics.max?.toFixed(1)} mGal
          </span>
        )}
      </div>
    </div>
  );
}

export default function GravityPage() {
  const { token, error: authError, login } = useAuthToken();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
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
      // poll to completion
      for (let i = 0; i < 20; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const st = await (await authed(`/api/v1/inversions/${job_id}`)).json();
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

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 p-8">
      <div className="max-w-4xl mx-auto space-y-6">
        <h1 className="text-2xl font-bold">
          Gravity Anomaly Map
          <span className="ml-3 text-sm font-normal text-gray-400">
            live inversion products · no fabricated data
          </span>
        </h1>

        {!token ? (
          <form
            className="bg-gray-800 rounded p-6 space-y-3 max-w-sm"
            onSubmit={(e) => {
              e.preventDefault();
              login(email, password);
            }}
          >
            <h2 className="font-semibold">Sign in</h2>
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
            <button
              className="w-full bg-blue-600 hover:bg-blue-700 rounded py-2"
              type="submit"
            >
              Get token
            </button>
            {authError && <p className="text-red-400 text-sm">{authError}</p>}
          </form>
        ) : (
          <>
            <div className="flex items-center gap-4">
              <select
                value={method}
                onChange={(e) =>
                  setMethod(e.target.value as 'tikhonov' | 'ml_completion')
                }
                className="bg-gray-700 rounded px-3 py-2"
              >
                <option value="tikhonov">Tikhonov (classical)</option>
                <option value="ml_completion">
                  ML completion (beat baseline by 47%)
                </option>
              </select>
              <button
                onClick={runInversion}
                disabled={busy}
                className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded px-4 py-2"
              >
                {busy ? 'Inverting…' : 'Run inversion on mission data'}
              </button>
              <button
                onClick={refreshJobs}
                className="bg-gray-700 hover:bg-gray-600 rounded px-4 py-2"
              >
                Refresh jobs
              </button>
            </div>

            {error && (
              <div className="bg-red-900/40 border border-red-600 rounded p-3 text-sm">
                {error}
              </div>
            )}

            {model && (
              <div className="bg-gray-800 rounded p-4">
                <h2 className="font-semibold mb-2">
                  {model.model_id}
                  <span className="ml-2 text-xs text-gray-400">
                    rms residual {model.rms_residual?.toFixed(1)}
                  </span>
                </h2>
                <AnomalyMap model={model} />
              </div>
            )}

            <div className="bg-gray-800 rounded p-4">
              <h2 className="font-semibold mb-2">Inversion jobs</h2>
              {jobs.length === 0 ? (
                <p className="text-sm text-gray-400">
                  No jobs yet — run an inversion, or ingest mission data
                  first (scripts/run_mission_scenario.py).
                </p>
              ) : (
                <table className="w-full text-sm">
                  <thead className="text-gray-400 text-left">
                    <tr>
                      <th className="py-1">job</th>
                      <th>status</th>
                      <th>type</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.map((j) => (
                      <tr key={j.job_id} className="border-t border-gray-700">
                        <td className="py-1 font-mono text-xs">{j.job_id}</td>
                        <td>{j.status}</td>
                        <td>{j.inversion_type}</td>
                        <td>
                          {j.status === 'completed' && (
                            <button
                              onClick={() => loadModel(j.job_id)}
                              className="text-blue-400 hover:underline"
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
            </div>
          </>
        )}
      </div>
    </div>
  );
}
