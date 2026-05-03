/**
 * Shared UI primitives — built on the unified design system.
 * Every page imports from here for consistency.
 */

import React from 'react';
import {
  Box, Card, CardContent, Typography, Chip, LinearProgress,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Stack, Tooltip, Paper,
} from '@mui/material';
import { TrendingUp, TrendingDown } from '@mui/icons-material';
import { C, F, S, comp, gradeColor, severityColor, pnlColor, fmt$, fmtPct } from '../../theme/algoTheme';

// ============================================================================
// SECTION CARD — primary container for grouped data
// ============================================================================
export const SectionCard = ({ title, action, subtitle, children, sx = {}, noPadding = false }) => (
  <Card sx={{ ...comp.card, ...sx }}>
    {title && (
      <Box sx={comp.cardHeader}>
        <Box>
          <Typography sx={{ ...F.overline, color: C.textBright }}>{title}</Typography>
          {subtitle && (
            <Typography sx={{ color: C.textDim, fontSize: F.xs, mt: 0.25 }}>
              {subtitle}
            </Typography>
          )}
        </Box>
        {action}
      </Box>
    )}
    {noPadding ? children : (
      <CardContent sx={{ '&:last-child': { pb: 2 } }}>{children}</CardContent>
    )}
  </Card>
);

// ============================================================================
// STAT — labelled numeric value block
// ============================================================================
export const Stat = ({ label, value, sub, color, mono = true, large = false }) => (
  <Box>
    <Typography sx={{ ...F.overline, color: C.textDim }}>{label}</Typography>
    <Typography sx={{
      color: color || C.textBright,
      fontFamily: mono ? F.mono : F.body,
      fontWeight: F.weight.bold,
      fontSize: large ? F.xxl : F.xl,
      lineHeight: 1.2,
    }}>
      {value}
    </Typography>
    {sub && (
      <Typography sx={{
        color: typeof sub === 'object' ? undefined : C.textDim,
        fontSize: F.xs,
        fontFamily: F.mono,
      }}>
        {sub}
      </Typography>
    )}
  </Box>
);

// ============================================================================
// KPI CARD — bordered stat with semantic accent
// ============================================================================
export const KpiCard = ({ label, value, sub, color, hint, accent = C.blue }) => (
  <Box sx={{
    p: 2, bgcolor: C.cardAlt, border: `1px solid ${C.border}`, borderRadius: 1,
    borderLeft: `4px solid ${accent}`,
    height: '100%',
  }}>
    <Typography sx={{ ...F.overline, color: C.textDim }}>{label}</Typography>
    <Typography sx={{
      color: color || C.textBright,
      fontFamily: F.mono,
      fontWeight: F.weight.bold,
      fontSize: F.xl,
      lineHeight: 1.2,
    }}>
      {value}
    </Typography>
    {(sub || hint) && (
      <Typography sx={{ color: C.textDim, fontSize: F.xs }}>
        {sub || hint}
      </Typography>
    )}
  </Box>
);

// ============================================================================
// PNL CELL — automatic color + arrow
// ============================================================================
export const PnlCell = ({ value, format = 'number', decimals = 2, sx = {} }) => {
  if (value === null || value === undefined || isNaN(value)) {
    return <Box component="span" sx={{ color: C.textDim, fontFamily: F.mono, ...sx }}>-</Box>;
  }
  const color = pnlColor(value);
  let display;
  if (format === 'currency') display = fmt$(value, decimals);
  else if (format === 'percent') display = fmtPct(value, decimals);
  else if (format === 'r-multiple') display = `${value > 0 ? '+' : ''}${Number(value).toFixed(decimals)}R`;
  else display = `${value > 0 ? '+' : ''}${Number(value).toFixed(decimals)}`;

  return (
    <Box component="span" sx={{ color, fontFamily: F.mono, fontWeight: F.weight.bold, ...sx }}>
      {display}
    </Box>
  );
};

// ============================================================================
// SEVERITY CHIP
// ============================================================================
export const SeverityChip = ({ severity, label }) => (
  <Chip
    size="small"
    label={(label || severity || '').toUpperCase()}
    sx={comp.chip(severityColor(severity), 'white')}
  />
);

// ============================================================================
// GRADE CHIP — A+/A/B/C/D/F
// ============================================================================
export const GradeChip = ({ grade }) => (
  <Chip
    size="small"
    label={grade || '?'}
    sx={{ ...comp.chip(gradeColor(grade)), minWidth: 32 }}
  />
);

// ============================================================================
// TREND ARROW
// ============================================================================
export const TrendArrow = ({ value, threshold = 0 }) => {
  if (value === null || value === undefined) return <Box component="span" sx={{ color: C.textDim }}>·</Box>;
  if (value > threshold) return <TrendingUp sx={{ color: C.bull, fontSize: 16, verticalAlign: 'middle' }} />;
  if (value < -threshold) return <TrendingDown sx={{ color: C.bear, fontSize: 16, verticalAlign: 'middle' }} />;
  return <Box component="span" sx={{ color: C.textDim }}>·</Box>;
};

