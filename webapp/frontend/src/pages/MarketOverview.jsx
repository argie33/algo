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
  return (
    <Zoom in={true} timeout={300 + delay * 100}>
      <div className="bg-white shadow-md rounded-lg"
        {...props}
        sx={{
          background: '#ffffff',
          backdropFilter: 'blur(10px)',
          border: '1px solid #1976d21A',
          transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          '&:hover': {
            transform: 'translateY(-4px)',
            boxShadow: '0px 12px 17px 2px rgba(0,0,0,0.14), 0px 5px 22px 4px rgba(0,0,0,0.12), 0px 7px 8px -4px rgba(0,0,0,0.2)',
            border: '1px solid #1976d233',
          },
          ...props.sx
        }}
      >
        {children}
      </div>
    </Zoom>
  )
}

const GradientCard = ({ children, gradient, ...props }) => {
  return (
    <div className="bg-white shadow-md rounded-lg"
      {...props}
      sx={{
        background: gradient || 'linear-gradient(135deg, #1976d2 0%, #9c27b0 100%)',
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
    </div>
  )
}

const MetricCard = ({ title, value, subtitle, icon, trend, color = 'primary', gradient }) => {
  const isPositive = trend > 0
  
  return (
    <GradientCard gradient={gradient}>
      <div className="bg-white shadow-md rounded-lg"Content>
        <div  sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <div  sx={{ flex: 1 }}>
            <div  variant="subtitle2" sx={{ opacity: 0.9, fontWeight: 500 }}>
              {title}
            </div>
            <div  variant="h3" sx={{ my: 1, fontWeight: 700 }}>
              {value}
            </div>
            {subtitle && (
              <div  variant="body2" sx={{ opacity: 0.8 }}>
                {subtitle}
              </div>
            )}
            {trend !== undefined && (
              <div  sx={{ display: 'flex', alignItems: 'center', mt: 1 }}>
                {isPositive ? <TrendingUp fontSize="small" /> : <TrendingDown fontSize="small" />}
                <div  variant="body2" sx={{ ml: 0.5, fontWeight: 600 }}>
                  {Math.abs(trend)}%
                </div>
              </div>
            )}
          </div>
          {icon && (
            <div 
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
            </div>
          )}
        </div>
      </div>
    </GradientCard>
  )
}

const SentimentGauge = ({ value, label, max = 100, size = 120 }) => {
  const percentage = (value / max) * 100
  const rotation = (percentage * 180) / 100 - 90
  
  const getColor = () => {
    if (percentage <= 20) return '#f44336'
    if (percentage <= 40) return '#ff9800'
    if (percentage <= 60) return '#2196f3'
    if (percentage <= 80) return '#81c784'
    return '#4caf50'
  }
  
  return (
    <div  sx={{ position: 'relative', width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={(size - 20) / 2}
          stroke="rgba(0, 0, 0, 0.12)"
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
      <div 
        sx={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          textAlign: 'center'
        }}
      >
        <div  variant="h4" sx={{ fontWeight: 700, color: getColor() }}>
          {value}
        </div>
        <div  variant="caption" color="text.secondary">
          {label}
        </div>
      </div>
    </div>
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
      <div  sx={{ pt: 3 }}>
        {children}
      </div>
    )}
  </div>
)

const MetricTable = ({ data, columns, title }) => (
  <div className="bg-white shadow-md rounded-lg">
    <div className="bg-white shadow-md rounded-lg"Content>
      <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
        {title}
      </div>
      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} elevation={0}>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow sx={{ backgroundColor: 'grey.50' }}>
              {columns.map((col) => (
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell key={col.key} sx={{ fontWeight: 600 }}>
                  {col.label}
                </td>
              ))}
            </tr>
          </thead>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
            {data?.slice(0, 10).map((item, index) => (
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={item.ticker || index} hover>
                {columns.map((col) => (
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell key={col.key}>
                    {col.render ? col.render(item[col.key], item) : item[col.key] || 'N/A'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  </div>
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
      <div>
        <div  variant="h4" sx={{ mb: 3, fontWeight: 600 }}>
          Market Overview
        </div>
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 3 }}>
          Failed to load market data. Please check your data sources and try again.
          <br /><small>Technical details: {marketError?.message || 'Unknown error'}</small>
                      <br /><small>Debug endpoint: <code>API service endpoint</code></small>
        </div>
      </div>
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
    <div>
      <div className="grid" container spacing={2} mb={2}>
        <div className="grid" item xs={12} md={4}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="subtitle2" color="text.secondary">Fear & Greed Index</div>
              <div  variant="h5" fontWeight={700} color={getChangeColor(latestFG.value)}>
                {latestFG.value ?? 'N/A'}
              </div>
              <div  variant="body2">{latestFG.value_text || ''}</div>
              <div  variant="caption" color="text.secondary">Measures market sentiment (0=Extreme Fear, 100=Extreme Greed)</div>
            </div>
          </div>
        </div>
        <div className="grid" item xs={12} md={4}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="subtitle2" color="text.secondary">NAAIM Exposure</div>
              <div  variant="h5" fontWeight={700} color={getChangeColor(latestNAAIM.mean_exposure)}>
                {latestNAAIM.mean_exposure ?? latestNAAIM.average ?? 'N/A'}
              </div>
              <div  variant="body2">Active manager equity exposure</div>
              <div  variant="caption" color="text.secondary">0 = fully out, 100 = fully in</div>
            </div>
          </div>
        </div>
        <div className="grid" item xs={12} md={4}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="subtitle2" color="text.secondary">AAII Sentiment</div>
              <div  variant="body2">Bullish: <b style={{color:'#10B981'}}>{latestAAII.bullish ?? 'N/A'}%</b> | Neutral: <b style={{color:'#8884d8'}}>{latestAAII.neutral ?? 'N/A'}%</b> | Bearish: <b style={{color:'#DC2626'}}>{latestAAII.bearish ?? 'N/A'}%</b></div>
              <div  variant="caption" color="text.secondary">% of retail investors bullish, neutral, or bearish</div>
            </div>
          </div>
        </div>
      </div>
      <div className="bg-white shadow-md rounded-lg">
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  variant="h6" mb={2}>Sentiment History (Last 30 Days)</div>
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
        </div>
      </div>
    </div>
  );

  return (
    <div  sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      {/* Enhanced Header Section */}
      <div  sx={{ mb: 4 }}>
        <div className="grid" container spacing={2} alignItems="center">
          <div className="grid" item xs={12} md={6}>
            <div  variant="h3" component="h1" gutterBottom sx={{ 
              fontWeight: 800, 
              background: 'linear-gradient(135deg, #1976d2 0%, #9c27b0 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              mb: 1
            }}>
              Market Overview
            </div>
            <div  variant="subtitle1" color="text.secondary">
              Real-time market analysis, sentiment indicators, and institutional-grade research insights
            </div>
          </div>
          <div className="grid" item xs={12} md={6}>
            <div className="flex flex-col space-y-2" direction="row" spacing={2} justifyContent={{ xs: 'flex-start', md: 'flex-end' }}>
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
              <button className="p-2 rounded-full hover:bg-gray-100" 
                onClick={() => window.location.reload()}
                sx={{ 
                  bgcolor: 'background.paper',
                  '&:hover': { bgcolor: 'action.hover' }
                }}
              >
                <Refresh />
              </button>
              <button className="p-2 rounded-full hover:bg-gray-100" 
                onClick={() => setFullscreen(!fullscreen)}
                sx={{ 
                  bgcolor: 'background.paper',
                  '&:hover': { bgcolor: 'action.hover' }
                }}
              >
                {fullscreen ? <FullscreenExit /> : <Fullscreen />}
              </button>
            </div>
          </div>
        </div>
        {marketLoading && (
          <div  sx={{ mt: 2 }}>
            <div className="w-full bg-gray-200 rounded-full h-2" 
              sx={{ 
                borderRadius: 1,
                height: 6,
                bgcolor: '#1976d21A',
                '& .MuiLinearProgress-bar': {
                  borderRadius: 1,
                  background: 'linear-gradient(90deg, #1976d2 0%, #9c27b0 100%)'
                }
              }} 
            />
            <div  variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
              Fetching real-time market data...
            </div>
          </div>
        )}
      </div>

      {/* Enhanced Market Sentiment Indicators */}
      <div className="grid" container spacing={3} sx={{ mb: 4 }}>
        <div className="grid" item xs={12} md={4}>
          <AnimatedCard delay={0}>
            <GradientCard gradient="linear-gradient(135deg, #667eea 0%, #764ba2 100%)">
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
                  <div>
                    <div  variant="h6" sx={{ fontWeight: 600, color: 'inherit' }}>
                      Fear & Greed Index
                    </div>
                    <div  variant="caption" sx={{ opacity: 0.8 }}>
                      Market Sentiment Indicator
                    </div>
                  </div>
                  <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ 
                    width: 48, 
                    height: 48, 
                    bgcolor: 'rgba(255,255,255,0.2)',
                    backdropFilter: 'blur(10px)'
                  }}>
                    <Psychology />
                  </div>
                </div>
                {sentimentIndicators.fear_greed ? (
                  <div>
                    <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', mb: 3 }}>
                      <SentimentGauge 
                        value={sentimentIndicators.fear_greed.value || 0} 
                        label={sentimentIndicators.fear_greed.value_text || 'Unknown'}
                      />
                    </div>
                    <div  sx={{ 
                      p: 2, 
                      bgcolor: 'rgba(255,255,255,0.1)', 
                      borderRadius: 2,
                      backdropFilter: 'blur(10px)'
                    }}>
                      <div className="grid" container spacing={2}>
                        <div className="grid" item xs={6}>
                          <div  variant="caption" sx={{ opacity: 0.8 }}>Previous</div>
                          <div  variant="body2" fontWeight={600}>
                            {sentimentIndicators.fear_greed.previous || 'N/A'}
                          </div>
                        </div>
                        <div className="grid" item xs={6}>
                          <div  variant="caption" sx={{ opacity: 0.8 }}>Change</div>
                          <div  variant="body2" fontWeight={600}>
                            {sentimentIndicators.fear_greed.change || '0'}%
                          </div>
                        </div>
                      </div>
                    </div>
                    <div  variant="caption" sx={{ display: 'block', mt: 2, opacity: 0.7, textAlign: 'center' }}>
                      Updated: {sentimentIndicators.fear_greed.timestamp ? new Date(sentimentIndicators.fear_greed.timestamp).toLocaleString() : 'N/A'}
                    </div>
                  </div>
                ) : (
                  <div  sx={{ textAlign: 'center', py: 4 }}>
                    <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" sx={{ color: 'rgba(255,255,255,0.5)' }} />
                    <div  variant="body2" sx={{ mt: 2, opacity: 0.7 }}>
                      Loading sentiment data...
                    </div>
                  </div>
                )}
              </div>
            </GradientCard>
          </AnimatedCard>
        </div>
        <div className="grid" item xs={12} md={4}>
          <AnimatedCard delay={1}>
            <GradientCard gradient="linear-gradient(135deg, #f093fb 0%, #f5576c 100%)">
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
                  <div>
                    <div  variant="h6" sx={{ fontWeight: 600, color: 'inherit' }}>
                      AAII Investor Sentiment
                    </div>
                    <div  variant="caption" sx={{ opacity: 0.8 }}>
                      Retail Investor Survey
                    </div>
                  </div>
                  <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ 
                    width: 48, 
                    height: 48, 
                    bgcolor: 'rgba(255,255,255,0.2)',
                    backdropFilter: 'blur(10px)'
                  }}>
                    <Assessment />
                  </div>
                </div>
              {sentimentIndicators.aaii ? (
                <div>
                  <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 2, p: 1, bgcolor: 'rgba(255,255,255,0.1)', borderRadius: 1 }}>
                    <div  variant="body2" sx={{ fontWeight: 600 }}>Bullish:</div>
                    <div  variant="body2" sx={{ fontWeight: 700 }}>
                      {sentimentIndicators.aaii.bullish !== undefined ? 
                        (typeof sentimentIndicators.aaii.bullish === 'number' && sentimentIndicators.aaii.bullish <= 1 ? 
                          (sentimentIndicators.aaii.bullish * 100).toFixed(1) + '%' : 
                          sentimentIndicators.aaii.bullish.toFixed(1) + '%'
                        ) : 'N/A'}
                    </div>
                  </div>
                  <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 2, p: 1, bgcolor: 'rgba(255,255,255,0.1)', borderRadius: 1 }}>
                    <div  variant="body2" sx={{ fontWeight: 600 }}>Neutral:</div>
                    <div  variant="body2" sx={{ fontWeight: 700 }}>
                      {sentimentIndicators.aaii.neutral !== undefined ? 
                        (typeof sentimentIndicators.aaii.neutral === 'number' && sentimentIndicators.aaii.neutral <= 1 ? 
                          (sentimentIndicators.aaii.neutral * 100).toFixed(1) + '%' : 
                          sentimentIndicators.aaii.neutral.toFixed(1) + '%'
                        ) : 'N/A'}
                    </div>
                  </div>
                  <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 2, p: 1, bgcolor: 'rgba(255,255,255,0.1)', borderRadius: 1 }}>
                    <div  variant="body2" sx={{ fontWeight: 600 }}>Bearish:</div>
                    <div  variant="body2" sx={{ fontWeight: 700 }}>
                      {sentimentIndicators.aaii.bearish !== undefined ? 
                        (typeof sentimentIndicators.aaii.bearish === 'number' && sentimentIndicators.aaii.bearish <= 1 ? 
                          (sentimentIndicators.aaii.bearish * 100).toFixed(1) + '%' : 
                          sentimentIndicators.aaii.bearish.toFixed(1) + '%'
                        ) : 'N/A'}
                    </div>
                  </div>
                  <div  variant="body2" sx={{ opacity: 0.9 }}>
                    Week ending: {sentimentIndicators.aaii.date ? new Date(sentimentIndicators.aaii.date).toLocaleDateString() : 'N/A'}
                  </div>
                </div>
              ) : (
                <div>
                  <div  variant="body2" sx={{ opacity: 0.7 }}>No AAII data available</div>
                  <div  variant="caption" sx={{ opacity: 0.6 }}>Sentiment indicators are loading...</div>
                </div>
              )}
            </div>
            </GradientCard>
          </AnimatedCard>
        </div>
        <div className="grid" item xs={12} md={4}>
          <AnimatedCard delay={2}>
            <GradientCard gradient="linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)">
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
                  <div>
                    <div  variant="h6" sx={{ fontWeight: 600, color: 'inherit' }}>
                      NAAIM Exposure Index
                    </div>
                    <div  variant="caption" sx={{ opacity: 0.8 }}>
                      Professional Manager Positioning
                    </div>
                  </div>
                  <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ 
                    width: 48, 
                    height: 48, 
                    bgcolor: 'rgba(255,255,255,0.2)',
                    backdropFilter: 'blur(10px)'
                  }}>
                    <AccountBalance />
                  </div>
                </div>
              {sentimentIndicators.naaim ? (
                <div>
                  <div  variant="h2" sx={{ mb: 2, fontWeight: 700 }}>
                    {sentimentIndicators.naaim.average !== undefined ? sentimentIndicators.naaim.average.toFixed(1) + '%' : 'N/A'}
                  </div>
                  <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 1, p: 1, bgcolor: 'rgba(255,255,255,0.1)', borderRadius: 1 }}>
                    <div  variant="body2" sx={{ fontWeight: 600 }}>Bullish:</div>
                    <div  variant="body2" sx={{ fontWeight: 700 }}>
                      {sentimentIndicators.naaim.bullish_8100 !== undefined ? sentimentIndicators.naaim.bullish_8100.toFixed(1) + '%' : 'N/A'}
                    </div>
                  </div>
                  <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 2, p: 1, bgcolor: 'rgba(255,255,255,0.1)', borderRadius: 1 }}>
                    <div  variant="body2" sx={{ fontWeight: 600 }}>Bearish:</div>
                    <div  variant="body2" sx={{ fontWeight: 700 }}>
                      {sentimentIndicators.naaim.bearish !== undefined ? sentimentIndicators.naaim.bearish.toFixed(1) + '%' : 'N/A'}
                    </div>
                  </div>
                  <div  variant="body2" sx={{ opacity: 0.9 }}>
                    Week ending: {sentimentIndicators.naaim.week_ending ? new Date(sentimentIndicators.naaim.week_ending).toLocaleDateString() : 'N/A'}
                  </div>
                </div>
              ) : (
                <div>
                  <div  variant="h2" sx={{ mb: 1, fontWeight: 700, opacity: 0.5 }}>
                    --
                  </div>
                  <div  variant="body2" sx={{ opacity: 0.7 }}>No NAAIM data available</div>
                </div>
              )}
            </div>
            </GradientCard>
          </AnimatedCard>
        </div>
      </div>

      {/* Enhanced Market Breadth Section */}
      <div className="grid" container spacing={3} sx={{ mb: 4 }}>
        <div className="grid" item xs={12} md={6}>
          <AnimatedCard delay={3}>
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Market Breadth
              </div>
              <div className="grid" container spacing={2}>
                <div className="grid" item xs={6}>
                  <div  sx={{ textAlign: 'center', p: 2, backgroundColor: 'success.light', borderRadius: 1 }}>
                    <div  variant="h4" color="success.contrastText">
                      {marketBreadth.advancing !== undefined && marketBreadth.advancing !== null ? parseInt(marketBreadth.advancing).toLocaleString() : 'N/A'}
                    </div>
                    <div  variant="body2" color="success.contrastText">
                      Advancing
                    </div>
                  </div>
                </div>
                <div className="grid" item xs={6}>
                  <div  sx={{ textAlign: 'center', p: 2, backgroundColor: 'error.light', borderRadius: 1 }}>
                    <div  variant="h4" color="error.contrastText">
                      {marketBreadth.declining !== undefined && marketBreadth.declining !== null ? parseInt(marketBreadth.declining).toLocaleString() : 'N/A'}
                    </div>
                    <div  variant="body2" color="error.contrastText">
                      Declining
                    </div>
                  </div>
                </div>
                <div className="grid" item xs={12}>
                  <div  sx={{ textAlign: 'center', mt: 2 }}>
                    <div  variant="body2" color="text.secondary">
                      Advance/Decline Ratio: {marketBreadth.advance_decline_ratio !== undefined ? marketBreadth.advance_decline_ratio : 'N/A'}
                    </div>
                    <div  variant="body2" color="text.secondary">
                      Average Change: {marketBreadth.average_change_percent !== undefined ? parseFloat(marketBreadth.average_change_percent).toFixed(2) : 'N/A'}%
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </AnimatedCard>
        </div>
        <div className="grid" item xs={12} md={6}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Market Statistics
              </div>
              <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                <div  variant="body2">Total Stocks:</div>
                <div  variant="body2" fontWeight="600">
                  {marketBreadth.total_stocks !== undefined ? parseInt(marketBreadth.total_stocks).toLocaleString() : 'N/A'}
                </div>
              </div>
              <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                <div  variant="body2">Total Market Cap:</div>
                <div  variant="body2" fontWeight="600">
                  {marketCap.total !== undefined ? formatCurrency(marketCap.total) : 'N/A'}
                </div>
              </div>
              <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                <div  variant="body2">Unchanged:</div>
                <div  variant="body2" fontWeight="600">
                  {marketBreadth.unchanged !== undefined ? parseInt(marketBreadth.unchanged).toLocaleString() : 'N/A'}
                </div>
              </div>            </div>
          </div>
        </div>
      </div>

      {/* Enhanced Tabs Section */}
      <AnimatedCard delay={5}>
        <div  sx={{ borderBottom: 1, borderColor: 'divider', bgcolor: 'background.paper' }}>
          <div className="border-b border-gray-200" 
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
                  color: '#1976d2',
                },
              },
              '& .MuiTabs-indicator': {
                height: 3,
                borderRadius: '3px 3px 0 0',
                background: 'linear-gradient(90deg, #1976d2 0%, #9c27b0 100%)'
              }
            }}
          >
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Market Overview" icon={<ShowChart />} iconPosition="start" />
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Sentiment History" icon={<Timeline />} iconPosition="start" />
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Sector Performance" icon={<Business />} iconPosition="start" />
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Market Breadth" icon={<Equalizer />} iconPosition="start" />
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Economic Indicators" icon={<Public />} iconPosition="start" />
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Seasonality" icon={<CalendarToday />} iconPosition="start" />
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Research Indicators" icon={<Analytics />} iconPosition="start" />
          </div>
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={tabValue} index={0}>
          <div className="grid" container spacing={3}>
            <div className="grid" item xs={12} md={6}>
              <div className="bg-white shadow-md rounded-lg">
                <div className="bg-white shadow-md rounded-lg"Content>
                  <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                    Market Cap Distribution
                  </div>
                  <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <div  variant="body2">Large Cap:</div>
                    <div  variant="body2" fontWeight="600">
                      {formatCurrency(marketCap.large_cap)}
                    </div>
                  </div>
                  <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <div  variant="body2">Mid Cap:</div>
                    <div  variant="body2" fontWeight="600">
                      {formatCurrency(marketCap.mid_cap)}
                    </div>
                  </div>
                  <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <div  variant="body2">Small Cap:</div>
                    <div  variant="body2" fontWeight="600">
                      {formatCurrency(marketCap.small_cap)}
                    </div>
                  </div>
                  <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <div  variant="body2">Total:</div>
                    <div  variant="body2" fontWeight="600">
                      {formatCurrency(marketCap.total)}
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div className="grid" item xs={12} md={6}>
              <div className="bg-white shadow-md rounded-lg">
                <div className="bg-white shadow-md rounded-lg"Content>
                  <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                    Latest Economic Indicators
                  </div>
                  {economicIndicators.slice(0, 5).map((indicator, index) => (
                    <div  key={index} sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                      <div  variant="body2">{indicator.name}:</div>
                      <div  variant="body2" fontWeight="600">
                        {indicator.value} {indicator.unit}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={tabValue} index={1}>
          {sentimentLoading ? (
            <div className="w-full bg-gray-200 rounded-full h-2" />
          ) : (
            <div>
              {sentimentLoading ? (
                <div className="w-full bg-gray-200 rounded-full h-2" />
              ) : (
                <SentimentHistoryPanel />
              )}
            </div>
          )}
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={tabValue} index={2}>
          {sectorLoading ? (
            <div className="w-full bg-gray-200 rounded-full h-2" />
          ) : (
            <div className="grid" container spacing={3}>
              <div className="grid" item xs={12} md={8}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                      Sector Performance
                    </div>
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
                  </div>
                </div>
              </div>
              <div className="grid" item xs={12} md={4}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                      Sector Details
                    </div>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Sector</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Change %</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Stocks</td>
                          </tr>
                        </thead>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                          {sectors.slice(0, 8).map((sector, index) => {
                            const changePercent = parseFloat(sector.avg_change_percent || sector.avg_change || sector.performance) || 0
                            return (
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={index}>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{sector.sector?.substring(0, 12) || 'N/A'}</td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell 
                                  align="right"
                                  sx={{ 
                                    color: getChangeColor(changePercent),
                                    fontWeight: 600
                                  }}
                                >
                                  {formatPercentage(changePercent)}
                                </td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                                  {sector.stock_count || sector.count || 0}
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={tabValue} index={3}>
          {breadthLoading ? (
            <div className="w-full bg-gray-200 rounded-full h-2" />
          ) : (
            <div className="grid" container spacing={3}>
              <div className="grid" item xs={12} md={6}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                      Market Breadth Details
                    </div>
                    <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                      <div  variant="body2">Advancing Stocks:</div>
                      <div  variant="body2" color="success.main" fontWeight="600">
                        {breadthInfo.advancing || 0}
                      </div>
                    </div>
                    <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                      <div  variant="body2">Declining Stocks:</div>
                      <div  variant="body2" color="error.main" fontWeight="600">
                        {breadthInfo.declining || 0}
                      </div>
                    </div>
                    <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                      <div  variant="body2">Unchanged:</div>
                      <div  variant="body2" fontWeight="600">
                        {breadthInfo.unchanged || 0}
                      </div>
                    </div>
                    <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                      <div  variant="body2">A/D Ratio:</div>
                      <div  variant="body2" fontWeight="600">
                        {breadthInfo.advance_decline_ratio || 'N/A'}
                      </div>
                    </div>
                    <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                      <div  variant="body2">Average Change:</div>
                      <div  
                        variant="body2" 
                        fontWeight="600"
                        sx={{ color: getChangeColor(parseFloat(breadthInfo.average_change_percent) || 0) }}
                      >
                        {formatPercentage(parseFloat(breadthInfo.average_change_percent) || 0)}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <div className="grid" item xs={12} md={6}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                      Breadth Visualization
                    </div>
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
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={tabValue} index={4}>
          {economicLoading ? (
            <div className="w-full bg-gray-200 rounded-full h-2" />
          ) : (
            <div className="grid" container spacing={3}>
              <div className="grid" item xs={12}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                      Economic Indicators (Last 90 Days)
                    </div>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow sx={{ backgroundColor: 'grey.50' }}>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell sx={{ fontWeight: 600 }}>Indicator</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right" sx={{ fontWeight: 600 }}>Current Value</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right" sx={{ fontWeight: 600 }}>Previous Value</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right" sx={{ fontWeight: 600 }}>Change</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right" sx={{ fontWeight: 600 }}>Date</td>
                          </tr>
                        </thead>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
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
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={index} hover>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{indicator.name || indicator.indicator_name || 'N/A'}</td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                                  {indicator.value} {indicator.unit}
                                </td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                                  {indicator.previous_value || 'N/A'} {indicator.unit}
                                </td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell 
                                  align="right"
                                  sx={{ 
                                    color: getChangeColor(parseFloat(indicator.change_percent) || 0),
                                    fontWeight: 600
                                  }}
                                >
                                  {indicator.change_percent ? formatPercentage(parseFloat(indicator.change_percent)) : 'N/A'}
                                </td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                                  {indicator.timestamp || indicator.date ? new Date(indicator.timestamp || indicator.date).toLocaleDateString() : 'N/A'}
                                </td>
                              </tr>
                            ))
                          })()}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={tabValue} index={5}>
          {seasonalityLoading ? (
            <div className="w-full bg-gray-200 rounded-full h-2" />
          ) : (
            <div className="grid" container spacing={3}>
              {seasonalityData?.data && (
                <>
                  {/* Current Seasonal Position Summary */}
                  <div className="grid" item xs={12}>
                    <div className="bg-white shadow-md rounded-lg" sx={{ border: '2px solid', borderColor: 'primary.main' }}>
                      <div className="bg-white shadow-md rounded-lg"Content>
                        <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Current Seasonal Position
                        </div>
                        <div className="grid" container spacing={3}>
                          <div className="grid" item xs={12} md={4}>
                            <div  sx={{ textAlign: 'center', p: 2, backgroundColor: 'info.light', borderRadius: 1 }}>
                              <div  variant="h4" color="info.contrastText">
                                {seasonalityData.data.currentPosition.seasonalScore}/100
                              </div>
                              <div  variant="body2" color="info.contrastText">
                                Seasonal Score
                              </div>
                              <div  variant="caption" color="info.contrastText">
                                {seasonalityData.data.summary.overallSeasonalBias}
                              </div>
                            </div>
                          </div>
                          <div className="grid" item xs={12} md={4}>
                            <div  sx={{ textAlign: 'center', p: 2, backgroundColor: 'secondary.light', borderRadius: 1 }}>
                              <div  variant="h6" color="secondary.contrastText">
                                {seasonalityData.data.currentPosition.presidentialCycle}
                              </div>
                              <div  variant="body2" color="secondary.contrastText">
                                Presidential Cycle
                              </div>
                            </div>
                          </div>
                          <div className="grid" item xs={12} md={4}>
                            <div  sx={{ textAlign: 'center', p: 2, backgroundColor: 'warning.light', borderRadius: 1 }}>
                              <div  variant="h6" color="warning.contrastText">
                                {seasonalityData.data.currentPosition.nextMajorEvent?.name}
                              </div>
                              <div  variant="body2" color="warning.contrastText">
                                Next Event ({seasonalityData.data.currentPosition.nextMajorEvent?.daysAway} days)
                              </div>
                            </div>
                          </div>
                        </div>
                        <div  sx={{ mt: 3 }}>
                          <div  variant="body1" sx={{ mb: 1 }}>
                            <strong>Recommendation:</strong> {seasonalityData.data.summary.recommendation}
                          </div>
                          <div  variant="body2" color="text.secondary">
                            Active Periods: {seasonalityData.data.currentPosition.activePeriods?.join(', ')}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Monthly Seasonality */}
                  <div className="grid" item xs={12} md={6}>
                    <div className="bg-white shadow-md rounded-lg">
                      <div className="bg-white shadow-md rounded-lg"Content>
                        <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Monthly Seasonality Pattern
                        </div>
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
                      </div>
                    </div>
                  </div>

                  {/* Quarterly Patterns */}
                  <div className="grid" item xs={12} md={6}>
                    <div className="bg-white shadow-md rounded-lg">
                      <div className="bg-white shadow-md rounded-lg"Content>
                        <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Quarterly Performance
                        </div>
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
                      </div>
                    </div>
                  </div>

                  {/* Presidential Cycle Details */}
                  <div className="grid" item xs={12} md={6}>
                    <div className="bg-white shadow-md rounded-lg">
                      <div className="bg-white shadow-md rounded-lg"Content>
                        <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Presidential Cycle (4-Year Pattern)
                        </div>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Year</td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Phase</td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Avg Return</td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Status</td>
                              </tr>
                            </thead>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                              {seasonalityData.data.presidentialCycle.data.map((cycle) => (
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={cycle.year} sx={{ backgroundColor: cycle.isCurrent ? 'primary.light' : 'inherit' }}>
                                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Year {cycle.year}</td>
                                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{cycle.label}</td>
                                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{formatPercentage(cycle.avgReturn)}</td>
                                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                                    {cycle.isCurrent && <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="CURRENT" color="primary" size="small" />}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Day of Week Effects */}
                  <div className="grid" item xs={12} md={6}>
                    <div className="bg-white shadow-md rounded-lg">
                      <div className="bg-white shadow-md rounded-lg"Content>
                        <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Day of Week Effects
                        </div>
                        {seasonalityData.data.dayOfWeekEffects.map((day) => (
                          <div  key={day.day} sx={{ 
                            display: 'flex', 
                            justifyContent: 'space-between', 
                            mb: 1,
                            p: 1,
                            backgroundColor: day.isCurrent ? 'primary.light' : 'inherit',
                            borderRadius: 1
                          }}>
                            <div  variant="body2" fontWeight={day.isCurrent ? 600 : 400}>
                              {day.day}
                            </div>
                            <div  
                              variant="body2" 
                              sx={{ color: getChangeColor(day.avgReturn * 100) }}
                              fontWeight={600}
                            >
                              {formatPercentage(day.avgReturn)}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Seasonal Anomalies */}
                  <div className="grid" item xs={12}>
                    <div className="bg-white shadow-md rounded-lg">
                      <div className="bg-white shadow-md rounded-lg"Content>
                        <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Seasonal Anomalies & Effects
                        </div>
                        <div className="grid" container spacing={2}>
                          {seasonalityData.data.seasonalAnomalies.map((anomaly, index) => (
                            <div className="grid" item xs={12} sm={6} md={3} key={index}>
                              <div  sx={{ 
                                p: 2, 
                                border: 1, 
                                borderColor: 'divider', 
                                borderRadius: 1,
                                height: '100%'
                              }}>
                                <div  variant="subtitle2" fontWeight={600}>
                                  {anomaly.name}
                                </div>
                                <div  variant="caption" color="text.secondary" display="block">
                                  {anomaly.period}
                                </div>
                                <div  variant="body2" sx={{ mt: 1, mb: 1 }}>
                                  {anomaly.description}
                                </div>
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                  label={anomaly.strength}
                                  size="small"
                                  color={
                                    anomaly.strength === 'Strong' ? 'error' :
                                    anomaly.strength === 'Moderate' ? 'warning' : 'default'
                                  }
                                />
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Holiday Effects */}
                  <div className="grid" item xs={12} md={6}>
                    <div className="bg-white shadow-md rounded-lg">
                      <div className="bg-white shadow-md rounded-lg"Content>
                        <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Holiday Effects
                        </div>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Holiday</td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Dates</td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Effect</td>
                              </tr>
                            </thead>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                              {seasonalityData.data.holidayEffects.map((holiday, index) => (
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={index}>
                                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{holiday.holiday}</td>
                                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{holiday.dates}</td>
                                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right" sx={{ 
                                    color: getChangeColor(parseFloat(holiday.effect.replace('%', ''))),
                                    fontWeight: 600
                                  }}>
                                    {holiday.effect}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Sector Seasonality */}
                  <div className="grid" item xs={12} md={6}>
                    <div className="bg-white shadow-md rounded-lg">
                      <div className="bg-white shadow-md rounded-lg"Content>
                        <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Sector Seasonality
                        </div>
                        {seasonalityData.data.sectorSeasonality.map((sector, index) => (
                          <div  key={index} sx={{ mb: 2 }}>
                            <div  variant="subtitle2" fontWeight={600}>
                              {sector.sector}
                            </div>
                            <div  variant="caption" color="text.secondary">
                              Best: {sector.bestMonths.map(m => new Date(0, m-1).toLocaleString('default', {month:'short'})).join(', ')}
                            </div>
                            <div  variant="caption" color="text.secondary" display="block">
                              Worst: {sector.worstMonths.map(m => new Date(0, m-1).toLocaleString('default', {month:'short'})).join(', ')}
                            </div>
                            <div  variant="body2" sx={{ mt: 0.5 }}>
                              {sector.rationale}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Summary & Outlook */}
                  <div className="grid" item xs={12}>
                    <div className="bg-white shadow-md rounded-lg">
                      <div className="bg-white shadow-md rounded-lg"Content>
                        <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Seasonal Outlook Summary
                        </div>
                        <div className="grid" container spacing={3}>
                          <div className="grid" item xs={12} md={6}>
                            <div  variant="body2" fontWeight={600} color="success.main" sx={{ mb: 1 }}>
                              Favorable Factors:
                            </div>
                            {seasonalityData.data.summary.favorableFactors?.map((factor, index) => (
                              <div  key={index} variant="body2" sx={{ ml: 2, mb: 0.5 }}>
                                • {factor}
                              </div>
                            ))}
                          </div>
                          <div className="grid" item xs={12} md={6}>
                            <div  variant="body2" fontWeight={600} color="error.main" sx={{ mb: 1 }}>
                              Unfavorable Factors:
                            </div>
                            {seasonalityData.data.summary.unfavorableFactors?.map((factor, index) => (
                              <div  key={index} variant="body2" sx={{ ml: 2, mb: 0.5 }}>
                                • {factor}
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={tabValue} index={6}>
          {researchLoading ? (
            <div className="w-full bg-gray-200 rounded-full h-2" />
          ) : (
            <div className="grid" container spacing={3}>
              {researchData?.data && (
                <>
                  {/* Market Summary */}
                  <div className="grid" item xs={12}>
                    <div className="bg-white shadow-md rounded-lg">
                      <div className="bg-white shadow-md rounded-lg"Content>
                        <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Market Research Summary
                        </div>
                        <div className="grid" container spacing={3}>
                          <div className="grid" item xs={12} md={4}>
                            <div  sx={{ textAlign: 'center', p: 2, backgroundColor: 'info.light', borderRadius: 1 }}>
                              <div  variant="h6" color="info.contrastText">
                                {researchData.data.summary.overallSentiment}
                              </div>
                              <div  variant="body2" color="info.contrastText">
                                Overall Market Sentiment
                              </div>
                            </div>
                          </div>
                          <div className="grid" item xs={12} md={4}>
                            <div  sx={{ textAlign: 'center', p: 2, backgroundColor: 'secondary.light', borderRadius: 1 }}>
                              <div  variant="h6" color="secondary.contrastText">
                                {researchData.data.summary.marketRegime}
                              </div>
                              <div  variant="body2" color="secondary.contrastText">
                                Market Regime
                              </div>
                            </div>
                          </div>
                          <div className="grid" item xs={12} md={4}>
                            <div  sx={{ textAlign: 'center', p: 2, backgroundColor: 'warning.light', borderRadius: 1 }}>
                              <div  variant="h6" color="warning.contrastText">
                                {researchData.data.summary.timeHorizon}
                              </div>
                              <div  variant="body2" color="warning.contrastText">
                                Investment Time Horizon
                              </div>
                            </div>
                          </div>
                        </div>
                        <div  sx={{ mt: 3 }}>
                          <div  variant="body1" sx={{ mb: 1 }}>
                            <strong>Recommendation:</strong> {researchData.data.summary.recommendation}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Volatility & Sentiment Indicators */}
                  <div className="grid" item xs={12} md={6}>
                    <div className="bg-white shadow-md rounded-lg">
                      <div className="bg-white shadow-md rounded-lg"Content>
                        <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Volatility & Sentiment
                        </div>
                        <div className="grid" container spacing={2}>
                          <div className="grid" item xs={12}>
                            <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                              <div  variant="body2">VIX (Fear Index):</div>
                              <div>
                                <div  variant="body2" fontWeight={600} display="inline">
                                  {researchData.data.volatility.vix.toFixed(1)}
                                </div>
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                  label={researchData.data.volatility.vixInterpretation.level}
                                  color={researchData.data.volatility.vixInterpretation.color}
                                  size="small"
                                  sx={{ ml: 1 }}
                                />
                              </div>
                            </div>
                            <div  variant="caption" color="text.secondary">
                              30-day avg: {researchData.data.volatility.vixAverage.toFixed(1)} | {researchData.data.volatility.vixInterpretation.sentiment}
                            </div>
                          </div>
                          <div className="grid" item xs={12}>
                            <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                              <div  variant="body2">Put/Call Ratio:</div>
                              <div>
                                <div  variant="body2" fontWeight={600} display="inline">
                                  {researchData.data.sentiment.putCallRatio.toFixed(2)}
                                </div>
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                  label={researchData.data.sentiment.putCallInterpretation.sentiment}
                                  color={researchData.data.sentiment.putCallInterpretation.color}
                                  size="small"
                                  sx={{ ml: 1 }}
                                />
                              </div>
                            </div>
                            <div  variant="caption" color="text.secondary">
                              10-day avg: {researchData.data.sentiment.putCallAverage.toFixed(2)} | {researchData.data.sentiment.putCallInterpretation.signal}
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Technical Levels */}
                  <div className="grid" item xs={12} md={6}>
                    <div className="bg-white shadow-md rounded-lg">
                      <div className="bg-white shadow-md rounded-lg"Content>
                        <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Major Index Technical Levels
                        </div>
                        {Object.entries(researchData.data.technicalLevels).map(([index, data]) => (
                          <div  key={index} sx={{ mb: 2 }}>
                            <div  variant="body2" fontWeight={600}>{index}</div>
                            <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                              <div  variant="caption">Current:</div>
                              <div  variant="caption">{data.current.toFixed(0)}</div>
                            </div>
                            <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                              <div  variant="caption">Trend:</div>
                              <div  variant="caption" sx={{ color: getChangeColor(data.trend === 'Bullish' ? 1 : data.trend === 'Bearish' ? -1 : 0) }}>
                                {data.trend}
                              </div>
                            </div>
                            <div  sx={{ display: 'flex', justifyContent: 'space-between' }}>
                              <div  variant="caption">RSI:</div>
                              <div  variant="caption">{data.rsi.toFixed(1)}</div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Sector Rotation */}
                  <div className="grid" item xs={12}>
                    <div className="bg-white shadow-md rounded-lg">
                      <div className="bg-white shadow-md rounded-lg"Content>
                        <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Sector Rotation Analysis
                        </div>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow sx={{ backgroundColor: 'grey.50' }}>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell sx={{ fontWeight: 600 }}>Sector</td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell sx={{ fontWeight: 600 }}>Momentum</td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell sx={{ fontWeight: 600 }}>Money Flow</td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right" sx={{ fontWeight: 600 }}>Performance</td>
                              </tr>
                            </thead>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                              {researchData.data.sectorRotation.map((sector, index) => (
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={index} hover>
                                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{sector.sector}</td>
                                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                      label={sector.momentum}
                                      color={sector.momentum === 'Strong' ? 'success' : sector.momentum === 'Moderate' ? 'info' : 'warning'}
                                      size="small"
                                    />
                                  </td>
                                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                      label={sector.flow}
                                      color={sector.flow === 'Inflow' ? 'success' : sector.flow === 'Outflow' ? 'error' : 'default'}
                                      size="small"
                                    />
                                  </td>
                                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell 
                                    align="right"
                                    sx={{ 
                                      color: getChangeColor(sector.performance),
                                      fontWeight: 600
                                    }}
                                  >
                                    {formatPercentage(sector.performance)}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Economic Calendar */}
                  <div className="grid" item xs={12} md={6}>
                    <div className="bg-white shadow-md rounded-lg">
                      <div className="bg-white shadow-md rounded-lg"Content>
                        <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Upcoming Economic Events
                        </div>
                        {researchData.data.economicCalendar.map((event, index) => (
                          <div  key={index} sx={{ mb: 2, p: 2, backgroundColor: 'grey.50', borderRadius: 1 }}>
                            <div  variant="body2" fontWeight={600}>{event.event}</div>
                            <div  variant="caption" color="text.secondary">
                              {new Date(event.date).toLocaleDateString()} | Expected: {event.expected}
                            </div>
                            <div  sx={{ mt: 0.5 }}>
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                label={event.importance}
                                color={event.importance === 'High' ? 'error' : 'warning'}
                                size="small"
                              />
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                label={event.impact}
                                color="info"
                                size="small"
                                sx={{ ml: 1 }}
                              />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Key Risks & Opportunities */}
                  <div className="grid" item xs={12} md={6}>
                    <div className="bg-white shadow-md rounded-lg">
                      <div className="bg-white shadow-md rounded-lg"Content>
                        <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                          Key Risks & Opportunities
                        </div>
                        <div  sx={{ mb: 3 }}>
                          <div  variant="body2" fontWeight={600} color="error.main" sx={{ mb: 1 }}>
                            Key Risks:
                          </div>
                          {researchData.data.summary.keyRisks.map((risk, index) => (
                            <div  key={index} variant="body2" sx={{ ml: 2, mb: 0.5 }}>
                              • {risk}
                            </div>
                          ))}
                        </div>
                        <div>
                          <div  variant="body2" fontWeight={600} color="success.main" sx={{ mb: 1 }}>
                            Key Opportunities:
                          </div>
                          {researchData.data.summary.keyOpportunities.map((opportunity, index) => (
                            <div  key={index} variant="body2" sx={{ ml: 2, mb: 0.5 }}>
                              • {opportunity}
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </AnimatedCard>
    </div>
  )
}

export default MarketOverview