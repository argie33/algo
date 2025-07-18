import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  Card,
  CardContent,
  Switch,
  FormControlLabel,
  Button,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Autocomplete,
  Alert,
  LinearProgress,
  IconButton,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Tabs,
  Tab,
  Badge,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  CircularProgress,
  Avatar,
  Snackbar,
  AlertTitle
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  PlayArrow,
  Stop,
  Settings,
  Analytics,
  Speed,
  SignalWifi4Bar,
  SignalWifiOff,
  Refresh,
  Add,
  Delete,
  Timeline,
  ShowChart,
  MonetizationOn,
  Assessment,
  Warning,
  CheckCircle,
  Error,
  Info,
  AdminPanelSettings,
  Dashboard,
  Storage,
  NetworkCheck,
  CloudSync,
  DataUsage,
  Security,
  Notifications,
  Schedule,
  ExpandMore,
  MoreVert,
  Power,
  PowerOff,
  Restore,
  ClearAll,
  Build,
  HealthAndSafety,
  TrendingFlat,
  SyncAlt,
  AutoFixHigh,
  ReportProblem,
  OnlinePrediction
} from '@mui/icons-material';
import liveDataIntegration from '../services/liveDataIntegration';
import webSocketService from '../services/webSocketService';

const UnifiedDataManagement = () => {
  const [activeTab, setActiveTab] = useState(0);
  const [systemStatus, setSystemStatus] = useState({
    overall: 'healthy',
    database: 'connected',
    webSocket: 'connected',
    dataProviders: 'active',
    lastUpdate: new Date()
  });
  const [dataStreams, setDataStreams] = useState([]);
  const [apiKeys, setApiKeys] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'info' });

  // Mock data for demonstration
  const mockDataStreams = [
    {
      id: 1,
      name: 'Real-time Stock Prices',
      provider: 'Alpaca',
      status: 'active',
      symbols: 4567,
      latency: 45,
      throughput: '1.2K/s',
      cost: '$89.50',
      quality: 98.5
    },
    {
      id: 2,
      name: 'Options Data',
      provider: 'Yahoo Finance',
      status: 'active',
      symbols: 1234,
      latency: 120,
      throughput: '456/s',
      cost: '$34.20',
      quality: 96.8
    },
    {
      id: 3,
      name: 'Economic Data',
      provider: 'FRED',
      status: 'active',
      symbols: 89,
      latency: 5000,
      throughput: '2/s',
      cost: '$0.00',
      quality: 99.9
    },
    {
      id: 4,
      name: 'Crypto Data',
      provider: 'Binance',
      status: 'warning',
      symbols: 567,
      latency: 89,
      throughput: '890/s',
      cost: '$45.67',
      quality: 94.2
    }
  ];

  const mockApiKeys = [
    { id: 1, provider: 'Alpaca', status: 'active', lastUsed: '2 mins ago', usage: '78%' },
    { id: 2, provider: 'Yahoo Finance', status: 'active', lastUsed: '5 mins ago', usage: '23%' },
    { id: 3, provider: 'FRED', status: 'active', lastUsed: '1 hour ago', usage: '5%' },
    { id: 4, provider: 'Binance', status: 'warning', lastUsed: '10 mins ago', usage: '89%' }
  ];

  const mockAlerts = [
    { id: 1, type: 'warning', message: 'Binance API usage approaching limit', timestamp: '2 mins ago' },
    { id: 2, type: 'info', message: 'Data quality check completed successfully', timestamp: '15 mins ago' },
    { id: 3, type: 'error', message: 'WebSocket connection interrupted briefly', timestamp: '1 hour ago' }
  ];

  useEffect(() => {
    setDataStreams(mockDataStreams);
    setApiKeys(mockApiKeys);
    setAlerts(mockAlerts);
  }, []);

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'active':
      case 'healthy':
      case 'connected':
        return 'success';
      case 'warning':
        return 'warning';
      case 'error':
      case 'disconnected':
        return 'error';
      default:
        return 'default';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'active':
      case 'healthy':
      case 'connected':
        return <CheckCircle color="success" />;
      case 'warning':
        return <Warning color="warning" />;
      case 'error':
      case 'disconnected':
        return <Error color="error" />;
      default:
        return <Info />;
    }
  };

  const handleStreamAction = (streamId, action) => {
    setSnackbar({
      open: true,
      message: `${action} applied to stream ${streamId}`,
      severity: 'success'
    });
  };

  const SystemOverview = () => (
    <div className="grid" container spacing={3}>
      {/* System Status Cards */}
      <div className="grid" item xs={12} md={3}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  display="flex" alignItems="center" mb={2}>
              <HealthAndSafety sx={{ mr: 1, color: 'success.main' }} />
              <div  variant="h6">System Health</div>
            </div>
            <div  display="flex" alignItems="center" justifyContent="space-between">
              <div  variant="h4" color="success.main">98.5%</div>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Healthy" color="success" size="small" />
            </div>
          </div>
        </div>
      </div>

      <div className="grid" item xs={12} md={3}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  display="flex" alignItems="center" mb={2}>
              <DataUsage sx={{ mr: 1, color: 'info.main' }} />
              <div  variant="h6">Data Throughput</div>
            </div>
            <div  display="flex" alignItems="center" justifyContent="space-between">
              <div  variant="h4" color="info.main">2.5K/s</div>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Normal" color="info" size="small" />
            </div>
          </div>
        </div>
      </div>

      <div className="grid" item xs={12} md={3}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  display="flex" alignItems="center" mb={2}>
              <MonetizationOn sx={{ mr: 1, color: 'warning.main' }} />
              <div  variant="h6">Daily Cost</div>
            </div>
            <div  display="flex" alignItems="center" justifyContent="space-between">
              <div  variant="h4" color="warning.main">$169.37</div>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Budget OK" color="success" size="small" />
            </div>
          </div>
        </div>
      </div>

      <div className="grid" item xs={12} md={3}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  display="flex" alignItems="center" mb={2}>
              <Speed sx={{ mr: 1, color: 'success.main' }} />
              <div  variant="h6">Avg Latency</div>
            </div>
            <div  display="flex" alignItems="center" justifyContent="space-between">
              <div  variant="h4" color="success.main">63ms</div>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Excellent" color="success" size="small" />
            </div>
          </div>
        </div>
      </div>

      {/* Recent Alerts */}
      <div className="grid" item xs={12}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  display="flex" alignItems="center" justifyContent="space-between" mb={2}>
              <div  variant="h6">Recent Alerts</div>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" size="small" startIcon={<ClearAll />}>Clear All</button>
            </div>
            <List>
              {alerts.map((alert) => (
                <ListItem key={alert.id}>
                  <ListItemIcon>
                    {alert.type === 'warning' && <Warning color="warning" />}
                    {alert.type === 'error' && <Error color="error" />}
                    {alert.type === 'info' && <Info color="info" />}
                  </ListItemIcon>
                  <ListItemText
                    primary={alert.message}
                    secondary={alert.timestamp}
                  />
                </ListItem>
              ))}
            </List>
          </div>
        </div>
      </div>
    </div>
  );

  const DataStreams = () => (
    <div className="grid" container spacing={3}>
      <div className="grid" item xs={12}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  display="flex" alignItems="center" justifyContent="space-between" mb={2}>
              <div  variant="h6">Active Data Streams</div>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" startIcon={<Add />} variant="contained" size="small">
                Add Stream
              </button>
            </div>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Stream Name</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Provider</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Status</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbols</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Latency</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Throughput</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Quality</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Cost</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Actions</td>
                  </tr>
                </thead>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                  {dataStreams.map((stream) => (
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={stream.id}>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{stream.name}</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{stream.provider}</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                          label={stream.status}
                          color={getStatusColor(stream.status)}
                          size="small"
                          icon={getStatusIcon(stream.status)}
                        />
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{stream.symbols.toLocaleString()}</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{stream.latency}ms</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{stream.throughput}</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                        <div  display="flex" alignItems="center">
                          <div className="w-full bg-gray-200 rounded-full h-2"
                            variant="determinate"
                            value={stream.quality}
                            sx={{ width: 60, mr: 1 }}
                          />
                          <div  variant="body2">{stream.quality}%</div>
                        </div>
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{stream.cost}</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                        <button className="p-2 rounded-full hover:bg-gray-100"
                          size="small"
                          onClick={() => handleStreamAction(stream.id, 'pause')}
                        >
                          <Stop />
                        </button>
                        <button className="p-2 rounded-full hover:bg-gray-100"
                          size="small"
                          onClick={() => handleStreamAction(stream.id, 'restart')}
                        >
                          <Refresh />
                        </button>
                        <button className="p-2 rounded-full hover:bg-gray-100"
                          size="small"
                          onClick={() => handleStreamAction(stream.id, 'configure')}
                        >
                          <Settings />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  const ApiManagement = () => (
    <div className="grid" container spacing={3}>
      <div className="grid" item xs={12}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  display="flex" alignItems="center" justifyContent="space-between" mb={2}>
              <div  variant="h6">API Keys & Providers</div>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" startIcon={<Add />} variant="contained" size="small">
                Add API Key
              </button>
            </div>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Provider</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Status</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Last Used</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Usage</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Actions</td>
                  </tr>
                </thead>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                  {apiKeys.map((key) => (
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={key.id}>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{key.provider}</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                          label={key.status}
                          color={getStatusColor(key.status)}
                          size="small"
                          icon={getStatusIcon(key.status)}
                        />
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{key.lastUsed}</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                        <div  display="flex" alignItems="center">
                          <div className="w-full bg-gray-200 rounded-full h-2"
                            variant="determinate"
                            value={parseInt(key.usage)}
                            sx={{ width: 60, mr: 1 }}
                            color={parseInt(key.usage) > 80 ? 'warning' : 'primary'}
                          />
                          <div  variant="body2">{key.usage}</div>
                        </div>
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                        <button className="p-2 rounded-full hover:bg-gray-100" size="small">
                          <Settings />
                        </button>
                        <button className="p-2 rounded-full hover:bg-gray-100" size="small">
                          <Refresh />
                        </button>
                        <button className="p-2 rounded-full hover:bg-gray-100" size="small" color="error">
                          <Delete />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  const SystemControls = () => (
    <div className="grid" container spacing={3}>
      <div className="grid" item xs={12} md={6}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              System Controls
            </div>
            <div  display="flex" flexDirection="column" gap={2}>
              <div className="mb-4"Label
                control={<input type="checkbox" className="toggle" defaultChecked />}
                label="Real-time Data Streaming"
              />
              <div className="mb-4"Label
                control={<input type="checkbox" className="toggle" defaultChecked />}
                label="Data Quality Monitoring"
              />
              <div className="mb-4"Label
                control={<input type="checkbox" className="toggle" />}
                label="Maintenance Mode"
              />
              <div className="mb-4"Label
                control={<input type="checkbox" className="toggle" defaultChecked />}
                label="Alert Notifications"
              />
            </div>
          </div>
        </div>
      </div>

      <div className="grid" item xs={12} md={6}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              Quick Actions
            </div>
            <div  display="flex" flexDirection="column" gap={2}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="outlined"
                startIcon={<Refresh />}
                fullWidth
              >
                Refresh All Data Streams
              </button>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="outlined"
                startIcon={<Build />}
                fullWidth
              >
                Run System Diagnostics
              </button>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="outlined"
                startIcon={<CloudSync />}
                fullWidth
              >
                Sync with External Sources
              </button>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="outlined"
                startIcon={<AutoFixHigh />}
                color="warning"
                fullWidth
              >
                Auto-Repair Data Issues
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  const tabContent = [
    { label: 'Overview', component: <SystemOverview /> },
    { label: 'Data Streams', component: <DataStreams /> },
    { label: 'API Management', component: <ApiManagement /> },
    { label: 'System Controls', component: <SystemControls /> }
  ];

  return (
    <div  sx={{ p: 3 }}>
      <div  variant="h4" gutterBottom>
        <AdminPanelSettings sx={{ mr: 2, verticalAlign: 'middle' }} />
        Unified Data Management
      </div>
      <div  variant="subtitle1" color="text.secondary" gutterBottom>
        Centralized control panel for all data operations, monitoring, and management
      </div>

      <div  sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <div className="border-b border-gray-200" value={activeTab} onChange={handleTabChange}>
          {tabContent.map((tab, index) => (
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" key={index} label={tab.label} />
          ))}
        </div>
      </div>

      {tabContent[activeTab].component}

      <div className="fixed bottom-4 right-4 bg-gray-800 text-white p-4 rounded-md shadow-lg"
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar({ ...snackbar, open: false })}
      >
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200"
          onClose={() => setSnackbar({ ...snackbar, open: false })}
          severity={snackbar.severity}
        >
          {snackbar.message}
        </div>
      </div>
    </div>
  );
};

export default UnifiedDataManagement;