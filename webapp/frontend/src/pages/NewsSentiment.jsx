import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  IconButton,
  Button,
  Chip,
  Alert,
  LinearProgress,
  Tabs,
  Tab,
  Stack,
  Paper,
  Divider,
  alpha,
  List,
  ListItem,
  ListItemText,
  ListItemAvatar,
  Avatar,
  Tooltip,
  ToggleButton,
  ToggleButtonGroup,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  InputAdornment
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Article,
  Assessment,
  Timeline,
  Update,
  Business,
  Language,
  Search,
  FilterList,
  Psychology,
  ShowChart,
  AttachMoney,
  Newspaper,
  Speed,
  Warning,
  CheckCircle,
  Error as ErrorIcon,
  Refresh,
  CalendarToday,
  AccessTime,
  LocalFireDepartment,
  AcUnit
} from '@mui/icons-material';
import { api } from '../services/api';
import { formatDistanceToNow } from 'date-fns';

function TabPanel({ children, value, index }) {
  return (
    <div hidden={value !== index}>
      {value === index && <div  sx={{ py: 2 }}>{children}</div>}
    </div>
  );
}

const NewsSentiment = () => {
  const [activeTab, setActiveTab] = useState(0);
  const [newsData, setNewsData] = useState([]);
  const [sentimentStats, setSentimentStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [timeframe, setTimeframe] = useState('24h');
  const [category, setCategory] = useState('all');
  const [sortBy, setSortBy] = useState('time');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedSector, setSelectedSector] = useState('all');
  const [impactLevel, setImpactLevel] = useState('all');

  useEffect(() => {
    loadNewsData();
    loadSentimentStats();
  }, [timeframe, category, selectedSector, impactLevel]);

  const loadNewsData = async () => {
    setLoading(true);
    try {
      const response = await api.get('/sentiment/news', {
        params: {
          timeframe,
          category,
          sector: selectedSector,
          impact: impactLevel
        }
      });
      setNewsData(response.data.articles || []);
    } catch (error) {
      console.error('Error loading news data:', error);
      // Use mock data for now
      setNewsData(getMockNewsData());
    } finally {
      setLoading(false);
    }
  };

  const loadSentimentStats = async () => {
    try {
      const response = await api.get('/sentiment/news/stats', {
        params: { timeframe }
      });
      setSentimentStats(response.data);
    } catch (error) {
      console.error('Error loading sentiment stats:', error);
      // Use mock data
      setSentimentStats(getMockSentimentStats());
    }
  };

  const getMockNewsData = () => {
    return [
      {
        id: 1,
        title: "Fed Signals Potential Rate Cut in Q2 2025",
        source: "Reuters",
        timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000),
        sentiment: 0.75,
        sentimentLabel: "Bullish",
        impact: "high",
        category: "monetary-policy",
        summary: "Federal Reserve officials indicated openness to rate cuts if inflation continues to moderate...",
        sectors: ["Financial", "Technology", "Real Estate"],
        tickers: ["JPM", "BAC", "AAPL", "MSFT"],
        readTime: 3,
        url: "#"
      },
      {
        id: 2,
        title: "Tech Earnings Beat Expectations Across the Board",
        source: "Bloomberg",
        timestamp: new Date(Date.now() - 4 * 60 * 60 * 1000),
        sentiment: 0.85,
        sentimentLabel: "Very Bullish",
        impact: "high",
        category: "earnings",
        summary: "Major technology companies reported stronger-than-expected Q4 earnings, driven by AI investments...",
        sectors: ["Technology"],
        tickers: ["NVDA", "META", "GOOGL", "AMZN"],
        readTime: 5,
        url: "#"
      },
      {
        id: 3,
        title: "Oil Prices Surge on Middle East Tensions",
        source: "CNBC",
        timestamp: new Date(Date.now() - 6 * 60 * 60 * 1000),
        sentiment: -0.65,
        sentimentLabel: "Bearish",
        impact: "medium",
        category: "commodities",
        summary: "Crude oil prices jumped 4% following escalating tensions in key producing regions...",
        sectors: ["Energy", "Transportation"],
        tickers: ["XOM", "CVX", "USO", "DAL", "UAL"],
        readTime: 4,
        url: "#"
      },
      {
        id: 4,
        title: "Retail Sales Data Shows Consumer Resilience",
        source: "WSJ",
        timestamp: new Date(Date.now() - 8 * 60 * 60 * 1000),
        sentiment: 0.45,
        sentimentLabel: "Moderately Bullish",
        impact: "medium",
        category: "economic-data",
        summary: "December retail sales exceeded expectations, suggesting continued consumer strength...",
        sectors: ["Consumer Discretionary", "Consumer Staples"],
        tickers: ["WMT", "TGT", "AMZN", "HD"],
        readTime: 3,
        url: "#"
      },
      {
        id: 5,
        title: "Biotech Breakthrough: New Cancer Treatment Shows Promise",
        source: "Financial Times",
        timestamp: new Date(Date.now() - 10 * 60 * 60 * 1000),
        sentiment: 0.90,
        sentimentLabel: "Very Bullish",
        impact: "high",
        category: "healthcare",
        summary: "Clinical trials show 85% response rate for new immunotherapy treatment...",
        sectors: ["Healthcare"],
        tickers: ["MRNA", "BNTX", "PFE", "JNJ"],
        readTime: 6,
        url: "#"
      }
    ];
  };

  const getMockSentimentStats = () => {
    return {
      overall: {
        score: 0.42,
        label: "Moderately Bullish",
        change24h: 0.15,
        articleCount: 1247,
        positiveCount: 672,
        negativeCount: 389,
        neutralCount: 186
      },
      byCategory: {
        "monetary-policy": { score: 0.65, count: 145 },
        "earnings": { score: 0.78, count: 234 },
        "economic-data": { score: 0.35, count: 189 },
        "commodities": { score: -0.25, count: 98 },
        "healthcare": { score: 0.55, count: 167 },
        "technology": { score: 0.82, count: 298 },
        "geopolitics": { score: -0.45, count: 116 }
      },
      bySector: {
        "Technology": { score: 0.75, change: 0.12 },
        "Financial": { score: 0.45, change: 0.08 },
        "Healthcare": { score: 0.62, change: -0.05 },
        "Energy": { score: -0.35, change: -0.22 },
        "Consumer Discretionary": { score: 0.38, change: 0.15 },
        "Industrials": { score: 0.22, change: 0.03 }
      },
      topBullish: ["NVDA", "META", "GOOGL", "MRNA", "AMZN"],
      topBearish: ["XOM", "CVX", "UAL", "DAL", "BA"],
      momentum: {
        hourly: [0.25, 0.28, 0.32, 0.35, 0.38, 0.42],
        labels: ["6h ago", "5h ago", "4h ago", "3h ago", "2h ago", "1h ago"]
      }
    };
  };

  const getSentimentColor = (sentiment) => {
    if (sentiment >= 0.6) return '#4caf50';
    if (sentiment >= 0.2) return '#81c784';
    if (sentiment >= -0.2) return '#9e9e9e';
    if (sentiment >= -0.6) return '#e57373';
    return '#f44336';
  };

  const getSentimentIcon = (sentiment) => {
    if (sentiment >= 0.6) return <LocalFireDepartment sx={{ color: '#4caf50' }} />;
    if (sentiment >= 0.2) return <TrendingUp sx={{ color: '#81c784' }} />;
    if (sentiment >= -0.2) return <Remove sx={{ color: '#9e9e9e' }} />;
    if (sentiment >= -0.6) return <TrendingDown sx={{ color: '#e57373' }} />;
    return <AcUnit sx={{ color: '#f44336' }} />;
  };

  const getImpactColor = (impact) => {
    switch (impact) {
      case 'high': return '#f44336';
      case 'medium': return '#ff9800';
      case 'low': return '#4caf50';
      default: return '#9e9e9e';
    }
  };

  const filteredNews = newsData
    .filter(article => {
      if (searchQuery) {
        const query = searchQuery.toLowerCase();
        return article.title.toLowerCase().includes(query) ||
               article.summary.toLowerCase().includes(query) ||
               article.tickers.some(t => t.toLowerCase().includes(query));
      }
      return true;
    })
    .sort((a, b) => {
      switch (sortBy) {
        case 'sentiment':
          return b.sentiment - a.sentiment;
        case 'impact':
          const impactOrder = { high: 3, medium: 2, low: 1 };
          return impactOrder[b.impact] - impactOrder[a.impact];
        case 'time':
        default:
          return b.timestamp - a.timestamp;
      }
    });

  return (
    <div className="container mx-auto" maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      {/* Header */}
      <div  sx={{ mb: 4 }}>
        <div  variant="h4" fontWeight={700} gutterBottom>
          News Sentiment Analysis
        </div>
        <div  variant="body1" color="text.secondary">
          AI-powered analysis of financial news sentiment and market impact predictions
        </div>
      </div>

      {/* Sentiment Overview Cards */}
      <div className="grid" container spacing={3} sx={{ mb: 4 }}>
        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div className="flex flex-col space-y-2" spacing={1}>
                <div  variant="subtitle2" color="text.secondary">
                  Overall Sentiment
                </div>
                <div  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  {getSentimentIcon(sentimentStats?.overall.score || 0)}
                  <div  variant="h4" fontWeight={600} color={getSentimentColor(sentimentStats?.overall.score || 0)}>
                    {sentimentStats?.overall.label || 'Loading...'}
                  </div>
                </div>
                <div  sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  {sentimentStats?.overall.change24h > 0 ? (
                    <TrendingUp sx={{ fontSize: 16, color: '#4caf50' }} />
                  ) : (
                    <TrendingDown sx={{ fontSize: 16, color: '#f44336' }} />
                  )}
                  <div  variant="body2" color={sentimentStats?.overall.change24h > 0 ? 'success.main' : 'error.main'}>
                    {Math.abs(sentimentStats?.overall.change24h || 0).toFixed(2)} vs 24h ago
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div className="flex flex-col space-y-2" spacing={1}>
                <div  variant="subtitle2" color="text.secondary">
                  Articles Analyzed
                </div>
                <div  variant="h4" fontWeight={600}>
                  {sentimentStats?.overall.articleCount || 0}
                </div>
                <div  variant="body2" color="text.secondary">
                  Last {timeframe}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg" sx={{ background: '#4caf500D' }}>
            <div className="bg-white shadow-md rounded-lg"Content>
              <div className="flex flex-col space-y-2" spacing={1}>
                <div  variant="subtitle2" color="text.secondary">
                  Positive Articles
                </div>
                <div  variant="h4" fontWeight={600} color="success.main">
                  {sentimentStats?.overall.positiveCount || 0}
                </div>
                <div  variant="body2" color="text.secondary">
                  {((sentimentStats?.overall.positiveCount / sentimentStats?.overall.articleCount) * 100 || 0).toFixed(1)}% of total
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg" sx={{ background: '#f443360D' }}>
            <div className="bg-white shadow-md rounded-lg"Content>
              <div className="flex flex-col space-y-2" spacing={1}>
                <div  variant="subtitle2" color="text.secondary">
                  Negative Articles
                </div>
                <div  variant="h4" fontWeight={600} color="error.main">
                  {sentimentStats?.overall.negativeCount || 0}
                </div>
                <div  variant="body2" color="text.secondary">
                  {((sentimentStats?.overall.negativeCount / sentimentStats?.overall.articleCount) * 100 || 0).toFixed(1)}% of total
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Filters and Controls */}
      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
        <div className="bg-white shadow-md rounded-lg"Content>
          <div className="grid" container spacing={2} alignItems="center">
            <div className="grid" item xs={12} md={3}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                fullWidth
                size="small"
                placeholder="Search news, tickers..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <Search />
                    </InputAdornment>
                  )
                }}
              />
            </div>
            <div className="grid" item xs={12} md={2}>
              <div className="mb-4" fullWidth size="small">
                <label className="block text-sm font-medium text-gray-700 mb-1">Timeframe</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={timeframe}
                  label="Timeframe"
                  onChange={(e) => setTimeframe(e.target.value)}
                >
                  <option  value="1h">Last Hour</option>
                  <option  value="6h">Last 6 Hours</option>
                  <option  value="24h">Last 24 Hours</option>
                  <option  value="7d">Last 7 Days</option>
                  <option  value="30d">Last 30 Days</option>
                </select>
              </div>
            </div>
            <div className="grid" item xs={12} md={2}>
              <div className="mb-4" fullWidth size="small">
                <label className="block text-sm font-medium text-gray-700 mb-1">Category</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={category}
                  label="Category"
                  onChange={(e) => setCategory(e.target.value)}
                >
                  <option  value="all">All Categories</option>
                  <option  value="earnings">Earnings</option>
                  <option  value="monetary-policy">Monetary Policy</option>
                  <option  value="economic-data">Economic Data</option>
                  <option  value="commodities">Commodities</option>
                  <option  value="healthcare">Healthcare</option>
                  <option  value="technology">Technology</option>
                  <option  value="geopolitics">Geopolitics</option>
                </select>
              </div>
            </div>
            <div className="grid" item xs={12} md={2}>
              <div className="mb-4" fullWidth size="small">
                <label className="block text-sm font-medium text-gray-700 mb-1">Impact Level</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={impactLevel}
                  label="Impact Level"
                  onChange={(e) => setImpactLevel(e.target.value)}
                >
                  <option  value="all">All Levels</option>
                  <option  value="high">High Impact</option>
                  <option  value="medium">Medium Impact</option>
                  <option  value="low">Low Impact</option>
                </select>
              </div>
            </div>
            <div className="grid" item xs={12} md={2}>
              <ToggleButtonGroup
                value={sortBy}
                exclusive
                onChange={(e, val) => val && setSortBy(val)}
                size="small"
                fullWidth
              >
                <ToggleButton value="time">Time</ToggleButton>
                <ToggleButton value="sentiment">Sentiment</ToggleButton>
                <ToggleButton value="impact">Impact</ToggleButton>
              </ToggleButtonGroup>
            </div>
            <div className="grid" item xs={12} md={1}>
              <div  title="Refresh data">
                <button className="p-2 rounded-full hover:bg-gray-100" onClick={() => { loadNewsData(); loadSentimentStats(); }}>
                  <Refresh />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content Tabs */}
      <div className="bg-white shadow-md rounded-lg">
        <div className="bg-white shadow-md rounded-lg"Content sx={{ pb: 0 }}>
          <div className="border-b border-gray-200" value={activeTab} onChange={(e, val) => setActiveTab(val)}>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Latest News" icon={<Article />} iconPosition="start" />
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Sentiment by Sector" icon={<Business />} iconPosition="start" />
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Sentiment Trends" icon={<Timeline />} iconPosition="start" />
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Impact Analysis" icon={<Assessment />} iconPosition="start" />
          </div>
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={0}>
          {loading ? (
            <div className="w-full bg-gray-200 rounded-full h-2" />
          ) : (
            <List>
              {filteredNews.map((article, index) => (
                <React.Fragment key={article.id}>
                  <ListItem alignItems="flex-start" sx={{ px: 3, py: 2 }}>
                    <ListItemAvatar>
                      <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ bgcolor: getSentimentColor(article.sentiment) + '1A' }}>
                        {getSentimentIcon(article.sentiment)}
                      </div>
                    </ListItemAvatar>
                    <ListItemText
                      primary={
                        <div  sx={{ mb: 1 }}>
                          <div  variant="h6" component="div" gutterBottom>
                            {article.title}
                          </div>
                          <div className="flex flex-col space-y-2" direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                              label={article.sentimentLabel}
                              size="small"
                              sx={{
                                bgcolor: getSentimentColor(article.sentiment) + '1A',
                                color: getSentimentColor(article.sentiment),
                                fontWeight: 600
                              }}
                            />
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                              label={article.impact.toUpperCase()}
                              size="small"
                              variant="outlined"
                              sx={{
                                borderColor: getImpactColor(article.impact),
                                color: getImpactColor(article.impact)
                              }}
                            />
                            <div  variant="caption" color="text.secondary">
                              {article.source} • {formatDistanceToNow(article.timestamp)} ago • {article.readTime} min read
                            </div>
                          </div>
                        </div>
                      }
                      secondary={
                        <div>
                          <div  variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                            {article.summary}
                          </div>
                          <div className="flex flex-col space-y-2" direction="row" spacing={2} flexWrap="wrap">
                            {article.sectors.length > 0 && (
                              <div>
                                <div  variant="caption" color="text.secondary">Sectors: </div>
                                {article.sectors.map(sector => (
                                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" key={sector} label={sector} size="small" sx={{ ml: 0.5 }} />
                                ))}
                              </div>
                            )}
                            {article.tickers.length > 0 && (
                              <div>
                                <div  variant="caption" color="text.secondary">Mentioned: </div>
                                {article.tickers.map(ticker => (
                                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                                    key={ticker}
                                    label={ticker}
                                    size="small"
                                    sx={{ ml: 0.5 }}
                                    onClick={() => window.location.href = `/stocks/${ticker}`}
                                  />
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      }
                    />
                  </ListItem>
                  {index < filteredNews.length - 1 && <hr className="border-gray-200" />}
                </React.Fragment>
              ))}
            </List>
          )}
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={1}>
          <div className="grid" container spacing={3}>
            {Object.entries(sentimentStats?.bySector || {}).map(([sector, data]) => (
              <div className="grid" item xs={12} md={6} key={sector}>
                <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2 }}>
                  <div  variant="h6" gutterBottom>{sector}</div>
                  <div  sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
                    <div  variant="h4" color={getSentimentColor(data.score)}>
                      {data.score > 0 ? '+' : ''}{(data.score * 100).toFixed(0)}%
                    </div>
                    <div  sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      {data.change > 0 ? (
                        <TrendingUp sx={{ fontSize: 16, color: '#4caf50' }} />
                      ) : (
                        <TrendingDown sx={{ fontSize: 16, color: '#f44336' }} />
                      )}
                      <div  variant="body2" color={data.change > 0 ? 'success.main' : 'error.main'}>
                        {Math.abs(data.change * 100).toFixed(0)}%
                      </div>
                    </div>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2"
                    variant="determinate"
                    value={50 + (data.score * 50)}
                    sx={{
                      height: 8,
                      borderRadius: 4,
                      bgcolor: '#9e9e9e1A',
                      '& .MuiLinearProgress-bar': {
                        bgcolor: getSentimentColor(data.score)
                      }
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={2}>
          <div  sx={{ p: 3 }}>
            <div  variant="h6" gutterBottom>Sentiment Momentum (Hourly)</div>
            <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, bgcolor: 'background.default' }}>
              <div className="flex flex-col space-y-2" spacing={2}>
                {sentimentStats?.momentum.hourly.map((value, index) => (
                  <div  key={index}>
                    <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                      <div  variant="body2">{sentimentStats.momentum.labels[index]}</div>
                      <div  variant="body2" fontWeight={600} color={getSentimentColor(value)}>
                        {value > 0 ? '+' : ''}{(value * 100).toFixed(0)}%
                      </div>
                    </div>
                    <div className="w-full bg-gray-200 rounded-full h-2"
                      variant="determinate"
                      value={50 + (value * 50)}
                      sx={{
                        height: 6,
                        borderRadius: 3,
                        bgcolor: '#9e9e9e1A',
                        '& .MuiLinearProgress-bar': {
                          bgcolor: getSentimentColor(value)
                        }
                      }}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={3}>
          <div className="grid" container spacing={3}>
            <div className="grid" item xs={12} md={6}>
              <div  variant="h6" gutterBottom>Top Bullish Mentions</div>
              <List>
                {sentimentStats?.topBullish.map(ticker => (
                  <ListItem key={ticker} sx={{ py: 1 }}>
                    <ListItemAvatar>
                      <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ bgcolor: '#4caf501A' }}>
                        <TrendingUp sx={{ color: '#4caf50' }} />
                      </div>
                    </ListItemAvatar>
                    <ListItemText
                      primary={ticker}
                      secondary="Strong positive sentiment"
                    />
                    <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      size="small"
                      onClick={() => window.location.href = `/stocks/${ticker}`}
                    >
                      View Details
                    </button>
                  </ListItem>
                ))}
              </List>
            </div>
            <div className="grid" item xs={12} md={6}>
              <div  variant="h6" gutterBottom>Top Bearish Mentions</div>
              <List>
                {sentimentStats?.topBearish.map(ticker => (
                  <ListItem key={ticker} sx={{ py: 1 }}>
                    <ListItemAvatar>
                      <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ bgcolor: '#f443361A' }}>
                        <TrendingDown sx={{ color: '#f44336' }} />
                      </div>
                    </ListItemAvatar>
                    <ListItemText
                      primary={ticker}
                      secondary="Strong negative sentiment"
                    />
                    <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      size="small"
                      onClick={() => window.location.href = `/stocks/${ticker}`}
                    >
                      View Details
                    </button>
                  </ListItem>
                ))}
              </List>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// Add missing import
const Remove = () => <div  sx={{ width: 20, height: 2, bgcolor: 'currentColor' }} />;

export default NewsSentiment;