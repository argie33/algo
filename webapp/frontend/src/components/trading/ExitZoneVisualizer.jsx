import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Chip,
  LinearProgress,
  Grid,
  Tooltip,
  IconButton,
  Stack,
  Alert,
  alpha
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Flag,
  Warning,
  CheckCircle,
  Info,
  Timeline
} from '@mui/icons-material';
import { formatCurrency } from '../../utils/formatters';

const ExitZoneVisualizer = ({ signal, currentPrice, entryPrice }) => {
  
  // Calculate exit zones based on O'Neill methodology
  const exitZones = [
    {
      level: 1,
      name: 'Zone 1',
      target: entryPrice * 1.20, // 20% profit
      percentage: 20,
      sellPercent: 25,
      color: '#81c784',
      description: '20% Profit Target - Sell 25% of position'
    },
    {
      level: 2,
      name: 'Zone 2',
      target: entryPrice * 1.25, // 25% profit
      percentage: 25,
      sellPercent: 25,
      color: '#4caf50',
      description: '25% Profit Target - Sell 25% of position'
    },
    {
      level: 3,
      name: 'Zone 3',
      target: signal?.ema_21 || entryPrice * 1.15,
      percentage: null,
      sellPercent: 25,
      color: '#ff9800',
      description: '21-day EMA Breach - Sell 25% of position',
      isDynamic: true,
      trigger: '21 EMA'
    },
    {
      level: 4,
      name: 'Zone 4',
      target: signal?.sma_50 || entryPrice * 1.10,
      percentage: null,
      sellPercent: 25,
      color: '#f44336',
      description: '50-day SMA Breach - Sell remaining position',
      isDynamic: true,
      trigger: '50 SMA'
    }
  ];

  const stopLoss = entryPrice * 0.93; // 7% stop loss
  const currentGain = ((currentPrice - entryPrice) / entryPrice) * 100;
  
  // Determine current position relative to zones
  const getCurrentZone = () => {
    if (currentPrice < stopLoss) return { zone: 'Stop Loss', color: '#d32f2f' };
    for (let i = exitZones.length - 1; i >= 0; i--) {
      if (currentPrice >= exitZones[i].target) {
        return { zone: exitZones[i].name, color: exitZones[i].color };
      }
    }
    return { zone: 'Entry', color: '#2196f3' };
  };

  const currentZone = getCurrentZone();

  // Calculate progress to next zone
  const getProgressToNextZone = () => {
    if (currentPrice < stopLoss) return 0;
    
    let nextZone = exitZones.find(zone => zone.target > currentPrice);
    if (!nextZone) return 100; // Already past all zones
    
    let previousPrice = entryPrice;
    let previousZone = exitZones[exitZones.indexOf(nextZone) - 1];
    if (previousZone && currentPrice > previousZone.target) {
      previousPrice = previousZone.target;
    }
    
    const progress = ((currentPrice - previousPrice) / (nextZone.target - previousPrice)) * 100;
    return Math.min(100, Math.max(0, progress));
  };

  const progressToNext = getProgressToNextZone();

  return (
    <div className="bg-white shadow-md rounded-lg p-4" 
      elevation={2} 
      sx={{ 
        p: 3, 
        background: '#ffffffE6',
        border: `1px solid ${'#e0e0e01A'}`
      }}
    >
      <div  sx={{ mb: 2 }}>
        <div  variant="h6" gutterBottom>
          Exit Zone Management
        </div>
        <div  sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
            label={`Current Zone: ${currentZone.zone}`}
            sx={{ 
              backgroundColor: currentZone.color + '33',
              color: currentZone.color,
              fontWeight: 600
            }}
          />
          <div  variant="body2" color="text.secondary">
            Gain: {currentGain >= 0 ? '+' : ''}{currentGain.toFixed(2)}%
          </div>
        </div>
      </div>

      {/* Visual Zone Representation */}
      <div  sx={{ position: 'relative', mb: 3 }}>
        <div  sx={{ 
          display: 'flex', 
          height: 60, 
          borderRadius: 1,
          overflow: 'hidden',
          border: `1px solid #e0e0e0`
        }}>
          {/* Stop Loss Zone */}
          <div  title="Stop Loss: 7% below entry">
            <div  sx={{ 
              width: '10%', 
              backgroundColor: '#d32f2f',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'white',
              cursor: 'pointer'
            }}>
              <Warning fontSize="small" />
            </div>
          </div>

          {/* Entry Zone */}
          <div  title="Entry Zone">
            <div  sx={{ 
              width: '15%', 
              backgroundColor: '#e0e0e0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <Flag fontSize="small" />
            </div>
          </div>

          {/* Exit Zones */}
          {exitZones.map((zone, index) => (
            <div  key={zone.level} title={zone.description}>
              <div  sx={{ 
                flex: 1,
                backgroundColor: zone.color,
                opacity: currentPrice >= zone.target ? 1 : 0.3,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'white',
                borderLeft: `1px solid #e0e0e0`,
                cursor: 'pointer',
                transition: 'all 0.3s ease'
              }}>
                <div  variant="caption" fontWeight={600}>
                  {zone.trigger || `${zone.percentage}%`}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Current Price Indicator */}
        <div  sx={{ 
          position: 'absolute',
          top: -10,
          left: `${Math.min(95, Math.max(5, (currentPrice - stopLoss) / (exitZones[3].target - stopLoss) * 100))}%`,
          transform: 'translateX(-50%)'
        }}>
          <div  sx={{ 
            width: 0,
            height: 0,
            borderLeft: '8px solid transparent',
            borderRight: '8px solid transparent',
            borderTop: `12px solid #1976d2`
          }} />
          <div  
            variant="caption" 
            sx={{ 
              position: 'absolute',
              top: -25,
              left: '50%',
              transform: 'translateX(-50%)',
              whiteSpace: 'nowrap',
              backgroundColor: '#1976d2',
              color: 'white',
              px: 1,
              py: 0.5,
              borderRadius: 1,
              fontWeight: 600
            }}
          >
            {formatCurrency(currentPrice)}
          </div>
        </div>
      </div>

      {/* Progress to Next Zone */}
      <div  sx={{ mb: 3 }}>
        <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
          <div  variant="body2" color="text.secondary">
            Progress to Next Zone
          </div>
          <div  variant="body2" fontWeight={600}>
            {progressToNext.toFixed(1)}%
          </div>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2" 
          variant="determinate" 
          value={progressToNext} 
          sx={{ 
            height: 8, 
            borderRadius: 4,
            backgroundColor: '#1976d21A',
            '& .MuiLinearProgress-bar': {
              borderRadius: 4
            }
          }}
        />
      </div>

      {/* Exit Zone Details */}
      <div className="grid" container spacing={2}>
        {exitZones.map((zone) => (
          <div className="grid" item xs={6} key={zone.level}>
            <div className="bg-white shadow-md rounded-lg p-4" 
              variant="outlined" 
              sx={{ 
                p: 2,
                backgroundColor: currentPrice >= zone.target 
                  ? zone.color + '1A' 
                  : 'transparent',
                borderColor: currentPrice >= zone.target 
                  ? zone.color 
                  : '#e0e0e0'
              }}
            >
              <div  sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                {currentPrice >= zone.target ? (
                  <CheckCircle sx={{ color: zone.color, fontSize: 20 }} />
                ) : (
                  <Timeline sx={{ color: '#666666', fontSize: 20 }} />
                )}
                <div  variant="subtitle2" fontWeight={600}>
                  {zone.name}
                </div>
              </div>
              <div  variant="body2" color="text.secondary" gutterBottom>
                {zone.isDynamic ? zone.trigger : `Target: ${formatCurrency(zone.target)}`}
              </div>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                label={`Sell ${zone.sellPercent}%`}
                size="small"
                variant={currentPrice >= zone.target ? 'filled' : 'outlined'}
                color={currentPrice >= zone.target ? 'success' : 'default'}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Stop Loss Warning */}
      {currentPrice < entryPrice && currentPrice > stopLoss && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
          severity="warning" 
          sx={{ mt: 2 }}
          icon={<Warning />}
        >
          <div  variant="body2">
            Price is {((stopLoss - currentPrice) / currentPrice * 100).toFixed(1)}% above stop loss ({formatCurrency(stopLoss)})
          </div>
        </div>
      )}

      {/* Buy Zone Indicator (for new entries) */}
      {!entryPrice && signal?.pivot_price && (
        <div  sx={{ mt: 3 }}>
          <div  variant="subtitle2" gutterBottom>
            5% Buy Zone (O'Neill Method)
          </div>
          <div  sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <div  sx={{ flex: 1 }}>
              <div className="w-full bg-gray-200 rounded-full h-2" 
                variant="determinate" 
                value={currentPrice <= signal.pivot_price * 1.05 ? 
                  ((currentPrice - signal.pivot_price) / (signal.pivot_price * 0.05)) * 100 : 100
                } 
                color={currentPrice <= signal.pivot_price * 1.05 ? 'success' : 'error'}
                sx={{ height: 8, borderRadius: 4 }}
              />
            </div>
            <div  variant="caption" color="text.secondary">
              {formatCurrency(signal.pivot_price)} - {formatCurrency(signal.pivot_price * 1.05)}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ExitZoneVisualizer;