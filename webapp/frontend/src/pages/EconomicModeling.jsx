import React, { useState, useEffect, useMemo } from 'react';
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
  LinearProgress,
  Alert,
  Button,
  TextField,
  MenuItem,
  IconButton,
  FormControl,
  InputLabel,
  Select,
  Tooltip,
  Badge,
  Divider,
  List,
  ListItem,
  ListItemText,
  ListItemAvatar,
  Avatar,
  Rating,
  Stepper,
  Step,
  StepLabel,
  StepContent,
  CircularProgress,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Switch,
  FormControlLabel,
  Slider,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Analytics,
  Assessment,
  ShowChart,
  Timeline,
  Warning,
  CheckCircle,
  Info,
  Error,
  Speed,
  AccountBalance,
  Business,
  Work,
  Psychology,
  PieChart as PieChartIcon,
  BarChart as BarChartIcon,
  Refresh,
  Download,
  Settings,
  Lightbulb,
  Security,
  MonetizationOn,
  TrendingFlat,
  ExpandMore,
  Notifications,
  Schedule,
  FlashOn,
  Flag,
  LocalAtm,
  Home,
  Factory,
  Store,
  AttachMoney,
  Construction
} from '@mui/icons-material';
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  Area,
  AreaChart,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ComposedChart,
  ScatterChart,
  Scatter,
  Treemap,
  ReferenceLine
} from 'recharts';

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`economic-tabpanel-${index}`}
      aria-labelledby={`economic-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ p: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

const EconomicModeling = () => {
  const [tabValue, setTabValue] = useState(0);
  const [selectedTimeframe, setSelectedTimeframe] = useState('6M');
  const [selectedModel, setSelectedModel] = useState('composite');
  const [selectedScenario, setSelectedScenario] = useState('base');
  const [loading, setLoading] = useState(false);
  const [liveUpdates, setLiveUpdates] = useState(false);
  const [economicData, setEconomicData] = useState(mockEconomicData);
  const [alertsEnabled, setAlertsEnabled] = useState(true);
  const [confidenceThreshold, setConfidenceThreshold] = useState(70);

  // Calculate composite recession probability
  const compositeRecessionProbability = useMemo(() => {
    if (!economicData.forecastModels) return 0;
    
    const weights = {
      'NY Fed Model': 0.35,
      'Goldman Sachs': 0.25,
      'JP Morgan': 0.25,
      'AI Ensemble': 0.15
    };
    
    const weightedSum = economicData.forecastModels.reduce((sum, model) => {
      return sum + (model.probability * (weights[model.name] || 0));
    }, 0);
    
    return Math.round(weightedSum);
  }, [economicData.forecastModels]);

  // Calculate economic stress index
  const economicStressIndex = useMemo(() => {
    if (!economicData.leadingIndicators) return 0;
    
    const negativeSignals = economicData.leadingIndicators.filter(
      indicator => indicator.signal === 'Negative'
    ).length;
    
    const totalSignals = economicData.leadingIndicators.length;
    const stressScore = (negativeSignals / totalSignals) * 100;
    
    return Math.round(stressScore);
  }, [economicData.leadingIndicators]);

  // Calculate yield curve signal strength
  const yieldCurveSignal = useMemo(() => {
    if (!economicData.yieldCurve) return 'Neutral';
    
    const { spread2y10y, spread3m10y } = economicData.yieldCurve;
    
    if (spread2y10y < -50 && spread3m10y < -50) return 'Strong Recession Signal';
    if (spread2y10y < 0 && spread3m10y < 0) return 'Recession Signal';
    if (spread2y10y < 50 && spread3m10y < 50) return 'Flattening';
    return 'Normal';
  }, [economicData.yieldCurve]);

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  const getRiskColor = (level) => {
    switch (level?.toLowerCase()) {
      case 'low':
        return 'success';
      case 'medium':
        return 'warning';
      case 'high':
        return 'error';
      default:
        return 'default';
    }
  };

  const getRecessionProbabilityColor = (probability) => {
    if (probability < 20) return 'success';
    if (probability < 40) return 'warning';
    return 'error';
  };

  const getIndicatorIcon = (trend) => {
    switch (trend) {
      case 'improving':
        return <TrendingUp color="success" />;
      case 'deteriorating':
        return <TrendingDown color="error" />;
      default:
        return <TrendingFlat color="action" />;
    }
  };

  const getSectorIcon = (sector) => {
    switch (sector.toLowerCase()) {
      case 'manufacturing':
        return <Factory color="primary" />;
      case 'services':
        return <Business color="secondary" />;
      case 'construction':
        return <Construction color="warning" />;
      case 'retail':
        return <Store color="info" />;
      default:
        return <Business color="action" />;
    }
  };

  const formatTimeHorizon = (months) => {
    if (months < 12) return `${months} months`;
    return `${Math.round(months / 12)} years`;
  };

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box display="flex" alignItems="center" justifyContent="between" mb={4}>
        <Box>
          <Typography variant="h3" component="h1" gutterBottom>
            Economic Modeling & Forecasting
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Advanced econometric models and real-time recession probability analysis
          </Typography>
        </Box>
        
        <Box display="flex" alignItems="center" gap={2}>
          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel>Timeframe</InputLabel>
            <Select
              value={selectedTimeframe}
              onChange={(e) => setSelectedTimeframe(e.target.value)}
              label="Timeframe"
            >
              <MenuItem value="3M">3 Months</MenuItem>
              <MenuItem value="6M">6 Months</MenuItem>
              <MenuItem value="1Y">1 Year</MenuItem>
              <MenuItem value="2Y">2 Years</MenuItem>
              <MenuItem value="5Y">5 Years</MenuItem>
            </Select>
          </FormControl>
          
          <FormControlLabel
            control={
              <Switch
                checked={liveUpdates}
                onChange={(e) => setLiveUpdates(e.target.checked)}
                color="primary"
              />
            }
            label="Live Updates"
          />
          
          <IconButton onClick={() => setLoading(true)}>
            <Refresh />
          </IconButton>
        </Box>
      </Box>

      {/* Critical Alerts */}
      {alertsEnabled && compositeRecessionProbability > 40 && (
        <Alert 
          severity="warning" 
          sx={{ mb: 3 }}
          action={
            <Button color="inherit" size="small">
              View Details
            </Button>
          }
        >
          <strong>Elevated Recession Risk:</strong> Composite model indicates {compositeRecessionProbability}% 
          probability of recession within {selectedTimeframe}. Monitor key indicators closely.
        </Alert>
      )}

      {economicData.yieldCurve?.isInverted && (
        <Alert 
          severity="error" 
          sx={{ mb: 3 }}
          action={
            <Button color="inherit" size="small">
              Learn More
            </Button>
          }
        >
          <strong>Yield Curve Inverted:</strong> {yieldCurveSignal} detected. 
          Historical accuracy: {economicData.yieldCurve.historicalAccuracy}% in predicting recessions.
        </Alert>
      )}

      {/* Key Economic Indicators */}
      <Grid container spacing={3} mb={4}>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="between">
                <Box>
                  <Typography variant="h6" color="text.secondary">
                    Recession Probability
                  </Typography>
                  <Typography variant="h4" color={getRecessionProbabilityColor(compositeRecessionProbability) + '.main'}>
                    {compositeRecessionProbability}%
                  </Typography>
                  <Typography variant="body2">
                    Composite model ({selectedTimeframe})
                  </Typography>
                </Box>
                <Assessment color={getRiskColor(economicData.riskLevel)} fontSize="large" />
              </Box>
              <LinearProgress 
                variant="determinate" 
                value={compositeRecessionProbability} 
                color={getRecessionProbabilityColor(compositeRecessionProbability)}
                sx={{ mt: 2 }}
              />
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="between">
                <Box>
                  <Typography variant="h6" color="text.secondary">
                    Economic Stress
                  </Typography>
                  <Typography variant="h4" color="primary">
                    {economicStressIndex}
                  </Typography>
                  <Typography variant="body2">
                    Stress Index (0-100)
                  </Typography>
                </Box>
                <Speed color="primary" fontSize="large" />
              </Box>
              <LinearProgress 
                variant="determinate" 
                value={economicStressIndex} 
                color={economicStressIndex > 60 ? 'error' : economicStressIndex > 30 ? 'warning' : 'success'}
                sx={{ mt: 2 }}
              />
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="between">
                <Box>
                  <Typography variant="h6" color="text.secondary">
                    GDP Growth
                  </Typography>
                  <Typography variant="h4" color="secondary">
                    {economicData.gdpGrowth}%
                  </Typography>
                  <Typography variant="body2">
                    Annualized Q/Q
                  </Typography>
                </Box>
                <ShowChart color="secondary" fontSize="large" />
              </Box>
              <Box display="flex" alignItems="center" mt={1}>
                {economicData.gdpGrowth > 0 ? (
                  <TrendingUp color="success" fontSize="small" />
                ) : (
                  <TrendingDown color="error" fontSize="small" />
                )}
                <Typography variant="body2" color="text.secondary" ml={1}>
                  vs previous quarter
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="between">
                <Box>
                  <Typography variant="h6" color="text.secondary">
                    Unemployment
                  </Typography>
                  <Typography variant="h4" color="info.main">
                    {economicData.unemployment}%
                  </Typography>
                  <Typography variant="body2">
                    Current rate
                  </Typography>
                </Box>
                <Work color="info" fontSize="large" />
              </Box>
              <Box display="flex" alignItems="center" mt={1}>
                <Typography variant="body2" color="text.secondary">
                  Sahm Rule: {economicData.employment?.sahmRule?.value || 'N/A'}
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Main Content Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={tabValue} onChange={handleTabChange} aria-label="economic modeling tabs">
          <Tab label="Leading Indicators" icon={<Analytics />} />
          <Tab label="Yield Curve" icon={<ShowChart />} />
          <Tab label="Forecast Models" icon={<Assessment />} />
          <Tab label="Sectoral Analysis" icon={<BarChartIcon />} />
          <Tab label="Scenario Planning" icon={<Flag />} />
          <Tab label="AI Insights" icon={<Psychology />} />
        </Tabs>
      </Box>

      <TabPanel value={tabValue} index={0}>
        {/* Leading Indicators */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader
                title="Leading Economic Indicators"
                subheader="Real-time economic momentum analysis"
                action={
                  <Chip 
                    label={`${economicData.leadingIndicators?.length || 0} indicators`} 
                    color="primary" 
                    variant="outlined" 
                  />
                }
              />
              <CardContent>
                <Grid container spacing={3}>
                  {economicData.leadingIndicators?.map((indicator, index) => (
                    <Grid item xs={12} md={6} key={index}>
                      <Card variant="outlined">
                        <CardContent>
                          <Box display="flex" alignItems="center" justifyContent="between" mb={2}>
                            <Box display="flex" alignItems="center" gap={1}>
                              {getIndicatorIcon(indicator.trend)}
                              <Typography variant="h6">
                                {indicator.name}
                              </Typography>
                            </Box>
                            <Chip 
                              label={indicator.signal} 
                              color={indicator.signal === 'Positive' ? 'success' : indicator.signal === 'Negative' ? 'error' : 'default'}
                              size="small"
                            />
                          </Box>
                          
                          <Box display="flex" alignItems="center" justifyContent="between" mb={2}>
                            <Typography variant="h4" color="primary">
                              {indicator.value}
                            </Typography>
                            <Typography 
                              variant="body2" 
                              color={indicator.change > 0 ? 'success.main' : 'error.main'}
                            >
                              {indicator.change > 0 ? '+' : ''}{indicator.change}%
                            </Typography>
                          </Box>
                          
                          <Typography variant="body2" color="text.secondary" mb={2}>
                            {indicator.description}
                          </Typography>
                          
                          <Box>
                            <Box display="flex" alignItems="center" justifyContent="between" mb={1}>
                              <Typography variant="body2" color="text.secondary">
                                Signal Strength
                              </Typography>
                              <Typography variant="body2" fontWeight="bold">
                                {indicator.strength}%
                              </Typography>
                            </Box>
                            <LinearProgress 
                              variant="determinate" 
                              value={indicator.strength} 
                              color={indicator.strength > 70 ? 'success' : indicator.strength > 40 ? 'warning' : 'error'}
                            />
                          </Box>
                        </CardContent>
                      </Card>
                    </Grid>
                  ))}
                </Grid>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Grid container spacing={3}>
              {/* Signal Summary */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Signal Summary" />
                  <CardContent>
                    <Box display="flex" alignItems="center" justifyContent="center" mb={3}>
                      <Box textAlign="center">
                        <Typography variant="h3" color="primary">
                          {economicStressIndex}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Stress Index
                        </Typography>
                      </Box>
                    </Box>
                    
                    <Box mb={3}>
                      <Typography variant="body2" color="text.secondary" mb={1}>
                        Risk Level
                      </Typography>
                      <Chip 
                        label={economicData.riskLevel} 
                        color={getRiskColor(economicData.riskLevel)}
                        size="large"
                      />
                    </Box>
                    
                    <Divider sx={{ mb: 2 }} />
                    
                    <Box display="flex" justifyContent="between" mb={1}>
                      <Typography variant="body2">Positive Signals</Typography>
                      <Typography variant="body2" fontWeight="bold">
                        {economicData.leadingIndicators?.filter(i => i.signal === 'Positive').length || 0}
                      </Typography>
                    </Box>
                    <Box display="flex" justifyContent="between" mb={1}>
                      <Typography variant="body2">Negative Signals</Typography>
                      <Typography variant="body2" fontWeight="bold">
                        {economicData.leadingIndicators?.filter(i => i.signal === 'Negative').length || 0}
                      </Typography>
                    </Box>
                    <Box display="flex" justifyContent="between">
                      <Typography variant="body2">Neutral Signals</Typography>
                      <Typography variant="body2" fontWeight="bold">
                        {economicData.leadingIndicators?.filter(i => i.signal === 'Neutral').length || 0}
                      </Typography>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>

              {/* Upcoming Economic Events */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader 
                    title="Upcoming Events" 
                    subheader="Next 30 days"
                  />
                  <CardContent>
                    <List>
                      {economicData.upcomingEvents?.map((event, index) => (
                        <ListItem key={index} alignItems="flex-start">
                          <ListItemAvatar>
                            <Avatar sx={{ bgcolor: getRiskColor(event.importance) + '.main' }}>
                              <Schedule />
                            </Avatar>
                          </ListItemAvatar>
                          <ListItemText
                            primary={event.event}
                            secondary={
                              <Box>
                                <Typography variant="body2" color="text.secondary">
                                  {event.date} • {event.time}
                                </Typography>
                                <Typography variant="body2" color="text.primary">
                                  {event.forecast}
                                </Typography>
                              </Box>
                            }
                          />
                        </ListItem>
                      ))}
                    </List>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={tabValue} index={1}>
        {/* Yield Curve */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader
                title="Yield Curve Analysis"
                subheader="Treasury yield curve and inversion analysis"
              />
              <CardContent>
                <ResponsiveContainer width="100%" height={400}>
                  <LineChart data={economicData.yieldCurveData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="maturity" />
                    <YAxis />
                    <RechartsTooltip formatter={(value) => [`${value}%`, 'Yield']} />
                    <Line 
                      type="monotone" 
                      dataKey="yield" 
                      stroke="#1976d2" 
                      strokeWidth={3}
                      dot={{ fill: '#1976d2', strokeWidth: 2, r: 6 }}
                    />
                    <ReferenceLine y={0} stroke="red" strokeDasharray="2 2" />
                  </LineChart>
                </ResponsiveContainer>
                
                <Box mt={3}>
                  <Grid container spacing={2}>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="text.secondary">
                        2Y-10Y Spread
                      </Typography>
                      <Typography 
                        variant="h6" 
                        color={economicData.yieldCurve?.spread2y10y < 0 ? 'error.main' : 'success.main'}
                      >
                        {economicData.yieldCurve?.spread2y10y} bps
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="text.secondary">
                        3M-10Y Spread
                      </Typography>
                      <Typography 
                        variant="h6" 
                        color={economicData.yieldCurve?.spread3m10y < 0 ? 'error.main' : 'success.main'}
                      >
                        {economicData.yieldCurve?.spread3m10y} bps
                      </Typography>
                    </Grid>
                  </Grid>
                </Box>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Card>
              <CardHeader title="Inversion Analysis" />
              <CardContent>
                <Alert 
                  severity={economicData.yieldCurve?.isInverted ? 'error' : 'success'}
                  sx={{ mb: 3 }}
                >
                  <Typography variant="h6">
                    {economicData.yieldCurve?.isInverted ? 'Yield Curve Inverted' : 'Normal Yield Curve'}
                  </Typography>
                  <Typography variant="body2">
                    {economicData.yieldCurve?.interpretation}
                  </Typography>
                </Alert>
                
                <Box mb={3}>
                  <Typography variant="body2" color="text.secondary" mb={1}>
                    Signal Strength
                  </Typography>
                  <Chip 
                    label={yieldCurveSignal} 
                    color={yieldCurveSignal.includes('Strong') ? 'error' : yieldCurveSignal.includes('Recession') ? 'warning' : 'success'}
                    size="large"
                  />
                </Box>
                
                <Divider sx={{ mb: 2 }} />
                
                <Typography variant="h6" mb={2}>Historical Context</Typography>
                <Box display="flex" justifyContent="between" mb={1}>
                  <Typography variant="body2">Historical Accuracy</Typography>
                  <Typography variant="body2" fontWeight="bold">
                    {economicData.yieldCurve?.historicalAccuracy}%
                  </Typography>
                </Box>
                <Box display="flex" justifyContent="between" mb={1}>
                  <Typography variant="body2">Average Lead Time</Typography>
                  <Typography variant="body2" fontWeight="bold">
                    {economicData.yieldCurve?.averageLeadTime} months
                  </Typography>
                </Box>
                
                <Box mt={3}>
                  <Typography variant="body2" color="text.secondary">
                    The yield curve has inverted before {economicData.yieldCurve?.historicalAccuracy}% of recessions 
                    since 1970, with an average lead time of {economicData.yieldCurve?.averageLeadTime} months.
                  </Typography>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={tabValue} index={2}>
        {/* Forecast Models */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader
                title="Recession Probability Models"
                subheader="Institutional forecasting models and ensemble predictions"
              />
              <CardContent>
                <Grid container spacing={3}>
                  {economicData.forecastModels?.map((model, index) => (
                    <Grid item xs={12} md={6} key={index}>
                      <Card variant="outlined">
                        <CardContent>
                          <Box display="flex" alignItems="center" justifyContent="between" mb={2}>
                            <Typography variant="h6">
                              {model.name}
                            </Typography>
                            <Chip 
                              label={`${model.confidence}% confidence`} 
                              color={model.confidence > 80 ? 'success' : model.confidence > 60 ? 'warning' : 'error'}
                              size="small"
                            />
                          </Box>
                          
                          <Box textAlign="center" mb={3}>
                            <Typography variant="h3" color="primary">
                              {model.probability}%
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              Recession Probability
                            </Typography>
                          </Box>
                          
                          <LinearProgress 
                            variant="determinate" 
                            value={model.probability} 
                            color={getRecessionProbabilityColor(model.probability)}
                            sx={{ mb: 2 }}
                          />
                          
                          <Box display="flex" justifyContent="between" mb={1}>
                            <Typography variant="body2" color="text.secondary">
                              Time Horizon
                            </Typography>
                            <Typography variant="body2" fontWeight="bold">
                              {model.timeHorizon}
                            </Typography>
                          </Box>
                          
                          <Typography variant="body2" color="text.secondary">
                            {model.methodology}
                          </Typography>
                        </CardContent>
                      </Card>
                    </Grid>
                  ))}
                </Grid>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Card>
              <CardHeader title="Ensemble Prediction" />
              <CardContent>
                <Box textAlign="center" mb={3}>
                  <Typography variant="h2" color="primary">
                    {compositeRecessionProbability}%
                  </Typography>
                  <Typography variant="body1" color="text.secondary">
                    Composite Probability
                  </Typography>
                </Box>
                
                <LinearProgress 
                  variant="determinate" 
                  value={compositeRecessionProbability} 
                  color={getRecessionProbabilityColor(compositeRecessionProbability)}
                  sx={{ mb: 3, height: 8 }}
                />
                
                <Alert 
                  severity={compositeRecessionProbability > 50 ? 'error' : compositeRecessionProbability > 30 ? 'warning' : 'info'}
                  sx={{ mb: 3 }}
                >
                  <Typography variant="body2">
                    {compositeRecessionProbability > 50 
                      ? 'High probability of recession. Consider defensive positioning.'
                      : compositeRecessionProbability > 30 
                      ? 'Elevated recession risk. Monitor indicators closely.'
                      : 'Low recession probability. Economic conditions appear stable.'}
                  </Typography>
                </Alert>
                
                <Typography variant="h6" mb={2}>Model Weights</Typography>
                <Box>
                  <Box display="flex" justifyContent="between" mb={1}>
                    <Typography variant="body2">NY Fed Model</Typography>
                    <Typography variant="body2" fontWeight="bold">35%</Typography>
                  </Box>
                  <Box display="flex" justifyContent="between" mb={1}>
                    <Typography variant="body2">Goldman Sachs</Typography>
                    <Typography variant="body2" fontWeight="bold">25%</Typography>
                  </Box>
                  <Box display="flex" justifyContent="between" mb={1}>
                    <Typography variant="body2">JP Morgan</Typography>
                    <Typography variant="body2" fontWeight="bold">25%</Typography>
                  </Box>
                  <Box display="flex" justifyContent="between">
                    <Typography variant="body2">AI Ensemble</Typography>
                    <Typography variant="body2" fontWeight="bold">15%</Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={tabValue} index={3}>
        {/* Sectoral Analysis */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader title="Sectoral Economic Performance" />
              <CardContent>
                <ResponsiveContainer width="100%" height={400}>
                  <BarChart data={economicData.sectoralData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="sector" />
                    <YAxis />
                    <RechartsTooltip formatter={(value) => [`${value}%`, 'Growth']} />
                    <Bar dataKey="growth">
                      {economicData.sectoralData?.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.growth >= 0 ? '#4caf50' : '#f44336'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Card>
              <CardHeader title="Sector Leaders" />
              <CardContent>
                <List>
                  {economicData.sectoralData?.sort((a, b) => b.growth - a.growth).map((sector, index) => (
                    <ListItem key={index}>
                      <ListItemAvatar>
                        <Avatar>
                          {getSectorIcon(sector.sector)}
                        </Avatar>
                      </ListItemAvatar>
                      <ListItemText
                        primary={sector.sector}
                        secondary={
                          <Box display="flex" alignItems="center" gap={1}>
                            <Typography variant="body2" color="text.secondary">
                              {sector.description}
                            </Typography>
                            <Chip 
                              label={`${sector.growth >= 0 ? '+' : ''}${sector.growth}%`}
                              color={sector.growth >= 0 ? 'success' : 'error'}
                              size="small"
                            />
                          </Box>
                        }
                      />
                    </ListItem>
                  ))}
                </List>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={tabValue} index={4}>
        {/* Scenario Planning */}
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Card>
              <CardHeader title="Economic Scenario Analysis" />
              <CardContent>
                <Grid container spacing={3}>
                  {economicData.scenarios?.map((scenario, index) => (
                    <Grid item xs={12} md={4} key={index}>
                      <Card 
                        variant="outlined" 
                        sx={{ 
                          border: selectedScenario === scenario.name.toLowerCase().replace(' ', '') ? 2 : 1,
                          borderColor: selectedScenario === scenario.name.toLowerCase().replace(' ', '') ? 'primary.main' : 'divider'
                        }}
                      >
                        <CardContent>
                          <Box display="flex" alignItems="center" justifyContent="between" mb={2}>
                            <Typography variant="h6">
                              {scenario.name}
                            </Typography>
                            <Chip 
                              label={`${scenario.probability}% probability`} 
                              color={scenario.name === 'Base Case' ? 'primary' : scenario.name === 'Bull Case' ? 'success' : 'error'}
                              size="small"
                            />
                          </Box>
                          
                          <Box mb={3}>
                            <Typography variant="body2" color="text.secondary">
                              {scenario.description}
                            </Typography>
                          </Box>
                          
                          <Box display="flex" justifyContent="between" mb={1}>
                            <Typography variant="body2" color="text.secondary">
                              GDP Growth
                            </Typography>
                            <Typography variant="body2" fontWeight="bold">
                              {scenario.gdpGrowth}%
                            </Typography>
                          </Box>
                          
                          <Box display="flex" justifyContent="between" mb={1}>
                            <Typography variant="body2" color="text.secondary">
                              Unemployment
                            </Typography>
                            <Typography variant="body2" fontWeight="bold">
                              {scenario.unemployment}%
                            </Typography>
                          </Box>
                          
                          <Box display="flex" justifyContent="between" mb={2}>
                            <Typography variant="body2" color="text.secondary">
                              Fed Funds Rate
                            </Typography>
                            <Typography variant="body2" fontWeight="bold">
                              {scenario.fedRate}%
                            </Typography>
                          </Box>
                          
                          <Button 
                            variant={selectedScenario === scenario.name.toLowerCase().replace(' ', '') ? 'contained' : 'outlined'}
                            fullWidth
                            onClick={() => setSelectedScenario(scenario.name.toLowerCase().replace(' ', ''))}
                          >
                            Analyze Scenario
                          </Button>
                        </CardContent>
                      </Card>
                    </Grid>
                  ))}
                </Grid>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={tabValue} index={5}>
        {/* AI Insights */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader 
                title="AI-Powered Economic Insights"
                subheader="Machine learning analysis of economic patterns and trends"
              />
              <CardContent>
                <Grid container spacing={3}>
                  {economicData.aiInsights?.map((insight, index) => (
                    <Grid item xs={12} key={index}>
                      <Card variant="outlined">
                        <CardContent>
                          <Box display="flex" alignItems="center" gap={2} mb={2}>
                            <Lightbulb color="primary" />
                            <Typography variant="h6">
                              {insight.title}
                            </Typography>
                            <Chip 
                              label={`${insight.confidence}% confidence`} 
                              color={insight.confidence > 80 ? 'success' : insight.confidence > 60 ? 'warning' : 'error'}
                              size="small"
                            />
                          </Box>
                          
                          <Typography variant="body1" mb={2}>
                            {insight.description}
                          </Typography>
                          
                          <Box display="flex" alignItems="center" gap={2}>
                            <Typography variant="body2" color="text.secondary">
                              Impact: {insight.impact}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              Timeframe: {insight.timeframe}
                            </Typography>
                          </Box>
                        </CardContent>
                      </Card>
                    </Grid>
                  ))}
                </Grid>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Card>
              <CardHeader title="AI Model Performance" />
              <CardContent>
                <Box textAlign="center" mb={3}>
                  <Typography variant="h3" color="primary">
                    87%
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Prediction Accuracy
                  </Typography>
                </Box>
                
                <LinearProgress 
                  variant="determinate" 
                  value={87} 
                  color="success"
                  sx={{ mb: 3, height: 8 }}
                />
                
                <Box display="flex" justifyContent="between" mb={1}>
                  <Typography variant="body2" color="text.secondary">
                    Data Points Analyzed
                  </Typography>
                  <Typography variant="body2" fontWeight="bold">
                    15,000+
                  </Typography>
                </Box>
                
                <Box display="flex" justifyContent="between" mb={1}>
                  <Typography variant="body2" color="text.secondary">
                    Last Model Update
                  </Typography>
                  <Typography variant="body2" fontWeight="bold">
                    2 hours ago
                  </Typography>
                </Box>
                
                <Box display="flex" justifyContent="between" mb={3}>
                  <Typography variant="body2" color="text.secondary">
                    Next Update
                  </Typography>
                  <Typography variant="body2" fontWeight="bold">
                    In 4 hours
                  </Typography>
                </Box>
                
                <Alert severity="info">
                  <Typography variant="body2">
                    AI models are continuously learning from new economic data to improve prediction accuracy.
                  </Typography>
                </Alert>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>
    </Container>
  );
};

// Enhanced mock data for development
const mockEconomicData = {
  recessionProbability: 35,
  riskLevel: 'Medium',
  gdpGrowth: 2.1,
  unemployment: 3.7,
  inflation: 3.2,
  leadingIndicators: [
    {
      name: 'Leading Economic Index',
      value: '102.5',
      change: -0.3,
      trend: 'deteriorating',
      signal: 'Negative',
      strength: 25,
      description: 'Composite index of 10 leading indicators showing economic momentum'
    },
    {
      name: 'ISM Manufacturing PMI',
      value: '48.7',
      change: -1.2,
      trend: 'deteriorating',
      signal: 'Negative',
      strength: 35,
      description: 'Manufacturing activity index; values below 50 indicate contraction'
    },
    {
      name: 'Consumer Confidence',
      value: '115.8',
      change: 2.1,
      trend: 'improving',
      signal: 'Positive',
      strength: 75,
      description: 'Consumer assessment of current and future economic conditions'
    },
    {
      name: 'Building Permits',
      value: '1.52M',
      change: -5.2,
      trend: 'deteriorating',
      signal: 'Negative',
      strength: 40,
      description: 'Forward-looking indicator of housing construction activity'
    },
    {
      name: 'Initial Jobless Claims',
      value: '220K',
      change: -2.8,
      trend: 'improving',
      signal: 'Positive',
      strength: 65,
      description: 'Weekly measure of unemployment insurance claims'
    },
    {
      name: 'Consumer Spending',
      value: '0.8%',
      change: 0.3,
      trend: 'improving',
      signal: 'Positive',
      strength: 70,
      description: 'Month-over-month change in personal consumption expenditures'
    }
  ],
  upcomingEvents: [
    {
      event: 'Federal Reserve Meeting',
      date: 'Mar 20, 2024',
      time: '2:00 PM EST',
      importance: 'High',
      forecast: '0.25% rate cut expected'
    },
    {
      event: 'Consumer Price Index',
      date: 'Mar 12, 2024',
      time: '8:30 AM EST',
      importance: 'High',
      forecast: '3.1% Y/Y expected'
    },
    {
      event: 'Employment Report',
      date: 'Mar 8, 2024',
      time: '8:30 AM EST',
      importance: 'High',
      forecast: '200K jobs added expected'
    },
    {
      event: 'GDP Advance Estimate',
      date: 'Mar 28, 2024',
      time: '8:30 AM EST',
      importance: 'High',
      forecast: '2.0% annualized growth'
    }
  ],
  yieldCurve: {
    spread2y10y: -45,
    spread3m10y: -62,
    isInverted: true,
    interpretation: 'The inverted yield curve suggests investor expectations of economic slowdown and potential Federal Reserve rate cuts.',
    historicalAccuracy: 85,
    averageLeadTime: 14
  },
  yieldCurveData: [
    { maturity: '3M', yield: 5.2 },
    { maturity: '6M', yield: 4.9 },
    { maturity: '1Y', yield: 4.6 },
    { maturity: '2Y', yield: 4.3 },
    { maturity: '5Y', yield: 4.5 },
    { maturity: '10Y', yield: 4.7 },
    { maturity: '30Y', yield: 4.9 }
  ],
  forecastModels: [
    {
      name: 'NY Fed Model',
      probability: 32,
      confidence: 78,
      timeHorizon: '12 months',
      methodology: 'Yield curve and term structure model'
    },
    {
      name: 'Goldman Sachs',
      probability: 35,
      confidence: 71,
      timeHorizon: '12 months',
      methodology: 'Multi-factor econometric model'
    },
    {
      name: 'JP Morgan',
      probability: 40,
      confidence: 68,
      timeHorizon: '18 months',
      methodology: 'Credit conditions and leading indicators'
    },
    {
      name: 'AI Ensemble',
      probability: 38,
      confidence: 82,
      timeHorizon: '12 months',
      methodology: 'Machine learning ensemble of 50+ models'
    }
  ],
  sectoralData: [
    { sector: 'Manufacturing', growth: -1.2, description: 'Industrial production declining' },
    { sector: 'Services', growth: 2.1, description: 'Strong service sector growth' },
    { sector: 'Construction', growth: -0.8, description: 'Housing market cooling' },
    { sector: 'Retail', growth: 1.5, description: 'Consumer spending holding up' },
    { sector: 'Technology', growth: 3.2, description: 'AI and software driving growth' },
    { sector: 'Healthcare', growth: 1.8, description: 'Steady demographic-driven growth' }
  ],
  scenarios: [
    {
      name: 'Bull Case',
      probability: 25,
      gdpGrowth: 3.2,
      unemployment: 3.4,
      fedRate: 4.5,
      description: 'Soft landing with continued growth and declining inflation'
    },
    {
      name: 'Base Case',
      probability: 50,
      gdpGrowth: 1.8,
      unemployment: 4.2,
      fedRate: 3.8,
      description: 'Mild slowdown with modest recession risk'
    },
    {
      name: 'Bear Case',
      probability: 25,
      gdpGrowth: -1.5,
      unemployment: 5.8,
      fedRate: 2.5,
      description: 'Economic recession with significant policy response'
    }
  ],
  employment: {
    sahmRule: {
      value: 0.23,
      triggered: false,
      interpretation: 'The Sahm Rule recession indicator remains below the 0.50 threshold that historically signals recession onset.'
    }
  },
  aiInsights: [
    {
      title: 'Labor Market Resilience',
      description: 'Despite economic headwinds, the labor market shows remarkable strength with unemployment near historic lows. This suggests consumers may continue spending, providing economic support.',
      confidence: 85,
      impact: 'Medium',
      timeframe: '6-12 months'
    },
    {
      title: 'Credit Market Stress',
      description: 'Widening credit spreads and tightening lending standards indicate financial institutions are becoming more cautious. This could lead to reduced business investment and consumer spending.',
      confidence: 78,
      impact: 'High',
      timeframe: '3-6 months'
    },
    {
      title: 'Yield Curve Normalization',
      description: 'The inverted yield curve is showing signs of potential normalization as the Fed approaches the end of its tightening cycle. This could reduce recession probability if sustained.',
      confidence: 72,
      impact: 'High',
      timeframe: '6-9 months'
    },
    {
      title: 'Consumer Spending Patterns',
      description: 'AI analysis of spending data reveals consumers are shifting from goods to services, indicating economic adaptation rather than contraction. This supports a soft landing scenario.',
      confidence: 88,
      impact: 'Medium',
      timeframe: '3-6 months'
    }
  ]
};

export default EconomicModeling;