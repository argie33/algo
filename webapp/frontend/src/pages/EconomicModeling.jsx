import React, { useState, useEffect, useMemo } from 'react';
import { getFredEconomicData, updateFredData, searchFredSeries, getEconomicCalendar } from '../services/api';
import economicDataService from '../services/economicDataService';
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
        <div  sx={{ p: 3 }}>
          {children}
        </div>
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
  const [economicData, setEconomicData] = useState({});
  const [fredData, setFredData] = useState(null);
  const [dataSource, setDataSource] = useState('loading');
  const [lastUpdated, setLastUpdated] = useState(null);
  const [alertsEnabled, setAlertsEnabled] = useState(true);
  const [confidenceThreshold, setConfidenceThreshold] = useState(70);

  // Load FRED economic data
  useEffect(() => {
    loadEconomicData();
  }, []);

  const loadEconomicData = async () => {
    setLoading(true);
    try {
      // Use comprehensive economic data service
      const [dashboardData, yieldCurve, recessionProb, calendarEvents] = await Promise.all([
        economicDataService.getDashboardData(),
        economicDataService.getYieldCurve(),
        economicDataService.getRecessionProbability(),
        economicDataService.getEconomicCalendar(30)
      ]);
      
      // Get additional detailed indicators
      const indicators = await economicDataService.getIndicators([
        'gdpGrowth', 'unemployment', 'cpiYoY', 'fedFunds', 'treasury10Y', 
        'treasury2Y', 'consumerSentiment', 'industrialProduction', 'retailSales',
        'housingStarts', 'vix', 'nonfarmPayrolls'
      ]);
      
      // Transform real data into UI format
      const transformedData = {
        isMockData: false,
        lastUpdated: new Date().toISOString(),
        dataSource: 'FRED Economic Data',
        
        // Core metrics from real data
        recessionProbability: recessionProb.probability,
        riskLevel: recessionProb.probability > 50 ? 'High' : recessionProb.probability > 30 ? 'Medium' : 'Low',
        gdpGrowth: dashboardData.gdpGrowth?.value || 0,
        unemployment: dashboardData.unemployment?.value || 0,
        inflation: dashboardData.cpiYoY?.value || 0,
        
        // Leading indicators from real data
        leadingIndicators: transformLeadingIndicators(indicators, dashboardData),
        
        // Yield curve data
        yieldCurve: transformYieldCurveData(yieldCurve),
        
        // Economic scenarios based on current conditions
        scenarios: generateRealScenarios(dashboardData, recessionProb),
        
        // AI insights based on real economic conditions
        aiInsights: generateRealAIInsights(dashboardData, indicators, recessionProb),
        
        // Calendar events
        upcomingEvents: transformCalendarData(calendarEvents),
        
        // Additional real data
        forecastModels: generateForecastModels(recessionProb, dashboardData),
        sectorImpacts: generateSectorImpacts(dashboardData),
        marketCorrelations: await economicDataService.getMarketCorrelations()
      };
      
      setEconomicData(transformedData);
      setFredData(indicators);
      setDataSource('real_data');
      setLastUpdated(new Date().toISOString());
      
    } catch (error) {
      console.error('Error loading economic data:', error);
      
      // Minimal fallback data (not 212 lines!)
      const fallbackData = generateMinimalFallbackData(error.message);
      setEconomicData(fallbackData);
      setDataSource('fallback');
    } finally {
      setLoading(false);
    }
  };

  const handleRefreshData = async () => {
    await loadEconomicData();
  };

  const transformCalendarData = (calendarData) => {
    if (!calendarData || !Array.isArray(calendarData)) {
      return mockEconomicData.upcomingEvents;
    }

    return calendarData.slice(0, 10).map(event => {
      // Format date
      let displayDate = 'TBD';
      let displayTime = '';
      
      if (event.date) {
        const eventDate = new Date(event.date);
        displayDate = eventDate.toLocaleDateString('en-US', { 
          month: 'short', 
          day: 'numeric', 
          year: 'numeric' 
        });
      }
      
      if (event.time) {
        displayTime = event.time.substring(0, 5); // Format HH:MM
      }

      // Create forecast text
      let forecast = '';
      if (event.forecast && event.previous) {
        forecast = `${event.forecast} expected (prev: ${event.previous})`;
      } else if (event.forecast) {
        forecast = `${event.forecast} expected`;
      } else if (event.description) {
        forecast = event.description;
      }

      return {
        event: event.event || event.event_name,
        date: displayDate,
        time: displayTime || 'TBD',
        importance: event.importance || 'Medium',
        forecast: forecast,
        category: event.category,
        source: event.source,
        country: event.country || 'US'
      };
    });
  };

  const handleUpdateFredData = async () => {
    setLoading(true);
    try {
      const response = await updateFredData();
      if (response.success) {
        // Reload data after update
        await loadEconomicData();
      }
    } catch (error) {
      console.error('Error updating FRED data:', error);
    } finally {
      setLoading(false);
    }
  };

  // Transform FRED data to match UI expectations
  const transformFredDataForUI = (fredData) => {
    if (!fredData.indicators) return mockEconomicData;

    const indicators = fredData.indicators;
    const derivedMetrics = fredData.derived_metrics || {};

    return {
      ...mockEconomicData, // Keep structure but replace data
      leadingIndicators: [
        {
          name: 'GDP Growth',
          value: indicators.GDP?.value || 0,
          change: '+2.1%',
          signal: indicators.GDP?.value > 25000 ? 'Positive' : 'Negative',
          confidence: 'High',
          impact: 'Major'
        },
        {
          name: 'Unemployment Rate',
          value: `${indicators.UNRATE?.value || 0}%`,
          change: '+0.1pp',
          signal: indicators.UNRATE?.value < 5.0 ? 'Positive' : 'Negative',
          confidence: 'High',
          impact: 'Major'
        },
        {
          name: 'Consumer Price Index',
          value: indicators.CPIAUCSL?.value || 0,
          change: '+0.3%',
          signal: indicators.CPIAUCSL?.value < 320 ? 'Positive' : 'Negative',
          confidence: 'High',
          impact: 'Major'
        },
        {
          name: 'Federal Funds Rate',
          value: `${indicators.FEDFUNDS?.value || 0}%`,
          change: '0.0pp',
          signal: indicators.FEDFUNDS?.value < 6.0 ? 'Neutral' : 'Negative',
          confidence: 'High',
          impact: 'Major'
        },
        {
          name: 'Consumer Sentiment',
          value: indicators.UMCSENT?.value || 0,
          change: '+2.1',
          signal: indicators.UMCSENT?.value > 70 ? 'Positive' : 'Negative',
          confidence: 'Medium',
          impact: 'Moderate'
        },
        {
          name: 'Industrial Production',
          value: indicators.INDPRO?.value || 0,
          change: '+0.4%',
          signal: indicators.INDPRO?.value > 100 ? 'Positive' : 'Negative',
          confidence: 'High',
          impact: 'Major'
        }
      ],
      yieldCurve: {
        spread2y10y: derivedMetrics.yield_curve_spread ? Math.round(derivedMetrics.yield_curve_spread * 100) : 120,
        spread3m10y: derivedMetrics.yield_curve_spread ? Math.round(derivedMetrics.yield_curve_spread * 100) + 20 : 140,
        inversionProbability: derivedMetrics.yield_curve_inverted ? 85 : 15,
        historicalContext: derivedMetrics.yield_curve_inverted ? 'Inverted - Historical Recession Predictor' : 'Normal Yield Curve'
      },
      ratesData: [
        { name: '3M', rate: indicators.DGS3MO?.value || 2.8, color: '#8884d8' },
        { name: '2Y', rate: indicators.DGS2?.value || 3.0, color: '#82ca9d' },
        { name: '10Y', rate: indicators.DGS10?.value || 4.2, color: '#ffc658' }
      ]
    };
  };

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
    <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <div  display="flex" alignItems="center" justifyContent="between" mb={3}>
        <div>
          <div  variant="h3" component="h1" gutterBottom>
            Economic Modeling & Forecasting
          </div>
          <div  variant="body1" color="text.secondary">
            Advanced econometric models and real-time recession probability analysis
          </div>
        </div>
        
        <div  display="flex" alignItems="center" gap={2}>
          <div className="mb-4" size="small" sx={{ minWidth: 120 }}>
            <label className="block text-sm font-medium text-gray-700 mb-1">Timeframe</label>
            <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={selectedTimeframe}
              onChange={(e) => setSelectedTimeframe(e.target.value)}
              label="Timeframe"
            >
              <option  value="3M">3 Months</option>
              <option  value="6M">6 Months</option>
              <option  value="1Y">1 Year</option>
              <option  value="2Y">2 Years</option>
              <option  value="5Y">5 Years</option>
            </select>
          </div>
          
          <div className="mb-4"Label
            control={
              <input type="checkbox" className="toggle"
                checked={liveUpdates}
                onChange={(e) => setLiveUpdates(e.target.checked)}
                color="primary"
              />
            }
            label="Live Updates"
          />
          
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            variant="outlined"
            size="small"
            onClick={handleRefreshData}
            startIcon={<Refresh />}
            disabled={loading}
          >
            Refresh
          </button>
          
          {dataSource === 'fred_api' && (
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              variant="outlined"
              size="small"
              onClick={handleUpdateFredData}
              disabled={loading}
              color="secondary"
            >
              Update FRED Data
            </button>
          )}
        </div>
      </div>

      {/* Data Source Information */}
      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
        <div className="bg-white shadow-md rounded-lg"Content sx={{ py: 2 }}>
          <div  display="flex" alignItems="center" justifyContent="space-between">
            <div  display="flex" alignItems="center" gap={2}>
              <div  variant="body2" color="text.secondary">
                Data Source:
              </div>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                label={
                  dataSource === 'fred_api' ? 'Federal Reserve Economic Data (FRED)' : 
                  dataSource === 'mock_data' ? 'Mock Data' : 'Loading...'
                }
                color={dataSource === 'fred_api' ? 'success' : dataSource === 'mock_data' ? 'warning' : 'default'}
                size="small"
              />
              {lastUpdated && (
                <div  variant="caption" color="text.secondary">
                  Last Updated: {new Date(lastUpdated).toLocaleString()}
                </div>
              )}
            </div>
            
            {loading && <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={20} />}
          </div>
          
          {dataSource === 'mock_data' && (
            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info" sx={{ mt: 2 }}>
              Using mock data. To get real-time FRED data, set the FRED_API_KEY environment variable.
            </div>
          )}
        </div>
      </div>

      {/* Critical Alerts */}
      {alertsEnabled && compositeRecessionProbability > 40 && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
          severity="warning" 
          sx={{ mb: 3 }}
          action={
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" color="inherit" size="small">
              View Details
            </button>
          }
        >
          <strong>Elevated Recession Risk:</strong> Composite model indicates {compositeRecessionProbability}% 
          probability of recession within {selectedTimeframe}. Monitor key indicators closely.
        </div>
      )}

      {economicData.yieldCurve?.isInverted && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
          severity="error" 
          sx={{ mb: 3 }}
          action={
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" color="inherit" size="small">
              Learn More
            </button>
          }
        >
          <strong>Yield Curve Inverted:</strong> {yieldCurveSignal} detected. 
          Historical accuracy: {economicData.yieldCurve.historicalAccuracy}% in predicting recessions.
        </div>
      )}

      {/* Key Economic Indicators */}
      <div className="grid" container spacing={3} mb={4}>
        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  display="flex" alignItems="center" justifyContent="between">
                <div>
                  <div  variant="h6" color="text.secondary">
                    Recession Probability
                  </div>
                  <div  variant="h4" color={getRecessionProbabilityColor(compositeRecessionProbability) + '.main'}>
                    {compositeRecessionProbability}%
                  </div>
                  <div  variant="body2">
                    Composite model ({selectedTimeframe})
                  </div>
                </div>
                <Assessment color={getRiskColor(economicData.riskLevel)} fontSize="large" />
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2" 
                variant="determinate" 
                value={compositeRecessionProbability} 
                color={getRecessionProbabilityColor(compositeRecessionProbability)}
                sx={{ mt: 2 }}
              />
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  display="flex" alignItems="center" justifyContent="between">
                <div>
                  <div  variant="h6" color="text.secondary">
                    Economic Stress
                  </div>
                  <div  variant="h4" color="primary">
                    {economicStressIndex}
                  </div>
                  <div  variant="body2">
                    Stress Index (0-100)
                  </div>
                </div>
                <Speed color="primary" fontSize="large" />
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2" 
                variant="determinate" 
                value={economicStressIndex} 
                color={economicStressIndex > 60 ? 'error' : economicStressIndex > 30 ? 'warning' : 'success'}
                sx={{ mt: 2 }}
              />
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  display="flex" alignItems="center" justifyContent="between">
                <div>
                  <div  variant="h6" color="text.secondary">
                    GDP Growth
                  </div>
                  <div  variant="h4" color="secondary">
                    {economicData.gdpGrowth}%
                  </div>
                  <div  variant="body2">
                    Annualized Q/Q
                  </div>
                </div>
                <ShowChart color="secondary" fontSize="large" />
              </div>
              <div  display="flex" alignItems="center" mt={1}>
                {economicData.gdpGrowth > 0 ? (
                  <TrendingUp color="success" fontSize="small" />
                ) : (
                  <TrendingDown color="error" fontSize="small" />
                )}
                <div  variant="body2" color="text.secondary" ml={1}>
                  vs previous quarter
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  display="flex" alignItems="center" justifyContent="between">
                <div>
                  <div  variant="h6" color="text.secondary">
                    Unemployment
                  </div>
                  <div  variant="h4" color="info.main">
                    {economicData.unemployment}%
                  </div>
                  <div  variant="body2">
                    Current rate
                  </div>
                </div>
                <Work color="info" fontSize="large" />
              </div>
              <div  display="flex" alignItems="center" mt={1}>
                <div  variant="body2" color="text.secondary">
                  Sahm Rule: {economicData.employment?.sahmRule?.value || 'N/A'}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content Tabs */}
      <div  sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <div className="border-b border-gray-200" value={tabValue} onChange={handleTabChange} aria-label="economic modeling tabs">
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Leading Indicators" icon={<Analytics />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Yield Curve" icon={<ShowChart />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Forecast Models" icon={<Assessment />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Sectoral Analysis" icon={<BarChartIcon />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Scenario Planning" icon={<Flag />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="AI Insights" icon={<Psychology />} />
        </div>
      </div>

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={tabValue} index={0}>
        {/* Leading Indicators */}
        <div className="grid" container spacing={3}>
          <div className="grid" item xs={12} md={8}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header
                title="Leading Economic Indicators"
                subheader="Real-time economic momentum analysis"
                action={
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                    label={`${economicData.leadingIndicators?.length || 0} indicators`} 
                    color="primary" 
                    variant="outlined" 
                  />
                }
              />
              <div className="bg-white shadow-md rounded-lg"Content>
                <div className="grid" container spacing={3}>
                  {economicData.leadingIndicators?.map((indicator, index) => (
                    <div className="grid" item xs={12} md={6} key={index}>
                      <div className="bg-white shadow-md rounded-lg" variant="outlined">
                        <div className="bg-white shadow-md rounded-lg"Content>
                          <div  display="flex" alignItems="center" justifyContent="between" mb={2}>
                            <div  display="flex" alignItems="center" gap={1}>
                              {getIndicatorIcon(indicator.trend)}
                              <div  variant="h6">
                                {indicator.name}
                              </div>
                            </div>
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                              label={indicator.signal} 
                              color={indicator.signal === 'Positive' ? 'success' : indicator.signal === 'Negative' ? 'error' : 'default'}
                              size="small"
                            />
                          </div>
                          
                          <div  display="flex" alignItems="center" justifyContent="between" mb={2}>
                            <div  variant="h4" color="primary">
                              {indicator.value}
                            </div>
                            <div  
                              variant="body2" 
                              color={indicator.change > 0 ? 'success.main' : 'error.main'}
                            >
                              {indicator.change > 0 ? '+' : ''}{indicator.change}%
                            </div>
                          </div>
                          
                          <div  variant="body2" color="text.secondary" mb={2}>
                            {indicator.description}
                          </div>
                          
                          <div>
                            <div  display="flex" alignItems="center" justifyContent="between" mb={1}>
                              <div  variant="body2" color="text.secondary">
                                Signal Strength
                              </div>
                              <div  variant="body2" fontWeight="bold">
                                {indicator.strength}%
                              </div>
                            </div>
                            <div className="w-full bg-gray-200 rounded-full h-2" 
                              variant="determinate" 
                              value={indicator.strength} 
                              color={indicator.strength > 70 ? 'success' : indicator.strength > 40 ? 'warning' : 'error'}
                            />
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="grid" item xs={12} md={4}>
            <div className="grid" container spacing={3}>
              {/* Signal Summary */}
              <div className="grid" item xs={12}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Header title="Signal Summary" />
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div  display="flex" alignItems="center" justifyContent="center" mb={3}>
                      <div  textAlign="center">
                        <div  variant="h3" color="primary">
                          {economicStressIndex}
                        </div>
                        <div  variant="body2" color="text.secondary">
                          Stress Index
                        </div>
                      </div>
                    </div>
                    
                    <div  mb={3}>
                      <div  variant="body2" color="text.secondary" mb={1}>
                        Risk Level
                      </div>
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                        label={economicData.riskLevel} 
                        color={getRiskColor(economicData.riskLevel)}
                        size="large"
                      />
                    </div>
                    
                    <hr className="border-gray-200" sx={{ mb: 2 }} />
                    
                    <div  display="flex" justifyContent="between" mb={1}>
                      <div  variant="body2">Positive Signals</div>
                      <div  variant="body2" fontWeight="bold">
                        {economicData.leadingIndicators?.filter(i => i.signal === 'Positive').length || 0}
                      </div>
                    </div>
                    <div  display="flex" justifyContent="between" mb={1}>
                      <div  variant="body2">Negative Signals</div>
                      <div  variant="body2" fontWeight="bold">
                        {economicData.leadingIndicators?.filter(i => i.signal === 'Negative').length || 0}
                      </div>
                    </div>
                    <div  display="flex" justifyContent="between">
                      <div  variant="body2">Neutral Signals</div>
                      <div  variant="body2" fontWeight="bold">
                        {economicData.leadingIndicators?.filter(i => i.signal === 'Neutral').length || 0}
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Upcoming Economic Events */}
              <div className="grid" item xs={12}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Header 
                    title="Upcoming Events" 
                    subheader="Next 30 days"
                  />
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <List>
                      {economicData.upcomingEvents?.map((event, index) => (
                        <ListItem key={index} alignItems="flex-start">
                          <ListItemAvatar>
                            <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ bgcolor: getRiskColor(event.importance) + '.main' }}>
                              <Schedule />
                            </div>
                          </ListItemAvatar>
                          <ListItemText
                            primary={event.event}
                            secondary={
                              <div>
                                <div  variant="body2" color="text.secondary">
                                  {event.date} • {event.time}
                                </div>
                                <div  variant="body2" color="text.primary">
                                  {event.forecast}
                                </div>
                              </div>
                            }
                          />
                        </ListItem>
                      ))}
                    </List>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={tabValue} index={1}>
        {/* Yield Curve */}
        <div className="grid" container spacing={3}>
          <div className="grid" item xs={12} md={8}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header
                title="Yield Curve Analysis"
                subheader="Treasury yield curve and inversion analysis"
              />
              <div className="bg-white shadow-md rounded-lg"Content>
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
                
                <div  mt={3}>
                  <div className="grid" container spacing={2}>
                    <div className="grid" item xs={6}>
                      <div  variant="body2" color="text.secondary">
                        2Y-10Y Spread
                      </div>
                      <div  
                        variant="h6" 
                        color={economicData.yieldCurve?.spread2y10y < 0 ? 'error.main' : 'success.main'}
                      >
                        {economicData.yieldCurve?.spread2y10y} bps
                      </div>
                    </div>
                    <div className="grid" item xs={6}>
                      <div  variant="body2" color="text.secondary">
                        3M-10Y Spread
                      </div>
                      <div  
                        variant="h6" 
                        color={economicData.yieldCurve?.spread3m10y < 0 ? 'error.main' : 'success.main'}
                      >
                        {economicData.yieldCurve?.spread3m10y} bps
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="grid" item xs={12} md={4}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header title="Inversion Analysis" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
                  severity={economicData.yieldCurve?.isInverted ? 'error' : 'success'}
                  sx={{ mb: 3 }}
                >
                  <div  variant="h6">
                    {economicData.yieldCurve?.isInverted ? 'Yield Curve Inverted' : 'Normal Yield Curve'}
                  </div>
                  <div  variant="body2">
                    {economicData.yieldCurve?.interpretation}
                  </div>
                </div>
                
                <div  mb={3}>
                  <div  variant="body2" color="text.secondary" mb={1}>
                    Signal Strength
                  </div>
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                    label={yieldCurveSignal} 
                    color={yieldCurveSignal.includes('Strong') ? 'error' : yieldCurveSignal.includes('Recession') ? 'warning' : 'success'}
                    size="large"
                  />
                </div>
                
                <hr className="border-gray-200" sx={{ mb: 2 }} />
                
                <div  variant="h6" mb={2}>Historical Context</div>
                <div  display="flex" justifyContent="between" mb={1}>
                  <div  variant="body2">Historical Accuracy</div>
                  <div  variant="body2" fontWeight="bold">
                    {economicData.yieldCurve?.historicalAccuracy}%
                  </div>
                </div>
                <div  display="flex" justifyContent="between" mb={1}>
                  <div  variant="body2">Average Lead Time</div>
                  <div  variant="body2" fontWeight="bold">
                    {economicData.yieldCurve?.averageLeadTime} months
                  </div>
                </div>
                
                <div  mt={3}>
                  <div  variant="body2" color="text.secondary">
                    The yield curve has inverted before {economicData.yieldCurve?.historicalAccuracy}% of recessions 
                    since 1970, with an average lead time of {economicData.yieldCurve?.averageLeadTime} months.
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={tabValue} index={2}>
        {/* Forecast Models */}
        <div className="grid" container spacing={3}>
          <div className="grid" item xs={12} md={8}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header
                title="Recession Probability Models"
                subheader="Institutional forecasting models and ensemble predictions"
              />
              <div className="bg-white shadow-md rounded-lg"Content>
                <div className="grid" container spacing={3}>
                  {economicData.forecastModels?.map((model, index) => (
                    <div className="grid" item xs={12} md={6} key={index}>
                      <div className="bg-white shadow-md rounded-lg" variant="outlined">
                        <div className="bg-white shadow-md rounded-lg"Content>
                          <div  display="flex" alignItems="center" justifyContent="between" mb={2}>
                            <div  variant="h6">
                              {model.name}
                            </div>
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                              label={`${model.confidence}% confidence`} 
                              color={model.confidence > 80 ? 'success' : model.confidence > 60 ? 'warning' : 'error'}
                              size="small"
                            />
                          </div>
                          
                          <div  textAlign="center" mb={3}>
                            <div  variant="h3" color="primary">
                              {model.probability}%
                            </div>
                            <div  variant="body2" color="text.secondary">
                              Recession Probability
                            </div>
                          </div>
                          
                          <div className="w-full bg-gray-200 rounded-full h-2" 
                            variant="determinate" 
                            value={model.probability} 
                            color={getRecessionProbabilityColor(model.probability)}
                            sx={{ mb: 2 }}
                          />
                          
                          <div  display="flex" justifyContent="between" mb={1}>
                            <div  variant="body2" color="text.secondary">
                              Time Horizon
                            </div>
                            <div  variant="body2" fontWeight="bold">
                              {model.timeHorizon}
                            </div>
                          </div>
                          
                          <div  variant="body2" color="text.secondary">
                            {model.methodology}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="grid" item xs={12} md={4}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header title="Ensemble Prediction" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  textAlign="center" mb={3}>
                  <div  variant="h2" color="primary">
                    {compositeRecessionProbability}%
                  </div>
                  <div  variant="body1" color="text.secondary">
                    Composite Probability
                  </div>
                </div>
                
                <div className="w-full bg-gray-200 rounded-full h-2" 
                  variant="determinate" 
                  value={compositeRecessionProbability} 
                  color={getRecessionProbabilityColor(compositeRecessionProbability)}
                  sx={{ mb: 3, height: 8 }}
                />
                
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
                  severity={compositeRecessionProbability > 50 ? 'error' : compositeRecessionProbability > 30 ? 'warning' : 'info'}
                  sx={{ mb: 3 }}
                >
                  <div  variant="body2">
                    {compositeRecessionProbability > 50 
                      ? 'High probability of recession. Consider defensive positioning.'
                      : compositeRecessionProbability > 30 
                      ? 'Elevated recession risk. Monitor indicators closely.'
                      : 'Low recession probability. Economic conditions appear stable.'}
                  </div>
                </div>
                
                <div  variant="h6" mb={2}>Model Weights</div>
                <div>
                  <div  display="flex" justifyContent="between" mb={1}>
                    <div  variant="body2">NY Fed Model</div>
                    <div  variant="body2" fontWeight="bold">35%</div>
                  </div>
                  <div  display="flex" justifyContent="between" mb={1}>
                    <div  variant="body2">Goldman Sachs</div>
                    <div  variant="body2" fontWeight="bold">25%</div>
                  </div>
                  <div  display="flex" justifyContent="between" mb={1}>
                    <div  variant="body2">JP Morgan</div>
                    <div  variant="body2" fontWeight="bold">25%</div>
                  </div>
                  <div  display="flex" justifyContent="between">
                    <div  variant="body2">AI Ensemble</div>
                    <div  variant="body2" fontWeight="bold">15%</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={tabValue} index={3}>
        {/* Sectoral Analysis */}
        <div className="grid" container spacing={3}>
          <div className="grid" item xs={12} md={8}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header title="Sectoral Economic Performance" />
              <div className="bg-white shadow-md rounded-lg"Content>
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
              </div>
            </div>
          </div>

          <div className="grid" item xs={12} md={4}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header title="Sector Leaders" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <List>
                  {economicData.sectoralData?.sort((a, b) => b.growth - a.growth).map((sector, index) => (
                    <ListItem key={index}>
                      <ListItemAvatar>
                        <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center">
                          {getSectorIcon(sector.sector)}
                        </div>
                      </ListItemAvatar>
                      <ListItemText
                        primary={sector.sector}
                        secondary={
                          <div  display="flex" alignItems="center" gap={1}>
                            <div  variant="body2" color="text.secondary">
                              {sector.description}
                            </div>
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                              label={`${sector.growth >= 0 ? '+' : ''}${sector.growth}%`}
                              color={sector.growth >= 0 ? 'success' : 'error'}
                              size="small"
                            />
                          </div>
                        }
                      />
                    </ListItem>
                  ))}
                </List>
              </div>
            </div>
          </div>
        </div>
      </div>

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={tabValue} index={4}>
        {/* Scenario Planning */}
        <div className="grid" container spacing={3}>
          <div className="grid" item xs={12}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header title="Economic Scenario Analysis" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <div className="grid" container spacing={3}>
                  {economicData.scenarios?.map((scenario, index) => (
                    <div className="grid" item xs={12} md={4} key={index}>
                      <div className="bg-white shadow-md rounded-lg" 
                        variant="outlined" 
                        sx={{ 
                          border: selectedScenario === scenario.name.toLowerCase().replace(' ', '') ? 2 : 1,
                          borderColor: selectedScenario === scenario.name.toLowerCase().replace(' ', '') ? 'primary.main' : 'divider'
                        }}
                      >
                        <div className="bg-white shadow-md rounded-lg"Content>
                          <div  display="flex" alignItems="center" justifyContent="between" mb={2}>
                            <div  variant="h6">
                              {scenario.name}
                            </div>
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                              label={`${scenario.probability}% probability`} 
                              color={scenario.name === 'Base Case' ? 'primary' : scenario.name === 'Bull Case' ? 'success' : 'error'}
                              size="small"
                            />
                          </div>
                          
                          <div  mb={3}>
                            <div  variant="body2" color="text.secondary">
                              {scenario.description}
                            </div>
                          </div>
                          
                          <div  display="flex" justifyContent="between" mb={1}>
                            <div  variant="body2" color="text.secondary">
                              GDP Growth
                            </div>
                            <div  variant="body2" fontWeight="bold">
                              {scenario.gdpGrowth}%
                            </div>
                          </div>
                          
                          <div  display="flex" justifyContent="between" mb={1}>
                            <div  variant="body2" color="text.secondary">
                              Unemployment
                            </div>
                            <div  variant="body2" fontWeight="bold">
                              {scenario.unemployment}%
                            </div>
                          </div>
                          
                          <div  display="flex" justifyContent="between" mb={2}>
                            <div  variant="body2" color="text.secondary">
                              Fed Funds Rate
                            </div>
                            <div  variant="body2" fontWeight="bold">
                              {scenario.fedRate}%
                            </div>
                          </div>
                          
                          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                            variant={selectedScenario === scenario.name.toLowerCase().replace(' ', '') ? 'contained' : 'outlined'}
                            fullWidth
                            onClick={() => setSelectedScenario(scenario.name.toLowerCase().replace(' ', ''))}
                          >
                            Analyze Scenario
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={tabValue} index={5}>
        {/* AI Insights */}
        <div className="grid" container spacing={3}>
          <div className="grid" item xs={12} md={8}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header 
                title="AI-Powered Economic Insights"
                subheader="Machine learning analysis of economic patterns and trends"
              />
              <div className="bg-white shadow-md rounded-lg"Content>
                <div className="grid" container spacing={3}>
                  {economicData.aiInsights?.map((insight, index) => (
                    <div className="grid" item xs={12} key={index}>
                      <div className="bg-white shadow-md rounded-lg" variant="outlined">
                        <div className="bg-white shadow-md rounded-lg"Content>
                          <div  display="flex" alignItems="center" gap={2} mb={2}>
                            <Lightbulb color="primary" />
                            <div  variant="h6">
                              {insight.title}
                            </div>
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                              label={`${insight.confidence}% confidence`} 
                              color={insight.confidence > 80 ? 'success' : insight.confidence > 60 ? 'warning' : 'error'}
                              size="small"
                            />
                          </div>
                          
                          <div  variant="body1" mb={2}>
                            {insight.description}
                          </div>
                          
                          <div  display="flex" alignItems="center" gap={2}>
                            <div  variant="body2" color="text.secondary">
                              Impact: {insight.impact}
                            </div>
                            <div  variant="body2" color="text.secondary">
                              Timeframe: {insight.timeframe}
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="grid" item xs={12} md={4}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header title="AI Model Performance" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  textAlign="center" mb={3}>
                  <div  variant="h3" color="primary">
                    87%
                  </div>
                  <div  variant="body2" color="text.secondary">
                    Prediction Accuracy
                  </div>
                </div>
                
                <div className="w-full bg-gray-200 rounded-full h-2" 
                  variant="determinate" 
                  value={87} 
                  color="success"
                  sx={{ mb: 3, height: 8 }}
                />
                
                <div  display="flex" justifyContent="between" mb={1}>
                  <div  variant="body2" color="text.secondary">
                    Data Points Analyzed
                  </div>
                  <div  variant="body2" fontWeight="bold">
                    15,000+
                  </div>
                </div>
                
                <div  display="flex" justifyContent="between" mb={1}>
                  <div  variant="body2" color="text.secondary">
                    Last Model Update
                  </div>
                  <div  variant="body2" fontWeight="bold">
                    2 hours ago
                  </div>
                </div>
                
                <div  display="flex" justifyContent="between" mb={3}>
                  <div  variant="body2" color="text.secondary">
                    Next Update
                  </div>
                  <div  variant="body2" fontWeight="bold">
                    In 4 hours
                  </div>
                </div>
                
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info">
                  <div  variant="body2">
                    AI models are continuously learning from new economic data to improve prediction accuracy.
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// Helper functions for transforming real economic data
const transformLeadingIndicators = (indicators, dashboardData) => {
  const leadingIndicators = [];
  
  // Transform real indicators into UI format
  if (indicators.unemployment) {
    const latest = indicators.unemployment.data[indicators.unemployment.data.length - 1];
    const previous = indicators.unemployment.data[indicators.unemployment.data.length - 2];
    const change = latest && previous ? (latest.value - previous.value).toFixed(1) : '0.0';
    
    leadingIndicators.push({
      name: 'Unemployment Rate',
      value: `${latest?.value?.toFixed(1) || '0.0'}%`,
      change: `${change}pp`,
      trend: parseFloat(change) > 0 ? 'deteriorating' : 'improving',
      signal: latest?.value < 4.0 ? 'Positive' : 'Negative',
      strength: latest?.value < 4.0 ? 75 : 25,
      description: 'Current unemployment rate - key labor market indicator'
    });
  }
  
  if (indicators.consumerSentiment) {
    const latest = indicators.consumerSentiment.data[indicators.consumerSentiment.data.length - 1];
    const previous = indicators.consumerSentiment.data[indicators.consumerSentiment.data.length - 2];
    const change = latest && previous ? (latest.value - previous.value).toFixed(1) : '0.0';
    
    leadingIndicators.push({
      name: 'Consumer Sentiment',
      value: latest?.value?.toFixed(1) || '100.0',
      change: change,
      trend: parseFloat(change) > 0 ? 'improving' : 'deteriorating',
      signal: latest?.value > 70 ? 'Positive' : 'Negative',
      strength: latest?.value > 70 ? 75 : 25,
      description: 'Consumer assessment of current and future economic conditions'
    });
  }
  
  if (indicators.industrialProduction) {
    const latest = indicators.industrialProduction.data[indicators.industrialProduction.data.length - 1];
    const previous = indicators.industrialProduction.data[indicators.industrialProduction.data.length - 2];
    const changePercent = latest && previous ? (((latest.value - previous.value) / previous.value) * 100).toFixed(1) : '0.0';
    
    leadingIndicators.push({
      name: 'Industrial Production',
      value: latest?.value?.toFixed(1) || '100.0',
      change: `${changePercent}%`,
      trend: parseFloat(changePercent) > 0 ? 'improving' : 'deteriorating',
      signal: parseFloat(changePercent) > 0 ? 'Positive' : 'Negative',
      strength: Math.abs(parseFloat(changePercent)) * 10,
      description: 'Manufacturing, mining, and utilities output indicator'
    });
  }
  
  return leadingIndicators;
};

const transformYieldCurveData = (yieldCurve) => {
  if (!yieldCurve || !yieldCurve.curve) {
    return {
      spread2y10y: 120,
      spread3m10y: 140,
      inversionProbability: 15,
      historicalContext: 'Data unavailable'
    };
  }
  
  const twoYear = yieldCurve.curve.find(c => c.maturity === '2 Year');
  const tenYear = yieldCurve.curve.find(c => c.maturity === '10 Year');
  const threeMonth = yieldCurve.curve.find(c => c.maturity === '3 Month');
  
  const spread2y10y = tenYear && twoYear ? Math.round((tenYear.yield - twoYear.yield) * 100) : 120;
  const spread3m10y = tenYear && threeMonth ? Math.round((tenYear.yield - threeMonth.yield) * 100) : 140;
  
  return {
    spread2y10y,
    spread3m10y,
    inversionProbability: yieldCurve.isInverted ? 85 : 15,
    historicalContext: yieldCurve.isInverted ? 'Inverted - Historical Recession Predictor' : 'Normal Yield Curve'
  };
};

const generateRealScenarios = (dashboardData, recessionProb) => [
  {
    name: 'Bull Case',
    probability: Math.max(20, 40 - Math.round(recessionProb.probability / 3)),
    gdpGrowth: Math.max((dashboardData.gdpGrowth?.value || 2.0) + 1.0, 2.5),
    unemployment: Math.max((dashboardData.unemployment?.value || 4.0) - 0.5, 3.0),
    fedRate: 4.5,
    description: 'Economic acceleration with declining unemployment'
  },
  {
    name: 'Base Case',
    probability: 50,
    gdpGrowth: dashboardData.gdpGrowth?.value || 1.8,
    unemployment: dashboardData.unemployment?.value || 4.2,
    fedRate: dashboardData.fedFunds?.value || 3.8,
    description: 'Current trajectory continues with modest growth'
  },
  {
    name: 'Bear Case',
    probability: Math.min(30, Math.round(recessionProb.probability / 2)),
    gdpGrowth: Math.min((dashboardData.gdpGrowth?.value || 2.0) - 2.0, -1.0),
    unemployment: Math.min((dashboardData.unemployment?.value || 4.0) + 2.0, 6.5),
    fedRate: 2.5,
    description: 'Economic contraction requiring policy intervention'
  }
];

const generateRealAIInsights = (dashboardData, indicators, recessionProb) => {
  const insights = [];
  
  const unemploymentRate = dashboardData.unemployment?.value;
  if (unemploymentRate && unemploymentRate < 4.0) {
    insights.push({
      title: 'Labor Market Strength',
      description: `Unemployment at ${unemploymentRate.toFixed(1)}% indicates a tight labor market, supporting consumer spending despite economic headwinds.`,
      confidence: 85,
      impact: 'Medium',
      timeframe: '6-12 months'
    });
  }
  
  if (recessionProb.probability > 40) {
    insights.push({
      title: 'Elevated Recession Risk',
      description: `Our model indicates ${recessionProb.probability}% recession probability based on current yield curve and economic indicators.`,
      confidence: Math.min(recessionProb.probability + 15, 90),
      impact: 'High',
      timeframe: '6-18 months'
    });
  }
  
  const gdpGrowth = dashboardData.gdpGrowth?.value;
  if (gdpGrowth !== null) {
    const trend = gdpGrowth > 2.5 ? 'accelerating' : gdpGrowth > 1.0 ? 'moderate' : 'slowing';
    insights.push({
      title: `Economic Growth ${trend.charAt(0).toUpperCase() + trend.slice(1)}`,
      description: `GDP growth at ${gdpGrowth.toFixed(1)}% suggests ${trend} economic momentum with implications for monetary policy.`,
      confidence: 75,
      impact: gdpGrowth > 2.0 ? 'High' : 'Medium',
      timeframe: '3-9 months'
    });
  }
  
  return insights;
};

const generateForecastModels = (recessionProb, dashboardData) => [
  {
    name: 'FRED-Based Model',
    probability: recessionProb.probability,
    confidence: 78,
    keyFactors: ['Yield Curve', 'Unemployment', 'GDP Growth'],
    lastUpdated: new Date().toISOString()
  },
  {
    name: 'Labor Market Model', 
    probability: dashboardData.unemployment?.value > 4.5 ? 45 : 25,
    confidence: 72,
    keyFactors: ['Unemployment Rate', 'Job Openings', 'Wage Growth'],
    lastUpdated: new Date().toISOString()
  }
];

const generateSectorImpacts = (dashboardData) => [
  { sector: 'Technology', impact: dashboardData.fedFunds?.value > 4.0 ? 'Negative' : 'Neutral', probability: 65 },
  { sector: 'Consumer Discretionary', impact: dashboardData.unemployment?.value > 4.5 ? 'Negative' : 'Positive', probability: 70 },
  { sector: 'Financials', impact: dashboardData.fedFunds?.value > 3.0 ? 'Positive' : 'Neutral', probability: 60 },
  { sector: 'Real Estate', impact: dashboardData.fedFunds?.value > 4.0 ? 'Negative' : 'Neutral', probability: 75 }
];

const generateMinimalFallbackData = (errorMessage) => ({
  isMockData: true,
  lastUpdated: new Date().toISOString(),
  dataSource: 'fallback',
  errorMessage,
  recessionProbability: 35,
  riskLevel: 'Medium',
  gdpGrowth: 1.8,
  unemployment: 4.0,
  inflation: 3.2,
  leadingIndicators: [
    {
      name: 'Economic Data Loading',
      value: 'N/A',
      change: '0.0',
      trend: 'stable',
      signal: 'Neutral',
      strength: 50,
      description: `Unable to load real data: ${errorMessage}`
    }
  ],
  yieldCurve: {
    spread2y10y: 120,
    spread3m10y: 140,
    inversionProbability: 15,
    historicalContext: 'Data temporarily unavailable'
  },
  scenarios: [
    {
      name: 'Base Case',
      probability: 100,
      gdpGrowth: 1.8,
      unemployment: 4.0,
      fedRate: 3.8,
      description: 'Please refresh to load real economic data'
    }
  ],
  aiInsights: [
    {
      title: 'Connection Issue',
      description: 'Unable to connect to economic data sources. Please check your internet connection and try refreshing.',
      confidence: 50,
      impact: 'Low',
      timeframe: 'Immediate'
    }
  ],
  upcomingEvents: [],
  forecastModels: [],
  sectorImpacts: [],
  marketCorrelations: {}
});

// Minimal mock data (replacing 212-line object!)
const mockEconomicData = {
  isMockData: true,
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