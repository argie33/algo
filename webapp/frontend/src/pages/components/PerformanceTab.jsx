import React from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, ResponsiveContainer,
  Tooltip as RechartTooltip, ReferenceLine
} from 'recharts';

const TOOLTIP_STYLE = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--r-sm)',
  fontSize: 'var(--t-xs)',
  padding: 'var(--space-2) var(--space-3)',
};

function PerfCard({ label, value, color, hint }) {
  return (
    <div style={{
      padding: 'var(--space-3)',
      background: 'var(--surface-2)',
      border: '1px solid var(--border)',
      borderLeft: `4px solid ${color || 'var(--brand)'}`,
      borderRadius: 'var(--r-md)',
    }}>
      <div className="t-2xs muted strong">{label}</div>
      <div className="mono tnum" style={{ fontSize: 'var(--t-lg)', fontWeight: 'var(--w-bold)', color: color || 'var(--text-2)', marginTop: 4 }}>
        {value}
      </div>
      {hint && <div className="t-2xs muted" style={{ marginTop: 4 }}>{hint}</div>}
    </div>
  );
}

export default function PerformanceTab({ performance, equityCurve = [] }) {
  const p = performance;
  const numColor = (n, threshold = 0) => (n > threshold ? 'var(--success)' : n < threshold ? 'var(--danger)' : 'var(--text-muted)');

  const drawdownData = React.useMemo(() => {
    if (!equityCurve.length) return [];
    let peak = 0;
    return equityCurve.map(pt => {
      peak = Math.max(peak, pt.total_portfolio_value);
      const dd = peak > 0 ? -((peak - pt.total_portfolio_value) / peak * 100) : 0;
      return { date: pt.snapshot_date, drawdown: Math.round(dd * 100) / 100 };
    });
  }, [equityCurve]);

  const monthlyReturns = React.useMemo(() => {
    if (!equityCurve.length) return [];
    const byMonth = {};
    equityCurve.forEach(pt => {
      const d = new Date(pt.snapshot_date);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
      if (!byMonth[key]) byMonth[key] = { key, label: d.toLocaleDateString('default', { month: 'short', year: '2-digit' }), total: 0 };
      byMonth[key].total += pt.daily_return_pct || 0;
    });
    return Object.values(byMonth).slice(-12);
  }, [equityCurve]);

  const chartFmt = (v) => `$${(v / 1000).toFixed(0)}k`;
  const startValue = equityCurve[0]?.total_portfolio_value;
  const endValue = equityCurve[equityCurve.length - 1]?.total_portfolio_value;
  const totalReturn = startValue > 0 ? ((endValue - startValue) / startValue * 100).toFixed(1) : null;

  return (
    <div style={{ padding: 'var(--space-4)' }}>
      {equityCurve.length > 1 && (
        <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
          <div className="card-head">
            <div className="card-title">
              Equity Curve {totalReturn != null && <span className="muted t-xs" style={{ fontWeight: 'normal', marginLeft: 8 }}>·  {totalReturn >= 0 ? '+' : ''}{totalReturn}% total return</span>}
            </div>
          </div>
          <div className="card-body">
            <div style={{ height: 220 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={equityCurve} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--brand)" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="var(--brand)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-soft)" />
                  <XAxis dataKey="snapshot_date" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} tickFormatter={v => v?.slice(5)} interval="preserveStartEnd" />
                  <YAxis tickFormatter={chartFmt} tick={{ fill: 'var(--text-muted)', fontSize: 10 }} width={48} />
                  <RechartTooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [`$${v?.toLocaleString()}`, 'Portfolio']} labelFormatter={v => v} />
                  <Area type="monotone" dataKey="total_portfolio_value" stroke="var(--brand)" fill="url(#eqGrad)" strokeWidth={2} dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {drawdownData.length > 1 && (
        <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
          <div className="card-head">
            <div className="card-title">Drawdown From Peak</div>
          </div>
          <div className="card-body">
            <div style={{ height: 140 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={drawdownData} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--danger)" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="var(--danger)" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-soft)" />
                  <XAxis dataKey="date" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} tickFormatter={v => v?.slice(5)} interval="preserveStartEnd" />
                  <YAxis tickFormatter={v => `${v}%`} tick={{ fill: 'var(--text-muted)', fontSize: 10 }} width={40} />
                  <ReferenceLine y={0} stroke="var(--border)" />
                  <RechartTooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [`${v}%`, 'Drawdown']} />
                  <Area type="monotone" dataKey="drawdown" stroke="var(--danger)" fill="url(#ddGrad)" strokeWidth={1.5} dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {monthlyReturns.length > 0 && (
        <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
          <div className="card-head">
            <div className="card-title">Monthly Returns (Last 12 Months)</div>
          </div>
          <div className="card-body">
            <div className="flex gap-2" style={{ flexWrap: 'wrap' }}>
              {monthlyReturns.map(m => {
                const pct = Math.round(m.total * 10) / 10;
                const bg = pct > 5 ? 'rgba(34, 197, 94, 0.15)' : pct > 0 ? 'rgba(34, 197, 94, 0.08)' : pct > -5 ? 'rgba(234, 88, 12, 0.08)' : 'rgba(225, 29, 72, 0.15)';
                const col = pct > 0 ? 'var(--success)' : 'var(--danger)';
                return (
                  <div key={m.key} style={{
                    padding: 'var(--space-3)',
                    background: bg,
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--r-md)',
                    minWidth: 72,
                    textAlign: 'center',
                  }}>
                    <div className="t-2xs muted">{m.label}</div>
                    <div className="mono tnum" style={{ color: col, fontWeight: 'var(--w-bold)', fontSize: 'var(--t-base)', marginTop: 4 }}>
                      {pct >= 0 ? '+' : ''}{pct}%
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {!performance && (
        <div className="alert alert-info" style={{ marginBottom: 'var(--space-4)' }}>
          No performance data — needs closed trades + portfolio snapshots
        </div>
      )}

      {performance && <>
        <div className="eyebrow" style={{ marginBottom: 'var(--space-3)' }}>Trade Statistics</div>
        <div className="grid grid-4" style={{ gap: 'var(--space-3)', marginBottom: 'var(--space-6)' }}>
          <PerfCard label="Total Trades" value={p.total_trades} hint={`${p.winning_trades}W / ${p.losing_trades}L`} />
          <PerfCard label="Win Rate" value={`${p.win_rate_pct}%`} color={numColor(p.win_rate_pct, 50)} hint="of closed trades" />
          <PerfCard label="Expectancy" value={`${p.expectancy_r >= 0 ? '+' : ''}${p.expectancy_r}R`} color={numColor(p.expectancy_r)} hint="per trade" />
          <PerfCard label="Profit Factor" value={p.profit_factor || '∞'} color={numColor((p.profit_factor || 0) - 1)} hint="gross win / gross loss" />
          <PerfCard label="Avg Win" value={`${p.avg_win_r >= 0 ? '+' : ''}${p.avg_win_r}R`} color="var(--success)" hint={`${p.avg_win_pct}%`} />
          <PerfCard label="Avg Loss" value={`${p.avg_loss_r}R`} color="var(--danger)" hint={`${p.avg_loss_pct}%`} />
          <PerfCard label="Avg Hold" value={`${p.avg_hold_days}d`} hint="days per trade" />
          <PerfCard label="Total P&L" value={`$${(p.total_pnl_dollars || 0).toLocaleString()}`} color={numColor(p.total_pnl_dollars)} />
        </div>

        <div className="eyebrow" style={{ marginBottom: 'var(--space-3)' }}>Risk-Adjusted Returns (Annualized)</div>
        <div className="grid grid-4" style={{ gap: 'var(--space-3)', marginBottom: 'var(--space-6)' }}>
          <PerfCard label="Sharpe Ratio" value={p.sharpe_annualized} color={numColor(p.sharpe_annualized - 1)} hint="(>1 good, >2 great)" />
          <PerfCard label="Sortino Ratio" value={p.sortino_annualized} color={numColor(p.sortino_annualized - 1)} hint="downside-only volatility" />
          <PerfCard label="Max Drawdown" value={`${p.max_drawdown_pct}%`} color={p.max_drawdown_pct > 20 ? 'var(--danger)' : p.max_drawdown_pct > 10 ? 'var(--amber)' : 'var(--success)'} hint="peak-to-trough" />
          <PerfCard label="Calmar Ratio" value={p.calmar_ratio} color={numColor(p.calmar_ratio - 1)} hint="return / max DD" />
        </div>

        <div className="eyebrow" style={{ marginBottom: 'var(--space-3)' }}>Streaks</div>
        <div className="grid grid-4" style={{ gap: 'var(--space-3)' }}>
          <PerfCard label="Current Streak" value={p.current_streak >= 0 ? `+${p.current_streak} W` : `${Math.abs(p.current_streak)} L`} color={p.current_streak >= 0 ? 'var(--success)' : 'var(--danger)'} />
          <PerfCard label="Best Win Streak" value={p.best_win_streak} color="var(--success)" />
          <PerfCard label="Worst Loss Streak" value={p.worst_loss_streak} color="var(--danger)" />
          <PerfCard label="Sample Size" value={`${p.portfolio_snapshots} snapshots`} hint={p.portfolio_snapshots < 30 ? '(too few for solid stats)' : ''} />
        </div>
      </>}
    </div>
  );
}
