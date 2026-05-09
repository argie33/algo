import React from 'react';
import {
  Box, Alert, Grid, Typography, Chip, Stack, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow
} from '@mui/material';
import {
  BarChart, Bar, XAxis, YAxis,
  Tooltip as RechartTooltip, ResponsiveContainer, Cell
} from 'recharts';

function RiskTab({ circuitBreakers, markets, positions = [], C, SectionCard }) {
  const breakers = circuitBreakers?.breakers || [];
  const anyTriggered = circuitBreakers?.any_triggered;

  const sectorExposure = React.useMemo(() => {
    const totals = {};
    positions.forEach(p => {
      const s = p.sector || 'Unknown';
      totals[s] = (totals[s] || 0) + (p.position_value || 0);
    });
    const total = Object.values(totals).reduce((a, b) => a + b, 0);
    return Object.entries(totals)
      .map(([sector, value]) => ({ sector, value, pct: total > 0 ? Math.round(value / total * 1000) / 10 : 0 }))
      .sort((a, b) => b.value - a.value);
  }, [positions]);

  const statusColor = (triggered) => triggered ? C.red : C.green;
  const breakerBg = (triggered) => triggered ? '#3a1414' : '#0e2a18';
  const breakerBorder = (triggered) => triggered ? C.redDark : C.greenDark;

  const getPct = (current, threshold) => threshold > 0 ? Math.min(current / threshold * 100, 100) : 0;

  if (!C || !SectionCard) {
    return <Alert severity="error">RiskTab: Missing color scheme or SectionCard component</Alert>;
  }

  return (
    <Box sx={{ p: 2 }}>
      {anyTriggered && (
        <Alert severity="error" sx={{ mb: 2, bgcolor: '#3a1414', color: C.red, border: `1px solid ${C.redDark}` }}>
          {circuitBreakers.triggered_count} circuit breaker{circuitBreakers.triggered_count !== 1 ? 's' : ''} triggered — new entries halted
        </Alert>
      )}

      <SectionCard title="CIRCUIT BREAKERS — KILL-SWITCH STATUS" sx={{ mb: 2 }}>
        <Grid container spacing={1.5}>
          {breakers.map(b => (
            <Grid item xs={12} sm={6} md={4} key={b.id}>
              <Box sx={{
                p: 1.5, borderRadius: 1,
                bgcolor: breakerBg(b.triggered),
                border: `1px solid ${breakerBorder(b.triggered)}`,
                borderLeft: `4px solid ${statusColor(b.triggered)}`,
              }}>
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                  <Box sx={{ flex: 1 }}>
                    <Typography variant="caption" sx={{ color: C.textDim, fontSize: '0.65rem', letterSpacing: 1, fontWeight: 700 }}>
                      {b.label}
                    </Typography>
                    <Stack direction="row" alignItems="baseline" spacing={0.5}>
                      <Typography sx={{ color: statusColor(b.triggered), fontFamily: 'monospace', fontWeight: 700, fontSize: '1.1rem' }}>
                        {b.current}{b.unit}
                      </Typography>
                      <Typography variant="caption" sx={{ color: C.textDim }}>
                        / {b.threshold}{b.unit}
                      </Typography>
                    </Stack>
                    <Box sx={{ mt: 0.5, height: 4, bgcolor: C.bg, borderRadius: 1, overflow: 'hidden' }}>
                      <Box sx={{
                        width: `${getPct(b.current, b.threshold)}%`,
                        height: '100%',
                        bgcolor: statusColor(b.triggered),
                        transition: 'width 0.3s',
                      }} />
                    </Box>
                  </Box>
                  <Chip size="small" label={b.triggered ? 'TRIGGERED' : 'OK'}
                    sx={{
                      bgcolor: b.triggered ? C.redDark : C.greenDark,
                      color: 'white', height: 18, fontSize: '0.6rem', fontWeight: 700, ml: 1,
                    }} />
                </Stack>
                <Typography variant="caption" sx={{ color: C.textDim, fontSize: '0.65rem', mt: 0.5, display: 'block' }}>
                  {b.description}
                </Typography>
              </Box>
            </Grid>
          ))}
        </Grid>
      </SectionCard>

      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <SectionCard title={`SECTOR EXPOSURE (${positions.length} open positions)`}>
            {sectorExposure.length === 0 ? (
              <Typography variant="caption" sx={{ color: C.textDim }}>No open positions</Typography>
            ) : (
              <Box sx={{ height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={sectorExposure} layout="vertical" margin={{ top: 0, right: 40, bottom: 0, left: 80 }}>
                    <XAxis type="number" tickFormatter={v => `${v}%`} tick={{ fill: C.textDim, fontSize: 10 }} />
                    <YAxis type="category" dataKey="sector" tick={{ fill: C.text, fontSize: 10 }} width={80} />
                    <RechartTooltip
                      contentStyle={{ background: C.card, border: `1px solid ${C.border}`, color: C.text, fontSize: 11 }}
                      formatter={(v, n, p) => [`${p.payload.pct}% ($${p.payload.value?.toLocaleString()})`, 'Exposure']}
                    />
                    <Bar dataKey="pct" radius={[0, 3, 3, 0]}>
                      {sectorExposure.map((_, i) => (
                        <Cell key={i} fill={[C.blue, C.purple, C.green, C.yellow, C.orange, C.red][i % 6]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </Box>
            )}
          </SectionCard>
        </Grid>

        <Grid item xs={12} md={6}>
          <SectionCard title="POSITION RISK SUMMARY">
            {positions.length === 0 ? (
              <Typography variant="caption" sx={{ color: C.textDim }}>No open positions</Typography>
            ) : (
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      {['SYMBOL', 'VALUE', 'STOP DIST', 'AT RISK $', 'SECTOR'].map(h => (
                        <TableCell key={h} sx={{ bgcolor: C.cardAlt, color: C.textDim, borderColor: C.border, fontSize: '0.65rem', fontWeight: 700 }}>{h}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {positions.map(p => (
                      <TableRow key={p.symbol}>
                        <TableCell sx={{ color: C.textBright, fontWeight: 700, fontFamily: 'monospace', borderColor: C.border }}>{p.symbol}</TableCell>
                        <TableCell sx={{ color: C.text, fontFamily: 'monospace', borderColor: C.border }}>
                          ${Math.round(p.position_value || 0).toLocaleString()}
                        </TableCell>
                        <TableCell sx={{ color: p.distance_to_stop_pct < 3 ? C.red : C.yellow, fontFamily: 'monospace', borderColor: C.border }}>
                          {p.distance_to_stop_pct != null ? `${p.distance_to_stop_pct.toFixed(1)}%` : '-'}
                        </TableCell>
                        <TableCell sx={{ color: C.red, fontFamily: 'monospace', borderColor: C.border }}>
                          {p.open_risk_dollars != null ? `$${Math.round(p.open_risk_dollars).toLocaleString()}` : '-'}
                        </TableCell>
                        <TableCell sx={{ color: C.textDim, fontSize: '0.7rem', borderColor: C.border }}>{p.sector || '-'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </SectionCard>
        </Grid>
      </Grid>
    </Box>
  );
}

export default RiskTab;
