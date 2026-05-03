/**
 * Markets Health — flagship page
 *
 * Template D: Multi-Section Dashboard. Shows ALL market-level data on one page,
 * organized by what swing traders need to know in priority order:
 *
 *   1. Regime banner — what tier are we in, what exposure can we use
 *   2. 9-factor exposure breakdown — the composite that drives everything
 *   3. Indices — SPY/QQQ/IWM with key levels
 *   4. Breadth — participation indicators
 *   5. Sectors — full ranking with momentum + acceleration
 *   6. Sentiment — AAII bull/bear with contrarian read
 *   7. Distribution days — institutional selling pressure indicator
 *   8. Economic — VIX and key macro
 *
 * Each card loads independently — no single failure blocks the page.
 * Mobile-responsive: cards stack to single column under 900px.
 *
 * Replaces: MarketOverview, Sentiment, EconomicDashboard, SectorAnalysis,
 *           CommoditiesAnalysis (all merged here per IA consolidation plan).
 */

import React, { useState, useEffect } from 'react';
import { Box, Grid, Stack, CircularProgress, Alert } from '@mui/material';
import { ShieldOutlined, TrendingUp, TrendingDown, Warning, CheckCircle } from '@mui/icons-material';
import { api } from '../services/api';
import {
  C, F, S, comp, tierColor, severityColor, pnlColor,
  fmt$, fmtPct, fmtNum, responsive,
} from '../theme/algoTheme';
import {
  SectionCard, Stat, KpiCard, PnlCell, SeverityChip, TrendArrow,
  ProgressBar, FactorBar, DataTable, StatusDot, PageHeader, EmptyState,
} from '../components/ui/AlgoUI';

// ============================================================================
function MarketsHealth() {
  const [data, setData] = useState({});
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchAll = async () => {
    try {
      const [marketsR, policyR, dataR] = await Promise.all([
        api.get('/algo/markets').catch(() => null),
        api.get('/algo/exposure-policy').catch(() => null),
        api.get('/algo/data-status').catch(() => null),
      ]);
      setData({
        markets: marketsR?.data?.data,
        policy: policyR?.data?.data,
        dataStatus: dataR?.data?.data,
      });
      setLoading(false);
    } catch (e) {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
    if (autoRefresh) {
      const id = setInterval(fetchAll, 30000);
      return () => clearInterval(id);
    }
  }, [autoRefresh]);

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
        <CircularProgress sx={{ color: C.brand }} />
      </Box>
    );
  }

  const m = data.markets;
  const p = data.policy;
  const dataIsStale = !data.dataStatus?.ready_to_trade;

  return (
    <Box sx={{ px: responsive.pageX, py: responsive.pageY, maxWidth: 1600, mx: 'auto' }}>
      {/* PAGE HEADER */}
      <PageHeader
        title="Market Health"
        subtitle={`Updated ${new Date().toLocaleTimeString()} · Auto-refresh ${autoRefresh ? 'ON' : 'OFF'}`}
        actions={
          <SeverityChip
            severity={data.dataStatus?.ready_to_trade ? 'success' : 'warn'}
            label={data.dataStatus?.ready_to_trade ? 'DATA FRESH' : 'DATA STALE'}
          />
        }
      />

      {dataIsStale && (
        <Alert
          severity="warning"
          icon={<Warning />}
          sx={{ mb: 2, bgcolor: C.warnSoft, color: C.text, border: `1px solid ${C.warn}` }}
        >
          Some market data is stale. Algo orchestrator will fail-closed on critical sources.
          Affected: {(data.dataStatus?.critical_stale || []).join(', ') || '—'}
        </Alert>
      )}

      {/* === REGIME BANNER === */}
      <RegimeBanner markets={m} policy={p} />

      {/* === MAIN GRID === */}
      <Grid container spacing={2}>

        {/* 9-FACTOR BREAKDOWN — primary block */}
        <Grid item xs={12} lg={6}>
          <ExposureBreakdownCard markets={m} />
        </Grid>

        {/* SECTOR RANKING */}
        <Grid item xs={12} lg={6}>
          <SectorRankingCard markets={m} />
        </Grid>

        {/* MARKET INTERNALS */}
        <Grid item xs={12} md={6} lg={4}>
          <InternalsCard markets={m} />
        </Grid>

        {/* AAII SENTIMENT */}
        <Grid item xs={12} md={6} lg={4}>
          <SentimentCard markets={m} />
        </Grid>

        {/* DISTRIBUTION DAYS */}
        <Grid item xs={12} md={12} lg={4}>
          <DistributionDaysCard markets={m} />
        </Grid>

        {/* EXPOSURE HISTORY */}
        <Grid item xs={12}>
          <ExposureHistoryCard markets={m} />
        </Grid>
      </Grid>
    </Box>
  );
}

