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
  useTheme,
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
      {value === index && <Box sx={{ py: 2 }}>{children}</Box>}
    </div>
  );
}

const MarketCommentary = () => {
  const theme = useTheme();
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
      case 'bullish': return theme.palette.success.main;
      case 'bearish': return theme.palette.error.main;
      case 'mixed': return theme.palette.warning.main;
      case 'cautious': return theme.palette.info.main;
      default: return theme.palette.grey[500];
    }
  };

  const getImpactColor = (impact) => {
    switch (impact) {
      case 'high': return theme.palette.error.main;
      case 'medium': return theme.palette.warning.main;
      case 'low': return theme.palette.success.main;
      default: return theme.palette.grey[500];
    }
  };

  const getDirectionIcon = (direction) => {
    switch (direction) {
      case 'bullish': return <TrendingUp sx={{ color: theme.palette.success.main }} />;
      case 'bearish': return <TrendingDown sx={{ color: theme.palette.error.main }} />;
      case 'neutral': return <TrendingFlat sx={{ color: theme.palette.grey[500] }} />;
      default: return <TrendingFlat sx={{ color: theme.palette.grey[500] }} />;
    }
  };

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" fontWeight={700} gutterBottom>
          Market Commentary
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Expert market commentary and analysis from our research team
        </Typography>
      </Box>

      {/* Market Insights Overview */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                Current Market Regime
              </Typography>
              <Typography variant="h5" fontWeight={600} gutterBottom>
                {marketInsights?.marketRegime.current}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {marketInsights?.marketRegime.description}
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography variant="caption">Confidence:</Typography>
                <Chip 
                  label={`${(marketInsights?.marketRegime.confidence * 100).toFixed(0)}%`}
                  size="small"
                  color="primary"
                />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={8}>
          <Card>
            <CardHeader title="Weekly Market Outlook" />
            <CardContent>
              <Grid container spacing={2}>
                {Object.entries(marketInsights?.weeklyOutlook || {}).map(([index, data]) => (
                  <Grid item xs={6} md={3} key={index}>
                    <Box sx={{ textAlign: 'center' }}>
                      <Typography variant="subtitle2" sx={{ textTransform: 'uppercase' }}>
                        {index}
                      </Typography>
                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1, my: 1 }}>
                        {getDirectionIcon(data.direction)}
                        <Typography variant="body2" fontWeight={600} sx={{ textTransform: 'capitalize' }}>
                          {data.direction}
                        </Typography>
                      </Box>
                      <Typography variant="caption" color="text.secondary">
                        Target: {data.target}
                      </Typography>
                    </Box>
                  </Grid>
                ))}
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Filters */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} md={3}>
              <FormControl fullWidth size="small">
                <InputLabel>Timeframe</InputLabel>
                <Select
                  value={timeframe}
                  label="Timeframe"
                  onChange={(e) => setTimeframe(e.target.value)}
                >
                  <MenuItem value="day">Today</MenuItem>
                  <MenuItem value="week">This Week</MenuItem>
                  <MenuItem value="month">This Month</MenuItem>
                  <MenuItem value="quarter">This Quarter</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={3}>
              <FormControl fullWidth size="small">
                <InputLabel>Category</InputLabel>
                <Select
                  value={category}
                  label="Category"
                  onChange={(e) => setCategory(e.target.value)}
                >
                  <MenuItem value="all">All Categories</MenuItem>
                  <MenuItem value="monetary-policy">Monetary Policy</MenuItem>
                  <MenuItem value="sector-analysis">Sector Analysis</MenuItem>
                  <MenuItem value="thematic-investing">Thematic Investing</MenuItem>
                  <MenuItem value="global-macro">Global Macro</MenuItem>
                  <MenuItem value="technical-analysis">Technical Analysis</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={3}>
              <FormControl fullWidth size="small">
                <InputLabel>Author</InputLabel>
                <Select
                  value={author}
                  label="Author"
                  onChange={(e) => setAuthor(e.target.value)}
                >
                  <MenuItem value="all">All Authors</MenuItem>
                  <MenuItem value="sarah-mitchell">Sarah Mitchell</MenuItem>
                  <MenuItem value="michael-chen">Michael Chen</MenuItem>
                  <MenuItem value="elena-rodriguez">Elena Rodriguez</MenuItem>
                  <MenuItem value="david-thompson">David Thompson</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={3}>
              <Button
                variant="outlined"
                startIcon={<Refresh />}
                onClick={() => { loadCommentaryData(); loadMarketInsights(); }}
                fullWidth
              >
                Refresh
              </Button>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Main Content */}
      <Card>
        <CardContent sx={{ pb: 0 }}>
          <Tabs value={activeTab} onChange={(e, val) => setActiveTab(val)}>
            <Tab label="Latest Commentary" icon={<Article />} iconPosition="start" />
            <Tab label="Key Themes" icon={<Assessment />} iconPosition="start" />
            <Tab label="Risk Factors" icon={<Warning />} iconPosition="start" />
          </Tabs>
        </CardContent>

        <TabPanel value={activeTab} index={0}>
          <Stack spacing={3} sx={{ p: 3 }}>
            {commentary.map((article) => (
              <Card key={article.id} variant="outlined">
                <CardContent>
                  <Grid container spacing={2}>
                    <Grid item xs={12} md={8}>
                      <Typography variant="h6" gutterBottom>
                        {article.title}
                      </Typography>
                      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
                        <Avatar sx={{ width: 32, height: 32 }}>
                          {article.author.name.split(' ').map(n => n[0]).join('')}
                        </Avatar>
                        <Box>
                          <Typography variant="body2" fontWeight={600}>
                            {article.author.name}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {article.author.title}
                          </Typography>
                        </Box>
                        <Chip size="small" label={article.category.replace('-', ' ')} />
                        <Typography variant="caption" color="text.secondary">
                          {formatDistanceToNow(article.publishedAt)} ago • {article.readTime} min read
                        </Typography>
                      </Stack>
                      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                        {article.summary}
                      </Typography>
                      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
                        <Chip
                          label={article.sentiment}
                          size="small"
                          sx={{
                            bgcolor: alpha(getSentimentColor(article.sentiment), 0.1),
                            color: getSentimentColor(article.sentiment),
                            textTransform: 'capitalize'
                          }}
                        />
                        <Chip
                          label={`${article.marketImpact} Impact`}
                          size="small"
                          variant="outlined"
                          sx={{
                            borderColor: getImpactColor(article.marketImpact),
                            color: getImpactColor(article.marketImpact),
                            textTransform: 'capitalize'
                          }}
                        />
                      </Stack>
                      <Stack direction="row" spacing={2} flexWrap="wrap">
                        {article.tags.map(tag => (
                          <Chip key={tag} label={tag} size="small" variant="outlined" />
                        ))}
                      </Stack>
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <Typography variant="subtitle2" gutterBottom>Key Takeaways</Typography>
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
                        <Box sx={{ mt: 2 }}>
                          <Typography variant="subtitle2" gutterBottom>Related Stocks</Typography>
                          <Stack direction="row" spacing={1} flexWrap="wrap">
                            {article.relatedStocks.map(ticker => (
                              <Chip
                                key={ticker}
                                label={ticker}
                                size="small"
                                onClick={() => window.location.href = `/stocks/${ticker}`}
                                sx={{ cursor: 'pointer' }}
                              />
                            ))}
                          </Stack>
                        </Box>
                      )}
                      <Stack direction="row" spacing={2} sx={{ mt: 2 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          <Visibility sx={{ fontSize: 16 }} />
                          <Typography variant="caption">{article.views.toLocaleString()}</Typography>
                        </Box>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          <ThumbUp sx={{ fontSize: 16 }} />
                          <Typography variant="caption">{article.likes}</Typography>
                        </Box>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          <Comment sx={{ fontSize: 16 }} />
                          <Typography variant="caption">{article.comments}</Typography>
                        </Box>
                      </Stack>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>
            ))}
          </Stack>
        </TabPanel>

        <TabPanel value={activeTab} index={1}>
          <Box sx={{ p: 3 }}>
            <Grid container spacing={3}>
              {marketInsights?.keyThemes.map((theme, index) => (
                <Grid item xs={12} md={6} key={index}>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="h6" gutterBottom>{theme.theme}</Typography>
                      <Stack spacing={2}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Typography variant="body2">Impact Level:</Typography>
                          <Chip
                            label={theme.impact}
                            size="small"
                            sx={{
                              bgcolor: alpha(getImpactColor(theme.impact.toLowerCase()), 0.1),
                              color: getImpactColor(theme.impact.toLowerCase())
                            }}
                          />
                        </Box>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Typography variant="body2">Timeline:</Typography>
                          <Typography variant="body2" fontWeight={600}>{theme.timeline}</Typography>
                        </Box>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Typography variant="body2">Probability:</Typography>
                          <Typography variant="body2" fontWeight={600}>
                            {(theme.probability * 100).toFixed(0)}%
                          </Typography>
                        </Box>
                      </Stack>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          </Box>
        </TabPanel>

        <TabPanel value={activeTab} index={2}>
          <Box sx={{ p: 3 }}>
            <List>
              {marketInsights?.riskFactors.map((risk, index) => (
                <ListItem key={index}>
                  <ListItemAvatar>
                    <Avatar sx={{ bgcolor: alpha(theme.palette.warning.main, 0.1) }}>
                      <Warning sx={{ color: theme.palette.warning.main }} />
                    </Avatar>
                  </ListItemAvatar>
                  <ListItemText primary={risk} />
                </ListItem>
              ))}
            </List>
          </Box>
        </TabPanel>
      </Card>
    </Container>
  );
};

export default MarketCommentary;