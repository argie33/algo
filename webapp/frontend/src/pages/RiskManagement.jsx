import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Tabs,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  CircularProgress,
  Alert,
  Button,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Slider,
  Switch,
  FormControlLabel,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  LinearProgress,
  Tooltip,
  IconButton
} from '@mui/material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  ScatterChart,
  Scatter
} from 'recharts';
import {
  Security,
  Warning,
  TrendingDown,
  TrendingUp,
  Shield,
  Assessment,
  Notifications,
  Settings,
  Analytics,
  ExpandMore,
  Add,
  Edit,
  Delete,
  NotificationsActive,
  Emergency,
  Speed
} from '@mui/icons-material';
import { getApiConfig } from '../services/api';
import { formatCurrency, formatPercentage, formatNumber } from '../utils/formatters';

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`risk-tabpanel-${index}`}
      aria-labelledby={`risk-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ py: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

const RiskManagement = () => {
  const { apiUrl: API_BASE } = getApiConfig();
  
  const [activeTab, setActiveTab] = useState(0);
  const [riskData, setRiskData] = useState({
    portfolioRisk: {},
    riskAlerts: [],
    riskLimits: {},
    stressTests: [],
    correlationMatrix: []
  });
  const [loading, setLoading] = useState(false);
  const [alertDialogOpen, setAlertDialogOpen] = useState(false);
  const [newAlert, setNewAlert] = useState({
    type: 'portfolio_loss',
    threshold: '',
    condition: 'greater_than',
    enabled: true
  });

  // Mock risk data for demonstration
  const mockRiskData = {
    portfolioRisk: {
      currentVaR: -2534.67, // Value at Risk (1-day, 95%)
      expectedShortfall: -3876.23,
      beta: 1.15,
      sharpeRatio: 0.87,
      sortino: 1.23,
      maxDrawdown: -12.34,
      volatility: 18.5,
      correlation: 0.92,
      riskLevel: 'Moderate High'
    },
    riskAlerts: [
      {
        id: 1,
        type: 'High Volatility',
        message: 'Portfolio volatility has exceeded 20%',
        severity: 'warning',
        timestamp: '2025-07-02T10:30:00Z',
        active: true
      },
      {
        id: 2,
        type: 'Concentration Risk',
        message: 'Technology sector allocation exceeds 70%',
        severity: 'error',
        timestamp: '2025-07-02T09:15:00Z',
        active: true
      },
      {
        id: 3,
        type: 'Beta Alert',
        message: 'Portfolio beta above 1.2',
        severity: 'info',
        timestamp: '2025-07-02T08:45:00Z',
        active: false
      }
    ],
    riskLimits: {
      maxPortfolioLoss: 10, // Percentage
      maxSectorConcentration: 40,
      maxSinglePosition: 15,
      maxBeta: 1.3,
      maxVolatility: 25,
      minCash: 5
    },
    stressTests: [
      {
        scenario: '2008 Financial Crisis',
        portfolioImpact: -34.5,
        timeframe: '12 months',
        probability: 'Low'
      },
      {
        scenario: 'Tech Crash (2000)',
        portfolioImpact: -28.7,
        timeframe: '18 months',
        probability: 'Medium'
      },
      {
        scenario: 'COVID-19 Pandemic',
        portfolioImpact: -22.1,
        timeframe: '3 months',
        probability: 'Low'
      },
      {
        scenario: 'Interest Rate Shock',
        portfolioImpact: -15.3,
        timeframe: '6 months',
        probability: 'Medium'
      }
    ],
    correlationMatrix: [
      { asset: 'AAPL', correlation: 1.0, risk: 'Low' },
      { asset: 'MSFT', correlation: 0.78, risk: 'Medium' },
      { asset: 'GOOGL', correlation: 0.82, risk: 'Medium' },
      { asset: 'SPY', correlation: 0.92, risk: 'High' }
    ]
  };

  useEffect(() => {
    loadRiskData();
  }, []);

  const loadRiskData = async () => {
    setLoading(true);
    try {
      // Try to fetch from API, fallback to mock data
      const response = await fetch(`${API_BASE}/api/risk/analysis`);
      if (response.ok) {
        const data = await response.json();
        setRiskData(data);
      } else {
        setRiskData(mockRiskData);
      }
    } catch (error) {
      console.error('Failed to load risk data:', error);
      setRiskData(mockRiskData);
    } finally {
      setLoading(false);
    }
  };

  const createAlert = async () => {
    if (!newAlert.threshold) return;

    const alert = {
      id: Date.now(),
      type: newAlert.type,
      threshold: parseFloat(newAlert.threshold),
      condition: newAlert.condition,
      enabled: newAlert.enabled,
      created: new Date().toISOString()
    };

    setRiskData(prev => ({
      ...prev,
      riskAlerts: [...prev.riskAlerts, {
        id: alert.id,
        type: alert.type,
        message: `${alert.type} alert set for ${alert.threshold}%`,
        severity: 'info',
        timestamp: alert.created,
        active: alert.enabled
      }]
    }));

    setAlertDialogOpen(false);
    setNewAlert({ type: 'portfolio_loss', threshold: '', condition: 'greater_than', enabled: true });
  };

  const dismissAlert = (alertId) => {
    setRiskData(prev => ({
      ...prev,
      riskAlerts: prev.riskAlerts.map(alert => 
        alert.id === alertId ? { ...alert, active: false } : alert
      )
    }));
  };

  const getRiskColor = (level) => {
    switch (level?.toLowerCase()) {
      case 'low': return 'success';
      case 'medium': return 'warning';
      case 'high': return 'error';
      default: return 'primary';
    }
  };

  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'error': return 'error';
      case 'warning': return 'warning';
      case 'info': return 'info';
      default: return 'primary';
    }
  };

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" gutterBottom sx={{ fontWeight: 700, display: 'flex', alignItems: 'center' }}>
          <Security sx={{ mr: 2, color: 'primary.main' }} />
          Risk Management
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Comprehensive portfolio risk analysis, monitoring, and stress testing tools.
        </Typography>
      </Box>

      {/* Risk Summary Cards */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" color="text.secondary" gutterBottom>
                Value at Risk (95%)
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, color: 'error.main' }}>
                {formatCurrency(riskData.portfolioRisk.currentVaR)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                1-day potential loss
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" color="text.secondary" gutterBottom>
                Portfolio Beta
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700 }}>
                {riskData.portfolioRisk.beta?.toFixed(2) || 'N/A'}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Market sensitivity
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" color="text.secondary" gutterBottom>
                Volatility
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, color: 'warning.main' }}>
                {formatPercentage(riskData.portfolioRisk.volatility)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Annualized
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" color="text.secondary" gutterBottom>
                Sharpe Ratio
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, color: 'success.main' }}>
                {riskData.portfolioRisk.sharpeRatio?.toFixed(2) || 'N/A'}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Risk-adjusted return
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Tabs value={activeTab} onChange={(e, v) => setActiveTab(v)} sx={{ mb: 3 }}>
        <Tab label="Risk Overview" icon={<Assessment />} />
        <Tab label="Alerts & Monitoring" icon={<NotificationsActive />} />
        <Tab label="Stress Testing" icon={<Emergency />} />
        <Tab label="Correlation Analysis" icon={<Analytics />} />
        <Tab label="Risk Limits" icon={<Settings />} />
      </Tabs>

      <TabPanel value={activeTab} index={0}>
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader title="Risk Profile Overview" />
              <CardContent>
                <Grid container spacing={3}>
                  <Grid item xs={12} sm={6}>
                    <Typography variant="body2" color="text.secondary" gutterBottom>
                      Risk Level
                    </Typography>
                    <Chip 
                      label={riskData.portfolioRisk.riskLevel || 'Moderate'} 
                      color={getRiskColor(riskData.portfolioRisk.riskLevel)}
                      size="large"
                    />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <Typography variant="body2" color="text.secondary" gutterBottom>
                      Max Drawdown
                    </Typography>
                    <Typography variant="h6" sx={{ color: 'error.main' }}>
                      {formatPercentage(riskData.portfolioRisk.maxDrawdown)}
                    </Typography>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <Typography variant="body2" color="text.secondary" gutterBottom>
                      Expected Shortfall
                    </Typography>
                    <Typography variant="h6" sx={{ color: 'error.main' }}>
                      {formatCurrency(riskData.portfolioRisk.expectedShortfall)}
                    </Typography>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <Typography variant="body2" color="text.secondary" gutterBottom>
                      Sortino Ratio
                    </Typography>
                    <Typography variant="h6" sx={{ color: 'success.main' }}>
                      {riskData.portfolioRisk.sortino?.toFixed(2) || 'N/A'}
                    </Typography>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} md={4}>
            <Card>
              <CardHeader title="Risk Gauge" />
              <CardContent>
                <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 200 }}>
                  <Box sx={{ position: 'relative', display: 'inline-flex' }}>
                    <CircularProgress
                      variant="determinate"
                      value={(riskData.portfolioRisk.volatility || 0) * 4} // Scale to 0-100
                      size={120}
                      thickness={4}
                      color={getRiskColor(riskData.portfolioRisk.riskLevel)}
                    />
                    <Box
                      sx={{
                        top: 0,
                        left: 0,
                        bottom: 0,
                        right: 0,
                        position: 'absolute',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexDirection: 'column'
                      }}
                    >
                      <Typography variant="h6" component="div" color="text.secondary">
                        Risk
                      </Typography>
                      <Typography variant="body2" component="div" color="text.secondary">
                        {riskData.portfolioRisk.riskLevel || 'Moderate'}
                      </Typography>
                    </Box>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={1}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
          <Typography variant="h6">Risk Alerts</Typography>
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={() => setAlertDialogOpen(true)}
          >
            Create Alert
          </Button>
        </Box>

        <Grid container spacing={2}>
          {riskData.riskAlerts.map((alert) => (
            <Grid item xs={12} key={alert.id}>
              <Alert 
                severity={getSeverityColor(alert.severity)}
                action={
                  alert.active && (
                    <IconButton
                      color="inherit"
                      size="small"
                      onClick={() => dismissAlert(alert.id)}
                    >
                      <Delete />
                    </IconButton>
                  )
                }
                sx={{ opacity: alert.active ? 1 : 0.6 }}
              >
                <Box>
                  <Typography variant="body2" fontWeight="bold">
                    {alert.type}
                  </Typography>
                  <Typography variant="body2">
                    {alert.message}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {new Date(alert.timestamp).toLocaleString()}
                  </Typography>
                </Box>
              </Alert>
            </Grid>
          ))}
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={2}>
        <Typography variant="h6" gutterBottom>
          Historical Stress Test Scenarios
        </Typography>
        
        <Grid container spacing={2}>
          {riskData.stressTests.map((test, index) => (
            <Grid item xs={12} sm={6} md={6} key={index}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    {test.scenario}
                  </Typography>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2" color="text.secondary">
                      Portfolio Impact:
                    </Typography>
                    <Typography variant="body2" sx={{ color: 'error.main', fontWeight: 'bold' }}>
                      {formatPercentage(test.portfolioImpact)}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2" color="text.secondary">
                      Timeframe:
                    </Typography>
                    <Typography variant="body2">
                      {test.timeframe}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2" color="text.secondary">
                      Probability:
                    </Typography>
                    <Chip 
                      label={test.probability} 
                      color={getRiskColor(test.probability)}
                      size="small"
                    />
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={3}>
        <Typography variant="h6" gutterBottom>
          Asset Correlation Matrix
        </Typography>
        
        <Card>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Asset</TableCell>
                  <TableCell align="center">Correlation</TableCell>
                  <TableCell align="center">Risk Level</TableCell>
                  <TableCell align="center">Correlation Bar</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {riskData.correlationMatrix.map((item) => (
                  <TableRow key={item.asset} hover>
                    <TableCell>
                      <Typography variant="body2" fontWeight="bold">
                        {item.asset}
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      {item.correlation.toFixed(2)}
                    </TableCell>
                    <TableCell align="center">
                      <Chip 
                        label={item.risk} 
                        color={getRiskColor(item.risk)}
                        size="small"
                      />
                    </TableCell>
                    <TableCell align="center">
                      <LinearProgress 
                        variant="determinate" 
                        value={Math.abs(item.correlation) * 100} 
                        sx={{ width: 100 }}
                        color={item.correlation > 0.8 ? 'error' : item.correlation > 0.5 ? 'warning' : 'success'}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Card>
      </TabPanel>

      <TabPanel value={activeTab} index={4}>
        <Typography variant="h6" gutterBottom>
          Risk Limit Configuration
        </Typography>
        
        <Grid container spacing={3}>
          {Object.entries(riskData.riskLimits).map(([key, value]) => (
            <Grid item xs={12} sm={6} md={4} key={key}>
              <Card>
                <CardContent>
                  <Typography variant="body2" color="text.secondary" gutterBottom sx={{ textTransform: 'capitalize' }}>
                    {key.replace(/([A-Z])/g, ' $1').trim()}
                  </Typography>
                  <Typography variant="h6" sx={{ mb: 2 }}>
                    {typeof value === 'number' ? (key.includes('max') || key.includes('min') ? `${value}%` : value.toFixed(2)) : value}
                  </Typography>
                  <Slider
                    value={value}
                    onChange={(e, newValue) => {
                      setRiskData(prev => ({
                        ...prev,
                        riskLimits: { ...prev.riskLimits, [key]: newValue }
                      }));
                    }}
                    min={0}
                    max={key.includes('Beta') ? 2 : 100}
                    step={key.includes('Beta') ? 0.1 : 1}
                    valueLabelDisplay="auto"
                    size="small"
                  />
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </TabPanel>

      {/* Create Alert Dialog */}
      <Dialog open={alertDialogOpen} onClose={() => setAlertDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Create Risk Alert</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>Alert Type</InputLabel>
                <Select
                  value={newAlert.type}
                  onChange={(e) => setNewAlert(prev => ({ ...prev, type: e.target.value }))}
                >
                  <MenuItem value="portfolio_loss">Portfolio Loss</MenuItem>
                  <MenuItem value="volatility">High Volatility</MenuItem>
                  <MenuItem value="beta">Beta Alert</MenuItem>
                  <MenuItem value="sector_concentration">Sector Concentration</MenuItem>
                  <MenuItem value="position_size">Position Size</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>Condition</InputLabel>
                <Select
                  value={newAlert.condition}
                  onChange={(e) => setNewAlert(prev => ({ ...prev, condition: e.target.value }))}
                >
                  <MenuItem value="greater_than">Greater Than</MenuItem>
                  <MenuItem value="less_than">Less Than</MenuItem>
                  <MenuItem value="equals">Equals</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                label="Threshold (%)"
                type="number"
                fullWidth
                value={newAlert.threshold}
                onChange={(e) => setNewAlert(prev => ({ ...prev, threshold: e.target.value }))}
                placeholder="10"
              />
            </Grid>
            <Grid item xs={12}>
              <FormControlLabel
                control={
                  <Switch
                    checked={newAlert.enabled}
                    onChange={(e) => setNewAlert(prev => ({ ...prev, enabled: e.target.checked }))}
                  />
                }
                label="Enable Alert"
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAlertDialogOpen(false)}>Cancel</Button>
          <Button onClick={createAlert} variant="contained">Create Alert</Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default RiskManagement;