// ============================================================================
// PROGRESS BAR — colored by fill ratio
// ============================================================================
export const ProgressBar = ({ value, max, height = 6 }) => {
  const pct = max > 0 ? (value / max) * 100 : 0;
  const color = pct >= 70 ? C.bull : pct >= 40 ? C.warn : C.bear;
  return (
    <Box sx={{ width: '100%', height, bgcolor: C.bg, borderRadius: 1, overflow: 'hidden' }}>
      <Box sx={{
        width: `${Math.max(0, Math.min(100, pct))}%`, height: '100%',
        bgcolor: color, transition: 'width 0.3s, background-color 0.3s',
      }} />
    </Box>
  );
};

// ============================================================================
// FACTOR BAR — labelled progress bar with score
// ============================================================================
export const FactorBar = ({ label, pts, max, sub, expanded, onToggle }) => (
  <Box sx={{ mb: 1.5 }}>
    <Box sx={{
      display: 'flex', justifyContent: 'space-between',
      mb: 0.5, alignItems: 'center',
      cursor: onToggle ? 'pointer' : 'default',
    }} onClick={onToggle}>
      <Typography sx={{ color: C.text, fontSize: F.sm, fontWeight: F.weight.semibold }}>
        {label}
      </Typography>
      <Typography sx={{
        color: pts / max >= 0.7 ? C.bull : pts / max >= 0.4 ? C.warn : C.bear,
        fontFamily: F.mono, fontWeight: F.weight.bold,
        fontSize: F.sm,
      }}>
        {(pts || 0).toFixed(1)} / {max}
      </Typography>
    </Box>
    <ProgressBar value={pts || 0} max={max} />
    {sub && (
      <Typography sx={{
        mt: 0.5, color: C.textDim, fontSize: F.xs, fontFamily: F.mono,
      }}>
        {sub}
      </Typography>
    )}
  </Box>
);

// ============================================================================
// DATA TABLE — pre-styled table for data rows
// ============================================================================
export const DataTable = ({ columns, rows, emptyMessage, maxHeight }) => (
  <TableContainer sx={maxHeight ? { maxHeight } : {}}>
    <Table size="small" stickyHeader={!!maxHeight}>
      <TableHead>
        <TableRow>
          {columns.map((col) => (
            <TableCell
              key={col.key || col.label}
              align={col.align || 'left'}
              sx={comp.thCell}
            >
              {col.label}
            </TableCell>
          ))}
        </TableRow>
      </TableHead>
      <TableBody>
        {(rows || []).length === 0 ? (
          <TableRow>
            <TableCell colSpan={columns.length} sx={{ ...comp.tdCell, textAlign: 'center', py: 4 }}>
              <Typography sx={{ color: C.textDim, fontSize: F.sm }}>
                {emptyMessage || 'No data'}
              </Typography>
            </TableCell>
          </TableRow>
        ) : rows.map((row, i) => (
          <TableRow key={row._key || i} hover sx={{
            '&:hover': { bgcolor: `${C.cardAlt} !important` },
          }}>
            {columns.map((col) => (
              <TableCell
                key={col.key || col.label}
                align={col.align || 'left'}
                sx={col.sx || comp.tdCell}
              >
                {col.render ? col.render(row, i) : row[col.key] ?? '-'}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  </TableContainer>
);

// ============================================================================
// STATUS DOT — small colored circle for status indicators
// ============================================================================
export const StatusDot = ({ severity, size = 8 }) => (
  <Box sx={{
    display: 'inline-block', width: size, height: size, borderRadius: '50%',
    bgcolor: severityColor(severity), mr: 0.75, verticalAlign: 'middle',
  }} />
);

// ============================================================================
// PAGE HEADER — title + breadcrumb + actions
// ============================================================================
export const PageHeader = ({ title, subtitle, actions }) => (
  <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
    <Box>
      <Typography sx={{
        color: C.textBright,
        fontWeight: F.weight.bold,
        fontSize: F.xxl,
        letterSpacing: '-0.02em',
      }}>
        {title}
      </Typography>
      {subtitle && (
        <Typography sx={{ color: C.textDim, fontSize: F.sm, fontFamily: F.mono, mt: 0.5 }}>
          {subtitle}
        </Typography>
      )}
    </Box>
    {actions && (
      <Stack direction="row" spacing={1} alignItems="center">
        {actions}
      </Stack>
    )}
  </Box>
);

// ============================================================================
// EMPTY STATE
// ============================================================================
export const EmptyState = ({ message, icon: Icon, action }) => (
  <Box sx={{ textAlign: 'center', py: 6, px: 3 }}>
    {Icon && <Icon sx={{ fontSize: 48, color: C.textDim, mb: 2 }} />}
    <Typography sx={{ color: C.textDim, fontSize: F.md, mb: action ? 2 : 0 }}>
      {message}
    </Typography>
    {action}
  </Box>
);

export default {
  SectionCard, Stat, KpiCard, PnlCell, SeverityChip, GradeChip,
  TrendArrow, ProgressBar, FactorBar, DataTable, StatusDot,
  PageHeader, EmptyState,
};
