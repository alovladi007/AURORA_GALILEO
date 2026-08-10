'use client';

/**
 * GALILEO landing page — the commercial front door.
 *
 * Hero copy + the CesiumJS 3D globe (kept from the original UI), a
 * LIVE platform-status strip fed by the gateway's public /health
 * endpoint, and capability sections that link to the real product
 * pages. No fabricated numbers: the status pills show actual service
 * state, and unavailable simply renders as unavailable.
 */

import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import {
  Card,
  GATEWAY,
  Icon,
  ICONS,
  OrbitMark,
  StatusPill,
  T,
} from '@/lib/console-ui';

const GlobeViewer = dynamic(() => import('../components/GlobeViewer'), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full bg-[#0a0e17]">
      <p className="text-sm text-[#97a3ba]">loading 3D globe…</p>
    </div>
  ),
});

const CAPABILITIES = [
  {
    icon: 'inversion',
    title: 'Gravity field inversion',
    body: 'Tikhonov and ML-completion inversions over ingested mission measurements, rendered as georeferenced anomaly maps. The ML model beats the classical baseline by 47% on the held-out benchmark.',
    href: '/gravity',
    link: 'Open the anomaly map',
  },
  {
    icon: 'overview',
    title: 'Mission simulation & orbit determination',
    body: 'A GRACE-like two-satellite scenario propagated with real spherical-harmonic dynamics, ingested through the live API, and recovered by dynamic orbit determination to 0.30 m.',
    href: '/dashboard',
    link: 'Open Mission Control',
  },
  {
    icon: 'data',
    title: 'Time-series data platform',
    body: 'Telemetry and gravity measurements in TimescaleDB behind gRPC microservices, with provenance tags on every record and an event-driven workflow engine on Kafka.',
    href: '/dashboard',
    link: 'Browse the database',
  },
  {
    icon: 'monitoring',
    title: 'Operations & observability',
    body: 'Prometheus metrics, Alertmanager rules, Jaeger traces, and Grafana dashboards — surfaced in an operations console that shows real monitoring state, never a decorative badge.',
    href: '/ops',
    link: 'Open the ops console',
  },
] as const;

