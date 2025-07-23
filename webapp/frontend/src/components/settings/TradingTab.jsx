import React from 'react';
import {
  Grid,
  Card,
  CardContent,
  Typography,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Switch,
  FormControlLabel,
  InputAdornment
} from '@mui/material';
import {
  TrendingUp,
  Security
} from '@mui/icons-material';

const TradingTab = ({ settings, updateSettings }) => {
  return (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Typography variant="h5" gutterBottom>
          Trading Preferences
        </Typography>
      </Grid>
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              <TrendingUp sx={{ mr: 1, verticalAlign: 'middle' }} />
              Order Settings
            </Typography>
            
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <FormControl fullWidth>
                  <InputLabel>Default Order Type</InputLabel>
                  <Select
                    value={settings?.trading?.defaultOrderType || 'market'}
                    onChange={(e) => updateSettings('trading', 'defaultOrderType', e.target.value)}
                  >
                    <MenuItem value="market">Market</MenuItem>
                    <MenuItem value="limit">Limit</MenuItem>
                    <MenuItem value="stop">Stop</MenuItem>
                    <MenuItem value="stop_limit">Stop Limit</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              
              <Grid item xs={12}>
                <FormControl fullWidth>
                  <InputLabel>Time in Force</InputLabel>
                  <Select
                    value={settings?.trading?.defaultTimeInForce || 'day'}
                    onChange={(e) => updateSettings('trading', 'defaultTimeInForce', e.target.value)}
                  >
                    <MenuItem value="day">Day</MenuItem>
                    <MenuItem value="gtc">Good Till Canceled</MenuItem>
                    <MenuItem value="ioc">Immediate or Cancel</MenuItem>
                    <MenuItem value="fok">Fill or Kill</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              
              <Grid item xs={12}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={settings?.trading?.enableAfterHours || false}
                      onChange={(e) => updateSettings('trading', 'enableAfterHours', e.target.checked)}
                    />
                  }
                  label="Enable After Hours Trading"
                />
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              <Security sx={{ mr: 1, verticalAlign: 'middle' }} />
              Risk Management
            </Typography>
            
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Max Position Size (%)"
                  type="number"
                  value={(settings?.trading?.maxPositionSize || 0.05) * 100}
                  onChange={(e) => updateSettings('trading', 'maxPositionSize', e.target.value / 100)}
                  InputProps={{
                    endAdornment: <InputAdornment position="end">%</InputAdornment>
                  }}
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Max Daily Loss (%)"
                  type="number"
                  value={(settings?.trading?.maxDailyLoss || 0.02) * 100}
                  onChange={(e) => updateSettings('trading', 'maxDailyLoss', e.target.value / 100)}
                  InputProps={{
                    endAdornment: <InputAdornment position="end">%</InputAdornment>
                  }}
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Risk Per Trade (%)"
                  type="number"
                  value={(settings?.trading?.riskPerTrade || 0.01) * 100}
                  onChange={(e) => updateSettings('trading', 'riskPerTrade', e.target.value / 100)}
                  InputProps={{
                    endAdornment: <InputAdornment position="end">%</InputAdornment>
                  }}
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Max Open Positions"
                  type="number"
                  value={settings?.trading?.maxOpenPositions || 10}
                  onChange={(e) => updateSettings('trading', 'maxOpenPositions', parseInt(e.target.value))}
                />
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              <Security sx={{ mr: 1, verticalAlign: 'middle' }} />
              Stop Loss & Take Profit
            </Typography>
            
            <Grid container spacing={2}>
              <Grid item xs={12} md={6}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={settings?.trading?.autoStopLoss || true}
                      onChange={(e) => updateSettings('trading', 'autoStopLoss', e.target.checked)}
                    />
                  }
                  label="Auto Stop Loss"
                />
                {settings?.trading?.autoStopLoss && (
                  <TextField
                    fullWidth
                    label="Default Stop Loss (%)"
                    type="number"
                    value={(settings?.trading?.defaultStopLoss || 0.02) * 100}
                    onChange={(e) => updateSettings('trading', 'defaultStopLoss', e.target.value / 100)}
                    InputProps={{
                      endAdornment: <InputAdornment position="end">%</InputAdornment>
                    }}
                    sx={{ mt: 1 }}
                  />
                )}
              </Grid>
              
              <Grid item xs={12} md={6}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={settings?.trading?.autoTakeProfit || true}
                      onChange={(e) => updateSettings('trading', 'autoTakeProfit', e.target.checked)}
                    />
                  }
                  label="Auto Take Profit"
                />
                {settings?.trading?.autoTakeProfit && (
                  <TextField
                    fullWidth
                    label="Default Take Profit (%)"
                    type="number"
                    value={(settings?.trading?.defaultTakeProfit || 0.04) * 100}
                    onChange={(e) => updateSettings('trading', 'defaultTakeProfit', e.target.value / 100)}
                    InputProps={{
                      endAdornment: <InputAdornment position="end">%</InputAdornment>
                    }}
                    sx={{ mt: 1 }}
                  />
                )}
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );
};

export default TradingTab;