/**
 * Service Health — patrol findings, loader status, data freshness, schedules.
 * Pure JSX + theme.css classes.
 */

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  RefreshCw, Inbox, CheckCircle, AlertTriangle, AlertCircle,
  Database, Clock, Activity, Server,
} from 'lucide-react';
import { api } from '../services/api';

const fmtAgo = (ts) => {
  if (!ts) return '—';
  const s = (Date.now() - new Date(ts).getTime()) / 1000;
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};

const STATUS_VARIANT = {
  ok: 'badge-success',
  stale: 'badge-amber',
  error: 'badge-danger',
  empty: 'badge',
};

export default function ServiceHealth() {
  const { data: dataStatus, isLoading, refetch } = useQuery({
    queryKey: ['algo-data-status'],
    queryFn: () => api.get('/api/algo/data-status').then(r => r.data?.data),
    refetchInterval: 30000,
  });
  const { data: patrolLog } = useQuery({
    queryKey: ['algo-patrol-log'],
    queryFn: () => api.get('/api/algo/patrol-log?limit=50').then(r => r.data),
    refetchInterval: 60000,
  });
  const { data: status } = useQuery({
    queryKey: ['algo-status'],
    queryFn: () => api.get('/api/algo/status').then(r => r.data?.data),
    refetchInterval: 30000,
  });

  const summary = dataStatus?.summary || { ok: 0, stale: 0, empty: 0, error: 0 };
  const sources = dataStatus?.sources || [];
  const ready = dataStatus?.ready_to_trade;
  const findings = patrolLog?.items || [];

  return (
    <div className="main-content">
      <div className="page-head">
        <div>
          <div className="page-head-title">Service Health</div>
          <div className="page-head-sub">Data freshness · Patrol findings · Algo readiness</div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-outline btn-sm" onClick={() => refetch()}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {/* Top status banner */}
      <div className="card" style={{ borderLeft: `3px solid ${ready ? 'var(--success)' : 'var(--danger)'}`, padding: 'var(--space-5) var(--space-6)' }}>
        <div className="grid grid-4 items-center">
          <div className="flex items-center gap-3">
            <div style={{
              width: 48, height: 48, borderRadius: 'var(--r-md)',
              background: ready ? 'var(--success-soft)' : 'var(--danger-soft)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              border: `1px solid ${ready ? 'var(--success)' : 'var(--danger)'}50`,
            }}>
              {ready
                ? <CheckCircle size={24} color="var(--success)" />
                : <AlertCircle size={24} color="var(--danger)" />}
            </div>
            <div>
              <div className="eyebrow">Algo Status</div>
              <div className={`mono ${ready ? 'up' : 'down'}`}
                   style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)' }}>
                {ready ? 'READY TO TRADE' : 'NOT READY'}
              </div>
            </div>
          </div>
          <div className="stile">
            <div className="stile-label">Sources OK</div>
            <div className="stile-value up">{summary.ok}</div>
          </div>
          <div className="stile">
            <div className="stile-label">Stale</div>
            <div className={`stile-value ${summary.stale > 0 ? 'down' : ''}`}>{summary.stale || 0}</div>
          </div>
          <div className="stile">
            <div className="stile-label">Errors</div>
            <div className={`stile-value ${(summary.error || 0) + (summary.empty || 0) > 0 ? 'down' : ''}`}>
              {(summary.error || 0) + (summary.empty || 0)}
            </div>
          </div>
        </div>
        {dataStatus?.critical_stale?.length > 0 && (
          <div className="alert alert-danger" style={{ marginTop: 'var(--space-4)' }}>
            <AlertCircle size={16} />
            <div>
              <strong>Critical sources stale:</strong> {dataStatus.critical_stale.join(', ')}
            </div>
          </div>
        )}
      </div>

      {/* Two-column: data sources + recent patrol findings */}
      <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">Data Sources ({sources.length})</div>
              <div className="card-sub">Per-table freshness · loader role · age</div>
            </div>
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            {isLoading ? <Empty title="Loading…" /> : sources.length === 0 ? <Empty title="No data" /> : (
              <div style={{ maxHeight: '60vh', overflow: 'auto' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Table</th>
                      <th>Role</th>
                      <th>Freq</th>
                      <th className="num">Latest</th>
                      <th className="num">Age</th>
                      <th className="num">Rows</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sources.map((s, i) => (
                      <tr key={i}>
                        <td><span className="strong" style={{ fontWeight: 'var(--w-semibold)' }}>{s.table}</span></td>
                        <td className="muted t-xs">{(s.role || '').split(':')[0]}</td>
                        <td className="muted t-xs">{s.frequency}</td>
                        <td className="num mono t-xs">{s.latest ? String(s.latest).slice(0, 10) : '—'}</td>
                        <td className={`num mono ${s.age_days > 7 ? 'down' : ''}`}>{s.age_days != null ? `${s.age_days}d` : '—'}</td>
                        <td className="num mono t-xs muted">{s.rows ? Number(s.rows).toLocaleString('en-US') : '—'}</td>
                        <td>
                          <span className={`badge ${STATUS_VARIANT[s.status] || 'badge'}`}>{(s.status || '').toUpperCase()}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">Recent Patrol Findings</div>
              <div className="card-sub">Last 50 issues across critical/error/warn</div>
            </div>
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            {findings.length === 0 ? (
              <Empty title="All clear" desc="No recent patrol findings." icon={CheckCircle} />
            ) : (
              <div style={{ maxHeight: '60vh', overflow: 'auto' }}>
                {findings.map((f, i) => (
                  <FindingRow key={i} finding={f} />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Algo run status panel */}
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Last Orchestrator Run</div>
            <div className="card-sub">Phase results from the most recent algo workflow execution</div>
          </div>
        </div>
        <div className="card-body">
          {status ? (
            <div className="grid grid-4">
              <div className="stile">
                <div className="stile-label">Last Run</div>
                <div className="stile-value">{status.last_run_at ? fmtAgo(status.last_run_at) : '—'}</div>
                <div className="stile-sub">{status.last_run_id || '—'}</div>
              </div>
              <div className="stile">
                <div className="stile-label">Status</div>
                <div className={`stile-value ${status.last_run_status === 'success' ? 'up' : 'down'}`}>
                  {(status.last_run_status || 'UNKNOWN').toUpperCase()}
                </div>
              </div>
              <div className="stile">
                <div className="stile-label">Execution Mode</div>
                <div className="stile-value">{status.execution_mode || '—'}</div>
              </div>
              <div className="stile">
                <div className="stile-label">Open Positions</div>
                <div className="stile-value">{status.open_positions ?? '—'}</div>
              </div>
            </div>
          ) : <Empty title="No status yet" desc="Algo orchestrator hasn't reported a run." />}
        </div>
      </div>
    </div>
  );
}

function FindingRow({ finding }) {
  const sev = (finding.severity || '').toUpperCase();
  const variant = sev === 'CRITICAL' || sev === 'ERROR' ? 'badge-danger'
                : sev === 'WARN' ? 'badge-amber'
                : 'badge';
  const icon = sev === 'CRITICAL' || sev === 'ERROR' ? <AlertCircle size={14} color="var(--danger)" />
             : sev === 'WARN' ? <AlertTriangle size={14} color="var(--amber)" />
             : <Activity size={14} className="muted" />;
  return (
    <div style={{
      padding: 'var(--space-3) var(--space-4)',
      borderBottom: '1px solid var(--border-soft)',
    }}>
      <div className="flex items-center gap-3">
        {icon}
        <span className={`badge ${variant}`}>{sev}</span>
        <span className="strong t-sm" style={{ fontWeight: 'var(--w-semibold)' }}>{finding.check_type || finding.type}</span>
        {finding.target && <span className="muted t-xs">· {finding.target}</span>}
        <span className="t-xs faint mono" style={{ marginLeft: 'auto' }}>{fmtAgo(finding.created_at)}</span>
      </div>
      <div className="t-sm" style={{ marginTop: 4, color: 'var(--text-2)' }}>{finding.message}</div>
    </div>
  );
}

function Empty({ title, desc, icon: Icon = Inbox }) {
  return (
    <div className="empty">
      <Icon size={36} />
      <div className="empty-title">{title}</div>
      {desc && <div className="empty-desc">{desc}</div>}
    </div>
  );
}
