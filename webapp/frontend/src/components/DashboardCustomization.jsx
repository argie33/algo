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
    <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
      <div className="bg-white shadow-md rounded-lg"Content>
        <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
          <div  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Settings />
            <div  variant="h6">Dashboard Customization</div>
          </div>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            variant="outlined"
            onClick={() => setExpanded(!expanded)}
            startIcon={<Tune />}
            size="small"
          >
            {expanded ? 'Hide' : 'Customize'}
          </button>
        </div>

        <Collapse in={expanded}>
          <div className="flex flex-col space-y-2" spacing={3}>
            {/* Layout Settings */}
            <div>
              <div  variant="subtitle1" gutterBottom>Layout Style</div>
              <div className="flex flex-col space-y-2" direction="row" spacing={1}>
                {['grid', 'list', 'compact'].map((layout) => (
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                    key={layout}
                    label={layout.charAt(0).toUpperCase() + layout.slice(1)}
                    clickable
                    color={settings.layout === layout ? 'primary' : 'default'}
                    onClick={() => handleLayoutChange(layout)}
                  />
                ))}
              </div>
            </div>

            <hr className="border-gray-200" />

            {/* Widget Management */}
            <div>
              <div  variant="subtitle1" gutterBottom>Widgets</div>
              <div className="grid" container spacing={2}>
                {Object.entries(settings.widgets).map(([key, widget]) => (
                  <div className="grid" item xs={12} sm={6} md={4} key={key}>
                    <div className="bg-white shadow-md rounded-lg" variant="outlined" sx={{ p: 2 }}>
                      <div  sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                        {widgetIcons[key]}
                        <div  variant="body2" sx={{ flex: 1 }}>
                          {widgetLabels[key]}
                        </div>
                        <input type="checkbox" className="toggle"
                          checked={widget.enabled}
                          onChange={() => handleWidgetToggle(key)}
                          size="small"
                        />
                      </div>
                      {widget.enabled && (
                        <div className="mb-4" size="small" fullWidth>
                          <label className="block text-sm font-medium text-gray-700 mb-1">Size</label>
                          <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                            value={widget.size}
                            onChange={(e) => handleWidgetSize(key, e.target.value)}
                          >
                            <option  value="small">Small</option>
                            <option  value="medium">Medium</option>
                            <option  value="large">Large</option>
                          </select>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <hr className="border-gray-200" />

            {/* Performance Settings */}
            <div>
              <div  variant="subtitle1" gutterBottom>Performance</div>
              <div className="flex flex-col space-y-2" spacing={2}>
                <div className="mb-4"Label
                  control={
                    <input type="checkbox" className="toggle"
                      checked={settings.animations}
                      onChange={(e) => updateSettings({ ...settings, animations: e.target.checked })}
                    />
                  }
                  label="Enable animations"
                />
                <div className="mb-4"Label
                  control={
                    <input type="checkbox" className="toggle"
                      checked={settings.autoRefresh}
                      onChange={(e) => updateSettings({ ...settings, autoRefresh: e.target.checked })}
                    />
                  }
                  label="Auto-refresh data"
                />
                {settings.autoRefresh && (
                  <div>
                    <div  variant="body2" gutterBottom>
                      Refresh interval: {settings.refreshInterval} seconds
                    </div>
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
                  </div>
                )}
              </div>
            </div>

            <hr className="border-gray-200" />

            {/* Quick Actions */}
            <div>
              <div  variant="subtitle1" gutterBottom>Quick Actions</div>
              <div className="flex flex-col space-y-2" direction="row" spacing={1}>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                </button>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                </button>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                </button>
              </div>
            </div>
          </div>
        </Collapse>
      </div>
    </div>
  );
};

export default DashboardCustomization;