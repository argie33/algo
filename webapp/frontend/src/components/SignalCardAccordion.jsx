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
          bgColor: alpha(theme.palette.success.main, 0.08),
          borderColor: alpha(theme.palette.success.main, 0.3),
          icon: <TrendingUp sx={{ fontSize: 20, color: theme.palette.success.main }} />,
          label: 'BUY',
        };
      case 'SELL':
        return {
          color: theme.palette.error.main,
          bgColor: alpha(theme.palette.error.main, 0.08),
          borderColor: alpha(theme.palette.error.main, 0.3),
          icon: <TrendingDown sx={{ fontSize: 20, color: theme.palette.error.main }} />,
          label: 'SELL',
        };
      default:
        return {
          color: theme.palette.warning.main,
          bgColor: alpha(theme.palette.warning.main, 0.08),
          borderColor: alpha(theme.palette.warning.main, 0.3),
          icon: <ShowChart sx={{ fontSize: 20, color: theme.palette.warning.main }} />,
          label: 'HOLD',
        };
    }
  };

  const DataField = ({ label, value, format = 'text', color = null }) => (
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
        {format === 'currency' && value ? `$${parseFloat(value).toFixed(2)}` : value || '—'}
      </Typography>
    </Box>
  );

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {signals.map((signal, index) => {
        const config = getSignalConfig(signal.signal);
        const currentGain = signal.current_gain_loss_pct || signal.current_gain_pct || 0;
        const gainColor = currentGain >= 0 ? theme.palette.success.main : theme.palette.error.main;

        return (
          <Accordion
            key={`${signal.symbol}-${index}`}
            defaultExpanded={index === 0}
            component={Paper}
            elevation={0}
            sx={{
              backgroundColor: config.bgColor,
              border: `1px solid ${config.borderColor}`,
              borderRadius: 1.5,
              transition: 'all 0.2s ease',
              '&:hover': {
                boxShadow: theme.shadows[2],
                backgroundColor: alpha(config.bgColor, 1.2),
              },
              '&.Mui-expanded': {
                margin: 0,
              },
              '&:before': { display: 'none' },
            }}
          >
            <AccordionSummary
              expandIcon={<ExpandMore />}
              sx={{
                backgroundColor: 'transparent',
                py: 2,
                px: 3,
                '&:hover': {
                  backgroundColor: alpha(config.color, 0.05),
                },
              }}
            >
              {/* Icon + Symbol */}
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, minWidth: 200 }}>
                {config.icon}
                <Box>
                  <Typography
                    variant="subtitle1"
                    sx={{
                      fontWeight: 700,
                      color: theme.palette.text.primary,
                      fontSize: '1.1rem',
                    }}
                  >
                    {signal.symbol}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {signal.company_name || 'N/A'}
                  </Typography>
                </Box>
              </Box>

              {/* Signal Badge */}
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexGrow: 1, ml: 2 }}>
                <Chip
                  label={config.label}
                  icon={config.icon}
                  sx={{
                    backgroundColor: config.color,
                    color: 'white',
                    fontWeight: 700,
                    height: 32,
                    '& .MuiChip-icon': {
                      color: 'white !important',
                      marginLeft: '4px',
                    },
                  }}
                />
              </Box>

              {/* Performance Metric */}
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 3, ml: 'auto', minWidth: 200 }}>
                <Box sx={{ textAlign: 'right' }}>
                  <Typography variant="caption" color="text.secondary" display="block">
                    Current Gain
                  </Typography>
                  <Typography
                    sx={{
                      fontWeight: 700,
                      fontSize: '1.1rem',
                      color: gainColor,
                    }}
                  >
                    {currentGain ? `${currentGain.toFixed(2)}%` : '—'}
                  </Typography>
                </Box>
                <Box sx={{ textAlign: 'right', minWidth: 100 }}>
                  <Typography variant="caption" color="text.secondary" display="block">
                    Date
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 500 }}>
                    {signal.date || '—'}
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
                {/* Price Data Section */}
                <Grid item xs={12} sm={6} md={3}>
                  <Typography
                    variant="overline"
                    sx={{
                      fontWeight: 700,
                      color: 'primary.main',
                      display: 'block',
                      mb: 2,
                      letterSpacing: 0.5,
                    }}
                  >
                    Price Data
                  </Typography>
                  <DataField label="Open" value={signal.open} format="currency" />
                  <DataField label="High" value={signal.high} format="currency" />
                  <DataField label="Low" value={signal.low} format="currency" />
                  <DataField label="Close" value={signal.close} format="currency" />
                </Grid>

                {/* Entry & Stop Section */}
                <Grid item xs={12} sm={6} md={3}>
                  <Typography
                    variant="overline"
                    sx={{
                      fontWeight: 700,
                      color: 'primary.main',
                      display: 'block',
                      mb: 2,
                      letterSpacing: 0.5,
                    }}
                  >
                    Entry & Stop
                  </Typography>
                  <DataField label="Buy Level" value={signal.buylevel} format="currency" />
                  <DataField label="Stop Level" value={signal.stoplevel} format="currency" />
                  <DataField label="Initial Stop" value={signal.initial_stop} format="currency" />
                  <DataField label="Trailing Stop" value={signal.trailing_stop} format="currency" />
                </Grid>

                {/* Technical Indicators */}
                <Grid item xs={12} sm={6} md={3}>
                  <Typography
                    variant="overline"
                    sx={{
                      fontWeight: 700,
                      color: 'primary.main',
                      display: 'block',
                      mb: 2,
                      letterSpacing: 0.5,
                    }}
                  >
                    Technical Indicators
                  </Typography>
                  <DataField label="Pivot Price" value={signal.pivot_price} format="currency" />
                  <DataField label="RS Rating" value={signal.rs_rating?.toFixed(1)} />
                  <DataField label="Base Type" value={signal.base_type} />
                  <DataField label="Base Length (Days)" value={signal.base_length_days} />
                </Grid>

                {/* Risk Management */}
                <Grid item xs={12} sm={6} md={3}>
                  <Typography
                    variant="overline"
                    sx={{
                      fontWeight: 700,
                      color: 'primary.main',
                      display: 'block',
                      mb: 2,
                      letterSpacing: 0.5,
                    }}
                  >
                    Risk Management
                  </Typography>
                  <DataField
                    label="Risk/Reward Ratio"
                    value={signal.risk_reward_ratio?.toFixed(2)}
                  />
                  <DataField label="Signal Strength" value={signal.strength} />
                  <DataField label="Timeframe" value={signal.timeframe} />
                  <Box sx={{ mt: 1.5 }}>
                    <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mb: 0.5 }}>
                      In Position
                    </Typography>
                    <Chip
                      label={signal.inposition ? 'Active' : 'Inactive'}
                      size="small"
                      color={signal.inposition ? 'success' : 'default'}
                      variant="outlined"
                    />
                  </Box>
                </Grid>

                {/* Position Performance */}
                {signal.days_in_position && (
                  <Grid item xs={12} sm={6} md={3}>
                    <Typography
                      variant="overline"
                      sx={{
                        fontWeight: 700,
                        color: 'primary.main',
                        display: 'block',
                        mb: 2,
                        letterSpacing: 0.5,
                      }}
                    >
                      Position Performance
                    </Typography>
                    <DataField label="Days in Position" value={signal.days_in_position} />
                    <DataField
                      label="Avg Volume (50d)"
                      value={signal.avg_volume_50d ? signal.avg_volume_50d.toLocaleString() : null}
                    />
                    <DataField label="Volume Surge" value={signal.volume_surge_pct} />
                    <DataField label="Current Volume" value={signal.volume ? signal.volume.toLocaleString() : null} />
                  </Grid>
                )}

                {/* Trade Quality */}
                {(signal.breakout_quality || signal.signal_type) && (
                  <Grid item xs={12} sm={6} md={3}>
                    <Typography
                      variant="overline"
                      sx={{
                        fontWeight: 700,
                        color: 'primary.main',
                        display: 'block',
                        mb: 2,
                        letterSpacing: 0.5,
                      }}
                    >
                      Trade Quality
                    </Typography>
                    <DataField label="Breakout Quality" value={signal.breakout_quality?.toFixed(1)} />
                    <DataField label="Signal Type" value={signal.signal_type} />
                    {signal.buy_zone_start && signal.buy_zone_end && (
                      <DataField
                        label="Buy Zone"
                        value={`$${signal.buy_zone_start.toFixed(2)} - $${signal.buy_zone_end.toFixed(2)}`}
                      />
                    )}
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
