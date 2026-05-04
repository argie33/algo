/**
 * Portfolio Dashboard — algo-only.
 *
 * Surfaces every metric the algo tracks: open positions w/ R/stop/targets,
 * performance ratios (Sharpe / Sortino / Calmar / max DD), trade-level
 * win rate / expectancy / profit factor, equity-curve from algo_portfolio_snapshots,
 * exposure context from market regime. Plus deep risk + composition analytics:
 * R-ladder, risk-pie, sector-bars, stage-donut, return-histogram, drawdown,
 * setup outcomes, holding histogram, position health, circuit breakers.
 *
 * Pure JSX + theme.css classes. Recharts only.
 */

import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  RefreshCw, TrendingUp, Activity, Shield,
  Inbox, DollarSign, BarChart3, Zap, AlertTriangle, Target,
} from 'lucide-react';
import {
  AreaChart, Area, BarChart, Bar, Cell, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, PieChart, Pie, Legend, ReferenceLine,
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

const PIE_PALETTE = [
  'var(--brand)', 'var(--cyan)', 'var(--purple)', 'var(--success)',
  'var(--amber)', 'var(--danger)', '#8BC34A', '#E91E63',
  '#FFC107', '#795548', '#607D8B', '#FF6B6B',
];

export default function PortfolioDashboard() {
  const navigate = useNavigate();

  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey: ['algo-status'],
    queryFn: () => api.get('/api/algo/status').then(r => r.data?.data),
    refetchInterval: 60000,
  });
  const { data: positions, isLoading: posLoading } = useQuery({
    queryKey: ['algo-positions'],
    queryFn: () => api.get('/api/algo/positions').then(r => r.data?.items || []),
    refetchInterval: 60000,
  });
  const { data: perf } = useQuery({
    queryKey: ['algo-performance'],
    queryFn: () => api.get('/api/algo/performance').then(r => r.data?.data),
    refetchInterval: 60000,
  });
  const { data: trades } = useQuery({
    queryKey: ['algo-trades-recent'],
    queryFn: () => api.get('/api/algo/trades?limit=200').then(r => r.data?.items || []),
    refetchInterval: 60000,
  });
  const { data: markets } = useQuery({
    queryKey: ['algo-markets'],
    queryFn: () => api.get('/api/algo/markets').then(r => r.data?.data),
    refetchInterval: 60000,
  });
  const { data: equityItems } = useQuery({
    queryKey: ['algo-equity-curve'],
    queryFn: () => api.get('/api/algo/equity-curve?limit=180')
                      .then(r => r.data?.items || []).catch(() => []),
    refetchInterval: 60000,
  });
  const { data: breakers } = useQuery({
    queryKey: ['algo-circuit-breakers'],
    queryFn: () => api.get('/api/algo/circuit-breakers')
                      .then(r => r.data?.data).catch(() => null),
    refetchInterval: 60000,
  });

  const portfolio = status?.portfolio || {};
  const market = status?.market || {};
  const totalValue = parseFloat(portfolio.total_value || 0);

  return (
    <div className="main-content">
      <div className="page-head">
        <div>
          <div className="page-head-title">Portfolio</div>
          <div className="page-head-sub">
            Algo positions · Performance · Risk profile · Market context
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

      {/* Circuit breakers */}
      <CircuitBreakerPanel data={breakers} />

      {/* Equity curve + Drawdown chart */}
      <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
        <EquityCurve series={equityItems} />
        <DrawdownChart series={equityItems} />
      </div>

      {/* Daily-return histogram + Trade outcome distribution */}
      <div className="grid grid-2" style={{ marginTop: 'var(--space-4)' }}>
        <DailyReturnHistogram series={equityItems} />
        <TradeDistribution trades={trades || []} />
      </div>

      {/* R-multiple ladder */}
      <RLadderPanel positions={positions || []} loading={posLoading}
                     onSelect={(s) => navigate(`/app/stock/${encodeURIComponent(s)}`)} />

      {/* Risk-pie + Sector concentration + Stage donut */}
      <div className="grid grid-3" style={{ marginTop: 'var(--space-4)' }}>
        <RiskAllocationPie positions={positions || []} totalValue={totalValue}
                            onSelect={(s) => navigate(`/app/stock/${encodeURIComponent(s)}`)} />
        <SectorConcentration positions={positions || []} totalValue={totalValue} />
        <StagePhaseDonut positions={positions || []} />
      </div>

      {/* Position-health table */}
      <PositionHealthTable positions={positions || []} loading={posLoading}
                            onSelect={(s) => navigate(`/app/stock/${encodeURIComponent(s)}`)} />

      {/* Trade-level metrics + holding-period histogram */}
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

        <HoldingPeriodHistogram trades={trades || []} />
      </div>

      {/* Recent trades */}
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Recent Trades</div>
            <div className="card-sub">Last closed positions</div>
          </div>
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          {(!trades || trades.length === 0) ? (
            <Empty title="No closed trades yet" />
          ) : (
            <div style={{ maxHeight: '360px', overflow: 'auto' }}>
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
                  {trades.slice(0, 25).map((t, i) => (
                    <tr key={i}
                        onClick={() => navigate(`/app/stock/${encodeURIComponent(t.symbol)}`)}
                        style={{ cursor: 'pointer' }}>
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
              value={<span className="mono tnum">{markets?.current?.exposure_pct ?? '—'}%</span>}
              sub={(markets?.current?.regime || '').toString().toUpperCase()}
            />
            <Stile
              label="9-Factor Score"
              value={<span className="mono tnum">{markets?.current?.raw_score ?? '—'}/100</span>}
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

// ─── Circuit breaker panel ──────────────────────────────────────────────────
function CircuitBreakerPanel({ data }) {
  const breakers = data?.breakers || [];
  if (breakers.length === 0) {
    return (
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card-head">
          <div>
            <div className="card-title">Circuit Breakers</div>
            <div className="card-sub">Pre-trade kill-switch state</div>
          </div>
        </div>
        <div className="card-body">
          <Empty title="Loading circuit breaker state…" />
        </div>
      </div>
    );
  }
  const tripped = breakers.filter(b => b.triggered).length;
  return (
    <div className="card" style={{ marginTop: 'var(--space-4)' }}>
      <div className="card-head">
        <div>
          <div className="card-title">Circuit Breakers</div>
          <div className="card-sub">
            {tripped === 0
              ? 'All clear — no kill-switches triggered'
              : `${tripped} of ${breakers.length} breakers triggered — new entries halted`}
          </div>
        </div>
        <span className={`badge ${tripped === 0 ? 'badge-success' : 'badge-danger'}`}>
          {tripped === 0 ? 'CLEAR' : 'HALTED'}
        </span>
      </div>
      <div className="card-body">
        <div className="grid grid-4" style={{ gap: 'var(--space-3)' }}>
          {breakers.map(b => {
            const utilPct = b.threshold > 0
              ? Math.min(100, Math.round((Number(b.current) / Number(b.threshold)) * 100))
              : 0;
            const tone = b.triggered ? 'down' : utilPct > 75 ? '' : 'up';
            const color = b.triggered ? 'var(--danger)'
                        : utilPct > 75 ? 'var(--amber)' : 'var(--success)';
            return (
              <div key={b.id} className="card" style={{ padding: 'var(--space-3)' }}>
                <div className="flex items-center justify-between" style={{ marginBottom: 'var(--space-2)' }}>
                  <div className="t-xs muted strong">{b.label}</div>
                  <span className={`badge ${b.triggered ? 'badge-danger' : 'badge-success'}`}
                        style={{ fontSize: 'var(--t-2xs)' }}>
                    {b.triggered ? 'TRIPPED' : 'OK'}
                  </span>
                </div>
                <div className={`mono tnum ${tone}`} style={{ fontSize: 'var(--t-lg)', fontWeight: 'var(--w-bold)' }}>
                  {b.current}{b.unit}
                  <span className="muted t-xs" style={{ marginLeft: 6, fontWeight: 'var(--w-medium)' }}>
                    / {b.threshold}{b.unit}
                  </span>
                </div>
                <div style={{
                  marginTop: 'var(--space-2)',
                  height: 4, background: 'var(--border-soft)',
                  borderRadius: 'var(--r-pill)', overflow: 'hidden',
                }}>
                  <div style={{ height: '100%', width: `${utilPct}%`, background: color, transition: 'width 200ms' }} />
                </div>
                <div className="t-2xs muted" style={{ marginTop: 'var(--space-2)', lineHeight: 1.3 }}>
                  {b.description}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ─── Equity curve ──────────────────────────────────────────────────────────
function EquityCurve({ series }) {
  const data = useMemo(() => {
    if (!series || series.length === 0) return [];
    return series.map(s => ({
      date: String(s.snapshot_date || '').slice(5, 10),
      value: Number(s.total_portfolio_value || 0),
    })).filter(d => d.value > 0);
  }, [series]);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Equity Curve</div>
          <div className="card-sub">Portfolio value · daily snapshots</div>
        </div>
      </div>
      <div className="card-body">
        {data.length < 2 ? (
          <Empty title="Equity curve building" desc={`${data.length} snapshot${data.length === 1 ? '' : 's'} — need 2+ for a curve.`} />
        ) : (
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--brand)" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="var(--brand)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                <XAxis dataKey="date" stroke="var(--text-3)" fontSize={11} tickLine={false} />
                <YAxis stroke="var(--text-3)" fontSize={11} tickLine={false}
                       tickFormatter={fmtMoneyShort} width={64} />
                <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [fmtMoney(v), 'Value']} />
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

// ─── Drawdown chart ────────────────────────────────────────────────────────
function DrawdownChart({ series }) {
  const data = useMemo(() => {
    if (!series || series.length === 0) return [];
    let peak = 0;
    return series.map(s => {
      const v = Number(s.total_portfolio_value || 0);
      if (v <= 0) return null;
      peak = Math.max(peak, v);
      const dd = peak > 0 ? -((peak - v) / peak) * 100 : 0;
      return { date: String(s.snapshot_date || '').slice(5, 10), dd: Number(dd.toFixed(2)) };
    }).filter(Boolean);
  }, [series]);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Drawdown</div>
          <div className="card-sub">% drawdown from peak (lower = deeper)</div>
        </div>
      </div>
      <div className="card-body">
        {data.length < 2 ? (
          <Empty title="Drawdown building" desc="Need 2+ snapshots to compute drawdown." />
        ) : (
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--danger)" stopOpacity={0} />
                    <stop offset="100%" stopColor="var(--danger)" stopOpacity={0.5} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                <XAxis dataKey="date" stroke="var(--text-3)" fontSize={11} tickLine={false} />
                <YAxis stroke="var(--text-3)" fontSize={11} tickLine={false}
                       tickFormatter={(v) => `${v}%`} width={50} />
                <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [`${v}%`, 'Drawdown']} />
                <ReferenceLine y={0} stroke="var(--border)" />
                <Area type="monotone" dataKey="dd" stroke="var(--danger)" strokeWidth={1.5}
                      fill="url(#ddGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Daily-return histogram (bell-curve overlay style) ─────────────────────
function DailyReturnHistogram({ series }) {
  const { buckets, stats } = useMemo(() => {
    if (!series || series.length === 0) return { buckets: [], stats: null };
    const last90 = series.slice(-90);
    const returns = last90
      .map(s => Number(s.daily_return_pct || 0))
      .filter(r => Number.isFinite(r));
    if (returns.length === 0) return { buckets: [], stats: null };
    const lo = Math.min(...returns);
    const hi = Math.max(...returns);
    const span = Math.max(0.5, hi - lo);
    const bins = 12;
    const step = span / bins;
    const arr = Array.from({ length: bins }, (_, i) => ({
      mid: Number((lo + step * (i + 0.5)).toFixed(2)),
      count: 0,
    }));
    for (const r of returns) {
      let idx = Math.floor((r - lo) / step);
      if (idx >= bins) idx = bins - 1;
      if (idx < 0) idx = 0;
      arr[idx].count += 1;
    }
    const mean = returns.reduce((a, b) => a + b, 0) / returns.length;
    const variance = returns.reduce((s, r) => s + (r - mean) ** 2, 0) / returns.length;
    const std = Math.sqrt(variance);
    return { buckets: arr, stats: { mean, std, n: returns.length } };
  }, [series]);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Daily Return Distribution</div>
          <div className="card-sub">
            {stats
              ? `${stats.n} sessions · mean ${stats.mean.toFixed(2)}% · σ ${stats.std.toFixed(2)}%`
              : 'Last 90 days'}
          </div>
        </div>
      </div>
      <div className="card-body">
        {buckets.length === 0 ? (
          <Empty title="No daily-return data yet" />
        ) : (
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={buckets} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                <XAxis dataKey="mid" stroke="var(--text-3)" fontSize={11} tickLine={false}
                       tickFormatter={(v) => `${v}%`} />
                <YAxis stroke="var(--text-3)" fontSize={11} tickLine={false} allowDecimals={false} width={32} />
                <Tooltip contentStyle={TOOLTIP_STYLE}
                  formatter={(v) => [v, 'Sessions']}
                  labelFormatter={(l) => `${l}%`} />
                <ReferenceLine x={0} stroke="var(--border)" strokeDasharray="2 4" />
                <Bar dataKey="count">
                  {buckets.map((b, i) => (
                    <Cell key={i} fill={b.mid >= 0 ? 'var(--success)' : 'var(--danger)'} fillOpacity={0.85} />
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
          <div className="card-sub">R-multiples across closed trades</div>
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
                      fill={b.min >= 0 ? 'var(--success)' : 'var(--danger)'} fillOpacity={0.85} />
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

// ─── Holding period histogram ──────────────────────────────────────────────
function HoldingPeriodHistogram({ trades }) {
  const buckets = useMemo(() => {
    if (!trades || trades.length === 0) return [];
    const bins = [
      { range: '0-3d', min: 0, max: 4, count: 0 },
      { range: '4-7d', min: 4, max: 8, count: 0 },
      { range: '8-14d', min: 8, max: 15, count: 0 },
      { range: '15-30d', min: 15, max: 31, count: 0 },
      { range: '31-60d', min: 31, max: 61, count: 0 },
      { range: '60d+', min: 61, max: Infinity, count: 0 },
    ];
    for (const t of trades) {
      const d = Number(t.trade_duration_days);
      if (!Number.isFinite(d)) continue;
      const b = bins.find(x => d >= x.min && d < x.max);
      if (b) b.count += 1;
    }
    return bins;
  }, [trades]);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Holding Period Distribution</div>
          <div className="card-sub">Days held per closed trade</div>
        </div>
      </div>
      <div className="card-body">
        {buckets.length === 0 ? (
          <Empty title="No closed trades yet" />
        ) : (
          <div style={{ height: 240 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={buckets} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                <XAxis dataKey="range" stroke="var(--text-3)" fontSize={11} tickLine={false} />
                <YAxis stroke="var(--text-3)" fontSize={11} tickLine={false} allowDecimals={false} width={32} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="count" fill="var(--cyan)" fillOpacity={0.85} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── R-multiple ladder per position ────────────────────────────────────────
function RLadderPanel({ positions, loading, onSelect }) {
  const ladders = useMemo(() => {
    if (!positions) return [];
    return positions
      .filter(p => p.avg_entry_price && p.current_price && p.stop_loss_price)
      .map(p => {
        const entry = p.avg_entry_price;
        const cur = p.current_price;
        const stop = p.stop_loss_price;
        const t1 = p.target_1_price;
        const t2 = p.target_2_price;
        const t3 = p.target_3_price;

        const lo = Math.min(stop, entry, cur);
        const hi = Math.max(t3 || t2 || t1 || entry, cur);
        const span = Math.max(0.0001, hi - lo);
        const pos = (price) => ((price - lo) / span) * 100;

        return {
          symbol: p.symbol,
          r_multiple: p.r_multiple,
          entry, cur, stop, t1, t2, t3,
          unrealized_pnl_pct: p.unrealized_pnl_pct,
          pStop: pos(stop),
          pEntry: pos(entry),
          pCur: pos(cur),
          pT1: t1 ? pos(t1) : null,
          pT2: t2 ? pos(t2) : null,
          pT3: t3 ? pos(t3) : null,
        };
      });
  }, [positions]);

  return (
    <div className="card" style={{ marginTop: 'var(--space-4)' }}>
      <div className="card-head">
        <div>
          <div className="card-title">R-Multiple Ladder</div>
          <div className="card-sub">Stop · entry · current · T1/T2/T3 per open position</div>
        </div>
      </div>
      <div className="card-body">
        {loading ? (
          <Empty title="Loading…" />
        ) : ladders.length === 0 ? (
          <Empty title="No open positions with stop/target levels"
                 desc="Stops & targets are populated by the orchestrator at entry time." />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            {ladders.map((l, i) => (
              <div key={i} onClick={() => onSelect(l.symbol)}
                   style={{ cursor: 'pointer' }}>
                <div className="flex items-center justify-between" style={{ marginBottom: 'var(--space-2)' }}>
                  <div className="flex items-center" style={{ gap: 'var(--space-3)' }}>
                    <span className="strong" style={{ fontWeight: 'var(--w-bold)', fontSize: 'var(--t-md)' }}>
                      {l.symbol}
                    </span>
                    <RChip r={l.r_multiple} />
                    <Pnl value={l.unrealized_pnl_pct} suffix="%" />
                  </div>
                  <div className="t-xs muted mono tnum">
                    Stop {fmtMoney(l.stop)} · Entry {fmtMoney(l.entry)} · Now {fmtMoney(l.cur)}
                  </div>
                </div>
                <div style={{ position: 'relative', height: 28, background: 'var(--surface-2)',
                              borderRadius: 'var(--r-pill)', overflow: 'visible',
                              border: '1px solid var(--border-soft)' }}>
                  {/* Filled track from stop to current (or stop to entry if underwater) */}
                  <div style={{
                    position: 'absolute', top: 0, bottom: 0,
                    left: `${Math.min(l.pStop, l.pCur)}%`,
                    width: `${Math.max(0, Math.abs(l.pCur - l.pStop))}%`,
                    background: l.pCur >= l.pEntry
                      ? 'linear-gradient(90deg, var(--danger) 0%, var(--amber) 50%, var(--success) 100%)'
                      : 'linear-gradient(90deg, var(--danger) 0%, var(--amber) 100%)',
                    opacity: 0.35,
                    borderRadius: 'var(--r-pill)',
                  }} />
                  <Marker pct={l.pStop} color="var(--danger)" label="S" />
                  <Marker pct={l.pEntry} color="var(--text-2)" label="E" />
                  {l.pT1 != null && <Marker pct={l.pT1} color="var(--cyan)" label="T1" />}
                  {l.pT2 != null && <Marker pct={l.pT2} color="var(--purple)" label="T2" />}
                  {l.pT3 != null && <Marker pct={l.pT3} color="var(--success)" label="T3" />}
                  <Marker pct={l.pCur} color="var(--brand)" label="◆" big />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Marker({ pct, color, label, big = false }) {
  return (
    <div style={{
      position: 'absolute', top: -4, bottom: -4,
      left: `${pct}%`, transform: 'translateX(-50%)',
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      pointerEvents: 'none',
    }}>
      <div style={{
        width: big ? 4 : 2, flex: 1, background: color,
        borderRadius: 'var(--r-pill)',
        boxShadow: big ? `0 0 4px ${color}` : 'none',
      }} />
      <div className="mono tnum" style={{
        fontSize: 'var(--t-2xs)', color, fontWeight: 'var(--w-bold)',
        marginTop: 2, lineHeight: 1, whiteSpace: 'nowrap',
      }}>{label}</div>
    </div>
  );
}

function RChip({ r }) {
  if (r == null) return <span className="badge" style={{ fontSize: 'var(--t-2xs)' }}>—</span>;
  const cls = r >= 1 ? 'badge-success' : r >= 0 ? 'badge-cyan' : r >= -0.5 ? 'badge-amber' : 'badge-danger';
  const sign = r > 0 ? '+' : '';
  return (
    <span className={`badge ${cls} mono tnum`} style={{ fontSize: 'var(--t-2xs)' }}>
      {sign}{r.toFixed(2)}R
    </span>
  );
}

// ─── Risk allocation pie ───────────────────────────────────────────────────
function RiskAllocationPie({ positions, totalValue, onSelect }) {
  const data = useMemo(() => {
    if (!positions) return [];
    return positions
      .map(p => ({
        symbol: p.symbol,
        risk: Number(p.open_risk_dollars) || 0,
      }))
      .filter(d => d.risk > 0)
      .sort((a, b) => b.risk - a.risk);
  }, [positions]);
  const totalRisk = data.reduce((s, d) => s + d.risk, 0);
  const riskPct = totalValue > 0 ? (totalRisk / totalValue) * 100 : 0;

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Open Risk Allocation</div>
          <div className="card-sub">
            {data.length === 0 ? 'No positions with stops'
              : `${fmtMoneyShort(totalRisk)} at risk · ${riskPct.toFixed(2)}% of portfolio`}
          </div>
        </div>
      </div>
      <div className="card-body">
        {data.length === 0 ? (
          <Empty title="No risk data" desc="Positions need stop levels." />
        ) : (
          <div style={{ height: 240 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={data} dataKey="risk" nameKey="symbol"
                     cx="50%" cy="50%" innerRadius={50} outerRadius={90}
                     onClick={(d) => d?.symbol && onSelect(d.symbol)}
                     paddingAngle={2}>
                  {data.map((_, i) => (
                    <Cell key={i} fill={PIE_PALETTE[i % PIE_PALETTE.length]}
                          style={{ cursor: 'pointer' }} />
                  ))}
                </Pie>
                <Tooltip contentStyle={TOOLTIP_STYLE}
                  formatter={(v, n) => [fmtMoney(v), n]} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Sector concentration bar chart ────────────────────────────────────────
function SectorConcentration({ positions, totalValue }) {
  const data = useMemo(() => {
    if (!positions || totalValue <= 0) return [];
    const byS = {};
    for (const p of positions) {
      const s = p.sector || 'Unknown';
      byS[s] = (byS[s] || 0) + Number(p.position_value || 0);
    }
    return Object.entries(byS)
      .map(([sector, value]) => ({ sector, value, pct: (value / totalValue) * 100 }))
      .sort((a, b) => b.pct - a.pct);
  }, [positions, totalValue]);
  const overweight = data.find(d => d.pct > 30);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Sector Concentration</div>
          <div className="card-sub">
            {overweight ? `Heavy in ${overweight.sector} (${overweight.pct.toFixed(1)}%)`
                        : 'Diversified across sectors'}
          </div>
        </div>
      </div>
      <div className="card-body">
        {data.length === 0 ? (
          <Empty title="No sector data" />
        ) : (
          <div style={{ height: 240 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} layout="vertical"
                        margin={{ top: 4, right: 16, left: 4, bottom: 0 }}>
                <CartesianGrid stroke="var(--border-soft)" strokeDasharray="2 4" />
                <XAxis type="number" stroke="var(--text-3)" fontSize={11}
                       tickFormatter={(v) => `${v.toFixed(0)}%`} />
                <YAxis type="category" dataKey="sector" stroke="var(--text-3)"
                       fontSize={11} width={110} />
                <Tooltip contentStyle={TOOLTIP_STYLE}
                  formatter={(v) => [`${v.toFixed(1)}%`, 'Allocation']} />
                <Bar dataKey="pct" radius={[0, 4, 4, 0]}>
                  {data.map((d, i) => (
                    <Cell key={i} fill={d.pct > 30 ? 'var(--danger)' : 'var(--brand)'} />
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

// ─── Stage phase donut ─────────────────────────────────────────────────────
function StagePhaseDonut({ positions }) {
  const data = useMemo(() => {
    if (!positions) return [];
    const labelFor = (p) => {
      const stage = p.weinstein_stage;
      const score = p.minervini_trend_score;
      if (stage === 1) return 'Stage 1 (base)';
      if (stage === 2) {
        if (score != null && score >= 8) return 'Late Stage-2';
        if (score != null && score >= 6) return 'Mid Stage-2';
        return 'Early Stage-2';
      }
      if (stage === 3) return 'Stage 3 (top)';
      if (stage === 4) return 'Stage 4 (down)';
      return 'Unknown';
    };
    const counts = {};
    for (const p of positions) {
      const k = labelFor(p);
      counts[k] = (counts[k] || 0) + 1;
    }
    const order = ['Early Stage-2', 'Mid Stage-2', 'Late Stage-2',
                   'Stage 1 (base)', 'Stage 3 (top)', 'Stage 4 (down)', 'Unknown'];
    return order
      .filter(k => counts[k])
      .map(k => ({ phase: k, count: counts[k] }));
  }, [positions]);

  const colorFor = (p) => {
    if (p.startsWith('Early')) return 'var(--success)';
    if (p.startsWith('Mid')) return 'var(--cyan)';
    if (p.startsWith('Late')) return 'var(--amber)';
    if (p.startsWith('Stage 1')) return 'var(--brand)';
    if (p.startsWith('Stage 3')) return 'var(--purple)';
    if (p.startsWith('Stage 4')) return 'var(--danger)';
    return 'var(--text-3)';
  };

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">Stage Phase Distribution</div>
          <div className="card-sub">Where holdings sit in the Weinstein cycle</div>
        </div>
      </div>
      <div className="card-body">
        {data.length === 0 ? (
          <Empty title="No stage data" desc="Positions need trend_template_data coverage." />
        ) : (
          <div style={{ height: 240 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={data} dataKey="count" nameKey="phase"
                     cx="50%" cy="50%" innerRadius={50} outerRadius={90} paddingAngle={2}>
                  {data.map((d, i) => (
                    <Cell key={i} fill={colorFor(d.phase)} />
                  ))}
                </Pie>
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Position health table ─────────────────────────────────────────────────
function PositionHealthTable({ positions, loading, onSelect }) {
  return (
    <div className="card" style={{ marginTop: 'var(--space-4)' }}>
      <div className="card-head">
        <div>
          <div className="card-title">Position Health ({positions?.length || 0})</div>
          <div className="card-sub">Days held · R · stop/target distance · trend posture · sector</div>
        </div>
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        {loading ? (
          <Empty title="Loading…" />
        ) : !positions || positions.length === 0 ? (
          <Empty title="No open positions" />
        ) : (
          <div style={{ overflow: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Sector</th>
                  <th className="num">Days</th>
                  <th className="num">R</th>
                  <th className="num">P&L %</th>
                  <th className="num">→ Stop</th>
                  <th className="num">→ T1</th>
                  <th className="num">→ T2</th>
                  <th className="num">→ T3</th>
                  <th>Stage</th>
                  <th className="num">Trend</th>
                  <th className="num">% from low</th>
                  <th>Exit Plan</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p, i) => (
                  <tr key={i}
                      onClick={() => onSelect(p.symbol)}
                      style={{ cursor: 'pointer' }}>
                    <td><span className="strong" style={{ fontWeight: 'var(--w-bold)' }}>{p.symbol}</span></td>
                    <td className="t-xs muted">{p.sector || '—'}</td>
                    <td className="num mono tnum muted">{p.days_since_entry ?? '—'}</td>
                    <td className="num"><RChip r={p.r_multiple} /></td>
                    <td className="num"><Pnl value={p.unrealized_pnl_pct} suffix="%" /></td>
                    <td className="num mono tnum down">
                      {p.distance_to_stop_pct != null ? `-${num(p.distance_to_stop_pct, 1)}%` : '—'}
                    </td>
                    <td className="num mono tnum">
                      {p.distance_to_t1_pct != null ? `+${num(p.distance_to_t1_pct, 1)}%` : '—'}
                    </td>
                    <td className="num mono tnum">
                      {p.distance_to_t2_pct != null ? `+${num(p.distance_to_t2_pct, 1)}%` : '—'}
                    </td>
                    <td className="num mono tnum">
                      {p.distance_to_t3_pct != null ? `+${num(p.distance_to_t3_pct, 1)}%` : '—'}
                    </td>
                    <td>
                      {p.weinstein_stage != null
                        ? <span className="badge mono">S{p.weinstein_stage}</span>
                        : <span className="muted">—</span>}
                    </td>
                    <td className="num mono tnum">
                      {p.minervini_trend_score != null ? `${p.minervini_trend_score}/8` : '—'}
                    </td>
                    <td className="num mono tnum">
                      {p.pct_from_52w_low != null ? `+${num(p.pct_from_52w_low, 0)}%` : '—'}
                    </td>
                    <td>
                      <span className="badge" style={{ textTransform: 'uppercase', fontSize: 'var(--t-2xs)' }}>
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
