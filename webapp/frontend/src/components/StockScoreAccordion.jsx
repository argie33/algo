import React from 'react';
import {
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Grid,
  Box,
  Typography,
  Chip,
  useTheme,
  alpha,
} from '@mui/material';
import { ExpandMore, Award } from '@mui/icons-material';
import { formatNumber, formatPercentageChange, formatCurrency } from '../utils/formatters';

const num = (v, dp = 1) => formatNumber(v, dp);
const pct = (v, dp = 2) => formatPercentageChange(v, dp);
const money = (v) => formatCurrency(v);

const scoreClass = (v) => {
  if (v == null || isNaN(Number(v))) return 'default';
  const n = Number(v);
  if (n >= 80) return 'success';
  if (n >= 60) return 'info';
  if (n >= 40) return 'warning';
  return 'error';
};

const scoreColor = (v, theme) => {
  if (v == null || isNaN(Number(v))) return theme.palette.text.secondary;
  const n = Number(v);
  if (n >= 80) return theme.palette.success.main;
  if (n >= 60) return theme.palette.info.main;
  if (n >= 40) return theme.palette.warning.main;
  return theme.palette.error.main;
};

const grade = (v) => {
  if (v == null) return '—';
  const n = Number(v);
  if (n >= 90) return 'A+';
  if (n >= 85) return 'A';
  if (n >= 80) return 'A-';
  if (n >= 75) return 'B+';
  if (n >= 70) return 'B';
  if (n >= 65) return 'B-';
  if (n >= 60) return 'C+';
  if (n >= 55) return 'C';
  if (n >= 50) return 'C-';
  if (n >= 45) return 'D+';
  if (n >= 40) return 'D';
  return 'F';
};

const FACTORS = [
  { key: 'quality',     label: 'Quality',     scoreKey: 'quality_score' },
  { key: 'momentum',    label: 'Momentum',    scoreKey: 'momentum_score' },
  { key: 'value',       label: 'Value',       scoreKey: 'value_score' },
  { key: 'growth',      label: 'Growth',      scoreKey: 'growth_score' },
  { key: 'positioning', label: 'Positioning', scoreKey: 'positioning_score' },
  { key: 'stability',   label: 'Stability',   scoreKey: 'stability_score' },
];

