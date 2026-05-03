/**
 * TradeTracker — every action the algo takes, visible.
 *
 * Three views in one page (tabs):
 *   1. TRADES        — open + closed positions with full reasoning
 *   2. ACTIVITY      — audit log of every algo decision (entries, exits,
 *                      stop adjustments, pyramid adds, halts, skips)
 *   3. NOTIFICATIONS — alerts from circuit breakers / sector rotation / etc
 *
 * Per FRONTEND_DESIGN_SYSTEM.md: light theme, tabular figures, all data shown,
 * every panel has a freshness timestamp + data source.
 */

import React, { useState, useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Box, Typography, Tabs, Tab, Chip, Tooltip, IconButton,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper,
  TextField, MenuItem, CircularProgress, Alert, Stack, Divider,
  Accordion, AccordionSummary, AccordionDetails,
} from '@mui/material';
import {
  Refresh as RefreshIcon, Search as SearchIcon, ExpandMore as ExpandMoreIcon,
  TrendingUp, TrendingDown, RemoveCircleOutline, Bolt, Warning, Info, CheckCircle,
} from '@mui/icons-material';
import { api } from '../services/api';
import { C, F, S, gradeColor, severityColor } from '../theme/algoTheme';

// =============================================================================
// SHARED PRIMITIVES
// =============================================================================

const SectionCard = ({ title, action, children, freshness, source }) => (
  <Paper
    elevation={0}
    sx={{
      bgcolor: C.card, border: `1px solid ${C.border}`, borderRadius: 1.5,
      p: 2, mb: 2,
    }}
  >
    {(title || action) && (
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1.5 }}>
        <Typography sx={{ fontSize: F.md, fontWeight: F.weight.semibold, color: C.textBright }}>
          {title}
        </Typography>
        <Box sx={{ flex: 1 }} />
        {freshness && (
          <Typography sx={{ fontSize: F.xs, color: C.textDim, mr: 1, fontFamily: F.mono }}>
            Updated {freshness}
          </Typography>
        )}
        {source && (
          <Chip
            label={source}
            size="small"
            sx={{ bgcolor: C.cardAlt, color: C.textDim, fontSize: F.xxs, mr: 1 }}
          />
        )}
        {action}
      </Box>
    )}
    {children}
  </Paper>
);

const PnlCell = ({ value, suffix = '', tabular = true }) => {
  if (value == null) return <span style={{ color: C.textDim }}>—</span>;
  const v = Number(value);
  const color = v > 0 ? C.bull : v < 0 ? C.bear : C.textDim;
  const sign = v > 0 ? '+' : '';
  return (
    <span style={{
      color, fontWeight: 600,
      fontFeatureSettings: tabular ? '"tnum"' : undefined,
      fontFamily: F.mono,
    }}>
      {sign}{v.toFixed(2)}{suffix}
    </span>
  );
};

const Stat = ({ label, value, sub, highlight }) => (
  <Box sx={{ minWidth: 110 }}>
    <Typography sx={{ fontSize: F.xs, color: C.textDim, fontWeight: F.weight.medium, letterSpacing: '0.04em', textTransform: 'uppercase' }}>
      {label}
    </Typography>
    <Typography sx={{
      fontSize: F.lg, fontWeight: F.weight.semibold,
      color: highlight || C.textBright,
      fontFeatureSettings: '"tnum"',
      fontFamily: F.mono,
    }}>
      {value}
    </Typography>
    {sub && (
      <Typography sx={{ fontSize: F.xxs, color: C.textDim, fontFamily: F.mono }}>
        {sub}
      </Typography>
    )}
  </Box>
);

const fmtMoney = (v) => v == null ? '—' : `$${Number(v).toLocaleString('en-US', { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`;
const fmtPct = (v, dp = 1) => v == null ? '—' : `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(dp)}%`;
const fmtAgo = (ts) => {
  if (!ts) return '—';
  const d = new Date(ts);
  const s = (Date.now() - d.getTime()) / 1000;
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};

