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
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  InputAdornment,
  Tabs,
  Tab
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
  AcUnit,
  Person,
  Star,
  Bookmark,
  Share,
  ThumbUp,
  Comment,
  Visibility,
  TrendingFlat
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

const MarketCommentary = () => {
  const [activeTab, setActiveTab] = useState(0);
  const [commentary, setCommentary] = useState([]);
  const [marketInsights, setMarketInsights] = useState(null);
  const [loading, setLoading] = useState(true);
  const [timeframe, setTimeframe] = useState('week');
  const [category, setCategory] = useState('all');
  const [author, setAuthor] = useState('all');

  useEffect(() => {
    loadCommentaryData();
    loadMarketInsights();
  }, [timeframe, category, author]);

  const loadCommentaryData = async () => {
    setLoading(true);
    try {
      const response = await api.get('/research/commentary', {
        params: { timeframe, category, author }
      });
      setCommentary(response.data.articles || []);
    } catch (error) {
      console.error('Error loading commentary:', error);
      setCommentary(getMockCommentary());
    } finally {
      setLoading(false);
    }
  };

  const loadMarketInsights = async () => {
    try {
      const response = await api.get('/research/market-insights');
      setMarketInsights(response.data);
    } catch (error) {
      console.error('Error loading insights:', error);
      setMarketInsights(getMockInsights());
    }
  };

  const getMockCommentary = () => {
    return [
      {
        id: 1,
        title: "Fed's Next Move: Why Rate Cuts May Come Sooner Than Expected",
        author: {
          name: "Sarah Mitchell",
          title: "Chief Market Strategist",
          avatar: "/avatars/sarah.jpg",
          expertise: ["Federal Reserve", "Monetary Policy", "Fixed Income"]
        },
        publishedAt: new Date(Date.now() - 2 * 60 * 60 * 1000),
        category: "monetary-policy",
        readTime: 8,
        summary: "Recent economic indicators suggest the Federal Reserve may pivot more aggressively than markets anticipate. Key inflation metrics are cooling faster than expected...",
        content: "The Federal Reserve's dual mandate of price stability and full employment is creating interesting dynamics in the current market environment...",
        tags: ["Federal Reserve", "Interest Rates", "Inflation", "Bond Markets"],
        views: 12500,
        likes: 340,
        comments: 45,
        marketImpact: "high",
        sentiment: "bullish",
        keyTakeaways: [
          "Core PCE inflation trending below Fed's comfort zone",
          "Labor market showing signs of normalization",
          "Credit markets pricing in aggressive easing cycle"
        ],
        relatedStocks: ["TLT", "IEF", "JPM", "BAC"],
        url: "#"
      },
      {
        id: 2,
        title: "Tech Earnings Season: Separating AI Winners from Pretenders",
        author: {
          name: "Michael Chen",
          title: "Technology Sector Analyst",
          avatar: "/avatars/michael.jpg",
          expertise: ["Technology", "AI/ML", "Semiconductors"]
        },
        publishedAt: new Date(Date.now() - 6 * 60 * 60 * 1000),
        category: "sector-analysis",
        readTime: 12,
        summary: "Q4 earnings revealed which technology companies have genuine AI-driven revenue growth versus those riding the hype wave. Our analysis of 50+ tech earnings calls...",
        content: "The artificial intelligence revolution is creating clear winners and losers in the technology sector...",
        tags: ["Technology", "Artificial Intelligence", "Earnings", "Growth Stocks"],
        views: 18200,
        likes: 520,
        comments: 78,
        marketImpact: "high",
        sentiment: "mixed",
        keyTakeaways: [
          "AI infrastructure spending accelerating faster than expected",
          "Software companies showing mixed AI monetization success",
          "Semiconductor demand showing geographic shifts"
        ],
        relatedStocks: ["NVDA", "MSFT", "GOOGL", "META", "AMD"],
        url: "#"
      },
      {
        id: 3,
        title: "Energy Transition Investment Opportunities",
        author: {
          name: "Elena Rodriguez",
          title: "ESG Investment Director",
          avatar: "/avatars/elena.jpg",
          expertise: ["ESG", "Energy", "Clean Technology"]
        },
        publishedAt: new Date(Date.now() - 12 * 60 * 60 * 1000),
        category: "thematic-investing",
        readTime: 10,
        summary: "The energy transition is creating unprecedented investment opportunities across multiple sectors. From utility-scale storage to electric vehicle infrastructure...",
        content: "The global energy transition represents one of the largest capital reallocation events in human history...",
        tags: ["Energy Transition", "ESG", "Clean Energy", "Infrastructure"],
        views: 9800,
        likes: 280,
        comments: 32,
        marketImpact: "medium",
        sentiment: "bullish",
        keyTakeaways: [
          "Grid modernization driving utility capex cycles",
          "EV charging infrastructure reaching inflection point",
          "Energy storage costs declining faster than projected"
        ],
        relatedStocks: ["TSLA", "ENPH", "SEDG", "NEE", "XEL"],
        url: "#"
      },
      {
        id: 4,
        title: "Geopolitical Risk Assessment: Markets in 2025",
        author: {
          name: "David Thompson",
          title: "Global Macro Strategist",
          avatar: "/avatars/david.jpg",
          expertise: ["Geopolitics", "Global Macro", "Currency Markets"]
        },
        publishedAt: new Date(Date.now() - 18 * 60 * 60 * 1000),
        category: "global-macro",
        readTime: 15,
        summary: "Political tensions and trade relationships will significantly impact market dynamics in 2025. Our framework for assessing geopolitical risk across asset classes...",
        content: "Geopolitical risk assessment has become increasingly complex in our multipolar world...",
        tags: ["Geopolitics", "Global Markets", "Risk Management", "Currency"],
        views: 15600,
        likes: 410,
        comments: 67,
        marketImpact: "high",
        sentiment: "cautious",
        keyTakeaways: [
          "Supply chain diversification accelerating",
          "Currency volatility likely to persist",
          "Defense spending creating investment themes"
        ],
        relatedStocks: ["GLD", "UUP", "EFA", "EEM", "VIX"],
        url: "#"
      }
    ];
  };

  const getMockInsights = () => {
    return {
      marketRegime: {
        current: "Transitional",
        confidence: 0.75,
        description: "Markets showing mixed signals with growth concerns offset by Fed dovishness"
      },
      keyThemes: [
        {
          theme: "AI Infrastructure Build-out",
          impact: "High",
          timeline: "12-24 months",
          probability: 0.85
        },
        {
          theme: "Federal Reserve Policy Pivot",
          impact: "High", 
          timeline: "3-6 months",
          probability: 0.70
        },
        {
          theme: "Energy Transition Acceleration",
          impact: "Medium",
          timeline: "24-36 months",
          probability: 0.90
        }
      ],
      weeklyOutlook: {
        sp500: { direction: "neutral", confidence: 0.60, target: "5800-6000" },
        nasdaq: { direction: "bullish", confidence: 0.70, target: "19500-20500" },
        russell2000: { direction: "bullish", confidence: 0.65, target: "2400-2600" },
        bonds: { direction: "bullish", confidence: 0.75, target: "TLT 95-100" }
      },
      riskFactors: [
        "Inflation persistence beyond Fed projections",
        "Geopolitical tensions in key regions",
        "AI investment bubble concerns",
        "Credit market stress indicators"
      ]
    };
  };

  const getSentimentColor = (sentiment) => {
    switch (sentiment) {
      case 'bullish': return '#4caf50';
      case 'bearish': return '#f44336';
      case 'mixed': return '#ff9800';
      case 'cautious': return '#2196f3';
      default: return '#9e9e9e';
    }
  };

  const getImpactColor = (impact) => {
    switch (impact) {
      case 'high': return '#f44336';
      case 'medium': return '#ff9800';
      case 'low': return '#4caf50';
      default: return '#9e9e9e';
    }
  };

  const getDirectionIcon = (direction) => {
    switch (direction) {
      case 'bullish': return <TrendingUp sx={{ color: '#4caf50' }} />;
      case 'bearish': return <TrendingDown sx={{ color: '#f44336' }} />;
      case 'neutral': return <TrendingFlat sx={{ color: '#9e9e9e' }} />;
      default: return <TrendingFlat sx={{ color: '#9e9e9e' }} />;
    }
  };

  return (
    <div className="container mx-auto" maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      {/* Header */}
      <div  sx={{ mb: 4 }}>
        <div  variant="h4" fontWeight={700} gutterBottom>
          Market Commentary
        </div>
        <div  variant="body1" color="text.secondary">
          Expert market commentary and analysis from our research team
        </div>
      </div>

      {/* Market Insights Overview */}
      <div className="grid" container spacing={3} sx={{ mb: 4 }}>
        <div className="grid" item xs={12} md={4}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="subtitle2" color="text.secondary" gutterBottom>
                Current Market Regime
              </div>
              <div  variant="h5" fontWeight={600} gutterBottom>
                {marketInsights?.marketRegime.current}
              </div>
              <div  variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {marketInsights?.marketRegime.description}
              </div>
              <div  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <div  variant="caption">Confidence:</div>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                  label={`${(marketInsights?.marketRegime.confidence * 100).toFixed(0)}%`}
                  size="small"
                  color="primary"
                />
              </div>
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={8}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Header title="Weekly Market Outlook" />
            <div className="bg-white shadow-md rounded-lg"Content>
              <div className="grid" container spacing={2}>
                {Object.entries(marketInsights?.weeklyOutlook || {}).map(([index, data]) => (
                  <div className="grid" item xs={6} md={3} key={index}>
                    <div  sx={{ textAlign: 'center' }}>
                      <div  variant="subtitle2" sx={{ textTransform: 'uppercase' }}>
                        {index}
                      </div>
                      <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1, my: 1 }}>
                        {getDirectionIcon(data.direction)}
                        <div  variant="body2" fontWeight={600} sx={{ textTransform: 'capitalize' }}>
                          {data.direction}
                        </div>
                      </div>
                      <div  variant="caption" color="text.secondary">
                        Target: {data.target}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
        <div className="bg-white shadow-md rounded-lg"Content>
          <div className="grid" container spacing={2} alignItems="center">
            <div className="grid" item xs={12} md={3}>
              <div className="mb-4" fullWidth size="small">
                <label className="block text-sm font-medium text-gray-700 mb-1">Timeframe</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={timeframe}
                  label="Timeframe"
                  onChange={(e) => setTimeframe(e.target.value)}
                >
                  <option  value="day">Today</option>
                  <option  value="week">This Week</option>
                  <option  value="month">This Month</option>
                  <option  value="quarter">This Quarter</option>
                </select>
              </div>
            </div>
            <div className="grid" item xs={12} md={3}>
              <div className="mb-4" fullWidth size="small">
                <label className="block text-sm font-medium text-gray-700 mb-1">Category</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={category}
                  label="Category"
                  onChange={(e) => setCategory(e.target.value)}
                >
                  <option  value="all">All Categories</option>
                  <option  value="monetary-policy">Monetary Policy</option>
                  <option  value="sector-analysis">Sector Analysis</option>
                  <option  value="thematic-investing">Thematic Investing</option>
                  <option  value="global-macro">Global Macro</option>
                  <option  value="technical-analysis">Technical Analysis</option>
                </select>
              </div>
            </div>
            <div className="grid" item xs={12} md={3}>
              <div className="mb-4" fullWidth size="small">
                <label className="block text-sm font-medium text-gray-700 mb-1">Author</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={author}
                  label="Author"
                  onChange={(e) => setAuthor(e.target.value)}
                >
                  <option  value="all">All Authors</option>
                  <option  value="sarah-mitchell">Sarah Mitchell</option>
                  <option  value="michael-chen">Michael Chen</option>
                  <option  value="elena-rodriguez">Elena Rodriguez</option>
                  <option  value="david-thompson">David Thompson</option>
                </select>
              </div>
            </div>
            <div className="grid" item xs={12} md={3}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="outlined"
                startIcon={<Refresh />}
                onClick={() => { loadCommentaryData(); loadMarketInsights(); }}
                fullWidth
              >
                Refresh
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="bg-white shadow-md rounded-lg">
        <div className="bg-white shadow-md rounded-lg"Content sx={{ pb: 0 }}>
          <div className="border-b border-gray-200" value={activeTab} onChange={(e, val) => setActiveTab(val)}>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Latest Commentary" icon={<Article />} iconPosition="start" />
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Key Themes" icon={<Assessment />} iconPosition="start" />
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Risk Factors" icon={<Warning />} iconPosition="start" />
          </div>
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={0}>
          <div className="flex flex-col space-y-2" spacing={3} sx={{ p: 3 }}>
            {commentary.map((article) => (
              <div className="bg-white shadow-md rounded-lg" key={article.id} variant="outlined">
                <div className="bg-white shadow-md rounded-lg"Content>
                  <div className="grid" container spacing={2}>
                    <div className="grid" item xs={12} md={8}>
                      <div  variant="h6" gutterBottom>
                        {article.title}
                      </div>
                      <div className="flex flex-col space-y-2" direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
                        <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ width: 32, height: 32 }}>
                          {article.author.name.split(' ').map(n => n[0]).join('')}
                        </div>
                        <div>
                          <div  variant="body2" fontWeight={600}>
                            {article.author.name}
                          </div>
                          <div  variant="caption" color="text.secondary">
                            {article.author.title}
                          </div>
                        </div>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" size="small" label={article.category.replace('-', ' ')} />
                        <div  variant="caption" color="text.secondary">
                          {formatDistanceToNow(article.publishedAt)} ago • {article.readTime} min read
                        </div>
                      </div>
                      <div  variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                        {article.summary}
                      </div>
                      <div className="flex flex-col space-y-2" direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                          label={article.sentiment}
                          size="small"
                          sx={{
                            bgcolor: getSentimentColor(article.sentiment) + '1A',
                            color: getSentimentColor(article.sentiment),
                            textTransform: 'capitalize'
                          }}
                        />
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                          label={`${article.marketImpact} Impact`}
                          size="small"
                          variant="outlined"
                          sx={{
                            borderColor: getImpactColor(article.marketImpact),
                            color: getImpactColor(article.marketImpact),
                            textTransform: 'capitalize'
                          }}
                        />
                      </div>
                      <div className="flex flex-col space-y-2" direction="row" spacing={2} flexWrap="wrap">
                        {article.tags.map(tag => (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" key={tag} label={tag} size="small" variant="outlined" />
                        ))}
                      </div>
                    </div>
                    <div className="grid" item xs={12} md={4}>
                      <div  variant="subtitle2" gutterBottom>Key Takeaways</div>
                      <List dense>
                        {article.keyTakeaways.map((takeaway, index) => (
                          <ListItem key={index} sx={{ py: 0.5 }}>
                            <ListItemText 
                              primary={takeaway}
                              primaryTypographyProps={{ variant: 'body2' }}
                            />
                          </ListItem>
                        ))}
                      </List>
                      {article.relatedStocks.length > 0 && (
                        <div  sx={{ mt: 2 }}>
                          <div  variant="subtitle2" gutterBottom>Related Stocks</div>
                          <div className="flex flex-col space-y-2" direction="row" spacing={1} flexWrap="wrap">
                            {article.relatedStocks.map(ticker => (
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                                key={ticker}
                                label={ticker}
                                size="small"
                                onClick={() => window.location.href = `/stocks/${ticker}`}
                                sx={{ cursor: 'pointer' }}
                              />
                            ))}
                          </div>
                        </div>
                      )}
                      <div className="flex flex-col space-y-2" direction="row" spacing={2} sx={{ mt: 2 }}>
                        <div  sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          <Visibility sx={{ fontSize: 16 }} />
                          <div  variant="caption">{article.views.toLocaleString()}</div>
                        </div>
                        <div  sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          <ThumbUp sx={{ fontSize: 16 }} />
                          <div  variant="caption">{article.likes}</div>
                        </div>
                        <div  sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          <Comment sx={{ fontSize: 16 }} />
                          <div  variant="caption">{article.comments}</div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={1}>
          <div  sx={{ p: 3 }}>
            <div className="grid" container spacing={3}>
              {marketInsights?.keyThemes.map((theme, index) => (
                <div className="grid" item xs={12} md={6} key={index}>
                  <div className="bg-white shadow-md rounded-lg" variant="outlined">
                    <div className="bg-white shadow-md rounded-lg"Content>
                      <div  variant="h6" gutterBottom>{theme.theme}</div>
                      <div className="flex flex-col space-y-2" spacing={2}>
                        <div  sx={{ display: 'flex', justifyContent: 'space-between' }}>
                          <div  variant="body2">Impact Level:</div>
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                            label={theme.impact}
                            size="small"
                            sx={{
                              bgcolor: getImpactColor(theme.impact.toLowerCase()) + '1A',
                              color: getImpactColor(theme.impact.toLowerCase())
                            }}
                          />
                        </div>
                        <div  sx={{ display: 'flex', justifyContent: 'space-between' }}>
                          <div  variant="body2">Timeline:</div>
                          <div  variant="body2" fontWeight={600}>{theme.timeline}</div>
                        </div>
                        <div  sx={{ display: 'flex', justifyContent: 'space-between' }}>
                          <div  variant="body2">Probability:</div>
                          <div  variant="body2" fontWeight={600}>
                            {(theme.probability * 100).toFixed(0)}%
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={2}>
          <div  sx={{ p: 3 }}>
            <List>
              {marketInsights?.riskFactors.map((risk, index) => (
                <ListItem key={index}>
                  <ListItemAvatar>
                    <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ bgcolor: '#ff98001A' }}>
                      <Warning sx={{ color: '#ff9800' }} />
                    </div>
                  </ListItemAvatar>
                  <ListItemText primary={risk} />
                </ListItem>
              ))}
            </List>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MarketCommentary;