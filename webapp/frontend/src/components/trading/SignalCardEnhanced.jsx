import React from 'react';
import {
  Card,
  CardContent,
  CardActions,
  Box,
  Typography,
  Chip,
  Grid,
  LinearProgress,
  Button,
  Divider,
  Stack,
  Tooltip,
  IconButton,
  Paper,
  useTheme,
  alpha
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Flag,
  CheckCircle,
  Warning,
  Info,
  Speed,
  ShowChart,
  VolumeUp,
  Timeline,
  BookmarkBorder,
  Bookmark,
  ArrowUpward,
  ArrowDownward
} from '@mui/icons-material';
import { formatCurrency } from '../../utils/formatters';

const SignalCardEnhanced = ({ signal, onBookmark, isBookmarked, onTrade }) => {
  const theme = useTheme();

  // Calculate buy zone position (O'Neill 5% rule)
  const buyZoneStart = signal.pivot_price || signal.entry_price;
  const buyZoneEnd = buyZoneStart * 1.05;
  const currentPrice = signal.current_price;
  const isInBuyZone = currentPrice >= buyZoneStart && currentPrice <= buyZoneEnd;
  const buyZonePosition = ((currentPrice - buyZoneStart) / (buyZoneEnd - buyZoneStart)) * 100;

  // Signal quality color
  const getQualityColor = (quality) => {
    const colors = {
      'A+': theme.palette.success.dark,
      'A': theme.palette.success.main,
      'B+': theme.palette.info.main,
      'B': theme.palette.warning.main,
      'C': theme.palette.error.main
    };
    return colors[quality] || theme.palette.grey[500];
  };

  // Volume surge indicator
  const volumeSurge = signal.volume_surge_pct || 0;
  const getVolumeSurgeColor = () => {
    if (volumeSurge >= 100) return theme.palette.success.dark;
    if (volumeSurge >= 50) return theme.palette.success.main;
    if (volumeSurge >= 40) return theme.palette.warning.main;
    return theme.palette.error.main;
  };

  // Base pattern icon
  const getBasePatternIcon = (pattern) => {
    const icons = {
      'Cup with Handle': '☕',
      'Cup': '🥤',
      'Flat Base': '━',
      'Double Bottom': 'W',
      'Ascending Base': '📈',
      'Flag': '🚩'
    };
    return icons[pattern] || '📊';
  };

  return (
    <Card 
      sx={{ 
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        transition: 'all 0.3s ease',
        border: `2px solid ${alpha(theme.palette.divider, 0.1)}`,
        '&:hover': {
          transform: 'translateY(-4px)',
          boxShadow: theme.shadows[8],
          borderColor: signal.signal === 'Buy' ? theme.palette.success.main : theme.palette.error.main
        }
      }}
    >
      <CardContent sx={{ flex: 1 }}>
        {/* Header */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography variant="h5" fontWeight={700}>
                {signal.symbol}
              </Typography>
              <Chip
                icon={signal.signal === 'Buy' ? <TrendingUp /> : <TrendingDown />}
                label={signal.signal}
                size="small"
                color={signal.signal === 'Buy' ? 'success' : 'error'}
                sx={{ fontWeight: 600 }}
              />
            </Box>
            <Typography variant="body2" color="text.secondary">
              {signal.company_name}
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Chip
              label={signal.breakout_quality || 'B'}
              sx={{
                backgroundColor: alpha(getQualityColor(signal.breakout_quality), 0.2),
                color: getQualityColor(signal.breakout_quality),
                fontWeight: 700,
                fontSize: '0.9rem'
              }}
            />
            <IconButton 
              size="small" 
              onClick={() => onBookmark(signal.symbol)}
              color={isBookmarked ? 'primary' : 'default'}
            >
              {isBookmarked ? <Bookmark /> : <BookmarkBorder />}
            </IconButton>
          </Box>
        </Box>

        <Divider sx={{ my: 2 }} />

        {/* Signal Details */}
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <Paper 
              elevation={0} 
              sx={{ 
                p: 2, 
                backgroundColor: alpha(theme.palette.primary.main, 0.05),
                border: `1px solid ${alpha(theme.palette.primary.main, 0.1)}`
              }}
            >
              <Typography variant="subtitle2" gutterBottom>
                {signal.signal_type || 'Breakout'} Signal
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <Chip
                  icon={<ShowChart />}
                  label={`${signal.base_type || 'Pattern'} ${getBasePatternIcon(signal.base_type)}`}
                  size="small"
                  variant="outlined"
                />
                <Chip
                  icon={<Timeline />}
                  label={`${signal.base_length_days || 0} days`}
                  size="small"
                  variant="outlined"
                />
                {signal.rs_rating && (
                  <Chip
                    icon={<Speed />}
                    label={`RS: ${signal.rs_rating}`}
                    size="small"
                    color={signal.rs_rating >= 80 ? 'success' : 'default'}
                    variant="outlined"
                  />
                )}
              </Box>
            </Paper>
          </Grid>

          {/* Buy Zone Indicator */}
          <Grid item xs={12}>
            <Box sx={{ mb: 1 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2" fontWeight={600}>
                  5% Buy Zone (O'Neill Method)
                </Typography>
                <Typography 
                  variant="body2" 
                  color={isInBuyZone ? 'success.main' : 'error.main'}
                  fontWeight={600}
                >
                  {isInBuyZone ? 'IN ZONE' : 'OUT OF ZONE'}
                </Typography>
              </Box>
              <Box sx={{ position: 'relative' }}>
                <LinearProgress 
                  variant="determinate" 
                  value={Math.min(100, Math.max(0, buyZonePosition))}
                  sx={{ 
                    height: 10, 
                    borderRadius: 5,
                    backgroundColor: alpha(theme.palette.grey[400], 0.2),
                    '& .MuiLinearProgress-bar': {
                      backgroundColor: isInBuyZone ? theme.palette.success.main : theme.palette.error.main
                    }
                  }}
                />
                <Box sx={{ 
                  display: 'flex', 
                  justifyContent: 'space-between', 
                  mt: 0.5 
                }}>
                  <Typography variant="caption">
                    {formatCurrency(buyZoneStart)}
                  </Typography>
                  <Typography variant="caption" fontWeight={600}>
                    Current: {formatCurrency(currentPrice)}
                  </Typography>
                  <Typography variant="caption">
                    {formatCurrency(buyZoneEnd)}
                  </Typography>
                </Box>
              </Box>
            </Box>
          </Grid>

          {/* Price & Volume */}
          <Grid item xs={6}>
            <Box>
              <Typography variant="caption" color="text.secondary">Entry Price</Typography>
              <Typography variant="h6" fontWeight={600}>
                {formatCurrency(signal.entry_price || buyZoneStart)}
              </Typography>
              <Typography variant="caption" color="error.main">
                Stop: {formatCurrency((signal.entry_price || buyZoneStart) * 0.93)}
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={6}>
            <Box>
              <Typography variant="caption" color="text.secondary">Volume Surge</Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <VolumeUp sx={{ color: getVolumeSurgeColor() }} />
                <Typography 
                  variant="h6" 
                  fontWeight={600}
                  color={getVolumeSurgeColor()}
                >
                  +{volumeSurge.toFixed(0)}%
                </Typography>
              </Box>
              <Typography variant="caption" color="text.secondary">
                vs 50-day avg
              </Typography>
            </Box>
          </Grid>

          {/* Exit Zones Preview */}
          <Grid item xs={12}>
            <Box sx={{ 
              p: 1.5, 
              backgroundColor: alpha(theme.palette.grey[500], 0.05),
              borderRadius: 1
            }}>
              <Typography variant="caption" color="text.secondary" gutterBottom>
                Exit Zone Targets (O'Neill Method)
              </Typography>
              <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                <Chip 
                  label={`20%: ${formatCurrency((signal.entry_price || buyZoneStart) * 1.20)}`}
                  size="small"
                  variant="outlined"
                  color="success"
                />
                <Chip 
                  label={`25%: ${formatCurrency((signal.entry_price || buyZoneStart) * 1.25)}`}
                  size="small"
                  variant="outlined"
                  color="success"
                />
                <Chip 
                  label="21 EMA"
                  size="small"
                  variant="outlined"
                  color="warning"
                />
                <Chip 
                  label="50 SMA"
                  size="small"
                  variant="outlined"
                  color="error"
                />
              </Stack>
            </Box>
          </Grid>

          {/* Risk/Reward */}
          <Grid item xs={12}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography variant="body2" color="text.secondary">
                Risk/Reward Ratio
              </Typography>
              <Typography variant="body2" fontWeight={600}>
                1:{((0.20 / 0.07).toFixed(1))} to 1:{((0.25 / 0.07).toFixed(1))}
              </Typography>
            </Box>
          </Grid>
        </Grid>

        {/* Signal Strength */}
        <Box sx={{ mt: 2 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Signal Strength
            </Typography>
            <Typography variant="body2" fontWeight={600}>
              {Math.round(signal.signal_strength * 100)}%
            </Typography>
          </Box>
          <LinearProgress 
            variant="determinate" 
            value={signal.signal_strength * 100}
            sx={{ 
              height: 6, 
              borderRadius: 3,
              backgroundColor: alpha(theme.palette.primary.main, 0.1),
              '& .MuiLinearProgress-bar': {
                backgroundColor: 
                  signal.signal_strength >= 0.8 ? theme.palette.success.main :
                  signal.signal_strength >= 0.6 ? theme.palette.warning.main :
                  theme.palette.error.main
              }
            }}
          />
        </Box>

        {/* Market Conditions */}
        {signal.market_in_uptrend !== undefined && (
          <Box sx={{ mt: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
            {signal.market_in_uptrend ? (
              <>
                <CheckCircle sx={{ color: theme.palette.success.main, fontSize: 20 }} />
                <Typography variant="caption" color="success.main">
                  Market in confirmed uptrend
                </Typography>
              </>
            ) : (
              <>
                <Warning sx={{ color: theme.palette.warning.main, fontSize: 20 }} />
                <Typography variant="caption" color="warning.main">
                  Market under pressure
                </Typography>
              </>
            )}
          </Box>
        )}
      </CardContent>

      <CardActions sx={{ p: 2, pt: 0 }}>
        <Button 
          fullWidth 
          variant="contained" 
          color={signal.signal === 'Buy' ? 'success' : 'error'}
          onClick={() => onTrade(signal)}
          disabled={signal.signal === 'Buy' && !isInBuyZone}
          startIcon={signal.signal === 'Buy' ? <ArrowUpward /> : <ArrowDownward />}
        >
          {signal.signal === 'Buy' 
            ? (isInBuyZone ? 'Enter Position' : 'Wait for Buy Zone')
            : 'Exit Position'
          }
        </Button>
      </CardActions>
    </Card>
  );
};

export default SignalCardEnhanced;