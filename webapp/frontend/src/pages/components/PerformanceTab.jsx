import React from 'react';
import { Box, Typography, Grid, Alert } from '@mui/material';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, ResponsiveContainer,
  Tooltip as RechartTooltip, ReferenceLine
} from 'recharts';

// Color scheme
const C = {
  card: '#1a1f3a',
  cardAlt: '#232838',
  border: '#2a2f42',
  text: '#e8eaf4',
  textBright: '#f5f7ff',
  textDim: '#8891b0',
  textFaint: '#6b7a99',
  blue: '#5b6ef5',
  greenDark: '#0e2a18',
  green: '#22c55e',
  redDark: '#3a1414',
  red: '#ef4444',
  yellow: '#f59e0b',
};

function SectionCard({ title, children, sx }) {
  return (
    <Box sx={{ bgcolor: C.cardAlt, border: `1px solid ${C.border}`, borderRadius: 1, p: 2, ...sx }}>
      {title && <Typography variant="h6" sx={{ color: C.textBright, mb: 2 }}>{title}</Typography>}
      {children}
    </Box>
  );
}

function PerfCard({ label, value, color, hint }) {
  return (
    <Box sx={{
      p: 2, bgcolor: C.cardAlt, border: `1px solid ${C.border}`, borderRadius: 1,
      borderLeft: `4px solid ${color || C.blue}`,
    }}>
      <Typography variant="caption" sx={{ color: C.textDim, fontSize: '0.65rem', letterSpacing: 1.2, fontWeight: 600 }}>
        {label}
      </Typography>
      <Typography variant="h5" sx={{
        color: color || C.textBright, fontFamily: 'monospace', fontWeight: 700, lineHeight: 1.2,
      }}>
        {value}
      </Typography>
      {hint && <Typography variant="caption" sx={{ color: C.textDim, fontSize: '0.7rem' }}>{hint}</Typography>}
    </Box>
  );
}

