import React from 'react';
import {
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Grid,
  Box,
  Typography,
  Chip,
  LinearProgress,
  useTheme,
  alpha
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';

const SignalCardAccordion = ({ signals = [] }) => {
  const theme = useTheme();

  if (!signals || signals.length === 0) {
    return (
      <Box sx={{ p: 3, textAlign: 'center' }}>
        <Typography variant="body2" color="text.secondary">
          No trading signals data found
        </Typography>
      </Box>
    );
  }

  const getSignalColor = (signal) => {
    if (signal === 'BUY') return theme.palette.success.main;
    if (signal === 'SELL') return theme.palette.error.main;
    return theme.palette.warning.main;
  };

  const getSignalBackgroundColor = (signal) => {
    if (signal === 'BUY') return alpha(theme.palette.success.main, 0.1);
    if (signal === 'SELL') return alpha(theme.palette.error.main, 0.1);
    return alpha(theme.palette.warning.main, 0.1);
  };

  return (
    <Box>
      {signals.map((signal, index) => (
        <Accordion
          key={index}
          defaultExpanded={index === 0}
          sx={{
            mb: 2,
            backgroundColor: getSignalBackgroundColor(signal.signal),
            border: `1px solid ${alpha(getSignalColor(signal.signal), 0.3)}`,
            '&:before': { display: 'none' },
            '&.Mui-expanded': {
              m: 0,
            },
          }}
        >
          <AccordionSummary
            expandIcon={<ExpandMoreIcon />}
            sx={{
              backgroundColor: 'transparent',
              borderBottom: `1px solid ${alpha(getSignalColor(signal.signal), 0.2)}`,
              py: 2,
              px: 3,
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, width: '100%' }}>
              <Typography
                variant="subtitle1"
                sx={{
                  fontWeight: 700,
                  color: getSignalColor(signal.signal),
                  minWidth: 100,
                }}
              >
                {signal.symbol}
              </Typography>
              <Chip
                label={signal.signal}
                size="small"
                sx={{
                  backgroundColor: getSignalColor(signal.signal),
                  color: 'white',
                  fontWeight: 600,
                  minWidth: 80,
                }}
              />
              <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>
                {signal.date}
              </Typography>
            </Box>
          </AccordionSummary>

          <AccordionDetails
            sx={{
              backgroundColor: 'background.paper',
              borderTop: `1px solid ${theme.palette.divider}`,
              pt: 3,
              pb: 3,
            }}
          >
            <Grid container spacing={3}>
              {/* Price Data */}
              <Grid item xs={12}>
                <Typography
                  variant="subtitle2"
                  sx={{ fontWeight: 700, mb: 2, color: 'primary.main' }}
                >
                  Price Data
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Open
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        ${signal.open ? parseFloat(signal.open).toFixed(2) : 'N/A'}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        High
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        ${signal.high ? parseFloat(signal.high).toFixed(2) : 'N/A'}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Low
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        ${signal.low ? parseFloat(signal.low).toFixed(2) : 'N/A'}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Close
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        ${signal.close ? parseFloat(signal.close).toFixed(2) : 'N/A'}
                      </Typography>
                    </Box>
                  </Grid>
                </Grid>
              </Grid>

              {/* Signals */}
              <Grid item xs={12}>
                <Typography
                  variant="subtitle2"
                  sx={{ fontWeight: 700, mb: 2, color: 'primary.main' }}
                >
                  Signals
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Buy Level
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        ${signal.buylevel ? parseFloat(signal.buylevel).toFixed(2) : 'N/A'}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Stop Level
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        ${signal.stoplevel ? parseFloat(signal.stoplevel).toFixed(2) : 'N/A'}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Strength
                      </Typography>
                      <Typography
                        variant="body2"
                        sx={{
                          fontWeight: 600,
                          color: signal.strength >= 75 ? 'success.main' : 'warning.main'
                        }}
                      >
                        {signal.strength || 'N/A'}%
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Timeframe
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {signal.timeframe || 'N/A'}
                      </Typography>
                    </Box>
                  </Grid>
                </Grid>
              </Grid>

              {/* Risk Management */}
              <Grid item xs={12}>
                <Typography
                  variant="subtitle2"
                  sx={{ fontWeight: 700, mb: 2, color: 'primary.main' }}
                >
                  Risk Management
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Initial Stop
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        ${signal.initial_stop ? parseFloat(signal.initial_stop).toFixed(2) : 'N/A'}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Trailing Stop
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        ${signal.trailing_stop ? parseFloat(signal.trailing_stop).toFixed(2) : 'N/A'}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Risk/Reward
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {signal.risk_reward_ratio ? parseFloat(signal.risk_reward_ratio).toFixed(2) : 'N/A'}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        In Position
                      </Typography>
                      <Chip
                        label={signal.inposition ? 'Yes' : 'No'}
                        size="small"
                        color={signal.inposition ? 'success' : 'default'}
                        variant="outlined"
                      />
                    </Box>
                  </Grid>
                </Grid>
              </Grid>

              {/* Technical Indicators */}
              <Grid item xs={12}>
                <Typography
                  variant="subtitle2"
                  sx={{ fontWeight: 700, mb: 2, color: 'primary.main' }}
                >
                  Technical Indicators
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Pivot Price
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        ${signal.pivot_price ? parseFloat(signal.pivot_price).toFixed(2) : 'N/A'}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        RS Rating
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {signal.rs_rating ? parseFloat(signal.rs_rating).toFixed(1) : 'N/A'}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Base Type
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {signal.base_type || 'N/A'}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Base Length
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {signal.base_length_days || 'N/A'} days
                      </Typography>
                    </Box>
                  </Grid>
                </Grid>
              </Grid>

              {/* Performance Metrics */}
              <Grid item xs={12}>
                <Typography
                  variant="subtitle2"
                  sx={{ fontWeight: 700, mb: 2, color: 'primary.main' }}
                >
                  Performance Metrics
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Current Gain
                      </Typography>
                      <Typography
                        variant="body2"
                        sx={{
                          fontWeight: 600,
                          color: signal.current_gain_pct >= 0 ? 'success.main' : 'error.main'
                        }}
                      >
                        {signal.current_gain_pct ? parseFloat(signal.current_gain_pct).toFixed(2) : 'N/A'}%
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Days in Position
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {signal.days_in_position || 'N/A'}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Avg Volume (50d)
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {signal.avg_volume_50d ? signal.avg_volume_50d.toLocaleString() : 'N/A'}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Volume Surge
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {signal.volume_surge_pct ? parseFloat(signal.volume_surge_pct).toFixed(2) : 'N/A'}%
                      </Typography>
                    </Box>
                  </Grid>
                </Grid>
              </Grid>

              {/* Position Management */}
              <Grid item xs={12}>
                <Typography
                  variant="subtitle2"
                  sx={{ fontWeight: 700, mb: 2, color: 'primary.main' }}
                >
                  Position Management
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Volume
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {signal.volume ? signal.volume.toLocaleString() : 'N/A'}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Breakout Quality
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {signal.breakout_quality ? parseFloat(signal.breakout_quality).toFixed(1) : 'N/A'}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Signal Type
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {signal.signal_type || 'N/A'}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Buy Zone
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        ${signal.buy_zone_start ? parseFloat(signal.buy_zone_start).toFixed(2) : 'N/A'} - ${signal.buy_zone_end ? parseFloat(signal.buy_zone_end).toFixed(2) : 'N/A'}
                      </Typography>
                    </Box>
                  </Grid>
                </Grid>
              </Grid>
            </Grid>
          </AccordionDetails>
        </Accordion>
      ))}
    </Box>
  );
};

export default SignalCardAccordion;
