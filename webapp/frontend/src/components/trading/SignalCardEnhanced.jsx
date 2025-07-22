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
  const theme = { palette: { mode: "light" } };

  // Calculate buy zone position (O'Neill 5% rule)
  const buyZoneStart = signal.pivot_price || signal.entry_price;
  const buyZoneEnd = buyZoneStart * 1.05;
  const currentPrice = signal.current_price;
  const isInBuyZone = currentPrice >= buyZoneStart && currentPrice <= buyZoneEnd;
  const buyZonePosition = ((currentPrice - buyZoneStart) / (buyZoneEnd - buyZoneStart)) * 100;

  // Signal quality color
  const getQualityColor = (quality) => {
    const colors = {
      'A+': '#1b5e20',
      'A': '#4caf50',
      'B+': '#2196f3',
      'B': '#ff9800',
      'C': '#f44336'
    };
    return colors[quality] || theme.palette.grey[500];
  };

  // Volume surge indicator
  const volumeSurge = signal.volume_surge_pct || 0;
  const getVolumeSurgeColor = () => {
    if (volumeSurge >= 100) return '#1b5e20';
    if (volumeSurge >= 50) return '#4caf50';
    if (volumeSurge >= 40) return '#ff9800';
    return '#f44336';
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
    <div className="bg-white shadow-md rounded-lg" 
      sx={{ 
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        transition: 'all 0.3s ease',
        border: `2px solid ${'#e0e0e01A'}`,
        '&:hover': {
          transform: 'translateY(-4px)',
          boxShadow: theme.shadows[8],
          borderColor: signal.signal === 'Buy' ? '#4caf50' : '#f44336'
        }
      }}
    >
      <div className="bg-white shadow-md rounded-lg"content sx={{ flex: 1 }}>
        {/* Header */}
        <div  sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
          <div>
            <div  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <div  variant="h5" fontWeight={700}>
                {signal.symbol}
              </div>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                icon={signal.signal === 'Buy' ? <TrendingUp /> : <TrendingDown />}
                label={signal.signal}
                size="small"
                color={signal.signal === 'Buy' ? 'success' : 'error'}
                sx={{ fontWeight: 600 }}
              />
            </div>
            <div  variant="body2" color="text.secondary">
              {signal.company_name}
            </div>
          </div>
          <div  sx={{ display: 'flex', gap: 1 }}>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
              label={signal.breakout_quality || 'B'}
              sx={{
                backgroundColor: getQualityColor(signal.breakout_quality) + '33',
                color: getQualityColor(signal.breakout_quality),
                fontWeight: 700,
                fontSize: '0.9rem'
              }}
            />
            <button className="p-2 rounded-full hover:bg-gray-100" 
              size="small" 
              onClick={() => onBookmark(signal.symbol)}
              color={isBookmarked ? 'primary' : 'default'}
            >
              {isBookmarked ? <Bookmark /> : <BookmarkBorder />}
            </button>
          </div>
        </div>

        <hr className="border-gray-200" sx={{ my: 2 }} />

        {/* Signal Details */}
        <div className="grid" container spacing={2}>
          <div className="grid" item xs={12}>
            <div className="bg-white shadow-md rounded-lg p-4" 
              elevation={0} 
              sx={{ 
                p: 2, 
                backgroundColor: '#1976d20D',
                border: `1px solid ${'#1976d21A'}`
              }}
            >
              <div  variant="subtitle2" gutterBottom>
                {signal.signal_type || 'Breakout'} Signal
              </div>
              <div  sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                  icon={<ShowChart />}
                  label={`${signal.base_type || 'Pattern'} ${getBasePatternIcon(signal.base_type)}`}
                  size="small"
                  variant="outlined"
                />
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                  icon={<Timeline />}
                  label={`${signal.base_length_days || 0} days`}
                  size="small"
                  variant="outlined"
                />
                {signal.rs_rating && (
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                    icon={<Speed />}
                    label={`RS: ${signal.rs_rating}`}
                    size="small"
                    color={signal.rs_rating >= 80 ? 'success' : 'default'}
                    variant="outlined"
                  />
                )}
              </div>
            </div>
          </div>

          {/* Buy Zone Indicator */}
          <div className="grid" item xs={12}>
            <div  sx={{ mb: 1 }}>
              <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <div  variant="body2" fontWeight={600}>
                  5% Buy Zone (O'Neill Method)
                </div>
                <div  
                  variant="body2" 
                  color={isInBuyZone ? 'success.main' : 'error.main'}
                  fontWeight={600}
                >
                  {isInBuyZone ? 'IN ZONE' : 'OUT OF ZONE'}
                </div>
              </div>
              <div  sx={{ position: 'relative' }}>
                <div className="w-full bg-gray-200 rounded-full h-2" 
                  variant="determinate" 
                  value={Math.min(100, Math.max(0, buyZonePosition))}
                  sx={{ 
                    height: 10, 
                    borderRadius: 5,
                    backgroundColor: '#bdbdbd33',
                    '& .MuiLinearProgress-bar': {
                      backgroundColor: isInBuyZone ? '#4caf50' : '#f44336'
                    }
                  }}
                />
                <div  sx={{ 
                  display: 'flex', 
                  justifyContent: 'space-between', 
                  mt: 0.5 
                }}>
                  <div  variant="caption">
                    {formatCurrency(buyZoneStart)}
                  </div>
                  <div  variant="caption" fontWeight={600}>
                    Current: {formatCurrency(currentPrice)}
                  </div>
                  <div  variant="caption">
                    {formatCurrency(buyZoneEnd)}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Price & Volume */}
          <div className="grid" item xs={6}>
            <div>
              <div  variant="caption" color="text.secondary">Entry Price</div>
              <div  variant="h6" fontWeight={600}>
                {formatCurrency(signal.entry_price || buyZoneStart)}
              </div>
              <div  variant="caption" color="error.main">
                Stop: {formatCurrency((signal.entry_price || buyZoneStart) * 0.93)}
              </div>
            </div>
          </div>
          <div className="grid" item xs={6}>
            <div>
              <div  variant="caption" color="text.secondary">Volume Surge</div>
              <div  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <VolumeUp sx={{ color: getVolumeSurgeColor() }} />
                <div  
                  variant="h6" 
                  fontWeight={600}
                  color={getVolumeSurgeColor()}
                >
                  +{volumeSurge.toFixed(0)}%
                </div>
              </div>
              <div  variant="caption" color="text.secondary">
                vs 50-day avg
              </div>
            </div>
          </div>

          {/* Exit Zones Preview */}
          <div className="grid" item xs={12}>
            <div  sx={{ 
              p: 1.5, 
              backgroundColor: '#9e9e9e0D',
              borderRadius: 1
            }}>
              <div  variant="caption" color="text.secondary" gutterBottom>
                Exit Zone Targets (O'Neill Method)
              </div>
              <div className="flex flex-col space-y-2" direction="row" spacing={1} sx={{ mt: 1 }}>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                  label={`20%: ${formatCurrency((signal.entry_price || buyZoneStart) * 1.20)}`}
                  size="small"
                  variant="outlined"
                  color="success"
                />
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                  label={`25%: ${formatCurrency((signal.entry_price || buyZoneStart) * 1.25)}`}
                  size="small"
                  variant="outlined"
                  color="success"
                />
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                  label="21 EMA"
                  size="small"
                  variant="outlined"
                  color="warning"
                />
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                  label="50 SMA"
                  size="small"
                  variant="outlined"
                  color="error"
                />
              </div>
            </div>
          </div>

          {/* Risk/Reward */}
          <div className="grid" item xs={12}>
            <div  sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div  variant="body2" color="text.secondary">
                Risk/Reward Ratio
              </div>
              <div  variant="body2" fontWeight={600}>
                1:{((0.20 / 0.07).toFixed(1))} to 1:{((0.25 / 0.07).toFixed(1))}
              </div>
            </div>
          </div>
        </div>

        {/* Signal Strength */}
        <div  sx={{ mt: 2 }}>
          <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
            <div  variant="body2" color="text.secondary">
              Signal Strength
            </div>
            <div  variant="body2" fontWeight={600}>
              {Math.round(signal.signal_strength * 100)}%
            </div>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2" 
            variant="determinate" 
            value={signal.signal_strength * 100}
            sx={{ 
              height: 6, 
              borderRadius: 3,
              backgroundColor: '#1976d21A',
              '& .MuiLinearProgress-bar': {
                backgroundColor: 
                  signal.signal_strength >= 0.8 ? '#4caf50' :
                  signal.signal_strength >= 0.6 ? '#ff9800' :
                  '#f44336'
              }
            }}
          />
        </div>

        {/* Market Conditions */}
        {signal.market_in_uptrend !== undefined && (
          <div  sx={{ mt: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
            {signal.market_in_uptrend ? (
              <>
                <CheckCircle sx={{ color: '#4caf50', fontSize: 20 }} />
                <div  variant="caption" color="success.main">
                  Market in confirmed uptrend
                </div>
              </>
            ) : (
              <>
                <Warning sx={{ color: '#ff9800', fontSize: 20 }} />
                <div  variant="caption" color="warning.main">
                  Market under pressure
                </div>
              </>
            )}
          </div>
        )}
      </div>

      <div className="bg-white shadow-md rounded-lg"Actions sx={{ p: 2, pt: 0 }}>
        <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
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
        </button>
      </div>
    </div>
  );
};

export default SignalCardEnhanced;