export default function PerformanceTab({ performance, equityCurve = [] }) {
  const p = performance;
  const numColor = (n, threshold = 0) => (n > threshold ? C.green : n < threshold ? C.red : C.textDim);

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
    <Box sx={{ p: 2 }}>
      {equityCurve.length > 1 && (
        <SectionCard title={`EQUITY CURVE${totalReturn != null ? `  ·  ${totalReturn >= 0 ? '+' : ''}${totalReturn}% total return` : ''}`} sx={{ mb: 2 }}>
          <Box sx={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={equityCurve} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={C.blue} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={C.blue} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={C.border} />
                <XAxis dataKey="snapshot_date" tick={{ fill: C.textDim, fontSize: 10 }} tickFormatter={v => v?.slice(5)} interval="preserveStartEnd" />
                <YAxis tickFormatter={chartFmt} tick={{ fill: C.textDim, fontSize: 10 }} width={48} />
                <RechartTooltip contentStyle={{ background: C.card, border: `1px solid ${C.border}`, color: C.text, fontSize: 11 }} formatter={(v) => [`$${v?.toLocaleString()}`, 'Portfolio']} labelFormatter={v => v} />
                <Area type="monotone" dataKey="total_portfolio_value" stroke={C.blue} fill="url(#eqGrad)" strokeWidth={2} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </Box>
        </SectionCard>
      )}

      {drawdownData.length > 1 && (
        <SectionCard title="DRAWDOWN FROM PEAK" sx={{ mb: 2 }}>
          <Box sx={{ height: 140 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={drawdownData} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={C.red} stopOpacity={0.4} />
                    <stop offset="95%" stopColor={C.red} stopOpacity={0.05} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={C.border} />
                <XAxis dataKey="date" tick={{ fill: C.textDim, fontSize: 10 }} tickFormatter={v => v?.slice(5)} interval="preserveStartEnd" />
                <YAxis tickFormatter={v => `${v}%`} tick={{ fill: C.textDim, fontSize: 10 }} width={40} />
                <ReferenceLine y={0} stroke={C.border} />
                <RechartTooltip contentStyle={{ background: C.card, border: `1px solid ${C.border}`, color: C.text, fontSize: 11 }} formatter={(v) => [`${v}%`, 'Drawdown']} />
                <Area type="monotone" dataKey="drawdown" stroke={C.red} fill="url(#ddGrad)" strokeWidth={1.5} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </Box>
        </SectionCard>
      )}

      {monthlyReturns.length > 0 && (
        <SectionCard title="MONTHLY RETURNS (last 12 months)" sx={{ mb: 2 }}>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            {monthlyReturns.map(m => {
              const pct = Math.round(m.total * 10) / 10;
              const bg = pct > 5 ? C.greenDark : pct > 0 ? '#1a3a20' : pct > -5 ? '#3a1414' : C.redDark;
              const col = pct > 0 ? C.green : C.red;
              return (
                <Box key={m.key} sx={{ p: 1.5, borderRadius: 1, bgcolor: bg, border: `1px solid ${C.border}`, minWidth: 72, textAlign: 'center' }}>
                  <Typography variant="caption" sx={{ color: C.textDim, fontSize: '0.65rem', display: 'block' }}>
                    {m.label}
                  </Typography>
                  <Typography sx={{ color: col, fontFamily: 'monospace', fontWeight: 700, fontSize: '1rem' }}>
                    {pct >= 0 ? '+' : ''}{pct}%
                  </Typography>
                </Box>
              );
            })}
          </Box>
        </SectionCard>
      )}

      {!performance && (
        <Alert severity="info" sx={{ bgcolor: C.cardAlt, color: C.text, mb: 2 }}>
          No performance data — needs closed trades + portfolio snapshots
        </Alert>
      )}

      {performance && <>
        <Typography variant="h6" sx={{ color: C.textBright, mb: 2 }}>Trade Statistics</Typography>
        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid item xs={6} sm={3}><PerfCard label="TOTAL TRADES" value={p.total_trades} hint={`${p.winning_trades}W / ${p.losing_trades}L`} /></Grid>
          <Grid item xs={6} sm={3}><PerfCard label="WIN RATE" value={`${p.win_rate_pct}%`} color={numColor(p.win_rate_pct, 50)} hint="of closed trades" /></Grid>
          <Grid item xs={6} sm={3}><PerfCard label="EXPECTANCY" value={`${p.expectancy_r >= 0 ? '+' : ''}${p.expectancy_r}R`} color={numColor(p.expectancy_r)} hint="per trade" /></Grid>
          <Grid item xs={6} sm={3}><PerfCard label="PROFIT FACTOR" value={p.profit_factor || '∞'} color={numColor((p.profit_factor || 0) - 1)} hint="gross win / gross loss" /></Grid>
          <Grid item xs={6} sm={3}><PerfCard label="AVG WIN" value={`${p.avg_win_r >= 0 ? '+' : ''}${p.avg_win_r}R`} color={C.green} hint={`${p.avg_win_pct}%`} /></Grid>
          <Grid item xs={6} sm={3}><PerfCard label="AVG LOSS" value={`${p.avg_loss_r}R`} color={C.red} hint={`${p.avg_loss_pct}%`} /></Grid>
          <Grid item xs={6} sm={3}><PerfCard label="AVG HOLD" value={`${p.avg_hold_days}d`} hint="days per trade" /></Grid>
          <Grid item xs={6} sm={3}><PerfCard label="TOTAL P&L" value={`$${(p.total_pnl_dollars || 0).toLocaleString()}`} color={numColor(p.total_pnl_dollars)} /></Grid>
        </Grid>

        <Typography variant="h6" sx={{ color: C.textBright, mb: 2 }}>Risk-Adjusted Returns (annualized)</Typography>
        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid item xs={6} sm={3}><PerfCard label="SHARPE RATIO" value={p.sharpe_annualized} color={numColor(p.sharpe_annualized - 1)} hint="(>1 good, >2 great)" /></Grid>
          <Grid item xs={6} sm={3}><PerfCard label="SORTINO RATIO" value={p.sortino_annualized} color={numColor(p.sortino_annualized - 1)} hint="downside-only volatility" /></Grid>
          <Grid item xs={6} sm={3}><PerfCard label="MAX DRAWDOWN" value={`${p.max_drawdown_pct}%`} color={p.max_drawdown_pct > 20 ? C.red : p.max_drawdown_pct > 10 ? C.yellow : C.green} hint="peak-to-trough" /></Grid>
          <Grid item xs={6} sm={3}><PerfCard label="CALMAR RATIO" value={p.calmar_ratio} color={numColor(p.calmar_ratio - 1)} hint="return / max DD" /></Grid>
        </Grid>

        <Typography variant="h6" sx={{ color: C.textBright, mb: 2 }}>Streaks</Typography>
        <Grid container spacing={2}>
          <Grid item xs={6} sm={3}><PerfCard label="CURRENT STREAK" value={p.current_streak >= 0 ? `+${p.current_streak} W` : `${Math.abs(p.current_streak)} L`} color={p.current_streak >= 0 ? C.green : C.red} /></Grid>
          <Grid item xs={6} sm={3}><PerfCard label="BEST WIN STREAK" value={p.best_win_streak} color={C.green} /></Grid>
          <Grid item xs={6} sm={3}><PerfCard label="WORST LOSS STREAK" value={p.worst_loss_streak} color={C.red} /></Grid>
          <Grid item xs={6} sm={3}><PerfCard label="SAMPLE SIZE" value={`${p.portfolio_snapshots} snapshots`} hint={p.portfolio_snapshots < 30 ? '(too few for solid stats)' : ''} /></Grid>
        </Grid>
      </>}
    </Box>
  );
}
