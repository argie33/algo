import React, { useState, useEffect } from 'react'
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

  useEffect(() => {
    fetchCryptoData()
    // Set up auto-refresh every 30 seconds if enabled
    const interval = autoRefresh ? setInterval(fetchCryptoData, 30 * 1000) : null
    return () => {
      if (interval) clearInterval(interval)
    }
  }, [autoRefresh])

  const fetchCryptoData = async () => {
    try {
      setLoading(true)
      const [marketResponse, fearGreedResponse, moversResponse, trendingResponse] = await Promise.all([
        fetch('/api/crypto/market-metrics'),
        fetch('/api/crypto/fear-greed'),
        fetch('/api/crypto/movers'),
        fetch('/api/crypto/trending')
      ])

      const [marketData, fearGreedData, moversData, trendingData] = await Promise.all([
        marketResponse.json(),
        fearGreedResponse.json(),
        moversResponse.json(),
        trendingResponse.json()
      ])

      setMarketData(marketData.data)
      setFearGreedIndex(fearGreedData.data)
      setTopMovers(moversData.data)
      setTrending(trendingData.data)
      setLastUpdated(new Date().toISOString())
      
      // Generate sample chart data (in production, this would come from API)
      generateChartData()
      
      setLoading(false)
      setError(null)
    } catch (err) {
      setError('Failed to fetch crypto market data')
      setLoading(false)
    }
  }

  const generateChartData = () => {
    // Generate sample historical data for charts
    const now = new Date()
    const chartData = Array.from({ length: 24 }, (_, i) => ({
      time: new Date(now.getTime() - (23 - i) * 60 * 60 * 1000).toISOString(),
      btc: 45000 + Math.random() * 5000,
      eth: 2800 + Math.random() * 300,
      total_market_cap: 2.1e12 + Math.random() * 2e11,
      volume: 8e10 + Math.random() * 2e10
    }))
    
    setPriceChartData(chartData)
    
    // Market cap distribution data
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
      <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
        <div  display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={60} />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error">{String(error)}</div>
      </div>
    )
  }

  return (
    <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
      <div  display="flex" justifyContent="space-between" alignItems="center" mb={4}>
        <div  variant="h4" component="h1" sx={{ fontWeight: 700 }}>
          Cryptocurrency Market Overview
        </div>
        <div  display="flex" alignItems="center" gap={2}>
          <div className="mb-4"Label
            control={
              <input type="checkbox" className="toggle"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                size="small"
              />
            }
            label="Auto-refresh"
          />
          <div  title="Refresh data">
            <button className="p-2 rounded-full hover:bg-gray-100" onClick={handleRefresh} color="primary">
              <Refresh />
            </button>
          </div>
          {lastUpdated && (
            <div  variant="caption" color="text.secondary">
              Last updated: {new Date(lastUpdated).toLocaleTimeString()}
            </div>
          )}
        </div>
      </div>

      {/* Market Overview Charts */}
      <div className="grid" container spacing={3} sx={{ mb: 4 }}>
        <div className="grid" item xs={12} md={8}>
          <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 3, height: 400 }}>
            <div  display="flex" justifyContent="space-between" alignItems="center" mb={2}>
              <div  variant="h6" component="h2">
                Market Price Trends (24h)
              </div>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"Group size="small">
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  variant={selectedTimeframe === '1h' ? 'contained' : 'outlined'}
                  onClick={() => setSelectedTimeframe('1h')}
                >
                  1H
                </button>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  variant={selectedTimeframe === '24h' ? 'contained' : 'outlined'}
                  onClick={() => setSelectedTimeframe('24h')}
                >
                  24H
                </button>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  variant={selectedTimeframe === '7d' ? 'contained' : 'outlined'}
                  onClick={() => setSelectedTimeframe('7d')}
                >
                  7D
                </button>
              </ButtonGroup>
            </div>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={priceChartData}>
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
                    name === 'btc' ? formatCurrency(value) : 
                    name === 'eth' ? formatCurrency(value) : 
                    name === 'total_market_cap' ? formatCurrency(value, 0) : 
                    formatCurrency(value, 0),
                    name === 'btc' ? 'Bitcoin' : 
                    name === 'eth' ? 'Ethereum' :
                    name === 'total_market_cap' ? 'Market Cap' : 'Volume'
                  ]}
                />
                <Line 
                  yAxisId="left" 
                  type="monotone" 
                  dataKey="btc" 
                  stroke="#f7931a" 
                  strokeWidth={2}
                  dot={false}
                />
                <Line 
                  yAxisId="left" 
                  type="monotone" 
                  dataKey="eth" 
                  stroke="#627eea" 
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
        
        <div className="grid" item xs={12} md={4}>
          <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 3, height: 400 }}>
            <div  variant="h6" component="h2" gutterBottom>
              Market Cap Distribution
            </div>
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
                  {marketCapData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <RechartsTooltip formatter={(value) => `${value}%`} />
              </PieChart>
            </ResponsiveContainer>
            <div  mt={2}>
              {marketCapData.map((entry, index) => (
                <div  key={index} display="flex" alignItems="center" justifyContent="space-between" mb={1}>
                  <div  display="flex" alignItems="center">
                    <div  
                      sx={{ 
                        width: 12, 
                        height: 12, 
                        backgroundColor: entry.color, 
                        borderRadius: '50%', 
                        mr: 1 
                      }} 
                    />
                    <div  variant="body2">{entry.name}</div>
                  </div>
                  <div  variant="body2" fontWeight={600}>{entry.value}%</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Market Metrics Cards */}
      <div className="grid" container spacing={3} sx={{ mb: 4 }}>
        <div className="grid" item xs={12} sm={6} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  display="flex" alignItems="center" mb={1}>
                <AccountBalance color="primary" sx={{ mr: 1 }} />
                <div  variant="h6" component="div">
                  Total Market Cap
                </div>
              </div>
              <div  variant="h4" component="div" sx={{ fontWeight: 700 }}>
                {formatCurrency(marketData?.total_market_cap || 0, 0)}
              </div>
              <div  
                variant="body2" 
                color={marketData?.market_cap_change_24h >= 0 ? 'success.main' : 'error.main'}
                sx={{ display: 'flex', alignItems: 'center', mt: 1 }}
              >
                {marketData?.market_cap_change_24h >= 0 ? <TrendingUp fontSize="small" /> : <TrendingDown fontSize="small" />}
                {formatPercentage(marketData?.market_cap_change_24h || 0)} (24h)
              </div>
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} sm={6} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  display="flex" alignItems="center" mb={1}>
                <ShowChart color="primary" sx={{ mr: 1 }} />
                <div  variant="h6" component="div">
                  24h Volume
                </div>
              </div>
              <div  variant="h4" component="div" sx={{ fontWeight: 700 }}>
                {formatCurrency(marketData?.total_volume_24h || 0, 0)}
              </div>
              <div  variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                Across all exchanges
              </div>
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} sm={6} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  display="flex" alignItems="center" mb={1}>
                <img 
                  src="https://cryptologos.cc/logos/bitcoin-btc-logo.png" 
                  alt="Bitcoin"
                  style={{ width: 24, height: 24, marginRight: 8 }}
                />
                <div  variant="h6" component="div">
                  BTC Dominance
                </div>
              </div>
              <div  variant="h4" component="div" sx={{ fontWeight: 700 }}>
                {formatPercentage(marketData?.btc_dominance || 0)}
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2" 
                variant="determinate" 
                value={marketData?.btc_dominance || 0} 
                sx={{ mt: 1, height: 8, borderRadius: 4 }}
              />
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} sm={6} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  display="flex" alignItems="center" mb={1}>
                <Psychology color="primary" sx={{ mr: 1 }} />
                <div  variant="h6" component="div">
                  Fear & Greed
                </div>
              </div>
              <div  
                variant="h4" 
                component="div" 
                sx={{ 
                  fontWeight: 700,
                  color: getFearGreedColor(fearGreedIndex?.value || 50)
                }}
              >
                {fearGreedIndex?.value || '--'}
              </div>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                label={getFearGreedLabel(fearGreedIndex?.value || 50)}
                size="small"
                sx={{
                  mt: 1,
                  backgroundColor: getFearGreedColor(fearGreedIndex?.value || 50),
                  color: 'white'
                }}
              />
            </div>
          </div>
        </div>
      </div>

      <div className="grid" container spacing={3}>
        {/* Top Gainers */}
        <div className="grid" item xs={12} md={6}>
          <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 3 }}>
            <div  display="flex" alignItems="center" mb={2}>
              <TrendingUp color="success" sx={{ mr: 1 }} />
              <div  variant="h6" component="h2">
                Top Gainers (24h)
              </div>
            </div>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Asset</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Price</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Change</td>
                  </tr>
                </thead>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                  {topMovers.gainers?.slice(0, 10).map((coin, index) => (
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={coin.symbol}>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                        <div  display="flex" alignItems="center">
                          <button className="p-2 rounded-full hover:bg-gray-100"
                            size="small"
                            onClick={() => toggleFavorite(coin.symbol)}
                            sx={{ mr: 1 }}
                          >
                            {favorites.has(coin.symbol) ? 
                              <Favorite fontSize="small" color="error" /> : 
                              <FavoriteBorder fontSize="small" />
                            }
                          </button>
                          <div  variant="body2" sx={{ fontWeight: 600 }}>
                            {coin.symbol}
                          </div>
                        </div>
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        <div  variant="body2">
                          {formatCurrency(coin.price)}
                        </div>
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        <div  
                          variant="body2" 
                          color="success.main"
                          sx={{ fontWeight: 600 }}
                        >
                          +{formatPercentage(coin.price_change_24h)}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Top Losers */}
        <div className="grid" item xs={12} md={6}>
          <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 3 }}>
            <div  display="flex" alignItems="center" mb={2}>
              <TrendingDown color="error" sx={{ mr: 1 }} />
              <div  variant="h6" component="h2">
                Top Losers (24h)
              </div>
            </div>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Asset</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Price</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Change</td>
                  </tr>
                </thead>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                  {topMovers.losers?.slice(0, 10).map((coin, index) => (
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={coin.symbol}>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                        <div  display="flex" alignItems="center">
                          <button className="p-2 rounded-full hover:bg-gray-100"
                            size="small"
                            onClick={() => toggleFavorite(coin.symbol)}
                            sx={{ mr: 1 }}
                          >
                            {favorites.has(coin.symbol) ? 
                              <Favorite fontSize="small" color="error" /> : 
                              <FavoriteBorder fontSize="small" />
                            }
                          </button>
                          <div  variant="body2" sx={{ fontWeight: 600 }}>
                            {coin.symbol}
                          </div>
                        </div>
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        <div  variant="body2">
                          {formatCurrency(coin.price)}
                        </div>
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        <div  
                          variant="body2" 
                          color="error.main"
                          sx={{ fontWeight: 600 }}
                        >
                          {formatPercentage(coin.price_change_24h)}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Trending Cryptocurrencies */}
        <div className="grid" item xs={12}>
          <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 3 }}>
            <div  display="flex" alignItems="center" mb={2}>
              <LocalFireDepartment color="warning" sx={{ mr: 1 }} />
              <div  variant="h6" component="h2">
                Trending Cryptocurrencies
              </div>
            </div>
            <div className="grid" container spacing={2}>
              {trending?.slice(0, 10).map((coin, index) => (
                <div className="grid" item xs={12} sm={6} md={4} lg={2.4} key={coin.symbol}>
                  <div className="bg-white shadow-md rounded-lg" 
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
                    <div className="bg-white shadow-md rounded-lg"Content sx={{ pb: '16px !important' }}>
                      <div  display="flex" justifyContent="space-between" alignItems="flex-start" mb={1}>
                        <div  variant="h6" component="div" sx={{ fontWeight: 600 }}>
                          {coin.symbol}
                        </div>
                        <button className="p-2 rounded-full hover:bg-gray-100"
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
                        </button>
                      </div>
                      <div  variant="body2" color="text.secondary" noWrap>
                        {coin.name}
                      </div>
                      <div  display="flex" alignItems="center" justifyContent="center" mt={1}>
                        <Star fontSize="small" color="warning" sx={{ mr: 0.5 }} />
                        <div  variant="body2">
                          #{index + 1}
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
    </div>
  )
}

export default CryptoMarketOverview