import React from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  Box,
  Typography,
  Chip,
  Grid,
  LinearProgress,
  Alert,
  Stack,
  Divider,
  Paper,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  alpha
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Warning,
  CheckCircle,
  Info,
  Schedule,
  Assessment,
  ShowChart,
  ErrorOutline,
  Circle
} from '@mui/icons-material';

const MarketTimingPanel = ({ marketData = {} }) => {

  // Default market data if not provided
  const {
    market_status = 'Confirmed Uptrend',
    distribution_days = 2,
    follow_through_day = '2024-01-15',
    sp500_above_50ma = 68,
    sp500_above_200ma = 75,
    nasdaq_above_50ma = 62,
    nasdaq_above_200ma = 71,
    growth_leaders_up = 42,
    growth_leaders_down = 8,
    put_call_ratio = 0.85,
    vix_level = 15.2,
    advance_decline = 1.8,
    new_highs = 145,
    new_lows = 32
  } = marketData;

  const getMarketStatusColor = (status) => {
    const colors = {
      'Confirmed Uptrend': '#4caf50',
      'Uptrend Under Pressure': '#ff9800',
      'Market Correction': '#f44336',
      'Rally Attempt': '#2196f3'
    };
    return colors[status] || '#9e9e9e';
  };

  const getMarketStatusIcon = (status) => {
    const icons = {
      'Confirmed Uptrend': <TrendingUp />,
      'Uptrend Under Pressure': <Warning />,
      'Market Correction': <TrendingDown />,
      'Rally Attempt': <ShowChart />
    };
    return icons[status] || <Info />;
  };

  const getBreadthStrength = () => {
    const score = (sp500_above_50ma + sp500_above_200ma + nasdaq_above_50ma + nasdaq_above_200ma) / 4;
    if (score >= 70) return { label: 'Strong', color: '#4caf50' };
    if (score >= 50) return { label: 'Moderate', color: '#ff9800' };
    return { label: 'Weak', color: '#f44336' };
  };

  const breadthStrength = getBreadthStrength();

  const getDistributionWarning = () => {
    if (distribution_days >= 5) return 'error';
    if (distribution_days >= 4) return 'warning';
    return 'info';
  };

  const daysSinceFollowThrough = Math.floor(
    (new Date() - new Date(follow_through_day)) / (1000 * 60 * 60 * 24)
  );

  return (
    <Card>
      <CardHeader 
        title="Market Timing Indicators"
        subheader="O'Neill's 'M' in CANSLIM - Market Direction"
        action={
          <Chip
            icon={getMarketStatusIcon(market_status)}
            label={market_status}
            sx={{
              backgroundColor: getMarketStatusColor(market_status) + '33',
              color: getMarketStatusColor(market_status),
              fontWeight: 600,
              border: `1px solid ${getMarketStatusColor(market_status) + '4D'}`
            }}
          />
        }
      />
      <CardContent>
        <Grid container spacing={3}>
          {/* Distribution Days Alert */}
          <Grid item xs={12}>
            <Alert 
              severity={getDistributionWarning()}
              icon={<Assessment />}
            >
              <Box>
                <Typography variant="body2" fontWeight={600}>
                  Distribution Days: {distribution_days} in last 25 sessions
                </Typography>
                <Typography variant="caption">
                  {distribution_days >= 4 
                    ? 'Caution: Heavy institutional selling detected. Consider reducing exposure.'
                    : distribution_days >= 2
                    ? 'Some distribution present. Monitor closely.'
                    : 'Minimal distribution. Market showing resilience.'
                  }
                </Typography>
              </Box>
            </Alert>
          </Grid>

          {/* Market Breadth */}
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle2" gutterBottom>
                Market Breadth
              </Typography>
              <Box sx={{ mb: 2 }}>
                <Chip 
                  label={breadthStrength.label}
                  size="small"
                  sx={{ 
                    backgroundColor: breadthStrength.color + '33',
                    color: breadthStrength.color,
                    mb: 2
                  }}
                />
              </Box>
              
              <Stack spacing={2}>
                <Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                    <Typography variant="caption">S&P 500 above 50-day MA</Typography>
                    <Typography variant="caption" fontWeight={600}>{sp500_above_50ma}%</Typography>
                  </Box>
                  <LinearProgress 
                    variant="determinate" 
                    value={sp500_above_50ma}
                    color={sp500_above_50ma >= 60 ? 'success' : sp500_above_50ma >= 40 ? 'warning' : 'error'}
                    sx={{ height: 6, borderRadius: 3 }}
                  />
                </Box>

                <Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                    <Typography variant="caption">S&P 500 above 200-day MA</Typography>
                    <Typography variant="caption" fontWeight={600}>{sp500_above_200ma}%</Typography>
                  </Box>
                  <LinearProgress 
                    variant="determinate" 
                    value={sp500_above_200ma}
                    color={sp500_above_200ma >= 70 ? 'success' : sp500_above_200ma >= 50 ? 'warning' : 'error'}
                    sx={{ height: 6, borderRadius: 3 }}
                  />
                </Box>

                <Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                    <Typography variant="caption">NASDAQ above 50-day MA</Typography>
                    <Typography variant="caption" fontWeight={600}>{nasdaq_above_50ma}%</Typography>
                  </Box>
                  <LinearProgress 
                    variant="determinate" 
                    value={nasdaq_above_50ma}
                    color={nasdaq_above_50ma >= 60 ? 'success' : nasdaq_above_50ma >= 40 ? 'warning' : 'error'}
                    sx={{ height: 6, borderRadius: 3 }}
                  />
                </Box>

                <Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                    <Typography variant="caption">NASDAQ above 200-day MA</Typography>
                    <Typography variant="caption" fontWeight={600}>{nasdaq_above_200ma}%</Typography>
                  </Box>
                  <LinearProgress 
                    variant="determinate" 
                    value={nasdaq_above_200ma}
                    color={nasdaq_above_200ma >= 70 ? 'success' : nasdaq_above_200ma >= 50 ? 'warning' : 'error'}
                    sx={{ height: 6, borderRadius: 3 }}
                  />
                </Box>
              </Stack>
            </Paper>
          </Grid>

          {/* Key Indicators */}
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle2" gutterBottom>
                Key Market Indicators
              </Typography>
              
              <List dense>
                <ListItem>
                  <ListItemIcon>
                    <ShowChart sx={{ fontSize: 20 }} />
                  </ListItemIcon>
                  <ListItemText 
                    primary="Advance/Decline Ratio"
                    secondary={`${advance_decline.toFixed(2)} : 1`}
                  />
                  <Chip 
                    label={advance_decline > 1.5 ? 'Bullish' : advance_decline > 1 ? 'Neutral' : 'Bearish'}
                    size="small"
                    color={advance_decline > 1.5 ? 'success' : advance_decline > 1 ? 'default' : 'error'}
                  />
                </ListItem>

                <ListItem>
                  <ListItemIcon>
                    <TrendingUp sx={{ fontSize: 20 }} />
                  </ListItemIcon>
                  <ListItemText 
                    primary="New Highs vs Lows"
                    secondary={`${new_highs} / ${new_lows}`}
                  />
                  <Chip 
                    label={`${(new_highs / (new_highs + new_lows) * 100).toFixed(0)}%`}
                    size="small"
                    color={new_highs > new_lows * 2 ? 'success' : 'warning'}
                  />
                </ListItem>

                <ListItem>
                  <ListItemIcon>
                    <Assessment sx={{ fontSize: 20 }} />
                  </ListItemIcon>
                  <ListItemText 
                    primary="Put/Call Ratio"
                    secondary={put_call_ratio.toFixed(2)}
                  />
                  <Chip 
                    label={put_call_ratio > 1.2 ? 'Oversold' : put_call_ratio < 0.7 ? 'Overbought' : 'Neutral'}
                    size="small"
                    color={put_call_ratio > 1.2 ? 'success' : put_call_ratio < 0.7 ? 'error' : 'default'}
                  />
                </ListItem>

                <ListItem>
                  <ListItemIcon>
                    <Warning sx={{ fontSize: 20 }} />
                  </ListItemIcon>
                  <ListItemText 
                    primary="VIX Level"
                    secondary={vix_level.toFixed(2)}
                  />
                  <Chip 
                    label={vix_level < 15 ? 'Low' : vix_level < 25 ? 'Normal' : 'High'}
                    size="small"
                    color={vix_level < 15 ? 'success' : vix_level < 25 ? 'default' : 'error'}
                  />
                </ListItem>
              </List>
            </Paper>
          </Grid>

          {/* Growth Leaders Health */}
          <Grid item xs={12}>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2" gutterBottom>
                Growth Leaders Performance
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                <Box sx={{ flex: 1 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="caption">Leaders Trending Up</Typography>
                    <Typography variant="caption" fontWeight={600} color="success.main">
                      {growth_leaders_up} ({(growth_leaders_up / (growth_leaders_up + growth_leaders_down) * 100).toFixed(0)}%)
                    </Typography>
                  </Box>
                  <LinearProgress 
                    variant="determinate" 
                    value={growth_leaders_up / (growth_leaders_up + growth_leaders_down) * 100}
                    color="success"
                    sx={{ height: 8, borderRadius: 4 }}
                  />
                </Box>
                <Typography variant="body2" color="text.secondary">vs</Typography>
                <Box sx={{ flex: 1 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="caption">Leaders Breaking Down</Typography>
                    <Typography variant="caption" fontWeight={600} color="error.main">
                      {growth_leaders_down} ({(growth_leaders_down / (growth_leaders_up + growth_leaders_down) * 100).toFixed(0)}%)
                    </Typography>
                  </Box>
                  <LinearProgress 
                    variant="determinate" 
                    value={growth_leaders_down / (growth_leaders_up + growth_leaders_down) * 100}
                    color="error"
                    sx={{ height: 8, borderRadius: 4 }}
                  />
                </Box>
              </Box>
            </Paper>
          </Grid>

          {/* Follow-Through Day Info */}
          <Grid item xs={12}>
            <Box sx={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: 2,
              p: 2,
              backgroundColor: '#2196f30D',
              borderRadius: 1
            }}>
              <Schedule sx={{ color: '#2196f3' }} />
              <Box>
                <Typography variant="body2" fontWeight={600}>
                  Last Follow-Through Day: {new Date(follow_through_day).toLocaleDateString()}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {daysSinceFollowThrough} days ago - {daysSinceFollowThrough < 30 ? 'Recent rally' : 'Mature uptrend'}
                </Typography>
              </Box>
            </Box>
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
};

export default MarketTimingPanel;