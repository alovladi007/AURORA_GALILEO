'use client';

/**
 * GALILEO console design system — shared by every page.
 *
 * ATLAS corporate palette (GALILEO is an ATLAS simulation platform;
 * values extracted from the published ATLAS site):
 *   surfaces  #faf9f7 paper · #ffffff cards · #f3f1ed alt band
 *   ink       #14171a primary · #3d4248 secondary · #93979d muted
 *   accent    #c2410c burnt orange · #9a3412 hover · #fdf1ea tint
 *   borders   #ddd9d3
 *   status    good/warning/serious/critical — always rendered as a
 *             pill with a text label, never color alone.
 */

import { useCallback, useState } from 'react';

export const GATEWAY =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:28000';

export const T = {
  app: 'bg-[#faf9f7]',
  alt: 'bg-[#f3f1ed]',
  card: 'bg-white border border-[#ddd9d3] rounded-lg',
  rail: 'bg-white border-r border-[#ddd9d3]',
  ink: 'text-[#14171a]',
  ink2: 'text-[#3d4248]',
  ink3: 'text-[#93979d]',
  accent: '#c2410c',
  accentHover: '#9a3412',
  accentTint: '#fdf1ea',
  divider: 'border-[#e7e3dc]',
  input:
    'rounded-md bg-white border border-[#ddd9d3] px-3 py-2 text-sm text-[#14171a] focus:outline-none focus:border-[#c2410c]',
  btnGhost:
    'inline-flex items-center gap-2 rounded-md border border-[#ddd9d3] bg-white px-3.5 py-2 text-sm hover:bg-[#f3f1ed] text-[#3d4248]',
};

/** Reserved status roles — dark readable text over a soft tint. */
export const STATUS_STYLE = {
  good: { text: '#027a48', bg: '#ecfdf3', border: '#a6f4c5' },
  warning: { text: '#b54708', bg: '#fffaeb', border: '#fedf89' },
  serious: { text: '#c4320a', bg: '#fff6ed', border: '#f9dbaf' },
  critical: { text: '#b42318', bg: '#fef3f2', border: '#fecdca' },
} as const;

export const STATUS = {
  good: '#027a48',
  warning: '#b54708',
  serious: '#c4320a',
  critical: '#b42318',
} as const;

export const Icon = ({ d, size = 16 }: { d: string; size?: number }) => (
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

export const ICONS: Record<string, string> = {
  overview: 'M3 12h4l3-8 4 16 3-8h4',
  jobs: 'M4 17l6-6-6-6M12 19h8',
  inversion: 'M12 3a9 9 0 1 0 9 9M12 3v9h9M12 3a9 9 0 0 1 9 9',
  data: 'M12 3c-4.4 0-8 1.3-8 3v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6c0-1.7-3.6-3-8-3ZM4 6c0 1.7 3.6 3 8 3s8-1.3 8-3M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3',
  ml: 'M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3M7 7h10v10H7zM10 10h4v4h-4z',
  workflows: 'M5 5h5v5H5zM14 14h5v5h-5zM10 7.5h7v9',
  monitoring: 'M22 12h-4l-3 9L9 3l-3 9H2',
  refresh: 'M21 12a9 9 0 1 1-2.6-6.3M21 3v6h-6',
  external:
    'M14 5h5v5M19 5l-8 8M12 5H6a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-6',
  back: 'M19 12H5M12 19l-7-7 7-7',
};

export function StatusPill({
  kind,
  label,
}: {
  kind: keyof typeof STATUS;
  label: string;
}) {
  const st = STATUS_STYLE[kind];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium"
      style={{
        color: st.text,
        backgroundColor: st.bg,
        border: `1px solid ${st.border}`,
      }}
    >
      <span
        className="inline-block w-1.5 h-1.5 rounded-full"
        style={{ backgroundColor: st.text }}
      />
      {label}
    </span>
  );
}

