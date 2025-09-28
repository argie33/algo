import React from 'react';
import {
  Box,
  Chip,
  Typography,
  Tooltip,
  alpha,
  useTheme,
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  ShowChart,
  SignalCellularAlt,
  Speed,
} from '@mui/icons-material';

const TradingSignal = ({
  signal,
  confidence = 0.75,
  size = "medium",
  showConfidence = false,
  showPerformance = false,
  performance = null,
  variant = "chip" // "chip", "badge", "inline"
}) => {
  const theme = useTheme();

  const getSignalConfig = (signalType) => {
    const normalizedSignal = signalType?.toUpperCase();

    switch (normalizedSignal) {
      case 'BUY':
      case 'STRONG_BUY':
        return {
          color: theme.palette.success.main,
          bgColor: alpha(theme.palette.success.main, 0.1),
          icon: <TrendingUp sx={{ fontSize: size === 'small' ? 16 : 20 }} />,
          label: normalizedSignal === 'STRONG_BUY' ? 'STRONG BUY' : 'BUY',
          textColor: theme.palette.success.dark,
          intensity: normalizedSignal === 'STRONG_BUY' ? 'strong' : 'normal'
        };
      case 'SELL':
      case 'STRONG_SELL':
        return {
          color: theme.palette.error.main,
          bgColor: alpha(theme.palette.error.main, 0.1),
          icon: <TrendingDown sx={{ fontSize: size === 'small' ? 16 : 20 }} />,
          label: normalizedSignal === 'STRONG_SELL' ? 'STRONG SELL' : 'SELL',
          textColor: theme.palette.error.dark,
          intensity: normalizedSignal === 'STRONG_SELL' ? 'strong' : 'normal'
        };
      case 'HOLD':
      case 'NEUTRAL':
        return {
          color: theme.palette.warning.main,
          bgColor: alpha(theme.palette.warning.main, 0.1),
          icon: <ShowChart sx={{ fontSize: size === 'small' ? 16 : 20 }} />,
          label: 'HOLD',
          textColor: theme.palette.warning.dark,
          intensity: 'normal'
        };
      default:
        return {
          color: theme.palette.grey[500],
          bgColor: alpha(theme.palette.grey[500], 0.1),
          icon: <SignalCellularAlt sx={{ fontSize: size === 'small' ? 16 : 20 }} />,
          label: 'N/A',
          textColor: theme.palette.grey[600],
          intensity: 'normal'
        };
    }
  };

  const config = getSignalConfig(signal);
  const confidencePercent = Math.round(confidence * 100);

  // Generate tooltip text
  const getTooltipText = () => {
    let text = `Signal: ${config.label}`;
    if (showConfidence) {
      text += ` (${confidencePercent}% confidence)`;
    }
    if (showPerformance && performance !== null) {
      text += ` | Performance: ${performance > 0 ? '+' : ''}${performance.toFixed(1)}%`;
    }
    return text;
  };

  // Chip variant (default)
  if (variant === "chip") {
    return (
      <Tooltip title={getTooltipText()}>
        <Chip
          icon={config.icon}
          label={
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <Typography
                variant={size === 'small' ? 'caption' : 'body2'}
                sx={{
                  color: config.textColor,
                  fontWeight: config.intensity === 'strong' ? 700 : 600,
                  fontSize: size === 'small' ? '0.65rem' : '0.75rem',
                }}
              >
                {config.label}
              </Typography>
              {showConfidence && (
                <Typography
                  variant="caption"
                  sx={{
                    color: alpha(config.textColor, 0.7),
                    fontSize: '0.6rem',
                  }}
                >
                  {confidencePercent}%
                </Typography>
              )}
            </Box>
          }
          size={size}
          sx={{
            backgroundColor: config.bgColor,
            borderColor: alpha(config.color, 0.3),
            '&:hover': {
              backgroundColor: alpha(config.color, 0.15),
            },
          }}
        />
      </Tooltip>
    );
  }

  // Badge variant
  if (variant === "badge") {
    return (
      <Tooltip title={getTooltipText()}>
        <Box
          sx={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 0.5,
            px: size === 'small' ? 1 : 1.5,
            py: size === 'small' ? 0.25 : 0.5,
            borderRadius: 2,
            backgroundColor: config.bgColor,
            border: `1px solid ${alpha(config.color, 0.3)}`,
            minWidth: size === 'small' ? 60 : 80,
            justifyContent: 'center',
            cursor: 'pointer',
            transition: 'all 0.2s ease-in-out',
            '&:hover': {
              backgroundColor: alpha(config.color, 0.15),
              borderColor: alpha(config.color, 0.5),
              transform: 'translateY(-1px)',
            },
          }}
        >
          {config.icon}
          <Typography
            variant={size === 'small' ? 'caption' : 'body2'}
            sx={{
              color: config.textColor,
              fontWeight: config.intensity === 'strong' ? 700 : 600,
              fontSize: size === 'small' ? '0.65rem' : '0.75rem',
            }}
          >
            {config.label}
          </Typography>
          {showConfidence && (
            <Typography
              variant="caption"
              sx={{
                color: alpha(config.textColor, 0.7),
                fontSize: '0.6rem',
                ml: 0.5,
              }}
            >
              {confidencePercent}%
            </Typography>
          )}
        </Box>
      </Tooltip>
    );
  }

  // Inline variant
  if (variant === "inline") {
    return (
      <Tooltip title={getTooltipText()}>
        <Box
          component="span"
          sx={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 0.3,
            color: config.color,
            cursor: 'pointer',
          }}
        >
          {React.cloneElement(config.icon, {
            sx: { fontSize: size === 'small' ? 14 : 16 }
          })}
          <Typography
            variant="caption"
            sx={{
              color: config.color,
              fontWeight: 600,
              fontSize: size === 'small' ? '0.6rem' : '0.7rem',
            }}
          >
            {config.label}
          </Typography>
          {showConfidence && (
            <Typography
              variant="caption"
              sx={{
                color: alpha(config.color, 0.7),
                fontSize: '0.55rem',
              }}
            >
              ({confidencePercent}%)
            </Typography>
          )}
        </Box>
      </Tooltip>
    );
  }

  return null;
};

// Enhanced signal with performance indicator
export const TradingSignalWithPerformance = ({ signal, confidence, performance, size = "medium" }) => {
  const theme = useTheme();

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <TradingSignal
        signal={signal}
        confidence={confidence}
        size={size}
        variant="badge"
        showConfidence={true}
      />
      {performance !== null && (
        <Tooltip title={`Performance: ${performance > 0 ? '+' : ''}${performance.toFixed(1)}%`}>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 0.3,
              px: 0.8,
              py: 0.3,
              borderRadius: 1,
              backgroundColor: alpha(
                performance >= 0 ? theme.palette.success.main : theme.palette.error.main,
                0.1
              ),
            }}
          >
            <Speed sx={{
              fontSize: 14,
              color: performance >= 0 ? theme.palette.success.main : theme.palette.error.main
            }} />
            <Typography
              variant="caption"
              sx={{
                color: performance >= 0 ? theme.palette.success.main : theme.palette.error.main,
                fontWeight: 600,
                fontSize: '0.6rem',
              }}
            >
              {performance > 0 ? '+' : ''}{performance.toFixed(1)}%
            </Typography>
          </Box>
        </Tooltip>
      )}
    </Box>
  );
};

export default TradingSignal;