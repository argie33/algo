import React, { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { createComponentLogger } from '../utils/errorLogger'
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Typography,
  Grid,
  Tabs,
  Tab,
  LinearProgress,
  Alert,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  IconButton,
  Button,
  Tooltip,
  Divider,
  Avatar,
  AvatarGroup,
  Badge,
  Stack,
  Fade,
  Zoom,
  Collapse,
  useTheme,
  alpha,
  Skeleton,
  ToggleButton,
  ToggleButtonGroup,
  CircularProgress,
  Select,
  MenuItem,
  FormControl,
  InputLabel
} from '@mui/material'
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, 
  BarChart, Bar, PieChart, Pie, Cell, Legend, AreaChart, Area, RadarChart, PolarGrid, 
  PolarAngleAxis, PolarRadiusAxis, Radar, ComposedChart, Treemap, RadialBarChart, RadialBar 
} from 'recharts'
import {
  TrendingUp,
  TrendingDown,
  Analytics,
  Speed,
  Psychology,
  Timeline,
  ShowChart,
  Refresh,
  Info,
  Warning,
  CheckCircle,
  Error as ErrorIcon,
  AccountBalance,
  Business,
  Assessment,
  Public,
  CalendarToday,
  AttachMoney,
  TrendingFlat,
  BarChart as BarChartIcon,
  PieChart as PieChartIcon,
  BubbleChart,
  DonutLarge,
  FilterList,
  Download,
  Share,
  Fullscreen,
  FullscreenExit,
  NavigateNext,
  NavigateBefore,
  Star,
  StarBorder,
  Equalizer,
  WaterDrop,
  Bolt,
  LocalFireDepartment
} from '@mui/icons-material'

import { api, getMarketOverview, getMarketSentimentHistory, getMarketSectorPerformance, getMarketBreadth, getEconomicIndicators, getSeasonalityData, getMarketResearchIndicators } from '../services/api'
import { formatCurrency, formatNumber, formatPercentage, getChangeColor, getMarketCapCategory } from '../utils/formatters'

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8', '#82ca9d', '#ffc658', '#ff7c7c']

// Advanced color schemes for different visualizations
const CHART_COLORS = {
  primary: ['#6366f1', '#8b5cf6', '#ec4899', '#f43f5e', '#f59e0b', '#10b981', '#06b6d4', '#3b82f6'],
  gradient: [
    { start: '#667eea', end: '#764ba2' },
    { start: '#f093fb', end: '#f5576c' },
    { start: '#4facfe', end: '#00f2fe' },
    { start: '#fa709a', end: '#fee140' },
    { start: '#30cfd0', end: '#330867' },
    { start: '#a8edea', end: '#fed6e3' },
    { start: '#ff9a9e', end: '#fecfef' },
    { start: '#fbc2eb', end: '#a6c1ee' }
  ],
  sentiment: {
    bullish: '#10b981',
    bearish: '#ef4444',
    neutral: '#6b7280',
    extreme: '#dc2626',
    moderate: '#f59e0b'
  },
  performance: {
    positive: '#10b981',
    negative: '#ef4444',
    neutral: '#6b7280',
    strong: '#059669',
    weak: '#dc2626'
  }
}