// =============================================================================
// VIEW 1 — TRADES (open + closed)
// =============================================================================

const StatusChip = ({ status }) => {
  const map = {
    open:    { color: C.bull,  bg: C.bullSoft, label: 'OPEN' },
    closed:  { color: C.textDim, bg: C.cardAlt, label: 'CLOSED' },
    pending: { color: C.warn,  bg: C.warnSoft, label: 'PENDING' },
  };
  const v = map[status] || { color: C.textDim, bg: C.cardAlt, label: status?.toUpperCase() || '—' };
  return (
    <Chip size="small" label={v.label}
      sx={{ bgcolor: v.bg, color: v.color, fontSize: F.xxs, fontWeight: F.weight.bold, height: 20 }} />
  );
};

const TradesView = () => {
  const [statusFilter, setStatusFilter] = useState('all');
  const [symbolFilter, setSymbolFilter] = useState('');
  const [expanded, setExpanded] = useState(null);

  const { data: positions, isLoading: lp, refetch: refetchP } = useQuery({
    queryKey: ['algo-positions'],
    queryFn: () => api.get('/algo/positions').then(r => r.data),
    refetchInterval: 30000,
  });
  const { data: trades, isLoading: lt, refetch: refetchT } = useQuery({
    queryKey: ['algo-trades', statusFilter],
    queryFn: () => api.get(`/algo/trades?limit=200`).then(r => r.data),
    refetchInterval: 60000,
  });

  const refetch = () => { refetchP(); refetchT(); };
  const openPositions = positions?.items || positions?.data?.items || [];
  const closedTrades  = (trades?.items || []).filter(t => t.status === 'closed');

  const filtered = useMemo(() => {
    const sym = symbolFilter.trim().toUpperCase();
    let rows;
    if (statusFilter === 'open') rows = openPositions;
    else if (statusFilter === 'closed') rows = closedTrades;
    else rows = [...openPositions.map(p => ({ ...p, _kind: 'open' })), ...closedTrades.map(t => ({ ...t, _kind: 'closed' }))];
    if (sym) rows = rows.filter(r => r.symbol?.startsWith(sym));
    return rows;
  }, [openPositions, closedTrades, statusFilter, symbolFilter]);

  return (
    <Box>
      <SectionCard
        title="Trades & Positions"
        source="algo_positions + algo_trades"
        action={
          <IconButton size="small" onClick={refetch}>
            <RefreshIcon sx={{ fontSize: 18 }} />
          </IconButton>
        }
      >
        <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
          <Stat label="Open" value={openPositions.length} highlight={C.bull} />
          <Stat label="Closed" value={closedTrades.length} />
          <Stat label="Open P&L"
            value={
              <PnlCell
                value={openPositions.reduce((s, p) => s + Number(p.unrealized_pnl || 0), 0)}
                suffix=""
              />
            }
          />
          <Stat label="Closed P&L"
            value={
              <PnlCell
                value={closedTrades.reduce((s, t) => s + Number(t.profit_loss_dollars || 0), 0)}
                suffix=""
              />
            }
          />
        </Stack>

        <Stack direction="row" spacing={1.5} sx={{ mb: 2 }}>
          <TextField
            size="small" select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
            sx={{ minWidth: 130 }} label="Status"
          >
            <MenuItem value="all">All</MenuItem>
            <MenuItem value="open">Open</MenuItem>
            <MenuItem value="closed">Closed</MenuItem>
          </TextField>
          <TextField
            size="small" placeholder="Symbol" value={symbolFilter}
            onChange={e => setSymbolFilter(e.target.value)}
            sx={{ width: 150 }}
            InputProps={{ startAdornment: <SearchIcon sx={{ fontSize: 16, mr: 0.5, color: C.textDim }} /> }}
          />
        </Stack>

        {(lp || lt) ? (
          <Box sx={{ textAlign: 'center', py: 4 }}><CircularProgress size={24} /></Box>
        ) : filtered.length === 0 ? (
          <Alert severity="info">No trades match these filters.</Alert>
        ) : (
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ '& th': { color: C.textDim, fontSize: F.xxs, fontWeight: F.weight.bold, letterSpacing: '0.05em', borderBottom: `1px solid ${C.border}`, py: 1 } }}>
                  <TableCell>Symbol</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell align="right">Entry</TableCell>
                  <TableCell align="right">Current/Exit</TableCell>
                  <TableCell align="right">Qty</TableCell>
                  <TableCell align="right">P&L $</TableCell>
                  <TableCell align="right">P&L %</TableCell>
                  <TableCell align="right">R</TableCell>
                  <TableCell align="right">Days</TableCell>
                  <TableCell>Reason</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filtered.map((row, i) => {
                  const isOpen = row._kind === 'open' || row.status === 'open';
                  const key = row.position_id || row.trade_id || `${row.symbol}-${i}`;
                  const isExp = expanded === key;
                  const px = isOpen ? row.current_price : row.exit_price;
                  const pl = isOpen ? row.unrealized_pnl : row.profit_loss_dollars;
                  const pp = isOpen ? row.unrealized_pnl_pct : row.profit_loss_pct;
                  const days = isOpen ? row.days_since_entry : row.trade_duration_days;
                  const reason = row.exit_reason || row.entry_reason || row.entry_quality_reason || '';
                  return (
                    <React.Fragment key={key}>
                      <TableRow hover sx={{
                        cursor: 'pointer', '&:hover': { bgcolor: C.cardAlt },
                        '& td': { fontSize: F.sm, py: 1, borderBottom: `1px solid ${C.borderLight}` },
                      }} onClick={() => setExpanded(isExp ? null : key)}>
                        <TableCell sx={{ fontWeight: F.weight.semibold, color: C.textBright }}>
                          {row.symbol}
                        </TableCell>
                        <TableCell><StatusChip status={isOpen ? 'open' : 'closed'} /></TableCell>
                        <TableCell align="right" sx={{ fontFamily: F.mono }}>{fmtMoney(row.entry_price || row.avg_entry_price)}</TableCell>
                        <TableCell align="right" sx={{ fontFamily: F.mono }}>{fmtMoney(px)}</TableCell>
                        <TableCell align="right" sx={{ fontFamily: F.mono }}>{row.quantity || row.entry_quantity || '—'}</TableCell>
                        <TableCell align="right"><PnlCell value={pl} /></TableCell>
                        <TableCell align="right"><PnlCell value={pp} suffix="%" /></TableCell>
                        <TableCell align="right" sx={{ fontFamily: F.mono }}>
                          {row.exit_r_multiple != null ? <PnlCell value={row.exit_r_multiple} suffix="R" /> :
                           row.r_multiple != null ? <PnlCell value={row.r_multiple} suffix="R" /> : '—'}
                        </TableCell>
                        <TableCell align="right" sx={{ fontFamily: F.mono, color: C.textDim }}>{days || '—'}</TableCell>
                        <TableCell sx={{ color: C.textDim, fontSize: F.xs }}>{reason || '—'}</TableCell>
                      </TableRow>
                      {isExp && (
                        <TableRow>
                          <TableCell colSpan={10} sx={{ bgcolor: C.cardAlt, py: 2 }}>
                            <TradeReasoning row={row} isOpen={isOpen} />
                          </TableCell>
                        </TableRow>
                      )}
                    </React.Fragment>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </SectionCard>
    </Box>
  );
};

const TradeReasoning = ({ row, isOpen }) => (
  <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} divider={<Divider orientation="vertical" flexItem />}>
    <Box sx={{ flex: 1 }}>
      <Typography sx={{ fontSize: F.xs, color: C.textDim, fontWeight: F.weight.bold, letterSpacing: '0.05em', mb: 1 }}>
        ENTRY CONTEXT
      </Typography>
      <Stack spacing={0.5}>
        <Detail label="Signal date" value={row.signal_date} mono />
        <Detail label="Trade date"  value={row.trade_date} mono />
        <Detail label="Entry $"     value={fmtMoney(row.entry_price || row.avg_entry_price)} mono />
        <Detail label="Quantity"    value={row.entry_quantity || row.initial_quantity || row.quantity} mono />
        <Detail label="Stop"        value={fmtMoney(row.current_stop_price || row.initial_stop)} mono />
        <Detail label="Base type"   value={row.base_type} />
        <Detail label="Stage phase" value={row.stage_phase} />
        <Detail label="Swing score" value={row.swing_score != null ? `${row.swing_score} (${row.swing_grade || '?'})` : '—'} />
      </Stack>
    </Box>
    <Box sx={{ flex: 1 }}>
      <Typography sx={{ fontSize: F.xs, color: C.textDim, fontWeight: F.weight.bold, letterSpacing: '0.05em', mb: 1 }}>
        {isOpen ? 'POSITION HEALTH' : 'EXIT CONTEXT'}
      </Typography>
      <Stack spacing={0.5}>
        {isOpen ? (
          <>
            <Detail label="Distribution days" value={row.distribution_day_count} mono />
            <Detail label="Targets hit"       value={row.target_levels_hit} mono />
            <Detail label="Trail stop"        value={fmtMoney(row.current_stop_price)} mono />
            <Detail label="Stage"             value={row.stage_in_exit_plan} />
          </>
        ) : (
          <>
            <Detail label="Exit date"   value={row.exit_date} mono />
            <Detail label="Exit $"      value={fmtMoney(row.exit_price)} mono />
            <Detail label="Exit reason" value={row.exit_reason} />
            <Detail label="Days held"   value={row.trade_duration_days} mono />
            <Detail label="R multiple"  value={row.exit_r_multiple != null ? `${Number(row.exit_r_multiple).toFixed(2)}R` : '—'} mono />
            <Detail label="MFE / MAE"   value={`${row.mfe_pct || '—'}% / ${row.mae_pct || '—'}%`} mono />
          </>
        )}
      </Stack>
    </Box>
  </Stack>
);

const Detail = ({ label, value, mono }) => (
  <Box sx={{ display: 'flex', alignItems: 'baseline' }}>
    <Typography sx={{ fontSize: F.xs, color: C.textDim, minWidth: 130 }}>{label}</Typography>
    <Typography sx={{
      fontSize: F.sm, color: C.textBright,
      fontFamily: mono ? F.mono : undefined,
      fontFeatureSettings: mono ? '"tnum"' : undefined,
    }}>
      {value || '—'}
    </Typography>
  </Box>
);

// =============================================================================
// VIEW 2 — ACTIVITY (audit log)
// =============================================================================

const ACTION_ICON = {
  ENTRY: <Bolt sx={{ color: C.bull, fontSize: 18 }} />,
  EXIT:  <RemoveCircleOutline sx={{ color: C.bear, fontSize: 18 }} />,
  STOP_RAISE: <TrendingUp sx={{ color: C.warn, fontSize: 18 }} />,
  PARTIAL_EXIT: <TrendingDown sx={{ color: C.warn, fontSize: 18 }} />,
  PYRAMID_ADD: <TrendingUp sx={{ color: C.bull, fontSize: 18 }} />,
  HALT: <Warning sx={{ color: C.bear, fontSize: 18 }} />,
  SKIP: <Info sx={{ color: C.textDim, fontSize: 18 }} />,
  PASS: <CheckCircle sx={{ color: C.bull, fontSize: 18 }} />,
};

const ActivityView = () => {
  const [filter, setFilter] = useState('');
  const [search, setSearch] = useState('');

  const { data: log, isLoading, refetch } = useQuery({
    queryKey: ['algo-audit-log', filter],
    queryFn: () => api.get(`/algo/audit-log?limit=300${filter ? '&action_type=' + filter : ''}`).then(r => r.data),
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
    <SectionCard
      title="Activity Log"
      source="algo_audit_log"
      freshness={fmtAgo(items[0]?.created_at)}
      action={<IconButton size="small" onClick={refetch}><RefreshIcon sx={{ fontSize: 18 }} /></IconButton>}
    >
      <Typography sx={{ fontSize: F.xs, color: C.textDim, mb: 1.5 }}>
        Every decision the algo makes — entries, exits, stop adjustments, pyramid adds,
        circuit-breaker halts, signal-quality skips. Drill into details for full reasoning.
      </Typography>

      <Stack direction="row" spacing={1.5} sx={{ mb: 2 }}>
        <TextField
          size="small" select value={filter} onChange={e => setFilter(e.target.value)}
          sx={{ minWidth: 160 }} label="Action type"
        >
          <MenuItem value="">All actions</MenuItem>
          <MenuItem value="ENTRY">Entries</MenuItem>
          <MenuItem value="EXIT">Exits</MenuItem>
          <MenuItem value="STOP">Stop adjustments</MenuItem>
          <MenuItem value="PYRAMID">Pyramid adds</MenuItem>
          <MenuItem value="HALT">Halts / circuit breakers</MenuItem>
          <MenuItem value="SKIP">Skipped signals</MenuItem>
        </TextField>
        <TextField
          size="small" placeholder="Search symbol or detail" value={search}
          onChange={e => setSearch(e.target.value)} sx={{ flex: 1 }}
          InputProps={{ startAdornment: <SearchIcon sx={{ fontSize: 16, mr: 0.5, color: C.textDim }} /> }}
        />
      </Stack>

      {isLoading ? (
        <Box sx={{ textAlign: 'center', py: 4 }}><CircularProgress size={24} /></Box>
      ) : items.length === 0 ? (
        <Alert severity="info">
          No activity yet. The algo will log every decision (entries, exits, stop-raises,
          halts) here. New entries appear as soon as the orchestrator runs.
        </Alert>
      ) : (
        <Stack spacing={1}>
          {items.map(item => (
            <ActivityRow key={item.id} item={item} />
          ))}
        </Stack>
      )}
    </SectionCard>
  );
};

const ActivityRow = ({ item }) => {
  const [open, setOpen] = useState(false);
  const actionKey = (item.action_type || '').toUpperCase();
  const icon = Object.entries(ACTION_ICON).find(([k]) => actionKey.includes(k))?.[1] || <Info sx={{ color: C.textDim, fontSize: 18 }} />;
  const failed = item.status === 'error' || !!item.error;
  return (
    <Accordion
      expanded={open}
      onChange={() => setOpen(o => !o)}
      elevation={0}
      sx={{
        bgcolor: C.cardAlt, border: `1px solid ${C.borderLight}`,
        borderRadius: 1, '&:before': { display: 'none' },
      }}
    >
      <AccordionSummary
        expandIcon={<ExpandMoreIcon />}
        sx={{ minHeight: 48, '& .MuiAccordionSummary-content': { my: 1 } }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, width: '100%' }}>
          {icon}
          <Box sx={{ flex: 1 }}>
            <Typography sx={{ fontSize: F.sm, fontWeight: F.weight.medium, color: failed ? C.bear : C.textBright }}>
              {item.action_type}
              {item.symbol && (
                <span style={{ color: C.textDim, marginLeft: 8 }}> · {item.symbol}</span>
              )}
            </Typography>
            <Typography sx={{ fontSize: F.xs, color: C.textDim }}>
              {fmtAgo(item.created_at)} · {item.actor || 'orchestrator'}
              {failed && <span style={{ color: C.bear, marginLeft: 8 }}>FAILED</span>}
            </Typography>
          </Box>
        </Box>
      </AccordionSummary>
      <AccordionDetails sx={{ pt: 0 }}>
        {item.error && (
          <Alert severity="error" sx={{ mb: 1, fontSize: F.xs }}>{item.error}</Alert>
        )}
        {item.details && (
          <Box sx={{
            bgcolor: C.bg, border: `1px solid ${C.border}`, p: 1.5, borderRadius: 1,
            fontFamily: F.mono, fontSize: F.xs, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            color: C.text,
          }}>
            {typeof item.details === 'string' ? item.details : JSON.stringify(item.details, null, 2)}
          </Box>
        )}
      </AccordionDetails>
    </Accordion>
  );
};

// =============================================================================
// VIEW 3 — NOTIFICATIONS
// =============================================================================

const NotificationsView = () => {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['algo-notifications-all'],
    queryFn: () => api.get('/algo/notifications?include_seen=1').then(r => r.data),
    refetchInterval: 30000,
  });
  const items = data?.items || [];
  return (
    <SectionCard
      title="Notifications"
      source="algo_notifications"
      freshness={fmtAgo(items[0]?.created_at)}
      action={<IconButton size="small" onClick={refetch}><RefreshIcon sx={{ fontSize: 18 }} /></IconButton>}
    >
      <Typography sx={{ fontSize: F.xs, color: C.textDim, mb: 1.5 }}>
        Circuit-breaker fires, sector-rotation alerts, exposure-tier transitions,
        and other algo notifications. Toasts appear app-wide; this is the full archive.
      </Typography>
      {isLoading ? (
        <Box sx={{ textAlign: 'center', py: 4 }}><CircularProgress size={24} /></Box>
      ) : items.length === 0 ? (
        <Alert severity="success">No active notifications. Quiet markets.</Alert>
      ) : (
        <Stack spacing={1}>
          {items.map(n => (
            <Box key={n.id} sx={{
              p: 1.5, borderRadius: 1, bgcolor: n.seen ? C.cardAlt : C.warnSoft,
              border: `1px solid ${n.seen ? C.borderLight : C.warn}`,
              opacity: n.seen ? 0.7 : 1,
            }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                <Chip
                  size="small" label={n.severity?.toUpperCase() || 'INFO'}
                  sx={{
                    bgcolor: severityColor(n.severity), color: 'white',
                    fontSize: F.xxs, fontWeight: F.weight.bold, height: 18,
                  }}
                />
                <Typography sx={{ fontSize: F.sm, fontWeight: F.weight.semibold, color: C.textBright }}>
                  {n.title || n.event_type}
                </Typography>
                <Box sx={{ flex: 1 }} />
                <Typography sx={{ fontSize: F.xxs, color: C.textDim, fontFamily: F.mono }}>
                  {fmtAgo(n.created_at)}
                </Typography>
              </Box>
              <Typography sx={{ fontSize: F.sm, color: C.text }}>{n.message}</Typography>
            </Box>
          ))}
        </Stack>
      )}
    </SectionCard>
  );
};

// =============================================================================
// MAIN
// =============================================================================

const TradeTracker = () => {
  const [tab, setTab] = useState(0);
  return (
    <Box sx={{ p: { xs: 2, md: 3 }, bgcolor: C.bg, minHeight: '100%' }}>
      <Box sx={{ mb: 3 }}>
        <Typography sx={{ fontSize: F.xl, fontWeight: F.weight.bold, color: C.textBright, letterSpacing: '-0.02em' }}>
          Trade Tracker
        </Typography>
        <Typography sx={{ fontSize: F.sm, color: C.textDim }}>
          Every action the algo takes — entries, exits, stop adjustments,
          pyramid adds, halts, skipped signals. Click any row for full reasoning.
        </Typography>
      </Box>

      <Paper elevation={0} sx={{ bgcolor: 'transparent', borderBottom: `1px solid ${C.border}`, mb: 2 }}>
        <Tabs
          value={tab} onChange={(_, v) => setTab(v)}
          sx={{ '& .MuiTab-root': { textTransform: 'none', fontSize: F.sm, fontWeight: F.weight.medium, minHeight: 40 } }}
        >
          <Tab label="Trades" />
          <Tab label="Activity Log" />
          <Tab label="Notifications" />
        </Tabs>
      </Paper>

      {tab === 0 && <TradesView />}
      {tab === 1 && <ActivityView />}
      {tab === 2 && <NotificationsView />}
    </Box>
  );
};

export default TradeTracker;
