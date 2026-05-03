/**
 * Swing Trading Algo Dashboard — Institutional Grade
 *
 * Full data density, dark professional palette, every detail visible.
 * Tabs: Markets / Setups / Positions / Trades / Workflow / Data / Config
 */

import React, { useState, useEffect, useMemo } from 'react';
import {
  Box, Card, CardContent, Grid, Typography, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Chip, LinearProgress, Alert, Button,
  Tabs, Tab, Paper, Tooltip, Stack, Divider, IconButton, Collapse,
} from '@mui/material';
import {
  TrendingUp, TrendingDown, CheckCircle, ErrorOutline, Warning, ExpandMore,
  ExpandLess, FiberManualRecord, Bolt, ShieldOutlined, GpsFixed,
} from '@mui/icons-material';
import { api } from '../services/api';

// ============================================================================
// THEME / STYLE TOKENS
// ============================================================================
const C = {
  bg: '#0e1116',
  card: '#161b22',
  cardAlt: '#1c232c',
  border: '#30363d',
  text: '#c9d1d9',
  textDim: '#8b949e',
  textBright: '#f0f6fc',
  green: '#3fb950',
  greenDark: '#238636',
  red: '#f85149',
  redDark: '#da3633',
  yellow: '#d29922',
  orange: '#fb950c',
  blue: '#388bfd',
  purple: '#a371f7',
};

const tierColor = (n) => ({
  confirmed_uptrend: C.green, healthy_uptrend: '#56b97a',
  pressure: C.yellow, caution: C.orange, correction: C.red,
}[n] || C.textDim);

const gradeColor = (g) => ({
  'A+': C.green, 'A': C.greenDark, 'B': C.blue,
  'C': C.yellow, 'D': C.orange, 'F': C.red,
}[g] || C.textDim);

const statusBg = (s) => ({
  ok: C.green, stale: C.orange, empty: C.red, error: C.red,
}[s] || C.textDim);

// Reusable styled card
const SectionCard = ({ title, action, children, sx = {} }) => (
  <Card sx={{ bgcolor: C.card, color: C.text, border: `1px solid ${C.border}`, ...sx }}>
    {title && (
      <Box sx={{
        px: 2, py: 1, borderBottom: `1px solid ${C.border}`,
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        bgcolor: C.cardAlt,
      }}>
        <Typography variant="overline" sx={{ color: C.textBright, letterSpacing: 1, fontWeight: 600 }}>
          {title}
        </Typography>
        {action}
      </Box>
    )}
    <CardContent sx={{ '&:last-child': { pb: 2 } }}>{children}</CardContent>
  </Card>
);

const Stat = ({ label, value, sub, color }) => (
  <Box>
    <Typography variant="caption" sx={{ color: C.textDim, fontSize: '0.65rem',
      letterSpacing: 1.2, fontWeight: 600 }}>{label}</Typography>
    <Typography variant="h5" sx={{ color: color || C.textBright, fontFamily: 'monospace',
      fontWeight: 600, lineHeight: 1.2 }}>{value}</Typography>
    {sub && <Typography variant="caption" sx={{ color: C.textDim }}>{sub}</Typography>}
  </Box>
);

const FactorBar = ({ label, pts, max, detail, expanded, onToggle }) => {
  const pct = max > 0 ? (pts / max * 100) : 0;
  const barColor = pct >= 70 ? C.green : pct >= 40 ? C.yellow : C.red;
  return (
    <Box sx={{ mb: 1.5, cursor: 'pointer' }} onClick={onToggle}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5, alignItems: 'center' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          {onToggle && (expanded ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />)}
          <Typography variant="caption" sx={{ color: C.text, fontSize: '0.75rem', fontWeight: 600 }}>
            {label}
          </Typography>
        </Box>
        <Typography variant="caption" sx={{ color: barColor, fontFamily: 'monospace', fontWeight: 700 }}>
          {pts.toFixed(1)} / {max}
        </Typography>
      </Box>
      <Box sx={{ width: '100%', height: 6, bgcolor: C.bg, borderRadius: 1, overflow: 'hidden' }}>
        <Box sx={{ width: `${pct}%`, height: '100%', bgcolor: barColor, transition: 'width 0.3s' }} />
      </Box>
      <Collapse in={expanded}>
        <Box sx={{ mt: 0.5, pl: 2, fontFamily: 'monospace', fontSize: '0.7rem', color: C.textDim }}>
          {detail && Object.entries(detail).filter(([k]) => !['pts', 'max', 'score_factor'].includes(k))
            .map(([k, v]) => (
              <Box key={k}>{k}: {typeof v === 'object' ? JSON.stringify(v) : String(v)}</Box>
            ))}
        </Box>
      </Collapse>
    </Box>
  );
};

