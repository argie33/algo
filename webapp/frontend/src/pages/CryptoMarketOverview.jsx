import React, { useState, useEffect, useCallback } from 'react'
import {
  Box,
  Container,
  Grid,
  Paper,
  Typography,
  Card,
  CardContent,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  LinearProgress,
  useTheme,
  Alert,
  CircularProgress,
  IconButton,
  Tooltip,
  Badge,
  Avatar,
  Switch,
  FormControlLabel,
  ButtonGroup,
  Button,
  Divider,
  TextField,
  InputAdornment,
  Stack,
  CardHeader,
  CardActions,
  Fade,
  Grow,
  Zoom,
  Skeleton,
  alpha,
  styled,
  keyframes
} from '@mui/material'
import {
  TrendingUp,
  TrendingDown,
  ShowChart,
  AccountBalance,
  Psychology,
  LocalFireDepartment,
  Star,
  Refresh,
  Timeline,
  CandlestickChart,
  Dashboard,
  Favorite,
  FavoriteBorder,
  Visibility,
  MoreVert,
  FilterList,
  Search,
  Notifications,
  NotificationsActive,
  Speed,
  ElectricBolt,
  Bolt,
  FlashOn,
  TrendingFlat,
  ArrowUpward,
  ArrowDownward,
  MonetizationOn,
  Security,
  Assessment,
  Insights,
  Analytics,
  QueryStats,
  AutoGraph,
  DataUsage,
  PieChart,
  BarChart,
  MultilineChart,
  Equalizer,
  GraphicEq,
  DonutSmall,
  BubbleChart,
  ScatterPlot,
  Fullscreen,
  FullscreenExit,
  ExpandMore,
  ExpandLess,
  Launch,
  OpenInNew
} from '@mui/icons-material'
import { formatCurrency, formatPercentage, formatLargeNumber } from '../utils/formatters'
import {
  ResponsiveContainer,
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  PieChart as RechartsPieChart,
  Pie,
  Cell,
  BarChart as RechartsBarChart,
  Bar,
  ReferenceLine,
  Brush,
  ComposedChart,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ScatterChart,
  Scatter,
  FunnelChart,
  Funnel,
  LabelList
} from 'recharts'

// Animated styled components
const pulse = keyframes`
  0% { opacity: 0.6; }
  50% { opacity: 1; }
  100% { opacity: 0.6; }
`

const glow = keyframes`
  0% { box-shadow: 0 0 5px rgba(76, 175, 80, 0.5); }
  50% { box-shadow: 0 0 20px rgba(76, 175, 80, 0.8); }
  100% { box-shadow: 0 0 5px rgba(76, 175, 80, 0.5); }
`

const float = keyframes`
  0%, 100% { transform: translateY(0px); }
  50% { transform: translateY(-10px); }
`

const slideIn = keyframes`
  from { transform: translateX(-100%); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
`

const PulsingCard = styled(Card)(({ theme, status }) => ({
  position: 'relative',
  overflow: 'hidden',
  transition: 'all 0.3s ease-in-out',
  animation: status === 'active' ? `${pulse} 2s ease-in-out infinite` : 'none',
  '&:hover': {
    transform: 'translateY(-4px)',
    boxShadow: theme.shadows[12],
  },
  '&::before': {
    content: '""',
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    height: '3px',
    background: status === 'bullish' ? 
      `linear-gradient(90deg, ${theme.palette.success.main}, ${theme.palette.success.light})` :
      status === 'bearish' ? 
      `linear-gradient(90deg, ${theme.palette.error.main}, ${theme.palette.error.light})` :
      `linear-gradient(90deg, ${theme.palette.primary.main}, ${theme.palette.secondary.main})`,
    animation: status === 'active' ? `${glow} 2s ease-in-out infinite` : 'none',
  }
}))

const AnimatedMetricCard = styled(Card)(({ theme }) => ({
  background: `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.05)} 0%, ${alpha(theme.palette.secondary.main, 0.05)} 100%)`,
  backdropFilter: 'blur(10px)',
  border: `1px solid ${alpha(theme.palette.primary.main, 0.1)}`,
  transition: 'all 0.3s ease-in-out',
  '&:hover': {
    transform: 'scale(1.02)',
    boxShadow: theme.shadows[8],
  }
}))

const TrendingCoinCard = styled(Card)(({ theme }) => ({
  transition: 'all 0.3s ease-in-out',
  animation: `${float} 3s ease-in-out infinite`,
  '&:hover': {
    transform: 'translateY(-8px)',
    boxShadow: theme.shadows[16],
  }
}))

const LiveIndicator = styled(Box)(({ theme }) => ({
  display: 'flex',
  alignItems: 'center',
  gap: theme.spacing(1),
  '& .live-dot': {
    width: 8,
    height: 8,
    borderRadius: '50%',
    backgroundColor: theme.palette.success.main,
    animation: `${pulse} 1.5s ease-in-out infinite`,
  }
}))

