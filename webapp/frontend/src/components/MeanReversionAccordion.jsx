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

const MeanReversionAccordion = ({ signals = [] }) => {
  const theme = useTheme();

  if (!signals || signals.length === 0) {
    return (
      <Box sx={{ p: 4, textAlign: 'center' }}>
        <Typography variant="body1" color="text.secondary">
          No mean reversion signals data found
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
          <Accordion key={`${signal.symbol}-${index}`} defaultExpanded={index === 0} sx={{ mb: 1 }}>
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
                          RSI(2)
                        </Typography>
                        <Typography
                          variant="caption"
                          fontWeight={700}
                          sx={{
                            fontSize: "0.9rem",
                            color: signal.rsi_2 && signal.rsi_2 < 10 ? theme.palette.success.main : 'text.primary'
                          }}
                        >
                          {signal.rsi_2 ? (signal.rsi_2).toFixed(1) : '—'}
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={6} sm="auto">
                      <Box>
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", fontSize: "0.7rem" }}>
                          % ABOVE 200 SMA
                        </Typography>
                        <Typography variant="caption" fontWeight={700} sx={{ fontSize: "0.9rem" }}>
                          {signal.pct_above_200sma ? (signal.pct_above_200sma).toFixed(2) : '—'}%
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={6} sm="auto">
                      <Box>
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", fontSize: "0.7rem" }}>
                          CONFLUENCE
                        </Typography>
                        <Typography variant="caption" fontWeight={700} sx={{ fontSize: "0.9rem" }}>
                          {signal.confluence_score ? (signal.confluence_score).toFixed(0) : '—'}
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={6} sm="auto">
                      <Box>
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", fontSize: "0.7rem" }}>
                          PRICE
                        </Typography>
                        <Typography variant="caption" fontWeight={700} sx={{ fontSize: "0.9rem" }}>
                          ${(signal.close || 0).toFixed(2)}
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
                    Connors RSI System
                  </Typography>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        RSI(2) - Oversold Signal
                      </Typography>
                      <Typography variant="body2" fontWeight={700} sx={{ color: signal.rsi_2 && signal.rsi_2 < 10 ? theme.palette.success.main : 'text.primary' }}>
                        {signal.rsi_2 ? (signal.rsi_2).toFixed(2) : '—'} {signal.rsi_2 && signal.rsi_2 < 10 ? '⚡ EXTREME' : ''}
                      </Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        Confluence Score
                      </Typography>
                      <Typography variant="body2" fontWeight={700}>
                        {signal.confluence_score ? `${(signal.confluence_score).toFixed(0)}/10` : '—'}
                      </Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        % Above 200 SMA
                      </Typography>
                      <Typography variant="body2" fontWeight={700}>
                        {signal.pct_above_200sma ? `${(signal.pct_above_200sma).toFixed(2)}%` : '—'}
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
                        Target Estimate
                      </Typography>
                      <Typography variant="body2" fontWeight={700}>
                        ${(signal.target_estimate || 0).toFixed(2)}
                      </Typography>
                    </Box>
                  </Box>
                </Grid>

                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom sx={{ fontWeight: 700, mb: 2 }}>
                    Moving Averages
                  </Typography>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        SMA 5 / SMA 20 / SMA 50
                      </Typography>
                      <Typography variant="body2" fontWeight={700}>
                        ${signal.sma_5 ? (signal.sma_5).toFixed(2) : '—'} / ${signal.sma_20 ? (signal.sma_20).toFixed(2) : '—'} / ${signal.sma_50 ? (signal.sma_50).toFixed(2) : '—'}
                      </Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        SMA 200 / EMA 21 / EMA 26
                      </Typography>
                      <Typography variant="body2" fontWeight={700}>
                        ${signal.sma_200 ? (signal.sma_200).toFixed(2) : '—'} / ${signal.ema_21 ? (signal.ema_21).toFixed(2) : '—'} / ${signal.ema_26 ? (signal.ema_26).toFixed(2) : '—'}
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
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        Market Stage
                      </Typography>
                      <Typography variant="body2" fontWeight={700}>
                        {signal.market_stage || '—'}
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

export default MeanReversionAccordion;