const StockScoreAccordion = ({ stocks = [], marketAvgs = {}, sectorAvgs = {} }) => {
  const theme = useTheme();

  if (!stocks || stocks.length === 0) {
    return (
      <Box sx={{ p: 4, textAlign: 'center' }}>
        <Typography variant="body1" color="text.secondary">
          No stock scores data found
        </Typography>
      </Box>
    );
  }

  const DataField = ({ label, value, format = 'text', color = null, unit = '' }) => {
    if (value === null || value === undefined || value === '') {
      return null;
    }

    let displayValue = value;
    if (format === 'currency' && value) {
      displayValue = formatCurrency(value);
    } else if (format === 'percent' && value !== null && value !== undefined) {
      displayValue = formatPercentageChange(value, 2);
    } else if (format === 'number' && value !== null && value !== undefined) {
      displayValue = formatNumber(value, 2);
    }

    return (
      <Box sx={{ mb: 1 }}>
        <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mb: 0.5 }}>
          {label}
        </Typography>
        <Typography
          variant="body2"
          sx={{
            fontWeight: 600,
            color: color || 'text.primary',
            fontSize: '0.95rem',
          }}
        >
          {displayValue} {unit}
        </Typography>
      </Box>
    );
  };

  const FactorSection = ({ factor, stock, sectorAvg, marketAvg }) => {
    const stockScore = stock[factor.scoreKey];
    const Icon = Award;

    return (
      <Grid item xs={12} sm={6} md={4} lg={2.4}>
        <Box sx={{ mb: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
            <Icon sx={{ fontSize: 18, color: scoreColor(stockScore, theme) }} />
            <Typography
              variant="subtitle2"
              sx={{
                fontWeight: 700,
                color: 'text.primary',
                fontSize: '0.85rem',
                textTransform: 'uppercase',
                letterSpacing: '0.3px',
              }}
            >
              {factor.label}
            </Typography>
            <Chip
              label={num(stockScore, 1)}
              size="small"
              color={scoreClass(stockScore)}
              sx={{ ml: 'auto', fontWeight: 700 }}
            />
          </Box>
        </Box>

        {/* Stock score comparison */}
        <Box sx={{ p: 1.5, backgroundColor: alpha(scoreColor(stockScore, theme), 0.08), borderRadius: 1, mb: 1 }}>
          <Typography variant="caption" sx={{ fontSize: '0.75rem', fontWeight: 600, color: 'text.secondary', display: 'block', mb: 0.5 }}>
            STOCK SCORE
          </Typography>
          <Typography variant="h6" sx={{ fontWeight: 700, color: scoreColor(stockScore, theme) }}>
            {num(stockScore, 1)}
          </Typography>
        </Box>

        {/* Sector comparison */}
        {sectorAvg != null && (
          <Box sx={{ p: 1.5, backgroundColor: alpha(theme.palette.info.main, 0.08), borderRadius: 1, mb: 1 }}>
            <Typography variant="caption" sx={{ fontSize: '0.75rem', fontWeight: 600, color: 'text.secondary', display: 'block', mb: 0.5 }}>
              SECTOR AVG
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 600, color: theme.palette.info.main }}>
              {num(sectorAvg, 1)}
            </Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.7rem' }}>
              {stockScore > sectorAvg ? '+' : ''}{num(stockScore - sectorAvg, 1)} vs sector
            </Typography>
          </Box>
        )}

        {/* Market average comparison */}
        {marketAvg != null && (
          <Box sx={{ p: 1.5, backgroundColor: alpha(theme.palette.text.secondary, 0.08), borderRadius: 1 }}>
            <Typography variant="caption" sx={{ fontSize: '0.75rem', fontWeight: 600, color: 'text.secondary', display: 'block', mb: 0.5 }}>
              MARKET AVG
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 600, color: theme.palette.text.primary }}>
              {num(marketAvg, 1)}
            </Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.7rem' }}>
              {stockScore > marketAvg ? '+' : ''}{num(stockScore - marketAvg, 1)} vs market
            </Typography>
          </Box>
        )}
      </Grid>
    );
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {stocks.map((stock, index) => {
        const sectorAvgsForStock = sectorAvgs[stock.symbol] || {};

        return (
          <Accordion
            key={`${stock.symbol}-${index}`}
            defaultExpanded={index === 0}
            sx={{ mb: 1 }}
          >
            {/* ─── ACCORDION SUMMARY (Header with key metrics) ─── */}
            <AccordionSummary
              expandIcon={<ExpandMore />}
              sx={{
                '&:hover': {
                  backgroundColor: alpha(theme.palette.primary.main, 0.02),
                },
              }}
            >
              <Grid container alignItems="center" spacing={2} sx={{ width: '100%' }}>
                {/* Composite Score Badge */}
                <Grid item xs="auto">
                  <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0.5 }}>
                    <Chip
                      label={grade(stock.composite_score)}
                      color={scoreClass(stock.composite_score)}
                      sx={{
                        fontWeight: 700,
                        fontSize: '0.9rem',
                        height: 36,
                        width: 36,
                      }}
                    />
                    <Typography variant="caption" sx={{ fontSize: '0.65rem', fontWeight: 600 }}>
                      Grade
                    </Typography>
                  </Box>
                </Grid>

                {/* Symbol, Company, Sector */}
                <Grid item xs={12} sm="auto" sx={{ flexGrow: { xs: 1, sm: 0 }, minWidth: { sm: 200 } }}>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Typography variant="h5" fontWeight={700}>
                        {stock.symbol}
                      </Typography>
                      {stock.price && (
                        <Typography variant="caption" sx={{ fontWeight: 600, color: 'text.secondary' }}>
                          ${num(stock.price, 2)}
                        </Typography>
                      )}
                    </Box>
                    {stock.company_name && (
                      <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.2, maxWidth: 250, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {stock.company_name}
                      </Typography>
                    )}
                    {stock.sector && (
                      <Typography variant="caption" color="text.secondary">
                        {stock.sector}
                      </Typography>
                    )}
                  </Box>
                </Grid>

                {/* Key Metrics - Right Side */}
                <Grid item xs={12} sm sx={{ flexGrow: 1 }}>
                  <Grid container spacing={2} sx={{ ml: 0 }}>
                    {/* Composite Score */}
                    <Grid item xs={6} sm="auto">
                      <Box sx={{ minWidth: 90 }}>
                        <Typography variant="caption" color="text.secondary" fontWeight={600} sx={{ display: 'block', fontSize: '0.7rem', mb: 0.25, textTransform: 'uppercase' }}>
                          Composite
                        </Typography>
                        <Chip
                          label={num(stock.composite_score, 1)}
                          color={scoreClass(stock.composite_score)}
                          sx={{ fontWeight: 700 }}
                        />
                      </Box>
                    </Grid>

                    {/* Quality Score */}
                    <Grid item xs={6} sm="auto">
                      <Box sx={{ minWidth: 70 }}>
                        <Typography variant="caption" color="text.secondary" fontWeight={600} sx={{ display: 'block', fontSize: '0.7rem', mb: 0.25 }}>
                          Quality
                        </Typography>
                        <Typography
                          variant="caption"
                          fontWeight={700}
                          sx={{
                            fontSize: '0.9rem',
                            color: scoreColor(stock.quality_score, theme),
                          }}
                        >
                          {num(stock.quality_score, 0)}
                        </Typography>
                      </Box>
                    </Grid>

                    {/* Momentum Score */}
                    <Grid item xs={6} sm="auto">
                      <Box sx={{ minWidth: 70 }}>
                        <Typography variant="caption" color="text.secondary" fontWeight={600} sx={{ display: 'block', fontSize: '0.7rem', mb: 0.25 }}>
                          Momentum
                        </Typography>
                        <Typography
                          variant="caption"
                          fontWeight={700}
                          sx={{
                            fontSize: '0.9rem',
                            color: scoreColor(stock.momentum_score, theme),
                          }}
                        >
                          {num(stock.momentum_score, 0)}
                        </Typography>
                      </Box>
                    </Grid>

                    {/* Value Score */}
                    <Grid item xs={6} sm="auto">
                      <Box sx={{ minWidth: 60 }}>
                        <Typography variant="caption" color="text.secondary" fontWeight={600} sx={{ display: 'block', fontSize: '0.7rem', mb: 0.25 }}>
                          Value
                        </Typography>
                        <Typography
                          variant="caption"
                          fontWeight={700}
                          sx={{
                            fontSize: '0.9rem',
                            color: scoreColor(stock.value_score, theme),
                          }}
                        >
                          {num(stock.value_score, 0)}
                        </Typography>
                      </Box>
                    </Grid>

                    {/* Growth Score */}
                    <Grid item xs={6} sm="auto">
                      <Box sx={{ minWidth: 70 }}>
                        <Typography variant="caption" color="text.secondary" fontWeight={600} sx={{ display: 'block', fontSize: '0.7rem', mb: 0.25 }}>
                          Growth
                        </Typography>
                        <Typography
                          variant="caption"
                          fontWeight={700}
                          sx={{
                            fontSize: '0.9rem',
                            color: scoreColor(stock.growth_score, theme),
                          }}
                        >
                          {num(stock.growth_score, 0)}
                        </Typography>
                      </Box>
                    </Grid>

                    {/* Positioning Score */}
                    <Grid item xs={6} sm="auto">
                      <Box sx={{ minWidth: 70 }}>
                        <Typography variant="caption" color="text.secondary" fontWeight={600} sx={{ display: 'block', fontSize: '0.7rem', mb: 0.25 }}>
                          Position
                        </Typography>
                        <Typography
                          variant="caption"
                          fontWeight={700}
                          sx={{
                            fontSize: '0.9rem',
                            color: scoreColor(stock.positioning_score, theme),
                          }}
                        >
                          {num(stock.positioning_score, 0)}
                        </Typography>
                      </Box>
                    </Grid>

                    {/* Stability Score */}
                    <Grid item xs={6} sm="auto">
                      <Box sx={{ minWidth: 70 }}>
                        <Typography variant="caption" color="text.secondary" fontWeight={600} sx={{ display: 'block', fontSize: '0.7rem', mb: 0.25 }}>
                          Stability
                        </Typography>
                        <Typography
                          variant="caption"
                          fontWeight={700}
                          sx={{
                            fontSize: '0.9rem',
                            color: scoreColor(stock.stability_score, theme),
                          }}
                        >
                          {num(stock.stability_score, 0)}
                        </Typography>
                      </Box>
                    </Grid>

                    {/* Updated Date */}
                    {stock.last_updated && (
                      <Grid item xs={12} sm="auto">
                        <Typography variant="caption" color="text.secondary">
                          Updated {new Date(stock.last_updated).toLocaleDateString()}
                        </Typography>
                      </Grid>
                    )}
                  </Grid>
                </Grid>
              </Grid>
            </AccordionSummary>

            {/* ─── ACCORDION DETAILS (Expandable factor breakdown) ─── */}
            <AccordionDetails
              sx={{
                backgroundColor: 'background.paper',
                borderTop: `2px solid ${alpha(theme.palette.primary.main, 0.1)}`,
                pt: 3.5,
                pb: 3.5,
                px: 3,
              }}
            >
              {/* ─── Factor Scores with Comparisons ─── */}
              <Box sx={{ mb: 4 }}>
                <Typography variant="h6" sx={{ fontWeight: 700, mb: 3, color: 'primary.main', textTransform: 'uppercase', fontSize: '0.9rem', letterSpacing: '0.5px' }}>
                  📊 Factor Scores & Comparisons
                </Typography>
                <Grid container spacing={2}>
                  {FACTORS.map(f => (
                    <FactorSection
                      key={f.key}
                      factor={f}
                      stock={stock}
                      sectorAvg={sectorAvgsForStock[f.key]}
                      marketAvg={marketAvgs[f.key]}
                    />
                  ))}
                </Grid>
              </Box>

              {/* ─── Factor Inputs Tables ─── */}
              <Box>
                <Typography variant="h6" sx={{ fontWeight: 700, mb: 3, color: 'primary.main', textTransform: 'uppercase', fontSize: '0.9rem', letterSpacing: '0.5px' }}>
                  📋 Detailed Factor Inputs
                </Typography>
                <Grid container spacing={3}>
                  <InputsGrid title="Quality & Fundamentals" inputs={stock.quality_inputs} schema={QUALITY_SCHEMA} />
                  <InputsGrid title="Momentum" inputs={stock.momentum_inputs} schema={MOMENTUM_SCHEMA} />
                  <InputsGrid title="Value" inputs={stock.value_inputs} schema={VALUE_SCHEMA} />
                  <InputsGrid title="Growth" inputs={stock.growth_inputs} schema={GROWTH_SCHEMA} />
                  <InputsGrid title="Positioning" inputs={stock.positioning_inputs} schema={POSITIONING_SCHEMA} />
                  <InputsGrid title="Stability" inputs={stock.stability_inputs} schema={STABILITY_SCHEMA} />
                </Grid>
              </Box>
            </AccordionDetails>
          </Accordion>
        );
      })}
    </Box>
  );
};

