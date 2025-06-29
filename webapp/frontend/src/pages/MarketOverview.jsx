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
  Chip,
  Button,
  Accordion,
  AccordionSummary,
  AccordionDetails
} from '@mui/material'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell, Legend } from 'recharts'
import { SentimentVerySatisfied, SentimentSatisfied, SentimentNeutral, SentimentDissatisfied, SentimentVeryDissatisfied, TrendingUp, TrendingDown, HorizontalRule, Business, ExpandLess, ExpandMore, AccountBalance, ShowChart } from '@mui/icons-material';

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
  const [showDetailedEcon, setShowDetailedEcon] = useState(false);
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
        console.log('Economic data received:', result);
        console.log('Economic data structure:', {
          hasData: !!result?.data,
          dataLength: result?.data?.length || 0,
          firstItem: result?.data?.[0],
          periodDays: result?.period_days,
          totalPoints: result?.total_data_points
        });
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

  // Prepare sentiment chart data - updated for new API structure
  const fearGreedHistory = sentimentData?.fear_greed?.history || sentimentData?.data?.fear_greed?.history || []
  const sentimentChartData = fearGreedHistory.slice(0, 30).map(item => ({
    date: new Date(item.date).toLocaleDateString(),
    value: item.index_value,
    text: item.rating
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
              {/* Fear & Greed Accordion */}
              <Card sx={{ mb: 2 }}>
                <Accordion>
                  <AccordionSummary expandIcon={<ExpandMore />}>
                    <Box sx={{ display: 'flex', alignItems: 'center', width: '100%' }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', flex: 1 }}>
                        {getFGIcon(Number(sentimentData?.fear_greed?.current?.index_value))}
                        <Typography variant="h6" sx={{ fontWeight: 600, ml: 1 }}>
                          Fear & Greed Index
                        </Typography>
                      </Box>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                        <Typography variant="h4" color="primary" sx={{ fontWeight: 700 }}>
                          {sentimentData?.fear_greed?.current?.index_value ? 
                            Number(sentimentData.fear_greed.current.index_value).toFixed(1) : 'N/A'}
                        </Typography>
                        <Chip 
                          label={sentimentData?.fear_greed?.current?.rating || 'N/A'} 
                          color="primary" 
                          variant="outlined"
                        />
                      </Box>
                    </Box>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Grid container spacing={3}>
                      <Grid item xs={12} md={8}>
                        <Card>
                          <CardContent>
                            <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                              Fear & Greed Index History ({sentimentRange} Days)
                            </Typography>
                            <ResponsiveContainer width="100%" height={300}>
                              <LineChart data={sentimentData?.fear_greed?.history?.map(item => ({
                                date: new Date(item.date).toLocaleDateString(),
                                value: item.index_value,
                                rating: item.rating
                              })).reverse() || []}>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="date" />
                                <YAxis domain={[0, 100]} />
                                <Tooltip 
                                  formatter={(value, name) => [`${value}`, 'Index Value']}
                                  labelFormatter={(label) => `Date: ${label}`}
                                />
                                <Line 
                                  type="monotone" 
                                  dataKey="value" 
                                  stroke="#8884d8" 
                                  strokeWidth={3}
                                  dot={{ fill: '#8884d8', strokeWidth: 2, r: 4 }}
                                />
                              </LineChart>
                            </ResponsiveContainer>
                          </CardContent>
                        </Card>
                      </Grid>
                      <Grid item xs={12} md={4}>
                        <Card>
                          <CardContent>
                            <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                              Current Status
                            </Typography>
                            <Box sx={{ mb: 2 }}>
                              <Typography variant="body2" color="text.secondary">Index Value:</Typography>
                              <Typography variant="h4" color="primary" fontWeight={700}>
                                {sentimentData?.fear_greed?.current?.index_value ? 
                                  Number(sentimentData.fear_greed.current.index_value).toFixed(1) : 'N/A'}
                              </Typography>
                            </Box>
                            <Box sx={{ mb: 2 }}>
                              <Typography variant="body2" color="text.secondary">Rating:</Typography>
                              <Chip 
                                label={sentimentData?.fear_greed?.current?.rating || 'N/A'} 
                                color="primary"
                                sx={{ mt: 1 }}
                              />
                            </Box>
                            <Box>
                              <Typography variant="body2" color="text.secondary">Last Updated:</Typography>
                              <Typography variant="body2">
                                {sentimentData?.fear_greed?.current?.date ? 
                                  new Date(sentimentData.fear_greed.current.date).toLocaleDateString() : 'N/A'}
                              </Typography>
                            </Box>
                          </CardContent>
                        </Card>
                      </Grid>
                      <Grid item xs={12}>
                        <Card>
                          <CardContent>
                            <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                              Historical Data
                            </Typography>
                            <TableContainer>
                              <Table size="small">
                                <TableHead>
                                  <TableRow>
                                    <TableCell>Date</TableCell>
                                    <TableCell align="right">Index Value</TableCell>
                                    <TableCell>Rating</TableCell>
                                  </TableRow>
                                </TableHead>
                                <TableBody>
                                  {sentimentData?.fear_greed?.history?.slice(0, 20).map((item, index) => (
                                    <TableRow key={index} hover>
                                      <TableCell>
                                        {new Date(item.date).toLocaleDateString()}
                                      </TableCell>
                                      <TableCell align="right" sx={{ fontWeight: 600 }}>
                                        {Number(item.index_value).toFixed(1)}
                                      </TableCell>
                                      <TableCell>
                                        <Chip 
                                          label={item.rating} 
                                          size="small" 
                                          variant="outlined"
                                        />
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
                  </AccordionDetails>
                </Accordion>
              </Card>

              {/* AAII Sentiment Accordion */}
              <Card sx={{ mb: 2 }}>
                <Accordion>
                  <AccordionSummary expandIcon={<ExpandMore />}>
                    <Box sx={{ display: 'flex', alignItems: 'center', width: '100%' }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', flex: 1 }}>
                        <TrendingUp sx={{ color: '#43a047', fontSize: 32, mr: 1 }} />
                        <Typography variant="h6" sx={{ fontWeight: 600, ml: 1 }}>
                          AAII Investor Sentiment
                        </Typography>
                      </Box>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                        <Box sx={{ textAlign: 'center' }}>
                          <Typography variant="body2" color="success.main">Bullish</Typography>
                          <Typography variant="h5" color="success.main" fontWeight={700}>
                            {sentimentData?.aaii?.current?.bullish ? 
                              (Number(sentimentData.aaii.current.bullish) * 100).toFixed(1) + '%' : 'N/A'}
                          </Typography>
                        </Box>
                        <Box sx={{ textAlign: 'center' }}>
                          <Typography variant="body2" color="error.main">Bearish</Typography>
                          <Typography variant="h5" color="error.main" fontWeight={700}>
                            {sentimentData?.aaii?.current?.bearish ? 
                              (Number(sentimentData.aaii.current.bearish) * 100).toFixed(1) + '%' : 'N/A'}
                          </Typography>
                        </Box>
                      </Box>
                    </Box>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Grid container spacing={3}>
                      <Grid item xs={12} md={8}>
                        <Card>
                          <CardContent>
                            <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                              AAII Sentiment History ({sentimentRange} Days)
                            </Typography>
                            <ResponsiveContainer width="100%" height={300}>
                              <LineChart data={sentimentData?.aaii?.history?.map(item => ({
                                date: new Date(item.date).toLocaleDateString(),
                                bullish: Number(item.bullish) * 100,
                                neutral: Number(item.neutral) * 100,
                                bearish: Number(item.bearish) * 100
                              })).reverse() || []}>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="date" />
                                <YAxis domain={[0, 100]} />
                                <Tooltip 
                                  formatter={(value, name) => [`${value.toFixed(1)}%`, name]}
                                  labelFormatter={(label) => `Date: ${label}`}
                                />
                                <Legend />
                                <Line 
                                  type="monotone" 
                                  dataKey="bullish" 
                                  stroke="#43a047" 
                                  strokeWidth={2}
                                  name="Bullish"
                                />
                                <Line 
                                  type="monotone" 
                                  dataKey="neutral" 
                                  stroke="#ffb300" 
                                  strokeWidth={2}
                                  name="Neutral"
                                />
                                <Line 
                                  type="monotone" 
                                  dataKey="bearish" 
                                  stroke="#e53935" 
                                  strokeWidth={2}
                                  name="Bearish"
                                />
                              </LineChart>
                            </ResponsiveContainer>
                          </CardContent>
                        </Card>
                      </Grid>
                      <Grid item xs={12} md={4}>
                        <Card>
                          <CardContent>
                            <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                              Current Sentiment
                            </Typography>
                            <Box sx={{ mb: 2 }}>
                              <Typography variant="body2" color="success.main">Bullish:</Typography>
                              <Typography variant="h5" color="success.main" fontWeight={700}>
                                {sentimentData?.aaii?.current?.bullish ? 
                                  (Number(sentimentData.aaii.current.bullish) * 100).toFixed(1) + '%' : 'N/A'}
                              </Typography>
                            </Box>
                            <Box sx={{ mb: 2 }}>
                              <Typography variant="body2" color="info.main">Neutral:</Typography>
                              <Typography variant="h5" color="info.main" fontWeight={700}>
                                {sentimentData?.aaii?.current?.neutral ? 
                                  (Number(sentimentData.aaii.current.neutral) * 100).toFixed(1) + '%' : 'N/A'}
                              </Typography>
                            </Box>
                            <Box sx={{ mb: 2 }}>
                              <Typography variant="body2" color="error.main">Bearish:</Typography>
                              <Typography variant="h5" color="error.main" fontWeight={700}>
                                {sentimentData?.aaii?.current?.bearish ? 
                                  (Number(sentimentData.aaii.current.bearish) * 100).toFixed(1) + '%' : 'N/A'}
                              </Typography>
                            </Box>
                            <Box>
                              <Typography variant="body2" color="text.secondary">Week Ending:</Typography>
                              <Typography variant="body2">
                                {sentimentData?.aaii?.current?.date ? 
                                  new Date(sentimentData.aaii.current.date).toLocaleDateString() : 'N/A'}
                              </Typography>
                            </Box>
                          </CardContent>
                        </Card>
                      </Grid>
                      <Grid item xs={12}>
                        <Card>
                          <CardContent>
                            <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                              Historical Data
                            </Typography>
                            <TableContainer>
                              <Table size="small">
                                <TableHead>
                                  <TableRow>
                                    <TableCell>Date</TableCell>
                                    <TableCell align="right">Bullish (%)</TableCell>
                                    <TableCell align="right">Neutral (%)</TableCell>
                                    <TableCell align="right">Bearish (%)</TableCell>
                                  </TableRow>
                                </TableHead>
                                <TableBody>
                                  {sentimentData?.aaii?.history?.slice(0, 20).map((item, index) => (
                                    <TableRow key={index} hover>
                                      <TableCell>
                                        {new Date(item.date).toLocaleDateString()}
                                      </TableCell>
                                      <TableCell align="right" sx={{ color: 'success.main', fontWeight: 600 }}>
                                        {(Number(item.bullish) * 100).toFixed(1)}%
                                      </TableCell>
                                      <TableCell align="right" sx={{ color: 'info.main', fontWeight: 600 }}>
                                        {(Number(item.neutral) * 100).toFixed(1)}%
                                      </TableCell>
                                      <TableCell align="right" sx={{ color: 'error.main', fontWeight: 600 }}>
                                        {(Number(item.bearish) * 100).toFixed(1)}%
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
                  </AccordionDetails>
                </Accordion>
              </Card>

              {/* NAAIM Exposure Accordion */}
              <Card sx={{ mb: 2 }}>
                <Accordion>
                  <AccordionSummary expandIcon={<ExpandMore />}>
                    <Box sx={{ display: 'flex', alignItems: 'center', width: '100%' }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', flex: 1 }}>
                        <HorizontalRule sx={{ color: '#8e24aa', fontSize: 32, mr: 1 }} />
                        <Typography variant="h6" sx={{ fontWeight: 600, ml: 1 }}>
                          NAAIM Exposure Index
                        </Typography>
                      </Box>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                        <Box sx={{ textAlign: 'center' }}>
                          <Typography variant="body2">Average</Typography>
                          <Typography variant="h5" color="primary" fontWeight={700}>
                            {sentimentData?.naaim?.current?.mean_exposure ? 
                              Number(sentimentData.naaim.current.mean_exposure).toFixed(1) + '%' : 'N/A'}
                          </Typography>
                        </Box>
                        <Box sx={{ textAlign: 'center' }}>
                          <Typography variant="body2" color="success.main">Bullish</Typography>
                          <Typography variant="h5" color="success.main" fontWeight={700}>
                            {sentimentData?.naaim?.current?.bullish_exposure ? 
                              Number(sentimentData.naaim.current.bullish_exposure).toFixed(1) + '%' : 'N/A'}
                          </Typography>
                        </Box>
                        <Box sx={{ textAlign: 'center' }}>
                          <Typography variant="body2" color="error.main">Bearish</Typography>
                          <Typography variant="h5" color="error.main" fontWeight={700}>
                            {sentimentData?.naaim?.current?.bearish_exposure ? 
                              Number(sentimentData.naaim.current.bearish_exposure).toFixed(1) + '%' : 'N/A'}
                          </Typography>
                        </Box>
                      </Box>
                    </Box>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Grid container spacing={3}>
                      <Grid item xs={12} md={8}>
                        <Card>
                          <CardContent>
                            <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                              NAAIM Exposure History ({sentimentRange} Days)
                            </Typography>
                            <ResponsiveContainer width="100%" height={300}>
                              <LineChart data={sentimentData?.naaim?.history?.map(item => ({
                                date: new Date(item.date).toLocaleDateString(),
                                average: Number(item.mean_exposure),
                                bullish: Number(item.bullish_exposure),
                                bearish: Number(item.bearish_exposure)
                              })).reverse() || []}>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="date" />
                                <YAxis />
                                <Tooltip 
                                  formatter={(value, name) => [`${value.toFixed(1)}%`, name]}
                                  labelFormatter={(label) => `Date: ${label}`}
                                />
                                <Legend />
                                <Line 
                                  type="monotone" 
                                  dataKey="average" 
                                  stroke="#1976d2" 
                                  strokeWidth={3}
                                  name="Average Exposure"
                                  dot={{ fill: '#1976d2', strokeWidth: 2, r: 4 }}
                                />
                                <Line 
                                  type="monotone" 
                                  dataKey="bullish" 
                                  stroke="#43a047" 
                                  strokeWidth={2}
                                  name="Bullish Exposure"
                                />
                                <Line 
                                  type="monotone" 
                                  dataKey="bearish" 
                                  stroke="#e53935" 
                                  strokeWidth={2}
                                  name="Bearish Exposure"
                                />
                              </LineChart>
                            </ResponsiveContainer>
                          </CardContent>
                        </Card>
                      </Grid>
                      <Grid item xs={12} md={4}>
                        <Card>
                          <CardContent>
                            <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                              Current Exposure
                            </Typography>
                            <Box sx={{ mb: 2 }}>
                              <Typography variant="body2">Average Exposure:</Typography>
                              <Typography variant="h5" color="primary" fontWeight={700}>
                                {sentimentData?.naaim?.current?.mean_exposure ? 
                                  Number(sentimentData.naaim.current.mean_exposure).toFixed(1) + '%' : 'N/A'}
                              </Typography>
                            </Box>
                            <Box sx={{ mb: 2 }}>
                              <Typography variant="body2" color="success.main">Bullish Exposure:</Typography>
                              <Typography variant="h5" color="success.main" fontWeight={700}>
                                {sentimentData?.naaim?.current?.bullish_exposure ? 
                                  Number(sentimentData.naaim.current.bullish_exposure).toFixed(1) + '%' : 'N/A'}
                              </Typography>
                            </Box>
                            <Box sx={{ mb: 2 }}>
                              <Typography variant="body2" color="error.main">Bearish Exposure:</Typography>
                              <Typography variant="h5" color="error.main" fontWeight={700}>
                                {sentimentData?.naaim?.current?.bearish_exposure ? 
                                  Number(sentimentData.naaim.current.bearish_exposure).toFixed(1) + '%' : 'N/A'}
                              </Typography>
                            </Box>
                            <Box>
                              <Typography variant="body2" color="text.secondary">Week Ending:</Typography>
                              <Typography variant="body2">
                                {sentimentData?.naaim?.current?.date ? 
                                  new Date(sentimentData.naaim.current.date).toLocaleDateString() : 'N/A'}
                              </Typography>
                            </Box>
                          </CardContent>
                        </Card>
                      </Grid>
                      <Grid item xs={12}>
                        <Card>
                          <CardContent>
                            <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                              Historical Data
                            </Typography>
                            <TableContainer>
                              <Table size="small">
                                <TableHead>
                                  <TableRow>
                                    <TableCell>Date</TableCell>
                                    <TableCell align="right">Average (%)</TableCell>
                                    <TableCell align="right">Bullish (%)</TableCell>
                                    <TableCell align="right">Bearish (%)</TableCell>
                                  </TableRow>
                                </TableHead>
                                <TableBody>
                                  {sentimentData?.naaim?.history?.slice(0, 20).map((item, index) => (
                                    <TableRow key={index} hover>
                                      <TableCell>
                                        {new Date(item.date).toLocaleDateString()}
                                      </TableCell>
                                      <TableCell align="right" sx={{ fontWeight: 600 }}>
                                        {Number(item.mean_exposure).toFixed(1)}%
                                      </TableCell>
                                      <TableCell align="right" sx={{ color: 'success.main', fontWeight: 600 }}>
                                        {Number(item.bullish_exposure).toFixed(1)}%
                                      </TableCell>
                                      <TableCell align="right" sx={{ color: 'error.main', fontWeight: 600 }}>
                                        {Number(item.bearish_exposure).toFixed(1)}%
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
                  </AccordionDetails>
                </Accordion>
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
          
          {/* Debug Information */}
          {process.env.NODE_ENV === 'development' && economicData && (
            <Alert severity="info" sx={{ mb: 2 }}>
              <Typography variant="body2">
                <strong>Debug Info:</strong> Found {economicData.data?.length || 0} economic indicators
              </Typography>
              <Typography variant="caption" display="block">
                Available series: {economicData.data?.map(i => i.series_id).join(', ') || 'None'}
              </Typography>
            </Alert>
          )}
          
          {economicLoading ? (
            <LinearProgress />
          ) : (
            <Box>
              {/* Economic Indicators Summary Cards */}
              <Grid container spacing={3} sx={{ mb: 3 }}>
                {/* Inflation Summary */}
                <Grid item xs={12} md={6} lg={3}>
                  <Card sx={{ 
                    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                    color: 'white',
                    boxShadow: 3
                  }}>
                    <CardContent>
                      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                        <TrendingUp sx={{ mr: 1 }} />
                        <Typography variant="h6" fontWeight={600}>Inflation</Typography>
                      </Box>
                      {(() => {
                        const cpi = economicData?.data?.find(i => 
                          i.name?.toLowerCase().includes('cpi') ||
                          i.series_id?.toLowerCase().includes('cpi') ||
                          i.series_id === 'CPI' ||
                          i.series_id === 'CPILFESL'
                        );
                        const value = cpi?.value || 'N/A';
                        const change = parseFloat(cpi?.change_percent) || 0;
                        const trend = change > 0 ? 'Rising' : change < 0 ? 'Falling' : 'Stable';
                        const impact = change > 2 ? 'Bearish' : change < 1 ? 'Bullish' : 'Neutral';
                        
                        return (
                          <>
                            <Typography variant="h4" fontWeight={700} sx={{ mb: 1 }}>
                              {value}
                            </Typography>
                            <Typography variant="body2" sx={{ mb: 1 }}>
                              {trend} ({change > 0 ? '+' : ''}{change.toFixed(2)}%)
                            </Typography>
                            <Chip 
                              label={impact} 
                              size="small" 
                              sx={{ 
                                bgcolor: impact === 'Bullish' ? 'success.main' : 
                                         impact === 'Bearish' ? 'error.main' : 'grey.500',
                                color: 'white'
                              }}
                            />
                          </>
                        );
                      })()}
                    </CardContent>
                  </Card>
                </Grid>

                {/* Employment Summary */}
                <Grid item xs={12} md={6} lg={3}>
                  <Card sx={{ 
                    background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
                    color: 'white',
                    boxShadow: 3
                  }}>
                    <CardContent>
                      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                        <Business sx={{ mr: 1 }} />
                        <Typography variant="h6" fontWeight={600}>Employment</Typography>
                      </Box>
                      {(() => {
                        const unemployment = economicData?.data?.find(i => 
                          i.name?.toLowerCase().includes('unemployment') ||
                          i.series_id?.toLowerCase().includes('unemployment') ||
                          i.series_id === 'UNRATE' ||
                          i.series_id === 'NFP'
                        );
                        const value = unemployment?.value || 'N/A';
                        const change = parseFloat(unemployment?.change_percent) || 0;
                        const trend = change > 0 ? 'Rising' : change < 0 ? 'Falling' : 'Stable';
                        const impact = change > 0 ? 'Bearish' : change < 0 ? 'Bullish' : 'Neutral';
                        
                        return (
                          <>
                            <Typography variant="h4" fontWeight={700} sx={{ mb: 1 }}>
                              {value}%
                            </Typography>
                            <Typography variant="body2" sx={{ mb: 1 }}>
                              {trend} ({change > 0 ? '+' : ''}{change.toFixed(2)}%)
                            </Typography>
                            <Chip 
                              label={impact} 
                              size="small" 
                              sx={{ 
                                bgcolor: impact === 'Bullish' ? 'success.main' : 
                                         impact === 'Bearish' ? 'error.main' : 'grey.500',
                                color: 'white'
                              }}
                            />
                          </>
                        );
                      })()}
                    </CardContent>
                  </Card>
                </Grid>

                {/* Growth Summary */}
                <Grid item xs={12} md={6} lg={3}>
                  <Card sx={{ 
                    background: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
                    color: 'white',
                    boxShadow: 3
                  }}>
                    <CardContent>
                      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                        <ShowChart sx={{ mr: 1 }} />
                        <Typography variant="h6" fontWeight={600}>Growth</Typography>
                      </Box>
                      {(() => {
                        const gdp = economicData?.data?.find(i => 
                          i.name?.toLowerCase().includes('gdp') ||
                          i.series_id?.toLowerCase().includes('gdp') ||
                          i.series_id === 'GDP' ||
                          i.series_id === 'GDPC1'
                        );
                        const value = gdp?.value || 'N/A';
                        const change = parseFloat(gdp?.change_percent) || 0;
                        const trend = change > 0 ? 'Expanding' : change < 0 ? 'Contracting' : 'Stable';
                        const impact = change > 2 ? 'Bullish' : change < 0 ? 'Bearish' : 'Neutral';
                        
                        return (
                          <>
                            <Typography variant="h4" fontWeight={700} sx={{ mb: 1 }}>
                              {value}%
                            </Typography>
                            <Typography variant="body2" sx={{ mb: 1 }}>
                              {trend} ({change > 0 ? '+' : ''}{change.toFixed(2)}%)
                            </Typography>
                            <Chip 
                              label={impact} 
                              size="small" 
                              sx={{ 
                                bgcolor: impact === 'Bullish' ? 'success.main' : 
                                         impact === 'Bearish' ? 'error.main' : 'grey.500',
                                color: 'white'
                              }}
                            />
                          </>
                        );
                      })()}
                    </CardContent>
                  </Card>
                </Grid>

                {/* Monetary Policy Summary */}
                <Grid item xs={12} md={6} lg={3}>
                  <Card sx={{ 
                    background: 'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)',
                    color: 'white',
                    boxShadow: 3
                  }}>
                    <CardContent>
                      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                        <AccountBalance sx={{ mr: 1 }} />
                        <Typography variant="h6" fontWeight={600}>Fed Policy</Typography>
                      </Box>
                      {(() => {
                        const fedRate = economicData?.data?.find(i => 
                          i.name?.toLowerCase().includes('federal funds') ||
                          i.series_id?.toLowerCase().includes('fedfunds') ||
                          i.series_id === 'FEDFUNDS' ||
                          i.series_id === 'DGS10'
                        );
                        const value = fedRate?.value || 'N/A';
                        const change = parseFloat(fedRate?.change_percent) || 0;
                        const trend = change > 0 ? 'Tightening' : change < 0 ? 'Easing' : 'Stable';
                        const impact = change > 0 ? 'Bearish' : change < 0 ? 'Bullish' : 'Neutral';
                        
                        return (
                          <>
                            <Typography variant="h4" fontWeight={700} sx={{ mb: 1 }}>
                              {value}%
                            </Typography>
                            <Typography variant="body2" sx={{ mb: 1 }}>
                              {trend} ({change > 0 ? '+' : ''}{change.toFixed(2)}%)
                            </Typography>
                            <Chip 
                              label={impact} 
                              size="small" 
                              sx={{ 
                                bgcolor: impact === 'Bullish' ? 'success.main' : 
                                         impact === 'Bearish' ? 'error.main' : 'grey.500',
                                color: 'white'
                              }}
                            />
                          </>
                        );
                      })()}
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>

              {/* Fallback: Show Available Indicators if Specific Ones Not Found */}
              {economicData?.data && economicData.data.length > 0 && (
                (() => {
                  const hasSpecificIndicators = economicData.data.some(i => 
                    ['CPI', 'CPILFESL', 'UNRATE', 'NFP', 'GDP', 'GDPC1', 'FEDFUNDS', 'DGS10'].includes(i.series_id)
                  );
                  
                  if (!hasSpecificIndicators) {
                    return (
                      <Card sx={{ mb: 3 }}>
                        <CardContent>
                          <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                            Available Economic Indicators
                          </Typography>
                          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                            Specific indicators (CPI, Unemployment, GDP, Fed Rate) not found. Showing available data:
                          </Typography>
                          <Grid container spacing={2}>
                            {economicData.data.slice(0, 8).map((indicator, index) => (
                              <Grid item xs={12} sm={6} md={3} key={index}>
                                <Box sx={{ p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
                                  <Typography variant="subtitle2" fontWeight={600}>
                                    {indicator.name || indicator.series_id}
                                  </Typography>
                                  <Typography variant="h6" color="primary">
                                    {indicator.value} {indicator.unit}
                                  </Typography>
                                  <Typography variant="caption" color="text.secondary">
                                    {indicator.category}
                                  </Typography>
                                </Box>
                              </Grid>
                            ))}
                          </Grid>
                        </CardContent>
                      </Card>
                    );
                  }
                  return null;
                })()
              )}

              {/* Market Impact Analysis */}
              <Card sx={{ mb: 3 }}>
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                    Market Impact Analysis
                  </Typography>
                  <Grid container spacing={2}>
                    <Grid item xs={12} md={6}>
                      <Box sx={{ p: 2, bgcolor: 'grey.50', borderRadius: 2 }}>
                        <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>
                          Current Economic Environment
                        </Typography>
                        {(() => {
                          const indicators = economicData?.data || [];
                          const bullishCount = indicators.filter(i => parseFloat(i.change_percent) < 0).length;
                          const bearishCount = indicators.filter(i => parseFloat(i.change_percent) > 2).length;
                          const neutralCount = indicators.length - bullishCount - bearishCount;
                          
                          return (
                            <>
                              <Typography variant="body2" sx={{ mb: 1 }}>
                                Based on {indicators.length} key indicators:
                              </Typography>
                              <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
                                <Chip label={`${bullishCount} Bullish`} size="small" color="success" />
                                <Chip label={`${neutralCount} Neutral`} size="small" color="default" />
                                <Chip label={`${bearishCount} Bearish`} size="small" color="error" />
                              </Box>
                              <Typography variant="body2" color="text.secondary">
                                {bullishCount > bearishCount ? 'Overall economic conditions favor risk assets' :
                                 bearishCount > bullishCount ? 'Economic headwinds suggest defensive positioning' :
                                 'Mixed signals - selective opportunities likely'}
                              </Typography>
                            </>
                          );
                        })()}
                      </Box>
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <Box sx={{ p: 2, bgcolor: 'grey.50', borderRadius: 2 }}>
                        <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>
                          Key Insights
                        </Typography>
                        <Box component="ul" sx={{ pl: 2, m: 0 }}>
                          <Typography component="li" variant="body2" sx={{ mb: 0.5 }}>
                            Inflation trends suggest {(() => {
                              const cpi = economicData?.data?.find(i => i.name?.toLowerCase().includes('cpi'));
                              return parseFloat(cpi?.change_percent) > 2 ? 'continued pressure on growth stocks' : 'supportive environment for equities';
                            })()}
                          </Typography>
                          <Typography component="li" variant="body2" sx={{ mb: 0.5 }}>
                            Employment data indicates {(() => {
                              const unemployment = economicData?.data?.find(i => i.name?.toLowerCase().includes('unemployment'));
                              return parseFloat(unemployment?.change_percent) > 0 ? 'potential economic slowdown' : 'resilient consumer spending';
                            })()}
                          </Typography>
                          <Typography component="li" variant="body2" sx={{ mb: 0.5 }}>
                            Fed policy stance is {(() => {
                              const fedRate = economicData?.data?.find(i => i.name?.toLowerCase().includes('federal funds'));
                              return parseFloat(fedRate?.change_percent) > 0 ? 'restrictive - favor defensive sectors' : 'accommodative - growth opportunities';
                            })()}
                          </Typography>
                        </Box>
                      </Box>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>

              {/* Detailed Data Section - Collapsible */}
              <Card>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      Detailed Economic Data
                    </Typography>
                    <Button
                      variant="outlined"
                      size="small"
                      onClick={() => setShowDetailedEcon(!showDetailedEcon)}
                      endIcon={showDetailedEcon ? <ExpandLess /> : <ExpandMore />}
                    >
                      {showDetailedEcon ? 'Hide Details' : 'View All Data'}
                    </Button>
                  </Box>
                  
                  {showDetailedEcon && (
                    <>
                      {economicData?.data && economicData.data.length > 0 ? (
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
                              {economicData.data.sort((a, b) => (a.category || '').localeCompare(b.category || '')).map((indicator, index) => (
                                <TableRow key={index} hover>
                                  <TableCell>{indicator.category || 'Other'}</TableCell>
                                  <TableCell>
                                    <Tooltip title={indicator.description || ''} arrow>
                                      <span>{indicator.name || indicator.series_id || 'N/A'}</span>
                                    </Tooltip>
                                  </TableCell>
                                  <TableCell align="right">
                                    {indicator.value !== null && indicator.value !== undefined ? `${indicator.value} ${indicator.unit}` : 'N/A'}
                                  </TableCell>
                                  <TableCell align="right">
                                    {indicator.previous_value !== null && indicator.previous_value !== undefined ? `${indicator.previous_value} ${indicator.unit}` : 'N/A'}
                                  </TableCell>
                                  <TableCell 
                                    align="right"
                                    sx={{ color: getChangeColor(parseFloat(indicator.change_percent) || 0), fontWeight: 600 }}
                                  >
                                    {indicator.change_percent !== null && indicator.change_percent !== undefined ? `${parseFloat(indicator.change_percent).toFixed(2)}%` : 'N/A'}
                                  </TableCell>
                                  <TableCell align="right">
                                    {indicator.timestamp ? new Date(indicator.timestamp).toLocaleDateString() : 'N/A'}
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </TableContainer>
                      ) : (
                        <Box sx={{ textAlign: 'center', py: 4 }}>
                          <Typography variant="body1" color="text.secondary">
                            No economic data available for the selected time period.
                          </Typography>
                        </Box>
                      )}
                    </>
                  )}
                  
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
                    Last updated: {economicData?.data?.[0]?.timestamp ? new Date(economicData.data[0].timestamp).toLocaleString() : 'N/A'}
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
