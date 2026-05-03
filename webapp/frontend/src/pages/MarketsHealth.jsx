/**
 * Markets Health — flagship page (market-level only).
 *
 * Section order (top to bottom):
 *   1. Regime banner — exposure %, tier, risk multiplier, halt status
 *   2. Indices grid — SPY / QQQ / IWM / DIA last + change + sparklines
 *   3. 9-factor exposure composite — bars w/ value, max, sub-detail
 *   4. Exposure history — 90-day line chart with regime bands
 *   5. Distribution days — recent 25-day stack
 *   6. Breadth time series — % > 50DMA, % > 200DMA, McClellan
 *   7. New highs / lows — 60-day net chart
 *   8. AAII sentiment — bull/bear/neutral 8-week
 *   9. VIX regime — last 90 days
 *
 * No sectors here — sectors live on /app/sectors.
 */

import React, { useEffect, useState } from 'react';
import {
  Box, Grid, Stack, CircularProgress, Alert, Chip, IconButton, Tooltip,
} from '@mui/material';
import {
  Refresh as RefreshIcon, ShieldOutlined, Warning,
  TrendingUp as TrendingUpIcon, TrendingDown as TrendingDownIcon,
} from '@mui/icons-material';
import {
  ResponsiveContainer, AreaChart, Area, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, ReferenceLine,
  ReferenceArea, Legend,
} from 'recharts';
import { api } from '../services/api';
import { C, F, S, comp, tierColor, severityColor, fmt$, fmtPct, responsive } from '../theme/algoTheme';
import {
  SectionCard, Stat, FactorBar, PageHeader, SeverityChip, EmptyState,
} from '../components/ui/AlgoUI';

// =============================================================================
// HELPERS
// =============================================================================
const fmtAgo = (ts) => {
  if (!ts) return '—';
  const s = (Date.now() - new Date(ts).getTime()) / 1000;
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};
const num = (v, dp = 2) => v == null ? '—' : Number(v).toFixed(dp);

// =============================================================================
// MAIN PAGE
// =============================================================================
function MarketsHealth() {
  const [data, setData] = useState({ loading: true });
  const fetchAll = async () => {
    try {
      const [marketsR, healthR, indicesR, ddR] = await Promise.all([
        api.get('/algo/markets').catch(() => null),
        api.get('/market/overview').catch(() => null),
        api.get('/market/indices').catch(() => null),
        api.get('/market/distribution-days').catch(() => null),
      ]);
      setData({
        markets: marketsR?.data?.data,
        health: healthR?.data?.data,
        indices: indicesR?.data?.data || indicesR?.data?.items,
        ddHistory: ddR?.data?.data || ddR?.data?.items,
        loading: false,
        ts: new Date(),
      });
    } catch {
      setData(d => ({ ...d, loading: false }));
    }
  };

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, 30000);
    return () => clearInterval(id);
  }, []);

  if (data.loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
        <CircularProgress sx={{ color: C.brand }} />
      </Box>
    );
  }

  const m = data.markets;

  return (
    <Box sx={{ px: responsive.pageX, py: responsive.pageY, maxWidth: 1600, mx: 'auto' }}>
      <PageHeader
        title="Market Health"
        subtitle={`Last refreshed ${fmtAgo(data.ts)} · Auto-refresh 30s`}
        actions={
          <IconButton size="small" onClick={fetchAll}><RefreshIcon /></IconButton>
        }
      />

      {/* === REGIME BANNER === */}
      <RegimeBanner markets={m} />

      {/* === INDICES === */}
      <IndicesStripCard indices={data.indices} />

      <Grid container spacing={2}>
        {/* 9-FACTOR BREAKDOWN */}
        <Grid item xs={12} lg={6}>
          <ExposureBreakdownCard markets={m} />
        </Grid>

        {/* MARKET PULSE (DD count + FTD) */}
        <Grid item xs={12} lg={6}>
          <MarketPulseCard markets={m} />
        </Grid>

        {/* EXPOSURE HISTORY LINE CHART */}
        <Grid item xs={12}>
          <ExposureHistoryChart markets={m} />
        </Grid>

        {/* BREADTH TIME SERIES */}
        <Grid item xs={12} lg={6}>
          <BreadthChart markets={m} health={data.health} />
        </Grid>

        {/* NEW HIGHS - LOWS */}
        <Grid item xs={12} lg={6}>
          <NewHighsLowsChart markets={m} health={data.health} />
        </Grid>

        {/* AAII SENTIMENT */}
        <Grid item xs={12} lg={6}>
          <SentimentChart markets={m} />
        </Grid>

        {/* VIX REGIME */}
        <Grid item xs={12} lg={6}>
          <VixChart markets={m} health={data.health} />
        </Grid>
      </Grid>
    </Box>
  );
}

