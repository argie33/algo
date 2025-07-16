import React, { useState, useEffect } from 'react';
import {
  Box, Card, CardContent, Typography, Switch, FormControlLabel,
  Grid, Button, Slider, Select, MenuItem, FormControl, InputLabel,
  Chip, Stack, Divider, IconButton, Collapse
} from '@mui/material';
import {
  Settings, Dashboard, Visibility, VisibilityOff, 
  DragIndicator, Add, Remove, Tune, Palette,
  Timeline, PieChart, BarChart, ShowChart
} from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';

const DashboardCustomization = ({ onSettingsChange }) => {
  const { user } = useAuth();
  const [expanded, setExpanded] = useState(false);
  const [settings, setSettings] = useState({
    layout: 'grid', // 'grid', 'list', 'compact'
    theme: 'auto', // 'light', 'dark', 'auto'
    widgets: {
      portfolio: { enabled: true, size: 'medium', position: 0 },
      market: { enabled: true, size: 'small', position: 1 },
      news: { enabled: true, size: 'medium', position: 2 },
      signals: { enabled: true, size: 'large', position: 3 },
      watchlist: { enabled: true, size: 'medium', position: 4 },
      performance: { enabled: true, size: 'large', position: 5 },
      economic: { enabled: false, size: 'small', position: 6 }
    },
    animations: true,
    autoRefresh: true,
    refreshInterval: 30, // seconds
    density: 'comfortable' // 'compact', 'comfortable', 'spacious'
  });

  // Load settings from localStorage on component mount
  useEffect(() => {
    const savedSettings = localStorage.getItem(`dashboard-settings-${user?.id || 'default'}`);
    if (savedSettings) {
      setSettings(JSON.parse(savedSettings));
    }
  }, [user]);

  // Save settings to localStorage and notify parent
  const updateSettings = (newSettings) => {
    setSettings(newSettings);
    localStorage.setItem(`dashboard-settings-${user?.id || 'default'}`, JSON.stringify(newSettings));
    onSettingsChange(newSettings);
  };

  const handleLayoutChange = (layout) => {
    updateSettings({ ...settings, layout });
  };

  const handleWidgetToggle = (widgetKey) => {
    updateSettings({
      ...settings,
      widgets: {
        ...settings.widgets,
        [widgetKey]: {
          ...settings.widgets[widgetKey],
          enabled: !settings.widgets[widgetKey].enabled
        }
      }
    });
  };

  const handleWidgetSize = (widgetKey, size) => {
    updateSettings({
      ...settings,
      widgets: {
        ...settings.widgets,
        [widgetKey]: {
          ...settings.widgets[widgetKey],
          size
        }
      }
    });
  };

  const widgetLabels = {
    portfolio: 'Portfolio Overview',
    market: 'Market Summary',
    news: 'News & Events',
    signals: 'Trading Signals',
    watchlist: 'Watchlist',
    performance: 'Performance Analytics',
    economic: 'Economic Indicators'
  };

  const widgetIcons = {
    portfolio: <PieChart />,
    market: <ShowChart />,
    news: <Timeline />,
    signals: <BarChart />,
    watchlist: <Visibility />,
    performance: <Timeline />,
    economic: <ShowChart />
  };

  return (
    <Card sx={{ mb: 3 }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Settings />
            <Typography variant="h6">Dashboard Customization</Typography>
          </Box>
          <Button
            variant="outlined"
            onClick={() => setExpanded(!expanded)}
            startIcon={<Tune />}
            size="small"
          >
            {expanded ? 'Hide' : 'Customize'}
          </Button>
        </Box>

        <Collapse in={expanded}>
          <Stack spacing={3}>
            {/* Layout Settings */}
            <Box>
              <Typography variant="subtitle1" gutterBottom>Layout Style</Typography>
              <Stack direction="row" spacing={1}>
                {['grid', 'list', 'compact'].map((layout) => (
                  <Chip
                    key={layout}
                    label={layout.charAt(0).toUpperCase() + layout.slice(1)}
                    clickable
                    color={settings.layout === layout ? 'primary' : 'default'}
                    onClick={() => handleLayoutChange(layout)}
                  />
                ))}
              </Stack>
            </Box>

            <Divider />

            {/* Widget Management */}
            <Box>
              <Typography variant="subtitle1" gutterBottom>Widgets</Typography>
              <Grid container spacing={2}>
                {Object.entries(settings.widgets).map(([key, widget]) => (
                  <Grid item xs={12} sm={6} md={4} key={key}>
                    <Card variant="outlined" sx={{ p: 2 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                        {widgetIcons[key]}
                        <Typography variant="body2" sx={{ flex: 1 }}>
                          {widgetLabels[key]}
                        </Typography>
                        <Switch
                          checked={widget.enabled}
                          onChange={() => handleWidgetToggle(key)}
                          size="small"
                        />
                      </Box>
                      {widget.enabled && (
                        <FormControl size="small" fullWidth>
                          <InputLabel>Size</InputLabel>
                          <Select
                            value={widget.size}
                            onChange={(e) => handleWidgetSize(key, e.target.value)}
                          >
                            <MenuItem value="small">Small</MenuItem>
                            <MenuItem value="medium">Medium</MenuItem>
                            <MenuItem value="large">Large</MenuItem>
                          </Select>
                        </FormControl>
                      )}
                    </Card>
                  </Grid>
                ))}
              </Grid>
            </Box>

            <Divider />

            {/* Performance Settings */}
            <Box>
              <Typography variant="subtitle1" gutterBottom>Performance</Typography>
              <Stack spacing={2}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={settings.animations}
                      onChange={(e) => updateSettings({ ...settings, animations: e.target.checked })}
                    />
                  }
                  label="Enable animations"
                />
                <FormControlLabel
                  control={
                    <Switch
                      checked={settings.autoRefresh}
                      onChange={(e) => updateSettings({ ...settings, autoRefresh: e.target.checked })}
                    />
                  }
                  label="Auto-refresh data"
                />
                {settings.autoRefresh && (
                  <Box>
                    <Typography variant="body2" gutterBottom>
                      Refresh interval: {settings.refreshInterval} seconds
                    </Typography>
                    <Slider
                      value={settings.refreshInterval}
                      onChange={(_, value) => updateSettings({ ...settings, refreshInterval: value })}
                      min={10}
                      max={300}
                      step={10}
                      marks={[
                        { value: 10, label: '10s' },
                        { value: 60, label: '1m' },
                        { value: 300, label: '5m' }
                      ]}
                      sx={{ mt: 1 }}
                    />
                  </Box>
                )}
              </Stack>
            </Box>

            <Divider />

            {/* Quick Actions */}
            <Box>
              <Typography variant="subtitle1" gutterBottom>Quick Actions</Typography>
              <Stack direction="row" spacing={1}>
                <Button
                  variant="outlined"
                  size="small"
                  onClick={() => {
                    const defaultSettings = {
                      layout: 'grid',
                      widgets: Object.fromEntries(
                        Object.entries(settings.widgets).map(([key, widget]) => [
                          key, { ...widget, enabled: true, size: 'medium' }
                        ])
                      ),
                      animations: true,
                      autoRefresh: true,
                      refreshInterval: 30,
                      density: 'comfortable'
                    };
                    updateSettings(defaultSettings);
                  }}
                >
                  Reset to Default
                </Button>
                <Button
                  variant="outlined"
                  size="small"
                  onClick={() => {
                    const compactSettings = {
                      ...settings,
                      layout: 'compact',
                      density: 'compact',
                      widgets: Object.fromEntries(
                        Object.entries(settings.widgets).map(([key, widget]) => [
                          key, { ...widget, size: 'small' }
                        ])
                      )
                    };
                    updateSettings(compactSettings);
                  }}
                >
                  Compact Mode
                </Button>
                <Button
                  variant="outlined"
                  size="small"
                  onClick={() => {
                    const performanceSettings = {
                      ...settings,
                      animations: false,
                      autoRefresh: false,
                      widgets: Object.fromEntries(
                        Object.entries(settings.widgets).map(([key, widget]) => [
                          key, { ...widget, enabled: ['portfolio', 'market', 'signals'].includes(key) }
                        ])
                      )
                    };
                    updateSettings(performanceSettings);
                  }}
                >
                  Performance Mode
                </Button>
              </Stack>
            </Box>
          </Stack>
        </Collapse>
      </CardContent>
    </Card>
  );
};

export default DashboardCustomization;