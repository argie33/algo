/**
 * Trade Tracker — every action the algo takes.
 *
 * Pure JSX + theme.css classes. Three tabs:
 *   1. Trades — open + closed positions w/ row expansion (full reasoning)
 *   2. Activity — algo audit log (entries, exits, stops, halts, skips)
 *   3. Notifications — circuit-breaker / sector-rotation / etc alerts
 */

import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  RefreshCw, Search, ChevronDown, ChevronUp, Inbox, AlertCircle,
  Bolt, Minus, TrendingUp, TrendingDown, Info, CheckCircle, AlertTriangle,
} from 'lucide-react';
import { api } from '../services/api';

// ─── helpers ───────────────────────────────────────────────────────────────
const num = (v, dp = 2) => v == null || isNaN(Number(v)) ? '—' : Number(v).toFixed(dp);
const fmtMoney = (v) => v == null ? '—' : `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmtAgo = (ts) => {
  if (!ts) return '—';
  const s = (Date.now() - new Date(ts).getTime()) / 1000;
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};
const Pnl = ({ value, suffix = '' }) => {
  if (value == null || isNaN(Number(value))) return <span className="muted">—</span>;
  const v = Number(value);
  const cls = v > 0 ? 'up' : v < 0 ? 'down' : 'flat';
  const sign = v > 0 ? '+' : '';
  return <span className={`mono tnum ${cls}`} style={{ fontWeight: 'var(--w-semibold)' }}>{sign}{v.toFixed(2)}{suffix}</span>;
};

// ─── main ──────────────────────────────────────────────────────────────────
export default function TradeTracker() {
  const [tab, setTab] = useState('trades');
  return (
    <div className="main-content">
      <div className="page-head">
        <div>
          <div className="page-head-title">Trade Tracker</div>
          <div className="page-head-sub">
            Every action the algo takes — entries, exits, stops, pyramids, halts, skipped signals
          </div>
        </div>
      </div>

      <Tabs
        tabs={[
          { value: 'trades', label: 'Trades' },
          { value: 'activity', label: 'Activity' },
          { value: 'notifications', label: 'Notifications' },
        ]}
        value={tab} onChange={setTab}
      />
      <div style={{ marginTop: 'var(--space-4)' }}>
        {tab === 'trades' && <TradesView />}
        {tab === 'activity' && <ActivityView />}
        {tab === 'notifications' && <NotificationsView />}
      </div>
    </div>
  );
}

// ─── TABS ──────────────────────────────────────────────────────────────────
function Tabs({ tabs, value, onChange }) {
  return (
    <div style={{ display: 'flex', borderBottom: '1px solid var(--border)' }}>
      {tabs.map(t => (
        <button
          key={t.value}
          type="button"
          onClick={() => onChange(t.value)}
          style={{
            background: 'transparent',
            border: 'none',
            borderBottom: `2px solid ${value === t.value ? 'var(--brand)' : 'transparent'}`,
            color: value === t.value ? 'var(--brand-2)' : 'var(--text-muted)',
            fontWeight: value === t.value ? 'var(--w-semibold)' : 'var(--w-medium)',
            fontSize: 'var(--t-sm)',
            padding: '12px 16px',
            cursor: 'pointer',
            marginBottom: -1,
            transition: 'all var(--t-fast)',
          }}
          onMouseEnter={(e) => { if (value !== t.value) e.currentTarget.style.color = 'var(--text)'; }}
          onMouseLeave={(e) => { if (value !== t.value) e.currentTarget.style.color = 'var(--text-muted)'; }}
        >
          {t.label}
          {t.count != null && (
            <span className="badge mono tnum" style={{ marginLeft: 8 }}>{t.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

// ─── TRADES VIEW ───────────────────────────────────────────────────────────
function TradesView() {
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState('all');
  const [symbolFilter, setSymbolFilter] = useState('');
  const [expandedKey, setExpandedKey] = useState(null);

  const { data: positions, refetch: rp, isLoading: lp } = useQuery({
    queryKey: ['algo-positions'],
    queryFn: () => api.get('/api/algo/positions').then(r => r.data),
    refetchInterval: 30000,
  });
  const { data: trades, refetch: rt, isLoading: lt } = useQuery({
    queryKey: ['algo-trades'],
    queryFn: () => api.get('/api/algo/trades?limit=200').then(r => r.data),
    refetchInterval: 60000,
  });
  const refetch = () => { rp(); rt(); };

  const openPositions = positions?.items || positions?.data?.items || [];
  const closedTrades = (trades?.items || []).filter(t => t.status === 'closed');

  const rows = useMemo(() => {
    const sym = symbolFilter.trim().toUpperCase();
    let list;
    if (statusFilter === 'open') list = openPositions.map(p => ({ ...p, _kind: 'open' }));
    else if (statusFilter === 'closed') list = closedTrades.map(t => ({ ...t, _kind: 'closed' }));
    else list = [...openPositions.map(p => ({ ...p, _kind: 'open' })), ...closedTrades.map(t => ({ ...t, _kind: 'closed' }))];
    if (sym) list = list.filter(r => r.symbol?.startsWith(sym));
    return list;
  }, [openPositions, closedTrades, statusFilter, symbolFilter]);

  const openPnL = openPositions.reduce((s, p) => s + Number(p.unrealized_pnl || 0), 0);
  const closedPnL = closedTrades.reduce((s, t) => s + Number(t.profit_loss_dollars || 0), 0);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Trades &amp; Positions</div>
          <div className="card-sub">algo_positions + algo_trades</div>
        </div>
        <div className="card-actions">
          <button className="btn btn-icon btn-ghost" onClick={refetch} aria-label="Refresh"><RefreshCw size={14} /></button>
        </div>
      </div>
      <div className="card-body">
        <div className="grid grid-4" style={{ marginBottom: 'var(--space-4)' }}>
          <div className="stile"><div className="stile-label">Open</div><div className="stile-value up">{openPositions.length}</div></div>
          <div className="stile"><div className="stile-label">Closed</div><div className="stile-value">{closedTrades.length}</div></div>
          <div className="stile"><div className="stile-label">Open P&L</div><div className={`stile-value ${openPnL >= 0 ? 'up' : 'down'}`}>{openPnL >= 0 ? '+' : ''}${num(openPnL, 0)}</div></div>
          <div className="stile"><div className="stile-label">Closed P&L</div><div className={`stile-value ${closedPnL >= 0 ? 'up' : 'down'}`}>{closedPnL >= 0 ? '+' : ''}${num(closedPnL, 0)}</div></div>
        </div>

        <div className="flex gap-3" style={{ marginBottom: 'var(--space-4)' }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-faint)' }} />
            <input className="input" placeholder="Symbol" value={symbolFilter}
              onChange={e => setSymbolFilter(e.target.value)} style={{ paddingLeft: 32 }} />
          </div>
          <select className="select" value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ width: 130 }}>
            <option value="all">All status</option>
            <option value="open">Open</option>
            <option value="closed">Closed</option>
          </select>
        </div>

        {(lp || lt) ? <Empty title="Loading…" /> : rows.length === 0 ? <Empty title="No trades" /> : (
          <div style={{ overflow: 'auto', maxHeight: '70vh', border: '1px solid var(--border)', borderRadius: 'var(--r-md)' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Status</th>
                  <th className="num">Entry</th>
                  <th className="num">Current/Exit</th>
                  <th className="num">Qty</th>
                  <th className="num">P&L $</th>
                  <th className="num">P&L %</th>
                  <th className="num">R</th>
                  <th className="num">Days</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => {
                  const isOpen = row._kind === 'open';
                  const k = row.position_id || row.trade_id || `${row.symbol}-${i}`;
                  const expanded = expandedKey === k;
                  const px = isOpen ? row.current_price : row.exit_price;
                  const pl = isOpen ? row.unrealized_pnl : row.profit_loss_dollars;
                  const plPct = isOpen ? row.unrealized_pnl_pct : row.profit_loss_pct;
                  const days = isOpen ? row.days_since_entry : row.trade_duration_days;
                  const reason = row.exit_reason || row.entry_reason || '';
                  const rMult = row.exit_r_multiple ?? row.r_multiple;
                  return (
                    <React.Fragment key={k}>
                      <tr onClick={() => setExpandedKey(expanded ? null : k)}>
                        <td>
                          <span
                            className="strong"
                            style={{ fontWeight: 'var(--w-bold)', cursor: 'pointer' }}
                            onClick={(e) => { e.stopPropagation(); navigate(`/app/stock/${row.symbol}`); }}
                          >
                            {row.symbol}
                          </span>
                        </td>
                        <td>
                          <span className={`badge ${isOpen ? 'badge-success' : ''}`}>{isOpen ? 'OPEN' : 'CLOSED'}</span>
                        </td>
                        <td className="num">{fmtMoney(row.entry_price || row.avg_entry_price)}</td>
                        <td className="num">{fmtMoney(px)}</td>
                        <td className="num">{row.quantity || row.entry_quantity || '—'}</td>
                        <td className="num"><Pnl value={pl} /></td>
                        <td className="num"><Pnl value={plPct} suffix="%" /></td>
                        <td className="num">{rMult != null ? <Pnl value={rMult} suffix="R" /> : '—'}</td>
                        <td className="num muted">{days || '—'}</td>
                        <td className="muted t-xs">{reason || '—'}</td>
                      </tr>
                      {expanded && (
                        <tr>
                          <td colSpan={10} style={{ background: 'var(--bg-2)', padding: 'var(--space-4)' }}>
                            <TradeReasoning row={row} isOpen={isOpen} />
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function TradeReasoning({ row, isOpen }) {
  return (
    <div className="grid grid-2 gap-4">
      <div>
        <div className="eyebrow" style={{ marginBottom: 8 }}>Entry context</div>
        <Detail label="Signal date" value={row.signal_date} />
        <Detail label="Trade date" value={row.trade_date} />
        <Detail label="Entry $" value={fmtMoney(row.entry_price || row.avg_entry_price)} />
        <Detail label="Quantity" value={row.entry_quantity || row.initial_quantity || row.quantity} />
        <Detail label="Stop" value={fmtMoney(row.current_stop_price || row.initial_stop)} />
        <Detail label="Base type" value={row.base_type} />
        <Detail label="Stage phase" value={row.stage_phase} />
        <Detail label="Swing score" value={row.swing_score != null ? `${row.swing_score} (${row.swing_grade || '?'})` : '—'} />
      </div>
      <div>
        <div className="eyebrow" style={{ marginBottom: 8 }}>{isOpen ? 'Position health' : 'Exit context'}</div>
        {isOpen ? (
          <>
            <Detail label="Distribution days" value={row.distribution_day_count} />
            <Detail label="Targets hit" value={row.target_levels_hit} />
            <Detail label="Trail stop" value={fmtMoney(row.current_stop_price)} />
            <Detail label="Stage" value={row.stage_in_exit_plan} />
          </>
        ) : (
          <>
            <Detail label="Exit date" value={row.exit_date} />
            <Detail label="Exit $" value={fmtMoney(row.exit_price)} />
            <Detail label="Exit reason" value={row.exit_reason} />
            <Detail label="Days held" value={row.trade_duration_days} />
            <Detail label="R multiple" value={row.exit_r_multiple != null ? `${num(row.exit_r_multiple)}R` : '—'} />
            <Detail label="MFE / MAE" value={`${row.mfe_pct || '—'}% / ${row.mae_pct || '—'}%`} />
          </>
        )}
      </div>
    </div>
  );
}
function Detail({ label, value }) {
  return (
    <div className="flex" style={{ padding: '4px 0', fontSize: 'var(--t-xs)' }}>
      <span className="muted" style={{ minWidth: 130 }}>{label}</span>
      <span className="strong mono tnum" style={{ flex: 1, textAlign: 'right' }}>{value || '—'}</span>
    </div>
  );
}

// ─── ACTIVITY VIEW ─────────────────────────────────────────────────────────
const ACTION_ICON = {
  ENTRY: <Bolt size={16} className="up" />,
  EXIT: <Minus size={16} className="down" />,
  STOP: <TrendingUp size={16} style={{ color: 'var(--amber)' }} />,
  PARTIAL: <TrendingDown size={16} style={{ color: 'var(--amber)' }} />,
  PYRAMID: <TrendingUp size={16} className="up" />,
  HALT: <AlertTriangle size={16} className="down" />,
  SKIP: <Info size={16} className="faint" />,
  PASS: <CheckCircle size={16} className="up" />,
};

function ActivityView() {
  const [filter, setFilter] = useState('');
  const [search, setSearch] = useState('');

  const { data: log, isLoading, refetch } = useQuery({
    queryKey: ['algo-audit-log', filter],
    queryFn: () => api.get(`/api/algo/audit-log?limit=300${filter ? '&action_type=' + filter : ''}`).then(r => r.data),
    refetchInterval: 60000,
  });

  const items = useMemo(() => {
    let rows = log?.items || [];
    if (search) {
      const s = search.toLowerCase();
      rows = rows.filter(r =>
        (r.symbol || '').toLowerCase().includes(s) ||
        (r.action_type || '').toLowerCase().includes(s) ||
        JSON.stringify(r.details || {}).toLowerCase().includes(s)
      );
    }
    return rows;
  }, [log, search]);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Activity Log</div>
          <div className="card-sub">algo_audit_log · every decision the algo makes</div>
        </div>
        <div className="card-actions">
          <button className="btn btn-icon btn-ghost" onClick={refetch}><RefreshCw size={14} /></button>
        </div>
      </div>
      <div className="card-body">
        <div className="flex gap-3" style={{ marginBottom: 'var(--space-4)' }}>
          <select className="select" value={filter} onChange={e => setFilter(e.target.value)} style={{ width: 180 }}>
            <option value="">All actions</option>
            <option value="ENTRY">Entries</option>
            <option value="EXIT">Exits</option>
            <option value="STOP">Stop adjustments</option>
            <option value="PYRAMID">Pyramid adds</option>
            <option value="HALT">Halts / breakers</option>
            <option value="SKIP">Skipped signals</option>
          </select>
          <div style={{ position: 'relative', flex: 1 }}>
            <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-faint)' }} />
            <input className="input" placeholder="Search symbol or detail" value={search}
              onChange={e => setSearch(e.target.value)} style={{ paddingLeft: 32 }} />
          </div>
        </div>

        {isLoading ? <Empty title="Loading…" /> : items.length === 0 ? (
          <Empty title="No activity yet" desc="The algo logs every decision here. Entries appear after each orchestrator run." />
        ) : (
          <div className="flex flex-col gap-2">
            {items.map(it => <ActivityRow key={it.id} item={it} />)}
          </div>
        )}
      </div>
    </div>
  );
}

function ActivityRow({ item }) {
  const [open, setOpen] = useState(false);
  const actionKey = (item.action_type || '').toUpperCase();
  const icon = Object.entries(ACTION_ICON).find(([k]) => actionKey.includes(k))?.[1] || <Info size={16} className="muted" />;
  const failed = item.status === 'error' || !!item.error;
  return (
    <div className="panel" style={{ padding: 0 }}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', background: 'transparent', border: 'none', textAlign: 'left',
          padding: 'var(--space-3) var(--space-4)', cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: 'var(--space-3)',
        }}
      >
        {icon}
        <div className="flex-1" style={{ minWidth: 0 }}>
          <div className="t-sm strong" style={{ fontWeight: 'var(--w-medium)', color: failed ? 'var(--danger)' : 'var(--text)' }}>
            {item.action_type}
            {item.symbol && <span className="muted" style={{ marginLeft: 8 }}>· {item.symbol}</span>}
          </div>
          <div className="t-xs muted">
            {fmtAgo(item.created_at)} · {item.actor || 'orchestrator'}
            {failed && <span className="down" style={{ marginLeft: 8 }}>FAILED</span>}
          </div>
        </div>
        {open ? <ChevronUp size={16} className="muted" /> : <ChevronDown size={16} className="muted" />}
      </button>
      {open && (
        <div style={{ borderTop: '1px solid var(--border-soft)', padding: 'var(--space-3) var(--space-4)' }}>
          {item.error && <div className="alert alert-danger t-xs" style={{ marginBottom: 8 }}><AlertCircle size={14} />{item.error}</div>}
          {item.details && (
            <pre className="mono t-xs" style={{
              background: 'var(--bg)', border: '1px solid var(--border)',
              padding: 'var(--space-3)', borderRadius: 'var(--r-sm)',
              whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0,
              color: 'var(--text-2)',
            }}>
              {typeof item.details === 'string' ? item.details : JSON.stringify(item.details, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

// ─── NOTIFICATIONS VIEW ────────────────────────────────────────────────────
function NotificationsView() {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['algo-notifications-all'],
    queryFn: () => api.get('/api/algo/notifications?include_seen=1').then(r => r.data),
    refetchInterval: 30000,
  });
  const items = data?.items || [];
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Notifications</div>
          <div className="card-sub">Circuit-breaker fires, sector rotation, exposure transitions</div>
        </div>
        <div className="card-actions">
          <button className="btn btn-icon btn-ghost" onClick={refetch}><RefreshCw size={14} /></button>
        </div>
      </div>
      <div className="card-body">
        {isLoading ? <Empty title="Loading…" /> : items.length === 0 ? (
          <Empty title="No active notifications" desc="Quiet markets." />
        ) : (
          <div className="flex flex-col gap-2">
            {items.map(n => (
              <div key={n.id} className={`alert ${n.severity === 'error' || n.severity === 'critical' ? 'alert-danger' : n.severity === 'warn' ? 'alert-warn' : 'alert-info'}`}>
                <Info size={16} />
                <div style={{ flex: 1 }}>
                  <div className="flex items-center gap-2">
                    <span className={`badge badge-${n.severity === 'error' || n.severity === 'critical' ? 'danger' : n.severity === 'warn' ? 'amber' : 'brand'}`}>
                      {(n.severity || 'info').toUpperCase()}
                    </span>
                    <span className="strong" style={{ fontWeight: 'var(--w-semibold)' }}>{n.title || n.event_type}</span>
                    <span className="t-xs faint mono" style={{ marginLeft: 'auto' }}>{fmtAgo(n.created_at)}</span>
                  </div>
                  <div className="t-sm" style={{ marginTop: 4 }}>{n.message}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── EMPTY ─────────────────────────────────────────────────────────────────
function Empty({ title, desc }) {
  return (
    <div className="empty">
      <Inbox />
      <div className="empty-title">{title}</div>
      {desc && <div className="empty-desc">{desc}</div>}
    </div>
  );
}