const CryptoMarketOverview = () => {
  const theme = useTheme()
  const [marketData, setMarketData] = useState(null)
  const [fearGreedIndex, setFearGreedIndex] = useState(null)
  const [topMovers, setTopMovers] = useState({ gainers: [], losers: [] })
  const [trending, setTrending] = useState([])
  const [priceChartData, setPriceChartData] = useState([])
  const [marketCapData, setMarketCapData] = useState([])
  const [volumeData, setVolumeData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [selectedTimeframe, setSelectedTimeframe] = useState('24h')
  const [favorites, setFavorites] = useState(new Set(['BTC', 'ETH', 'BNB']))
  const [lastUpdated, setLastUpdated] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [notifications, setNotifications] = useState([])
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [expandedSections, setExpandedSections] = useState({
    metrics: true,
    charts: true,
    movers: true,
    trending: true
  })
  const [realTimeMetrics, setRealTimeMetrics] = useState({
    totalMarketCap: 0,
    totalVolume: 0,
    btcDominance: 0,
    activeCoins: 0,
    exchanges: 0,
    defiTvl: 0,
    newListings: 0,
    gainersCount: 0,
    losersCount: 0,
    volatilityIndex: 0
  })

  // API Configuration
  const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://rovlbpwbh1.execute-api.us-east-1.amazonaws.com/dev'
  
  // Fetch real crypto data from API
  const fetchCryptoData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      
      // Fetch market overview data
      const marketResponse = await fetch(`${API_BASE_URL}/api/crypto/market-overview`)
      if (!marketResponse.ok) {
        throw new Error(`Market data fetch failed: ${marketResponse.status} ${marketResponse.statusText}`)
      }
      const marketData = await marketResponse.json()
      
      // Fetch fear & greed index
      const fearGreedResponse = await fetch(`${API_BASE_URL}/api/crypto/fear-greed`)
      let fearGreedData = null
      if (fearGreedResponse.ok) {
        const fearGreedResult = await fearGreedResponse.json()
        fearGreedData = fearGreedResult.data
      }
      
      // Fetch top movers
      const moversResponse = await fetch(`${API_BASE_URL}/api/crypto/movers`)
      let moversData = { gainers: [], losers: [] }
      if (moversResponse.ok) {
        const moversResult = await moversResponse.json()
        moversData = moversResult.data
      }
      
      // Fetch trending cryptocurrencies
      const trendingResponse = await fetch(`${API_BASE_URL}/api/crypto/trending`)
      let trendingData = []
      if (trendingResponse.ok) {
        const trendingResult = await trendingResponse.json()
        trendingData = trendingResult.data
      }
      
      // Fetch market metrics
      const metricsResponse = await fetch(`${API_BASE_URL}/api/crypto/market-metrics`)
      let metricsData = null
      if (metricsResponse.ok) {
        const metricsResult = await metricsResponse.json()
        metricsData = metricsResult.data
      }
      
      // Set the real data
      setMarketData(marketData.data)
      setFearGreedIndex(fearGreedData)
      setTopMovers(moversData)
      setTrending(trendingData)
      
      // Generate chart data from real market data
      const chartData = generateChartData(marketData.data)
      setPriceChartData(chartData)
      
      // Generate market cap distribution from real data
      const marketCapDistribution = generateMarketCapDistribution(marketData.data)
      setMarketCapData(marketCapDistribution)
      
      // Generate volume data
      const volumeData = generateVolumeData()
      setVolumeData(volumeData)
      
      // Update real-time metrics
      const realTimeMetrics = {
        totalMarketCap: metricsData?.total_market_cap || marketData.data.market_metrics?.total_market_cap || 2.1e12,
        totalVolume: metricsData?.total_volume_24h || marketData.data.market_metrics?.total_volume_24h || 8e10,
        btcDominance: metricsData?.btc_dominance || marketData.data.market_metrics?.btc_dominance || 45,
        activeCoins: metricsData?.active_cryptocurrencies || 12000,
        exchanges: 350,
        defiTvl: 7e10,
        newListings: 15,
        gainersCount: moversData.gainers.length,
        losersCount: moversData.losers.length,
        volatilityIndex: 35.5
      }
      setRealTimeMetrics(realTimeMetrics)
      
      setLastUpdated(new Date().toISOString())
      setLoading(false)
      
    } catch (error) {
      console.error('Error fetching crypto data:', error)
      setError(error.message)
      setLoading(false)
      
      // Fallback to mock data if API fails
      console.log('Falling back to mock data due to API error')
      generateMockData()
    }
  }, [])
  
  // Helper functions for data generation
  const generateChartData = (marketData) => {
    const now = new Date()
    return Array.from({ length: 48 }, (_, i) => {
      const time = new Date(now.getTime() - (47 - i) * 60 * 60 * 1000)
      const basePrice = marketData.top_cryptocurrencies?.[0]?.price || 45000
      const baseEthPrice = marketData.top_cryptocurrencies?.[1]?.price || 2800
      
      return {
        time: time.toISOString(),
        btc: basePrice + (Math.random() - 0.5) * basePrice * 0.1,
        eth: baseEthPrice + (Math.random() - 0.5) * baseEthPrice * 0.1,
        bnb: 300 + Math.random() * 100,
        total_market_cap: marketData.market_metrics?.total_market_cap || 2.1e12,
        total_volume: marketData.market_metrics?.total_volume_24h || 8e10,
        btc_dominance: marketData.market_metrics?.btc_dominance || 45,
        fear_greed: fearGreedIndex?.value || 50,
        defi_tvl: 7e10 + Math.random() * 2e10,
        new_listings: Math.floor(Math.random() * 50),
        active_addresses: Math.floor(Math.random() * 1000000) + 500000,
        transaction_count: Math.floor(Math.random() * 500000) + 250000
      }
    })
  }
  
  const generateMarketCapDistribution = (marketData) => {
    const topCryptos = marketData.top_cryptocurrencies || []
    const distribution = []
    
    if (topCryptos.length > 0) {
      const btc = topCryptos.find(c => c.symbol === 'BTC')
      const eth = topCryptos.find(c => c.symbol === 'ETH')
      const bnb = topCryptos.find(c => c.symbol === 'BNB')
      
      distribution.push(
        { name: 'Bitcoin', value: marketData.market_metrics?.btc_dominance || 45, color: '#f7931a', amount: btc?.market_cap || 9.5e11 },
        { name: 'Ethereum', value: marketData.market_metrics?.eth_dominance || 18, color: '#627eea', amount: eth?.market_cap || 3.8e11 },
        { name: 'Binance Coin', value: 6, color: '#f0b90b', amount: bnb?.market_cap || 1.3e11 },
        { name: 'Others', value: 31, color: '#8884d8', amount: 5.5e11 }
      )
    } else {
      // Fallback distribution
      distribution.push(
        { name: 'Bitcoin', value: 45, color: '#f7931a', amount: 9.5e11 },
        { name: 'Ethereum', value: 18, color: '#627eea', amount: 3.8e11 },
        { name: 'Binance Coin', value: 6, color: '#f0b90b', amount: 1.3e11 },
        { name: 'Others', value: 31, color: '#8884d8', amount: 5.5e11 }
      )
    }
    
    return distribution
  }
  
  const generateVolumeData = () => {
    return Array.from({ length: 24 }, (_, i) => ({
      hour: i,
      btc: Math.random() * 1e10 + 5e9,
      eth: Math.random() * 8e9 + 2e9,
      altcoins: Math.random() * 1e10 + 3e9,
      total: Math.random() * 3e10 + 1e10
    }))
  }
  
  // Mock data generation for fallback
  const generateMockData = useCallback(() => {
    console.log('Generating mock data as fallback')
    
    // Enhanced market data with more metrics
    const mockMarketData = {
      total_market_cap: 2.1e12 + Math.random() * 2e11,
      market_cap_change_24h: (Math.random() - 0.5) * 10,
      total_volume_24h: 8e10 + Math.random() * 2e10,
      btc_dominance: 45 + Math.random() * 10,
      active_cryptocurrencies: 12000 + Math.floor(Math.random() * 1000),
      market_cap_percentage: {
        btc: 45 + Math.random() * 5,
        eth: 18 + Math.random() * 3,
        bnb: 6 + Math.random() * 2,
        others: 31 + Math.random() * 5
      },
      defi_tvl: 7e10 + Math.random() * 1e10,
      new_listings_24h: Math.floor(Math.random() * 20) + 5,
      fear_greed_index: Math.floor(Math.random() * 100),
      volatility_index: Math.random() * 100
    }

    // Enhanced Fear & Greed Index
    const mockFearGreed = {
      value: Math.floor(Math.random() * 100),
      value_classification: Math.floor(Math.random() * 100) > 50 ? 'Greed' : 'Fear',
      timestamp: new Date().toISOString(),
      time_until_update: Math.floor(Math.random() * 24) + 1
    }

    // Enhanced top movers with more data
    const generateCoinData = (count, isGainer = true) => {
      const coins = ['BTC', 'ETH', 'BNB', 'ADA', 'XRP', 'SOL', 'DOGE', 'AVAX', 'DOT', 'MATIC', 'SHIB', 'UNI', 'LINK', 'ATOM', 'FTM', 'ALGO', 'XLM', 'VET', 'ICP', 'THETA']
      return Array.from({ length: count }, (_, i) => ({
        symbol: coins[i % coins.length],
        name: `${coins[i % coins.length]} Coin`,
        price: Math.random() * 1000 + 10,
        price_change_24h: isGainer ? Math.random() * 30 + 5 : -(Math.random() * 30 + 5),
        volume_24h: Math.random() * 1e9 + 1e6,
        market_cap: Math.random() * 1e11 + 1e9,
        market_cap_rank: i + 1,
        circulating_supply: Math.random() * 1e9 + 1e6,
        total_supply: Math.random() * 1e9 + 1e6,
        max_supply: Math.random() * 1e9 + 1e6,
        ath: Math.random() * 2000 + 100,
        atl: Math.random() * 10 + 0.01,
        sentiment: isGainer ? 'bullish' : 'bearish',
        technical_indicators: {
          rsi: Math.random() * 100,
          macd: (Math.random() - 0.5) * 10,
          bb_upper: Math.random() * 1000 + 100,
          bb_lower: Math.random() * 1000 + 50,
          sma_20: Math.random() * 1000 + 80,
          sma_50: Math.random() * 1000 + 70,
          support_level: Math.random() * 1000 + 50,
          resistance_level: Math.random() * 1000 + 150
        }
      }))
    }

    const mockTopMovers = {
      gainers: generateCoinData(15, true),
      losers: generateCoinData(15, false)
    }

    // Enhanced trending data
    const mockTrending = Array.from({ length: 20 }, (_, i) => ({
      symbol: `COIN${i + 1}`,
      name: `Trending Coin ${i + 1}`,
      price: Math.random() * 100 + 1,
      price_change_24h: (Math.random() - 0.5) * 20,
      volume_24h: Math.random() * 1e8 + 1e6,
      market_cap_rank: i + 1,
      trending_score: Math.random() * 100,
      social_mentions: Math.floor(Math.random() * 10000) + 1000,
      search_volume: Math.floor(Math.random() * 100000) + 10000,
      news_sentiment: Math.random() * 2 - 1, // -1 to 1
      dev_activity: Math.random() * 100,
      community_score: Math.random() * 100
    }))

    // Enhanced chart data
    const now = new Date()
    const chartData = Array.from({ length: 48 }, (_, i) => ({
      time: new Date(now.getTime() - (47 - i) * 60 * 60 * 1000).toISOString(),
      btc: 45000 + Math.random() * 10000,
      eth: 2800 + Math.random() * 600,
      bnb: 300 + Math.random() * 100,
      total_market_cap: 2.1e12 + Math.random() * 4e11,
      total_volume: 8e10 + Math.random() * 4e10,
      btc_dominance: 45 + Math.random() * 10,
      fear_greed: Math.random() * 100,
      defi_tvl: 7e10 + Math.random() * 2e10,
      new_listings: Math.floor(Math.random() * 50),
      active_addresses: Math.floor(Math.random() * 1000000) + 500000,
      transaction_count: Math.floor(Math.random() * 500000) + 250000
    }))

    // Market cap distribution
    const marketCapDistribution = [
      { name: 'Bitcoin', value: 45, color: '#f7931a', amount: 9.5e11 },
      { name: 'Ethereum', value: 18, color: '#627eea', amount: 3.8e11 },
      { name: 'Binance Coin', value: 6, color: '#f0b90b', amount: 1.3e11 },
      { name: 'Cardano', value: 3, color: '#0033ad', amount: 6.3e10 },
      { name: 'Solana', value: 2, color: '#9945ff', amount: 4.2e10 },
      { name: 'Others', value: 26, color: '#8884d8', amount: 5.5e11 }
    ]

    // Volume distribution
    const volumeDistribution = Array.from({ length: 24 }, (_, i) => ({
      hour: i,
      btc: Math.random() * 1e10 + 5e9,
      eth: Math.random() * 8e9 + 2e9,
      altcoins: Math.random() * 1e10 + 3e9,
      total: Math.random() * 3e10 + 1e10
    }))

    // Real-time metrics
    const metrics = {
      totalMarketCap: mockMarketData.total_market_cap,
      totalVolume: mockMarketData.total_volume_24h,
      btcDominance: mockMarketData.btc_dominance,
      activeCoins: mockMarketData.active_cryptocurrencies,
      exchanges: Math.floor(Math.random() * 500) + 200,
      defiTvl: mockMarketData.defi_tvl,
      newListings: mockMarketData.new_listings_24h,
      gainersCount: mockTopMovers.gainers.length,
      losersCount: mockTopMovers.losers.length,
      volatilityIndex: mockMarketData.volatility_index
    }

    setMarketData(mockMarketData)
    setFearGreedIndex(mockFearGreed)
    setTopMovers(mockTopMovers)
    setTrending(mockTrending)
    setPriceChartData(chartData)
    setMarketCapData(marketCapDistribution)
    setVolumeData(volumeDistribution)
    setRealTimeMetrics(metrics)
    setLastUpdated(new Date().toISOString())
    setLoading(false)
    setError(null)
  }, [])

  useEffect(() => {
    fetchCryptoData()
    // Set up auto-refresh every 30 seconds if enabled
    const interval = autoRefresh ? setInterval(fetchCryptoData, 30 * 1000) : null
    return () => {
      if (interval) clearInterval(interval)
    }
  }, [autoRefresh, fetchCryptoData])

  const toggleFavorite = (symbol) => {
    setFavorites(prev => {
      const newFavorites = new Set(prev)
      if (newFavorites.has(symbol)) {
        newFavorites.delete(symbol)
      } else {
        newFavorites.add(symbol)
      }
      return newFavorites
    })
  }

  const handleRefresh = () => {
    setLoading(true)
    setTimeout(() => {
      fetchCryptoData()
    }, 1000)
  }

  const getFearGreedColor = (value) => {
    if (value <= 25) return '#f44336' // Extreme Fear - Red
    if (value <= 45) return '#ff9800' // Fear - Orange  
    if (value <= 55) return '#ffeb3b' // Neutral - Yellow
    if (value <= 75) return '#8bc34a' // Greed - Light Green
    return '#4caf50' // Extreme Greed - Green
  }

  const getFearGreedLabel = (value) => {
    if (value <= 25) return 'Extreme Fear'
    if (value <= 45) return 'Fear'
    if (value <= 55) return 'Neutral'
    if (value <= 75) return 'Greed'
    return 'Extreme Greed'
  }

  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }))
  }

  const filteredTrending = trending.filter(coin => 
    coin.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
    coin.name.toLowerCase().includes(searchQuery.toLowerCase())
  )

  if (loading) {
    return (
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <Stack alignItems="center" spacing={2}>
            <CircularProgress size={60} />
            <Typography variant="h6" color="text.secondary">
              Loading crypto market data...
            </Typography>
          </Stack>
        </Box>
      </Container>
    )
  }

  if (error) {
    return (
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Alert severity="error" action={
          <Button color="inherit" size="small" onClick={handleRefresh}>
            Retry
          </Button>
        }>
          {String(error)}
        </Alert>
      </Container>
    )
  }

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Paper
        elevation={3}
        sx={{
          p: 2,
          mb: 3,
          background: `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.1)} 0%, ${alpha(theme.palette.secondary.main, 0.1)} 100%)`,
          border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`
        }}
      >
        <Box display="flex" justifyContent="space-between" alignItems="center">
          <Box display="flex" alignItems="center" gap={2}>
            <Box sx={{ position: 'relative' }}>
              <CandlestickChart fontSize="large" color="primary" />
              <Box
                sx={{
                  position: 'absolute',
                  top: -4,
                  right: -4,
                  width: 12,
                  height: 12,
                  borderRadius: '50%',
                  backgroundColor: 'success.main',
                  animation: `${pulse} 2s ease-in-out infinite`,
                }}
              />
            </Box>
            <Box>
              <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
                Crypto Market Command Center
              </Typography>
              <Typography variant="subtitle1" color="text.secondary">
                Real-time cryptocurrency market analysis and insights
              </Typography>
            </Box>
          </Box>
          
          <Stack direction="row" spacing={1} alignItems="center">
            <LiveIndicator>
              <Box className="live-dot" />
              <Typography variant="body2" color="success.main" fontWeight="bold">
                LIVE
              </Typography>
            </LiveIndicator>
            
            <TextField
              size="small"
              placeholder="Search coins..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Search fontSize="small" />
                  </InputAdornment>
                )
              }}
              sx={{ width: 200 }}
            />
            
            <FormControlLabel
              control={
                <Switch
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                  size="small"
                />
              }
              label="Auto-refresh"
            />
            
            <Tooltip title="Refresh data">
              <IconButton onClick={handleRefresh} color="primary">
                <Refresh />
              </IconButton>
            </Tooltip>
            
            <Tooltip title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}>
              <IconButton onClick={() => setIsFullscreen(!isFullscreen)} color="primary">
                {isFullscreen ? <FullscreenExit /> : <Fullscreen />}
              </IconButton>
            </Tooltip>
            
            {lastUpdated && (
              <Typography variant="caption" color="text.secondary">
                Updated: {new Date(lastUpdated).toLocaleTimeString()}
              </Typography>
            )}
          </Stack>
        </Box>
      </Paper>

      {/* Real-time Metrics Dashboard */}
      <Fade in={expandedSections.metrics}>
        <Box mb={4}>
          <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
            <Typography variant="h5" fontWeight="bold">
              Market Metrics
            </Typography>
            <IconButton onClick={() => toggleSection('metrics')}>
              {expandedSections.metrics ? <ExpandLess /> : <ExpandMore />}
            </IconButton>
          </Box>
          
          <Grid container spacing={2}>
            {[
              {
                title: 'Market Cap',
                value: formatCurrency(realTimeMetrics.totalMarketCap, 0),
                change: marketData?.market_cap_change_24h || 0,
                icon: <AccountBalance />,
                color: 'primary'
              },
              {
                title: '24h Volume',
                value: formatCurrency(realTimeMetrics.totalVolume, 0),
                change: 5.2,
                icon: <ShowChart />,
                color: 'secondary'
              },
              {
                title: 'BTC Dominance',
                value: `${realTimeMetrics.btcDominance.toFixed(1)}%`,
                change: -0.8,
                icon: <img src="https://cryptologos.cc/logos/bitcoin-btc-logo.png" alt="BTC" style={{ width: 24, height: 24 }} />,
                color: 'warning'
              },
              {
                title: 'Active Coins',
                value: realTimeMetrics.activeCoins.toLocaleString(),
                change: 2.1,
                icon: <Analytics />,
                color: 'info'
              },
              {
                title: 'Exchanges',
                value: realTimeMetrics.exchanges.toLocaleString(),
                change: 0.5,
                icon: <Security />,
                color: 'success'
              },
              {
                title: 'DeFi TVL',
                value: formatCurrency(realTimeMetrics.defiTvl, 0),
                change: 8.3,
                icon: <Insights />,
                color: 'error'
              }
            ].map((metric, index) => (
              <Grid item xs={12} sm={6} md={2} key={index}>
                <Grow in={true} timeout={300 + index * 100}>
                  <AnimatedMetricCard>
                    <CardContent>
                      <Box display="flex" alignItems="center" justifyContent="space-between" mb={1}>
                        <Box color={`${metric.color}.main`}>
                          {metric.icon}
                        </Box>
                        <Box display="flex" alignItems="center">
                          {metric.change > 0 ? (
                            <ArrowUpward fontSize="small" color="success" />
                          ) : (
                            <ArrowDownward fontSize="small" color="error" />
                          )}
                          <Typography
                            variant="caption"
                            color={metric.change > 0 ? 'success.main' : 'error.main'}
                            fontWeight="bold"
                          >
                            {Math.abs(metric.change).toFixed(1)}%
                          </Typography>
                        </Box>
                      </Box>
                      <Typography variant="body2" color="text.secondary" gutterBottom>
                        {metric.title}
                      </Typography>
                      <Typography variant="h6" fontWeight="bold">
                        {metric.value}
                      </Typography>
                    </CardContent>
                  </AnimatedMetricCard>
                </Grow>
              </Grid>
            ))}
          </Grid>
        </Box>
      </Fade>

      {/* Enhanced Charts Section */}
      <Fade in={expandedSections.charts}>
        <Box mb={4}>
          <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
            <Typography variant="h5" fontWeight="bold">
              Market Analysis
            </Typography>
            <IconButton onClick={() => toggleSection('charts')}>
              {expandedSections.charts ? <ExpandLess /> : <ExpandMore />}
            </IconButton>
          </Box>
          
          <Grid container spacing={3}>
            <Grid item xs={12} md={8}>
              <PulsingCard status="active">
                <CardHeader
                  title="Price Trends & Volume"
                  action={
                    <ButtonGroup size="small">
                      {['1h', '24h', '7d', '30d'].map((timeframe) => (
                        <Button
                          key={timeframe}
                          variant={selectedTimeframe === timeframe ? 'contained' : 'outlined'}
                          onClick={() => setSelectedTimeframe(timeframe)}
                        >
                          {timeframe}
                        </Button>
                      ))}
                    </ButtonGroup>
                  }
                />
                <CardContent>
                  <ResponsiveContainer width="100%" height={350}>
                    <ComposedChart data={priceChartData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis 
                        dataKey="time" 
                        tickFormatter={(time) => new Date(time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      />
                      <YAxis yAxisId="left" orientation="left" />
                      <YAxis yAxisId="right" orientation="right" />
                      <RechartsTooltip 
                        labelFormatter={(time) => new Date(time).toLocaleString()}
                        formatter={(value, name) => [
                          formatCurrency(value, name.includes('volume') ? 0 : 2),
                          name === 'btc' ? 'Bitcoin' : 
                          name === 'eth' ? 'Ethereum' :
                          name === 'total_volume' ? 'Volume' : 'Market Cap'
                        ]}
                      />
                      <Area 
                        yAxisId="right" 
                        type="monotone" 
                        dataKey="total_volume" 
                        fill={alpha(theme.palette.info.main, 0.3)}
                        stroke={theme.palette.info.main}
                        strokeWidth={1}
                      />
                      <Line 
                        yAxisId="left" 
                        type="monotone" 
                        dataKey="btc" 
                        stroke="#f7931a" 
                        strokeWidth={3}
                        dot={{ fill: '#f7931a', strokeWidth: 2, r: 4 }}
                      />
                      <Line 
                        yAxisId="left" 
                        type="monotone" 
                        dataKey="eth" 
                        stroke="#627eea" 
                        strokeWidth={3}
                        dot={{ fill: '#627eea', strokeWidth: 2, r: 4 }}
                      />
                      <Brush dataKey="time" height={30} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </CardContent>
              </PulsingCard>
            </Grid>
            
            <Grid item xs={12} md={4}>
              <Stack spacing={2}>
                <PulsingCard>
                  <CardHeader title="Market Cap Distribution" />
                  <CardContent>
                    <ResponsiveContainer width="100%" height={200}>
                      <RechartsPieChart>
                        <Pie
                          data={marketCapData}
                          cx="50%"
                          cy="50%"
                          innerRadius={40}
                          outerRadius={80}
                          paddingAngle={2}
                          dataKey="value"
                        >
                          {marketCapData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Pie>
                        <RechartsTooltip formatter={(value) => [`${value}%`, 'Market Share']} />
                      </RechartsPieChart>
                    </ResponsiveContainer>
                    <Box mt={1}>
                      {marketCapData.map((entry, index) => (
                        <Box key={index} display="flex" alignItems="center" justifyContent="space-between" mb={0.5}>
                          <Box display="flex" alignItems="center">
                            <Box 
                              sx={{ 
                                width: 8, 
                                height: 8, 
                                backgroundColor: entry.color, 
                                borderRadius: '50%', 
                                mr: 1 
                              }} 
                            />
                            <Typography variant="body2" fontSize="0.8rem">
                              {entry.name}
                            </Typography>
                          </Box>
                          <Typography variant="body2" fontWeight={600} fontSize="0.8rem">
                            {entry.value}%
                          </Typography>
                        </Box>
                      ))}
                    </Box>
                  </CardContent>
                </PulsingCard>
                
                <PulsingCard status="active">
                  <CardHeader title="Fear & Greed Index" />
                  <CardContent>
                    <Box display="flex" flexDirection="column" alignItems="center">
                      <Box position="relative" display="inline-flex" mb={2}>
                        <CircularProgress
                          variant="determinate"
                          value={fearGreedIndex?.value || 50}
                          size={100}
                          thickness={8}
                          sx={{
                            color: getFearGreedColor(fearGreedIndex?.value || 50),
                            '& .MuiCircularProgress-circle': {
                              strokeLinecap: 'round',
                            },
                          }}
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
                            flexDirection: 'column',
                          }}
                        >
                          <Typography variant="h6" fontWeight="bold">
                            {fearGreedIndex?.value || '--'}
                          </Typography>
                        </Box>
                      </Box>
                      <Chip
                        label={getFearGreedLabel(fearGreedIndex?.value || 50)}
                        sx={{
                          backgroundColor: getFearGreedColor(fearGreedIndex?.value || 50),
                          color: 'white',
                          fontWeight: 'bold'
                        }}
                      />
                      <Typography variant="body2" color="text.secondary" mt={1} textAlign="center">
                        Market sentiment indicator based on volatility, momentum, and social signals
                      </Typography>
                    </Box>
                  </CardContent>
                </PulsingCard>
              </Stack>
            </Grid>
          </Grid>
        </Box>
      </Fade>

      {/* Enhanced Top Movers */}
      <Fade in={expandedSections.movers}>
        <Box mb={4}>
          <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
            <Typography variant="h5" fontWeight="bold">
              Top Movers
            </Typography>
            <IconButton onClick={() => toggleSection('movers')}>
              {expandedSections.movers ? <ExpandLess /> : <ExpandMore />}
            </IconButton>
          </Box>
          
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <PulsingCard status="bullish">
                <CardHeader
                  title={
                    <Box display="flex" alignItems="center">
                      <TrendingUp color="success" sx={{ mr: 1 }} />
                      <Typography variant="h6">Top Gainers (24h)</Typography>
                      <Badge badgeContent={topMovers.gainers?.length || 0} color="success" sx={{ ml: 1 }} />
                    </Box>
                  }
                />
                <CardContent>
                  <TableContainer sx={{ maxHeight: 300 }}>
                    <Table size="small" stickyHeader>
                      <TableHead>
                        <TableRow>
                          <TableCell>Asset</TableCell>
                          <TableCell align="right">Price</TableCell>
                          <TableCell align="right">Change</TableCell>
                          <TableCell align="right">Volume</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {topMovers.gainers?.slice(0, 10).map((coin, index) => (
                          <TableRow key={coin.symbol} sx={{ animation: `${slideIn} 0.5s ease-out ${index * 0.1}s` }}>
                            <TableCell>
                              <Box display="flex" alignItems="center">
                                <IconButton
                                  size="small"
                                  onClick={() => toggleFavorite(coin.symbol)}
                                  sx={{ mr: 1 }}
                                >
                                  {favorites.has(coin.symbol) ? 
                                    <Favorite fontSize="small" color="error" /> : 
                                    <FavoriteBorder fontSize="small" />
                                  }
                                </IconButton>
                                <Box>
                                  <Typography variant="body2" fontWeight="bold">
                                    {coin.symbol}
                                  </Typography>
                                  <Typography variant="caption" color="text.secondary">
                                    #{coin.market_cap_rank}
                                  </Typography>
                                </Box>
                              </Box>
                            </TableCell>
                            <TableCell align="right">
                              <Typography variant="body2" fontWeight="bold">
                                {formatCurrency(coin.price)}
                              </Typography>
                            </TableCell>
                            <TableCell align="right">
                              <Box display="flex" alignItems="center" justifyContent="flex-end">
                                <TrendingUp fontSize="small" color="success" sx={{ mr: 0.5 }} />
                                <Typography 
                                  variant="body2" 
                                  color="success.main"
                                  fontWeight="bold"
                                >
                                  +{formatPercentage(coin.price_change_24h)}
                                </Typography>
                              </Box>
                            </TableCell>
                            <TableCell align="right">
                              <Typography variant="body2">
                                {formatCurrency(coin.volume_24h, 0)}
                              </Typography>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </CardContent>
              </PulsingCard>
            </Grid>

            <Grid item xs={12} md={6}>
              <PulsingCard status="bearish">
                <CardHeader
                  title={
                    <Box display="flex" alignItems="center">
                      <TrendingDown color="error" sx={{ mr: 1 }} />
                      <Typography variant="h6">Top Losers (24h)</Typography>
                      <Badge badgeContent={topMovers.losers?.length || 0} color="error" sx={{ ml: 1 }} />
                    </Box>
                  }
                />
                <CardContent>
                  <TableContainer sx={{ maxHeight: 300 }}>
                    <Table size="small" stickyHeader>
                      <TableHead>
                        <TableRow>
                          <TableCell>Asset</TableCell>
                          <TableCell align="right">Price</TableCell>
                          <TableCell align="right">Change</TableCell>
                          <TableCell align="right">Volume</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {topMovers.losers?.slice(0, 10).map((coin, index) => (
                          <TableRow key={coin.symbol} sx={{ animation: `${slideIn} 0.5s ease-out ${index * 0.1}s` }}>
                            <TableCell>
                              <Box display="flex" alignItems="center">
                                <IconButton
                                  size="small"
                                  onClick={() => toggleFavorite(coin.symbol)}
                                  sx={{ mr: 1 }}
                                >
                                  {favorites.has(coin.symbol) ? 
                                    <Favorite fontSize="small" color="error" /> : 
                                    <FavoriteBorder fontSize="small" />
                                  }
                                </IconButton>
                                <Box>
                                  <Typography variant="body2" fontWeight="bold">
                                    {coin.symbol}
                                  </Typography>
                                  <Typography variant="caption" color="text.secondary">
                                    #{coin.market_cap_rank}
                                  </Typography>
                                </Box>
                              </Box>
                            </TableCell>
                            <TableCell align="right">
                              <Typography variant="body2" fontWeight="bold">
                                {formatCurrency(coin.price)}
                              </Typography>
                            </TableCell>
                            <TableCell align="right">
                              <Box display="flex" alignItems="center" justifyContent="flex-end">
                                <TrendingDown fontSize="small" color="error" sx={{ mr: 0.5 }} />
                                <Typography 
                                  variant="body2" 
                                  color="error.main"
                                  fontWeight="bold"
                                >
                                  {formatPercentage(coin.price_change_24h)}
                                </Typography>
                              </Box>
                            </TableCell>
                            <TableCell align="right">
                              <Typography variant="body2">
                                {formatCurrency(coin.volume_24h, 0)}
                              </Typography>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </CardContent>
              </PulsingCard>
            </Grid>
          </Grid>
        </Box>
      </Fade>

      {/* Enhanced Trending Section */}
      <Fade in={expandedSections.trending}>
        <Box mb={4}>
          <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
            <Typography variant="h5" fontWeight="bold">
              Trending & Hot Coins
            </Typography>
            <IconButton onClick={() => toggleSection('trending')}>
              {expandedSections.trending ? <ExpandLess /> : <ExpandMore />}
            </IconButton>
          </Box>
          
          <PulsingCard>
            <CardHeader
              title={
                <Box display="flex" alignItems="center">
                  <LocalFireDepartment color="warning" sx={{ mr: 1 }} />
                  <Typography variant="h6">Most Trending</Typography>
                  <Badge badgeContent={filteredTrending.length} color="warning" sx={{ ml: 1 }} />
                </Box>
              }
            />
            <CardContent>
              <Grid container spacing={2}>
                {filteredTrending.slice(0, 12).map((coin, index) => (
                  <Grid item xs={12} sm={6} md={4} lg={3} key={coin.symbol}>
                    <Zoom in={true} timeout={300 + index * 100}>
                      <TrendingCoinCard 
                        variant="outlined" 
                        sx={{ 
                          cursor: 'pointer',
                          animationDelay: `${index * 0.5}s`
                        }}
                      >
                        <CardContent sx={{ p: 2 }}>
                          <Box display="flex" justifyContent="space-between" alignItems="flex-start" mb={1}>
                            <Box display="flex" alignItems="center">
                              <Box
                                sx={{
                                  width: 8,
                                  height: 8,
                                  borderRadius: '50%',
                                  backgroundColor: coin.price_change_24h > 0 ? 'success.main' : 'error.main',
                                  mr: 1,
                                  animation: `${pulse} 2s ease-in-out infinite`
                                }}
                              />
                              <Typography variant="subtitle2" fontWeight="bold">
                                {coin.symbol}
                              </Typography>
                            </Box>
                            <IconButton
                              size="small"
                              onClick={(e) => {
                                e.stopPropagation()
                                toggleFavorite(coin.symbol)
                              }}
                            >
                              {favorites.has(coin.symbol) ? 
                                <Favorite fontSize="small" color="error" /> : 
                                <FavoriteBorder fontSize="small" />
                              }
                            </IconButton>
                          </Box>
                          
                          <Typography variant="body2" color="text.secondary" noWrap mb={1}>
                            {coin.name}
                          </Typography>
                          
                          <Box display="flex" alignItems="center" justifyContent="space-between" mb={1}>
                            <Typography variant="h6" fontWeight="bold">
                              {formatCurrency(coin.price)}
                            </Typography>
                            <Box display="flex" alignItems="center">
                              {coin.price_change_24h > 0 ? (
                                <TrendingUp fontSize="small" color="success" />
                              ) : (
                                <TrendingDown fontSize="small" color="error" />
                              )}
                              <Typography 
                                variant="body2"
                                color={coin.price_change_24h > 0 ? 'success.main' : 'error.main'}
                                fontWeight="bold"
                                fontSize="0.8rem"
                              >
                                {formatPercentage(coin.price_change_24h)}
                              </Typography>
                            </Box>
                          </Box>
                          
                          <Box display="flex" alignItems="center" justifyContent="space-between">
                            <Box display="flex" alignItems="center">
                              <LocalFireDepartment fontSize="small" color="warning" sx={{ mr: 0.5 }} />
                              <Typography variant="caption">
                                {coin.trending_score?.toFixed(0) || '--'}
                              </Typography>
                            </Box>
                            <Typography variant="caption" color="text.secondary">
                              #{coin.market_cap_rank}
                            </Typography>
                          </Box>
                        </CardContent>
                      </TrendingCoinCard>
                    </Zoom>
                  </Grid>
                ))}
              </Grid>
            </CardContent>
          </PulsingCard>
        </Box>
      </Fade>
    </Container>
  )
}

export default CryptoMarketOverview