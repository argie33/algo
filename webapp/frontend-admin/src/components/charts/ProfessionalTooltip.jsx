/**
 * Professional Financial Chart Tooltip
 * Elegant, informative, with real-time data display
 *
 * Features:
 * - Dark/Light mode support
 * - Multiple data series display
 * - Trend indicators
 * - Proper formatting for financial data
 * - Smooth animations
 * - Mobile-friendly
 */

import React from 'react';
import {
  Box,
  Typography,
  useTheme,
  Paper,
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Remove,
} from '@mui/icons-material';
import { FINANCIAL_COLORS, _getValueColor, formatChartCurrency, formatChartPercent } from '../../theme/chartTheme';

const ProfessionalTooltip = ({
  active,
  payload,
  label,
  valuePrefix = '$',
  isPercent = false,
  showTrend = true,
  custom = null,
}) => {
  const theme = useTheme();

  if (!active || !payload || payload.length === 0) {
    return null;
  }

  // Handle custom tooltip content
  if (custom && typeof custom === 'function') {
    return custom(active, payload, label);
  }

  const bgColor = theme.palette.mode === 'dark' ? '#1F2937' : '#FFFFFF';
  const textColor = theme.palette.mode === 'dark' ? '#F3F4F6' : '#111827';
  const borderColor = theme.palette.mode === 'dark' ? '#374151' : '#E5E7EB';
  const secondaryTextColor = theme.palette.mode === 'dark' ? '#9CA3AF' : '#6B7280';

  return (
    <Paper
      elevation={0}
      sx={{
        backgroundColor: bgColor,
        border: `1px solid ${borderColor}`,
        borderRadius: 1.5,
        p: 2,
        boxShadow: theme.palette.mode === 'dark'
          ? '0 10px 25px rgba(0, 0, 0, 0.5)'
          : '0 10px 25px rgba(0, 0, 0, 0.1)',
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
        pointerEvents: 'none',
        zIndex: 1000,
        minWidth: 200,
        animation: 'fadeIn 0.2s ease-out',
        '@keyframes fadeIn': {
          from: {
            opacity: 0,
            transform: 'scale(0.95) translateY(-4px)',
          },
          to: {
            opacity: 1,
            transform: 'scale(1) translateY(0)',
          },
        },
      }}
    >
      {/* Label/Header */}
      <Typography
        variant="caption"
        sx={{
          display: 'block',
          fontWeight: 600,
          fontSize: '12px',
          color: secondaryTextColor,
          mb: 1.5,
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
        }}
      >
        {label}
      </Typography>

      {/* Data Series */}
      {payload.map((entry, index) => {
        const value = entry.value;
        const dataKey = entry.dataKey || entry.name;
        const color = entry.color || entry.fill || '#3B82F6';

        // Determine if value should be formatted as currency or percent
        let displayValue;
        if (isPercent) {
          displayValue = formatChartPercent(value);
        } else if (typeof value === 'number') {
          displayValue = valuePrefix === '%'
            ? `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
            : formatChartCurrency(value);
        } else {
          displayValue = value;
        }

        const isPositive = value > 0;
        const isNegative = value < 0;

        return (
          <Box
            key={`${dataKey}-${index}`}
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 2,
              mb: index < payload.length - 1 ? 1 : 0,
              padding: '6px 0',
              borderBottom: index < payload.length - 1 ? `1px solid ${borderColor}` : 'none',
            }}
          >
            {/* Left Section: Label + Indicator */}
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1,
              }}
            >
              {/* Color Indicator Dot */}
              <Box
                sx={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  backgroundColor: color,
                  flexShrink: 0,
                  opacity: 0.9,
                }}
              />

              {/* Series Name */}
              <Typography
                variant="caption"
                sx={{
                  fontWeight: 500,
                  fontSize: '12px',
                  color: textColor,
                }}
              >
                {dataKey}
              </Typography>
            </Box>

            {/* Right Section: Value + Trend */}
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 0.5,
                justifyContent: 'flex-end',
              }}
            >
              {/* Value */}
              <Typography
                variant="caption"
                sx={{
                  fontWeight: 700,
                  fontSize: '12px',
                  color: textColor,
                  minWidth: '60px',
                  textAlign: 'right',
                }}
              >
                {displayValue}
              </Typography>

              {/* Trend Icon */}
              {showTrend && typeof value === 'number' && (
                <>
                  {isPositive && (
                    <TrendingUp
                      sx={{
                        fontSize: '14px',
                        color: FINANCIAL_COLORS.bullish.primary,
                        flexShrink: 0,
                      }}
                    />
                  )}
                  {isNegative && (
                    <TrendingDown
                      sx={{
                        fontSize: '14px',
                        color: FINANCIAL_COLORS.bearish.primary,
                        flexShrink: 0,
                      }}
                    />
                  )}
                  {!isPositive && !isNegative && (
                    <Remove
                      sx={{
                        fontSize: '14px',
                        color: FINANCIAL_COLORS.neutral.primary,
                        flexShrink: 0,
                      }}
                    />
                  )}
                </>
              )}
            </Box>
          </Box>
        );
      })}
    </Paper>
  );
};

export default ProfessionalTooltip;