// ============================================================================
// REGIME BANNER — top status strip
// ============================================================================
function RegimeBanner({ markets, policy }) {
  if (!markets?.current) {
    return (
      <SectionCard sx={{ mb: 2, p: 3 }}>
        <Alert severity="info" sx={{ bgcolor: 'transparent' }}>
          No market exposure computed yet. Run algo_market_exposure.py to populate.
        </Alert>
      </SectionCard>
    );
  }

  const exposure = markets.current.exposure_pct;
  const regime = markets.active_tier?.name || markets.current.regime || 'unknown';
  const tier = policy?.active_tier;
  const haltReasons = markets.current.halt_reasons;

  return (
    <Box sx={{
      mb: 2, p: 3,
      bgcolor: C.card, border: `1px solid ${C.border}`, borderRadius: 1,
      borderLeft: `6px solid ${tierColor(regime)}`,
      boxShadow: comp.card.boxShadow,
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
              <Box sx={{ ...F.overline, color: C.textDim, fontSize: F.xs }}>
                Market Exposure
              </Box>
              <Box sx={{
                fontSize: F.xxxl, fontFamily: F.mono, fontWeight: F.weight.black,
                color: tierColor(regime), lineHeight: 1, letterSpacing: '-0.02em',
              }}>
                {exposure}<span style={{ fontSize: F.lg, fontWeight: F.weight.semibold }}>%</span>
              </Box>
            </Box>
          </Stack>
        </Grid>

        <Grid item xs={12} md={3}>
          <Stat
            label="Regime Tier"
            value={regime.replace(/_/g, ' ').toUpperCase()}
            sub={tier?.description || markets.active_tier?.description}
            mono={false}
            color={tierColor(regime)}
          />
        </Grid>

        <Grid item xs={6} md={2}>
          <Stat label="Risk Multiplier" value={`${tier?.risk_multiplier ?? markets.active_tier?.risk_mult ?? '--'}×`} />
        </Grid>

        <Grid item xs={6} md={2}>
          <Stat
            label="Max New / Day"
            value={tier?.max_new_positions_today ?? markets.active_tier?.max_new ?? '--'}
          />
        </Grid>

        <Grid item xs={12} md={2}>
          <Stat
            label="Entry Status"
            value={tier?.halt_new_entries ?? markets.active_tier?.halt ? 'HALTED' : 'ALLOWED'}
            color={tier?.halt_new_entries ?? markets.active_tier?.halt ? C.bear : C.bull}
            mono={false}
          />
        </Grid>
      </Grid>

      {haltReasons && (
        <Box sx={{
          mt: 2, p: 1.5, borderRadius: 1,
          bgcolor: C.warnSoft, color: C.text, border: `1px solid ${C.warn}`,
          fontFamily: F.mono, fontSize: F.sm,
        }}>
          <strong style={{ color: C.warn }}>ACTIVE VETOES:</strong> {haltReasons}
        </Box>
      )}
    </Box>
  );
}

// ============================================================================
// 9-FACTOR EXPOSURE BREAKDOWN
// ============================================================================
function ExposureBreakdownCard({ markets }) {
  const factors = markets?.current?.factors || {};
  const factorList = [
    ['ibd_state', 'MARKET STATE', 20],
    ['trend_30wk', '30-WEEK MA TREND', 15],
    ['breadth_50dma', '% > 50-DMA (BREADTH)', 15],
    ['breadth_200dma', '% > 200-DMA (HEALTH)', 10],
    ['vix_regime', 'VIX REGIME', 10],
    ['mcclellan', 'MCCLELLAN OSCILLATOR', 10],
    ['new_highs_lows', 'NEW HIGHS - LOWS', 8],
    ['ad_line', 'A/D LINE CONFIRMATION', 7],
    ['aaii_sentiment', 'AAII SENTIMENT (CONTR.)', 5],
  ];

  return (
    <SectionCard
      title="9-Factor Exposure Composite"
      subtitle="Each factor independently scored, summed for total exposure"
      action={
        <Box sx={{ fontFamily: F.mono, fontSize: F.xs, color: C.textDim }}>
          raw {markets?.current?.raw_score} → capped {markets?.current?.exposure_pct}%
        </Box>
      }
    >
      {factorList.map(([key, label, max]) => {
        const f = factors[key] || {};
        const sub = [];
        if (f.value !== undefined && f.value !== null) sub.push(`value: ${f.value}`);
        if (f.state) sub.push(`state: ${f.state}`);
        if (f.relation) sub.push(`relation: ${f.relation}`);
        if (f.bull_bear_spread !== undefined) sub.push(`spread: ${f.bull_bear_spread}`);
        if (f.new_highs !== undefined) sub.push(`${f.new_highs} highs / ${f.new_lows} lows`);
        if (f.distribution_days_25d !== undefined) sub.push(`${f.distribution_days_25d} dist days (25d)`);

        return (
          <FactorBar
            key={key}
            label={label}
            pts={parseFloat(f.pts || 0)}
            max={max}
            sub={sub.join(' · ')}
          />
        );
      })}
    </SectionCard>
  );
}

// ============================================================================
// SECTOR RANKING
// ============================================================================
function SectorRankingCard({ markets }) {
  const sectors = markets?.sectors || [];
  const cols = [
    { label: '#', key: 'rank', sx: { ...comp.tdCell, fontFamily: F.mono, fontWeight: F.weight.bold, color: C.textBright } },
    { label: 'SECTOR', key: 'name', sx: { ...comp.tdCell, fontWeight: F.weight.semibold } },
    {
      label: 'MOMENTUM',
      align: 'right',
      render: (r) => <PnlCell value={r.momentum} decimals={2} />,
    },
    { label: '1W AGO', align: 'right', sx: comp.monoCell, render: (r) => r.rank_1w_ago || '-' },
    { label: '4W AGO', align: 'right', sx: comp.monoCell, render: (r) => r.rank_4w_ago || '-' },
    {
      label: 'TREND',
      align: 'center',
      render: (r) => {
        const delta = r.rank_4w_ago ? r.rank_4w_ago - r.rank : 0;
        return <TrendArrow value={delta} threshold={1} />;
      },
    },
  ];

  return (
    <SectionCard title="Sector Strength" subtitle={`${sectors.length} sectors ranked`}>
      <DataTable
        columns={cols}
        rows={sectors.map((s, i) => ({ ...s, _key: s.name }))}
        emptyMessage="No sector ranking data"
      />
    </SectionCard>
  );
}

// ============================================================================
// MARKET INTERNALS
// ============================================================================
function InternalsCard({ markets }) {
  const cur = markets?.current || {};
  const health = markets?.market_health || {};
  const dd = cur.distribution_days || 0;

  return (
    <SectionCard title="Market Internals">
      <Stack spacing={2}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Box sx={{ ...F.overline, color: C.textDim }}>Distribution Days (4w)</Box>
          <Box sx={{
            ...F.overline,
            color: dd >= 5 ? C.bear : dd >= 4 ? C.warn : C.bull,
            fontFamily: F.mono, fontSize: F.lg, fontWeight: F.weight.bold,
          }}>
            {dd}
          </Box>
        </Stack>
        <Stack direction="row" justifyContent="space-between">
          <Box sx={{ ...F.overline, color: C.textDim }}>Market Trend</Box>
          <Box sx={{ fontFamily: F.mono, fontSize: F.sm, color: C.text }}>
            {health.market_trend || '--'}
          </Box>
        </Stack>
        <Stack direction="row" justifyContent="space-between">
          <Box sx={{ ...F.overline, color: C.textDim }}>Weinstein Stage</Box>
          <Box sx={{ fontFamily: F.mono, fontSize: F.sm, color: C.text }}>
            {health.market_stage ? `Stage ${health.market_stage}` : '--'}
          </Box>
        </Stack>
        <Stack direction="row" justifyContent="space-between">
          <Box sx={{ ...F.overline, color: C.textDim }}>VIX Level</Box>
          <Box sx={{
            fontFamily: F.mono, fontSize: F.sm,
            color: health.vix_level > 25 ? C.bear : health.vix_level > 20 ? C.warn : C.bull,
            fontWeight: F.weight.bold,
          }}>
            {health.vix_level || '--'}
          </Box>
        </Stack>
      </Stack>
    </SectionCard>
  );
}

// ============================================================================
// AAII SENTIMENT
// ============================================================================
function SentimentCard({ markets }) {
  const sent = markets?.sentiment || [];
  const latest = sent[0];

  if (!latest) {
    return (
      <SectionCard title="AAII Investor Sentiment">
        <EmptyState message="No sentiment data" />
      </SectionCard>
    );
  }

  const spread = (latest.bullish || 0) - (latest.bearish || 0);
  const cols = [
    { label: 'WEEK', key: 'date', sx: { ...comp.monoCell, fontSize: F.xs } },
    { label: 'BULL %', align: 'right', render: (r) => <Box sx={{ color: C.bull, fontFamily: F.mono }}>{r.bullish?.toFixed(1)}</Box> },
    { label: 'BEAR %', align: 'right', render: (r) => <Box sx={{ color: C.bear, fontFamily: F.mono }}>{r.bearish?.toFixed(1)}</Box> },
    { label: 'SPREAD', align: 'right', render: (r) => <PnlCell value={(r.bullish || 0) - (r.bearish || 0)} decimals={1} /> },
  ];

  return (
    <SectionCard
      title="AAII Investor Sentiment"
      subtitle="Contrarian indicator: extreme bullishness = caution"
    >
      <Box sx={{ mb: 2, p: 1.5, bgcolor: C.cardAlt, borderRadius: 1 }}>
        <Stack direction="row" spacing={2} justifyContent="space-around">
          <Stat label="Bull" value={`${latest.bullish?.toFixed(1)}%`} color={C.bull} />
          <Stat label="Bear" value={`${latest.bearish?.toFixed(1)}%`} color={C.bear} />
          <Stat label="Spread" value={`${spread >= 0 ? '+' : ''}${spread.toFixed(1)}`}
            color={pnlColor(spread)} />
        </Stack>
      </Box>
      <DataTable
        columns={cols}
        rows={sent.slice(0, 8).map(s => ({ ...s, _key: s.date }))}
        emptyMessage="No history"
        maxHeight={250}
      />
    </SectionCard>
  );
}

// ============================================================================
// DISTRIBUTION DAYS
// ============================================================================
function DistributionDaysCard({ markets }) {
  const cur = markets?.current || {};
  const dd = cur.distribution_days || 0;
  const ftd = cur.factors?.ibd_state?.follow_through_day;

  return (
    <SectionCard title="Market Pulse">
      <Stack spacing={2}>
        <Box sx={{ textAlign: 'center', py: 2 }}>
          <Box sx={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 100, height: 100, borderRadius: '50%',
            bgcolor: dd >= 5 ? C.bearSoft : dd >= 4 ? C.warnSoft : C.bullSoft,
            border: `4px solid ${dd >= 5 ? C.bear : dd >= 4 ? C.warn : C.bull}`,
          }}>
            <Box sx={{
              fontFamily: F.mono, fontSize: F.xxxl, fontWeight: F.weight.black,
              color: dd >= 5 ? C.bear : dd >= 4 ? C.warn : C.bull,
            }}>
              {dd}
            </Box>
          </Box>
          <Box sx={{ ...F.overline, color: C.textDim, mt: 1 }}>
            DISTRIBUTION DAYS (4 WEEK)
          </Box>
        </Box>

        <Box sx={{
          p: 1.5, bgcolor: C.cardAlt, borderRadius: 1,
          fontSize: F.sm, color: C.text, fontFamily: F.mono,
        }}>
          <Stack spacing={0.5}>
            <Stack direction="row" justifyContent="space-between">
              <span>Follow-Through Day:</span>
              <strong style={{ color: ftd ? C.bull : C.bear }}>
                {ftd ? 'YES' : 'NO'}
              </strong>
            </Stack>
            <Stack direction="row" justifyContent="space-between">
              <span>State:</span>
              <strong>{cur.factors?.ibd_state?.state || '-'}</strong>
            </Stack>
          </Stack>
        </Box>

        <Box sx={{ fontSize: F.xs, color: C.textDim }}>
          5+ distribution days in 4 weeks signals market correction. Confirmed
          uptrend requires &lt; 4 distribution days and a follow-through day after a rally attempt.
        </Box>
      </Stack>
    </SectionCard>
  );
}

// ============================================================================
// EXPOSURE HISTORY
// ============================================================================
function ExposureHistoryCard({ markets }) {
  const history = (markets?.history || []).slice().reverse();

  return (
    <SectionCard
      title={`Exposure History (last ${history.length} days)`}
      subtitle="Tracks how the algo's risk allocation shifted with market regime"
    >
      <Box sx={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(50px, 1fr))',
        gap: 0.5, mt: 1, mb: 1,
      }}>
        {history.slice(0, 60).map((h, i) => {
          const exp = h.exposure_pct || 0;
          return (
            <Box
              key={i}
              title={`${h.date}: ${exp}% (${h.regime})`}
              sx={{
                height: 36 + (exp * 0.6),
                bgcolor: tierColor(h.regime),
                borderRadius: 0.5,
                opacity: 0.85,
                '&:hover': { opacity: 1, transform: 'scaleY(1.05)' },
                transition: 'all 0.15s',
                cursor: 'pointer',
              }}
            />
          );
        })}
      </Box>
      <Stack direction="row" spacing={3} sx={{ mt: 2, fontFamily: F.mono, fontSize: F.xs, color: C.textDim, flexWrap: 'wrap' }}>
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

export default MarketsHealth;
