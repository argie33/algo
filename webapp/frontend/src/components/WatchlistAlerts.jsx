import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Switch,
  FormControlLabel,
  Chip,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
  Alert,
  Divider,
  Grid,
  Tooltip,
  Badge
} from '@mui/material';
import {
  Add,
  Edit,
  Delete,
  Notifications,
  NotificationsActive,
  TrendingUp,
  TrendingDown,
  Warning,
  CheckCircle,
  Schedule,
  Settings
} from '@mui/icons-material';

const WatchlistAlerts = ({ watchlistItems, onAlertTriggered }) => {
  const [alerts, setAlerts] = useState([]);
  const [openDialog, setOpenDialog] = useState(false);
  const [editingAlert, setEditingAlert] = useState(null);
  const [alertForm, setAlertForm] = useState({
    symbol: '',
    type: 'price_above',
    value: '',
    enabled: true,
    frequency: 'once',
    notificationMethod: 'browser'
  });

  // Alert types
  const alertTypes = [
    { value: 'price_above', label: 'Price Above', icon: <TrendingUp /> },
    { value: 'price_below', label: 'Price Below', icon: <TrendingDown /> },
    { value: 'volume_spike', label: 'Volume Spike', icon: <Warning /> },
    { value: 'percent_change', label: 'Percent Change', icon: <TrendingUp /> },
    { value: 'technical_signal', label: 'Technical Signal', icon: <CheckCircle /> }
  ];

  // Load alerts from localStorage
  useEffect(() => {
    const savedAlerts = localStorage.getItem('watchlist_alerts');
    if (savedAlerts) {
      try {
        setAlerts(JSON.parse(savedAlerts));
      } catch (error) {
        console.error('Error loading alerts:', error);
      }
    }
  }, []);

  // Save alerts to localStorage
  useEffect(() => {
    localStorage.setItem('watchlist_alerts', JSON.stringify(alerts));
  }, [alerts]);

  // Check alerts against current market data
  useEffect(() => {
    if (watchlistItems && watchlistItems.length > 0) {
      checkAlerts();
    }
  }, [watchlistItems, alerts]);

  const checkAlerts = () => {
    const triggeredAlerts = [];

    alerts.forEach(alert => {
      if (!alert.enabled) return;

      const stock = watchlistItems.find(item => item.symbol === alert.symbol);
      if (!stock) return;

      let triggered = false;
      let message = '';

      switch (alert.type) {
        case 'price_above':
          if (stock.current_price >= parseFloat(alert.value)) {
            triggered = true;
            message = `${alert.symbol} price (${stock.current_price}) is above ${alert.value}`;
          }
          break;

        case 'price_below':
          if (stock.current_price <= parseFloat(alert.value)) {
            triggered = true;
            message = `${alert.symbol} price (${stock.current_price}) is below ${alert.value}`;
          }
          break;

        case 'volume_spike':
          if (stock.volume && stock.average_volume) {
            const volumeRatio = stock.volume / stock.average_volume;
            if (volumeRatio >= parseFloat(alert.value)) {
              triggered = true;
              message = `${alert.symbol} volume spike: ${volumeRatio.toFixed(1)}x average`;
            }
          }
          break;

        case 'percent_change':
          if (Math.abs(stock.day_change_percent) >= parseFloat(alert.value)) {
            triggered = true;
            message = `${alert.symbol} daily change: ${stock.day_change_percent.toFixed(2)}%`;
          }
          break;

        case 'technical_signal':
          // This would integrate with your technical analysis
          // For now, we'll use a simple RSI-like indicator
          if (stock.rsi) {
            if (alert.value === 'oversold' && stock.rsi <= 30) {
              triggered = true;
              message = `${alert.symbol} is oversold (RSI: ${stock.rsi.toFixed(1)})`;
            } else if (alert.value === 'overbought' && stock.rsi >= 70) {
              triggered = true;
              message = `${alert.symbol} is overbought (RSI: ${stock.rsi.toFixed(1)})`;
            }
          }
          break;
      }

      if (triggered) {
        triggeredAlerts.push({
          ...alert,
          message,
          timestamp: new Date().toISOString()
        });

        // Send notification
        sendNotification(alert, message);

        // Handle frequency
        if (alert.frequency === 'once') {
          setAlerts(prev => prev.map(a => 
            a.id === alert.id ? { ...a, enabled: false } : a
          ));
        }
      }
    });

    if (triggeredAlerts.length > 0 && onAlertTriggered) {
      onAlertTriggered(triggeredAlerts);
    }
  };

  const sendNotification = (alert, message) => {
    switch (alert.notificationMethod) {
      case 'browser':
        if (Notification.permission === 'granted') {
          new Notification('Watchlist Alert', {
            body: message,
            icon: '/favicon.ico',
            badge: '/favicon.ico'
          });
        }
        break;
      
      case 'email':
        // Would integrate with email service
        console.log('Email notification:', message);
        break;
      
      case 'sms':
        // Would integrate with SMS service
        console.log('SMS notification:', message);
        break;
    }
  };

  const handleCreateAlert = () => {
    setEditingAlert(null);
    setAlertForm({
      symbol: '',
      type: 'price_above',
      value: '',
      enabled: true,
      frequency: 'once',
      notificationMethod: 'browser'
    });
    setOpenDialog(true);
  };

  const handleEditAlert = (alert) => {
    setEditingAlert(alert);
    setAlertForm({ ...alert });
    setOpenDialog(true);
  };

  const handleSaveAlert = () => {
    if (!alertForm.symbol || !alertForm.value) return;

    const alertData = {
      id: editingAlert?.id || Date.now(),
      ...alertForm,
      createdAt: editingAlert?.createdAt || new Date().toISOString(),
      updatedAt: new Date().toISOString()
    };

    if (editingAlert) {
      setAlerts(prev => prev.map(a => a.id === editingAlert.id ? alertData : a));
    } else {
      setAlerts(prev => [...prev, alertData]);
    }

    setOpenDialog(false);
    setEditingAlert(null);
  };

  const handleDeleteAlert = (alertId) => {
    setAlerts(prev => prev.filter(a => a.id !== alertId));
  };

  const handleToggleAlert = (alertId) => {
    setAlerts(prev => prev.map(a => 
      a.id === alertId ? { ...a, enabled: !a.enabled } : a
    ));
  };

  const getAlertTypeInfo = (type) => {
    return alertTypes.find(t => t.value === type) || alertTypes[0];
  };

  const getAlertStatusColor = (alert) => {
    if (!alert.enabled) return 'default';
    
    const stock = watchlistItems?.find(item => item.symbol === alert.symbol);
    if (!stock) return 'warning';
    
    // Check if alert would trigger
    switch (alert.type) {
      case 'price_above':
        return stock.current_price >= parseFloat(alert.value) ? 'error' : 'success';
      case 'price_below':
        return stock.current_price <= parseFloat(alert.value) ? 'error' : 'success';
      default:
        return 'primary';
    }
  };

  const requestNotificationPermission = () => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  };

  useEffect(() => {
    requestNotificationPermission();
  }, []);

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
        <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Badge badgeContent={alerts.filter(a => a.enabled).length} color="primary">
            <Notifications />
          </Badge>
          Price Alerts
        </Typography>
        <Button
          variant="contained"
          size="small"
          startIcon={<Add />}
          onClick={handleCreateAlert}
        >
          Add Alert
        </Button>
      </Box>

      {alerts.length === 0 ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          No price alerts set. Create alerts to get notified when stocks reach your target prices.
        </Alert>
      ) : (
        <List>
          {alerts.map((alert) => {
            const typeInfo = getAlertTypeInfo(alert.type);
            const statusColor = getAlertStatusColor(alert);
            
            return (
              <ListItem key={alert.id} divider>
                <ListItemText
                  primary={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      {typeInfo.icon}
                      <Typography variant="body2" fontWeight="bold">
                        {alert.symbol}
                      </Typography>
                      <Chip
                        label={typeInfo.label}
                        size="small"
                        variant="outlined"
                        color={statusColor}
                      />
                      {alert.type === 'technical_signal' ? (
                        <Typography variant="body2">
                          {alert.value}
                        </Typography>
                      ) : (
                        <Typography variant="body2">
                          {alert.value}
                        </Typography>
                      )}
                    </Box>
                  }
                  secondary={
                    <Box sx={{ mt: 1 }}>
                      <Typography variant="caption" color="text.secondary">
                        {alert.frequency === 'once' ? 'One-time alert' : 'Recurring alert'} • 
                        {alert.notificationMethod} • 
                        Created {new Date(alert.createdAt).toLocaleDateString()}
                      </Typography>
                    </Box>
                  }
                />
                <ListItemSecondaryAction>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Switch
                      checked={alert.enabled}
                      onChange={() => handleToggleAlert(alert.id)}
                      size="small"
                    />
                    <Tooltip title="Edit alert">
                      <IconButton
                        size="small"
                        onClick={() => handleEditAlert(alert)}
                      >
                        <Edit />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Delete alert">
                      <IconButton
                        size="small"
                        onClick={() => handleDeleteAlert(alert.id)}
                        color="error"
                      >
                        <Delete />
                      </IconButton>
                    </Tooltip>
                  </Box>
                </ListItemSecondaryAction>
              </ListItem>
            );
          })}
        </List>
      )}

      {/* Create/Edit Alert Dialog */}
      <Dialog open={openDialog} onClose={() => setOpenDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {editingAlert ? 'Edit Alert' : 'Create Alert'}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>Stock Symbol</InputLabel>
                <Select
                  value={alertForm.symbol}
                  onChange={(e) => setAlertForm({...alertForm, symbol: e.target.value})}
                >
                  {watchlistItems?.map(item => (
                    <MenuItem key={item.symbol} value={item.symbol}>
                      {item.symbol} - {item.short_name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>Alert Type</InputLabel>
                <Select
                  value={alertForm.type}
                  onChange={(e) => setAlertForm({...alertForm, type: e.target.value})}
                >
                  {alertTypes.map(type => (
                    <MenuItem key={type.value} value={type.value}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        {type.icon}
                        {type.label}
                      </Box>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>

            <Grid item xs={12}>
              {alertForm.type === 'technical_signal' ? (
                <FormControl fullWidth>
                  <InputLabel>Signal Type</InputLabel>
                  <Select
                    value={alertForm.value}
                    onChange={(e) => setAlertForm({...alertForm, value: e.target.value})}
                  >
                    <MenuItem value="oversold">Oversold (RSI ≤ 30)</MenuItem>
                    <MenuItem value="overbought">Overbought (RSI ≥ 70)</MenuItem>
                    <MenuItem value="breakout">Breakout</MenuItem>
                    <MenuItem value="breakdown">Breakdown</MenuItem>
                  </Select>
                </FormControl>
              ) : (
                <TextField
                  fullWidth
                  label={
                    alertForm.type === 'price_above' || alertForm.type === 'price_below' ? 'Price' :
                    alertForm.type === 'volume_spike' ? 'Volume Multiplier' :
                    alertForm.type === 'percent_change' ? 'Percentage' : 'Value'
                  }
                  type="number"
                  value={alertForm.value}
                  onChange={(e) => setAlertForm({...alertForm, value: e.target.value})}
                  placeholder={
                    alertForm.type === 'price_above' || alertForm.type === 'price_below' ? '150.00' :
                    alertForm.type === 'volume_spike' ? '2.0' :
                    alertForm.type === 'percent_change' ? '5.0' : ''
                  }
                />
              )}
            </Grid>

            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>Frequency</InputLabel>
                <Select
                  value={alertForm.frequency}
                  onChange={(e) => setAlertForm({...alertForm, frequency: e.target.value})}
                >
                  <MenuItem value="once">One-time</MenuItem>
                  <MenuItem value="daily">Daily</MenuItem>
                  <MenuItem value="always">Always</MenuItem>
                </Select>
              </FormControl>
            </Grid>

            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>Notification Method</InputLabel>
                <Select
                  value={alertForm.notificationMethod}
                  onChange={(e) => setAlertForm({...alertForm, notificationMethod: e.target.value})}
                >
                  <MenuItem value="browser">Browser Notification</MenuItem>
                  <MenuItem value="email">Email</MenuItem>
                  <MenuItem value="sms">SMS</MenuItem>
                </Select>
              </FormControl>
            </Grid>

            <Grid item xs={12}>
              <FormControlLabel
                control={
                  <Switch
                    checked={alertForm.enabled}
                    onChange={(e) => setAlertForm({...alertForm, enabled: e.target.checked})}
                  />
                }
                label="Enable Alert"
              />
            </Grid>
          </Grid>

          {Notification.permission === 'default' && (
            <Alert severity="info" sx={{ mt: 2 }}>
              <Button
                size="small"
                onClick={requestNotificationPermission}
                sx={{ mr: 1 }}
              >
                Enable Notifications
              </Button>
              Enable browser notifications to receive alerts.
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDialog(false)}>Cancel</Button>
          <Button onClick={handleSaveAlert} variant="contained">
            {editingAlert ? 'Update' : 'Create'} Alert
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default WatchlistAlerts;