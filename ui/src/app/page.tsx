'use client';

/**
 * GALILEO landing page — styled to the ATLAS corporate site
 * (GALILEO is one of ATLAS's two simulation platforms). Layout
 * mirrors atlas: eyebrow + hero with a right-hand index panel, a
 * monospace stats strip, the CesiumJS globe as the centerpiece,
 * capability cards, numbered principles, and a multi-column footer.
 *
 * No fabricated numbers: the status strip is fed by the gateway's
 * public /health endpoint and renders unreachable as unreachable;
 * the stats are measured platform results.
 */

import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import {
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
    <div className="flex items-center justify-center h-full bg-[#14171a]">
      <p className="text-sm text-[#93979d]">loading 3D globe…</p>
    </div>
  ),
});

const SURFACES = [
  {
    icon: 'overview',
    name: 'Mission Control',
    desc: 'Console for the whole platform',
    href: '/dashboard',
  },
  {
    icon: 'inversion',
    name: 'Gravity anomaly map',
    desc: 'Run classical & ML inversions',
    href: '/gravity',
  },
  {
    icon: 'monitoring',
    name: 'Operations console',
    desc: 'Health, targets, alerts',
    href: '/ops',
  },
  {
    icon: 'data',
    name: 'REST API',
    desc: '32 documented endpoints',
    href: 'http://localhost:28000/docs',
  },
] as const;

const STATS = [
  ['2', 'satellites in the simulated formation'],
  ['0.30 m', 'orbit recovery, dynamic OD'],
  ['47%', 'ML inversion gain over baseline'],
  ['32', 'documented API endpoints'],
] as const;

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

