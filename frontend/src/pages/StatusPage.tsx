import { useQuery } from '@tanstack/react-query';
import { Shield, CheckCircle, XCircle, Clock, Cpu, Database } from 'lucide-react';
import axios from 'axios';

// ─── Types ───────────────────────────────────────────────────
interface HealthResponse {
  status: string;
  service: string;
  version: string;
  environment: string;
  uptime_seconds: number;
}

interface ReadinessResponse {
  status: string;
  service: string;
  version: string;
  checks: Record<string, { status: string; note?: string }>;
}

interface InfoResponse {
  service: string;
  version: string;
  environment: string;
  description: string;
  api_version: string;
  modules: string[];
}

// ─── API Functions ───────────────────────────────────────────
const fetchHealth = () =>
  axios.get<HealthResponse>('/api/v1/health').then((r) => r.data);

const fetchReadiness = () =>
  axios.get<ReadinessResponse>('/api/v1/health/ready').then((r) => r.data);

const fetchInfo = () =>
  axios.get<InfoResponse>('/api/v1/health/info').then((r) => r.data);

// ─── Status Badge ─────────────────────────────────────────────
function StatusBadge({ status }: { status: string }) {
  const isOk = status === 'ok';
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${
        isOk
          ? 'bg-success-500/10 text-success-400 border-success-500/30'
          : 'bg-danger-500/10 text-danger-400 border-danger-500/30'
      }`}
    >
      {isOk ? <CheckCircle size={12} /> : <XCircle size={12} />}
      {status.toUpperCase()}
    </span>
  );
}

// ─── Service Check Row ────────────────────────────────────────
function CheckRow({ name, check }: { name: string; check: { status: string; note?: string } }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-surface-700/50 last:border-0">
      <div className="flex items-center gap-3">
        <Database size={14} className="text-surface-400" />
        <span className="text-sm font-medium text-surface-200 capitalize">{name}</span>
        {check.note && (
          <span className="text-xs text-surface-500 italic">{check.note}</span>
        )}
      </div>
      <StatusBadge status={check.status} />
    </div>
  );
}

// ─── Status Page ─────────────────────────────────────────────
export function StatusPage() {
  const { data: health, isLoading: healthLoading, isError: healthError } = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: 10000,
  });

  const { data: readiness, isLoading: readyLoading } = useQuery({
    queryKey: ['readiness'],
    queryFn: fetchReadiness,
    refetchInterval: 15000,
  });

  const { data: info, isLoading: infoLoading } = useQuery({
    queryKey: ['info'],
    queryFn: fetchInfo,
  });

  return (
    <div className="min-h-screen flex flex-col items-center justify-start py-16 px-4">
      {/* ─── Header ─── */}
      <div className="flex flex-col items-center gap-4 mb-12 animate-fade-in">
        <div className="w-20 h-20 rounded-2xl bg-primary-600/20 border border-primary-500/30 flex items-center justify-center shadow-cyber">
          <Shield size={40} className="text-primary-400" />
        </div>
        <div className="text-center">
          <h1 className="text-3xl font-bold text-surface-100 tracking-tight">
            ITBIS
          </h1>
          <p className="text-surface-400 text-sm mt-1">
            Insider Threat Behavioral Intelligence System
          </p>
        </div>

        {healthLoading ? (
          <div className="animate-pulse w-24 h-7 bg-surface-700 rounded-full" />
        ) : healthError ? (
          <StatusBadge status="error" />
        ) : health ? (
          <StatusBadge status={health.status} />
        ) : null}
      </div>

      {/* ─── Grid ─── */}
      <div className="w-full max-w-4xl grid grid-cols-1 md:grid-cols-2 gap-6 animate-slide-up">

        {/* Liveness Card */}
        <div className="card-glass p-6">
          <div className="flex items-center gap-2 mb-4">
            <Cpu size={16} className="text-primary-400" />
            <h2 className="text-sm font-semibold text-surface-200 uppercase tracking-wider">
              System
            </h2>
          </div>
          {healthLoading ? (
            <div className="space-y-3">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="h-5 bg-surface-700 rounded animate-pulse" />
              ))}
            </div>
          ) : health ? (
            <dl className="space-y-3">
              {[
                ['Service',     health.service],
                ['Version',     health.version],
                ['Environment', health.environment],
                ['Uptime',      `${health.uptime_seconds}s`],
              ].map(([label, value]) => (
                <div key={label} className="flex justify-between text-sm">
                  <dt className="text-surface-400">{label}</dt>
                  <dd className="text-surface-100 font-mono">{value}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </div>

        {/* Readiness Card */}
        <div className="card-glass p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Database size={16} className="text-primary-400" />
              <h2 className="text-sm font-semibold text-surface-200 uppercase tracking-wider">
                Infrastructure
              </h2>
            </div>
            {readiness && <StatusBadge status={readiness.status} />}
          </div>
          {readyLoading ? (
            <div className="space-y-3">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-10 bg-surface-700 rounded animate-pulse" />
              ))}
            </div>
          ) : readiness ? (
            <div>
              {Object.entries(readiness.checks).map(([name, check]) => (
                <CheckRow key={name} name={name} check={check} />
              ))}
            </div>
          ) : null}
        </div>

        {/* API Info Card */}
        <div className="card-glass p-6">
          <div className="flex items-center gap-2 mb-4">
            <Clock size={16} className="text-primary-400" />
            <h2 className="text-sm font-semibold text-surface-200 uppercase tracking-wider">
              API Info
            </h2>
          </div>
          {infoLoading ? (
            <div className="h-5 bg-surface-700 rounded animate-pulse" />
          ) : info ? (
            <dl className="space-y-3 text-sm">
              <div className="flex justify-between">
                <dt className="text-surface-400">API Version</dt>
                <dd className="font-mono text-primary-400">v{info.api_version}</dd>
              </div>
              <div>
                <dt className="text-surface-400 mb-2">Description</dt>
                <dd className="text-surface-300 text-xs leading-relaxed">{info.description}</dd>
              </div>
            </dl>
          ) : null}
        </div>

        {/* Modules Card */}
        <div className="card-glass p-6">
          <div className="flex items-center gap-2 mb-4">
            <Shield size={16} className="text-primary-400" />
            <h2 className="text-sm font-semibold text-surface-200 uppercase tracking-wider">
              Modules ({info?.modules?.length ?? 0})
            </h2>
          </div>
          {infoLoading ? (
            <div className="grid grid-cols-2 gap-2">
              {[...Array(8)].map((_, i) => (
                <div key={i} className="h-6 bg-surface-700 rounded animate-pulse" />
              ))}
            </div>
          ) : info ? (
            <div className="flex flex-wrap gap-2">
              {info.modules.map((mod) => (
                <span
                  key={mod}
                  className="px-2.5 py-1 rounded-lg bg-surface-700/60 text-surface-300 text-xs font-mono border border-surface-600/50"
                >
                  {mod}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      {/* ─── Phase Banner ─── */}
      <div className="mt-10 w-full max-w-4xl">
        <div className="card-glass px-6 py-4 border-l-4 border-primary-500">
          <p className="text-sm text-surface-300">
            <span className="text-primary-400 font-semibold">Phase 0 — Foundation Complete.</span>
            {' '}Backend, infrastructure, and frontend scaffolding are in place.
            Authentication, ML pipeline, and SOC dashboard will be implemented in subsequent phases.
          </p>
        </div>
      </div>

      {/* ─── Footer ─── */}
      <footer className="mt-16 text-surface-600 text-xs text-center">
        ITBIS v{health?.version ?? '0.1.0'} · Enterprise UEBA Platform · Internal Use Only
      </footer>
    </div>
  );
}