// ============================================================================
function AlgoTradingDashboard() {
  const [data, setData] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState(0);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchAll = async () => {
    try {
      setError(null);
      const [statusR, marketsR, scoresR, posR, tradesR, configR, dataR, policyR, evalR] =
        await Promise.all([
          api.get('/algo/status').catch(() => null),
          api.get('/algo/markets').catch(() => null),
          api.get('/algo/swing-scores?limit=100').catch(() => null),
          api.get('/algo/positions').catch(() => null),
          api.get('/algo/trades?limit=200').catch(() => null),
          api.get('/algo/config').catch(() => null),
          api.get('/algo/data-status').catch(() => null),
          api.get('/algo/exposure-policy').catch(() => null),
          api.get('/algo/evaluate').catch(() => null),
        ]);
      setData({
        status: statusR?.data?.data,
        markets: marketsR?.data?.data,
        scores: scoresR?.data?.items || [],
        positions: posR?.data?.items || [],
        trades: tradesR?.data?.items || [],
        config: configR?.data?.data,
        dataStatus: dataR?.data?.data,
        policy: policyR?.data?.data,
        evaluated: evalR?.data?.data,
      });
      setLoading(false);
    } catch (err) {
      setError(err.message || 'Failed to fetch algo data');
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
      <Box sx={{ bgcolor: C.bg, minHeight: '100vh', p: 3 }}>
        <LinearProgress sx={{ bgcolor: C.cardAlt }} />
      </Box>
    );
  }

  const portfolio = data.status?.portfolio || {};
  const market = data.markets;

  return (
    <Box sx={{ bgcolor: C.bg, minHeight: '100vh', color: C.text, p: 2 }}>
      {/* HEADER */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Box>
          <Typography variant="h4" sx={{ color: C.textBright, fontWeight: 700, letterSpacing: -0.5 }}>
            SWING TRADING ALGO
          </Typography>
          <Typography variant="caption" sx={{ color: C.textDim, fontFamily: 'monospace' }}>
            Pine signals × multi-factor scoring × IBD market exposure × hedge-fund discipline
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Chip size="small" label={data.dataStatus?.ready_to_trade ? 'DATA READY' : 'DATA STALE'}
            sx={{ bgcolor: data.dataStatus?.ready_to_trade ? C.greenDark : C.redDark, color: 'white' }} />
          <Button variant="contained" size="small" onClick={fetchAll}
            sx={{ bgcolor: C.blue }}>Refresh</Button>
          <Button variant={autoRefresh ? 'contained' : 'outlined'} size="small"
            onClick={() => setAutoRefresh(!autoRefresh)}
            sx={{ color: autoRefresh ? 'white' : C.text, borderColor: C.border }}>
            {autoRefresh ? 'AUTO 30s' : 'MANUAL'}
          </Button>
        </Stack>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {/* TOP STRIP — 4 KPI CARDS */}
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={3}>
          <Card sx={{
            bgcolor: tierColor(market?.active_tier?.name),
            color: 'white', border: 'none', height: '100%',
          }}>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <Box>
                  <Typography variant="overline" sx={{ opacity: 0.85, letterSpacing: 1.5 }}>
                    MARKET EXPOSURE
                  </Typography>
                  <Typography variant="h2" sx={{ fontWeight: 800, lineHeight: 1, fontFamily: 'monospace' }}>
                    {market?.current?.exposure_pct ?? '--'}<span style={{ fontSize: '1.5rem' }}>%</span>
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 600, mt: 0.5 }}>
                    {market?.active_tier?.name?.replace(/_/g, ' ').toUpperCase() || 'UNKNOWN'}
                  </Typography>
                  <Typography variant="caption" sx={{ opacity: 0.85, display: 'block' }}>
                    {market?.active_tier?.description}
                  </Typography>
                </Box>
                <ShieldOutlined sx={{ fontSize: 36, opacity: 0.7 }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <SectionCard sx={{ height: '100%' }}>
            <Stat label="PORTFOLIO VALUE"
              value={`$${(portfolio.total_value || 0).toLocaleString()}`}
              sub={
                <Box component="span" sx={{
                  color: portfolio.unrealized_pnl_pct >= 0 ? C.green : C.red,
                  fontWeight: 600, fontFamily: 'monospace',
                }}>
                  {portfolio.unrealized_pnl_pct >= 0 ? '+' : ''}
                  {portfolio.unrealized_pnl_pct?.toFixed(2)}% unrealized
                </Box>
              }
            />
            <Divider sx={{ my: 1, borderColor: C.border }} />
            <Stack direction="row" spacing={2}>
              <Stat label="DAILY" value={
                <span style={{ color: portfolio.daily_return_pct >= 0 ? C.green : C.red }}>
                  {portfolio.daily_return_pct >= 0 ? '+' : ''}{portfolio.daily_return_pct?.toFixed(2)}%
                </span>
              } />
              <Stat label="POSITIONS" value={`${data.positions?.length || 0}/${data.config?.max_positions?.value || 6}`} />
            </Stack>
          </SectionCard>
        </Grid>
        <Grid item xs={12} md={3}>
          <SectionCard sx={{ height: '100%' }}>
            <Typography variant="overline" sx={{ color: C.textDim, letterSpacing: 1.2, fontWeight: 600 }}>
              ACTIVE TIER POLICY
            </Typography>
            <Box sx={{ mt: 1 }}>
              <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
                <Typography variant="caption" sx={{ color: C.textDim }}>Risk multiplier</Typography>
                <Typography variant="caption" sx={{ color: C.textBright, fontFamily: 'monospace' }}>
                  {market?.active_tier?.risk_mult ?? '--'}x
                </Typography>
              </Stack>
              <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
                <Typography variant="caption" sx={{ color: C.textDim }}>Max new / day</Typography>
                <Typography variant="caption" sx={{ color: C.textBright, fontFamily: 'monospace' }}>
                  {market?.active_tier?.max_new ?? '--'}
                </Typography>
              </Stack>
              <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
                <Typography variant="caption" sx={{ color: C.textDim }}>Min grade</Typography>
                <Chip size="small" label={market?.active_tier?.min_grade || '--'}
                  sx={{ bgcolor: gradeColor(market?.active_tier?.min_grade), color: 'white',
                    height: 18, fontSize: '0.65rem', fontWeight: 700 }} />
              </Stack>
              <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
                <Typography variant="caption" sx={{ color: C.textDim }}>Entries</Typography>
                <Typography variant="caption" sx={{
                  color: market?.active_tier?.halt ? C.red : C.green,
                  fontWeight: 700, fontFamily: 'monospace',
                }}>
                  {market?.active_tier?.halt ? 'HALTED' : 'ALLOWED'}
                </Typography>
              </Stack>
            </Box>
          </SectionCard>
        </Grid>
        <Grid item xs={12} md={3}>
          <SectionCard sx={{ height: '100%' }}>
            <Typography variant="overline" sx={{ color: C.textDim, letterSpacing: 1.2, fontWeight: 600 }}>
              MARKET INTERNALS
            </Typography>
            <Box sx={{ mt: 1 }}>
              <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
                <Typography variant="caption" sx={{ color: C.textDim }}>Distribution days (4w)</Typography>
                <Typography variant="caption" sx={{
                  color: market?.current?.distribution_days >= 5 ? C.red :
                    market?.current?.distribution_days >= 4 ? C.yellow : C.green,
                  fontFamily: 'monospace', fontWeight: 700,
                }}>
                  {market?.current?.distribution_days ?? '--'}
                </Typography>
              </Stack>
              <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
                <Typography variant="caption" sx={{ color: C.textDim }}>Trend</Typography>
                <Typography variant="caption" sx={{ color: C.text, fontFamily: 'monospace' }}>
                  {market?.market_health?.market_trend || '--'}
                </Typography>
              </Stack>
              <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
                <Typography variant="caption" sx={{ color: C.textDim }}>Stage</Typography>
                <Typography variant="caption" sx={{ color: C.text, fontFamily: 'monospace' }}>
                  {market?.market_health?.market_stage || '--'}
                </Typography>
              </Stack>
              <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
                <Typography variant="caption" sx={{ color: C.textDim }}>VIX</Typography>
                <Typography variant="caption" sx={{ color: C.text, fontFamily: 'monospace' }}>
                  {market?.market_health?.vix_level ?? '--'}
                </Typography>
              </Stack>
            </Box>
          </SectionCard>
        </Grid>
      </Grid>

      {/* HALT REASONS BANNER */}
      {market?.current?.halt_reasons && (
        <Alert severity="warning" sx={{
          mb: 2, bgcolor: '#3a2a00', color: '#fed7aa', border: `1px solid ${C.orange}`,
          '& .MuiAlert-icon': { color: C.orange },
        }}>
          <Typography variant="caption" sx={{ fontFamily: 'monospace', fontWeight: 700 }}>
            ACTIVE EXPOSURE VETOES: {market.current.halt_reasons}
          </Typography>
        </Alert>
      )}

      {/* TABS */}
      <Paper sx={{ bgcolor: C.card, border: `1px solid ${C.border}`, color: C.text }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)}
          variant="scrollable"
          sx={{
            borderBottom: `1px solid ${C.border}`,
            '& .MuiTab-root': { color: C.textDim, fontWeight: 600, letterSpacing: 0.8 },
            '& .Mui-selected': { color: `${C.textBright} !important` },
            '& .MuiTabs-indicator': { backgroundColor: C.blue },
          }}>
          <Tab label="MARKETS" />
          <Tab label={`SETUPS (${(data.scores || []).filter(s => s.pass_gates).length})`} />
          <Tab label={`POSITIONS (${data.positions?.length || 0})`} />
          <Tab label={`TRADES (${data.trades?.length || 0})`} />
          <Tab label="WORKFLOW" />
          <Tab label="DATA HEALTH" />
          <Tab label="CONFIG" />
        </Tabs>
        {tab === 0 && <MarketsTab markets={market} />}
        {tab === 1 && <SetupsTab scores={data.scores} evaluated={data.evaluated} />}
        {tab === 2 && <PositionsTab positions={data.positions} />}
        {tab === 3 && <TradesTab trades={data.trades} />}
        {tab === 4 && <WorkflowTab policy={data.policy} markets={market} />}
        {tab === 5 && <DataStatusTab dataStatus={data.dataStatus} />}
        {tab === 6 && <ConfigTab config={data.config} />}
      </Paper>
    </Box>
  );
}