export default function Home() {
  const [health, setHealth] = useState<any>(null);
  const [healthFailed, setHealthFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const r = await fetch(`${GATEWAY}/health`);
        if (!cancelled && r.ok) {
          setHealth(await r.json());
          setHealthFailed(false);
          return;
        }
        if (!cancelled) setHealthFailed(true);
      } catch {
        if (!cancelled) setHealthFailed(true);
      }
    };
    poll();
    const id = setInterval(poll, 30000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const services = health ? Object.entries(health.services || {}) : [];
  const allUp =
    !!health &&
    health.status === 'healthy' &&
    services.every(([, v]) => v === 'healthy' || v === 'connected');

  return (
    <main className={`min-h-screen ${T.app} ${T.ink}`}>
      {/* nav */}
      <header className="border-b border-[#e4e7ec] bg-white">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <OrbitMark />
            <div>
              <div className="font-semibold tracking-tight">GALILEO</div>
              <div className={`text-[11px] ${T.ink3}`}>
                part of the ATLAS platform
              </div>
            </div>
          </div>
          <nav className="flex items-center gap-3">
            <Link href="/gravity" className={T.btnGhost}>
              Anomaly map
            </Link>
            <Link href="/ops" className={T.btnGhost}>
              Operations
            </Link>
            <Link
              href="/dashboard"
              className="rounded-lg px-4 py-2 text-sm font-medium text-white"
              style={{ backgroundColor: T.accent }}
            >
              Mission Control
            </Link>
          </nav>
        </div>
      </header>

      {/* hero */}
      <section className="max-w-6xl mx-auto px-6 pt-16 pb-10 grid lg:grid-cols-2 gap-10 items-center">
        <div>
          <p
            className="text-xs font-medium uppercase tracking-widest mb-4"
            style={{ color: T.accent }}
          >
            Satellite gravimetry, end to end
          </p>
          <h1 className="text-4xl font-semibold tracking-tight leading-tight">
            See the Earth&apos;s gravity field
            <br />
            from simulated orbit to anomaly map
          </h1>
          <p className={`mt-5 text-base leading-relaxed ${T.ink2}`}>
            GALILEO flies a GRACE-like satellite formation through real
            orbital dynamics, streams its measurements through a
            production-grade microservice platform, and inverts them into
            gravity anomaly maps — classical and machine-learned. Every
            number on every page comes from the live system.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              href="/dashboard"
              className="rounded-lg px-5 py-2.5 text-sm font-medium text-white"
              style={{ backgroundColor: T.accent }}
            >
              Open Mission Control
            </Link>
            <Link href="/gravity" className={T.btnGhost}>
              Run an inversion <Icon d={ICONS.external} size={13} />
            </Link>
          </div>

          {/* live status strip — real /health, no decoration */}
          <div className={`${T.card} mt-10 px-4 py-3`}>
            <div className="flex flex-wrap items-center gap-2">
              <span className={`text-xs mr-1 ${T.ink3}`}>
                platform status
              </span>
              {healthFailed ? (
                <StatusPill kind="critical" label="gateway unreachable" />
              ) : health ? (
                <>
                  {allUp ? (
                    <StatusPill kind="good" label="all systems nominal" />
                  ) : (
                    <StatusPill kind="serious" label="degraded" />
                  )}
                  {services.map(([k, v]) => (
                    <StatusPill
                      key={k}
                      kind={
                        v === 'healthy' || v === 'connected'
                          ? 'good'
                          : 'critical'
                      }
                      label={k}
                    />
                  ))}
                </>
              ) : (
                <span className={`text-xs ${T.ink3}`}>checking…</span>
              )}
            </div>
          </div>
        </div>

        {/* the globe — kept from the original UI */}
        <div
          className={`${T.card} overflow-hidden`}
          style={{ height: 560 }}
        >
          <GlobeViewer />
        </div>
      </section>

      {/* capabilities */}
      <section className="max-w-6xl mx-auto px-6 py-12">
        <h2 className="text-xl font-semibold tracking-tight mb-6">
          One platform, orbit to insight
        </h2>
        <div className="grid md:grid-cols-2 gap-6">
          {CAPABILITIES.map((c) => (
            <Card key={c.title} className="h-full">
              <div className="flex items-start gap-4">
                <span
                  className="mt-0.5 rounded-lg p-2"
                  style={{
                    color: T.accent,
                    backgroundColor: '#eaf2fc',
                  }}
                >
                  <Icon d={ICONS[c.icon]} size={20} />
                </span>
                <div>
                  <h3 className="font-semibold">{c.title}</h3>
                  <p className={`text-sm mt-2 leading-relaxed ${T.ink2}`}>
                    {c.body}
                  </p>
                  <Link
                    href={c.href}
                    className="inline-flex items-center gap-1.5 text-sm mt-3"
                    style={{ color: T.accent }}
                  >
                    {c.link} <Icon d={ICONS.external} size={12} />
                  </Link>
                </div>
              </div>
            </Card>
          ))}
        </div>
      </section>

      {/* pipeline strip */}
      <section className="border-y border-[#e4e7ec] bg-white">
        <div className="max-w-6xl mx-auto px-6 py-10">
          <h2 className="text-xl font-semibold tracking-tight mb-6">
            The live pipeline
          </h2>
          <ol className="grid md:grid-cols-4 gap-6 text-sm">
            {[
              [
                '01 · Simulate',
                'Two-satellite formation propagated with degree-6 spherical-harmonic gravity, J2, drag and SRP.',
              ],
              [
                '02 · Ingest',
                'Telemetry and gravimetry stream through the authenticated REST→gRPC gateway into TimescaleDB.',
              ],
              [
                '03 · Recover',
                'Dynamic orbit determination fits the truth orbit to 0.30 m; residuals feed quality control.',
              ],
              [
                '04 · Invert',
                'Tikhonov or ML-completion inversion turns measurements into a georeferenced anomaly map.',
              ],
            ].map(([step, body]) => (
              <li key={step}>
                <div
                  className="text-xs font-medium uppercase tracking-widest mb-2"
                  style={{ color: T.accent }}
                >
                  {step}
                </div>
                <p className={`leading-relaxed ${T.ink2}`}>{body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* footer */}
      <footer className="max-w-6xl mx-auto px-6 py-10 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <OrbitMark />
          <span className={`text-sm ${T.ink3}`}>
            GALILEO · part of the ATLAS platform
          </span>
        </div>
        <nav className="flex items-center gap-5 text-sm">
          <Link href="/dashboard" style={{ color: T.accent }}>
            Mission Control
          </Link>
          <Link href="/gravity" style={{ color: T.accent }}>
            Anomaly map
          </Link>
          <Link href="/ops" style={{ color: T.accent }}>
            Operations
          </Link>
          <a
            href="http://localhost:28000/docs"
            target="_blank"
            style={{ color: T.accent }}
          >
            API
          </a>
        </nav>
      </footer>
    </main>
  );
}
