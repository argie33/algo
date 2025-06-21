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
  Tooltip,
  CircularProgress
} from '@mui/material'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell, Legend } from 'recharts'
import AssessmentIcon from '@mui/icons-material/Assessment';
import SentimentVeryDissatisfiedIcon from '@mui/icons-material/SentimentVeryDissatisfied';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import SentimentNeutralIcon from '@mui/icons-material/SentimentNeutral';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';

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

function MarketOverview() {  const [tabValue, setTabValue] = useState(0)
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
    queryKey: ['market-sentiment-history'],
    queryFn: async () => {
      try {
        const result = await getMarketSentimentHistory(30);
        logger.success('getMarketSentimentHistory', result, { days: 30 });
        return result;
      } catch (err) {
        logger.error('getMarketSentimentHistory', err, { days: 30 });
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
    queryKey: ['economic-indicators'],
    queryFn: async () => {
      try {
        const result = await getEconomicIndicators(90);
        logger.success('getEconomicIndicators', result, { days: 90 });
        return result;
      } catch (err) {
        logger.error('getEconomicIndicators', err, { days: 90 });
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
          Failed to load market data: {marketError.message || JSON.stringify(marketError)}
        </Alert>
      </Box>
    )
  }

  // Extract data from the new market API structure
  const sentimentIndicators = marketData?.data?.sentiment_indicators || {}
  const marketBreadth = marketData?.data?.market_breadth || {}
  const marketCap = marketData?.data?.market_cap || {}
  const economicIndicators = marketData?.data?.economic_indicators || []
  
  const sectors = sectorData?.data?.sectors || []
  const breadthInfo = breadthData?.data || {}
  const sentimentHistory = sentimentData?.data || {}

  // Prepare chart data for sectors
  const sectorChartData = sectors.slice(0, 8).map(sector => ({
    name: sector.sector?.substring(0, 15) || 'Other',
    performance: parseFloat(sector.avg_change_percent) || 0,
    marketCap: parseFloat(sector.sector_market_cap) || 0,
    stocks: parseInt(sector.stock_count) || 0,
    advanceDeclineRatio: parseFloat(sector.advance_decline_ratio) || 0
  }))

  // Prepare sentiment chart data
  const fearGreedHistory = sentimentHistory.fear_greed_history || [];
  const naaimHistory = sentimentHistory.naaim_history || [];
  const aaiiHistory = sentimentHistory.aaii_history || [];

  // Prepare chart data for all three
  const sentimentChartData = Array.from({ length: 30 }, (_, i) => {
    const fg = fearGreedHistory[i] || {};
    const naaim = naaimHistory[i] || {};
    const aaii = aaiiHistory[i] || {};
    return {
      date: fg.date ? new Date(fg.date).toLocaleDateString() : naaim.date ? new Date(naaim.date).toLocaleDateString() : aaii.date ? new Date(aaii.date).toLocaleDateString() : '',
      fear_greed: fg.index_value ?? null,
      naaim: naaim.mean_exposure ?? null,
      aaii_bullish: aaii.bullish !== undefined ? aaii.bullish * 100 : null,
      aaii_neutral: aaii.neutral !== undefined ? aaii.neutral * 100 : null,
      aaii_bearish: aaii.bearish !== undefined ? aaii.bearish * 100 : null
    };
  }).reverse()

  return (
    <Box>
      <Typography variant="h4" sx={{ mb: 3, fontWeight: 600 }}>
        Market Overview
      </Typography>

      {marketLoading && <LinearProgress sx={{ mb: 2 }} />}

      {/* Market Sentiment Indicators - FANCY VERSION */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        {/* Fear & Greed */}
        <Grid item xs={12} md={4}>
          <Card sx={{
            background: 'linear-gradient(135deg, #f8fafc 60%, #e3f2fd 100%)',
            boxShadow: 6,
            borderRadius: 3,
            position: 'relative',
            overflow: 'visible',
            minHeight: 220
          }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <AssessmentIcon sx={{ fontSize: 44, color: '#1976d2', mr: 1 }} />
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  Fear & Greed Index
                </Typography>
                <Tooltip title="Measures market sentiment from extreme fear to extreme greed" placement="top">
                  <InfoOutlinedIcon sx={{ ml: 1, color: 'grey.500' }} />
                </Tooltip>
              </Box>
              {sentimentIndicators.fear_greed ? (
                <Box sx={{ mt: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <Typography variant="body1" sx={{ fontWeight: 700, minWidth: 90 }}>Value:</Typography>
                    <Typography variant="body1" color="primary.main" sx={{ fontWeight: 700, fontSize: 28, ml: 1 }}>
                      {sentimentIndicators.fear_greed.value !== undefined ? Number(sentimentIndicators.fear_greed.value).toFixed(1) : 'N/A'}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <Typography variant="body1" sx={{ fontWeight: 700, minWidth: 90 }}>Rating:</Typography>
                    <Chip 
                      label={sentimentIndicators.fear_greed.value_text} 
                      color={
                        sentimentIndicators.fear_greed.value > 75 ? 'error' :
                        sentimentIndicators.fear_greed.value > 55 ? 'warning' :
                        sentimentIndicators.fear_greed.value > 45 ? 'info' :
                        sentimentIndicators.fear_greed.value > 25 ? 'warning' : 'success'
                      }
                      sx={{ fontWeight: 700, fontSize: 16, ml: 1 }}
                    />
                  </Box>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                    Last updated: {sentimentIndicators.fear_greed.timestamp ? new Date(sentimentIndicators.fear_greed.timestamp).toLocaleDateString() : 'N/A'}
                  </Typography>
                </Box>
              ) : (
                <Typography variant="body2" color="text.secondary">No data available</Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
        {/* AAII Sentiment */}
        <Grid item xs={12} md={4}>
          <Card sx={{
            background: 'linear-gradient(135deg, #f8fafc 60%, #fffde7 100%)',
            boxShadow: 6,
            borderRadius: 3,
            position: 'relative',
            overflow: 'visible',
            minHeight: 220
          }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <SentimentNeutralIcon sx={{ fontSize: 48, color: '#fbc02d', mr: 1 }} />
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  AAII Investor Sentiment
                </Typography>
                <Tooltip title="Weekly survey of individual investor sentiment (bullish, neutral, bearish)" placement="top">
                  <InfoOutlinedIcon sx={{ ml: 1, color: 'grey.500' }} />
                </Tooltip>
              </Box>
              {sentimentIndicators.aaii ? (
                <Box sx={{ mt: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <TrendingUpIcon sx={{ color: '#388e3c', mr: 1 }} />
                    <Typography variant="body1" sx={{ fontWeight: 700, minWidth: 70 }}>Bullish:</Typography>
                    <Typography variant="body1" color="success.main" sx={{ fontWeight: 700 }}>
                      {sentimentIndicators.aaii.bullish !== undefined ? (sentimentIndicators.aaii.bullish * 100).toFixed(1) + '%' : 'N/A'}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <SentimentNeutralIcon sx={{ color: '#fbc02d', mr: 1 }} />
                    <Typography variant="body1" sx={{ fontWeight: 700, minWidth: 70 }}>Neutral:</Typography>
                    <Typography variant="body1" color="warning.main" sx={{ fontWeight: 700 }}>
                      {sentimentIndicators.aaii.neutral !== undefined ? (sentimentIndicators.aaii.neutral * 100).toFixed(1) + '%' : 'N/A'}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <TrendingDownIcon sx={{ color: '#d32f2f', mr: 1 }} />
                    <Typography variant="body1" sx={{ fontWeight: 700, minWidth: 70 }}>Bearish:</Typography>
                    <Typography variant="body1" color="error.main" sx={{ fontWeight: 700 }}>
                      {sentimentIndicators.aaii.bearish !== undefined ? (sentimentIndicators.aaii.bearish * 100).toFixed(1) + '%' : 'N/A'}
                    </Typography>
                  </Box>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                    Week ending: {sentimentIndicators.aaii.week_ending ? new Date(sentimentIndicators.aaii.week_ending).toLocaleDateString() : 'N/A'}
                  </Typography>
                </Box>
              ) : (
                <Typography variant="body2" color="text.secondary">No data available</Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
        {/* NAAIM Sentiment */}
        <Grid item xs={12} md={4}>
          <Card sx={{
            background: 'linear-gradient(135deg, #f8fafc 60%, #e8f5e9 100%)',
            boxShadow: 6,
            borderRadius: 3,
            position: 'relative',
            overflow: 'visible',
            minHeight: 220
          }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <TrendingUpIcon sx={{ fontSize: 48, color: '#388e3c', mr: 1 }} />
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  NAAIM Exposure Index
                </Typography>
                <Tooltip title="Active manager equity exposure (average, bullish, bearish)" placement="top">
                  <InfoOutlinedIcon sx={{ ml: 1, color: 'grey.500' }} />
                </Tooltip>
              </Box>
              {sentimentIndicators.naaim ? (
                <Box sx={{ mt: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <TrendingUpIcon sx={{ color: '#388e3c', mr: 1 }} />
                    <Typography variant="body1" sx={{ fontWeight: 700, minWidth: 70 }}>Bullish:</Typography>
                    <Typography variant="body1" color="success.main" sx={{ fontWeight: 700 }}>
                      {sentimentIndicators.naaim.bullish_8100 !== undefined ? sentimentIndicators.naaim.bullish_8100.toFixed(1) + '%' : 'N/A'}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <TrendingDownIcon sx={{ color: '#d32f2f', mr: 1 }} />
                    <Typography variant="body1" sx={{ fontWeight: 700, minWidth: 70 }}>Bearish:</Typography>
                    <Typography variant="body1" color="error.main" sx={{ fontWeight: 700 }}>
                      {sentimentIndicators.naaim.bearish !== undefined ? sentimentIndicators.naaim.bearish.toFixed(1) + '%' : 'N/A'}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <SentimentNeutralIcon sx={{ color: '#fbc02d', mr: 1 }} />
                    <Typography variant="body1" sx={{ fontWeight: 700, minWidth: 70 }}>Average:</Typography>
                    <Typography variant="body1" color="info.main" sx={{ fontWeight: 700 }}>
                      {sentimentIndicators.naaim.average !== undefined ? sentimentIndicators.naaim.average.toFixed(1) + '%' : 'N/A'}
                    </Typography>
                  </Box>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                    Week ending: {sentimentIndicators.naaim.week_ending ? new Date(sentimentIndicators.naaim.week_ending).toLocaleDateString() : 'N/A'}
                  </Typography>
                </Box>
              ) : (
                <Typography variant="body2" color="text.secondary">No data available</Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

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
          {sentimentLoading ? (
            <LinearProgress />
          ) : (
            <Card>
              <CardContent>
                <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                  Sentiment History (30 Days)
                </Typography>
                <ResponsiveContainer width="100%" height={420}>
                  <LineChart data={sentimentChartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" minTickGap={4} />
                    <YAxis yAxisId="left" domain={[0, 100]} tickFormatter={v => v + '%'} />
                    <YAxis yAxisId="right" orientation="right" domain={[0, 100]} hide />
                    <RechartsTooltip 
                      formatter={(value, name) => {
                        if (name === 'fear_greed') return [value, 'Fear & Greed'];
                        if (name === 'naaim') return [value + '%', 'NAAIM'];
                        if (name === 'aaii_bullish') return [value + '%', 'AAII Bullish'];
                        if (name === 'aaii_neutral') return [value + '%', 'AAII Neutral'];
                        if (name === 'aaii_bearish') return [value + '%', 'AAII Bearish'];
                        return value;
                      }}
                    />
                    <Legend verticalAlign="top" height={36} />
                    <Line yAxisId="left" type="monotone" dataKey="fear_greed" name="Fear & Greed" stroke="#1976d2" strokeWidth={2} dot={false} />
                    <Line yAxisId="left" type="monotone" dataKey="naaim" name="NAAIM" stroke="#388e3c" strokeWidth={2} dot={false} />
                    <Line yAxisId="left" type="monotone" dataKey="aaii_bullish" name="AAII Bullish" stroke="#43a047" strokeDasharray="5 2" dot={false} />
                    <Line yAxisId="left" type="monotone" dataKey="aaii_neutral" name="AAII Neutral" stroke="#fbc02d" strokeDasharray="3 3" dot={false} />
                    <Line yAxisId="left" type="monotone" dataKey="aaii_bearish" name="AAII Bearish" stroke="#d32f2f" strokeDasharray="2 2" dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
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
                          {economicData?.data?.slice(0, 10).map((indicator, index) => (
                            <TableRow key={index} hover>
                              <TableCell>{indicator.name || 'N/A'}</TableCell>
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
                                {indicator.timestamp ? new Date(indicator.timestamp).toLocaleDateString() : 'N/A'}
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
      </Card>
    </Box>
  )
}

export default MarketOverview
