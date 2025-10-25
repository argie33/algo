import React from 'react';
import {
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Grid,
  Box,
  Typography,
  Chip,
  Paper,
  useTheme,
  alpha,
  Tooltip,
  LinearProgress,
} from '@mui/material';
import { ExpandMore, TrendingUp, TrendingDown, ShowChart } from '@mui/icons-material';

const SignalCardAccordion = ({ signals = [] }) => {
  const theme = useTheme();

  if (!signals || signals.length === 0) {
    return (
      <Box sx={{ p: 4, textAlign: 'center' }}>
        <Typography variant="body1" color="text.secondary">
          No trading signals data found
        </Typography>
      </Box>
    );
  }

  const getSignalConfig = (signalType) => {
    switch (signalType?.toUpperCase()) {
      case 'BUY':
        return {
          color: theme.palette.success.main,
          bgColor: alpha(theme.palette.success.main, 0.1),
          borderColor: alpha(theme.palette.success.main, 0.2),
          icon: <TrendingUp sx={{ fontSize: 20, color: theme.palette.success.main }} />,
          label: 'BUY',
          textColor: theme.palette.success.dark,
        };
      case 'SELL':
        return {
          color: theme.palette.error.main,
          bgColor: alpha(theme.palette.error.main, 0.1),
          borderColor: alpha(theme.palette.error.main, 0.2),
          icon: <TrendingDown sx={{ fontSize: 20, color: theme.palette.error.main }} />,
          label: 'SELL',
          textColor: theme.palette.error.dark,
        };
      default:
        return {
          color: theme.palette.warning.main,
          bgColor: alpha(theme.palette.warning.main, 0.1),
          borderColor: alpha(theme.palette.warning.main, 0.2),
          icon: <ShowChart sx={{ fontSize: 20, color: theme.palette.warning.main }} />,
          label: 'HOLD',
          textColor: theme.palette.warning.dark,
        };
    }
  };

  const DataField = ({ label, value, format = 'text', color = null, unit = '' }) => {
    let displayValue = value;
    if (format === 'currency' && value) {
      displayValue = `$${parseFloat(value).toFixed(2)}`;
    } else if (format === 'percent' && value !== null && value !== undefined) {
      displayValue = `${parseFloat(value).toFixed(2)}%`;
    } else if (format === 'number' && value !== null && value !== undefined) {
      displayValue = parseFloat(value).toFixed(2);
    } else if (!value && value !== 0) {
      displayValue = '—';
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

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {signals.map((signal, index) => {
        const config = getSignalConfig(signal.signal);
        const currentGain = signal.current_gain_loss_pct || signal.current_gain_pct || signal.current_pnl_pct || 0;
        const gainColor = currentGain >= 0 ? theme.palette.success.main : theme.palette.error.main;
        const currentPrice = signal.current_price || signal.currentPrice || signal.close || 0;

        return (
          <Accordion
            key={`${signal.symbol}-${index}`}
            defaultExpanded={index === 0}
            component={Paper}
            elevation={1}
            sx={{
              backgroundColor: 'background.paper',
              border: `2px solid ${config.borderColor}`,
              borderRadius: 1.5,
              transition: 'all 0.3s ease',
              marginBottom: 2,
              '&:hover': {
                boxShadow: theme.shadows[4],
                borderColor: config.color,
              },
              '&.Mui-expanded': {
                margin: '0 0 16px 0',
              },
              '&:before': { display: 'none' },
            }}
          >
            <AccordionSummary
              expandIcon={<ExpandMore />}
              sx={{
                backgroundColor: 'transparent',
                py: 2.5,
                px: 3,
                transition: 'all 0.2s ease',
                '&:hover': {
                  backgroundColor: alpha(config.color, 0.08),
                },
              }}
            >
              {/* Icon + Symbol + Price Summary */}
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, minWidth: 280 }}>
                {config.icon}
                <Box>
                  <Typography
                    variant="subtitle1"
                    sx={{
                      fontWeight: 700,
                      color: config.textColor,
                      fontSize: '1.1rem',
                    }}
                  >
                    {signal.symbol}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {signal.company_name || 'N/A'}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', fontSize: '0.8rem', mt: 0.3 }}>
                    ${currentPrice.toFixed(2)}
                  </Typography>
                </Box>
              </Box>

              {/* Signal Badge */}
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexGrow: 1, ml: 2 }}>
                <Chip
                  label={config.label}
                  icon={config.icon}
                  sx={{
                    backgroundColor: alpha(config.color, 0.25),
                    color: config.textColor,
                    fontWeight: 700,
                    height: 32,
                    border: `1.5px solid ${config.color}`,
                    '& .MuiChip-icon': {
                      color: config.textColor + ' !important',
                      marginLeft: '4px',
                    },
                  }}
                />
              </Box>

              {/* Performance Metrics */}
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 3, ml: 'auto', minWidth: 300 }}>
                <Box sx={{ textAlign: 'right' }}>
                  <Typography variant="caption" color="text.secondary" display="block">
                    Entry Price
                  </Typography>
                  <Typography
                    sx={{
                      fontWeight: 700,
                      fontSize: '1rem',
                      color: 'text.primary',
                    }}
                  >
                    ${(signal.entry_price || signal.buylevel || 0).toFixed(2)}
                  </Typography>
                </Box>
                <Box sx={{ textAlign: 'right' }}>
                  <Typography variant="caption" color="text.secondary" display="block">
                    Current Gain
                  </Typography>
                  <Typography
                    sx={{
                      fontWeight: 700,
                      fontSize: '1rem',
                      color: gainColor,
                    }}
                  >
                    {currentGain ? `${currentGain.toFixed(2)}%` : '—'}
                  </Typography>
                </Box>
                <Box sx={{ textAlign: 'right', minWidth: 100 }}>
                  <Typography variant="caption" color="text.secondary" display="block">
                    Days In Position
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {signal.days_in_position || 0}
                  </Typography>
                </Box>
              </Box>
            </AccordionSummary>

            <AccordionDetails
              sx={{
                backgroundColor: 'background.paper',
                borderTop: `1px solid ${config.borderColor}`,
                pt: 3,
                pb: 3,
                px: 3,
              }}
            >
              <Grid container spacing={3}>
                {/* PRICE DATA */}
                <Grid item xs={12} sm={6} md={4} lg={2.4}>
                  <Typography variant="overline" sx={{ fontWeight: 700, color: 'primary.main', display: 'block', mb: 2 }}>
                    Price Data
                  </Typography>
                  <DataField label="Open" value={signal.open} format="currency" />
                  <DataField label="High" value={signal.high} format="currency" />
                  <DataField label="Low" value={signal.low} format="currency" />
                  <DataField label="Close" value={signal.close} format="currency" />
                  <DataField label="Current" value={currentPrice} format="currency" />
                </Grid>

                {/* ENTRY & LEVELS */}
                <Grid item xs={12} sm={6} md={4} lg={2.4}>
                  <Typography variant="overline" sx={{ fontWeight: 700, color: 'primary.main', display: 'block', mb: 2 }}>
                    Entry & Levels
                  </Typography>
                  <DataField label="Buy Level" value={signal.buylevel || signal.buy_level} format="currency" />
                  <DataField label="Entry Price" value={signal.entry_price} format="currency" />
                  <DataField label="Stop Level" value={signal.stoplevel || signal.stop_level} format="currency" />
                  <DataField label="Initial Stop" value={signal.initial_stop} format="currency" />
                  <DataField label="Trailing Stop" value={signal.trailing_stop} format="currency" />
                </Grid>

                {/* TECHNICAL INDICATORS */}
                <Grid item xs={12} sm={6} md={4} lg={2.4}>
                  <Typography variant="overline" sx={{ fontWeight: 700, color: 'primary.main', display: 'block', mb: 2 }}>
                    Technical
                  </Typography>
                  <DataField label="RSI" value={signal.rsi} format="number" />
                  <DataField label="ADX" value={signal.adx} format="number" />
                  <DataField label="ATR" value={signal.atr} format="number" />
                  <DataField label="RS Rating" value={signal.rs_rating} format="number" />
                  <DataField label="Pivot Price" value={signal.pivot_price} format="currency" />
                </Grid>

                {/* MOVING AVERAGES */}
                <Grid item xs={12} sm={6} md={4} lg={2.4}>
                  <Typography variant="overline" sx={{ fontWeight: 700, color: 'primary.main', display: 'block', mb: 2 }}>
                    Moving Avg
                  </Typography>
                  <DataField label="% from EMA21" value={signal.pct_from_ema_21} format="percent" />
                  <DataField label="% from SMA50" value={signal.pct_from_sma_50} format="percent" />
                  <DataField label="% from SMA200" value={signal.pct_from_sma_200} format="percent" />
                  <DataField label="Daily Range %" value={signal.daily_range_pct} format="percent" />
                </Grid>

                {/* VOLUME ANALYSIS */}
                <Grid item xs={12} sm={6} md={4} lg={2.4}>
                  <Typography variant="overline" sx={{ fontWeight: 700, color: 'primary.main', display: 'block', mb: 2 }}>
                    Volume
                  </Typography>
                  <DataField label="Current Volume" value={signal.volume ? parseInt(signal.volume).toLocaleString() : null} />
                  <DataField label="Avg 50d" value={signal.avg_volume_50d ? parseInt(signal.avg_volume_50d).toLocaleString() : null} />
                  <DataField label="Volume Surge %" value={signal.volume_surge_pct} format="percent" />
                  <DataField label="Volume Ratio" value={signal.volume_ratio} format="number" />
                  <DataField label="Vol Percentile" value={signal.volume_percentile} format="percent" />
                </Grid>

                {/* RISK & REWARD */}
                <Grid item xs={12} sm={6} md={4} lg={2.4}>
                  <Typography variant="overline" sx={{ fontWeight: 700, color: 'primary.main', display: 'block', mb: 2 }}>
                    Risk & Reward
                  </Typography>
                  <DataField label="Risk/Reward Ratio" value={signal.risk_reward_ratio} format="number" />
                  <DataField label="Risk %" value={signal.risk_pct} format="percent" />
                  <DataField label="Signal Strength" value={signal.strength} format="number" />
                  <DataField label="Position Size %" value={signal.position_size_recommendation} format="percent" />
                </Grid>

                {/* ENTRY QUALITY */}
                <Grid item xs={12} sm={6} md={4} lg={2.4}>
                  <Typography variant="overline" sx={{ fontWeight: 700, color: 'primary.main', display: 'block', mb: 2 }}>
                    Entry Quality
                  </Typography>
                  <DataField label="Entry Quality Score" value={signal.entry_quality_score} format="number" />
                  <DataField label="Breakout Quality" value={signal.breakout_quality} format="number" />
                  <Box sx={{ mt: 1.5 }}>
                    <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mb: 0.5 }}>
                      Minervini Template
                    </Typography>
                    <Chip
                      label={signal.passes_minervini_template ? 'Pass' : 'Fail'}
                      size="small"
                      color={signal.passes_minervini_template ? 'success' : 'default'}
                      variant="outlined"
                    />
                  </Box>
                </Grid>

                {/* MARKET STAGE */}
                <Grid item xs={12} sm={6} md={4} lg={2.4}>
                  <Typography variant="overline" sx={{ fontWeight: 700, color: 'primary.main', display: 'block', mb: 2 }}>
                    Market Stage
                  </Typography>
                  <DataField label="Market Stage" value={signal.market_stage} />
                  <DataField label="Stage Number" value={signal.stage_number} format="number" />
                  <DataField label="Stage Confidence" value={signal.stage_confidence} format="percent" />
                  <DataField label="Substage" value={signal.substage} />
                </Grid>

                {/* PROFIT TARGETS */}
                <Grid item xs={12} sm={6} md={4} lg={2.4}>
                  <Typography variant="overline" sx={{ fontWeight: 700, color: 'primary.main', display: 'block', mb: 2 }}>
                    Profit Targets
                  </Typography>
                  <DataField label="Target +8%" value={signal.profit_target_8pct} format="currency" />
                  <DataField label="Target +20%" value={signal.profit_target_20pct} format="currency" />
                  <DataField label="Target +25%" value={signal.profit_target_25pct} format="currency" />
                  <DataField label="Sell Level" value={signal.sell_level || signal.selllevel} format="currency" />
                </Grid>

                {/* CURRENT PERFORMANCE */}
                {signal.days_in_position > 0 && (
                  <Grid item xs={12} sm={6} md={4} lg={2.4}>
                    <Typography variant="overline" sx={{ fontWeight: 700, color: 'primary.main', display: 'block', mb: 2 }}>
                      Trade Performance
                    </Typography>
                    <DataField label="Current P&L %" value={signal.current_pnl_pct} format="percent" color={signal.current_pnl_pct >= 0 ? theme.palette.success.main : theme.palette.error.main} />
                    <DataField label="R Multiple" value={signal.current_r_multiple} format="number" />
                    <DataField label="Max Fav Excurse" value={signal.max_favorable_excursion_pct} format="percent" />
                    <DataField label="Max Adv Excurse" value={signal.max_adverse_excursion_pct} format="percent" color={theme.palette.error.light} />
                  </Grid>
                )}

                {/* TRADE QUALITY */}
                <Grid item xs={12} sm={6} md={4} lg={2.4}>
                  <Typography variant="overline" sx={{ fontWeight: 700, color: 'primary.main', display: 'block', mb: 2 }}>
                    Trade Quality
                  </Typography>
                  <DataField label="Base Type" value={signal.base_type} />
                  <DataField label="Base Length" value={signal.base_length_days} unit="days" format="number" />
                  <DataField label="Timeframe" value={signal.timeframe} />
                  <Box sx={{ mt: 1.5 }}>
                    <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mb: 0.5 }}>
                      In Position
                    </Typography>
                    <Chip
                      label={signal.inposition || signal.in_position ? 'Active' : 'Inactive'}
                      size="small"
                      color={signal.inposition || signal.in_position ? 'success' : 'default'}
                      variant="outlined"
                    />
                  </Box>
                </Grid>

                {/* EXIT TRIGGERS */}
                {(signal.exit_trigger_1_price || signal.exit_trigger_2_price) && (
                  <Grid item xs={12} sm={6} md={4} lg={2.4}>
                    <Typography variant="overline" sx={{ fontWeight: 700, color: 'primary.main', display: 'block', mb: 2 }}>
                      Exit Triggers
                    </Typography>
                    <DataField label="Trigger 1" value={signal.exit_trigger_1_price} format="currency" />
                    <DataField label="Trigger 2" value={signal.exit_trigger_2_price} format="currency" />
                    <DataField label="Trigger 3" value={signal.exit_trigger_3_price} format="currency" />
                    <DataField label="Trigger 4" value={signal.exit_trigger_4_price} format="currency" />
                  </Grid>
                )}

                {/* BUY ZONE */}
                {signal.buy_zone_start && signal.buy_zone_end && (
                  <Grid item xs={12} sm={6} md={4} lg={2.4}>
                    <Typography variant="overline" sx={{ fontWeight: 700, color: 'primary.main', display: 'block', mb: 2 }}>
                      Buy Zone
                    </Typography>
                    <DataField
                      label="Start"
                      value={signal.buy_zone_start}
                      format="currency"
                    />
                    <DataField
                      label="End"
                      value={signal.buy_zone_end}
                      format="currency"
                    />
                    <DataField
                      label="Width"
                      value={signal.buy_zone_end - signal.buy_zone_start}
                      format="currency"
                    />
                  </Grid>
                )}
              </Grid>
            </AccordionDetails>
          </Accordion>
        );
      })}
    </Box>
  );
};

export default SignalCardAccordion;