function InputsGrid({ title, inputs, schema }) {
  const theme = useTheme();

  if (!inputs || typeof inputs !== 'object' || Array.isArray(inputs)) {
    return (
      <Grid item xs={12} sm={6} md={4}>
        <Box sx={{ p: 2, backgroundColor: 'action.hover', borderRadius: 1 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1, fontSize: '0.85rem' }}>
            {title}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            No data available
          </Typography>
        </Box>
      </Grid>
    );
  }

  const rows = schema
    .map(s => ({ ...s, value: inputs[s.key] }))
    .filter(r => r.value != null && r.fmt && typeof r.fmt === 'function');

  if (rows.length === 0) {
    return (
      <Grid item xs={12} sm={6} md={4}>
        <Box sx={{ p: 2, backgroundColor: 'action.hover', borderRadius: 1 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1, fontSize: '0.85rem' }}>
            {title}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            No detailed metrics available
          </Typography>
        </Box>
      </Grid>
    );
  }

  return (
    <Grid item xs={12} sm={6} md={4}>
      <Box sx={{ borderRadius: 1, overflow: 'hidden', border: `1px solid ${theme.palette.divider}` }}>
        <Box sx={{ p: 1.5, backgroundColor: alpha(theme.palette.primary.main, 0.06), borderBottom: `1px solid ${theme.palette.divider}` }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.3px' }}>
            {title}
          </Typography>
        </Box>
        <Box sx={{ p: 1.5 }}>
          {rows.map(r => (
            <Box key={r.key} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', py: 0.75, borderBottom: `1px solid ${alpha(theme.palette.divider, 0.5)}`, '&:last-child': { borderBottom: 'none' } }}>
              <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.8rem' }}>
                {r.label}
              </Typography>
              <Typography
                variant="caption"
                sx={{
                  fontWeight: 600,
                  fontSize: '0.8rem',
                  fontFamily: 'monospace',
                  ml: 1,
                  textAlign: 'right',
                  color: 'text.primary',
                }}
              >
                {r.fmt(r.value)}
              </Typography>
            </Box>
          ))}
        </Box>
      </Box>
    </Grid>
  );
}

export default StockScoreAccordion;

// ─── Input Schemas ────────────────────────────────────────────────────────────
const QUALITY_SCHEMA = [
  { key: 'return_on_equity_pct',           label: 'ROE',                      fmt: v => pct(v, 1) },
  { key: 'return_on_assets_pct',           label: 'ROA',                      fmt: v => pct(v, 1) },
  { key: 'return_on_invested_capital_pct', label: 'ROIC',                     fmt: v => pct(v, 1) },
  { key: 'gross_margin_pct',               label: 'Gross Margin',             fmt: v => pct(v, 1) },
  { key: 'operating_margin_pct',           label: 'Operating Margin',         fmt: v => pct(v, 1) },
  { key: 'profit_margin_pct',              label: 'Profit Margin',            fmt: v => pct(v, 1) },
  { key: 'ebitda_margin_pct',              label: 'EBITDA Margin',            fmt: v => pct(v, 1) },
  { key: 'fcf_to_net_income',              label: 'FCF / Net Income',         fmt: v => num(v, 2) },
  { key: 'operating_cf_to_net_income',     label: 'OCF / Net Income',         fmt: v => num(v, 2) },
  { key: 'debt_to_equity',                 label: 'Debt / Equity',            fmt: v => num(v, 2) },
  { key: 'current_ratio',                  label: 'Current Ratio',            fmt: v => num(v, 2) },
  { key: 'quick_ratio',                    label: 'Quick Ratio',              fmt: v => num(v, 2) },
  { key: 'earnings_surprise_avg',          label: 'Earnings Surprise (4Q)',   fmt: v => pct(v, 2) },
  { key: 'eps_growth_stability',           label: 'EPS Growth Stability',     fmt: v => num(v, 2) },
  { key: 'earnings_beat_rate',             label: 'Earnings Beat Rate',       fmt: v => pct(v, 1) },
  { key: 'consecutive_positive_quarters',  label: 'Consecutive +Q',           fmt: v => num(v, 0) },
  { key: 'estimate_revision_direction',    label: 'Revision Direction',       fmt: v => num(v, 1) },
  { key: 'revision_activity_30d',          label: 'Revision Activity 30d',    fmt: v => num(v, 1) },
  { key: 'estimate_momentum_60d',          label: 'Estimate Momentum 60d',    fmt: v => pct(v, 2) },
  { key: 'estimate_momentum_90d',          label: 'Estimate Momentum 90d',    fmt: v => pct(v, 2) },
  { key: 'revision_trend_score',           label: 'Revision Trend',           fmt: v => num(v, 1) },
  { key: 'payout_ratio',                   label: 'Payout Ratio',             fmt: v => pct(v, 1) },
  { key: 'free_cashflow',                  label: 'Free Cash Flow',           fmt: money },
  { key: 'operating_cashflow',             label: 'Operating Cash Flow',      fmt: money },
  { key: 'total_debt',                     label: 'Total Debt',               fmt: money },
  { key: 'total_cash',                     label: 'Total Cash',               fmt: money },
  { key: 'cash_per_share',                 label: 'Cash / Share',             fmt: v => `$${num(v, 2)}` },
  { key: 'earnings_growth_pct',            label: 'Earnings Growth',          fmt: v => pct(v, 2) },
  { key: 'revenue_growth_pct',             label: 'Revenue Growth',           fmt: v => pct(v, 2) },
  { key: 'earnings_growth_4q_avg',         label: 'Earnings Growth 4Q Avg',   fmt: v => pct(v, 2) },
];

const MOMENTUM_SCHEMA = [
  { key: 'price_vs_sma_50',  label: 'Price vs 50-SMA',  fmt: v => pct(v, 2) },
  { key: 'price_vs_sma_200', label: 'Price vs 200-SMA', fmt: v => pct(v, 2) },
  { key: 'momentum_3m',      label: '3-Month Return',   fmt: v => pct(v, 2) },
  { key: 'momentum_6m',      label: '6-Month Return',   fmt: v => pct(v, 2) },
  { key: 'momentum_12_3',    label: '12-3 Momentum',    fmt: v => pct(v, 2) },
  { key: 'price_vs_52w_high',label: 'Price vs 52w High',fmt: v => pct(v, 2) },
  { key: 'current_price',    label: 'Current Price',    fmt: v => `$${num(v, 2)}` },
  { key: 'rsi',              label: 'RSI (14)',         fmt: v => num(v, 1) },
  { key: 'macd',             label: 'MACD',             fmt: v => num(v, 3) },
];

const VALUE_SCHEMA = [
  { key: 'stock_pe',            label: 'P/E',          fmt: v => num(v, 2) },
  { key: 'stock_forward_pe',    label: 'Forward P/E',  fmt: v => num(v, 2) },
  { key: 'stock_pb',            label: 'P/B',          fmt: v => num(v, 2) },
  { key: 'stock_ps',            label: 'P/S',          fmt: v => num(v, 2) },
  { key: 'stock_ev_ebitda',     label: 'EV / EBITDA',  fmt: v => num(v, 2) },
  { key: 'stock_ev_revenue',    label: 'EV / Revenue', fmt: v => num(v, 2) },
  { key: 'peg_ratio',           label: 'PEG',          fmt: v => num(v, 2) },
  { key: 'stock_dividend_yield',label: 'Dividend Yield', fmt: v => pct(v == null ? null : v * 100, 2) },
];

const GROWTH_SCHEMA = [
  { key: 'revenue_growth_3y_cagr',     label: 'Revenue CAGR (3Y)',       fmt: v => pct(v, 2) },
  { key: 'eps_growth_3y_cagr',         label: 'EPS CAGR (3Y)',           fmt: v => pct(v, 2) },
  { key: 'net_income_growth_yoy',      label: 'Net Income Growth YoY',   fmt: v => pct(v, 2) },
  { key: 'operating_income_growth_yoy',label: 'Op Income Growth YoY',    fmt: v => pct(v, 2) },
  { key: 'gross_margin_trend',         label: 'Gross Margin Trend',      fmt: v => `${num(v, 2)} pp` },
  { key: 'operating_margin_trend',     label: 'Op Margin Trend',         fmt: v => `${num(v, 2)} pp` },
  { key: 'net_margin_trend',           label: 'Net Margin Trend',        fmt: v => `${num(v, 2)} pp` },
  { key: 'roe_trend',                  label: 'ROE Trend',               fmt: v => num(v, 2) },
  { key: 'sustainable_growth_rate',    label: 'Sustainable Growth Rate', fmt: v => pct(v, 2) },
  { key: 'quarterly_growth_momentum',  label: 'Quarterly Growth Mom',    fmt: v => `${num(v, 2)} pp` },
  { key: 'fcf_growth_yoy',             label: 'FCF Growth YoY',          fmt: v => pct(v, 2) },
  { key: 'ocf_growth_yoy',             label: 'OCF Growth YoY',          fmt: v => pct(v, 2) },
  { key: 'asset_growth_yoy',           label: 'Asset Growth YoY',        fmt: v => pct(v, 2) },
];

const POSITIONING_SCHEMA = [
  { key: 'institutional_ownership_pct', label: 'Institutional Own %', fmt: v => pct(v, 1) },
  { key: 'top_10_institutions_pct',     label: 'Top 10 Institutions %', fmt: v => pct(v, 1) },
  { key: 'institutional_holders_count', label: 'Institutional Holders', fmt: v => num(v, 0) },
  { key: 'insider_ownership_pct',       label: 'Insider Own %',       fmt: v => pct(v, 1) },
  { key: 'short_interest_pct',          label: 'Short Interest %',    fmt: v => pct(v, 2) },
  { key: 'short_percent_of_float',      label: 'Short % of Float',    fmt: v => pct(v, 1) },
  { key: 'short_ratio',                 label: 'Days to Cover',       fmt: v => Number(v) < 99999 ? num(v, 2) : '—' },
  { key: 'ad_rating',                   label: 'A/D Rating',          fmt: v => num(v, 1) },
];

const STABILITY_SCHEMA = [
  { key: 'volatility_12m',           label: 'Volatility (12M)',     fmt: v => pct(v, 2) },
  { key: 'downside_volatility',      label: 'Downside Volatility',  fmt: v => pct(v, 2) },
  { key: 'max_drawdown_52w',         label: 'Max Drawdown (52W)',   fmt: v => pct(v, 2) },
  { key: 'beta',                     label: 'Beta vs Market',       fmt: v => num(v, 2) },
  { key: 'volatility_risk_component',label: 'Volatility Risk Score',fmt: v => num(v, 1) },
  { key: 'volume_consistency',       label: 'Volume Consistency',   fmt: v => num(v, 1) },
  { key: 'turnover_velocity',        label: 'Turnover Velocity',    fmt: v => num(v, 1) },
  { key: 'volatility_volume_ratio',  label: 'Volatility / Volume',  fmt: v => num(v, 1) },
  { key: 'daily_spread',             label: 'Daily Spread',         fmt: v => num(v, 1) },
];