export const okPill = (
  ok: boolean,
  okLabel = 'healthy',
  badLabel = 'down'
) =>
  ok ? (
    <StatusPill kind="good" label={okLabel} />
  ) : (
    <StatusPill kind="critical" label={badLabel} />
  );

export const jobStatusPill = (status: string) =>
  status === 'completed' ? (
    <StatusPill kind="good" label="completed" />
  ) : status === 'failed' ? (
    <StatusPill kind="critical" label="failed" />
  ) : (
    <StatusPill kind="warning" label={status || 'pending'} />
  );

export function Card({
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
        <div className="flex items-start justify-between px-5 pt-4 pb-3 border-b border-[#e7e3dc]">
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
        {error ? <ErrorNote text={error} /> : children}
      </div>
    </div>
  );
}

export function ErrorNote({ text }: { text: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{
        color: STATUS_STYLE.critical.text,
        backgroundColor: STATUS_STYLE.critical.bg,
        border: `1px solid ${STATUS_STYLE.critical.border}`,
      }}
    >
      {text}
    </div>
  );
}

export function StatTile({
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

export const Th = ({ children }: { children: React.ReactNode }) => (
  <th className="pb-2.5 pr-4 text-left text-[11px] font-medium uppercase tracking-wider text-[#93979d]">
    {children}
  </th>
);

export const pct = (p: any) =>
  p == null ? '—' : `${Math.round(p <= 1 ? p * 100 : p)}%`;

export function OrbitMark() {
  return (
    <svg width="34" height="34" viewBox="0 0 34 34" fill="none">
      <circle cx="17" cy="17" r="7" stroke="#c2410c" strokeWidth="1.8" />
      <ellipse
        cx="17"
        cy="17"
        rx="15"
        ry="6"
        stroke="#93979d"
        strokeWidth="1.2"
        transform="rotate(-22 17 17)"
      />
      <circle cx="29.5" cy="11.5" r="2.2" fill="#c2410c" />
    </svg>
  );
}

export function useAuthToken() {
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

/** Full-screen sign-in card with the dev account prefilled in dev. */
export function SignIn({
  subtitle,
  onLogin,
  error,
}: {
  subtitle: string;
  onLogin: (email: string, password: string) => void;
  error: string | null;
}) {
  const isDev = process.env.NODE_ENV === 'development';
  const [email, setEmail] = useState(
    isDev ? 'mission-sim@galileo.dev' : ''
  );
  const [password, setPassword] = useState(
    isDev ? 'mission-scenario-2026' : ''
  );
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
            <div className={`text-xs ${T.ink3}`}>{subtitle}</div>
          </div>
        </div>
        <form
          className={`${T.card} p-6 space-y-4`}
          onSubmit={(e) => {
            e.preventDefault();
            onLogin(email.trim(), password);
          }}
        >
          <div>
            <label className={`block text-xs mb-1.5 ${T.ink2}`}>Email</label>
            <input
              className={`w-full ${T.input}`}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div>
            <label className={`block text-xs mb-1.5 ${T.ink2}`}>
              Password
            </label>
            <input
              className={`w-full ${T.input}`}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <button
            className="w-full rounded-lg py-2 text-sm font-medium text-white"
            style={{ backgroundColor: T.accent }}
          >
            Sign in
          </button>
          {error && (
            <p className="text-xs" style={{ color: STATUS.critical }}>
              {error}
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

/** Slim top bar for the product pages (gravity, ops). */
export function PageHeader({
  title,
  badge,
  actions,
}: {
  title: string;
  badge?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <header className="flex items-center justify-between px-8 py-4 border-b border-[#e7e3dc]">
      <div className="flex items-center gap-4">
        <a href="/dashboard" className="flex items-center gap-3">
          <OrbitMark />
        </a>
        <div>
          <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
        </div>
        {badge}
      </div>
      <div className="flex items-center gap-3">{actions}</div>
    </header>
  );
}