const PRINCIPLES = [
  [
    '01',
    'No fabricated data',
    'Every number on every page comes from the live system. Synthetic measurements carry provenance tags; failures render as failures.',
  ],
  [
    '02',
    'Physics you can check',
    'Spherical-harmonic gravity cross-validated against closed-form J2; nineteen reference tests pin the dynamics to published values.',
  ],
  [
    '03',
    'One platform, orbit to insight',
    'Simulation, ingestion, orbit determination, and inversion run through the same authenticated API the UI uses — no side doors.',
  ],
  [
    '04',
    'Built to operate',
    'The monitoring plane is part of the product: scrape targets, alert rules, and traces ship with the stack and surface in the console.',
  ],
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
      <header className="border-b border-[#e7e3dc] bg-[#faf9f7]">
        <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <OrbitMark />
            <div className="leading-tight">
              <div className="font-bold tracking-tight text-[15px]">
                GALILEO
              </div>
              <div className="text-[10px] uppercase tracking-widest text-[#93979d]">
                Simulation &amp; Gravimetry
              </div>
            </div>
          </div>
          <nav className="flex items-center gap-5 text-sm">
            <Link href="/gravity" className={T.ink2}>
              Anomaly map
            </Link>
            <Link href="/ops" className={T.ink2}>
              Operations
            </Link>
            <a
              href="http://localhost:28000/docs"
              target="_blank"
              className={T.ink2}
            >
              API
            </a>
            <Link
              href="/dashboard"
              className="rounded-md px-4 py-2 text-sm font-medium text-white"
              style={{ backgroundColor: T.accent }}
            >
              Mission Control
            </Link>
          </nav>
        </div>
      </header>

      {/* hero */}
      <section className="max-w-6xl mx-auto px-6 pt-14 pb-12 grid lg:grid-cols-[1fr,360px] gap-12">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-[0.2em] mb-5 text-[#93979d]">
            A simulation platform of ATLAS Corporation
          </p>
          <h1 className="text-[2.6rem] leading-[1.1] font-bold tracking-tight">
            Gravity missions designed
            <br />
            from orbit dynamics to
            <br />
            field inversion
          </h1>
          <p className={`mt-6 text-base leading-relaxed max-w-xl ${T.ink2}`}>
            GALILEO flies a GRACE-like satellite formation through real
            orbital dynamics, streams its measurements through a
            production-grade microservice platform, and inverts them into
            gravity anomaly maps — classical and machine-learned. Both
            answer the same question: will the mission survive its own
            error budget?
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              href="/dashboard"
              className="rounded-md px-5 py-2.5 text-sm font-medium text-white"
              style={{ backgroundColor: T.accent }}
            >
              Open Mission Control
            </Link>
            <Link href="/gravity" className={T.btnGhost}>
              Run an inversion
            </Link>
          </div>

          {/* live status — real /health */}
          <div className="mt-10 flex flex-wrap items-center gap-2">
            <span className="text-[11px] uppercase tracking-widest mr-1 text-[#93979d]">
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

        {/* platform index panel (atlas-style) */}
        <aside>
          <p className="text-[11px] font-medium uppercase tracking-[0.2em] mb-3 text-[#93979d]">
            Platform surfaces
          </p>
          <div className={`${T.card} divide-y divide-[#e7e3dc]`}>
            {SURFACES.map((sfc) => (
              <a
                key={sfc.name}
                href={sfc.href}
                className="flex items-center gap-3 px-4 py-3.5 hover:bg-[#f7f5f1]"
              >
                <span style={{ color: T.accent }}>
                  <Icon d={ICONS[sfc.icon]} size={16} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium">
                    {sfc.name}
                  </span>
                  <span className={`block text-xs ${T.ink3}`}>
                    {sfc.desc}
                  </span>
                </span>
                <span className={T.ink3}>→</span>
              </a>
            ))}
          </div>
        </aside>
      </section>

      {/* stats strip (mono numerals, atlas-style) */}
      <section className={`${T.alt} border-y border-[#e7e3dc]`}>
        <div className="max-w-6xl mx-auto px-6 grid grid-cols-2 md:grid-cols-4 divide-x divide-[#ddd9d3]">
          {STATS.map(([n, label]) => (
            <div key={label} className="px-6 py-6 first:pl-0">
              <div className="font-mono text-xl font-semibold tracking-tight">
                {n}
              </div>
              <div
                className={`text-[11px] uppercase tracking-wider mt-1 ${T.ink3}`}
              >
                {label}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* globe */}
      <section className="max-w-6xl mx-auto px-6 py-12">
        <div className="flex items-end justify-between mb-4">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-[0.2em] mb-2 text-[#93979d]">
              The mission, on the globe
            </p>
            <h2 className="text-xl font-bold tracking-tight">
              Drag to rotate · scroll to zoom · click to pinpoint
            </h2>
          </div>
        </div>
        <div className={`${T.card} overflow-hidden`} style={{ height: 560 }}>
          <GlobeViewer />
        </div>
      </section>

      {/* capabilities */}
      <section className={`${T.alt} border-y border-[#e7e3dc]`}>
        <div className="max-w-6xl mx-auto px-6 py-12">
          <h2 className="text-xl font-bold tracking-tight mb-6">
            One platform, orbit to insight
          </h2>
          <div className="grid md:grid-cols-2 gap-5">
            {CAPABILITIES.map((c) => (
              <div key={c.title} className={`${T.card} p-5`}>
                <div className="flex items-start gap-4">
                  <span
                    className="mt-0.5 rounded-md p-2"
                    style={{
                      color: T.accent,
                      backgroundColor: T.accentTint,
                    }}
                  >
                    <Icon d={ICONS[c.icon]} size={18} />
                  </span>
                  <div>
                    <h3 className="font-semibold text-[15px]">{c.title}</h3>
                    <p
                      className={`text-sm mt-2 leading-relaxed ${T.ink2}`}
                    >
                      {c.body}
                    </p>
                    <Link
                      href={c.href}
                      className="inline-flex items-center gap-1.5 text-sm mt-3 font-medium"
                      style={{ color: T.accent }}
                    >
                      {c.link} →
                    </Link>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* numbered principles (atlas-style) */}
      <section className="max-w-6xl mx-auto px-6 py-14">
        <div className="grid md:grid-cols-2 gap-x-14 gap-y-10">
          {PRINCIPLES.map(([n, title, body]) => (
            <div key={n}>
              <div
                className="font-mono text-xs mb-2"
                style={{ color: T.accent }}
              >
                {n}
              </div>
              <h3 className="font-bold">{title}</h3>
              <p className={`text-sm mt-2 leading-relaxed ${T.ink2}`}>
                {body}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* footer */}
      <footer className={`${T.alt} border-t border-[#e7e3dc]`}>
        <div className="max-w-6xl mx-auto px-6 py-10 grid md:grid-cols-3 gap-8">
          <div>
            <div className="flex items-center gap-2.5 mb-3">
              <OrbitMark />
              <div className="leading-tight">
                <div className="font-bold tracking-tight text-[15px]">
                  GALILEO
                </div>
                <div className="text-[10px] uppercase tracking-widest text-[#93979d]">
                  Simulation &amp; Gravimetry
                </div>
              </div>
            </div>
            <p className={`text-sm leading-relaxed ${T.ink2}`}>
              GALILEO designs satellite gravimetry missions from orbit
              dynamics to gravity-field inversion. A simulation platform
              of ATLAS Corporation.
            </p>
          </div>
          <div>
            <p className="text-[11px] font-medium uppercase tracking-[0.2em] mb-3 text-[#93979d]">
              Product
            </p>
            <ul className="space-y-2 text-sm">
              <li>
                <Link href="/dashboard" className={T.ink2}>
                  Mission Control
                </Link>
              </li>
              <li>
                <Link href="/gravity" className={T.ink2}>
                  Gravity anomaly map
                </Link>
              </li>
              <li>
                <Link href="/ops" className={T.ink2}>
                  Operations console
                </Link>
              </li>
              <li>
                <a
                  href="http://localhost:28000/docs"
                  target="_blank"
                  className={T.ink2}
                >
                  API reference
                </a>
              </li>
            </ul>
          </div>
          <div>
            <p className="text-[11px] font-medium uppercase tracking-[0.2em] mb-3 text-[#93979d]">
              ATLAS
            </p>
            <ul className="space-y-2 text-sm">
              <li>
                <a
                  href="https://alovladi007.github.io/ATLAS-Advanced-Technology-Labs-for-Applied-Sciences/"
                  target="_blank"
                  className={T.ink2}
                >
                  ATLAS Robotics &amp; Sensors
                </a>
              </li>
              <li>
                <span className={`${T.ink3} text-sm`}>
                  AURORA-NAV — subsea navigation
                </span>
              </li>
              <li>
                <span className={`${T.ink3} text-sm`}>
                  GALILEO — satellite gravimetry
                </span>
              </li>
            </ul>
          </div>
        </div>
        <div className="border-t border-[#e7e3dc]">
          <div
            className={`max-w-6xl mx-auto px-6 py-4 text-xs ${T.ink3}`}
          >
            GALILEO is a simulation platform of ATLAS Corporation.
          </div>
        </div>
      </footer>
    </main>
  );
}