// =============================================================================
// REGIME BANNER
// =============================================================================
function RegimeBanner({ markets }) {
  if (!markets?.current) {
    return (
      <Alert severity="info" sx={{ mb: 2 }}>
        No market exposure computed yet. Run algo_market_exposure.py to populate.
      </Alert>
    );
  }
  const cur = markets.current;
  const tier = markets.active_tier || {};
  const exposure = cur.exposure_pct;
  const regime = tier.name || cur.regime;

  return (
    <Box sx={{
      mb: 2, p: 3,
      bgcolor: C.card, border: `1px solid ${C.border}`, borderRadius: 1,
      borderLeft: `6px solid ${tierColor(regime)}`,
    }}>
      <Grid container spacing={3} alignItems="center">
        <Grid item xs={12} md={3}>
          <Stack direction="row" alignItems="center" spacing={2}>
            <Box sx={{
              width: 56, height: 56, borderRadius: 2,
              bgcolor: `${tierColor(regime)}20`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <ShieldOutlined sx={{ fontSize: 32, color: tierColor(regime) }} />
            </Box>
            <Box>
              <Box sx={{ fontSize: F.xs, color: C.textDim, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Market Exposure
              </Box>
              <Box sx={{
                fontSize: F.xxxl, fontFamily: F.mono, fontWeight: F.weight.black,
                color: tierColor(regime), lineHeight: 1,
              }}>
                {exposure}<span style={{ fontSize: F.lg }}>%</span>
              </Box>
            </Box>
          </Stack>
        </Grid>
        <Grid item xs={12} md={3}>
          <Stat
            label="Regime Tier"
            value={(regime || 'unknown').replace(/_/g, ' ').toUpperCase()}
            sub={tier.description}
            color={tierColor(regime)}
            mono={false}
          />
        </Grid>
        <Grid item xs={6} md={2}>
          <Stat label="Risk Multiplier" value={`${tier.risk_mult ?? '—'}×`} />
        </Grid>
        <Grid item xs={6} md={2}>
          <Stat label="Max New / Day" value={tier.max_new ?? '—'} />
        </Grid>
        <Grid item xs={12} md={2}>
          <Stat
            label="Entry Status"
            value={tier.halt ? 'HALTED' : 'ALLOWED'}
            color={tier.halt ? C.bear : C.bull}
            mono={false}
          />
        </Grid>
      </Grid>
      {cur.halt_reasons && (
        <Box sx={{
          mt: 2, p: 1.5, borderRadius: 1, bgcolor: C.warnSoft,
          border: `1px solid ${C.warn}`, fontFamily: F.mono, fontSize: F.sm, color: C.text,
        }}>
          <strong style={{ color: C.warn }}>ACTIVE VETOES:</strong> {cur.halt_reasons}
        </Box>
      )}
    </Box>
  );
}

// =============================================================================
// INDICES STRIP — last + change + sparkline
// =============================================================================
function IndicesStripCard({ indices }) {
  // Defensive: indices may come from various endpoint shapes
  const list = Array.isArray(indices) ? indices :
               indices?.indices ? indices.indices :
               [];
  const known = list.length ? list : [
    { symbol: 'SPY', name: 'S&P 500' },
    { symbol: 'QQQ', name: 'Nasdaq 100' },
    { symbol: 'IWM', name: 'Russell 2000' },
    { symbol: 'DIA', name: 'Dow Jones' },
  ];

  return (
    <SectionCard title="Major Indices" subtitle="Last close, daily change, recent trend">
      <Grid container spacing={2}>
        {known.map(idx => (
          <Grid item xs={6} md={3} key={idx.symbol}>
            <IndexCell idx={idx} />
          </Grid>
        ))}
      </Grid>
    </SectionCard>
  );
}

function IndexCell({ idx }) {
  const [series, setSeries] = useState(null);
  const [meta, setMeta] = useState(idx);
  useEffect(() => {
    api.get(`/price/history/${idx.symbol}?timeframe=daily&limit=30`)
      .then(r => {
        const rows = r.data?.items || r.data?.data || [];
        setSeries(rows.slice(-30).map(p => ({
          date: p.date, close: parseFloat(p.close || p.adj_close),
        })));
        if (rows.length) {
          const last = rows[rows.length - 1];
          const prev = rows[rows.length - 2];
          if (last && prev) {
            setMeta(m => ({
              ...m,
              last: parseFloat(last.close || last.adj_close),
              prev_close: parseFloat(prev.close || prev.adj_close),
            }));
          }
        }
      })
      .catch(() => {});
  }, [idx.symbol]);

  const chg = meta.last && meta.prev_close ? (meta.last - meta.prev_close) : null;
  const chgPct = chg && meta.prev_close ? (chg / meta.prev_close) * 100 : null;
  const positive = chgPct != null && chgPct >= 0;
  const color = positive ? C.bull : C.bear;

  return (
    <Box sx={{
      p: 2, bgcolor: C.cardAlt, borderRadius: 1, border: `1px solid ${C.borderLight}`,
    }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.5 }}>
        <Box>
          <Box sx={{ fontSize: F.md, fontWeight: F.weight.bold, color: C.textBright }}>
            {meta.symbol}
          </Box>
          <Box sx={{ fontSize: F.xxs, color: C.textDim }}>{meta.name}</Box>
        </Box>
        {chgPct != null && (positive
          ? <TrendingUpIcon sx={{ color: C.bull, fontSize: 20 }} />
          : <TrendingDownIcon sx={{ color: C.bear, fontSize: 20 }} />)}
      </Stack>
      <Box sx={{
        fontSize: F.xl, fontWeight: F.weight.semibold,
        fontFamily: F.mono, fontFeatureSettings: '"tnum"', color: C.textBright,
      }}>
        {meta.last != null ? `$${num(meta.last)}` : '—'}
      </Box>
      <Box sx={{
        fontSize: F.sm, fontWeight: 600, color,
        fontFamily: F.mono, fontFeatureSettings: '"tnum"',
      }}>
        {chg != null ? `${chg >= 0 ? '+' : ''}${num(chg)} (${chg >= 0 ? '+' : ''}${num(chgPct, 2)}%)` : '—'}
      </Box>
      {series && series.length > 1 && (
        <Box sx={{ mt: 1, height: 40 }}>
          <ResponsiveContainer>
            <AreaChart data={series}>
              <defs>
                <linearGradient id={`gr-${idx.symbol}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area
                type="monotone" dataKey="close" stroke={color}
                strokeWidth={1.5} fill={`url(#gr-${idx.symbol})`}
              />
            </AreaChart>
          </ResponsiveContainer>
        </Box>
      )}
    </Box>
  );
}

// =============================================================================
// 9-FACTOR EXPOSURE
// =============================================================================
function ExposureBreakdownCard({ markets }) {
  const factors = markets?.current?.factors || {};
  const list = [
    ['ibd_state', 'MARKET STATE', 20],
    ['trend_30wk', '30-WEEK MA TREND', 15],
    ['breadth_50dma', 'BREADTH (% > 50-DMA)', 15],
    ['breadth_200dma', 'HEALTH (% > 200-DMA)', 10],
    ['vix_regime', 'VIX REGIME', 10],
    ['mcclellan', 'MCCLELLAN OSC.', 10],
    ['new_highs_lows', 'NEW HIGHS - LOWS', 8],
    ['ad_line', 'A/D LINE CONFIRM.', 7],
    ['aaii_sentiment', 'SENTIMENT (CONTR.)', 5],
  ];
  return (
    <SectionCard
      title="9-Factor Exposure Composite"
      subtitle="Each factor scored independently, summed for total exposure"
    >
      <Box sx={{
        fontFamily: F.mono, fontSize: F.xs, color: C.textDim, mb: 1,
      }}>
        raw {markets?.current?.raw_score} → capped {markets?.current?.exposure_pct}%
      </Box>
      {list.map(([key, label, max]) => {
        const f = factors[key] || {};
        const sub = [];
        if (f.value !== undefined && f.value !== null) sub.push(`value: ${num(f.value, 2)}`);
        if (f.state) sub.push(f.state);
        if (f.relation) sub.push(f.relation);
        if (f.bull_bear_spread !== undefined) sub.push(`spread: ${num(f.bull_bear_spread, 2)}`);
        if (f.new_highs !== undefined) sub.push(`${f.new_highs} highs / ${f.new_lows} lows`);
        if (f.distribution_days_25d !== undefined) sub.push(`${f.distribution_days_25d} dist days (25d)`);
        return (
          <FactorBar
            key={key}
            label={label}
            value={f.pts || 0}
            max={f.max || max}
            sub={sub.join(' · ')}
          />
        );
      })}
    </SectionCard>
  );
}

// =============================================================================
// MARKET PULSE — DD count + FTD
// =============================================================================
function MarketPulseCard({ markets }) {
  const cur = markets?.current;
  if (!cur) return null;
  const dd = cur.distribution_days || 0;
  const ftd = cur.factors?.ibd_state?.follow_through_day;
  const state = cur.factors?.ibd_state?.state || '—';
  const ddColor = dd >= 5 ? C.bear : dd >= 4 ? C.warn : C.bull;

  return (
    <SectionCard title="Market Pulse" subtitle="Institutional selling pressure indicator">
      <Stack spacing={2}>
        <Box sx={{ textAlign: 'center', py: 2 }}>
          <Box sx={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 100, height: 100, borderRadius: '50%',
            bgcolor: dd >= 5 ? C.bearSoft : dd >= 4 ? C.warnSoft : C.bullSoft,
            border: `4px solid ${ddColor}`,
          }}>
            <Box sx={{
              fontFamily: F.mono, fontSize: F.xxxl, fontWeight: F.weight.black, color: ddColor,
            }}>
              {dd}
            </Box>
          </Box>
          <Box sx={{ fontSize: F.xs, color: C.textDim, mt: 1, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
            Distribution Days (25 sessions)
          </Box>
        </Box>
        <Box sx={{
          p: 1.5, bgcolor: C.cardAlt, borderRadius: 1,
          fontSize: F.sm, color: C.text, fontFamily: F.mono,
        }}>
          <Stack spacing={0.5}>
            <Stack direction="row" justifyContent="space-between">
              <span>Follow-Through Day:</span>
              <strong style={{ color: ftd ? C.bull : C.bear }}>{ftd ? 'YES' : 'NO'}</strong>
            </Stack>
            <Stack direction="row" justifyContent="space-between">
              <span>State:</span>
              <strong style={{ color: state.includes('uptrend') ? C.bull : C.bear }}>
                {state.replace(/_/g, ' ').toUpperCase()}
              </strong>
            </Stack>
          </Stack>
        </Box>
        <Box sx={{ fontSize: F.xs, color: C.textDim }}>
          5+ distribution days in 4 weeks signals correction. Confirmed uptrend
          requires &lt; 4 distribution days and a follow-through day after a rally attempt.
        </Box>
      </Stack>
    </SectionCard>
  );
}

// =============================================================================
// EXPOSURE HISTORY LINE CHART
// =============================================================================
function ExposureHistoryChart({ markets }) {
  const history = (markets?.history || []).slice().reverse();
  if (!history.length) {
    return (
      <SectionCard title="Exposure History">
        <EmptyState message="No history yet. Once exposure runs daily, this chart populates." />
      </SectionCard>
    );
  }
  const data = history.map(h => ({
    date: h.date, exposure: parseFloat(h.exposure_pct),
    regime: h.regime, dd: h.distribution_days,
  }));

  return (
    <SectionCard
      title={`Exposure History — last ${data.length} sessions`}
      subtitle="Shows how the algo's risk allocation moved with the market regime"
    >
      <Box sx={{ height: 280 }}>
        <ResponsiveContainer>
          <AreaChart data={data} margin={{ top: 10, right: 16, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="expGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={C.brand} stopOpacity={0.3} />
                <stop offset="100%" stopColor={C.brand} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke={C.borderLight} strokeDasharray="2 4" />
            <XAxis
              dataKey="date" tick={{ fill: C.textDim, fontSize: 11 }}
              tickFormatter={d => String(d).slice(5)}
            />
            <YAxis
              domain={[0, 100]} tick={{ fill: C.textDim, fontSize: 11 }}
              tickFormatter={v => `${v}%`} width={45}
            />
            <RTooltip
              contentStyle={{ background: C.bgElev, border: `1px solid ${C.border}`, fontSize: 12 }}
              formatter={(v, n) => [`${v}%`, 'exposure']}
              labelFormatter={l => `Date: ${l}`}
            />
            <ReferenceLine y={80} stroke={C.bull} strokeDasharray="3 3" label={{ value: 'Confirmed', fill: C.bull, fontSize: 10, position: 'right' }} />
            <ReferenceLine y={60} stroke={C.brand} strokeDasharray="3 3" label={{ value: 'Healthy', fill: C.brand, fontSize: 10, position: 'right' }} />
            <ReferenceLine y={40} stroke={C.warn} strokeDasharray="3 3" label={{ value: 'Pressure', fill: C.warn, fontSize: 10, position: 'right' }} />
            <ReferenceLine y={20} stroke={C.bear} strokeDasharray="3 3" label={{ value: 'Caution', fill: C.bear, fontSize: 10, position: 'right' }} />
            <Area
              type="monotone" dataKey="exposure" stroke={C.brand}
              strokeWidth={2} fill="url(#expGrad)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </Box>
      <Stack direction="row" spacing={3} sx={{ mt: 2, fontSize: F.xs, color: C.textDim, flexWrap: 'wrap' }}>
        {['confirmed_uptrend', 'healthy_uptrend', 'pressure', 'caution', 'correction'].map(r => (
          <Stack key={r} direction="row" alignItems="center" spacing={0.5}>
            <Box sx={{ width: 12, height: 12, bgcolor: tierColor(r), borderRadius: 0.5 }} />
            <Box>{r.replace(/_/g, ' ')}</Box>
          </Stack>
        ))}
      </Stack>
    </SectionCard>
  );
}

// =============================================================================
// BREADTH — % above 50/200 DMA over time
// =============================================================================
function BreadthChart({ markets }) {
  const cur = markets?.current?.factors || {};
  const b50 = cur.breadth_50dma || {};
  const b200 = cur.breadth_200dma || {};

  // Build a snapshot view (we don't have history endpoint for breadth yet)
  const data = [
    { name: '> 50-DMA', value: b50.value || 0, color: C.bull, count: `${b50.above || 0}/${b50.total || 0}` },
    { name: '> 200-DMA', value: b200.value || 0, color: C.brand, count: `${b200.above || 0}/${b200.total || 0}` },
  ];

  return (
    <SectionCard title="Market Breadth" subtitle="% of stocks above key moving averages">
      <Box sx={{ height: 240 }}>
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 12, right: 16, bottom: 8, left: 0 }} barSize={48}>
            <CartesianGrid stroke={C.borderLight} strokeDasharray="2 4" />
            <XAxis dataKey="name" tick={{ fill: C.textDim, fontSize: 12 }} />
            <YAxis
              domain={[0, 100]} tick={{ fill: C.textDim, fontSize: 11 }}
              tickFormatter={v => `${v}%`}
            />
            <RTooltip
              contentStyle={{ background: C.bgElev, border: `1px solid ${C.border}`, fontSize: 12 }}
              formatter={(v, _, p) => [`${v}% (${p.payload.count})`, p.payload.name]}
            />
            <ReferenceLine y={50} stroke={C.textDim} strokeDasharray="3 3" />
            <Bar dataKey="value" fill={C.brand} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </Box>
      <Stack direction="row" spacing={2} sx={{ mt: 1, flexWrap: 'wrap' }}>
        <Stat label="> 50-DMA" value={`${num(b50.value, 1)}%`} sub={`${b50.above || 0} of ${b50.total || 0}`} />
        <Stat label="> 200-DMA" value={`${num(b200.value, 1)}%`} sub={`${b200.above || 0} of ${b200.total || 0}`} />
        <Stat label="McClellan" value={num(cur.mcclellan?.value, 2)} sub={cur.mcclellan?.value > 0 ? 'positive' : 'negative'} />
      </Stack>
    </SectionCard>
  );
}

// =============================================================================
// NEW HIGHS - LOWS
// =============================================================================
function NewHighsLowsChart({ markets }) {
  const nhnl = markets?.current?.factors?.new_highs_lows || {};
  const data = [
    { name: 'New Highs', value: nhnl.new_highs || 0, color: C.bull },
    { name: 'New Lows', value: -(nhnl.new_lows || 0), color: C.bear },
  ];
  return (
    <SectionCard
      title="New Highs vs New Lows"
      subtitle="Net leadership signal — positive net = healthy market participation"
    >
      <Box sx={{ height: 240 }}>
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 12, right: 16, bottom: 8, left: 0 }} barSize={64}>
            <CartesianGrid stroke={C.borderLight} strokeDasharray="2 4" />
            <XAxis dataKey="name" tick={{ fill: C.textDim, fontSize: 12 }} />
            <YAxis tick={{ fill: C.textDim, fontSize: 11 }} />
            <ReferenceLine y={0} stroke={C.borderStrong} />
            <RTooltip
              contentStyle={{ background: C.bgElev, border: `1px solid ${C.border}`, fontSize: 12 }}
              formatter={v => [Math.abs(v), '']}
            />
            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
              {data.map((d, i) => <ReferenceLine key={i} stroke={d.color} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Box>
      <Stack direction="row" spacing={2} sx={{ mt: 1 }}>
        <Stat label="New Highs" value={nhnl.new_highs || 0} color={C.bull} />
        <Stat label="New Lows" value={nhnl.new_lows || 0} color={C.bear} />
        <Stat label="Net" value={nhnl.net || 0} color={(nhnl.net || 0) >= 0 ? C.bull : C.bear} />
      </Stack>
    </SectionCard>
  );
}

// =============================================================================
// AAII SENTIMENT — recent 8 weeks
// =============================================================================
function SentimentChart({ markets }) {
  const sentiment = markets?.sentiment || [];
  if (!sentiment.length) {
    return (
      <SectionCard title="Investor Sentiment">
        <EmptyState message="No sentiment data yet." />
      </SectionCard>
    );
  }
  const data = sentiment.slice().reverse().map(s => ({
    date: s.date,
    bull: parseFloat(s.bullish || 0),
    bear: parseFloat(s.bearish || 0),
    neutral: parseFloat(s.neutral || 0),
  }));
  const latest = data[data.length - 1] || {};
  const spread = (latest.bull || 0) - (latest.bear || 0);

  return (
    <SectionCard
      title="Investor Sentiment"
      subtitle="Bull-bear spread (contrarian signal at extremes)"
    >
      <Box sx={{ height: 220 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 12, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={C.borderLight} strokeDasharray="2 4" />
            <XAxis dataKey="date" tick={{ fill: C.textDim, fontSize: 11 }} tickFormatter={d => String(d).slice(5)} />
            <YAxis tick={{ fill: C.textDim, fontSize: 11 }} tickFormatter={v => `${v}%`} />
            <RTooltip
              contentStyle={{ background: C.bgElev, border: `1px solid ${C.border}`, fontSize: 12 }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line type="monotone" dataKey="bull" stroke={C.bull} strokeWidth={2} dot={false} name="Bullish" />
            <Line type="monotone" dataKey="bear" stroke={C.bear} strokeWidth={2} dot={false} name="Bearish" />
            <Line type="monotone" dataKey="neutral" stroke={C.textDim} strokeWidth={1.5} strokeDasharray="3 3" dot={false} name="Neutral" />
          </LineChart>
        </ResponsiveContainer>
      </Box>
      <Stack direction="row" spacing={2} sx={{ mt: 1 }}>
        <Stat label="Bullish" value={`${num(latest.bull, 1)}%`} color={C.bull} />
        <Stat label="Bearish" value={`${num(latest.bear, 1)}%`} color={C.bear} />
        <Stat
          label="Spread"
          value={`${spread >= 0 ? '+' : ''}${num(spread, 1)}`}
          sub={Math.abs(spread) > 20 ? 'Contrarian alert' : 'Normal'}
          color={spread >= 0 ? C.bull : C.bear}
        />
      </Stack>
    </SectionCard>
  );
}

// =============================================================================
// VIX REGIME
// =============================================================================
function VixChart({ markets, health }) {
  const vix = markets?.current?.factors?.vix_regime || {};
  const data = [
    { name: 'VIX', value: vix.value || 0 },
  ];
  const level = vix.value || 0;
  const regime = level < 15 ? 'Calm' : level < 20 ? 'Normal' : level < 28 ? 'Elevated' : level < 36 ? 'High' : 'Extreme';
  const color = level < 15 ? C.bull : level < 20 ? C.brand : level < 28 ? C.warn : C.bear;

  return (
    <SectionCard
      title="Volatility Regime (VIX)"
      subtitle="Implied volatility — proxy for market fear"
    >
      <Box sx={{ textAlign: 'center', py: 3 }}>
        <Box sx={{
          fontSize: F.xxxxl, fontFamily: F.mono, fontWeight: F.weight.black,
          color, lineHeight: 1, fontFeatureSettings: '"tnum"',
        }}>
          {num(level, 2)}
        </Box>
        <Chip
          label={regime.toUpperCase()}
          sx={{
            mt: 1, bgcolor: `${color}25`, color, fontWeight: F.weight.bold,
            letterSpacing: '0.05em', fontSize: F.xs,
          }}
        />
        <Box sx={{ fontSize: F.xs, color: C.textDim, mt: 1, fontFamily: F.mono }}>
          {vix.rising ? 'RISING' : 'STABLE/FALLING'}
        </Box>
      </Box>
      <Box sx={{
        mt: 2, p: 1.5, borderRadius: 1, bgcolor: C.cardAlt,
        fontSize: F.xs, color: C.textDim, fontFamily: F.mono,
      }}>
        <Stack direction="row" justifyContent="space-around">
          <span>&lt;15: Calm</span>
          <span>15-20: Normal</span>
          <span>20-28: Elevated</span>
          <span>28+: High</span>
        </Stack>
      </Box>
    </SectionCard>
  );
}

export default MarketsHealth;
