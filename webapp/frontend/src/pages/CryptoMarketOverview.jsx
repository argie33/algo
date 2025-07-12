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
  useTheme,
  Alert,
  CircularProgress
} from '@mui/material'
import {
  TrendingUp,
  TrendingDown,
  ShowChart,
  AccountBalance,
  Psychology,
  LocalFireDepartment,
  Star
} from '@mui/icons-material'
import { formatCurrency, formatPercentage, formatLargeNumber } from '../utils/formatters'

const CryptoMarketOverview = () => {
  const theme = useTheme()
  const [marketData, setMarketData] = useState(null)
  const [fearGreedIndex, setFearGreedIndex] = useState(null)
  const [topMovers, setTopMovers] = useState({ gainers: [], losers: [] })
  const [trending, setTrending] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchCryptoData()
    // Set up auto-refresh every 5 minutes
    const interval = setInterval(fetchCryptoData, 5 * 60 * 1000)
    return () => clearInterval(interval)
  }, [])

  const fetchCryptoData = async () => {
    try {
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
      setLoading(false)
    } catch (err) {
      setError('Failed to fetch crypto market data')
      setLoading(false)
    }
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
      <Typography variant="h4" component="h1" gutterBottom sx={{ fontWeight: 700, mb: 4 }}>
        Cryptocurrency Market Overview
      </Typography>

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
                  {topMovers.gainers?.slice(0, 10).map((coin, index) => (
                    <TableRow key={coin.symbol}>
                      <TableCell>
                        <Box display="flex" alignItems="center">
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
                  {topMovers.losers?.slice(0, 10).map((coin, index) => (
                    <TableRow key={coin.symbol}>
                      <TableCell>
                        <Box display="flex" alignItems="center">
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
              {trending?.slice(0, 10).map((coin, index) => (
                <Grid item xs={12} sm={6} md={4} lg={2.4} key={coin.symbol}>
                  <Card variant="outlined" sx={{ textAlign: 'center', p: 1 }}>
                    <CardContent sx={{ pb: '16px !important' }}>
                      <Typography variant="h6" component="div" sx={{ fontWeight: 600 }}>
                        {coin.symbol}
                      </Typography>
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