// ============================================================================
// MARKETS TAB
// ============================================================================
function MarketsTab({ markets }) {
  const [expanded, setExpanded] = useState({});
  const toggle = (k) => setExpanded(e => ({ ...e, [k]: !e[k] }));

  if (!markets) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="info" sx={{ bgcolor: C.cardAlt, color: C.text }}>
          No markets data — run algo_market_exposure.py
        </Alert>
      </Box>
    );
  }

  const factors = markets.current?.factors || {};
  const factorList = [
    ['ibd_state', 'IBD MARKET STATE', 20],
    ['trend_30wk', 'TREND 30-WK MA', 15],
    ['breadth_50dma', 'BREADTH > 50-DMA', 15],
    ['breadth_200dma', 'BREADTH > 200-DMA', 10],
    ['vix_regime', 'VIX REGIME', 10],
    ['mcclellan', 'MCCLELLAN OSC', 10],
    ['new_highs_lows', 'NEW HIGHS / LOWS', 8],
    ['ad_line', 'A/D LINE', 7],
    ['aaii_sentiment', 'AAII SENTIMENT', 5],
  ];

  return (
    <Box sx={{ p: 2 }}>
      <Grid container spacing={2}>
        {/* 9-FACTOR EXPOSURE BREAKDOWN */}
        <Grid item xs={12} lg={5}>
          <SectionCard title="9-Factor Exposure Composite" action={
            <Stack direction="row" spacing={1}>
              <Chip size="small" label={`raw ${markets.current?.raw_score}`}
                sx={{ bgcolor: C.cardAlt, color: C.textDim, fontFamily: 'monospace' }} />
              <Chip size="small" label={`final ${markets.current?.exposure_pct}%`}
                sx={{ bgcolor: tierColor(markets.active_tier?.name), color: 'white', fontWeight: 700 }} />
            </Stack>
          }>
            {factorList.map(([key, label, max]) => (
              <FactorBar
                key={key}
                label={label}
                pts={parseFloat(factors[key]?.pts || 0)}
                max={max}
                detail={factors[key]}
                expanded={expanded[key]}
                onToggle={() => toggle(key)}
              />
            ))}
          </SectionCard>
        </Grid>

        {/* SECTOR RANKING */}
        <Grid item xs={12} lg={7}>
          <SectionCard title="Sector Strength (today)">
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.7rem' }}>#</TableCell>
                    <TableCell sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.7rem' }}>SECTOR</TableCell>
                    <TableCell align="right" sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.7rem' }}>MOMENTUM</TableCell>
                    <TableCell align="right" sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.7rem' }}>1W AGO</TableCell>
                    <TableCell align="right" sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.7rem' }}>4W AGO</TableCell>
                    <TableCell align="right" sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.7rem' }}>12W</TableCell>
                    <TableCell align="center" sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.7rem' }}>TREND</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(markets.sectors || []).map(s => {
                    const w1Delta = s.rank_1w_ago ? s.rank_1w_ago - s.rank : 0;
                    const w4Delta = s.rank_4w_ago ? s.rank_4w_ago - s.rank : 0;
                    return (
                      <TableRow key={s.name}>
                        <TableCell sx={{ color: C.textBright, borderColor: C.border, fontFamily: 'monospace', fontWeight: 700 }}>
                          #{s.rank}
                        </TableCell>
                        <TableCell sx={{ color: C.text, borderColor: C.border, fontWeight: 600 }}>{s.name}</TableCell>
                        <TableCell align="right" sx={{
                          color: s.momentum >= 0 ? C.green : C.red, borderColor: C.border, fontFamily: 'monospace',
                        }}>
                          {s.momentum >= 0 ? '+' : ''}{s.momentum?.toFixed(2)}
                        </TableCell>
                        <TableCell align="right" sx={{ color: C.textDim, borderColor: C.border, fontFamily: 'monospace' }}>
                          {s.rank_1w_ago || '-'}
                        </TableCell>
                        <TableCell align="right" sx={{ color: C.textDim, borderColor: C.border, fontFamily: 'monospace' }}>
                          {s.rank_4w_ago || '-'}
                        </TableCell>
                        <TableCell align="right" sx={{ color: C.textDim, borderColor: C.border, fontFamily: 'monospace' }}>
                          {s.rank_12w_ago || '-'}
                        </TableCell>
                        <TableCell align="center" sx={{ borderColor: C.border }}>
                          {w4Delta > 1 ? <TrendingUp sx={{ color: C.green, fontSize: 18 }} /> :
                            w4Delta < -1 ? <TrendingDown sx={{ color: C.red, fontSize: 18 }} /> :
                            <FiberManualRecord sx={{ color: C.textDim, fontSize: 10 }} />}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          </SectionCard>
        </Grid>

        {/* AAII SENTIMENT */}
        <Grid item xs={12} lg={6}>
          <SectionCard title="AAII Investor Sentiment (contrarian indicator)">
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.7rem' }}>WEEK</TableCell>
                    <TableCell align="right" sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.7rem' }}>BULL %</TableCell>
                    <TableCell align="right" sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.7rem' }}>BEAR %</TableCell>
                    <TableCell align="right" sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.7rem' }}>NEUT %</TableCell>
                    <TableCell align="right" sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.7rem' }}>SPREAD</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(markets.sentiment || []).slice(0, 10).map(s => {
                    const sp = (s.bullish || 0) - (s.bearish || 0);
                    return (
                      <TableRow key={s.date}>
                        <TableCell sx={{ color: C.text, borderColor: C.border, fontFamily: 'monospace', fontSize: '0.75rem' }}>{s.date}</TableCell>
                        <TableCell align="right" sx={{ color: C.green, borderColor: C.border, fontFamily: 'monospace' }}>
                          {s.bullish?.toFixed(1)}
                        </TableCell>
                        <TableCell align="right" sx={{ color: C.red, borderColor: C.border, fontFamily: 'monospace' }}>
                          {s.bearish?.toFixed(1)}
                        </TableCell>
                        <TableCell align="right" sx={{ color: C.textDim, borderColor: C.border, fontFamily: 'monospace' }}>
                          {s.neutral?.toFixed(1)}
                        </TableCell>
                        <TableCell align="right" sx={{
                          color: sp >= 0 ? C.green : C.red, borderColor: C.border,
                          fontFamily: 'monospace', fontWeight: 700,
                        }}>
                          {sp >= 0 ? '+' : ''}{sp.toFixed(1)}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          </SectionCard>
        </Grid>

        {/* HISTORY */}
        <Grid item xs={12} lg={6}>
          <SectionCard title={`Exposure History (${(markets.history || []).length} days)`}>
            <Box sx={{ maxHeight: 280, overflowY: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.7rem' }}>DATE</TableCell>
                    <TableCell align="right" sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.7rem' }}>EXPOSURE</TableCell>
                    <TableCell align="right" sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.7rem' }}>DD</TableCell>
                    <TableCell sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.7rem' }}>REGIME</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {[...(markets.history || [])].reverse().slice(0, 30).map(h => (
                    <TableRow key={h.date}>
                      <TableCell sx={{ color: C.text, borderColor: C.border, fontFamily: 'monospace', fontSize: '0.75rem' }}>
                        {h.date}
                      </TableCell>
                      <TableCell align="right" sx={{
                        color: tierColor(h.regime), fontWeight: 700, fontFamily: 'monospace', borderColor: C.border,
                      }}>
                        {h.exposure_pct?.toFixed(0)}%
                      </TableCell>
                      <TableCell align="right" sx={{ color: C.text, fontFamily: 'monospace', borderColor: C.border }}>
                        {h.distribution_days || 0}
                      </TableCell>
                      <TableCell sx={{ color: tierColor(h.regime), fontSize: '0.7rem', borderColor: C.border, fontFamily: 'monospace' }}>
                        {h.regime}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          </SectionCard>
        </Grid>
      </Grid>
    </Box>
  );
}

// ============================================================================
// SETUPS TAB
// ============================================================================
function SetupsTab({ scores, evaluated }) {
  const [expandedRow, setExpandedRow] = useState(null);
  const passing = (scores || []).filter(s => s.pass_gates);
  const blocked = (scores || []).filter(s => !s.pass_gates);

  return (
    <Box sx={{ p: 2 }}>
      <Box sx={{ mb: 2, display: 'flex', gap: 2, flexWrap: 'wrap' }}>
        <Stat label="RAW BUY SIGNALS" value={evaluated?.total_buy_signals || 0} />
        <Stat label="PASSING SCORE" value={passing.length} color={C.green} />
        <Stat label="BLOCKED" value={blocked.length} color={C.orange} />
        <Stat label="LATEST DATE" value={scores?.[0]?.eval_date || '--'} />
      </Box>

      <Typography variant="caption" sx={{ color: C.textDim, fontFamily: 'monospace', display: 'block', mb: 2 }}>
        weights: 25% setup · 20% trend · 20% momentum · 12% volume · 10% fundamentals · 8% sector · 5% multi-tf
      </Typography>

      <SectionCard title={`Top Setups (${passing.length})`}>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                {['SYM', 'GRADE', 'SCORE', 'SETUP', 'TREND', 'MOM', 'VOL', 'FUND', 'SEC', 'MTF', 'SECTOR', 'INDUSTRY'].map(h => (
                  <TableCell key={h} sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.65rem', letterSpacing: 1, fontWeight: 700 }}>
                    {h}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {passing.map(s => (
                <React.Fragment key={s.symbol}>
                  <TableRow hover sx={{ cursor: 'pointer' }}
                    onClick={() => setExpandedRow(expandedRow === s.symbol ? null : s.symbol)}>
                    <TableCell sx={{ color: C.textBright, fontWeight: 700, fontFamily: 'monospace', borderColor: C.border }}>
                      {s.symbol}
                    </TableCell>
                    <TableCell sx={{ borderColor: C.border }}>
                      <Chip size="small" label={s.grade}
                        sx={{ bgcolor: gradeColor(s.grade), color: 'white', fontWeight: 700, height: 20, fontSize: '0.7rem' }} />
                    </TableCell>
                    <TableCell sx={{ color: C.textBright, fontFamily: 'monospace', fontWeight: 700, borderColor: C.border }}>
                      {s.swing_score.toFixed(1)}
                    </TableCell>
                    <ScoreCell value={s.components.setup} max={25} />
                    <ScoreCell value={s.components.trend} max={20} />
                    <ScoreCell value={s.components.momentum} max={20} />
                    <ScoreCell value={s.components.volume} max={12} />
                    <ScoreCell value={s.components.fundamentals} max={10} />
                    <ScoreCell value={s.components.sector} max={8} />
                    <ScoreCell value={s.components.multi_tf} max={5} />
                    <TableCell sx={{ color: C.text, borderColor: C.border, fontSize: '0.75rem' }}>{s.sector}</TableCell>
                    <TableCell sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.7rem' }}>{s.industry}</TableCell>
                  </TableRow>
                  {expandedRow === s.symbol && (
                    <TableRow sx={{ bgcolor: C.bg }}>
                      <TableCell colSpan={12} sx={{ borderColor: C.border, p: 2 }}>
                        <ScoreDetailExpanded details={s.details} symbol={s.symbol} />
                      </TableCell>
                    </TableRow>
                  )}
                </React.Fragment>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </SectionCard>

      {blocked.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <SectionCard title={`Blocked Candidates (${blocked.length}) — failed hard gates`}>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.7rem' }}>SYMBOL</TableCell>
                    <TableCell sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.7rem' }}>FAIL REASON</TableCell>
                    <TableCell sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.7rem' }}>SECTOR</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {blocked.slice(0, 30).map(s => (
                    <TableRow key={s.symbol}>
                      <TableCell sx={{ color: C.text, fontWeight: 600, borderColor: C.border, fontFamily: 'monospace' }}>{s.symbol}</TableCell>
                      <TableCell sx={{ color: C.orange, borderColor: C.border, fontSize: '0.75rem' }}>{s.fail_reason}</TableCell>
                      <TableCell sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.75rem' }}>{s.sector}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </SectionCard>
        </Box>
      )}
    </Box>
  );
}

const ScoreCell = ({ value, max }) => {
  const pct = max > 0 ? (value / max) : 0;
  const color = pct >= 0.7 ? C.green : pct >= 0.4 ? C.yellow : C.red;
  return (
    <TableCell align="right" sx={{
      color: color, fontFamily: 'monospace', borderColor: C.border, fontSize: '0.8rem',
    }}>
      {value.toFixed(1)}
    </TableCell>
  );
};

const ScoreDetailExpanded = ({ details, symbol }) => {
  if (!details) return null;
  const ent = Object.entries(details);
  return (
    <Grid container spacing={1}>
      {ent.map(([key, info]) => (
        <Grid item xs={12} md={6} key={key}>
          <Typography variant="caption" sx={{ color: C.blue, fontFamily: 'monospace', fontWeight: 700, fontSize: '0.7rem' }}>
            {key.toUpperCase()}: {info?.pts?.toFixed?.(1) ?? '-'} / {info?.max ?? '-'}
          </Typography>
          {info?.detail && (
            <Box sx={{ pl: 1, fontSize: '0.7rem', color: C.textDim, fontFamily: 'monospace' }}>
              {Object.entries(info.detail).filter(([k]) => !['pts', 'max'].includes(k))
                .map(([k, v]) => (
                  <div key={k}>{k}: {typeof v === 'object' ? JSON.stringify(v) : String(v)}</div>
                ))}
            </Box>
          )}
        </Grid>
      ))}
    </Grid>
  );
};

// ============================================================================
// POSITIONS TAB
// ============================================================================
function PositionsTab({ positions }) {
  if (!positions || positions.length === 0)
    return <Box sx={{ p: 2 }}><Alert severity="info" sx={{ bgcolor: C.cardAlt, color: C.text }}>No active positions</Alert></Box>;
  return (
    <Box sx={{ p: 2 }}>
      <SectionCard title="Active Positions">
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                {['SYMBOL', 'QTY', 'ENTRY', 'CURRENT', 'STOP', 'VALUE', 'P&L $', 'P&L %', 'DAYS', 'TARGETS', 'STAGE'].map(h => (
                  <TableCell key={h} align={h === 'SYMBOL' ? 'left' : ['QTY', 'DAYS', 'TARGETS'].includes(h) ? 'center' : 'right'}
                    sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.65rem', letterSpacing: 1, fontWeight: 700 }}>
                    {h}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {positions.map(p => {
                const pnlColor = p.unrealized_pnl >= 0 ? C.green : C.red;
                return (
                  <TableRow key={p.position_id}>
                    <TableCell sx={{ color: C.textBright, fontWeight: 700, fontFamily: 'monospace', borderColor: C.border }}>
                      {p.symbol}
                    </TableCell>
                    <TableCell align="center" sx={{ color: C.text, fontFamily: 'monospace', borderColor: C.border }}>{p.quantity}</TableCell>
                    <TableCell align="right" sx={{ color: C.text, fontFamily: 'monospace', borderColor: C.border }}>${p.avg_entry_price?.toFixed(2)}</TableCell>
                    <TableCell align="right" sx={{ color: C.textBright, fontFamily: 'monospace', fontWeight: 700, borderColor: C.border }}>${p.current_price?.toFixed(2)}</TableCell>
                    <TableCell align="right" sx={{ color: C.orange, fontFamily: 'monospace', borderColor: C.border }}>
                      ${(p.current_stop_price || p.stop_loss_price)?.toFixed(2) || '-'}
                    </TableCell>
                    <TableCell align="right" sx={{ color: C.text, fontFamily: 'monospace', borderColor: C.border }}>${p.position_value?.toLocaleString()}</TableCell>
                    <TableCell align="right" sx={{ color: pnlColor, fontWeight: 700, fontFamily: 'monospace', borderColor: C.border }}>
                      ${p.unrealized_pnl?.toFixed(2)}
                    </TableCell>
                    <TableCell align="right" sx={{ color: pnlColor, fontFamily: 'monospace', fontWeight: 700, borderColor: C.border }}>
                      {p.unrealized_pnl_pct?.toFixed(2)}%
                    </TableCell>
                    <TableCell align="center" sx={{ color: C.text, fontFamily: 'monospace', borderColor: C.border }}>{p.days_since_entry || 0}</TableCell>
                    <TableCell align="center" sx={{ color: C.blue, fontFamily: 'monospace', fontWeight: 700, borderColor: C.border }}>
                      {p.target_levels_hit || 0}/3
                    </TableCell>
                    <TableCell sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.75rem' }}>{p.stage_in_exit_plan || '-'}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      </SectionCard>
    </Box>
  );
}

// ============================================================================
// TRADES TAB
// ============================================================================
function TradesTab({ trades }) {
  if (!trades || trades.length === 0)
    return <Box sx={{ p: 2 }}><Alert severity="info" sx={{ bgcolor: C.cardAlt, color: C.text }}>No trade history</Alert></Box>;

  const closed = trades.filter(t => t.status === 'closed');
  const wins = closed.filter(t => t.profit_loss_dollars > 0);
  const winRate = closed.length > 0 ? (wins.length / closed.length * 100).toFixed(1) : '0';
  const totalPnl = closed.reduce((s, t) => s + (parseFloat(t.profit_loss_dollars) || 0), 0);
  const avgR = closed.reduce((s, t) => s + (parseFloat(t.exit_r_multiple) || 0), 0) / Math.max(1, closed.length);

  return (
    <Box sx={{ p: 2 }}>
      <Box sx={{ mb: 2, display: 'flex', gap: 3 }}>
        <Stat label="CLOSED TRADES" value={closed.length} />
        <Stat label="WIN RATE" value={`${winRate}%`} color={parseFloat(winRate) >= 50 ? C.green : C.red} />
        <Stat label="AVG R" value={avgR.toFixed(2)} color={avgR > 0 ? C.green : C.red} />
        <Stat label="TOTAL P&L" value={`$${totalPnl.toFixed(2)}`}
          color={totalPnl >= 0 ? C.green : C.red} />
      </Box>

      <SectionCard title="Trade History">
        <TableContainer sx={{ maxHeight: 600 }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                {['SYMBOL', 'DATE', 'ENTRY', 'EXIT', 'P&L $', 'P&L %', 'R-MULT', 'DAYS', 'EXIT REASON', 'PARTIAL CHAIN', 'STATUS'].map(h => (
                  <TableCell key={h} sx={{
                    bgcolor: C.cardAlt, color: C.textDim, borderColor: C.border,
                    fontSize: '0.65rem', letterSpacing: 1, fontWeight: 700,
                  }}>
                    {h}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {trades.map(t => {
                const pnlColor = t.profit_loss_dollars >= 0 ? C.green : C.red;
                return (
                  <TableRow key={t.trade_id}>
                    <TableCell sx={{ color: C.textBright, fontWeight: 700, fontFamily: 'monospace', borderColor: C.border }}>
                      {t.symbol}
                    </TableCell>
                    <TableCell sx={{ color: C.textDim, fontFamily: 'monospace', fontSize: '0.7rem', borderColor: C.border }}>{t.trade_date}</TableCell>
                    <TableCell sx={{ color: C.text, fontFamily: 'monospace', borderColor: C.border }}>${t.entry_price?.toFixed(2)}</TableCell>
                    <TableCell sx={{ color: t.exit_price ? C.text : C.textDim, fontFamily: 'monospace', borderColor: C.border }}>
                      {t.exit_price ? `$${t.exit_price.toFixed(2)}` : '-'}
                    </TableCell>
                    <TableCell sx={{ color: pnlColor, fontWeight: 700, fontFamily: 'monospace', borderColor: C.border }}>
                      {t.profit_loss_dollars?.toFixed(2) || '-'}
                    </TableCell>
                    <TableCell sx={{ color: pnlColor, fontFamily: 'monospace', borderColor: C.border }}>
                      {t.profit_loss_pct?.toFixed(2)}%
                    </TableCell>
                    <TableCell sx={{ color: t.exit_r_multiple > 0 ? C.green : t.exit_r_multiple < 0 ? C.red : C.text,
                      fontFamily: 'monospace', fontWeight: 700, borderColor: C.border }}>
                      {t.exit_r_multiple ? `${t.exit_r_multiple > 0 ? '+' : ''}${t.exit_r_multiple.toFixed(2)}R` : '-'}
                    </TableCell>
                    <TableCell sx={{ color: C.text, fontFamily: 'monospace', borderColor: C.border }}>{t.trade_duration_days || 0}</TableCell>
                    <TableCell sx={{ color: C.text, fontSize: '0.7rem', borderColor: C.border, maxWidth: 200 }}>
                      {t.exit_reason || '-'}
                    </TableCell>
                    <TableCell sx={{
                      color: C.purple, fontFamily: 'monospace', fontSize: '0.65rem',
                      maxWidth: 280, whiteSpace: 'pre-wrap', borderColor: C.border,
                    }}>
                      {t.partial_exits_log || '-'}
                    </TableCell>
                    <TableCell sx={{ borderColor: C.border }}>
                      <Chip size="small" label={t.status}
                        sx={{
                          bgcolor: t.status === 'closed' ? C.cardAlt : C.blue,
                          color: t.status === 'closed' ? C.textDim : 'white',
                          height: 18, fontSize: '0.65rem', fontWeight: 700,
                        }} />
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      </SectionCard>
    </Box>
  );
}

// ============================================================================
// WORKFLOW TAB
// ============================================================================
function WorkflowTab({ policy, markets }) {
  return (
    <Box sx={{ p: 2 }}>
      <Grid container spacing={2}>
        <Grid item xs={12} md={5}>
          <SectionCard title="7-Phase Daily Workflow">
            {[
              ['1', 'DATA FRESHNESS', 'Halt if any CRITICAL data > 7d stale', 'fail-closed'],
              ['2', 'CIRCUIT BREAKERS', 'Drawdown / consec losses / VIX / breadth / data', 'fail-closed'],
              ['3', 'POSITION MONITOR', 'RS, sector, time decay, earnings — flag for action', 'fail-open'],
              ['3b', 'EXPOSURE POLICY', 'Tier-based stops, partials, force-exit losers', 'fail-open'],
              ['4', 'EXIT EXECUTION', 'Stops, T1/T2/T3, time, TD, RS-break, distribution', 'fail-open'],
              ['5', 'SIGNAL GENERATION', 'Pine BUYs → 6 tiers → swing_score ranking', 'fail-open'],
              ['6', 'ENTRY EXECUTION', 'Idempotent fills, tier caps, grade filter', 'fail-open'],
              ['7', 'RECONCILIATION', 'Alpaca sync, P&L, snapshot, audit trail', 'fail-open'],
            ].map(([n, name, desc, mode]) => (
              <Box key={n} sx={{
                py: 1.5, px: 2, mb: 1, bgcolor: C.cardAlt, border: `1px solid ${C.border}`,
                borderLeft: `4px solid ${C.blue}`, borderRadius: 1,
              }}>
                <Stack direction="row" justifyContent="space-between">
                  <Box>
                    <Typography variant="caption" sx={{ color: C.blue, fontFamily: 'monospace', fontWeight: 700 }}>PHASE {n}</Typography>
                    <Typography variant="body2" sx={{ color: C.textBright, fontWeight: 700 }}>{name}</Typography>
                    <Typography variant="caption" sx={{ color: C.textDim, fontSize: '0.7rem' }}>{desc}</Typography>
                  </Box>
                  <Chip size="small" label={mode} sx={{
                    bgcolor: mode === 'fail-closed' ? C.redDark : C.cardAlt,
                    color: mode === 'fail-closed' ? 'white' : C.text,
                    height: 20, fontSize: '0.65rem', fontFamily: 'monospace',
                  }} />
                </Stack>
              </Box>
            ))}
          </SectionCard>
        </Grid>

        <Grid item xs={12} md={7}>
          <SectionCard title="Exposure Tier Policy Matrix">
            <Typography variant="caption" sx={{ color: C.textDim, display: 'block', mb: 2 }}>
              Current exposure: {policy?.current_exposure_pct ?? '--'}% → tier{' '}
              <span style={{ color: C.textBright, fontWeight: 700 }}>{policy?.active_tier?.name?.toUpperCase()}</span>
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    {['TIER', 'RANGE', 'RISK', 'NEW/DAY', 'GRADE', 'TIGHTEN @', 'PARTIAL @', 'HALT', 'FORCE EXIT'].map(h => (
                      <TableCell key={h} sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.65rem', fontWeight: 700, letterSpacing: 1 }}>
                        {h}
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(policy?.all_tiers || []).map(t => {
                    const isActive = t.name === policy?.active_tier?.name;
                    return (
                      <TableRow key={t.name} sx={{ bgcolor: isActive ? C.cardAlt : 'transparent' }}>
                        <TableCell sx={{ borderColor: C.border, color: tierColor(t.name), fontWeight: 700, fontFamily: 'monospace' }}>
                          {isActive && '▶ '}{t.name}
                        </TableCell>
                        <TableCell sx={{ borderColor: C.border, color: C.text, fontFamily: 'monospace' }}>
                          {t.min_pct}-{t.max_pct}%
                        </TableCell>
                        <TableCell sx={{ borderColor: C.border, color: C.text, fontFamily: 'monospace' }}>
                          {t.risk_multiplier}x
                        </TableCell>
                        <TableCell sx={{ borderColor: C.border, color: C.text, fontFamily: 'monospace' }}>
                          {t.max_new_positions_today}
                        </TableCell>
                        <TableCell sx={{ borderColor: C.border }}>
                          <Chip size="small" label={t.min_swing_grade}
                            sx={{ bgcolor: gradeColor(t.min_swing_grade), color: 'white', height: 18, fontSize: '0.65rem', fontWeight: 700 }} />
                        </TableCell>
                        <TableCell sx={{ borderColor: C.border, color: C.text, fontFamily: 'monospace', fontSize: '0.75rem' }}>
                          {t.tighten_winners_at_r ? `+${t.tighten_winners_at_r}R` : '-'}
                        </TableCell>
                        <TableCell sx={{ borderColor: C.border, color: C.text, fontFamily: 'monospace', fontSize: '0.75rem' }}>
                          {t.force_partial_at_r ? `+${t.force_partial_at_r}R` : '-'}
                        </TableCell>
                        <TableCell sx={{ borderColor: C.border, color: t.halt_new_entries ? C.red : C.green,
                          fontFamily: 'monospace', fontWeight: 700 }}>
                          {t.halt_new_entries ? 'YES' : 'no'}
                        </TableCell>
                        <TableCell sx={{ borderColor: C.border, color: t.force_exit_negative_r ? C.red : C.textDim,
                          fontFamily: 'monospace', fontWeight: 700 }}>
                          {t.force_exit_negative_r ? 'CUT LOSERS' : '-'}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          </SectionCard>
        </Grid>
      </Grid>
    </Box>
  );
}

// ============================================================================
// DATA STATUS TAB
// ============================================================================
function DataStatusTab({ dataStatus }) {
  if (!dataStatus) return <Box sx={{ p: 2 }}><Alert severity="info" sx={{ bgcolor: C.cardAlt, color: C.text }}>Data status not loaded</Alert></Box>;
  return (
    <Box sx={{ p: 2 }}>
      <Box sx={{
        p: 2, mb: 2, borderRadius: 1,
        bgcolor: dataStatus.ready_to_trade ? '#0e2a18' : '#3a1414',
        border: `1px solid ${dataStatus.ready_to_trade ? C.greenDark : C.redDark}`,
      }}>
        <Stack direction="row" alignItems="center" spacing={2}>
          {dataStatus.ready_to_trade ?
            <CheckCircle sx={{ color: C.green, fontSize: 28 }} /> :
            <Warning sx={{ color: C.red, fontSize: 28 }} />}
          <Box>
            <Typography variant="h6" sx={{ color: C.textBright, fontWeight: 700 }}>
              {dataStatus.ready_to_trade ? 'READY TO TRADE' : 'DATA STALE — ALGO WILL FAIL-CLOSE'}
            </Typography>
            <Typography variant="caption" sx={{ color: C.textDim, fontFamily: 'monospace' }}>
              {dataStatus.summary.ok} ok · {dataStatus.summary.stale} stale · {dataStatus.summary.empty} empty · {dataStatus.summary.error} error
            </Typography>
            {!dataStatus.ready_to_trade && (
              <Typography variant="caption" sx={{ color: C.red, display: 'block', fontFamily: 'monospace', mt: 0.5 }}>
                Critical stale: {dataStatus.critical_stale.join(', ')}
              </Typography>
            )}
          </Box>
        </Stack>
      </Box>

      <SectionCard title={`Data Sources (${(dataStatus.sources || []).length})`}>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                {['STATUS', 'TABLE', 'FREQUENCY', 'ROLE', 'LATEST', 'AGE', 'ROWS'].map(h => (
                  <TableCell key={h} sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.65rem', fontWeight: 700, letterSpacing: 1 }}>
                    {h}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {(dataStatus.sources || []).map(s => (
                <TableRow key={s.table}>
                  <TableCell sx={{ borderColor: C.border }}>
                    <Box sx={{
                      display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
                      bgcolor: statusBg(s.status), mr: 1,
                    }} />
                    <span style={{ color: statusBg(s.status), fontFamily: 'monospace',
                      fontSize: '0.75rem', textTransform: 'uppercase', fontWeight: 700 }}>
                      {s.status}
                    </span>
                  </TableCell>
                  <TableCell sx={{ color: C.textBright, fontWeight: 600, fontFamily: 'monospace', borderColor: C.border }}>
                    {s.table}
                  </TableCell>
                  <TableCell sx={{ color: C.text, borderColor: C.border, fontFamily: 'monospace', fontSize: '0.75rem' }}>
                    {s.frequency}
                  </TableCell>
                  <TableCell sx={{ color: C.textDim, borderColor: C.border, fontSize: '0.75rem' }}>
                    {s.role}
                  </TableCell>
                  <TableCell sx={{ color: C.text, borderColor: C.border, fontFamily: 'monospace', fontSize: '0.75rem' }}>
                    {s.latest || '-'}
                  </TableCell>
                  <TableCell sx={{ color: s.age_days > 7 ? C.orange : C.text, borderColor: C.border, fontFamily: 'monospace' }}>
                    {s.age_days !== null ? `${s.age_days}d` : '-'}
                  </TableCell>
                  <TableCell sx={{ color: C.text, borderColor: C.border, fontFamily: 'monospace' }}>
                    {s.rows?.toLocaleString() || '-'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </SectionCard>
    </Box>
  );
}

// ============================================================================
// CONFIG TAB
// ============================================================================
function ConfigTab({ config }) {
  if (!config) return <Box sx={{ p: 2 }}><Alert severity="info" sx={{ bgcolor: C.cardAlt, color: C.text }}>Config not loaded</Alert></Box>;
  const entries = Object.entries(config).sort((a, b) => a[0].localeCompare(b[0]));
  return (
    <Box sx={{ p: 2 }}>
      <Typography variant="caption" sx={{ color: C.textDim, mb: 2, display: 'block' }}>
        {entries.length} configuration parameters · all hot-reload via /api/algo/config/:key
      </Typography>
      <Grid container spacing={1}>
        {entries.map(([key, val]) => (
          <Grid item xs={12} sm={6} md={4} lg={3} key={key}>
            <Card variant="outlined" sx={{ bgcolor: C.cardAlt, color: C.text, border: `1px solid ${C.border}` }}>
              <CardContent sx={{ py: 1.5 }}>
                <Typography variant="caption" sx={{ color: C.textDim, fontSize: '0.65rem', letterSpacing: 1, fontWeight: 600 }}>
                  {key.toUpperCase()}
                </Typography>
                <Typography variant="body2" sx={{
                  color: C.textBright, fontFamily: 'monospace', fontWeight: 700, fontSize: '0.95rem',
                }}>
                  {String(val.value)}
                </Typography>
                <Typography variant="caption" sx={{ color: C.textDim, fontSize: '0.7rem', display: 'block' }}>
                  {val.description}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Box>
  );
}

export default AlgoTradingDashboard;
