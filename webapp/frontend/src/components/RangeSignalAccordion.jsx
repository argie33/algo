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
import { ExpandMore, TrendingUp, TrendingDown } from '@mui/icons-material';

const RangeSignalAccordion = ({ signals = [] }) => {
  const theme = useTheme();

  if (!signals || signals.length === 0) {
    return (
      <Box sx={{ p: 4, textAlign: 'center' }}>
        <Typography variant="body1" color="text.secondary">
          No range trading signals data found
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
    }
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {signals.map((signal, index) => {
        const config = getSignalConfig(signal.signal);
        if (!config) return null;

        return (
          <Accordion key={`${signal.symbol}-${index}`}defaultExpanded={index === 0} sx={{ mb: 1 }}>
            <AccordionSummary expandIcon={<ExpandMore />}>
              <Grid container alignItems="center" spacing={2} sx={{ width: "100%" }}>
                <Grid item xs="auto">
                  <Chip
                    label={config.label}
                    icon={config.icon}
                    sx={{
                      backgroundColor: alpha(config.color, 0.25),
                      color: config.textColor,
                      fontWeight: 700,
                      height: 32,
                      border: `1.5px solid ${config.color}`,
                    }}
                  />
                </Grid>

                <Grid item xs={12} sm="auto" sx={{ flexGrow: { xs: 1, sm: 0 } }}>
                  <Box>
                    <Typography variant="h5" fontWeight={700}>
                      {signal.symbol}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {signal.company_name}
                    </Typography>
                  </Box>
                </Grid>

                <Grid item xs={12} sm sx={{ flexGrow: 1 }}>
                  <Grid container spacing={2}>
                    <Grid item xs={6} sm="auto">
                      <Box>
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", fontSize: "0.7rem" }}>
                          RANGE HIGH
                        </Typography>
                        <Typography variant="caption" fontWeight={700} sx={{ fontSize: "0.9rem" }}>
                          ${(signal.range_high || 0).toFixed(2)}
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={6} sm="auto">
                      <Box>
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", fontSize: "0.7rem" }}>
                          RANGE LOW
                        </Typography>
                        <Typography variant="caption" fontWeight={700} sx={{ fontSize: "0.9rem" }}>
                          ${(signal.range_low || 0).toFixed(2)}
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={6} sm="auto">
                      <Box>
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", fontSize: "0.7rem" }}>
                          POSITION %
                        </Typography>
                        <Typography variant="caption" fontWeight={700} sx={{ fontSize: "0.9rem" }}>
                          {(signal.range_position || 0).toFixed(1)}%
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={6} sm="auto">
                      <Box>
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", fontSize: "0.7rem" }}>
                          AGE (DAYS)
                        </Typography>
                        <Typography variant="caption" fontWeight={700} sx={{ fontSize: "0.9rem" }}>
                          {signal.range_age_days || 0}
                        </Typography>
                      </Box>
                    </Grid>
                  </Grid>
                </Grid>
              </Grid>
            </AccordionSummary>

            <AccordionDetails sx={{ pt: 3 }}>
              <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom sx={{ fontWeight: 700, mb: 2 }}>
                    Range Metrics
                  </Typography>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        Range Strength
                      </Typography>
                      <Typography variant="body2" fontWeight={700}>
                        {signal.range_strength || 0}
                      </Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        Range Height %
                      </Typography>
                      <Typography variant="body2" fontWeight={700}>
                        {signal.range_height_pct ? `${(signal.range_height_pct).toFixed(2)}%` : '—'}
                      </Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        Signal Type
                      </Typography>
                      <Typography variant="body2" fontWeight={700}>
                        {signal.signal_type || '—'}
                      </Typography>
                    </Box>
                  </Box>
                </Grid>

                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom sx={{ fontWeight: 700, mb: 2 }}>
                    Entry & Exit
                  </Typography>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        Entry Price
                      </Typography>
                      <Typography variant="body2" fontWeight={700}>
                        ${(signal.entry_price || 0).toFixed(2)}
                      </Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        Stop Level
                      </Typography>
                      <Typography variant="body2" fontWeight={700}>
                        ${(signal.stop_level || 0).toFixed(2)}
                      </Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        Target 1 / Target 2
                      </Typography>
                      <Typography variant="body2" fontWeight={700}>
                        ${(signal.target_1 || 0).toFixed(2)} / ${(signal.target_2 || 0).toFixed(2)}
                      </Typography>
                    </Box>
                  </Box>
                </Grid>

                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom sx={{ fontWeight: 700, mb: 2 }}>
                    Quality & Risk
                  </Typography>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        Breakout Quality
                      </Typography>
                      <Typography variant="body2" fontWeight={700}>
                        {signal.breakout_quality || '—'}
                      </Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        Entry Quality Score
                      </Typography>
                      <Typography variant="body2" fontWeight={700}>
                        {signal.entry_quality_score ? `${(signal.entry_quality_score).toFixed(1)}/100` : '—'}
                      </Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        Risk/Reward Ratio
                      </Typography>
                      <Typography variant="body2" fontWeight={700}>
                        {signal.risk_reward_ratio ? `${(signal.risk_reward_ratio).toFixed(2)}:1` : '—'}
                      </Typography>
                    </Box>
                  </Box>
                </Grid>

                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom sx={{ fontWeight: 700, mb: 2 }}>
                    Technical Indicators
                  </Typography>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        RSI / ADX / ATR
                      </Typography>
                      <Typography variant="body2" fontWeight={700}>
                        {signal.rsi ? `${(signal.rsi).toFixed(1)}` : '—'} / {signal.adx ? `${(signal.adx).toFixed(1)}` : '—'} / {signal.atr ? `${(signal.atr).toFixed(2)}` : '—'}
                      </Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        Market Stage
                      </Typography>
                      <Typography variant="body2" fontWeight={700}>
                        {signal.market_stage || '—'}
                      </Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        SATA Score
                      </Typography>
                      <Typography variant="body2" fontWeight={700}>
                        {signal.sata_score ? `${(signal.sata_score).toFixed(1)}/10` : '—'}
                      </Typography>
                    </Box>
                  </Box>
                </Grid>
              </Grid>
            </AccordionDetails>
          </Accordion>
        );
      })}
    </Box>
  );
};

export default RangeSignalAccordion;
