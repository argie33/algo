/**
 * Backtest Results — list runs, drill into trades + equity curve.
 * Pure JSX + theme.css classes.
 */

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  RefreshCw, ChevronLeft, ChevronRight, ArrowLeft, Inbox, AlertCircle,
} from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from 'recharts';
import { api } from '../services/api';

const fmtDate = (s) => s ? new Date(s).toLocaleDateString() : '—';
const num = (v, dp = 2) => v == null || isNaN(Number(v)) ? '—' : Number(v).toFixed(dp);
const pct = (v, dp = 1) => v == null || isNaN(Number(v)) ? '—' : `${Number(v).toFixed(dp)}%`;

const TOOLTIP_STYLE = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--r-sm)',
  fontSize: 'var(--t-xs)',
  padding: 'var(--space-2) var(--space-3)',
};

export default function BacktestResults() {
  const [filters, setFilters] = useState({
    strategy_name: '',
    sort_by: 'run_timestamp',
    order: 'desc',
    limit: 20,
    offset: 0,
  });
  const [selectedRun, setSelectedRun] = useState(null);

  const { data: list, isLoading, error: listErr, refetch } = useQuery({
    queryKey: ['backtest-runs', filters],
    queryFn: () => {
      const p = new URLSearchParams();
      if (filters.strategy_name) p.set('strategy_name', filters.strategy_name);
      p.set('limit', filters.limit);
      p.set('offset', filters.offset);
      p.set('sort_by', filters.sort_by);
      p.set('order', filters.order);
      return api.get(`/api/research/backtests?${p.toString()}`).then(r => r.data);
    },
  });

  const { data: detail } = useQuery({
    queryKey: ['backtest-detail', selectedRun],
    queryFn: () => api.get(`/api/research/backtests/${selectedRun}`).then(r => r.data),
    enabled: !!selectedRun,
  });

  const runs = list?.items || [];
  const pagination = list?.pagination || { total: 0, page: 1, totalPages: 1 };

  if (selectedRun && detail) {
    return <RunDetail detail={detail} onBack={() => setSelectedRun(null)} />;
  }

  return (
    <div className="main-content">
      <div className="page-head">
        <div>
          <div className="page-head-title">Backtest Results</div>
          <div className="page-head-sub">
            Strategy validation runs · win rate · expectancy · Sharpe · max DD
          </div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-outline btn-sm" onClick={() => refetch()}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="card">
        <div className="card-body">
          <div className="flex items-center gap-3" style={{ flexWrap: 'wrap' }}>
            <select
              className="select"
              value={filters.strategy_name}
              onChange={(e) => setFilters({ ...filters, strategy_name: e.target.value, offset: 0 })}
            >
              <option value="">All strategies</option>
              <option value="swing">Swing breakout</option>
              <option value="range">Range trading</option>
              <option value="mean_reversion">Mean reversion</option>
            </select>
            <select
              className="select"
              value={filters.sort_by}
              onChange={(e) => setFilters({ ...filters, sort_by: e.target.value })}
            >
              <option value="run_timestamp">Date</option>
              <option value="win_rate">Win rate</option>
              <option value="expectancy_per_trade">Expectancy</option>
              <option value="sharpe">Sharpe</option>
              <option value="total_signals">Signals</option>
            </select>
            <select
              className="select"
              value={filters.order}
              onChange={(e) => setFilters({ ...filters, order: e.target.value })}
            >
              <option value="desc">Desc</option>
              <option value="asc">Asc</option>
            </select>
            <span className="t-xs muted" style={{ marginLeft: 'auto' }}>
              {pagination.total ?? 0} runs total
            </span>
          </div>
        </div>
      </div>

      {/* List */}
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-body" style={{ padding: 0 }}>
          {listErr ? (
            <div className="alert alert-danger" style={{ margin: 'var(--space-4)' }}>
              <AlertCircle size={16} />
              <div>{listErr.message || 'Failed to load runs'}</div>
            </div>
          ) : isLoading ? (
            <Empty title="Loading…" />
          ) : runs.length === 0 ? (
            <Empty title="No backtest runs" desc="Trigger a walk-forward run to populate this list." />
          ) : (
            <div style={{ overflow: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Run</th>
                    <th>Strategy</th>
                    <th>Range</th>
                    <th className="num">Signals</th>
                    <th className="num">Win %</th>
                    <th className="num">Expect</th>
                    <th className="num">Max DD</th>
                    <th className="num">Sharpe</th>
                    <th className="num">Return %</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.run_id}>
                      <td><span className="strong">{r.run_name}</span></td>
                      <td className="muted t-xs">{r.strategy_name}</td>
                      <td className="t-xs muted">{fmtDate(r.date_start)} → {fmtDate(r.date_end)}</td>
                      <td className="num mono tnum">{r.total_signals ?? '—'}</td>
                      <td className="num">
                        <span className={`badge ${(r.win_rate >= 50) ? 'badge-success' : 'badge-amber'}`}>
                          {pct(r.win_rate)}
                        </span>
                      </td>
                      <td className="num mono tnum">{num(r.expectancy_per_trade, 3)}</td>
                      <td className="num mono tnum down">{pct(r.max_drawdown_pct)}</td>
                      <td className="num mono tnum">{num(r.sharpe)}</td>
                      <td className="num">
                        <span className={`badge ${(r.total_return_pct >= 0) ? 'badge-success' : 'badge-danger'}`}>
                          {pct(r.total_return_pct)}
                        </span>
                      </td>
                      <td>
                        <button className="btn btn-outline btn-sm" onClick={() => setSelectedRun(r.run_id)}>
                          View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Pagination */}
      {runs.length > 0 && (
        <div className="flex items-center justify-between" style={{ marginTop: 'var(--space-4)' }}>
          <span className="t-xs muted">
            Page {pagination.page ?? 1} of {pagination.totalPages ?? 1} · {pagination.total ?? 0} runs
          </span>
          <div className="flex items-center gap-2">
            <button className="btn btn-outline btn-sm"
                    disabled={!pagination.hasPrev}
                    onClick={() => setFilters({ ...filters, offset: Math.max(0, filters.offset - filters.limit) })}>
              <ChevronLeft size={14} /> Prev
            </button>
            <button className="btn btn-outline btn-sm"
                    disabled={!pagination.hasNext}
                    onClick={() => setFilters({ ...filters, offset: filters.offset + filters.limit })}>
              Next <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Run detail view ───────────────────────────────────────────────────────
function RunDetail({ detail, onBack }) {
  const navigate = useNavigate();
  const r = detail?.run || {};
  const trades = detail?.trades || [];
  const tp = detail?.trade_pagination || { total: trades.length };

  return (
    <div className="main-content">
      <div className="page-head">
        <div>
          <button className="btn btn-ghost btn-sm" onClick={onBack} style={{ marginBottom: 'var(--space-2)' }}>
            <ArrowLeft size={14} /> Back to runs
          </button>
          <div className="page-head-title">{r.run_name || 'Run'}</div>
          <div className="page-head-sub">
            {r.strategy_name} · {fmtDate(r.date_start)} → {fmtDate(r.date_end)}
          </div>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-4">
        <Kpi label="Total Signals" value={<span className="mono tnum">{r.total_signals ?? '—'}</span>} />
        <Kpi label="Win Rate" value={<span className="mono tnum">{pct(r.win_rate)}</span>}
             tone={r.win_rate >= 50 ? 'up' : 'down'} />
        <Kpi label="Expectancy" value={<span className="mono tnum">{num(r.expectancy_per_trade, 3)}</span>}
             tone={r.expectancy_per_trade > 0 ? 'up' : 'down'} />
        <Kpi label="Sharpe" value={<span className="mono tnum">{num(r.sharpe)}</span>}
             tone={r.sharpe > 1 ? 'up' : ''} />
      </div>
      <div className="grid grid-4" style={{ marginTop: 'var(--space-4)' }}>
        <Kpi label="Profit Factor" value={<span className="mono tnum">{num(r.profit_factor)}</span>}
             tone={r.profit_factor > 1.5 ? 'up' : ''} />
        <Kpi label="Max Drawdown" value={<span className="mono tnum down">{pct(r.max_drawdown_pct)}</span>} />
        <Kpi label="Avg Win" value={<span className="mono tnum up">{pct(r.avg_win_pct, 2)}</span>} />
        <Kpi label="Avg Loss" value={<span className="mono tnum down">{pct(r.avg_loss_pct, 2)}</span>} />
      </div>

      {r.notes && (
        <div className="card" style={{ marginTop: 'var(--space-4)' }}>
          <div className="card-body">
            <div className="eyebrow">Notes</div>
            <div className="t-sm" style={{ marginTop: 'var(--space-2)' }}>{r.notes}</div>
          </div>
        </div>
      )}

      {/* Equity curve */}
      {Array.isArray(r.equity_curve) && r.equity_curve.length > 0 && (
        <div className="card" style={{ marginTop: 'var(--space-4)' }}>
          <div className="card-head">
            <div>
              <div className="card-title">Equity Curve</div>
              <div className="card-sub">Portfolio value over backtest window</div>
            </div>
          </div>
          <div className="card-body">
            <div style={{ height: 300 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={r.equity_curve} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="bkEq" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--brand)" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="var(--brand)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                  <XAxis dataKey="date" stroke="var(--text-3)" fontSize={11} />
                  <YAxis stroke="var(--text-3)" fontSize={11} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Area type="monotone" dataKey="equity" stroke="var(--brand)" strokeWidth={2}
                        fill="url(#bkEq)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* Trades */}
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Trades ({tp.total})</div>
            <div className="card-sub">Per-signal outcome with MFE / MAE</div>
          </div>
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          {trades.length === 0 ? (
            <Empty title="No trades on this run" />
          ) : (
            <div style={{ maxHeight: '60vh', overflow: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Signal</th>
                    <th>Exit</th>
                    <th className="num">Entry</th>
                    <th className="num">Exit</th>
                    <th className="num">Return</th>
                    <th>Outcome</th>
                    <th className="num">Days</th>
                    <th className="num">MFE</th>
                    <th className="num">MAE</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((t) => (
                    <tr key={t.trade_id}>
                      <td>
                        <span
                          className="strong"
                          style={{ cursor: 'pointer' }}
                          onClick={() => navigate(`/app/stock/${t.symbol}`)}
                        >
                          {t.symbol}
                        </span>
                      </td>
                      <td className="t-xs muted">{fmtDate(t.signal_date)}</td>
                      <td className="t-xs muted">{fmtDate(t.exit_date)}</td>
                      <td className="num mono tnum">${num(t.entry_price)}</td>
                      <td className="num mono tnum">${num(t.exit_price)}</td>
                      <td className="num">
                        <span className={`mono tnum ${t.return_pct >= 0 ? 'up' : 'down'}`}>
                          {pct(t.return_pct, 2)}
                        </span>
                      </td>
                      <td className="t-xs muted" style={{ textTransform: 'uppercase' }}>{t.outcome}</td>
                      <td className="num mono tnum muted">{t.days_held ?? '—'}</td>
                      <td className="num mono tnum up">{pct(t.mfe_pct)}</td>
                      <td className="num mono tnum down">{pct(t.mae_pct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Kpi({ label, value, tone }) {
  return (
    <div className="card" style={{ padding: 'var(--space-5) var(--space-6)' }}>
      <div className="eyebrow">{label}</div>
      <div className={`mono ${tone || ''}`}
           style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', marginTop: 'var(--space-2)' }}>
        {value}
      </div>
    </div>
  );
}

function Empty({ title, desc }) {
  return (
    <div className="empty">
      <Inbox size={36} />
      <div className="empty-title">{title}</div>
      {desc && <div className="empty-desc">{desc}</div>}
    </div>
  );
}
