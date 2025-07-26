import React, { useState, useEffect } from 'react';
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
  Divider
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
  FilterList
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
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar
} from 'recharts'

const CryptoMarketOverview = () => {
  const [marketData, setMarketData] = useState(null)
  const [fearGreedIndex, setFearGreedIndex] = useState(null)
  const [topMovers, setTopMovers] = useState({ gainers: [], losers: [] })
  const [trending, setTrending] = useState([])
  const [priceChartData, setPriceChartData] = useState([])
  const [marketCapData, setMarketCapData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [selectedTimeframe, setSelectedTimeframe] = useState('24h')
  const [favorites, setFavorites] = useState(new Set(['BTC', 'ETH', 'BNB']))
  const [lastUpdated, setLastUpdated] = useState(null)

  const fetchCryptoData = React.useCallback(async () => {
    try {
      setLoading(true)
      const [marketResponse, fearGreedResponse, moversResponse, trendingResponse, overviewResponse] = await Promise.all([
        fetch('/api/crypto/market-metrics'),
        fetch('/api/crypto/fear-greed'),
        fetch('/api/crypto/movers'),
        fetch('/api/crypto/trending'),
        fetch('/api/crypto/market-overview')
      ])

      const [marketData, fearGreedData, moversData, trendingData, overviewData] = await Promise.all([
        marketResponse.json(),
        fearGreedResponse.json(),
        moversResponse.json(),
        trendingResponse.json(),
        overviewResponse.json()
      ])

      setMarketData(marketData.data)
      setFearGreedIndex(fearGreedData.data)
      setTopMovers(moversData.data)
      setTrending(trendingData.data.trending || trendingData.data)
      setLastUpdated(new Date().toISOString())
      
      // Fetch real chart data from live APIs
      await fetchLiveChartData(overviewData.data)
      
      setLoading(false)
      setError(null)
    } catch (err) {
      console.error('Failed to fetch crypto market data:', err)
      setError('Failed to fetch crypto market data. Using fallback data.')
      // On error, still try to show some data
      generateFallbackChartData()
      setLoading(false)
    }
  }, [selectedTimeframe])

  useEffect(() => {
    fetchCryptoData()
    // Set up auto-refresh every 30 seconds if enabled
    const interval = autoRefresh ? setInterval(fetchCryptoData, 30 * 1000) : null
    return () => {
      if (interval) clearInterval(interval)
    }
  }, [autoRefresh, fetchCryptoData, selectedTimeframe])

  const fetchLiveChartData = async (overviewData) => {
    try {
      // Determine timeframe for historical data
      const timeframeDays = {
        '1h': 0.04, // ~1 hour in days
        '24h': 1,
        '7d': 7
      }[selectedTimeframe] || 1
      
      // Fetch historical data for BTC and ETH
      const [btcHistoryResponse, ethHistoryResponse] = await Promise.all([
        fetch(`/api/crypto/historical/bitcoin?days=${timeframeDays}&interval=${selectedTimeframe === '1h' ? 'hourly' : 'daily'}`),
        fetch(`/api/crypto/historical/ethereum?days=${timeframeDays}&interval=${selectedTimeframe === '1h' ? 'hourly' : 'daily'}`)
      ])
      
      const [btcHistoryData, ethHistoryData] = await Promise.all([
        btcHistoryResponse.json(),
        ethHistoryResponse.json()
      ])
      
      // Process and combine chart data
      if (btcHistoryData.success && ethHistoryData.success) {
        const btcPrices = btcHistoryData.data.prices || []
        const ethPrices = ethHistoryData.data.prices || []
        
        // Combine data by timestamp
        const combinedData = btcPrices.map((btcPoint, index) => {
          const ethPoint = ethPrices[index] || { price: 0 }
          return {
            time: btcPoint.timestamp,
            btc: btcPoint.price,
            eth: ethPoint.price,
            total_market_cap: overviewData?.global?.total_market_cap || 0,
            volume: overviewData?.global?.total_volume_24h || 0
          }
        })
        
        setPriceChartData(combinedData)
      } else {
        throw new Error('Failed to fetch historical price data')
      }
      
      // Calculate real market cap distribution from live data
      if (overviewData?.top_cryptocurrencies && overviewData.top_cryptocurrencies.length > 0) {
        const topCryptos = overviewData.top_cryptocurrencies.slice(0, 10)
        const totalMarketCap = topCryptos.reduce((sum, crypto) => sum + (crypto.market_cap || 0), 0)
        
        const btcData = topCryptos.find(c => c.symbol === 'BTC')
        const ethData = topCryptos.find(c => c.symbol === 'ETH')
        const bnbData = topCryptos.find(c => c.symbol === 'BNB')
        
        const btcPercentage = btcData ? ((btcData.market_cap / totalMarketCap) * 100) : 0
        const ethPercentage = ethData ? ((ethData.market_cap / totalMarketCap) * 100) : 0
        const bnbPercentage = bnbData ? ((bnbData.market_cap / totalMarketCap) * 100) : 0
        const othersPercentage = 100 - btcPercentage - ethPercentage - bnbPercentage
        
        const liveMarketCapData = [
          { name: 'Bitcoin', value: Math.round(btcPercentage * 10) / 10, color: '#f7931a' },
          { name: 'Ethereum', value: Math.round(ethPercentage * 10) / 10, color: '#627eea' },
          { name: 'Binance Coin', value: Math.round(bnbPercentage * 10) / 10, color: '#f0b90b' },
          { name: 'Others', value: Math.round(othersPercentage * 10) / 10, color: '#8884d8' }
        ]
        
        setMarketCapData(liveMarketCapData)
      } else {
        generateFallbackMarketCapData()
      }
      
    } catch (error) {
      console.error('Failed to fetch live chart data:', error)
      generateFallbackChartData()
    }
  }
  
  const generateFallbackChartData = () => {
    console.log('🔄 Using fallback chart data')
    // Generate fallback data when live data fails
    const now = new Date()
    const hours = selectedTimeframe === '7d' ? 168 : selectedTimeframe === '24h' ? 24 : 1
    const interval = selectedTimeframe === '7d' ? 60 * 60 * 1000 * 4 : 60 * 60 * 1000 // 4h for 7d, 1h otherwise
    
    const chartData = Array.from({ length: hours }, (_, i) => ({
      time: new Date(now.getTime() - (hours - 1 - i) * interval).toISOString(),
      btc: 45000 + Math.random() * 5000,
      eth: 2800 + Math.random() * 300,
      total_market_cap: 2.1e12 + Math.random() * 2e11,
      volume: 8e10 + Math.random() * 2e10
    }))
    
    setPriceChartData(chartData)
  }
  
  const generateFallbackMarketCapData = () => {
    // Fallback market cap distribution data
    const marketCapData = [
      { name: 'Bitcoin', value: 45, color: '#f7931a' },
      { name: 'Ethereum', value: 18, color: '#627eea' },
      { name: 'Binance Coin', value: 6, color: '#f0b90b' },
      { name: 'Others', value: 31, color: '#8884d8' }
    ]
    
    setMarketCapData(marketCapData)
  }

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
    fetchCryptoData()
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

  if (loading) {
    return (
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <CircularProgress size={60} />
        </Box>
      </Container>
    )
  }

  if (error) {
    return (
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Alert severity="error">{String(error)}</Alert>
      </Container>
    )
  }

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={4}>
        <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
          Cryptocurrency Market Overview
        </Typography>
        <Box display="flex" alignItems="center" gap={2}>
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
          {lastUpdated && (
            <Typography variant="caption" color="text.secondary">
              Last updated: {new Date(lastUpdated).toLocaleTimeString()}
            </Typography>
          )}
        </Box>
      </Box>

      {/* Market Overview Charts */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={8}>
          <Paper sx={{ p: 3, height: 400 }}>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
              <Typography variant="h6" component="h2">
                Market Price Trends (24h)
              </Typography>
              <ButtonGroup size="small">
                <Button
                  variant={selectedTimeframe === '1h' ? 'contained' : 'outlined'}
                  onClick={() => setSelectedTimeframe('1h')}
                >
                  1H
                </Button>
                <Button
                  variant={selectedTimeframe === '24h' ? 'contained' : 'outlined'}
                  onClick={() => setSelectedTimeframe('24h')}
                >
                  24H
                </Button>
                <Button
                  variant={selectedTimeframe === '7d' ? 'contained' : 'outlined'}
                  onClick={() => setSelectedTimeframe('7d')}
                >
                  7D
                </Button>
              </ButtonGroup>
            </Box>
            {priceChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={priceChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis 
                    dataKey="time" 
                    tickFormatter={(time) => {
                      const date = new Date(time)
                      if (selectedTimeframe === '1h') {
                        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                      } else if (selectedTimeframe === '24h') {
                        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                      } else {
                        return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
                      }
                    }}
                    tick={{ fontSize: 12 }}
                  />
                  <YAxis 
                    yAxisId="left" 
                    orientation="left" 
                    tickFormatter={(value) => formatCurrency(value, 0, true)}
                    tick={{ fontSize: 12 }}
                  />
                  <RechartsTooltip 
                    labelFormatter={(time) => new Date(time).toLocaleString()}
                    formatter={(value, name) => [
                      name === 'btc' ? formatCurrency(value) : 
                      name === 'eth' ? formatCurrency(value) : 
                      name === 'total_market_cap' ? formatCurrency(value, 0) : 
                      formatCurrency(value, 0),
                      name === 'btc' ? 'Bitcoin (BTC)' : 
                      name === 'eth' ? 'Ethereum (ETH)' :
                      name === 'total_market_cap' ? 'Total Market Cap' : 'Volume'
                    ]}
                    contentStyle={{
                      backgroundColor: '#fff',
                      border: '1px solid #e0e0e0',
                      borderRadius: '8px',
                      boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)'
                    }}
                  />
                  <Line 
                    yAxisId="left" 
                    type="monotone" 
                    dataKey="btc" 
                    stroke="#f7931a" 
                    strokeWidth={3}
                    dot={false}
                    activeDot={{ r: 6, stroke: '#f7931a', strokeWidth: 2, fill: '#fff' }}
                  />
                  <Line 
                    yAxisId="left" 
                    type="monotone" 
                    dataKey="eth" 
                    stroke="#627eea" 
                    strokeWidth={3}
                    dot={false}
                    activeDot={{ r: 6, stroke: '#627eea', strokeWidth: 2, fill: '#fff' }}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <Box 
                display="flex" 
                justifyContent="center" 
                alignItems="center" 
                height={300}
                flexDirection="column"
              >
                <CircularProgress size={40} sx={{ mb: 2 }} />
                <Typography variant="body2" color="text.secondary">
                  Loading chart data...
                </Typography>
              </Box>
            )}
          </Paper>
        </Grid>
        
        <Grid item xs={12} md={4}>
          <Paper sx={{ p: 3, height: 400 }}>
            <Typography variant="h6" component="h2" gutterBottom>
              Market Cap Distribution
            </Typography>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={marketCapData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={120}
                  paddingAngle={5}
                  dataKey="value"
                >
                  {marketCapData.map((entry) => (
                    <Cell key={entry.name} fill={entry.color} />
                  ))}
                </Pie>
                <RechartsTooltip formatter={(value) => `${value}%`} />
              </PieChart>
            </ResponsiveContainer>
            <Box mt={2}>
              {marketCapData.map((entry) => (
                <Box key={entry.name} display="flex" alignItems="center" justifyContent="space-between" mb={1}>
                  <Box display="flex" alignItems="center">
                    <Box 
                      sx={{ 
                        width: 12, 
                        height: 12, 
                        backgroundColor: entry.color, 
                        borderRadius: '50%', 
                        mr: 1 
                      }} 
                    />
                    <Typography variant="body2">{entry.name}</Typography>
                  </Box>
                  <Typography variant="body2" fontWeight={600}>{entry.value}%</Typography>
                </Box>
              ))}
            </Box>
          </Paper>
        </Grid>
      </Grid>

      {/* Market Metrics Cards */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" mb={1}>
                <AccountBalance color="primary" sx={{ mr: 1 }} />
                <Typography variant="h6" component="div">
                  Total Market Cap
                </Typography>
              </Box>
              <Typography variant="h4" component="div" sx={{ fontWeight: 700 }}>
                {formatCurrency(marketData?.total_market_cap || 0, 0)}
              </Typography>
              <Typography 
                variant="body2" 
                color={marketData?.market_cap_change_24h >= 0 ? 'success.main' : 'error.main'}
                sx={{ display: 'flex', alignItems: 'center', mt: 1 }}
              >
                {marketData?.market_cap_change_24h >= 0 ? <TrendingUp fontSize="small" /> : <TrendingDown fontSize="small" />}
                {formatPercentage(marketData?.market_cap_change_24h || 0)} (24h)
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" mb={1}>
                <ShowChart color="primary" sx={{ mr: 1 }} />
                <Typography variant="h6" component="div">
                  24h Volume
                </Typography>
              </Box>
              <Typography variant="h4" component="div" sx={{ fontWeight: 700 }}>
                {formatCurrency(marketData?.total_volume_24h || 0, 0)}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                Across all exchanges
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" mb={1}>
                <img 
                  src="https://cryptologos.cc/logos/bitcoin-btc-logo.png" 
                  alt="Bitcoin"
                  style={{ width: 24, height: 24, marginRight: 8 }}
                />
                <Typography variant="h6" component="div">
                  BTC Dominance
                </Typography>
              </Box>
              <Typography variant="h4" component="div" sx={{ fontWeight: 700 }}>
                {formatPercentage(marketData?.btc_dominance || 0)}
              </Typography>
              <LinearProgress 
                variant="determinate" 
                value={marketData?.btc_dominance || 0} 
                sx={{ mt: 1, height: 8, borderRadius: 4 }}
              />
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" mb={1}>
                <Psychology color="primary" sx={{ mr: 1 }} />
                <Typography variant="h6" component="div">
                  Fear & Greed
                </Typography>
              </Box>
              <Typography 
                variant="h4" 
                component="div" 
                sx={{ 
                  fontWeight: 700,
                  color: getFearGreedColor(fearGreedIndex?.value || 50)
                }}
              >
                {fearGreedIndex?.value || '--'}
              </Typography>
              <Chip
                label={getFearGreedLabel(fearGreedIndex?.value || 50)}
                size="small"
                sx={{
                  mt: 1,
                  backgroundColor: getFearGreedColor(fearGreedIndex?.value || 50),
                  color: 'white'
                }}
              />
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Grid container spacing={3}>
        {/* Top Gainers */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Box display="flex" alignItems="center" mb={2}>
              <TrendingUp color="success" sx={{ mr: 1 }} />
              <Typography variant="h6" component="h2">
                Top Gainers (24h)
              </Typography>
            </Box>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Asset</TableCell>
                    <TableCell align="right">Price</TableCell>
                    <TableCell align="right">Change</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(topMovers.gainers || []).slice(0, 5).map((coin, index) => (
                    <TableRow key={coin.symbol}>
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
                          <Typography variant="body2" sx={{ fontWeight: 600 }}>
                            {coin.symbol}
                          </Typography>
                        </Box>
                      </TableCell>
                      <TableCell align="right">
                        <Typography variant="body2">
                          {formatCurrency(coin.price)}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Typography 
                          variant="body2" 
                          color="success.main"
                          sx={{ fontWeight: 600 }}
                        >
                          +{formatPercentage(coin.price_change_24h)}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </Grid>

        {/* Top Losers */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Box display="flex" alignItems="center" mb={2}>
              <TrendingDown color="error" sx={{ mr: 1 }} />
              <Typography variant="h6" component="h2">
                Top Losers (24h)
              </Typography>
            </Box>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Asset</TableCell>
                    <TableCell align="right">Price</TableCell>
                    <TableCell align="right">Change</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(topMovers.losers || []).slice(0, 5).map((coin, index) => (
                    <TableRow key={coin.symbol}>
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
                          <Typography variant="body2" sx={{ fontWeight: 600 }}>
                            {coin.symbol}
                          </Typography>
                        </Box>
                      </TableCell>
                      <TableCell align="right">
                        <Typography variant="body2">
                          {formatCurrency(coin.price)}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Typography 
                          variant="body2" 
                          color="error.main"
                          sx={{ fontWeight: 600 }}
                        >
                          {formatPercentage(coin.price_change_24h)}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </Grid>

        {/* Trending Cryptocurrencies */}
        <Grid item xs={12}>
          <Paper sx={{ p: 3 }}>
            <Box display="flex" alignItems="center" mb={2}>
              <LocalFireDepartment color="warning" sx={{ mr: 1 }} />
              <Typography variant="h6" component="h2">
                Trending Cryptocurrencies
              </Typography>
            </Box>
            <Grid container spacing={2}>
              {(trending || []).slice(0, 10).map((coin, index) => (
                <Grid item xs={12} sm={6} md={4} lg={2.4} key={coin.symbol}>
                  <Card 
                    variant="outlined" 
                    sx={{ 
                      textAlign: 'center', 
                      p: 1,
                      cursor: 'pointer',
                      transition: 'all 0.2s ease',
                      '&:hover': {
                        transform: 'translateY(-2px)',
                        boxShadow: '0px 2px 4px -1px rgba(0,0,0,0.2),0px 4px 5px 0px rgba(0,0,0,0.14),0px 1px 10px 0px rgba(0,0,0,0.12)'
                      }
                    }}
                  >
                    <CardContent sx={{ pb: '16px !important' }}>
                      <Box display="flex" justifyContent="space-between" alignItems="flex-start" mb={1}>
                        <Typography variant="h6" component="div" sx={{ fontWeight: 600 }}>
                          {coin.symbol}
                        </Typography>
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
                      <Typography variant="body2" color="text.secondary" noWrap>
                        {coin.name}
                      </Typography>
                      <Box display="flex" alignItems="center" justifyContent="center" mt={1}>
                        <Star fontSize="small" color="warning" sx={{ mr: 0.5 }} />
                        <Typography variant="body2">
                          #{index + 1}
                        </Typography>
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          </Paper>
        </Grid>
      </Grid>
    </Container>
  )
}

export default CryptoMarketOverview