// Enhanced custom components
const AnimatedCard = ({ children, delay = 0, ...props }) => {
  const theme = useTheme()
  return (
    <Zoom in={true} timeout={300 + delay * 100}>
      <Card
        {...props}
        sx={{
          background: theme.palette.background.paper,
          backdropFilter: 'blur(10px)',
          border: `1px solid ${alpha(theme.palette.primary.main, 0.1)}`,
          transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          '&:hover': {
            transform: 'translateY(-4px)',
            boxShadow: theme.shadows[8],
            border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`,
          },
          ...props.sx
        }}
      >
        {children}
      </Card>
    </Zoom>
  )
}

const GradientCard = ({ children, gradient, ...props }) => {
  const theme = useTheme()
  return (
    <Card
      {...props}
      sx={{
        background: gradient || `linear-gradient(135deg, ${theme.palette.primary.main} 0%, ${theme.palette.secondary.main} 100%)`,
        color: 'white',
        position: 'relative',
        overflow: 'hidden',
        '&::before': {
          content: '""',
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(255,255,255,0.1)',
          transform: 'translateX(-100%)',
          transition: 'transform 0.6s ease',
        },
        '&:hover::before': {
          transform: 'translateX(0)',
        },
        ...props.sx
      }}
    >
      {children}
    </Card>
  )
}

const MetricCard = ({ title, value, subtitle, icon, trend, color = 'primary', gradient }) => {
  const theme = useTheme()
  const isPositive = trend > 0
  
  return (
    <GradientCard gradient={gradient}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <Box sx={{ flex: 1 }}>
            <Typography variant="subtitle2" sx={{ opacity: 0.9, fontWeight: 500 }}>
              {title}
            </Typography>
            <Typography variant="h3" sx={{ my: 1, fontWeight: 700 }}>
              {value}
            </Typography>
            {subtitle && (
              <Typography variant="body2" sx={{ opacity: 0.8 }}>
                {subtitle}
              </Typography>
            )}
            {trend !== undefined && (
              <Box sx={{ display: 'flex', alignItems: 'center', mt: 1 }}>
                {isPositive ? <TrendingUp fontSize="small" /> : <TrendingDown fontSize="small" />}
                <Typography variant="body2" sx={{ ml: 0.5, fontWeight: 600 }}>
                  {Math.abs(trend)}%
                </Typography>
              </Box>
            )}
          </Box>
          {icon && (
            <Box
              sx={{
                width: 48,
                height: 48,
                borderRadius: '50%',
                bgcolor: 'rgba(255,255,255,0.2)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '1.5rem'
              }}
            >
              {icon}
            </Box>
          )}
        </Box>
      </CardContent>
    </GradientCard>
  )
}

const SentimentGauge = ({ value, label, max = 100, size = 120 }) => {
  const theme = useTheme()
  const percentage = (value / max) * 100
  const rotation = (percentage * 180) / 100 - 90
  
  const getColor = () => {
    if (percentage <= 20) return theme.palette.error.main
    if (percentage <= 40) return theme.palette.warning.main
    if (percentage <= 60) return theme.palette.info.main
    if (percentage <= 80) return theme.palette.success.light
    return theme.palette.success.main
  }
  
  return (
    <Box sx={{ position: 'relative', width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={(size - 20) / 2}
          stroke={alpha(theme.palette.divider, 0.3)}
          strokeWidth="10"
          fill="none"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={(size - 20) / 2}
          stroke={getColor()}
          strokeWidth="10"
          fill="none"
          strokeDasharray={`${(percentage * Math.PI * (size - 20)) / 100} ${Math.PI * (size - 20)}`}
          style={{ transition: 'stroke-dasharray 0.5s ease' }}
        />
      </svg>
      <Box
        sx={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          textAlign: 'center'
        }}
      >
        <Typography variant="h4" sx={{ fontWeight: 700, color: getColor() }}>
          {value}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {label}
        </Typography>
      </Box>
    </Box>
  )
}

const TabPanel = ({ children, value, index, ...other }) => (
  <div
    role="tabpanel"
    hidden={value !== index}
    id={`market-tabpanel-${index}`}
    aria-labelledby={`market-tab-${index}`}
    {...other}
  >
    {value === index && (
      <Box sx={{ pt: 3 }}>
        {children}
      </Box>
    )}
  </div>
)

const MetricTable = ({ data, columns, title }) => (
  <Card>
    <CardContent>
      <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
        {title}
      </Typography>
      <TableContainer component={Paper} elevation={0}>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ backgroundColor: 'grey.50' }}>
              {columns.map((col) => (
                <TableCell key={col.key} sx={{ fontWeight: 600 }}>
                  {col.label}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.slice(0, 10).map((item, index) => (
              <TableRow key={item.ticker || index} hover>
                {columns.map((col) => (
                  <TableCell key={col.key}>
                    {col.render ? col.render(item[col.key], item) : item[col.key] || 'N/A'}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </CardContent>
  </Card>
)

// Create component-specific logger
const logger = createComponentLogger('MarketOverview');

// Simplified API functions that work directly with your data
const fetchMarketOverview = async () => {
  try {
    console.log('📈 Fetching market overview...')
    const response = await getMarketOverview()
    console.log('📈 Market overview response:', response)
    return response
  } catch (error) {
    console.error('❌ Market overview error:', error)
    throw error
  }
}

const fetchSentimentHistory = async (days = 30) => {
  try {
    console.log(`📊 Fetching sentiment history for ${days} days...`)
    const response = await getMarketSentimentHistory(days)
    console.log('📊 Sentiment history response:', response)
    return response
  } catch (error) {
    console.error('❌ Sentiment history error:', error)
    throw error
  }
}

const fetchSectorPerformance = async () => {
  try {
    console.log('🏭 Fetching sector performance...')
    const response = await getMarketSectorPerformance()
    console.log('🏭 Sector performance response:', response)
    return response
  } catch (error) {
    console.error('❌ Sector performance error:', error)
    throw error
  }
}

const fetchMarketBreadth = async () => {
  try {
    console.log('📏 Fetching market breadth...')
    const response = await getMarketBreadth()
    console.log('📏 Market breadth response:', response)
    return response
  } catch (error) {
    console.error('❌ Market breadth error:', error)
    throw error
  }
}

const fetchEconomicIndicators = async (days = 90) => {
  try {
    console.log(`💰 Fetching economic indicators for ${days} days...`)
    const response = await getEconomicIndicators(days)
    console.log('💰 Economic indicators response:', response)
    return response
  } catch (error) {
    console.error('❌ Economic indicators error:', error)
    throw error
  }
}

const fetchSeasonalityData = async () => {
  try {
    console.log('📅 Fetching seasonality data...')
    const response = await getSeasonalityData()
    console.log('📅 Seasonality response:', response)
    return response
  } catch (error) {
    console.error('❌ Seasonality error:', error)
    throw error
  }
}

const fetchResearchIndicators = async () => {
  try {
    console.log('🔬 Fetching research indicators...')
    const response = await getMarketResearchIndicators()
    console.log('🔬 Research indicators response:', response)
    return response
  } catch (error) {
    console.error('❌ Research indicators error:', error)
    throw error
  }
}

function MarketOverview() {
  const [tabValue, setTabValue] = useState(0)
  const [timeframe, setTimeframe] = useState('1D')
  const [viewMode, setViewMode] = useState('cards')
  const [selectedSector, setSelectedSector] = useState('all')
  const [fullscreen, setFullscreen] = useState(false)
  const theme = useTheme()
  
  const { data: marketData, isLoading: marketLoading, error: marketError } = useQuery({
    queryKey: ['market-overview'],
    queryFn: fetchMarketOverview,
    refetchInterval: 60000,
    retry: 2,
    staleTime: 30000
  })

  const { data: sentimentData, isLoading: sentimentLoading } = useQuery({
    queryKey: ['market-sentiment-history'],
    queryFn: () => fetchSentimentHistory(30),
    enabled: tabValue === 1,
    staleTime: 30000
  })

  const { data: sectorData, isLoading: sectorLoading } = useQuery({
    queryKey: ['market-sector-performance'],
    queryFn: fetchSectorPerformance,
    enabled: tabValue === 2,
    staleTime: 30000
  })

  const { data: breadthData, isLoading: breadthLoading } = useQuery({
    queryKey: ['market-breadth'],
    queryFn: fetchMarketBreadth,
    enabled: tabValue === 3,
    staleTime: 30000
  })

  const { data: economicData, isLoading: economicLoading } = useQuery({
    queryKey: ['economic-indicators'],
    queryFn: () => fetchEconomicIndicators(90),
    enabled: tabValue === 4,
    staleTime: 30000
  })

  const { data: seasonalityData, isLoading: seasonalityLoading } = useQuery({
    queryKey: ['seasonality-data'],
    queryFn: fetchSeasonalityData,
    enabled: tabValue === 5,
    staleTime: 30000
  })

  const { data: researchData, isLoading: researchLoading } = useQuery({
    queryKey: ['market-research-indicators'],
    queryFn: fetchResearchIndicators,
    enabled: tabValue === 6,
    staleTime: 30000
  })

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue)
  }
  if (marketError) {
    return (
      <Box>
        <Typography variant="h4" sx={{ mb: 3, fontWeight: 600 }}>
          Market Overview
        </Typography>
        <Alert severity="error" sx={{ mb: 3 }}>
          Failed to load market data. Please check your data sources and try again.
          <br /><small>Technical details: {marketError?.message || 'Unknown error'}</small>
          <br /><small>Debug endpoint: <code>PLACEHOLDER_API_URL/market/debug</code></small>
        </Alert>
      </Box>
    )
  }

  // Extract data from API responses - handles both direct data and nested structure
  const sentimentIndicators = marketData?.data?.sentiment_indicators || marketData?.sentiment_indicators || {}
  const marketBreadth = marketData?.data?.market_breadth || marketData?.market_breadth || {}
  const marketCap = marketData?.data?.market_cap || marketData?.market_cap || {}
  const economicIndicators = marketData?.data?.economic_indicators || marketData?.economic_indicators || []
  
  // Handle sector data - it could be at data.sectors or just data array
  const sectors = sectorData?.data?.sectors || sectorData?.data || []
  
  // Handle breadth data - flatten if needed
  const breadthInfo = breadthData?.data || breadthData || {}
  
  // Handle sentiment history data
  const sentimentHistory = sentimentData?.data || sentimentData || {}

  // Prepare chart data for sectors - handle different field names
  const sectorChartData = sectors.slice(0, 8).map(sector => ({
    name: sector.sector?.substring(0, 15) || 'Other',
    performance: parseFloat(sector.avg_change_percent || sector.avg_change || sector.performance) || 0,
    marketCap: parseFloat(sector.sector_market_cap || sector.market_cap || sector.avg_market_cap) || 0,
    stocks: parseInt(sector.stock_count || sector.count) || 0,
    advanceDeclineRatio: parseFloat(sector.advance_decline_ratio) || 0
  }))

  // Prepare sentiment chart data for all indicators
  const fearGreedHistory = sentimentHistory.fear_greed_history || [];
  const naaimHistory = sentimentHistory.naaim_history || [];
  const aaiiHistory = sentimentHistory.aaii_history || [];

  // Merge by date for multi-line chart (assume all have 'date' or 'timestamp')
  const dateMap = {};
  fearGreedHistory.forEach(item => {
    const date = item.date || item.timestamp;
    if (!dateMap[date]) dateMap[date] = { date };
    dateMap[date].fear_greed = item.value;
    dateMap[date].fear_greed_text = item.value_text;
  });
  naaimHistory.forEach(item => {
    const date = item.date || item.timestamp;
    if (!dateMap[date]) dateMap[date] = { date };
    dateMap[date].naaim = item.mean_exposure || item.average;
  });
  aaiiHistory.forEach(item => {
    const date = item.date || item.timestamp;
    if (!dateMap[date]) dateMap[date] = { date };
    dateMap[date].aaii_bullish = item.bullish;
    dateMap[date].aaii_bearish = item.bearish;
    dateMap[date].aaii_neutral = item.neutral;
  });
  const sentimentChartData = Object.values(dateMap)
    .sort((a, b) => new Date(a.date) - new Date(b.date))
    .slice(-30);

  // Latest stats for summary cards
  const latestFG = fearGreedHistory[0] || {};
  const latestNAAIM = naaimHistory[0] || {};
  const latestAAII = aaiiHistory[0] || {};

  // --- Sentiment History Tab ---
  const SentimentHistoryPanel = () => (
    <Box>
      <Grid container spacing={2} mb={2}>
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="subtitle2" color="text.secondary">Fear & Greed Index</Typography>
              <Typography variant="h5" fontWeight={700} color={getChangeColor(latestFG.value)}>
                {latestFG.value ?? 'N/A'}
              </Typography>
              <Typography variant="body2">{latestFG.value_text || ''}</Typography>
              <Typography variant="caption" color="text.secondary">Measures market sentiment (0=Extreme Fear, 100=Extreme Greed)</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="subtitle2" color="text.secondary">NAAIM Exposure</Typography>
              <Typography variant="h5" fontWeight={700} color={getChangeColor(latestNAAIM.mean_exposure)}>
                {latestNAAIM.mean_exposure ?? latestNAAIM.average ?? 'N/A'}
              </Typography>
              <Typography variant="body2">Active manager equity exposure</Typography>
              <Typography variant="caption" color="text.secondary">0 = fully out, 100 = fully in</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="subtitle2" color="text.secondary">AAII Sentiment</Typography>
              <Typography variant="body2">Bullish: <b style={{color:'#10B981'}}>{latestAAII.bullish ?? 'N/A'}%</b> | Neutral: <b style={{color:'#8884d8'}}>{latestAAII.neutral ?? 'N/A'}%</b> | Bearish: <b style={{color:'#DC2626'}}>{latestAAII.bearish ?? 'N/A'}%</b></Typography>
              <Typography variant="caption" color="text.secondary">% of retail investors bullish, neutral, or bearish</Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
      <Card>
        <CardContent>
          <Typography variant="h6" mb={2}>Sentiment History (Last 30 Days)</Typography>
          <ResponsiveContainer width="100%" height={350}>
            <LineChart data={sentimentChartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} />
              <YAxis yAxisId="left" label={{ value: 'FG/NAAIM', angle: -90, position: 'insideLeft', fontSize: 12 }} />
              <YAxis yAxisId="right" orientation="right" label={{ value: 'AAII %', angle: 90, position: 'insideRight', fontSize: 12 }} />
              <RechartsTooltip formatter={(value, name) => [`${value}`, name]} />
              <Legend verticalAlign="top" height={36} />
              <Line yAxisId="left" type="monotone" dataKey="fear_greed" name="Fear & Greed" stroke="#FF8042" strokeWidth={2} dot={false} />
              <Line yAxisId="left" type="monotone" dataKey="naaim" name="NAAIM Exposure" stroke="#0088FE" strokeWidth={2} dot={false} />
              <Line yAxisId="right" type="monotone" dataKey="aaii_bullish" name="AAII Bullish" stroke="#10B981" strokeWidth={2} dot={false} />
              <Line yAxisId="right" type="monotone" dataKey="aaii_bearish" name="AAII Bearish" stroke="#DC2626" strokeWidth={2} dot={false} />
              <Line yAxisId="right" type="monotone" dataKey="aaii_neutral" name="AAII Neutral" stroke="#8884d8" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </Box>
  );

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      {/* Enhanced Header Section */}
      <Box sx={{ mb: 4 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} md={6}>
            <Typography variant="h3" component="h1" gutterBottom sx={{ 
              fontWeight: 800, 
              background: `linear-gradient(135deg, ${theme.palette.primary.main} 0%, ${theme.palette.secondary.main} 100%)`,
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              mb: 1
            }}>
              Market Overview
            </Typography>
            <Typography variant="subtitle1" color="text.secondary">
              Real-time market analysis, sentiment indicators, and institutional-grade research insights
            </Typography>
          </Grid>
          <Grid item xs={12} md={6}>
            <Stack direction="row" spacing={2} justifyContent={{ xs: 'flex-start', md: 'flex-end' }}>
              <ToggleButtonGroup
                value={timeframe}
                exclusive
                onChange={(e, val) => val && setTimeframe(val)}
                size="small"
                sx={{ bgcolor: 'background.paper', borderRadius: 2 }}
              >
                <ToggleButton value="1D">1D</ToggleButton>
                <ToggleButton value="1W">1W</ToggleButton>
                <ToggleButton value="1M">1M</ToggleButton>
                <ToggleButton value="3M">3M</ToggleButton>
                <ToggleButton value="1Y">1Y</ToggleButton>
              </ToggleButtonGroup>
              <IconButton 
                onClick={() => window.location.reload()}
                sx={{ 
                  bgcolor: 'background.paper',
                  '&:hover': { bgcolor: 'action.hover' }
                }}
              >
                <Refresh />
              </IconButton>
              <IconButton 
                onClick={() => setFullscreen(!fullscreen)}
                sx={{ 
                  bgcolor: 'background.paper',
                  '&:hover': { bgcolor: 'action.hover' }
                }}
              >
                {fullscreen ? <FullscreenExit /> : <Fullscreen />}
              </IconButton>
            </Stack>
          </Grid>
        </Grid>
        {marketLoading && (
          <Box sx={{ mt: 2 }}>
            <LinearProgress 
              sx={{ 
                borderRadius: 1,
                height: 6,
                bgcolor: alpha(theme.palette.primary.main, 0.1),
                '& .MuiLinearProgress-bar': {
                  borderRadius: 1,
                  background: `linear-gradient(90deg, ${theme.palette.primary.main} 0%, ${theme.palette.secondary.main} 100%)`
                }
              }} 
            />
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
              Fetching real-time market data...
            </Typography>
          </Box>
        )}
      </Box>

      {/* Enhanced Market Sentiment Indicators */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={4}>
          <AnimatedCard delay={0}>
            <GradientCard gradient="linear-gradient(135deg, #667eea 0%, #764ba2 100%)">
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
                  <Box>
                    <Typography variant="h6" sx={{ fontWeight: 600, color: 'inherit' }}>
                      Fear & Greed Index
                    </Typography>
                    <Typography variant="caption" sx={{ opacity: 0.8 }}>
                      Market Sentiment Indicator
                    </Typography>
                  </Box>
                  <Avatar sx={{ 
                    width: 48, 
                    height: 48, 
                    bgcolor: 'rgba(255,255,255,0.2)',
                    backdropFilter: 'blur(10px)'
                  }}>
                    <Psychology />
                  </Avatar>
                </Box>
                {sentimentIndicators.fear_greed ? (
                  <Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', mb: 3 }}>
                      <SentimentGauge 
                        value={sentimentIndicators.fear_greed.value || 0} 
                        label={sentimentIndicators.fear_greed.value_text || 'Unknown'}
                      />
                    </Box>
                    <Box sx={{ 
                      p: 2, 
                      bgcolor: 'rgba(255,255,255,0.1)', 
                      borderRadius: 2,
                      backdropFilter: 'blur(10px)'
                    }}>
                      <Grid container spacing={2}>
                        <Grid item xs={6}>
                          <Typography variant="caption" sx={{ opacity: 0.8 }}>Previous</Typography>
                          <Typography variant="body2" fontWeight={600}>
                            {sentimentIndicators.fear_greed.previous || 'N/A'}
                          </Typography>
                        </Grid>
                        <Grid item xs={6}>
                          <Typography variant="caption" sx={{ opacity: 0.8 }}>Change</Typography>
                          <Typography variant="body2" fontWeight={600}>
                            {sentimentIndicators.fear_greed.change || '0'}%
                          </Typography>
                        </Grid>
                      </Grid>
                    </Box>
                    <Typography variant="caption" sx={{ display: 'block', mt: 2, opacity: 0.7, textAlign: 'center' }}>
                      Updated: {sentimentIndicators.fear_greed.timestamp ? new Date(sentimentIndicators.fear_greed.timestamp).toLocaleString() : 'N/A'}
                    </Typography>
                  </Box>
                ) : (
                  <Box sx={{ textAlign: 'center', py: 4 }}>
                    <CircularProgress sx={{ color: 'rgba(255,255,255,0.5)' }} />
                    <Typography variant="body2" sx={{ mt: 2, opacity: 0.7 }}>
                      Loading sentiment data...
                    </Typography>
                  </Box>
                )}
              </CardContent>
            </GradientCard>
          </AnimatedCard>
        </Grid>
        <Grid item xs={12} md={4}>
          <AnimatedCard delay={1}>
            <GradientCard gradient="linear-gradient(135deg, #f093fb 0%, #f5576c 100%)">
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
                  <Box>
                    <Typography variant="h6" sx={{ fontWeight: 600, color: 'inherit' }}>
                      AAII Investor Sentiment
                    </Typography>
                    <Typography variant="caption" sx={{ opacity: 0.8 }}>
                      Retail Investor Survey
                    </Typography>
                  </Box>
                  <Avatar sx={{ 
                    width: 48, 
                    height: 48, 
                    bgcolor: 'rgba(255,255,255,0.2)',
                    backdropFilter: 'blur(10px)'
                  }}>
                    <Assessment />
                  </Avatar>
                </Box>
              {sentimentIndicators.aaii ? (
                <Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2, p: 1, bgcolor: 'rgba(255,255,255,0.1)', borderRadius: 1 }}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>Bullish:</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>
                      {sentimentIndicators.aaii.bullish !== undefined ? 
                        (typeof sentimentIndicators.aaii.bullish === 'number' && sentimentIndicators.aaii.bullish <= 1 ? 
                          (sentimentIndicators.aaii.bullish * 100).toFixed(1) + '%' : 
                          sentimentIndicators.aaii.bullish.toFixed(1) + '%'
                        ) : 'N/A'}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2, p: 1, bgcolor: 'rgba(255,255,255,0.1)', borderRadius: 1 }}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>Neutral:</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>
                      {sentimentIndicators.aaii.neutral !== undefined ? 
                        (typeof sentimentIndicators.aaii.neutral === 'number' && sentimentIndicators.aaii.neutral <= 1 ? 
                          (sentimentIndicators.aaii.neutral * 100).toFixed(1) + '%' : 
                          sentimentIndicators.aaii.neutral.toFixed(1) + '%'
                        ) : 'N/A'}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2, p: 1, bgcolor: 'rgba(255,255,255,0.1)', borderRadius: 1 }}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>Bearish:</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>
                      {sentimentIndicators.aaii.bearish !== undefined ? 
                        (typeof sentimentIndicators.aaii.bearish === 'number' && sentimentIndicators.aaii.bearish <= 1 ? 
                          (sentimentIndicators.aaii.bearish * 100).toFixed(1) + '%' : 
                          sentimentIndicators.aaii.bearish.toFixed(1) + '%'
                        ) : 'N/A'}
                    </Typography>
                  </Box>
                  <Typography variant="body2" sx={{ opacity: 0.9 }}>
                    Week ending: {sentimentIndicators.aaii.date ? new Date(sentimentIndicators.aaii.date).toLocaleDateString() : 'N/A'}
                  </Typography>
                </Box>
              ) : (
                <Box>
                  <Typography variant="body2" sx={{ opacity: 0.7 }}>No AAII data available</Typography>
                  <Typography variant="caption" sx={{ opacity: 0.6 }}>Sentiment indicators are loading...</Typography>
                </Box>
              )}
            </CardContent>
            </GradientCard>
          </AnimatedCard>
        </Grid>
        <Grid item xs={12} md={4}>
          <AnimatedCard delay={2}>
            <GradientCard gradient="linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)">
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
                  <Box>
                    <Typography variant="h6" sx={{ fontWeight: 600, color: 'inherit' }}>
                      NAAIM Exposure Index
                    </Typography>
                    <Typography variant="caption" sx={{ opacity: 0.8 }}>
                      Professional Manager Positioning
                    </Typography>
                  </Box>
                  <Avatar sx={{ 
                    width: 48, 
                    height: 48, 
                    bgcolor: 'rgba(255,255,255,0.2)',
                    backdropFilter: 'blur(10px)'
                  }}>
                    <AccountBalance />
                  </Avatar>
                </Box>
              {sentimentIndicators.naaim ? (
                <Box>
                  <Typography variant="h2" sx={{ mb: 2, fontWeight: 700 }}>
                    {sentimentIndicators.naaim.average !== undefined ? sentimentIndicators.naaim.average.toFixed(1) + '%' : 'N/A'}
                  </Typography>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1, p: 1, bgcolor: 'rgba(255,255,255,0.1)', borderRadius: 1 }}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>Bullish:</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>
                      {sentimentIndicators.naaim.bullish_8100 !== undefined ? sentimentIndicators.naaim.bullish_8100.toFixed(1) + '%' : 'N/A'}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2, p: 1, bgcolor: 'rgba(255,255,255,0.1)', borderRadius: 1 }}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>Bearish:</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>
                      {sentimentIndicators.naaim.bearish !== undefined ? sentimentIndicators.naaim.bearish.toFixed(1) + '%' : 'N/A'}
                    </Typography>
                  </Box>
                  <Typography variant="body2" sx={{ opacity: 0.9 }}>
                    Week ending: {sentimentIndicators.naaim.week_ending ? new Date(sentimentIndicators.naaim.week_ending).toLocaleDateString() : 'N/A'}
                  </Typography>
                </Box>
              ) : (
                <Box>
                  <Typography variant="h2" sx={{ mb: 1, fontWeight: 700, opacity: 0.5 }}>
                    --
                  </Typography>
                  <Typography variant="body2" sx={{ opacity: 0.7 }}>No NAAIM data available</Typography>
                </Box>
              )}
            </CardContent>
            </GradientCard>
          </AnimatedCard>
        </Grid>
      </Grid>

      {/* Enhanced Market Breadth Section */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={6}>
          <AnimatedCard delay={3}>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Market Breadth
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Box sx={{ textAlign: 'center', p: 2, backgroundColor: 'success.light', borderRadius: 1 }}>
                    <Typography variant="h4" color="success.contrastText">
                      {marketBreadth.advancing !== undefined && marketBreadth.advancing !== null ? parseInt(marketBreadth.advancing).toLocaleString() : 'N/A'}
                    </Typography>
                    <Typography variant="body2" color="success.contrastText">
                      Advancing
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={6}>
                  <Box sx={{ textAlign: 'center', p: 2, backgroundColor: 'error.light', borderRadius: 1 }}>
                    <Typography variant="h4" color="error.contrastText">
                      {marketBreadth.declining !== undefined && marketBreadth.declining !== null ? parseInt(marketBreadth.declining).toLocaleString() : 'N/A'}
                    </Typography>
                    <Typography variant="body2" color="error.contrastText">
                      Declining
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={12}>
                  <Box sx={{ textAlign: 'center', mt: 2 }}>
                    <Typography variant="body2" color="text.secondary">
                      Advance/Decline Ratio: {marketBreadth.advance_decline_ratio !== undefined ? marketBreadth.advance_decline_ratio : 'N/A'}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Average Change: {marketBreadth.average_change_percent !== undefined ? parseFloat(marketBreadth.average_change_percent).toFixed(2) : 'N/A'}%
                    </Typography>
                  </Box>
                </Grid>
              </Grid>
            </CardContent>
          </AnimatedCard>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Market Statistics
              </Typography>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                <Typography variant="body2">Total Stocks:</Typography>
                <Typography variant="body2" fontWeight="600">
                  {marketBreadth.total_stocks !== undefined ? parseInt(marketBreadth.total_stocks).toLocaleString() : 'N/A'}
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                <Typography variant="body2">Total Market Cap:</Typography>
                <Typography variant="body2" fontWeight="600">
                  {marketCap.total !== undefined ? formatCurrency(marketCap.total) : 'N/A'}
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                <Typography variant="body2">Unchanged:</Typography>
                <Typography variant="body2" fontWeight="600">
                  {marketBreadth.unchanged !== undefined ? parseInt(marketBreadth.unchanged).toLocaleString() : 'N/A'}
                </Typography>
              </Box>            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Enhanced Tabs Section */}
      <AnimatedCard delay={5}>
        <Box sx={{ borderBottom: 1, borderColor: 'divider', bgcolor: 'background.paper' }}>
          <Tabs 
            value={tabValue} 
            onChange={handleTabChange} 
            aria-label="market data tabs"
            variant="scrollable"
            scrollButtons="auto"
            sx={{
              '& .MuiTab-root': {
                minHeight: 56,
                fontWeight: 600,
                fontSize: '0.875rem',
                textTransform: 'none',
                '&.Mui-selected': {
                  color: theme.palette.primary.main,
                },
              },
              '& .MuiTabs-indicator': {
                height: 3,
                borderRadius: '3px 3px 0 0',
                background: `linear-gradient(90deg, ${theme.palette.primary.main} 0%, ${theme.palette.secondary.main} 100%)`
              }
            }}
          >
            <Tab label="Market Overview" icon={<ShowChart />} iconPosition="start" />
            <Tab label="Sentiment History" icon={<Timeline />} iconPosition="start" />
            <Tab label="Sector Performance" icon={<Business />} iconPosition="start" />
            <Tab label="Market Breadth" icon={<Equalizer />} iconPosition="start" />
            <Tab label="Economic Indicators" icon={<Public />} iconPosition="start" />
            <Tab label="Seasonality" icon={<CalendarToday />} iconPosition="start" />
            <Tab label="Research Indicators" icon={<Analytics />} iconPosition="start" />
          </Tabs>
        </Box>

        <TabPanel value={tabValue} index={0}>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                    Market Cap Distribution
                  </Typography>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2">Large Cap:</Typography>
                    <Typography variant="body2" fontWeight="600">
                      {formatCurrency(marketCap.large_cap)}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2">Mid Cap:</Typography>
                    <Typography variant="body2" fontWeight="600">
                      {formatCurrency(marketCap.mid_cap)}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2">Small Cap:</Typography>
                    <Typography variant="body2" fontWeight="600">
                      {formatCurrency(marketCap.small_cap)}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2">Total:</Typography>
                    <Typography variant="body2" fontWeight="600">
                      {formatCurrency(marketCap.total)}
                    </Typography>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                    Latest Economic Indicators
                  </Typography>
                  {economicIndicators.slice(0, 5).map((indicator, index) => (
                    <Box key={index} sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                      <Typography variant="body2">{indicator.name}:</Typography>
                      <Typography variant="body2" fontWeight="600">
                        {indicator.value} {indicator.unit}
                      </Typography>
                    </Box>
                  ))}
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </TabPanel>

        <TabPanel value={tabValue} index={1}>
          {sentimentLoading ? (
            <LinearProgress />
          ) : (
            <Box>
              {sentimentLoading ? (
                <LinearProgress />
              ) : (
                <SentimentHistoryPanel />
              )}
            </Box>
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={2}>
          {sectorLoading ? (
            <LinearProgress />
          ) : (
            <Grid container spacing={3}>
              <Grid item xs={12} md={8}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                      Sector Performance
                    </Typography>
                    <ResponsiveContainer width="100%" height={400}>
                      <BarChart data={sectorChartData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis 
                          dataKey="name" 
                          angle={-45}
                          textAnchor="end"
                          height={80}
                        />
                        <YAxis />
                        <RechartsTooltip 
                          formatter={(value, name) => [
                            `${value.toFixed(2)}%`,
                            'Performance'
                          ]}
                        />
                        <Bar dataKey="performance" fill="#8884d8" />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={4}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                      Sector Details
                    </Typography>
                    <TableContainer>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Sector</TableCell>
                            <TableCell align="right">Change %</TableCell>
                            <TableCell align="right">Stocks</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {sectors.slice(0, 8).map((sector, index) => {
                            const changePercent = parseFloat(sector.avg_change_percent || sector.avg_change || sector.performance) || 0
                            return (
                              <TableRow key={index}>
                                <TableCell>{sector.sector?.substring(0, 12) || 'N/A'}</TableCell>
                                <TableCell 
                                  align="right"
                                  sx={{ 
                                    color: getChangeColor(changePercent),
                                    fontWeight: 600
                                  }}
                                >
                                  {formatPercentage(changePercent)}
                                </TableCell>
                                <TableCell align="right">
                                  {sector.stock_count || sector.count || 0}
                                </TableCell>
                              </TableRow>
                            )
                          })}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={3}>
          {breadthLoading ? (
            <LinearProgress />
          ) : (
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                      Market Breadth Details
                    </Typography>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                      <Typography variant="body2">Advancing Stocks:</Typography>
                      <Typography variant="body2" color="success.main" fontWeight="600">
                        {breadthInfo.advancing || 0}
                      </Typography>
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                      <Typography variant="body2">Declining Stocks:</Typography>
                      <Typography variant="body2" color="error.main" fontWeight="600">
                        {breadthInfo.declining || 0}
                      </Typography>
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                      <Typography variant="body2">Unchanged:</Typography>
                      <Typography variant="body2" fontWeight="600">
                        {breadthInfo.unchanged || 0}
                      </Typography>
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                      <Typography variant="body2">A/D Ratio:</Typography>
                      <Typography variant="body2" fontWeight="600">
                        {breadthInfo.advance_decline_ratio || 'N/A'}
                      </Typography>
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                      <Typography variant="body2">Average Change:</Typography>
                      <Typography 
                        variant="body2" 
                        fontWeight="600"
                        sx={{ color: getChangeColor(parseFloat(breadthInfo.average_change_percent) || 0) }}
                      >
                        {formatPercentage(parseFloat(breadthInfo.average_change_percent) || 0)}
                      </Typography>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                      Breadth Visualization
                    </Typography>
                    <ResponsiveContainer width="100%" height={300}>
                      <PieChart>
                        <Pie
                          data={[
                            { name: 'Advancing', value: breadthInfo.advancing || 0, color: '#4CAF50' },
                            { name: 'Declining', value: breadthInfo.declining || 0, color: '#F44336' },
                            { name: 'Unchanged', value: breadthInfo.unchanged || 0, color: '#9E9E9E' }
                          ]}
                          cx="50%"
                          cy="50%"
                          outerRadius={80}
                          dataKey="value"
                          label={({ name, value }) => `${name}: ${value}`}
                        >
                          <Cell fill="#4CAF50" />
                          <Cell fill="#F44336" />
                          <Cell fill="#9E9E9E" />
                        </Pie>
                        <RechartsTooltip />
                      </PieChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={4}>
          {economicLoading ? (
            <LinearProgress />
          ) : (
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                      Economic Indicators (Last 90 Days)
                    </Typography>
                    <TableContainer>
                      <Table>
                        <TableHead>
                          <TableRow sx={{ backgroundColor: 'grey.50' }}>
                            <TableCell sx={{ fontWeight: 600 }}>Indicator</TableCell>
                            <TableCell align="right" sx={{ fontWeight: 600 }}>Current Value</TableCell>
                            <TableCell align="right" sx={{ fontWeight: 600 }}>Previous Value</TableCell>
                            <TableCell align="right" sx={{ fontWeight: 600 }}>Change</TableCell>
                            <TableCell align="right" sx={{ fontWeight: 600 }}>Date</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {(() => {
                            // Handle different data structures for economic indicators
                            let indicators = []
                            if (economicData?.data && Array.isArray(economicData.data)) {
                              indicators = economicData.data.slice(0, 10)
                            } else if (economicData?.data && typeof economicData.data === 'object') {
                              // If data is grouped by indicator name
                              indicators = Object.entries(economicData.data).flatMap(([name, values]) => 
                                Array.isArray(values) ? values.slice(0, 2).map(v => ({...v, name})) : [{...values, name}]
                              ).slice(0, 10)
                            } else if (Array.isArray(economicData)) {
                              indicators = economicData.slice(0, 10)
                            }
                            
                            return indicators.map((indicator, index) => (
                              <TableRow key={index} hover>
                                <TableCell>{indicator.name || indicator.indicator_name || 'N/A'}</TableCell>
                                <TableCell align="right">
                                  {indicator.value} {indicator.unit}
                                </TableCell>
                                <TableCell align="right">
                                  {indicator.previous_value || 'N/A'} {indicator.unit}
                                </TableCell>
                                <TableCell 
                                  align="right"
                                  sx={{ 
                                    color: getChangeColor(parseFloat(indicator.change_percent) || 0),
                                    fontWeight: 600
                                  }}
                                >
                                  {indicator.change_percent ? formatPercentage(parseFloat(indicator.change_percent)) : 'N/A'}
                                </TableCell>
                                <TableCell align="right">
                                  {indicator.timestamp || indicator.date ? new Date(indicator.timestamp || indicator.date).toLocaleDateString() : 'N/A'}
                                </TableCell>
                              </TableRow>
                            ))
                          })()}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={5}>
          {seasonalityLoading ? (
            <LinearProgress />
          ) : (
            <Grid container spacing={3}>
              {seasonalityData?.data && (
                <>
                  {/* Current Seasonal Position Summary */}
                  <Grid item xs={12}>
                    <Card sx={{ border: '2px solid', borderColor: 'primary.main' }}>
                      <CardContent>
                        <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Current Seasonal Position
                        </Typography>
                        <Grid container spacing={3}>
                          <Grid item xs={12} md={4}>
                            <Box sx={{ textAlign: 'center', p: 2, backgroundColor: 'info.light', borderRadius: 1 }}>
                              <Typography variant="h4" color="info.contrastText">
                                {seasonalityData.data.currentPosition.seasonalScore}/100
                              </Typography>
                              <Typography variant="body2" color="info.contrastText">
                                Seasonal Score
                              </Typography>
                              <Typography variant="caption" color="info.contrastText">
                                {seasonalityData.data.summary.overallSeasonalBias}
                              </Typography>
                            </Box>
                          </Grid>
                          <Grid item xs={12} md={4}>
                            <Box sx={{ textAlign: 'center', p: 2, backgroundColor: 'secondary.light', borderRadius: 1 }}>
                              <Typography variant="h6" color="secondary.contrastText">
                                {seasonalityData.data.currentPosition.presidentialCycle}
                              </Typography>
                              <Typography variant="body2" color="secondary.contrastText">
                                Presidential Cycle
                              </Typography>
                            </Box>
                          </Grid>
                          <Grid item xs={12} md={4}>
                            <Box sx={{ textAlign: 'center', p: 2, backgroundColor: 'warning.light', borderRadius: 1 }}>
                              <Typography variant="h6" color="warning.contrastText">
                                {seasonalityData.data.currentPosition.nextMajorEvent?.name}
                              </Typography>
                              <Typography variant="body2" color="warning.contrastText">
                                Next Event ({seasonalityData.data.currentPosition.nextMajorEvent?.daysAway} days)
                              </Typography>
                            </Box>
                          </Grid>
                        </Grid>
                        <Box sx={{ mt: 3 }}>
                          <Typography variant="body1" sx={{ mb: 1 }}>
                            <strong>Recommendation:</strong> {seasonalityData.data.summary.recommendation}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            Active Periods: {seasonalityData.data.currentPosition.activePeriods?.join(', ')}
                          </Typography>
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Monthly Seasonality */}
                  <Grid item xs={12} md={6}>
                    <Card>
                      <CardContent>
                        <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Monthly Seasonality Pattern
                        </Typography>
                        <ResponsiveContainer width="100%" height={300}>
                          <BarChart data={seasonalityData.data.monthlySeasonality}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="name" angle={-45} textAnchor="end" height={80} />
                            <YAxis label={{ value: 'Avg Return %', angle: -90, position: 'insideLeft' }} />
                            <RechartsTooltip formatter={(value) => [`${value.toFixed(1)}%`, 'Average Return']} />
                            <Bar 
                              dataKey="avgReturn" 
                              fill={(entry) => entry?.isCurrent ? '#82ca9d' : '#8884d8'}
                              name="Monthly Average"
                            />
                          </BarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Quarterly Patterns */}
                  <Grid item xs={12} md={6}>
                    <Card>
                      <CardContent>
                        <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Quarterly Performance
                        </Typography>
                        <ResponsiveContainer width="100%" height={300}>
                          <BarChart data={seasonalityData.data.quarterlySeasonality}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="name" />
                            <YAxis label={{ value: 'Avg Return %', angle: -90, position: 'insideLeft' }} />
                            <RechartsTooltip 
                              formatter={(value, name, props) => [`${value.toFixed(1)}%`, 'Average Return']}
                              labelFormatter={(label, payload) => {
                                const data = payload[0]?.payload;
                                return `${label} (${data?.months})`;
                              }}
                            />
                            <Bar 
                              dataKey="avgReturn" 
                              fill="#8884d8"
                              name="Quarterly Average"
                            />
                          </BarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Presidential Cycle Details */}
                  <Grid item xs={12} md={6}>
                    <Card>
                      <CardContent>
                        <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Presidential Cycle (4-Year Pattern)
                        </Typography>
                        <TableContainer>
                          <Table size="small">
                            <TableHead>
                              <TableRow>
                                <TableCell>Year</TableCell>
                                <TableCell>Phase</TableCell>
                                <TableCell align="right">Avg Return</TableCell>
                                <TableCell align="center">Status</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {seasonalityData.data.presidentialCycle.data.map((cycle) => (
                                <TableRow key={cycle.year} sx={{ backgroundColor: cycle.isCurrent ? 'primary.light' : 'inherit' }}>
                                  <TableCell>Year {cycle.year}</TableCell>
                                  <TableCell>{cycle.label}</TableCell>
                                  <TableCell align="right">{formatPercentage(cycle.avgReturn)}</TableCell>
                                  <TableCell align="center">
                                    {cycle.isCurrent && <Chip label="CURRENT" color="primary" size="small" />}
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </TableContainer>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Day of Week Effects */}
                  <Grid item xs={12} md={6}>
                    <Card>
                      <CardContent>
                        <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Day of Week Effects
                        </Typography>
                        {seasonalityData.data.dayOfWeekEffects.map((day) => (
                          <Box key={day.day} sx={{ 
                            display: 'flex', 
                            justifyContent: 'space-between', 
                            mb: 1,
                            p: 1,
                            backgroundColor: day.isCurrent ? 'primary.light' : 'inherit',
                            borderRadius: 1
                          }}>
                            <Typography variant="body2" fontWeight={day.isCurrent ? 600 : 400}>
                              {day.day}
                            </Typography>
                            <Typography 
                              variant="body2" 
                              sx={{ color: getChangeColor(day.avgReturn * 100) }}
                              fontWeight={600}
                            >
                              {formatPercentage(day.avgReturn)}
                            </Typography>
                          </Box>
                        ))}
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Seasonal Anomalies */}
                  <Grid item xs={12}>
                    <Card>
                      <CardContent>
                        <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Seasonal Anomalies & Effects
                        </Typography>
                        <Grid container spacing={2}>
                          {seasonalityData.data.seasonalAnomalies.map((anomaly, index) => (
                            <Grid item xs={12} sm={6} md={3} key={index}>
                              <Box sx={{ 
                                p: 2, 
                                border: 1, 
                                borderColor: 'divider', 
                                borderRadius: 1,
                                height: '100%'
                              }}>
                                <Typography variant="subtitle2" fontWeight={600}>
                                  {anomaly.name}
                                </Typography>
                                <Typography variant="caption" color="text.secondary" display="block">
                                  {anomaly.period}
                                </Typography>
                                <Typography variant="body2" sx={{ mt: 1, mb: 1 }}>
                                  {anomaly.description}
                                </Typography>
                                <Chip 
                                  label={anomaly.strength}
                                  size="small"
                                  color={
                                    anomaly.strength === 'Strong' ? 'error' :
                                    anomaly.strength === 'Moderate' ? 'warning' : 'default'
                                  }
                                />
                              </Box>
                            </Grid>
                          ))}
                        </Grid>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Holiday Effects */}
                  <Grid item xs={12} md={6}>
                    <Card>
                      <CardContent>
                        <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Holiday Effects
                        </Typography>
                        <TableContainer>
                          <Table size="small">
                            <TableHead>
                              <TableRow>
                                <TableCell>Holiday</TableCell>
                                <TableCell>Dates</TableCell>
                                <TableCell align="right">Effect</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {seasonalityData.data.holidayEffects.map((holiday, index) => (
                                <TableRow key={index}>
                                  <TableCell>{holiday.holiday}</TableCell>
                                  <TableCell>{holiday.dates}</TableCell>
                                  <TableCell align="right" sx={{ 
                                    color: getChangeColor(parseFloat(holiday.effect.replace('%', ''))),
                                    fontWeight: 600
                                  }}>
                                    {holiday.effect}
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </TableContainer>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Sector Seasonality */}
                  <Grid item xs={12} md={6}>
                    <Card>
                      <CardContent>
                        <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Sector Seasonality
                        </Typography>
                        {seasonalityData.data.sectorSeasonality.map((sector, index) => (
                          <Box key={index} sx={{ mb: 2 }}>
                            <Typography variant="subtitle2" fontWeight={600}>
                              {sector.sector}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              Best: {sector.bestMonths.map(m => new Date(0, m-1).toLocaleString('default', {month:'short'})).join(', ')}
                            </Typography>
                            <Typography variant="caption" color="text.secondary" display="block">
                              Worst: {sector.worstMonths.map(m => new Date(0, m-1).toLocaleString('default', {month:'short'})).join(', ')}
                            </Typography>
                            <Typography variant="body2" sx={{ mt: 0.5 }}>
                              {sector.rationale}
                            </Typography>
                          </Box>
                        ))}
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Summary & Outlook */}
                  <Grid item xs={12}>
                    <Card>
                      <CardContent>
                        <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Seasonal Outlook Summary
                        </Typography>
                        <Grid container spacing={3}>
                          <Grid item xs={12} md={6}>
                            <Typography variant="body2" fontWeight={600} color="success.main" sx={{ mb: 1 }}>
                              Favorable Factors:
                            </Typography>
                            {seasonalityData.data.summary.favorableFactors?.map((factor, index) => (
                              <Typography key={index} variant="body2" sx={{ ml: 2, mb: 0.5 }}>
                                • {factor}
                              </Typography>
                            ))}
                          </Grid>
                          <Grid item xs={12} md={6}>
                            <Typography variant="body2" fontWeight={600} color="error.main" sx={{ mb: 1 }}>
                              Unfavorable Factors:
                            </Typography>
                            {seasonalityData.data.summary.unfavorableFactors?.map((factor, index) => (
                              <Typography key={index} variant="body2" sx={{ ml: 2, mb: 0.5 }}>
                                • {factor}
                              </Typography>
                            ))}
                          </Grid>
                        </Grid>
                      </CardContent>
                    </Card>
                  </Grid>
                </>
              )}
            </Grid>
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={6}>
          {researchLoading ? (
            <LinearProgress />
          ) : (
            <Grid container spacing={3}>
              {researchData?.data && (
                <>
                  {/* Market Summary */}
                  <Grid item xs={12}>
                    <Card>
                      <CardContent>
                        <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Market Research Summary
                        </Typography>
                        <Grid container spacing={3}>
                          <Grid item xs={12} md={4}>
                            <Box sx={{ textAlign: 'center', p: 2, backgroundColor: 'info.light', borderRadius: 1 }}>
                              <Typography variant="h6" color="info.contrastText">
                                {researchData.data.summary.overallSentiment}
                              </Typography>
                              <Typography variant="body2" color="info.contrastText">
                                Overall Market Sentiment
                              </Typography>
                            </Box>
                          </Grid>
                          <Grid item xs={12} md={4}>
                            <Box sx={{ textAlign: 'center', p: 2, backgroundColor: 'secondary.light', borderRadius: 1 }}>
                              <Typography variant="h6" color="secondary.contrastText">
                                {researchData.data.summary.marketRegime}
                              </Typography>
                              <Typography variant="body2" color="secondary.contrastText">
                                Market Regime
                              </Typography>
                            </Box>
                          </Grid>
                          <Grid item xs={12} md={4}>
                            <Box sx={{ textAlign: 'center', p: 2, backgroundColor: 'warning.light', borderRadius: 1 }}>
                              <Typography variant="h6" color="warning.contrastText">
                                {researchData.data.summary.timeHorizon}
                              </Typography>
                              <Typography variant="body2" color="warning.contrastText">
                                Investment Time Horizon
                              </Typography>
                            </Box>
                          </Grid>
                        </Grid>
                        <Box sx={{ mt: 3 }}>
                          <Typography variant="body1" sx={{ mb: 1 }}>
                            <strong>Recommendation:</strong> {researchData.data.summary.recommendation}
                          </Typography>
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Volatility & Sentiment Indicators */}
                  <Grid item xs={12} md={6}>
                    <Card>
                      <CardContent>
                        <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Volatility & Sentiment
                        </Typography>
                        <Grid container spacing={2}>
                          <Grid item xs={12}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                              <Typography variant="body2">VIX (Fear Index):</Typography>
                              <Box>
                                <Typography variant="body2" fontWeight={600} display="inline">
                                  {researchData.data.volatility.vix.toFixed(1)}
                                </Typography>
                                <Chip 
                                  label={researchData.data.volatility.vixInterpretation.level}
                                  color={researchData.data.volatility.vixInterpretation.color}
                                  size="small"
                                  sx={{ ml: 1 }}
                                />
                              </Box>
                            </Box>
                            <Typography variant="caption" color="text.secondary">
                              30-day avg: {researchData.data.volatility.vixAverage.toFixed(1)} | {researchData.data.volatility.vixInterpretation.sentiment}
                            </Typography>
                          </Grid>
                          <Grid item xs={12}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                              <Typography variant="body2">Put/Call Ratio:</Typography>
                              <Box>
                                <Typography variant="body2" fontWeight={600} display="inline">
                                  {researchData.data.sentiment.putCallRatio.toFixed(2)}
                                </Typography>
                                <Chip 
                                  label={researchData.data.sentiment.putCallInterpretation.sentiment}
                                  color={researchData.data.sentiment.putCallInterpretation.color}
                                  size="small"
                                  sx={{ ml: 1 }}
                                />
                              </Box>
                            </Box>
                            <Typography variant="caption" color="text.secondary">
                              10-day avg: {researchData.data.sentiment.putCallAverage.toFixed(2)} | {researchData.data.sentiment.putCallInterpretation.signal}
                            </Typography>
                          </Grid>
                        </Grid>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Technical Levels */}
                  <Grid item xs={12} md={6}>
                    <Card>
                      <CardContent>
                        <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Major Index Technical Levels
                        </Typography>
                        {Object.entries(researchData.data.technicalLevels).map(([index, data]) => (
                          <Box key={index} sx={{ mb: 2 }}>
                            <Typography variant="body2" fontWeight={600}>{index}</Typography>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                              <Typography variant="caption">Current:</Typography>
                              <Typography variant="caption">{data.current.toFixed(0)}</Typography>
                            </Box>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                              <Typography variant="caption">Trend:</Typography>
                              <Typography variant="caption" sx={{ color: getChangeColor(data.trend === 'Bullish' ? 1 : data.trend === 'Bearish' ? -1 : 0) }}>
                                {data.trend}
                              </Typography>
                            </Box>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                              <Typography variant="caption">RSI:</Typography>
                              <Typography variant="caption">{data.rsi.toFixed(1)}</Typography>
                            </Box>
                          </Box>
                        ))}
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Sector Rotation */}
                  <Grid item xs={12}>
                    <Card>
                      <CardContent>
                        <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Sector Rotation Analysis
                        </Typography>
                        <TableContainer>
                          <Table>
                            <TableHead>
                              <TableRow sx={{ backgroundColor: 'grey.50' }}>
                                <TableCell sx={{ fontWeight: 600 }}>Sector</TableCell>
                                <TableCell sx={{ fontWeight: 600 }}>Momentum</TableCell>
                                <TableCell sx={{ fontWeight: 600 }}>Money Flow</TableCell>
                                <TableCell align="right" sx={{ fontWeight: 600 }}>Performance</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {researchData.data.sectorRotation.map((sector, index) => (
                                <TableRow key={index} hover>
                                  <TableCell>{sector.sector}</TableCell>
                                  <TableCell>
                                    <Chip 
                                      label={sector.momentum}
                                      color={sector.momentum === 'Strong' ? 'success' : sector.momentum === 'Moderate' ? 'info' : 'warning'}
                                      size="small"
                                    />
                                  </TableCell>
                                  <TableCell>
                                    <Chip 
                                      label={sector.flow}
                                      color={sector.flow === 'Inflow' ? 'success' : sector.flow === 'Outflow' ? 'error' : 'default'}
                                      size="small"
                                    />
                                  </TableCell>
                                  <TableCell 
                                    align="right"
                                    sx={{ 
                                      color: getChangeColor(sector.performance),
                                      fontWeight: 600
                                    }}
                                  >
                                    {formatPercentage(sector.performance)}
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </TableContainer>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Economic Calendar */}
                  <Grid item xs={12} md={6}>
                    <Card>
                      <CardContent>
                        <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Upcoming Economic Events
                        </Typography>
                        {researchData.data.economicCalendar.map((event, index) => (
                          <Box key={index} sx={{ mb: 2, p: 2, backgroundColor: 'grey.50', borderRadius: 1 }}>
                            <Typography variant="body2" fontWeight={600}>{event.event}</Typography>
                            <Typography variant="caption" color="text.secondary">
                              {new Date(event.date).toLocaleDateString()} | Expected: {event.expected}
                            </Typography>
                            <Box sx={{ mt: 0.5 }}>
                              <Chip 
                                label={event.importance}
                                color={event.importance === 'High' ? 'error' : 'warning'}
                                size="small"
                              />
                              <Chip 
                                label={event.impact}
                                color="info"
                                size="small"
                                sx={{ ml: 1 }}
                              />
                            </Box>
                          </Box>
                        ))}
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Key Risks & Opportunities */}
                  <Grid item xs={12} md={6}>
                    <Card>
                      <CardContent>
                        <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Key Risks & Opportunities
                        </Typography>
                        <Box sx={{ mb: 3 }}>
                          <Typography variant="body2" fontWeight={600} color="error.main" sx={{ mb: 1 }}>
                            Key Risks:
                          </Typography>
                          {researchData.data.summary.keyRisks.map((risk, index) => (
                            <Typography key={index} variant="body2" sx={{ ml: 2, mb: 0.5 }}>
                              • {risk}
                            </Typography>
                          ))}
                        </Box>
                        <Box>
                          <Typography variant="body2" fontWeight={600} color="success.main" sx={{ mb: 1 }}>
                            Key Opportunities:
                          </Typography>
                          {researchData.data.summary.keyOpportunities.map((opportunity, index) => (
                            <Typography key={index} variant="body2" sx={{ ml: 2, mb: 0.5 }}>
                              • {opportunity}
                            </Typography>
                          ))}
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>
                </>
              )}
            </Grid>
          )}
        </TabPanel>
      </AnimatedCard>
    </Box>
  )
}

export default MarketOverview