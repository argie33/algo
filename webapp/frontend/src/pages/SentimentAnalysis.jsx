import React, { useState, useEffect, useMemo } from 'react';
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
  TableSortLabel,
  Accordion,
  AccordionSummary,
  AccordionDetails
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Psychology,
  Analytics,
  Newspaper,
  Reddit,
  Twitter,
  Assessment,
  Warning,
  CheckCircle,
  Info,
  Timeline,
  ShowChart,
  BarChart,
  FilterList,
  Refresh,
  Download,
  Share,
  BookmarkBorder,
  Bookmark,
  ThumbUp,
  ThumbDown,
  Visibility,
  VisibilityOff,
  ExpandMore,
  Speed,
  TrendingFlat,
  Lightbulb
} from '@mui/icons-material';
import {
  PieChart,
  Pie,
  Cell,
  BarChart as RechartsBarChart,
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
  Scatter
} from 'recharts';
import { formatPercentage, formatNumber } from '../utils/formatters';

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`sentiment-tabpanel-${index}`}
      aria-labelledby={`sentiment-tab-${index}`}
      {...other}
    >
      {value === index && (
        <div  sx={{ py: 3 }}>
          {children}
        </div>
      )}
    </div>
  );
}

const SentimentAnalysis = () => {
  const [activeTab, setActiveTab] = useState(0);
  // ⚠️ MOCK DATA - Using mock sentiment data
  const [sentimentData, setSentimentData] = useState(mockSentimentData);
  const [loading, setLoading] = useState(false);
  const [selectedTimeframe, setSelectedTimeframe] = useState('1W');
  const [selectedSymbol, setSelectedSymbol] = useState('SPY');
  const [orderBy, setOrderBy] = useState('impact');
  const [order, setOrder] = useState('desc');

  // Advanced sentiment metrics calculations
  const sentimentMetrics = useMemo(() => {
    const overall = sentimentData.sources.reduce((sum, source) => sum + source.score * source.weight, 0);
    const momentum = calculateSentimentMomentum(sentimentData.historicalData);
    const volatility = calculateSentimentVolatility(sentimentData.historicalData);
    const extremeReadings = detectExtremeReadings(sentimentData.sources);
    const contrarian = calculateContrarianSignal(sentimentData.sources);
    
    return {
      overall: Math.round(overall),
      momentum,
      volatility,
      extremeReadings,
      contrarian,
      confidence: calculateConfidenceScore(sentimentData.sources),
      divergence: calculateSentimentDivergence(sentimentData.sources)
    };
  }, [sentimentData]);

  // AI insights based on sentiment patterns
  const aiInsights = useMemo(() => {
    return generateSentimentInsights(sentimentMetrics, sentimentData);
  }, [sentimentMetrics, sentimentData]);

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };

  const handleSort = (property) => {
    const isAsc = orderBy === property && order === 'asc';
    setOrder(isAsc ? 'desc' : 'asc');
    setOrderBy(property);
  };

  const getSentimentColor = (score) => {
    if (score >= 70) return 'success';
    if (score >= 40) return 'warning';
    return 'error';
  };

  const getSentimentIcon = (score) => {
    if (score >= 60) return <TrendingUp />;
    if (score >= 40) return <TrendingFlat />;
    return <TrendingDown />;
  };

  return (
    <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <div  display="flex" alignItems="center" justifyContent="between" mb={4}>
        <div>
          <div  variant="h3" component="h1" gutterBottom>
            Advanced Sentiment Analysis
          </div>
          <div  variant="subtitle1" color="text.secondary">
            AI-powered multi-source sentiment tracking and contrarian analysis
          </div>
        </div>
        
        <div  display="flex" alignItems="center" gap={2}>
          <div className="mb-4" size="small" sx={{ minWidth: 120 }}>
            <label className="block text-sm font-medium text-gray-700 mb-1">Symbol</label>
            <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={selectedSymbol}
              label="Symbol"
              onChange={(e) => setSelectedSymbol(e.target.value)}
            >
              <option  value="SPY">SPY (Market)</option>
              <option  value="QQQ">QQQ (Tech)</option>
              <option  value="AAPL">AAPL</option>
              <option  value="TSLA">TSLA</option>
              <option  value="NVDA">NVDA</option>
            </select>
          </div>
          
          <div className="mb-4" size="small" sx={{ minWidth: 120 }}>
            <label className="block text-sm font-medium text-gray-700 mb-1">Timeframe</label>
            <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={selectedTimeframe}
              label="Timeframe"
              onChange={(e) => setSelectedTimeframe(e.target.value)}
            >
              <option  value="1D">1 Day</option>
              <option  value="1W">1 Week</option>
              <option  value="1M">1 Month</option>
              <option  value="3M">3 Months</option>
            </select>
          </div>
          
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="outlined" startIcon={<Download />}>
            Export
          </button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="contained" startIcon={<Refresh />}>
            Refresh
          </button>
        </div>
      </div>

      {/* Sentiment Alert */}
      {sentimentMetrics.extremeReadings.length > 0 && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
          severity="warning" 
          sx={{ mb: 3 }}
          icon={<Warning />}
        >
          <strong>Extreme Sentiment Alert:</strong> {sentimentMetrics.extremeReadings[0].message}
          {sentimentMetrics.contrarian > 75 && " - Strong contrarian signal detected."}
        </div>
      )}

      {/* Key Metrics Cards */}
      <div className="grid" container spacing={3} mb={4}>
        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  display="flex" alignItems="center" justifyContent="between">
                <div>
                  <div  variant="h6" color="text.secondary">
                    Overall Sentiment
                  </div>
                  <div  variant="h3" color="primary">
                    {sentimentMetrics.overall}
                  </div>
                  <div  display="flex" alignItems="center" mt={1}>
                    {getSentimentIcon(sentimentMetrics.overall)}
                    <div  variant="body2" color="text.secondary" ml={1}>
                      {sentimentMetrics.overall >= 70 ? 'Extremely Bullish' :
                       sentimentMetrics.overall >= 60 ? 'Bullish' :
                       sentimentMetrics.overall >= 40 ? 'Neutral' :
                       sentimentMetrics.overall >= 30 ? 'Bearish' : 'Extremely Bearish'}
                    </div>
                  </div>
                </div>
                <Psychology color="primary" fontSize="large" />
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2" 
                variant="determinate" 
                value={sentimentMetrics.overall} 
                color={getSentimentColor(sentimentMetrics.overall)}
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
                    Sentiment Momentum
                  </div>
                  <div  variant="h3" color="secondary">
                    {formatNumber(sentimentMetrics.momentum, 1)}
                  </div>
                  <div  variant="body2" color="text.secondary">
                    {sentimentMetrics.momentum > 0 ? 'Improving' : 'Deteriorating'}
                  </div>
                </div>
                <Speed color="secondary" fontSize="large" />
              </div>
              <Rating 
                value={Math.min(5, Math.max(0, (sentimentMetrics.momentum + 50) / 20))} 
                readOnly 
                size="small"
                sx={{ mt: 1 }}
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
                    Contrarian Signal
                  </div>
                  <div  variant="h3" color="warning.main">
                    {sentimentMetrics.contrarian}%
                  </div>
                  <div  variant="body2" color="text.secondary">
                    {sentimentMetrics.contrarian > 75 ? 'Strong Signal' :
                     sentimentMetrics.contrarian > 50 ? 'Moderate Signal' : 'Weak Signal'}
                  </div>
                </div>
                <Analytics color="warning" fontSize="large" />
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
                    AI Confidence
                  </div>
                  <div  variant="h3" color="info.main">
                    {sentimentMetrics.confidence}%
                  </div>
                  <div  variant="body2" color="text.secondary">
                    Analysis reliability
                  </div>
                </div>
                <Assessment color="info" fontSize="large" />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content Tabs */}
      <div  sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <div className="border-b border-gray-200" value={activeTab} onChange={handleTabChange} aria-label="sentiment analysis tabs" variant="scrollable" scrollButtons="auto">
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Multi-Source Analysis" icon={<Analytics />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Sentiment Trends" icon={<Timeline />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Contrarian Signals" icon={<Psychology />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="News Impact" icon={<Newspaper />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Social Sentiment" icon={<Reddit />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="AI Insights" icon={<Lightbulb />} />
        </div>
      </div>

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={0}>
        {/* Multi-Source Analysis */}
        <div className="grid" container spacing={3}>
          <div className="grid" item xs={12} md={8}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header title="Sentiment Source Breakdown" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <ResponsiveContainer width="100%" height={400}>
                  <RadarChart data={sentimentData.sources}>
                    <PolarGrid />
                    <PolarAngleAxis dataKey="source" />
                    <PolarRadiusAxis 
                      angle={90} 
                      domain={[0, 100]} 
                      tick={{ fontSize: 12 }}
                    />
                    <Radar
                      name="Current"
                      dataKey="score"
                      stroke="#8884d8"
                      fill="#8884d8"
                      fillOpacity={0.3}
                      strokeWidth={2}
                    />
                    <Radar
                      name="1W Ago"
                      dataKey="previousScore"
                      stroke="#82ca9d"
                      fill="transparent"
                      strokeWidth={2}
                      strokeDasharray="5 5"
                    />
                    <RechartsTooltip />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <div className="grid" item xs={12} md={4}>
            <div className="grid" container spacing={3}>
              {/* Source Rankings */}
              <div className="grid" item xs={12}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Header title="Source Rankings" />
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <List>
                      {sentimentData.sources
                        .sort((a, b) => b.score - a.score)
                        .map((source, index) => (
                        <ListItem key={source.source} disablePadding>
                          <ListItemAvatar>
                            <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ bgcolor: getSentimentColor(source.score) + '.main' }}>
                              {index + 1}
                            </div>
                          </ListItemAvatar>
                          <ListItemText
                            primary={source.source}
                            secondary={
                              <div  display="flex" alignItems="center" gap={1}>
                                <div  variant="body2">
                                  Score: {source.score}
                                </div>
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                  label={`${source.change >= 0 ? '+' : ''}${source.change}`}
                                  color={source.change >= 0 ? 'success' : 'error'}
                                  size="small"
                                  variant="outlined"
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

              {/* Sentiment Divergence */}
              <div className="grid" item xs={12}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Header title="Sentiment Divergence" />
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div  mb={2}>
                      <div  variant="body2" color="text.secondary">
                        Cross-Source Divergence
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2" 
                        variant="determinate" 
                        value={sentimentMetrics.divergence} 
                        color={sentimentMetrics.divergence > 30 ? 'warning' : 'success'}
                        sx={{ mt: 1 }}
                      />
                      <div  variant="caption" color="text.secondary">
                        {sentimentMetrics.divergence}% divergence
                      </div>
                    </div>
                    
                    <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
                      severity={sentimentMetrics.divergence > 30 ? 'warning' : 'info'}
                      size="small"
                    >
                      {sentimentMetrics.divergence > 30 
                        ? 'High divergence may indicate uncertain market conditions'
                        : 'Low divergence suggests consensus across sources'}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={1}>
        {/* Sentiment Trends */}
        <div className="grid" container spacing={3}>
          <div className="grid" item xs={12} md={8}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header title="Sentiment Historical Trends" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <ResponsiveContainer width="100%" height={400}>
                  <ComposedChart data={sentimentData.historicalData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis yAxisId="left" domain={[0, 100]} />
                    <YAxis yAxisId="right" orientation="right" />
                    <RechartsTooltip />
                    <Area 
                      yAxisId="left"
                      type="monotone" 
                      dataKey="overall" 
                      fill="#8884d8" 
                      stroke="#8884d8"
                      fillOpacity={0.3}
                    />
                    <Line 
                      yAxisId="left"
                      type="monotone" 
                      dataKey="analyst" 
                      stroke="#82ca9d" 
                      strokeWidth={2}
                    />
                    <Line 
                      yAxisId="left"
                      type="monotone" 
                      dataKey="social" 
                      stroke="#ffc658" 
                      strokeWidth={2}
                    />
                    <Bar 
                      yAxisId="right"
                      dataKey="volume" 
                      fill="#ff7300"
                      opacity={0.3}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <div className="grid" item xs={12} md={4}>
            <div className="grid" container spacing={3}>
              {/* Trend Analysis */}
              <div className="grid" item xs={12}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Header title="Trend Indicators" />
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div  display="flex" flexDirection="column" gap={2}>
                      <div  display="flex" justifyContent="between">
                        <div  variant="body2">5-Day Trend</div>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                          label={sentimentData.trends.short >= 0 ? 'Bullish' : 'Bearish'}
                          color={sentimentData.trends.short >= 0 ? 'success' : 'error'}
                          size="small"
                        />
                      </div>
                      <div  display="flex" justifyContent="between">
                        <div  variant="body2">20-Day Trend</div>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                          label={sentimentData.trends.medium >= 0 ? 'Bullish' : 'Bearish'}
                          color={sentimentData.trends.medium >= 0 ? 'success' : 'error'}
                          size="small"
                        />
                      </div>
                      <div  display="flex" justifyContent="between">
                        <div  variant="body2">60-Day Trend</div>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                          label={sentimentData.trends.long >= 0 ? 'Bullish' : 'Bearish'}
                          color={sentimentData.trends.long >= 0 ? 'success' : 'error'}
                          size="small"
                        />
                      </div>
                      <div  display="flex" justifyContent="between">
                        <div  variant="body2">Momentum Score</div>
                        <div  variant="body2" fontWeight="bold">
                          {formatNumber(sentimentMetrics.momentum, 1)}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Volatility Analysis */}
              <div className="grid" item xs={12}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Header title="Sentiment Volatility" />
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div  textAlign="center" mb={2}>
                      <div  variant="h4" color="warning.main">
                        {formatNumber(sentimentMetrics.volatility, 1)}%
                      </div>
                      <div  variant="body2" color="text.secondary">
                        30-Day Volatility
                      </div>
                    </div>
                    
                    <div className="w-full bg-gray-200 rounded-full h-2" 
                      variant="determinate" 
                      value={Math.min(100, sentimentMetrics.volatility * 5)} 
                      color="warning"
                      sx={{ mb: 2 }}
                    />
                    
                    <div  variant="caption" color="text.secondary">
                      {sentimentMetrics.volatility > 20 ? 'High volatility indicates uncertain sentiment' :
                       sentimentMetrics.volatility > 10 ? 'Moderate volatility' : 'Low volatility - stable sentiment'}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={2}>
        {/* Contrarian Signals */}
        <div className="grid" container spacing={3}>
          <div className="grid" item xs={12} md={8}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header title="Contrarian Signal Analysis" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <ResponsiveContainer width="100%" height={400}>
                  <ScatterChart data={sentimentData.contrarianData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis 
                      dataKey="sentiment" 
                      name="Sentiment Score"
                      domain={[0, 100]}
                    />
                    <YAxis 
                      dataKey="priceChange" 
                      name="Future Returns"
                      domain={[-10, 10]}
                    />
                    <RechartsTooltip 
                      cursor={{ strokeDasharray: '3 3' }}
                      formatter={(value, name) => [
                        name === 'priceChange' ? `${value}%` : value,
                        name === 'priceChange' ? 'Future Returns' : 'Sentiment'
                      ]}
                    />
                    <Scatter dataKey="priceChange" fill="#8884d8" />
                  </ScatterChart>
                </ResponsiveContainer>
                <div  variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
                  Scatter plot showing relationship between sentiment extremes and future price movements
                </div>
              </div>
            </div>
          </div>

          <div className="grid" item xs={12} md={4}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header title="Contrarian Opportunities" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <List>
                  {sentimentData.contrarianOpportunities.map((opportunity, index) => (
                    <ListItem key={index} divider={index < sentimentData.contrarianOpportunities.length - 1}>
                      <ListItemText
                        primary={
                          <div  display="flex" alignItems="center" gap={1}>
                            <div  variant="subtitle2" fontWeight="bold">
                              {opportunity.symbol}
                            </div>
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                              label={`${opportunity.probability}%`}
                              color={opportunity.probability > 70 ? 'success' : 'warning'}
                              size="small"
                            />
                          </div>
                        }
                        secondary={
                          <div>
                            <div  variant="body2" gutterBottom>
                              {opportunity.reason}
                            </div>
                            <div  display="flex" gap={1}>
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                label={`Sentiment: ${opportunity.currentSentiment}`}
                                size="small"
                                variant="outlined"
                              />
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                label={opportunity.signal}
                                color={opportunity.signal === 'Buy' ? 'success' : 'error'}
                                size="small"
                              />
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

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={3}>
        {/* News Impact */}
        <div className="grid" container spacing={3}>
          <div className="grid" item xs={12}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header 
                title="News Sentiment Impact Analysis" 
                action={
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                    label={`${sentimentData.newsImpact.length} articles analyzed`} 
                    color="primary" 
                    variant="outlined" 
                  />
                }
              />
              <div className="bg-white shadow-md rounded-lg"Content>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leSortLabel
                            active={orderBy === 'timestamp'}
                            direction={orderBy === 'timestamp' ? order : 'asc'}
                            onClick={() => handleSort('timestamp')}
                          >
                            Time
                          </TableSortLabel>
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Headline</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leSortLabel
                            active={orderBy === 'sentiment'}
                            direction={orderBy === 'sentiment' ? order : 'asc'}
                            onClick={() => handleSort('sentiment')}
                          >
                            Sentiment
                          </TableSortLabel>
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leSortLabel
                            active={orderBy === 'impact'}
                            direction={orderBy === 'impact' ? order : 'asc'}
                            onClick={() => handleSort('impact')}
                          >
                            Market Impact
                          </TableSortLabel>
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Confidence</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Actions</td>
                      </tr>
                    </thead>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                      {sentimentData.newsImpact
                        .sort((a, b) => {
                          const aValue = a[orderBy];
                          const bValue = b[orderBy];
                          if (order === 'asc') {
                            return aValue < bValue ? -1 : 1;
                          } else {
                            return aValue > bValue ? -1 : 1;
                          }
                        })
                        .slice(0, 10)
                        .map((news, index) => (
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={index}>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                            <div  variant="caption">
                              {new Date(news.timestamp).toLocaleTimeString()}
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                            <div>
                              <div  variant="body2" fontWeight="bold" gutterBottom>
                                {news.headline}
                              </div>
                              <div  variant="caption" color="text.secondary">
                                {news.source}
                              </div>
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                              label={news.sentiment}
                              color={getSentimentColor(news.sentimentScore)}
                              size="small"
                            />
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                            <div>
                              <div  variant="body2" fontWeight="bold">
                                {formatPercentage(news.impact)}
                              </div>
                              <div className="w-full bg-gray-200 rounded-full h-2" 
                                variant="determinate" 
                                value={Math.abs(news.impact) * 10} 
                                color={news.impact >= 0 ? 'success' : 'error'}
                                sx={{ width: 60, mt: 0.5 }}
                              />
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                            <Rating 
                              value={news.confidence / 20} 
                              readOnly 
                              size="small"
                            />
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                            <button className="p-2 rounded-full hover:bg-gray-100" size="small">
                              <BookmarkBorder />
                            </button>
                            <button className="p-2 rounded-full hover:bg-gray-100" size="small">
                              <Share />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={4}>
        {/* Social Sentiment */}
        <div className="grid" container spacing={3}>
          <div className="grid" item xs={12} md={6}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header title="Platform Sentiment Breakdown" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie
                      data={sentimentData.socialPlatforms}
                      cx="50%"
                      cy="50%"
                      outerRadius={80}
                      fill="#8884d8"
                      dataKey="mentions"
                      label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                    >
                      {sentimentData.socialPlatforms.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <RechartsTooltip />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <div className="grid" item xs={12} md={6}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header title="Viral Content Analysis" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <List>
                  {sentimentData.viralContent.map((content, index) => (
                    <ListItem key={index} divider={index < sentimentData.viralContent.length - 1}>
                      <ListItemAvatar>
                        <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ bgcolor: content.platform === 'Twitter' ? '#1DA1F2' : '#FF4500' }}>
                          {content.platform === 'Twitter' ? <Twitter /> : <Reddit />}
                        </div>
                      </ListItemAvatar>
                      <ListItemText
                        primary={content.content}
                        secondary={
                          <div  display="flex" alignItems="center" gap={1} mt={1}>
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                              label={`${content.engagement} engagements`}
                              size="small"
                              variant="outlined"
                            />
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                              label={content.sentiment}
                              color={getSentimentColor(content.sentimentScore)}
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

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={5}>
        {/* AI Insights */}
        <div className="grid" container spacing={3}>
          <div className="grid" item xs={12} md={8}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header 
                title="AI-Powered Sentiment Insights" 
                avatar={<Psychology color="primary" />}
              />
              <div className="bg-white shadow-md rounded-lg"Content>
                <Stepper orientation="vertical">
                  <Step expanded>
                    <StepLabel>
                      <div  variant="h6" color="primary">
                        Current Market Sentiment
                      </div>
                    </StepLabel>
                    <StepContent>
                      <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info" sx={{ mb: 2 }}>
                        {aiInsights.marketSummary}
                      </div>
                    </StepContent>
                  </Step>

                  <Step expanded>
                    <StepLabel>
                      <div  variant="h6" color="success.main">
                        Key Opportunities
                      </div>
                    </StepLabel>
                    <StepContent>
                      <List>
                        {aiInsights.opportunities.map((opportunity, index) => (
                          <ListItem key={index}>
                            <CheckCircle color="success" sx={{ mr: 2 }} />
                            <div  variant="body2">{opportunity}</div>
                          </ListItem>
                        ))}
                      </List>
                    </StepContent>
                  </Step>

                  <Step expanded>
                    <StepLabel>
                      <div  variant="h6" color="warning.main">
                        Risk Factors
                      </div>
                    </StepLabel>
                    <StepContent>
                      <List>
                        {aiInsights.risks.map((risk, index) => (
                          <ListItem key={index}>
                            <Warning color="warning" sx={{ mr: 2 }} />
                            <div  variant="body2">{risk}</div>
                          </ListItem>
                        ))}
                      </List>
                    </StepContent>
                  </Step>

                  <Step expanded>
                    <StepLabel>
                      <div  variant="h6" color="info.main">
                        Forecast
                      </div>
                    </StepLabel>
                    <StepContent>
                      <div  variant="body2" paragraph>
                        {aiInsights.forecast}
                      </div>
                      
                      <Accordion>
                        <AccordionSummary expandIcon={<ExpandMore />}>
                          <div  variant="subtitle2">Technical Details</div>
                        </AccordionSummary>
                        <AccordionDetails>
                          <div  variant="body2" color="text.secondary">
                            {aiInsights.technicalDetails}
                          </div>
                        </AccordionDetails>
                      </Accordion>
                    </StepContent>
                  </Step>
                </Stepper>
              </div>
            </div>
          </div>

          <div className="grid" item xs={12} md={4}>
            <div className="grid" container spacing={3}>
              {/* AI Confidence */}
              <div className="grid" item xs={12}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Header title="AI Analysis Confidence" />
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div  textAlign="center" mb={3}>
                      <div  variant="h2" color="primary">
                        {sentimentMetrics.confidence}%
                      </div>
                      <Rating 
                        value={sentimentMetrics.confidence / 20} 
                        readOnly 
                        size="large"
                      />
                      <div  variant="body2" color="text.secondary">
                        Model Confidence
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Model Performance */}
              <div className="grid" item xs={12}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Header title="Model Performance" />
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div  display="flex" flexDirection="column" gap={2}>
                      <div  display="flex" justifyContent="between">
                        <div  variant="body2">Accuracy (30d)</div>
                        <div  variant="body2" fontWeight="bold">
                          {aiInsights.modelStats.accuracy}%
                        </div>
                      </div>
                      <div  display="flex" justifyContent="between">
                        <div  variant="body2">Precision</div>
                        <div  variant="body2" fontWeight="bold">
                          {aiInsights.modelStats.precision}%
                        </div>
                      </div>
                      <div  display="flex" justifyContent="between">
                        <div  variant="body2">Recall</div>
                        <div  variant="body2" fontWeight="bold">
                          {aiInsights.modelStats.recall}%
                        </div>
                      </div>
                      <div  display="flex" justifyContent="between">
                        <div  variant="body2">Data Sources</div>
                        <div  variant="body2" fontWeight="bold">
                          {aiInsights.modelStats.dataSources}
                        </div>
                      </div>
                    </div>
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

// ⚠️ MOCK DATA - Replace with real API when available
const mockSentimentData = {
  isMockData: true,
  sources: [
    {
      source: 'Analyst Reports',
      score: 72,
      previousScore: 68,
      change: 4,
      weight: 0.3,
      reliability: 0.9
    },
    {
      source: 'Social Media',
      score: 58,
      previousScore: 62,
      change: -4,
      weight: 0.2,
      reliability: 0.7
    },
    {
      source: 'News Sentiment',
      score: 70,
      previousScore: 65,
      change: 5,
      weight: 0.25,
      reliability: 0.85
    },
    {
      source: 'Options Flow',
      score: 45,
      previousScore: 55,
      change: -10,
      weight: 0.15,
      reliability: 0.8
    },
    {
      source: 'Insider Trading',
      score: 65,
      previousScore: 60,
      change: 5,
      weight: 0.1,
      reliability: 0.95
    }
  ],
  historicalData: Array.from({ length: 30 }, (_, i) => ({
    date: new Date(Date.now() - (29 - i) * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
    overall: 60 + Math.sin(i / 5) * 15 + Math.random() * 10,
    analyst: 65 + Math.cos(i / 7) * 10 + Math.random() * 8,
    social: 55 + Math.sin(i / 3) * 20 + Math.random() * 12,
    volume: 1000 + Math.random() * 2000
  })),
  trends: {
    short: 2.3,    // 5-day
    medium: -1.2,  // 20-day
    long: 4.5      // 60-day
  },
  contrarianData: Array.from({ length: 50 }, (_, i) => ({
    sentiment: Math.random() * 100,
    priceChange: (Math.random() - 0.5) * 20,
    date: new Date(Date.now() - i * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
  })),
  contrarianOpportunities: [
    {
      symbol: 'AAPL',
      currentSentiment: 25,
      probability: 78,
      signal: 'Buy',
      reason: 'Sentiment at extreme low while fundamentals remain strong'
    },
    {
      symbol: 'TSLA',
      currentSentiment: 85,
      probability: 72,
      signal: 'Sell',
      reason: 'Euphoric sentiment levels historically followed by correction'
    },
    {
      symbol: 'NVDA',
      currentSentiment: 20,
      probability: 65,
      signal: 'Buy',
      reason: 'Oversold sentiment despite strong AI growth prospects'
    }
  ],
  newsImpact: Array.from({ length: 20 }, (_, i) => ({
    timestamp: new Date(Date.now() - i * 60 * 60 * 1000).toISOString(),
    headline: [
      'Fed signals dovish stance on interest rates',
      'Tech earnings beat expectations across sector',
      'Geopolitical tensions escalate affecting markets',
      'Inflation data shows cooling trend',
      'Major bank upgrades equity outlook'
    ][i % 5],
    source: ['Reuters', 'Bloomberg', 'CNBC', 'WSJ', 'FT'][i % 5],
    sentiment: ['Bullish', 'Bearish', 'Neutral'][Math.floor(Math.random() * 3)],
    sentimentScore: 20 + Math.random() * 60,
    impact: (Math.random() - 0.5) * 4,
    confidence: 60 + Math.random() * 40
  })),
  socialPlatforms: [
    { name: 'Twitter', mentions: 15420, sentiment: 62 },
    { name: 'Reddit', mentions: 8970, sentiment: 55 },
    { name: 'Discord', mentions: 4320, sentiment: 71 },
    { name: 'Telegram', mentions: 2180, sentiment: 48 }
  ],
  viralContent: [
    {
      platform: 'Twitter',
      content: 'Market showing strong resilience despite headwinds...',
      engagement: '15.2K',
      sentiment: 'Bullish',
      sentimentScore: 75
    },
    {
      platform: 'Reddit',
      content: 'Technical analysis suggests major support level holding...',
      engagement: '8.9K',
      sentiment: 'Neutral',
      sentimentScore: 52
    },
    {
      platform: 'Twitter',
      content: 'Concerning patterns emerging in credit markets...',
      engagement: '12.1K',
      sentiment: 'Bearish',
      sentimentScore: 28
    }
  ]
};

// Color palette for charts
const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8', '#82CA9D'];

// ⚠️ MOCK DATA - Advanced calculation functions using mock data
function calculateSentimentMomentum(historicalData) {
  if (historicalData.length < 5) return 0;
  
  const recent = historicalData.slice(-5);
  const older = historicalData.slice(-10, -5);
  
  const recentAvg = recent.reduce((sum, d) => sum + d.overall, 0) / recent.length;
  const olderAvg = older.reduce((sum, d) => sum + d.overall, 0) / older.length;
  
  return ((recentAvg - olderAvg) / olderAvg) * 100;
}

function calculateSentimentVolatility(historicalData) {
  if (historicalData.length < 2) return 0;
  
  const returns = [];
  for (let i = 1; i < historicalData.length; i++) {
    const change = (historicalData[i].overall - historicalData[i-1].overall) / historicalData[i-1].overall;
    returns.push(change);
  }
  
  const mean = returns.reduce((sum, r) => sum + r, 0) / returns.length;
  const variance = returns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / returns.length;
  
  return Math.sqrt(variance) * 100 * Math.sqrt(252); // Annualized
}

function detectExtremeReadings(sources) {
  const extremes = [];
  sources.forEach(source => {
    if (source.score > 80) {
      extremes.push({
        source: source.source,
        message: `${source.source} showing extreme bullish reading (${source.score})`
      });
    } else if (source.score < 20) {
      extremes.push({
        source: source.source,
        message: `${source.source} showing extreme bearish reading (${source.score})`
      });
    }
  });
  return extremes;
}

function calculateContrarianSignal(sources) {
  const extremeCount = sources.filter(s => s.score > 80 || s.score < 20).length;
  const totalSources = sources.length;
  return Math.round((extremeCount / totalSources) * 100);
}

function calculateConfidenceScore(sources) {
  const weightedReliability = sources.reduce((sum, s) => sum + s.reliability * s.weight, 0);
  return Math.round(weightedReliability * 100);
}

function calculateSentimentDivergence(sources) {
  const scores = sources.map(s => s.score);
  const mean = scores.reduce((sum, s) => sum + s, 0) / scores.length;
  const variance = scores.reduce((sum, s) => sum + Math.pow(s - mean, 2), 0) / scores.length;
  return Math.round(Math.sqrt(variance));
}

function generateSentimentInsights(metrics, data) {
  return {
    marketSummary: `Current sentiment shows ${metrics.overall >= 60 ? 'bullish' : metrics.overall >= 40 ? 'neutral' : 'bearish'} bias with ${metrics.momentum > 0 ? 'improving' : 'deteriorating'} momentum. ${metrics.contrarian > 50 ? 'Contrarian signals suggest potential reversal ahead.' : 'Sentiment alignment supports current trend.'}`,
    opportunities: [
      'Social media sentiment diverging from analyst views - potential alpha opportunity',
      'Options flow showing defensive positioning despite bullish news sentiment',
      'Insider trading patterns suggest accumulation during sentiment weakness',
      'Cross-asset sentiment divergence creating relative value opportunities'
    ],
    risks: [
      'High sentiment volatility indicates unstable market psychology',
      'Extreme readings in multiple sources suggest potential reversal risk',
      'Divergence between sentiment sources may signal market uncertainty',
      'Elevated contrarian signal warns of potential sentiment-driven correction'
    ],
    forecast: `Based on current sentiment patterns and historical analysis, expect ${metrics.momentum > 0 ? 'continued positive' : 'potential reversal in'} sentiment trends over the next 5-10 trading days. Key inflection points likely around major economic releases or earnings announcements.`,
    technicalDetails: 'Analysis incorporates machine learning models trained on 5+ years of multi-source sentiment data with real-time natural language processing. Confidence intervals and statistical significance testing ensure robust signal generation.',
    modelStats: {
      accuracy: 84,
      precision: 79,
      recall: 86,
      dataSources: 47
    }
  };
}

export default SentimentAnalysis;