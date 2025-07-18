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
    <div>
      <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
        <div  variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <span className="inline-flex items-center justify-center px-2 py-1 text-xs font-bold leading-none text-red-100 bg-red-600 rounded-full" badgeContent={alerts.filter(a => a.enabled).length} color="primary">
            <Notifications />
          </span>
          Price Alerts
        </div>
        <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
          variant="contained"
          size="small"
          startIcon={<Add />}
          onClick={handleCreateAlert}
        >
          Add Alert
        </button>
      </div>

      {alerts.length === 0 ? (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info" sx={{ mb: 2 }}>
          No price alerts set. Create alerts to get notified when stocks reach your target prices.
        </div>
      ) : (
        <List>
          {alerts.map((alert) => {
            const typeInfo = getAlertTypeInfo(alert.type);
            const statusColor = getAlertStatusColor(alert);
            
            return (
              <ListItem key={alert.id} divider>
                <ListItemText
                  primary={
                    <div  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      {typeInfo.icon}
                      <div  variant="body2" fontWeight="bold">
                        {alert.symbol}
                      </div>
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                        label={typeInfo.label}
                        size="small"
                        variant="outlined"
                        color={statusColor}
                      />
                      {alert.type === 'technical_signal' ? (
                        <div  variant="body2">
                          {alert.value}
                        </div>
                      ) : (
                        <div  variant="body2">
                          {alert.value}
                        </div>
                      )}
                    </div>
                  }
                  secondary={
                    <div  sx={{ mt: 1 }}>
                      <div  variant="caption" color="text.secondary">
                        {alert.frequency === 'once' ? 'One-time alert' : 'Recurring alert'} • 
                        {alert.notificationMethod} • 
                        Created {new Date(alert.createdAt).toLocaleDateString()}
                      </div>
                    </div>
                  }
                />
                <ListItemSecondaryAction>
                  <div  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <input type="checkbox" className="toggle"
                      checked={alert.enabled}
                      onChange={() => handleToggleAlert(alert.id)}
                      size="small"
                    />
                    <div  title="Edit alert">
                      <button className="p-2 rounded-full hover:bg-gray-100"
                        size="small"
                        onClick={() => handleEditAlert(alert)}
                      >
                        <Edit />
                      </button>
                    </div>
                    <div  title="Delete alert">
                      <button className="p-2 rounded-full hover:bg-gray-100"
                        size="small"
                        onClick={() => handleDeleteAlert(alert.id)}
                        color="error"
                      >
                        <Delete />
                      </button>
                    </div>
                  </div>
                </ListItemSecondaryAction>
              </ListItem>
            );
          })}
        </List>
      )}

      {/* Create/Edit Alert Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" open={openDialog} onClose={() => setOpenDialog(false)} maxWidth="sm" fullWidth>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>
          {editingAlert ? 'Edit Alert' : 'Create Alert'}
        </h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
          <div className="grid" container spacing={2} sx={{ mt: 1 }}>
            <div className="grid" item xs={12} sm={6}>
              <div className="mb-4" fullWidth>
                <label className="block text-sm font-medium text-gray-700 mb-1">Stock Symbol</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={alertForm.symbol}
                  onChange={(e) => setAlertForm({...alertForm, symbol: e.target.value})}
                >
                  {watchlistItems?.map(item => (
                    <option  key={item.symbol} value={item.symbol}>
                      {item.symbol} - {item.short_name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            
            <div className="grid" item xs={12} sm={6}>
              <div className="mb-4" fullWidth>
                <label className="block text-sm font-medium text-gray-700 mb-1">Alert Type</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={alertForm.type}
                  onChange={(e) => setAlertForm({...alertForm, type: e.target.value})}
                >
                  {alertTypes.map(type => (
                    <option  key={type.value} value={type.value}>
                      <div  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        {type.icon}
                        {type.label}
                      </div>
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid" item xs={12}>
              {alertForm.type === 'technical_signal' ? (
                <div className="mb-4" fullWidth>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Signal Type</label>
                  <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={alertForm.value}
                    onChange={(e) => setAlertForm({...alertForm, value: e.target.value})}
                  >
                    <option  value="oversold">Oversold (RSI ≤ 30)</option>
                    <option  value="overbought">Overbought (RSI ≥ 70)</option>
                    <option  value="breakout">Breakout</option>
                    <option  value="breakdown">Breakdown</option>
                  </select>
                </div>
              ) : (
                <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
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
            </div>

            <div className="grid" item xs={12} sm={6}>
              <div className="mb-4" fullWidth>
                <label className="block text-sm font-medium text-gray-700 mb-1">Frequency</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={alertForm.frequency}
                  onChange={(e) => setAlertForm({...alertForm, frequency: e.target.value})}
                >
                  <option  value="once">One-time</option>
                  <option  value="daily">Daily</option>
                  <option  value="always">Always</option>
                </select>
              </div>
            </div>

            <div className="grid" item xs={12} sm={6}>
              <div className="mb-4" fullWidth>
                <label className="block text-sm font-medium text-gray-700 mb-1">Notification Method</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={alertForm.notificationMethod}
                  onChange={(e) => setAlertForm({...alertForm, notificationMethod: e.target.value})}
                >
                  <option  value="browser">Browser Notification</option>
                  <option  value="email">Email</option>
                  <option  value="sms">SMS</option>
                </select>
              </div>
            </div>

            <div className="grid" item xs={12}>
              <div className="mb-4"Label
                control={
                  <input type="checkbox" className="toggle"
                    checked={alertForm.enabled}
                    onChange={(e) => setAlertForm({...alertForm, enabled: e.target.checked})}
                  />
                }
                label="Enable Alert"
              />
            </div>
          </div>

          {Notification.permission === 'default' && (
            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info" sx={{ mt: 2 }}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                size="small"
                onClick={requestNotificationPermission}
                sx={{ mr: 1 }}
              >
                Enable Notifications
              </button>
              Enable browser notifications to receive alerts.
            </div>
          )}
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setOpenDialog(false)}>Cancel</button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={handleSaveAlert} variant="contained">
            {editingAlert ? 'Update' : 'Create'} Alert
          </button>
        </div>
      </div>
    </div>
  );
};

export default WatchlistAlerts;