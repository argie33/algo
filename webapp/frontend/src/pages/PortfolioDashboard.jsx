/**
 * Portfolio Dashboard — algo-only.
 *
 * Surfaces every metric the algo tracks: open positions w/ R/stop/targets,
 * performance ratios (Sharpe / Sortino / Calmar / max DD), trade-level
 * win rate / expectancy / profit factor, equity-curve from algo_portfolio_snapshots,
 * exposure context from market regime.
 *
 * Pure JSX + theme.css classes.
 */

import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  RefreshCw, TrendingUp, Activity, Shield,
  Inbox, DollarSign, BarChart3, Zap, AlertTriangle,
} from 'lucide-react';
import {
  AreaChart, Area, BarChart, Bar, Cell, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from 'recharts';
import { api } from '../services/api';

const fmtMoney = (v) =>
  v == null || isNaN(Number(v)) ? '—'
  : `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmtMoneyShort = (v) => {
  if (v == null || isNaN(Number(v))) return '—';
  const n = Number(v);
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
};
const num = (v, dp = 2) => v == null || isNaN(Number(v)) ? '—' : Number(v).toFixed(dp);
const pct = (v, dp = 2) => v == null || isNaN(Number(v)) ? '—' : `${Number(v).toFixed(dp)}%`;
const Pnl = ({ value, suffix = '' }) => {
  if (value == null || isNaN(Number(value))) return <span className="muted">—</span>;
  const v = Number(value);
  const cls = v > 0 ? 'up' : v < 0 ? 'down' : 'flat';
  const sign = v > 0 ? '+' : '';
  return (
    <span className={`mono tnum ${cls}`} style={{ fontWeight: 'var(--w-semibold)' }}>
      {sign}{v.toFixed(2)}{suffix}
    </span>
  );
};

const TOOLTIP_STYLE = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--r-sm)',
  fontSize: 'var(--t-xs)',
  padding: 'var(--space-2) var(--space-3)',
  boxShadow: 'var(--shadow-md)',
};

export default function PortfolioDashboard() {
  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey: ['algo-status'],
    queryFn: () => api.get('/api/algo/status').then(r => r.data?.data),
    refetchInterval: 30000,
  });
  const { data: positions, isLoading: posLoading } = useQuery({
    queryKey: ['algo-positions'],
    queryFn: () => api.get('/api/algo/positions').then(r => r.data?.items || []),
    refetchInterval: 30000,
  });
  const { data: perf } = useQuery({
    queryKey: ['algo-performance'],
    queryFn: () => api.get('/api/algo/performance').then(r => r.data?.data),
    refetchInterval: 60000,
  });
  const { data: trades } = useQuery({
    queryKey: ['algo-trades-recent'],
    queryFn: () => api.get('/api/algo/trades?limit=20').then(r => r.data?.items || []),
    refetchInterval: 60000,
  });
  const { data: markets } = useQuery({
    queryKey: ['algo-markets'],
    queryFn: () => api.get('/api/algo/markets').then(r => r.data?.data),
    refetchInterval: 60000,
  });

  const portfolio = status?.portfolio || {};
  const market = status?.market || {};

  return (
    <div className="main-content">
      <div className="page-head">
        <div>
          <div className="page-head-title">Portfolio</div>
          <div className="page-head-sub">
            Algo positions · Performance metrics · Risk profile · Market context
          </div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-outline btn-sm" onClick={() => refetchStatus()}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {/* Top KPI strip */}
      <div className="grid grid-4">
        <Kpi
          label="Portfolio Value"
          value={fmtMoneyShort(portfolio.total_value)}
          sub={`${portfolio.position_count ?? 0} open positions`}
          icon={DollarSign}
        />
        <Kpi
          label="Unrealized P&L"
          value={<Pnl value={portfolio.unrealized_pnl_pct} suffix="%" />}
          sub={`Daily: ${num(portfolio.daily_return_pct)}%`}
          icon={Activity}
          tone={portfolio.unrealized_pnl_pct >= 0 ? 'up' : 'down'}
        />
        <Kpi
          label="Total Return"
          value={<Pnl value={perf?.total_return_pct} suffix="%" />}
          sub={`${perf?.total_trades ?? 0} closed trades`}
          icon={TrendingUp}
          tone={perf?.total_return_pct >= 0 ? 'up' : 'down'}
        />
        <Kpi
          label="Market Regime"
          value={<span className="mono">{(market.trend || '—').toString().toUpperCase()}</span>}
          sub={`Stage ${market.stage ?? '—'} · DD ${market.distribution_days ?? 0}`}
          icon={Shield}
        />
      </div>

      {/* Ratios row */}
      <div className="grid grid-4" style={{ marginTop: 'var(--space-4)' }}>
        <Kpi
          label="Sharpe (annualized)"
          value={<span className="mono tnum">{num(perf?.sharpe_annualized)}</span>}
          sub="risk-adjusted"
          icon={BarChart3}
          tone={perf?.sharpe_annualized > 1 ? 'up' : perf?.sharpe_annualized < 0 ? 'down' : ''}
        />
        <Kpi
          label="Sortino"
          value={<span className="mono tnum">{num(perf?.sortino_annualized)}</span>}
          sub="downside-only"
          icon={Shield}
        />
        <Kpi
          label="Calmar"
          value={<span className="mono tnum">{num(perf?.calmar_ratio)}</span>}
          sub={`Max DD ${pct(perf?.max_drawdown_pct, 1)}`}
          icon={AlertTriangle}
          tone={perf?.calmar_ratio > 1 ? 'up' : perf?.max_drawdown_pct > 20 ? 'down' : ''}
        />
        <Kpi
          label="Profit Factor"
          value={<span className="mono tnum">{perf?.profit_factor == null ? '—' : num(perf.profit_factor)}</span>}
          sub={`${perf?.win_rate_pct ?? 0}% win rate`}
          icon={Zap}
          tone={perf?.profit_factor > 1.5 ? 'up' : perf?.profit_factor < 1 ? 'down' : ''}
        />
      </div>

      {/* Equity curve + Trade outcome distribution */}
      <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
        <EquityCurve />
        <TradeDistribution trades={trades || []} />
      </div>

      {/* Open positions table */}
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Open Positions ({positions?.length || 0})</div>
            <div className="card-sub">Algo-managed positions with current P&L and exit-plan stage</div>
          </div>
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          {posLoading ? (
            <Empty title="Loading…" />
          ) : !positions || positions.length === 0 ? (
            <Empty title="No open positions" desc="Algo isn't holding anything right now." />
          ) : (
            <div style={{ overflow: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th className="num">Qty</th>
                    <th className="num">Entry</th>
                    <th className="num">Current</th>
                    <th className="num">Value</th>
                    <th className="num">P&L $</th>
                    <th className="num">P&L %</th>
                    <th className="num">Days</th>
                    <th>Stage</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p, i) => (
                    <tr key={i}>
                      <td>
                        <span className="strong" style={{ fontWeight: 'var(--w-semibold)' }}>{p.symbol}</span>
                      </td>
                      <td className="num mono tnum">{p.quantity}</td>
                      <td className="num mono tnum">{fmtMoney(p.avg_entry_price)}</td>
                      <td className="num mono tnum">{fmtMoney(p.current_price)}</td>
                      <td className="num mono tnum">{fmtMoneyShort(p.position_value)}</td>
                      <td className="num"><Pnl value={p.unrealized_pnl} /></td>
                      <td className="num"><Pnl value={p.unrealized_pnl_pct} suffix="%" /></td>
                      <td className="num mono tnum muted">{p.days_since_entry ?? '—'}</td>
                      <td>
                        <span className="badge" style={{ textTransform: 'uppercase' }}>
                          {(p.stage_in_exit_plan || 'init').toString()}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Trade-level metrics + recent trades */}
      <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">Trade Metrics</div>
              <div className="card-sub">Closed trades · win/loss profile · expectancy</div>
            </div>
          </div>
          <div className="card-body">
            <div className="grid grid-3">
              <Stile label="Avg Win" value={<Pnl value={perf?.avg_win_pct} suffix="%" />} />
              <Stile label="Avg Loss" value={<Pnl value={perf?.avg_loss_pct} suffix="%" />} />
              <Stile label="Expectancy" value={<span className="mono tnum">{num(perf?.expectancy_r, 3)}R</span>} />
              <Stile label="Avg Win R" value={<span className="mono tnum">{num(perf?.avg_win_r)}R</span>} />
              <Stile label="Avg Loss R" value={<span className="mono tnum">{num(perf?.avg_loss_r)}R</span>} />
              <Stile label="Avg Hold" value={<span className="mono tnum">{num(perf?.avg_hold_days, 1)}d</span>} />
              <Stile label="Best Streak" value={<span className="mono tnum up">{perf?.best_win_streak ?? 0}W</span>} />
              <Stile label="Worst Streak" value={<span className="mono tnum down">{perf?.worst_loss_streak ?? 0}L</span>} />
              <Stile label="Current" value={<StreakValue v={perf?.current_streak} />} />
            </div>
            <div style={{ marginTop: 'var(--space-4)', paddingTop: 'var(--space-4)', borderTop: '1px solid var(--border-soft)' }}>
              <div className="grid grid-3">
                <Stile label="Total P&L" value={<Pnl value={perf?.total_pnl_dollars} />} />
                <Stile label="Gross Wins" value={<span className="mono tnum up">{fmtMoneyShort(perf?.gross_win_dollars)}</span>} />
                <Stile label="Gross Losses" value={<span className="mono tnum down">{fmtMoneyShort(perf?.gross_loss_dollars)}</span>} />
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">Recent Trades</div>
              <div className="card-sub">Last 20 closed positions</div>
            </div>
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            {(!trades || trades.length === 0) ? (
              <Empty title="No closed trades yet" />
            ) : (
              <div style={{ maxHeight: '420px', overflow: 'auto' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th className="num">Entry</th>
                      <th className="num">Exit</th>
                      <th className="num">P&L %</th>
                      <th className="num">R</th>
                      <th className="num">Days</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.map((t, i) => (
                      <tr key={i}>
                        <td>
                          <span className="strong" style={{ fontWeight: 'var(--w-semibold)' }}>{t.symbol}</span>
                        </td>
                        <td className="num mono tnum">{fmtMoney(t.entry_price)}</td>
                        <td className="num mono tnum">{t.exit_price ? fmtMoney(t.exit_price) : '—'}</td>
                        <td className="num"><Pnl value={t.profit_loss_pct} suffix="%" /></td>
                        <td className="num"><Pnl value={t.exit_r_multiple} suffix="R" /></td>
                        <td className="num mono tnum muted">{t.trade_duration_days ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Market context */}
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Market Context</div>
            <div className="card-sub">Regime, exposure target, and risk inputs feeding position sizing</div>
          </div>
        </div>
        <div className="card-body">
          <div className="grid grid-4">
            <Stile
              label="Exposure Target"
              value={<span className="mono tnum">{markets?.market_exposure?.exposure_pct ?? '—'}%</span>}
              sub={(markets?.market_exposure?.regime || '').toString().toUpperCase()}
            />
            <Stile
              label="9-Factor Score"
              value={<span className="mono tnum">{markets?.market_exposure?.composite_score ?? '—'}/100</span>}
              sub="0-100 IBD-style"
            />
            <Stile
              label="VIX"
              value={<span className="mono tnum">{num(market.vix, 1)}</span>}
              sub={market.vix > 25 ? 'elevated' : market.vix > 15 ? 'normal' : 'low'}
            />
            <Stile
              label="Distribution Days"
              value={<span className={`mono tnum ${market.distribution_days >= 5 ? 'down' : ''}`}>
                {market.distribution_days ?? 0}
              </span>}
              sub="trailing 4 weeks"
            />
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Equity curve ──────────────────────────────────────────────────────────
function EquityCurve() {
  const { data: snaps } = useQuery({
    queryKey: ['algo-equity-curve'],
    queryFn: async () => {
      const r = await api.get('/api/algo/performance');
      return r.data?.data;
    },
    refetchInterval: 60000,
  });

  const { data: chartData } = useQuery({
    queryKey: ['algo-equity-curve'],
    queryFn: async () => {
      const r = await api.get('/api/algo/equity-curve?limit=180').catch(() => null);
      return r?.data?.items || [];
    },
    refetchInterval: 60000,
  });

  const series = useMemo(() => {
    if (!chartData || chartData.length === 0) return [];
    return chartData.map(s => ({
      date: String(s.snapshot_date || s.date || '').slice(5, 10),
      value: Number(s.total_portfolio_value || 0),
    })).filter(d => d.value > 0);
  }, [chartData]);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Equity Curve</div>
          <div className="card-sub">Total portfolio value · daily snapshots</div>
        </div>
      </div>
      <div className="card-body">
        {series.length < 2 ? (
          <Empty
            title="Equity curve building"
            desc={`${series.length} snapshot${series.length === 1 ? '' : 's'} so far · need 2+ for a curve.`}
          />
        ) : (
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--brand)" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="var(--brand)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                <XAxis dataKey="date" stroke="var(--text-3)" fontSize={11} tickLine={false} />
                <YAxis stroke="var(--text-3)" fontSize={11} tickLine={false}
                       tickFormatter={(v) => fmtMoneyShort(v)} width={64} />
                <Tooltip contentStyle={TOOLTIP_STYLE}
                  formatter={(v) => [fmtMoney(v), 'Value']} />
                <Area type="monotone" dataKey="value" stroke="var(--brand)" strokeWidth={2}
                      fill="url(#equityGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Trade outcome distribution ────────────────────────────────────────────
function TradeDistribution({ trades }) {
  const buckets = useMemo(() => {
    if (!trades || trades.length === 0) return [];
    const bins = [
      { range: '< -2R', min: -Infinity, max: -2, count: 0 },
      { range: '-2 to -1R', min: -2, max: -1, count: 0 },
      { range: '-1 to 0R', min: -1, max: 0, count: 0 },
      { range: '0 to 1R', min: 0, max: 1, count: 0 },
      { range: '1 to 2R', min: 1, max: 2, count: 0 },
      { range: '2 to 3R', min: 2, max: 3, count: 0 },
      { range: '> 3R', min: 3, max: Infinity, count: 0 },
    ];
    for (const t of trades) {
      const r = Number(t.exit_r_multiple);
      if (isNaN(r)) continue;
      const b = bins.find(x => r >= x.min && r < x.max) || bins[bins.length - 1];
      b.count += 1;
    }
    return bins;
  }, [trades]);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Trade Outcome Distribution</div>
          <div className="card-sub">R-multiples across recent closed trades</div>
        </div>
      </div>
      <div className="card-body">
        {buckets.length === 0 ? (
          <Empty title="No closed trades yet" />
        ) : (
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={buckets} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                <XAxis dataKey="range" stroke="var(--text-3)" fontSize={11} tickLine={false} />
                <YAxis stroke="var(--text-3)" fontSize={11} tickLine={false} allowDecimals={false} width={32} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="count">
                  {buckets.map((b, i) => (
                    <Cell key={i}
                      fill={b.min >= 0 ? 'var(--success)' : 'var(--danger)'}
                      fillOpacity={0.85} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── shared little components ──────────────────────────────────────────────
function Kpi({ label, value, sub, icon: Icon, tone }) {
  return (
    <div className="card" style={{ padding: 'var(--space-5) var(--space-6)' }}>
      <div className="flex items-center justify-between">
        <div className="eyebrow">{label}</div>
        {Icon && <Icon size={16} className="muted" />}
      </div>
      <div className={`mono ${tone || ''}`}
           style={{ fontSize: 'var(--t-xl)', fontWeight: 'var(--w-bold)', marginTop: 'var(--space-2)' }}>
        {value}
      </div>
      {sub && <div className="t-xs muted" style={{ marginTop: 'var(--space-1)' }}>{sub}</div>}
    </div>
  );
}

function Stile({ label, value, sub }) {
  return (
    <div className="stile">
      <div className="stile-label">{label}</div>
      <div className="stile-value">{value}</div>
      {sub && <div className="stile-sub">{sub}</div>}
    </div>
  );
}

function StreakValue({ v }) {
  if (v == null || v === 0) return <span className="mono muted">0</span>;
  const cls = v > 0 ? 'up' : 'down';
  return <span className={`mono tnum ${cls}`}>{v > 0 ? `${v}W` : `${Math.abs(v)}L`}</span>;
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
