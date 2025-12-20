/**
 * Professional Chart Container
 * Award-winning financial chart wrapper
 *
 * Features:
 * - Responsive container with proper aspect ratios
 * - Professional header with title and subtitle
 * - Real-time data indicator
 * - Theme-aware styling
 * - Animation support
 * - Custom footer for context/attribution
 */

import React from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Typography,
  useTheme,
  useMediaQuery,
  Chip,
  Stack,
} from '@mui/material';
import { Refresh, AccessTime } from '@mui/icons-material';
import { _CHART_TYPOGRAPHY } from '../../theme/chartTheme';

const ProfessionalChartContainer = ({
  title,
  subtitle,
  children,
  isLoading = false,
  lastUpdated = null,
  height = 400,
  footer = null,
  actions = null,
  dataQuality = 'real-time',
  sx = {},
}) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

  // Format last updated time
  const getLastUpdatedText = () => {
    if (!lastUpdated) return null;
    const now = new Date();
    const diff = Math.floor((now - new Date(lastUpdated)) / 1000);

    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  };

  const updatedText = getLastUpdatedText();

  // Data quality badge color
  const getQualityColor = () => {
    switch (dataQuality) {
      case 'real-time':
        return 'success';
      case 'delayed':
        return 'warning';
      case 'stale':
        return 'error';
      default:
        return 'default';
    }
  };

  return (
    <Card
      sx={{
        height: 'fit-content',
        background: theme.palette.mode === 'dark'
          ? `linear-gradient(135deg, ${theme.palette.background.paper} 0%, ${theme.palette.background.default} 100%)`
          : `linear-gradient(135deg, #FFFFFF 0%, ${theme.palette.grey[50]} 100%)`,
        borderRadius: 2,
        boxShadow: theme.palette.mode === 'dark'
          ? '0 4px 12px rgba(0, 0, 0, 0.3)'
          : '0 4px 12px rgba(0, 0, 0, 0.08)',
        transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
        '&:hover': {
          boxShadow: theme.palette.mode === 'dark'
            ? '0 8px 24px rgba(0, 0, 0, 0.4)'
            : '0 8px 24px rgba(0, 0, 0, 0.12)',
        },
        ...sx,
      }}
    >
      {/* Header Section */}
      <CardHeader
        title={
          <Box>
            <Typography
              variant="h6"
              sx={{
                fontWeight: 700,
                fontSize: isMobile ? '16px' : '18px',
                letterSpacing: '-0.5px',
                mb: 0.5,
              }}
            >
              {title}
            </Typography>
            {subtitle && (
              <Typography
                variant="caption"
                sx={{
                  color: 'text.secondary',
                  fontSize: '13px',
                  fontWeight: 400,
                }}
              >
                {subtitle}
              </Typography>
            )}
          </Box>
        }
        action={
          <Stack direction="row" spacing={1} alignItems="center">
            {/* Data Quality Badge */}
            <Chip
              icon={<AccessTime sx={{ fontSize: '14px !important' }} />}
              label={
                updatedText ? (
                  <span style={{ fontSize: '12px', fontWeight: 500 }}>
                    {updatedText}
                  </span>
                ) : null
              }
              color={getQualityColor()}
              variant="outlined"
              size="small"
              sx={{
                height: 28,
                '& .MuiChip-icon': {
                  marginLeft: '4px',
                  marginRight: '-4px',
                },
              }}
            />
            {actions}
          </Stack>
        }
        sx={{
          pb: 2,
          borderBottom: `1px solid ${theme.palette.divider}`,
          '& .MuiCardHeader-action': {
            mt: 0,
          },
        }}
      />

      {/* Content Section */}
      <CardContent
        sx={{
          p: isMobile ? 2 : 3,
          pt: 3,
          display: 'flex',
          flexDirection: 'column',
          minHeight: height,
          position: 'relative',
          '&:last-child': {
            pb: isMobile ? 2 : 3,
          },
        }}
      >
        {isLoading && (
          <Box
            sx={{
              position: 'absolute',
              inset: 0,
              backgroundColor: 'rgba(255, 255, 255, 0.7)',
              backdropFilter: 'blur(4px)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: 1,
              zIndex: 10,
            }}
          >
            <Box sx={{ textAlign: 'center' }}>
              <Refresh
                sx={{
                  fontSize: 40,
                  animation: 'spin 1s linear infinite',
                  color: 'primary.main',
                  mb: 1,
                  '@keyframes spin': {
                    from: { transform: 'rotate(0deg)' },
                    to: { transform: 'rotate(360deg)' },
                  },
                }}
              />
              <Typography variant="caption" color="text.secondary">
                Loading...
              </Typography>
            </Box>
          </Box>
        )}

        {/* Chart Content */}
        <Box
          sx={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            opacity: isLoading ? 0.3 : 1,
            transition: 'opacity 0.3s ease',
          }}
        >
          {children}
        </Box>

        {/* Footer */}
        {footer && (
          <Box
            sx={{
              mt: 2,
              pt: 2,
              borderTop: `1px solid ${theme.palette.divider}`,
              fontSize: '12px',
              color: 'text.secondary',
              lineHeight: 1.6,
            }}
          >
            {footer}
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default ProfessionalChartContainer;
