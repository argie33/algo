import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { createComponentLogger } from '../utils/errorLogger'
import {
  Box,
  Card,
  CardContent,
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
  Chip
} from '@mui/material'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell, Legend } from 'recharts'
import { SentimentVerySatisfied, SentimentSatisfied, SentimentNeutral, SentimentDissatisfied, SentimentVeryDissatisfied, TrendingUp, TrendingDown, HorizontalRule } from '@mui/icons-material';

import { 
  getMarketOverview, 
  getMarketSentimentHistory, 
  getMarketSectorPerformance, 
  getMarketBreadth, 
  getEconomicIndicators 
} from '../services/api'
import { formatCurrency, formatNumber, formatPercentage, getChangeColor, getMarketCapCategory } from '../utils/formatters'

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8', '#82ca9d', '#ffc658', '#ff7c7c']

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

function MarketOverview() {
  // Restore original sentiment indicator boxes at the top, before the tabs
  const [sentimentRange, setSentimentRange] = useState(30);
  const [econRange, setEconRange] = useState(90);
  const [tabValue, setTabValue] = useState(0)
  const { data: marketData, isLoading: marketLoading, error: marketError } = useQuery({
    queryKey: ['market-overview'],
    queryFn: async () => {
      try {
        const result = await getMarketOverview();
        logger.success('getMarketOverview', result);
        return result;
      } catch (err) {
        logger.error('getMarketOverview', err);
        throw err;
      }
    },
    refetchInterval: 60000,
    onError: (err) => logger.queryError('market-overview', err)
  });

  const { data: sentimentData, isLoading: sentimentLoading } = useQuery({
    queryKey: ['market-sentiment-history', sentimentRange],
    queryFn: async () => {
      try {
        const result = await getMarketSentimentHistory(sentimentRange);
        logger.success('getMarketSentimentHistory', result, { days: sentimentRange });
        return result;
      } catch (err) {
        logger.error('getMarketSentimentHistory', err, { days: sentimentRange });
        throw err;
      }
    },
    enabled: tabValue === 1,
    onError: (err) => logger.queryError('market-sentiment-history', err)
  });

  const { data: sectorData, isLoading: sectorLoading } = useQuery({
    queryKey: ['market-sector-performance'],
    queryFn: async () => {
      try {
        const result = await getMarketSectorPerformance();
        logger.success('getMarketSectorPerformance', result);
        return result;
      } catch (err) {
        logger.error('getMarketSectorPerformance', err);
        throw err;
      }
    },
    enabled: tabValue === 2,
    onError: (err) => logger.queryError('market-sector-performance', err)
  });

  const { data: breadthData, isLoading: breadthLoading } = useQuery({
    queryKey: ['market-breadth'],
    queryFn: async () => {
      try {
        const result = await getMarketBreadth();
        logger.success('getMarketBreadth', result);
        return result;
      } catch (err) {
        logger.error('getMarketBreadth', err);
        throw err;
      }
    },
    enabled: tabValue === 3,
    onError: (err) => logger.queryError('market-breadth', err)
  });

  const { data: economicData, isLoading: economicLoading } = useQuery({
    queryKey: ['economic-indicators', econRange],
    queryFn: async () => {
      try {
        const result = await getEconomicIndicators(econRange);
        logger.success('getEconomicIndicators', result, { days: econRange });
        return result;
      } catch (err) {
        logger.error('getEconomicIndicators', err, { days: econRange });
        throw err;
      }
    },
    enabled: tabValue === 4,
    onError: (err) => logger.queryError('economic-indicators', err)
  });

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue)
  }
  if (marketError) {
    return (
      <Box>
        <Typography variant="h4" sx={{ mb: 3, fontWeight: 600 }}>
          Market Overview
        </Typography>
        <Alert severity="error">
          Failed to load market data: {marketError.message}
        </Alert>
      </Box>
    )
  }

  // Extract data from the new market API structure (robust to both old and new API shapes)
  const sentimentIndicators = marketData?.data?.sentiment_indicators ?? marketData?.sentiment_indicators ?? {};
  const marketBreadth = marketData?.data?.market_breadth ?? marketData?.market_breadth ?? {};
  const marketCap = marketData?.data?.market_cap ?? marketData?.market_cap ?? {};
  const economicIndicators = marketData?.data?.economic_indicators ?? marketData?.economic_indicators ?? [];
  
  const sectors = sectorData?.data?.sectors ?? sectorData?.sectors ?? [];
  const breadthInfo = breadthData?.data ?? breadthData ?? {};
  const sentimentHistory = sentimentData?.data ?? sentimentData ?? {}

  // Prepare chart data for sectors
  const sectorChartData = sectors.slice(0, 8).map(sector => ({
    name: sector.sector?.substring(0, 15) || 'Other',
    performance: parseFloat(sector.avg_change_percent) || 0,
    marketCap: parseFloat(sector.sector_market_cap) || 0,
    stocks: parseInt(sector.stock_count) || 0,
    advanceDeclineRatio: parseFloat(sector.advance_decline_ratio) || 0
  }))

  // Prepare sentiment chart data
  const fearGreedHistory = sentimentHistory.fear_greed_history || []
  const sentimentChartData = fearGreedHistory.slice(0, 30).map(item => ({
    date: new Date(item.timestamp).toLocaleDateString(),
    value: item.value,
    text: item.value_text
  })).reverse()

  // Helper: get icon and color for sentiment
  const getFGIcon = (value) => {
    if (value >= 75) return <SentimentVerySatisfied sx={{ color: '#43a047', fontSize: 36, mr: 1 }} />;
    if (value >= 55) return <SentimentSatisfied sx={{ color: '#8bc34a', fontSize: 36, mr: 1 }} />;
    if (value >= 45) return <SentimentNeutral sx={{ color: '#ffb300', fontSize: 36, mr: 1 }} />;
    if (value >= 25) return <SentimentDissatisfied sx={{ color: '#fb8c00', fontSize: 36, mr: 1 }} />;
    return <SentimentVeryDissatisfied sx={{ color: '#e53935', fontSize: 36, mr: 1 }} />;
  };

  return (
    <Box>
      {/* Executive Summary & Key Takeaways */}
      <Card sx={{ mb: 3, p: 2, background: 'linear-gradient(90deg, #f5f7fa 0%, #c3cfe2 100%)', boxShadow: 3 }}>
        <CardContent>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} md={8}>
              <Typography variant="h5" sx={{ fontWeight: 700, mb: 1 }}>
                Executive Market Summary
              </Typography>
              <Typography variant="body1" color="text.secondary">
                {marketData?.summary || (
                  <>
                    Stocks are mixed as investors weigh recent economic data and earnings. Sentiment remains <b>{sentimentIndicators.fear_greed?.value_text || 'neutral'}</b>, with sector rotation favoring <b>{sectors[0]?.sector || 'Technology'}</b>. Watch for upcoming macro events and volatility in global markets.
                  </>
                )}
              </Typography>
            </Grid>
            <Grid item xs={12} md={4}>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                <Typography variant="subtitle2" color="text.secondary">S&P 500</Typography>
                <Typography variant="h6" color={getChangeColor(marketData?.sp500_change || 0)}>
                  {marketData?.sp500_level ? formatNumber(marketData.sp500_level) : 'N/A'} ({marketData?.sp500_change ? formatPercentage(marketData.sp500_change) : 'N/A'})
                </Typography>
                <Typography variant="subtitle2" color="text.secondary">VIX</Typography>
                <Typography variant="h6" color={getChangeColor(marketData?.vix_change || 0)}>
                  {marketData?.vix_level ? marketData.vix_level.toFixed(2) : 'N/A'} ({marketData?.vix_change ? formatPercentage(marketData.vix_change) : 'N/A'})
                </Typography>
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Sentiment indicator boxes with icons and color cues */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={4}>
          <Card sx={{ borderLeft: '6px solid #1976d2', boxShadow: 2, height: '100%' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                {getFGIcon(Number(sentimentIndicators.fear_greed?.value))}
                <Typography variant="h6" sx={{ fontWeight: 700, ml: 1 }}>
                  Fear & Greed Index
                </Typography>
              </Box>
              {sentimentIndicators.fear_greed ? (
                <>
                  <Typography variant="h3" color="primary" sx={{ fontWeight: 700, mb: 1 }}>
                    {sentimentIndicators.fear_greed.value !== undefined ? Number(sentimentIndicators.fear_greed.value).toFixed(1) : 'N/A'}
                  </Typography>
                  <Chip label={sentimentIndicators.fear_greed.value_text} sx={{ mb: 1 }} />
                  <Typography variant="body2" color="text.secondary">
                    Last updated: {sentimentIndicators.fear_greed.timestamp ? new Date(sentimentIndicators.fear_greed.timestamp).toLocaleDateString() : 'N/A'}
                  </Typography>
                </>
              ) : (
                <Typography variant="body2" color="text.secondary">No data available</Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={4}>
          <Card sx={{ borderLeft: '6px solid #43a047', boxShadow: 2, height: '100%' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <TrendingUp sx={{ color: '#43a047', fontSize: 32, mr: 1 }} />
                <Typography variant="h6" sx={{ fontWeight: 700, ml: 1 }}>
                  AAII Investor Sentiment
                </Typography>
              </Box>
              {sentimentIndicators.aaii ? (
                <>
                  <Typography variant="body2" color="success.main">Bullish: <b>{sentimentIndicators.aaii.bullish !== undefined ? (Number(sentimentIndicators.aaii.bullish) * 100).toFixed(1) + '%' : 'N/A'}</b></Typography>
                  <Typography variant="body2" color="info.main">Neutral: <b>{sentimentIndicators.aaii.neutral !== undefined ? (Number(sentimentIndicators.aaii.neutral) * 100).toFixed(1) + '%' : 'N/A'}</b></Typography>
                  <Typography variant="body2" color="error.main">Bearish: <b>{sentimentIndicators.aaii.bearish !== undefined ? (Number(sentimentIndicators.aaii.bearish) * 100).toFixed(1) + '%' : 'N/A'}</b></Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                    Week ending: {sentimentIndicators.aaii.week_ending ? new Date(sentimentIndicators.aaii.week_ending).toLocaleDateString() : 'N/A'}
                  </Typography>
                </>
              ) : (
                <Typography variant="body2" color="text.secondary">No data available</Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={4}>
          <Card sx={{ borderLeft: '6px solid #8e24aa', boxShadow: 2, height: '100%' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <HorizontalRule sx={{ color: '#8e24aa', fontSize: 32, mr: 1 }} />
                <Typography variant="h6" sx={{ fontWeight: 700, ml: 1 }}>
                  NAAIM Exposure Index
                </Typography>
              </Box>
              {sentimentIndicators.naaim ? (
                <>
                  <Typography variant="body2">Average: <b>{sentimentIndicators.naaim.average !== undefined ? Number(sentimentIndicators.naaim.average).toFixed(1) + '%' : 'N/A'}</b></Typography>
                  <Typography variant="body2">Bullish: <b>{sentimentIndicators.naaim.bullish_8100 !== undefined ? Number(sentimentIndicators.naaim.bullish_8100).toFixed(1) + '%' : 'N/A'}</b></Typography>
                  <Typography variant="body2">Bearish: <b>{sentimentIndicators.naaim.bearish !== undefined ? Number(sentimentIndicators.naaim.bearish).toFixed(1) + '%' : 'N/A'}</b></Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                    Week ending: {sentimentIndicators.naaim.week_ending ? new Date(sentimentIndicators.naaim.week_ending).toLocaleDateString() : 'N/A'}
                  </Typography>
                </>
              ) : (
                <Typography variant="body2" color="text.secondary">No data available</Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Key Market Movers & Sector Rotation */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={6}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Top Gainers & Losers
              </Typography>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Ticker</TableCell>
                      <TableCell>Change</TableCell>
                      <TableCell>Sector</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(marketData?.top_movers || []).slice(0, 5).map((mover, idx) => (
                      <TableRow key={idx}>
                        <TableCell>{mover.ticker}</TableCell>
                        <TableCell sx={{ color: getChangeColor(mover.change) }}>{formatPercentage(mover.change)}</TableCell>
                        <TableCell>{mover.sector}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Sector Rotation
              </Typography>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={sectorChartData}>
                  <XAxis dataKey="name" hide />
                  <YAxis hide />
                  <Bar dataKey="performance">
                    {sectorChartData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <Box sx={{ mt: 1 }}>
                <Typography variant="body2" color="text.secondary">
                  Leading: <b>{sectorChartData[0]?.name || 'N/A'}</b>
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Lagging: <b>{sectorChartData[sectorChartData.length-1]?.name || 'N/A'}</b>
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Global Markets Snapshot */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
            Global Markets Snapshot
          </Typography>
          <Grid container spacing={2}>
            {(marketData?.global_indices || [
              { name: 'S&P 500', value: marketData?.sp500_level, change: marketData?.sp500_change },
              { name: 'NASDAQ', value: marketData?.nasdaq_level, change: marketData?.nasdaq_change },
              { name: 'Dow Jones', value: marketData?.dow_level, change: marketData?.dow_change },
              { name: 'FTSE 100', value: 8200, change: 0.2 },
              { name: 'DAX', value: 18000, change: -0.1 },
              { name: 'Nikkei 225', value: 39000, change: 0.3 },
              { name: 'Hang Seng', value: 18000, change: -0.4 }
            ]).slice(0, 6).map((idx, i) => (
              <Grid item xs={6} md={2} key={i}>
                <Paper sx={{ p: 2, textAlign: 'center', background: '#f8fafc', borderRadius: 2, boxShadow: 1 }}>
                  <Typography variant="subtitle2">{idx.name}</Typography>
                  <Typography variant="h6" color={getChangeColor(idx.change)}>
                    {idx.value ? formatNumber(idx.value) : 'N/A'}
                  </Typography>
                  <Typography variant="body2" color={getChangeColor(idx.change)}>
                    {idx.change ? formatPercentage(idx.change) : 'N/A'}
                  </Typography>
                </Paper>
              </Grid>
            ))}
          </Grid>
        </CardContent>
      </Card>

      {/* Macro & Event Radar */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
            Macro & Event Radar
          </Typography>
          <Grid container spacing={2}>
            {(marketData?.macro_events || [
              { date: new Date().toLocaleDateString(), event: 'FOMC Rate Decision', impact: 'High' },
              { date: new Date(Date.now() + 86400000).toLocaleDateString(), event: 'CPI Release', impact: 'High' },
              { date: new Date(Date.now() + 2*86400000).toLocaleDateString(), event: 'Jobs Report', impact: 'Medium' }
            ]).slice(0, 3).map((evt, i) => (
              <Grid item xs={12} md={4} key={i}>
                <Paper sx={{ p: 2, background: evt.impact === 'High' ? '#ffe0e0' : '#e0f7fa', borderRadius: 2, boxShadow: 1 }}>
                  <Typography variant="subtitle2">{evt.event}</Typography>
                  <Typography variant="body2" color="text.secondary">{evt.date}</Typography>
                  <Chip label={evt.impact} color={evt.impact === 'High' ? 'error' : 'info'} size="small" sx={{ mt: 1 }} />
                </Paper>
              </Grid>
            ))}
          </Grid>
        </CardContent>
      </Card>

      {/* Market Breadth */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Market Breadth
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Box sx={{ textAlign: 'center', p: 2, backgroundColor: 'success.light', borderRadius: 1 }}>
                    <Typography variant="h4" color="success.contrastText">
                      {marketBreadth.advancing !== undefined ? marketBreadth.advancing : 'N/A'}
                    </Typography>
                    <Typography variant="body2" color="success.contrastText">
                      Advancing
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={6}>
                  <Box sx={{ textAlign: 'center', p: 2, backgroundColor: 'error.light', borderRadius: 1 }}>
                    <Typography variant="h4" color="error.contrastText">
                      {marketBreadth.declining !== undefined ? marketBreadth.declining : 'N/A'}
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
                      Average Change: {marketBreadth.average_change_percent !== undefined ? marketBreadth.average_change_percent : 'N/A'}%
                    </Typography>
                  </Box>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
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
                  {marketBreadth.total_stocks !== undefined ? marketBreadth.total_stocks.toLocaleString() : 'N/A'}
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
                  {marketBreadth.unchanged !== undefined ? marketBreadth.unchanged : 'N/A'}
                </Typography>
              </Box>            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Tabs for different market data */}
      <Card>
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs value={tabValue} onChange={handleTabChange} aria-label="market data tabs">
            <Tab label="Market Overview" />
            <Tab label="Sentiment History" />
            <Tab label="Sector Performance" />
            <Tab label="Market Breadth" />
            <Tab label="Economic Indicators" />
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
          <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 2 }}>
            <Typography variant="body2">Range:</Typography>
            <Chip label="7d" color={sentimentRange === 7 ? 'primary' : 'default'} onClick={() => setSentimentRange(7)} clickable />
            <Chip label="30d" color={sentimentRange === 30 ? 'primary' : 'default'} onClick={() => setSentimentRange(30)} clickable />
            <Chip label="90d" color={sentimentRange === 90 ? 'primary' : 'default'} onClick={() => setSentimentRange(90)} clickable />
          </Box>
          {sentimentLoading ? (
            <LinearProgress />
          ) : (
            <Box>
              {/* Professional Sentiment Summary Row */}
              <Grid container spacing={3} sx={{ mb: 2 }}>
                <Grid item xs={12} md={4}>
                  <Card variant="outlined" sx={{ bgcolor: 'background.paper', boxShadow: 1 }}>
                    <CardContent>
                      <Typography variant="subtitle2" color="text.secondary">Fear & Greed</Typography>
                      <Typography variant="h4" color="primary" fontWeight={700}>
                        {sentimentChartData.length > 0 ? sentimentChartData[sentimentChartData.length-1].value : 'N/A'}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {sentimentChartData.length > 0 ? sentimentChartData[sentimentChartData.length-1].text : ''}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={12} md={4}>
                  <Card variant="outlined" sx={{ bgcolor: 'background.paper', boxShadow: 1 }}>
                    <CardContent>
                      <Typography variant="subtitle2" color="text.secondary">AAII Sentiment</Typography>
                      <Typography variant="body2" color="success.main">Bullish: {sentimentHistory?.aaii_history?.length && typeof sentimentHistory.aaii_history[sentimentHistory.aaii_history.length-1].bullish === 'number' ? (sentimentHistory.aaii_history[sentimentHistory.aaii_history.length-1].bullish*100).toFixed(1)+'%' : 'N/A'}</Typography>
                      <Typography variant="body2" color="info.main">Neutral: {sentimentHistory?.aaii_history?.length && typeof sentimentHistory.aaii_history[sentimentHistory.aaii_history.length-1].neutral === 'number' ? (sentimentHistory.aaii_history[sentimentHistory.aaii_history.length-1].neutral*100).toFixed(1)+'%' : 'N/A'}</Typography>
                      <Typography variant="body2" color="error.main">Bearish: {sentimentHistory?.aaii_history?.length && typeof sentimentHistory.aaii_history[sentimentHistory.aaii_history.length-1].bearish === 'number' ? (sentimentHistory.aaii_history[sentimentHistory.aaii_history.length-1].bearish*100).toFixed(1)+'%' : 'N/A'}</Typography>
                      <Typography variant="body2" color="text.secondary">
                        Week ending: {sentimentHistory?.aaii_history?.length ? new Date(sentimentHistory.aaii_history[sentimentHistory.aaii_history.length-1].date).toLocaleDateString() : 'N/A'}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={12} md={4}>
                  <Card variant="outlined" sx={{ bgcolor: 'background.paper', boxShadow: 1 }}>
                    <CardContent>
                      <Typography variant="subtitle2" color="text.secondary">NAAIM Exposure</Typography>
                      <Typography variant="h4" color="primary" fontWeight={700}>
                        {sentimentHistory?.naaim_history?.length && typeof sentimentHistory.naaim_history[sentimentHistory.naaim_history.length-1].average === 'number' ? sentimentHistory.naaim_history[sentimentHistory.naaim_history.length-1].average.toFixed(1)+'%' : 'N/A'}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Week ending: {sentimentHistory?.naaim_history?.length ? new Date(sentimentHistory.naaim_history[sentimentHistory.naaim_history.length-1].week_ending).toLocaleDateString() : 'N/A'}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>

              {/* Multi-line Sentiment History Chart */}
              <Card sx={{ mb: 2 }}>
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                    Sentiment History (30 Days)
                  </Typography>
                  <ResponsiveContainer width="100%" height={350}>
                    <LineChart>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" type="category" tick={{ fontSize: 12 }} />
                      <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
                      <Tooltip formatter={(value, name) => [`${value.toFixed(1)}%`, name]} />
                      <Legend verticalAlign="top" height={36} />
                      {/* Fear & Greed */}
                      <Line
                        dataKey="fearGreed"
                        data={sentimentChartData.map(d => ({ date: d.date, fearGreed: d.value }))}
                        name="Fear & Greed"
                        stroke="#8884d8"
                        strokeWidth={2}
                        dot={false}
                      />
                      {/* AAII Bullish */}
                      <Line
                        dataKey="aaiiBullish"
                        data={sentimentHistory?.aaii_history?.map(item => ({ date: new Date(item.date).toLocaleDateString(), aaiiBullish: item.bullish*100 })) || []}
                        name="AAII Bullish"
                        stroke="#43a047"
                        strokeWidth={2}
                        dot={false}
                      />
                      {/* AAII Bearish */}
                      <Line
                        dataKey="aaiiBearish"
                        data={sentimentHistory?.aaii_history?.map(item => ({ date: new Date(item.date).toLocaleDateString(), aaiiBearish: item.bearish*100 })) || []}
                        name="AAII Bearish"
                        stroke="#e53935"
                        strokeWidth={2}
                        dot={false}
                      />
                      {/* NAAIM Average */}
                      <Line
                        dataKey="naaimAvg"
                        data={sentimentHistory?.naaim_history?.map(item => ({ date: new Date(item.week_ending).toLocaleDateString(), naaimAvg: item.average })) || []}
                        name="NAAIM Avg"
                        stroke="#1976d2"
                        strokeWidth={2}
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
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
                        <Tooltip 
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
                          {sectors.slice(0, 8).map((sector, index) => (
                            <TableRow key={index}>
                              <TableCell>{sector.sector?.substring(0, 12) || 'N/A'}</TableCell>
                              <TableCell 
                                align="right"
                                sx={{ 
                                  color: getChangeColor(parseFloat(sector.avg_change_percent) || 0),
                                  fontWeight: 600
                                }}
                              >
                                {formatPercentage(parseFloat(sector.avg_change_percent) || 0)}
                              </TableCell>
                              <TableCell align="right">
                                {sector.stock_count || 0}
                              </TableCell>
                            </TableRow>
                          ))}
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
                        <Tooltip />
                      </PieChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={4}>
          <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 2 }}>
            <Typography variant="body2">Range:</Typography>
            <Chip label="30d" color={econRange === 30 ? 'primary' : 'default'} onClick={() => setEconRange(30)} clickable />
            <Chip label="90d" color={econRange === 90 ? 'primary' : 'default'} onClick={() => setEconRange(90)} clickable />
            <Chip label="180d" color={econRange === 180 ? 'primary' : 'default'} onClick={() => setEconRange(180)} clickable />
          </Box>
          {economicLoading ? (
            <LinearProgress />
          ) : (
            <Box>
              {/* Economic Indicators Summary Row */}
              <Card sx={{ mb: 2, background: 'linear-gradient(90deg, #f5f7fa 0%, #c3cfe2 100%)', boxShadow: 2 }}>
                <CardContent>
                  <Grid container spacing={2}>
                    {['CPI', 'Unemployment Rate', 'GDP', 'Fed Funds Rate'].map((key, idx) => {
                      const ind = economicData?.data?.find(i => i.name?.toLowerCase().includes(key.toLowerCase()));
                      return (
                        <Grid item xs={12} sm={6} md={3} key={key}>
                          <Box sx={{ p: 2, borderRadius: 2, background: '#fff', boxShadow: 1, textAlign: 'center' }}>
                            <Typography variant="subtitle2" color="text.secondary">{key}</Typography>
                            <Typography variant="h5" fontWeight={700} color={ind && parseFloat(ind.change_percent) > 0 ? 'success.main' : ind && parseFloat(ind.change_percent) < 0 ? 'error.main' : 'text.primary'}>
                              {ind ? `${ind.value} ${ind.unit}` : 'N/A'}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              Prev: {ind ? `${ind.previous_value} ${ind.unit}` : 'N/A'}
                            </Typography>
                            <Typography variant="body2" color={ind && parseFloat(ind.change_percent) > 0 ? 'success.main' : ind && parseFloat(ind.change_percent) < 0 ? 'error.main' : 'text.secondary'}>
                              {ind && ind.change_percent ? `${parseFloat(ind.change_percent).toFixed(2)}%` : 'N/A'}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {ind && ind.timestamp ? new Date(ind.timestamp).toLocaleDateString() : 'N/A'}
                            </Typography>
                          </Box>
                        </Grid>
                      );
                    })}
                  </Grid>
                </CardContent>
              </Card>

              {/* Grouped Economic Indicators Table */}
              <Card>
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                    Economic Indicators Table (Grouped)
                  </Typography>
                  <TableContainer>
                    <Table size="small">
                      <TableHead>
                        <TableRow sx={{ backgroundColor: 'grey.50' }}>
                          <TableCell sx={{ fontWeight: 600 }}>Category</TableCell>
                          <TableCell sx={{ fontWeight: 600 }}>Indicator</TableCell>
                          <TableCell align="right" sx={{ fontWeight: 600 }}>Current Value</TableCell>
                          <TableCell align="right" sx={{ fontWeight: 600 }}>Previous Value</TableCell>
                          <TableCell align="right" sx={{ fontWeight: 600 }}>Change</TableCell>
                          <TableCell align="right" sx={{ fontWeight: 600 }}>Date</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {(economicData?.data || []).sort((a, b) => (a.category || '').localeCompare(b.category || '')).map((indicator, index) => (
                          <TableRow key={index} hover>
                            <TableCell>{indicator.category || 'Other'}</TableCell>
                            <TableCell>
                              <Tooltip title={indicator.description || ''} arrow>
                                <span>{indicator.name || 'N/A'}</span>
                              </Tooltip>
                            </TableCell>
                            <TableCell align="right">
                              {indicator.value} {indicator.unit}
                            </TableCell>
                            <TableCell align="right">
                              {indicator.previous_value || 'N/A'} {indicator.unit}
                            </TableCell>
                            <TableCell 
                              align="right"
                              sx={{ color: getChangeColor(parseFloat(indicator.change_percent) || 0), fontWeight: 600 }}
                            >
                              {indicator.change_percent ? `${parseFloat(indicator.change_percent).toFixed(2)}%` : 'N/A'}
                            </TableCell>
                            <TableCell align="right">
                              {indicator.timestamp ? new Date(indicator.timestamp).toLocaleDateString() : 'N/A'}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
                    Data grouped by category. Hover indicator names for definitions. Last updated: {economicData?.data?.[0]?.timestamp ? new Date(economicData.data[0].timestamp).toLocaleString() : 'N/A'}
                  </Typography>
                </CardContent>
              </Card>
            </Box>
          )}
        </TabPanel>
      </Card>
    </Box>
  )
}

export default MarketOverview
