import React, { useState, useEffect } from "react";
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
  CircularProgress,
  TextField,
  IconButton,
  LinearProgress,
  Divider,
  Switch,
  FormControlLabel,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Autocomplete,
  Rating,
  List,
  ListItem,
  ListItemText,
  ListItemAvatar,
  Avatar,
  alpha,
  useTheme,
  Collapse,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
} from "@mui/material";
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  LineChart,
  Line,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  Legend,
  Tooltip as RechartsTooltip,
} from "recharts";
import {
  TrendingUp,
  TrendingDown,
  Assessment,
  AccountBalance,
  Info,
  Speed,
  Psychology,
  Groups,
  Stars,
  Lightbulb,
  School,
  WorkspacePremium,
  Refresh,
  Download,
  ExpandMore,
  Security,
  CompareArrows,
  Remove,
} from "@mui/icons-material";

// Custom styled components
const ScoreGauge = ({
  score,
  size = 120,
  thickness = 10,
  showGrade = true,
}) => {
  const theme = useTheme();

  const getColor = (value) => {
    if (value >= 80) return theme.palette.success.main;
    if (value >= 60) return theme.palette.warning.main;
    if (value >= 40) return theme.palette.info.main;
    return theme.palette.error.main;
  };

  const getGrade = (value) => {
    if (value >= 90) return "A+";
    if (value >= 85) return "A";
    if (value >= 80) return "A-";
    if (value >= 75) return "B+";
    if (value >= 70) return "B";
    if (value >= 65) return "B-";
    if (value >= 60) return "C+";
    if (value >= 55) return "C";
    if (value >= 50) return "C-";
    if (value >= 45) return "D+";
    if (value >= 40) return "D";
    return "F";
  };

  const data = [
    { name: "Score", value: score, fill: getColor(score) },
    {
      name: "Remaining",
      value: 100 - score,
      fill: alpha(theme.palette.action.disabled, 0.1),
    },
  ];

  return (
    <Box sx={{ position: "relative", width: size, height: size }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            startAngle={90}
            endAngle={-270}
            innerRadius={size / 2 - thickness}
            outerRadius={size / 2}
            dataKey="value"
            stroke="none"
          >
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.fill} />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <Box
        sx={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          textAlign: "center",
        }}
      >
        <Typography variant="h4" fontWeight={700}>
          {score}
        </Typography>
        {showGrade && (
          <Typography variant="h6" color={getColor(score)} fontWeight={600}>
            {getGrade(score)}
          </Typography>
        )}
      </Box>
    </Box>
  );
};

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`scores-tabpanel-${index}`}
      aria-labelledby={`scores-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ py: 3 }}>{children}</Box>}
    </div>
  );
}

const ScoresDashboard = () => {
  const theme = useTheme();
  const [activeTab, setActiveTab] = useState(0);
  const [selectedStock, setSelectedStock] = useState(null);
  const [stockOptions, setStockOptions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [scores, setScores] = useState(null);
  const [historicalScores, setHistoricalScores] = useState([]);
  const [peerComparison, setPeerComparison] = useState([]);
  const [expandedCategories, setExpandedCategories] = useState({});
  const [selectedTimeframe, setSelectedTimeframe] = useState("3M");
  const [_watchlist, _setWatchlist] = useState([]);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [_compareMode, _setCompareMode] = useState(false);
  const [_selectedPeers, _setSelectedPeers] = useState([]);

  // Mock data for demonstration
  const mockScores = {
    symbol: "AAPL",
    company_name: "Apple Inc.",
    composite: 82,
    quality: {
      composite: 88,
      earnings_quality: 92,
      balance_strength: 85,
      profitability: 89,
      management: 86,
      trend: "improving",
    },
    growth: {
      composite: 78,
      revenue_growth: 76,
      earnings_growth: 82,
      fundamental_growth: 78,
      market_expansion: 75,
      trend: "stable",
    },
    value: {
      composite: 65,
      pe_score: 62,
      dcf_score: 68,
      relative_value: 65,
      trend: "improving",
    },
    momentum: {
      composite: 85,
      price_momentum: 88,
      fundamental_momentum: 82,
      technical: 86,
      volume_analysis: 80,
      trend: "strong",
    },
    sentiment: {
      composite: 79,
      analyst_sentiment: 82,
      social_sentiment: 75,
      market_sentiment: 78,
      news_sentiment: 81,
      trend: "improving",
    },
    positioning: {
      composite: 84,
      institutional: 86,
      insider: 78,
      short_interest: 85,
      options_flow: 88,
      trend: "bullish",
    },
    market_regime: "bull",
    confidence_level: 92,
    last_updated: new Date().toISOString(),
  };

  const scoreCategories = [
    {
      id: "quality",
      title: "Quality Score",
      icon: <Stars />,
      description:
        "Earnings quality, balance sheet strength, profitability, and management effectiveness",
      color: theme.palette.primary.main,
      academicBasis:
        "Based on Piotroski F-Score (2000) and Altman Z-Score (1968)",
      weight: 0.2,
      subScores: [
        {
          name: "Earnings Quality",
          key: "earnings_quality",
          weight: "25%",
          description: "Cash flow vs. accruals analysis",
        },
        {
          name: "Balance Sheet Strength",
          key: "balance_strength",
          weight: "30%",
          description: "Financial stability metrics",
        },
        {
          name: "Profitability Metrics",
          key: "profitability",
          weight: "25%",
          description: "ROIC, ROE, and margins",
        },
        {
          name: "Management Effectiveness",
          key: "management",
          weight: "20%",
          description: "Capital allocation efficiency",
        },
      ],
    },
    {
      id: "growth",
      title: "Growth Score",
      icon: <TrendingUp />,
      description:
        "Revenue growth, earnings growth, fundamental drivers, and market expansion potential",
      color: theme.palette.success.main,
      academicBasis: "Sustainable Growth Rate model (Higgins, 1977)",
      weight: 0.2,
      subScores: [
        {
          name: "Revenue Growth Analysis",
          key: "revenue_growth",
          weight: "30%",
          description: "Organic growth assessment",
        },
        {
          name: "Earnings Growth Quality",
          key: "earnings_growth",
          weight: "30%",
          description: "EPS growth decomposition",
        },
        {
          name: "Fundamental Growth Drivers",
          key: "fundamental_growth",
          weight: "25%",
          description: "ROA trends and efficiency",
        },
        {
          name: "Market Expansion Potential",
          key: "market_expansion",
          weight: "15%",
          description: "TAM and penetration analysis",
        },
      ],
    },
    {
      id: "value",
      title: "Value Score",
      icon: <AccountBalance />,
      description:
        "Traditional multiples, intrinsic value analysis, and relative value assessment",
      color: theme.palette.info.main,
      academicBasis: "Fama-French Value Factor (1992)",
      weight: 0.2,
      subScores: [
        {
          name: "Traditional Multiple Analysis",
          key: "pe_score",
          weight: "40%",
          description: "P/E, P/B, EV/EBITDA ratios",
        },
        {
          name: "Intrinsic Value Analysis",
          key: "dcf_score",
          weight: "35%",
          description: "DCF and residual income models",
        },
        {
          name: "Relative Value Assessment",
          key: "relative_value",
          weight: "25%",
          description: "Peer and historical comparison",
        },
      ],
    },
    {
      id: "momentum",
      title: "Momentum Score",
      icon: <Speed />,
      description:
        "Price momentum, fundamental momentum, technical indicators, and volume analysis",
      color: theme.palette.warning.main,
      academicBasis: "Jegadeesh-Titman Momentum (1993)",
      weight: 0.15,
      subScores: [
        {
          name: "Price Momentum",
          key: "price_momentum",
          weight: "40%",
          description: "12-1 month returns",
        },
        {
          name: "Fundamental Momentum",
          key: "fundamental_momentum",
          weight: "30%",
          description: "Earnings revision trends",
        },
        {
          name: "Technical Momentum",
          key: "technical",
          weight: "20%",
          description: "Moving averages and RSI",
        },
        {
          name: "Volume Analysis",
          key: "volume_analysis",
          weight: "10%",
          description: "On-balance volume trends",
        },
      ],
    },
    {
      id: "sentiment",
      title: "Sentiment Score",
      icon: <Psychology />,
      description:
        "Analyst sentiment, social sentiment, market-based sentiment, and news sentiment",
      color: theme.palette.secondary.main,
      academicBasis: "Baker & Wurgler Sentiment Index (2006)",
      weight: 0.15,
      subScores: [
        {
          name: "Analyst Sentiment",
          key: "analyst_sentiment",
          weight: "25%",
          description: "Recommendation changes",
        },
        {
          name: "Social Sentiment",
          key: "social_sentiment",
          weight: "25%",
          description: "Reddit and social media NLP",
        },
        {
          name: "Market-Based Sentiment",
          key: "market_sentiment",
          weight: "25%",
          description: "Put/call ratios and skew",
        },
        {
          name: "News Sentiment",
          key: "news_sentiment",
          weight: "25%",
          description: "Financial news NLP analysis",
        },
      ],
    },
    {
      id: "positioning",
      title: "Positioning Score",
      icon: <Groups />,
      description:
        "Institutional holdings, insider activity, short interest dynamics, and options flow",
      color: theme.palette.error.main,
      academicBasis: "Smart Money Tracking (13F Analysis)",
      weight: 0.1,
      subScores: [
        {
          name: "Institutional Holdings",
          key: "institutional",
          weight: "40%",
          description: "13F filing analysis",
        },
        {
          name: "Insider Activity",
          key: "insider",
          weight: "25%",
          description: "Form 4 transactions",
        },
        {
          name: "Short Interest Dynamics",
          key: "short_interest",
          weight: "20%",
          description: "Days to cover trends",
        },
        {
          name: "Options Flow Analysis",
          key: "options_flow",
          weight: "15%",
          description: "Unusual options activity",
        },
      ],
    },
  ];

  // Load stock options
  useEffect(() => {
    const loadStockOptions = async () => {
      try {
        // Mock data for demonstration
        setStockOptions([
          { symbol: "AAPL", company_name: "Apple Inc." },
          { symbol: "MSFT", company_name: "Microsoft Corporation" },
          { symbol: "GOOGL", company_name: "Alphabet Inc." },
          { symbol: "AMZN", company_name: "Amazon.com Inc." },
          { symbol: "NVDA", company_name: "NVIDIA Corporation" },
          { symbol: "META", company_name: "Meta Platforms Inc." },
          { symbol: "TSLA", company_name: "Tesla Inc." },
          { symbol: "BRK.B", company_name: "Berkshire Hathaway Inc." },
        ]);
      } catch (error) {
        console.error("Error loading stock options:", error);
      }
    };
    loadStockOptions();
  }, []);

  // Load scores when stock is selected
  useEffect(() => {
    if (selectedStock) {
      loadScores(selectedStock.symbol);
      loadHistoricalScores(selectedStock.symbol);
      loadPeerComparison(selectedStock.symbol);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedStock, selectedTimeframe]);

  const loadScores = async (_symbol) => {
    setLoading(true);
    try {
      // Mock data loading
      setTimeout(() => {
        setScores(mockScores);
        setLoading(false);
      }, 1000);
    } catch (error) {
      console.error("Error loading scores:", error);
      setLoading(false);
    }
  };

  const loadHistoricalScores = () => {
    // Mock historical data
    const mockHistorical = Array.from({ length: 90 }, (_, i) => {
      const date = new Date();
      date.setDate(date.getDate() - (90 - i));
      return {
        date: date.toISOString().split("T")[0],
        composite: 75 + Math.random() * 15 + (i / 90) * 5,
        quality: 80 + Math.random() * 10 + (i / 90) * 3,
        growth: 70 + Math.random() * 15 + (i / 90) * 4,
        value: 60 + Math.random() * 20 + (i / 90) * 2,
        momentum: 75 + Math.random() * 20 + (i / 90) * 6,
        sentiment: 65 + Math.random() * 25 + (i / 90) * 5,
        positioning: 70 + Math.random() * 20 + (i / 90) * 3,
      };
    });
    setHistoricalScores(mockHistorical);
  };

  const loadPeerComparison = () => {
    // Mock peer comparison data
    const mockPeers = [
      {
        symbol: "AAPL",
        name: "Apple",
        composite: 82,
        quality: 88,
        growth: 78,
        value: 65,
        momentum: 85,
        sentiment: 79,
        positioning: 84,
      },
      {
        symbol: "MSFT",
        name: "Microsoft",
        composite: 85,
        quality: 90,
        growth: 82,
        value: 70,
        momentum: 80,
        sentiment: 85,
        positioning: 88,
      },
      {
        symbol: "GOOGL",
        name: "Google",
        composite: 78,
        quality: 85,
        growth: 75,
        value: 68,
        momentum: 78,
        sentiment: 72,
        positioning: 80,
      },
      {
        symbol: "AMZN",
        name: "Amazon",
        composite: 76,
        quality: 82,
        growth: 88,
        value: 55,
        momentum: 75,
        sentiment: 70,
        positioning: 78,
      },
      {
        symbol: "META",
        name: "Meta",
        composite: 72,
        quality: 78,
        growth: 70,
        value: 75,
        momentum: 68,
        sentiment: 65,
        positioning: 72,
      },
    ];
    setPeerComparison(mockPeers);
  };

  const handleCategoryToggle = (categoryId) => {
    setExpandedCategories((prev) => ({
      ...prev,
      [categoryId]: !prev[categoryId],
    }));
  };

  const getScoreInterpretation = (score) => {
    if (score >= 90)
      return { label: "Exceptional", color: theme.palette.success.dark };
    if (score >= 80)
      return { label: "Strong", color: theme.palette.success.main };
    if (score >= 70)
      return { label: "Good", color: theme.palette.success.light };
    if (score >= 60)
      return { label: "Fair", color: theme.palette.warning.main };
    if (score >= 50)
      return { label: "Weak", color: theme.palette.warning.light };
    if (score >= 40) return { label: "Poor", color: theme.palette.error.light };
    return { label: "Critical", color: theme.palette.error.main };
  };

  const getTrendIcon = (trend) => {
    switch (trend) {
      case "improving":
        return <TrendingUp sx={{ color: theme.palette.success.main }} />;
      case "declining":
        return <TrendingDown sx={{ color: theme.palette.error.main }} />;
      case "stable":
        return <Remove sx={{ color: theme.palette.info.main }} />;
      default:
        return <Remove />;
    }
  };

  const renderMainDashboard = () => (
    <Grid container spacing={3}>
      {/* Stock Selection */}
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Grid container spacing={3} alignItems="center">
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>
                  Select Stock for Analysis
                </Typography>
                <Autocomplete
                  options={stockOptions}
                  getOptionLabel={(option) =>
                    `${option.symbol} - ${option.company_name}`
                  }
                  value={selectedStock}
                  onChange={(event, newValue) => setSelectedStock(newValue)}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Search stocks..."
                      variant="outlined"
                      placeholder="Type symbol or company name"
                    />
                  )}
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
                  <ToggleButtonGroup
                    value={selectedTimeframe}
                    exclusive
                    onChange={(e, value) =>
                      value && setSelectedTimeframe(value)
                    }
                    size="small"
                  >
                    <ToggleButton value="1W">1W</ToggleButton>
                    <ToggleButton value="1M">1M</ToggleButton>
                    <ToggleButton value="3M">3M</ToggleButton>
                    <ToggleButton value="6M">6M</ToggleButton>
                    <ToggleButton value="1Y">1Y</ToggleButton>
                  </ToggleButtonGroup>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={showAdvanced}
                        onChange={(e) => setShowAdvanced(e.target.checked)}
                      />
                    }
                    label="Advanced View"
                  />
                  <IconButton
                    color="primary"
                    onClick={() =>
                      selectedStock && loadScores(selectedStock.symbol)
                    }
                  >
                    <Refresh />
                  </IconButton>
                </Box>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Grid>

      {loading && (
        <Grid item xs={12}>
          <Box sx={{ display: "flex", justifyContent: "center", my: 4 }}>
            <CircularProgress />
          </Box>
        </Grid>
      )}

      {scores && selectedStock && !loading && (
        <>
          {/* Composite Score Hero Card */}
          <Grid item xs={12}>
            <Card
              sx={{
                background: `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.1)} 0%, ${alpha(theme.palette.secondary.main, 0.1)} 100%)`,
                border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`,
              }}
            >
              <CardContent>
                <Grid container spacing={3} alignItems="center">
                  <Grid item xs={12} md={3}>
                    <ScoreGauge
                      score={scores.composite}
                      size={180}
                      thickness={15}
                    />
                  </Grid>
                  <Grid item xs={12} md={5}>
                    <Typography variant="h4" fontWeight={700} gutterBottom>
                      {selectedStock.symbol} - {selectedStock.company_name}
                    </Typography>
                    <Typography
                      variant="h6"
                      color="text.secondary"
                      gutterBottom
                    >
                      Composite Score Analysis
                    </Typography>
                    <Box
                      sx={{ display: "flex", gap: 2, flexWrap: "wrap", mt: 2 }}
                    >
                      <Chip
                        icon={<WorkspacePremium />}
                        label={getScoreInterpretation(scores.composite).label}
                        color="primary"
                        sx={{ fontWeight: 600 }}
                      />
                      <Chip
                        icon={<Speed />}
                        label={`Market Regime: ${scores.market_regime.toUpperCase()}`}
                        variant="outlined"
                      />
                      <Chip
                        icon={<Security />}
                        label={`Confidence: ${scores.confidence_level}%`}
                        variant="outlined"
                      />
                    </Box>
                  </Grid>
                  <Grid item xs={12} md={4}>
                    <Paper
                      sx={{
                        p: 2,
                        backgroundColor: alpha(
                          theme.palette.background.paper,
                          0.8
                        ),
                      }}
                    >
                      <Typography
                        variant="subtitle2"
                        color="text.secondary"
                        gutterBottom
                      >
                        Investment Recommendation
                      </Typography>
                      <Rating
                        value={scores.composite / 20}
                        readOnly
                        precision={0.5}
                        size="large"
                      />
                      <Typography
                        variant="h6"
                        color={getScoreInterpretation(scores.composite).color}
                        sx={{ mt: 1 }}
                      >
                        {scores.composite >= 70
                          ? "Strong Buy"
                          : scores.composite >= 50
                            ? "Hold"
                            : "Avoid"}
                      </Typography>
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{ mt: 1 }}
                      >
                        Based on institutional-grade multi-factor analysis
                      </Typography>
                    </Paper>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Grid>

          {/* Category Scores Grid */}
          <Grid item xs={12}>
            <Typography variant="h5" gutterBottom sx={{ mb: 2 }}>
              Six-Factor Analysis
            </Typography>
          </Grid>

          {scoreCategories.map((category) => {
            const categoryScore = scores[category.id];
            const isExpanded = expandedCategories[category.id];

            return (
              <Grid item xs={12} md={6} lg={4} key={category.id}>
                <Card
                  sx={{
                    height: "100%",
                    transition: "all 0.3s ease",
                    "&:hover": {
                      transform: "translateY(-4px)",
                      boxShadow: theme.shadows[8],
                    },
                  }}
                >
                  <CardHeader
                    avatar={
                      <Avatar
                        sx={{
                          bgcolor: alpha(category.color, 0.1),
                          color: category.color,
                        }}
                      >
                        {category.icon}
                      </Avatar>
                    }
                    action={
                      <Box
                        sx={{ display: "flex", alignItems: "center", gap: 1 }}
                      >
                        {getTrendIcon(categoryScore.trend)}
                        <IconButton
                          onClick={() => handleCategoryToggle(category.id)}
                          size="small"
                        >
                          {isExpanded ? (
                            <ExpandMore />
                          ) : (
                            <ExpandMore sx={{ transform: "rotate(-90deg)" }} />
                          )}
                        </IconButton>
                      </Box>
                    }
                    title={
                      <Box
                        sx={{ display: "flex", alignItems: "center", gap: 1 }}
                      >
                        <Typography variant="h6">{category.title}</Typography>
                        <Tooltip title={category.description}>
                          <Info
                            sx={{ fontSize: 16, color: "text.secondary" }}
                          />
                        </Tooltip>
                      </Box>
                    }
                    subheader={
                      <Typography variant="caption" color="text.secondary">
                        Weight: {(category.weight * 100).toFixed(0)}% •{" "}
                        {category.academicBasis}
                      </Typography>
                    }
                  />
                  <CardContent>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 3 }}>
                      <ScoreGauge
                        score={categoryScore.composite}
                        size={100}
                        thickness={8}
                        showGrade={false}
                      />
                      <Box>
                        <Typography
                          variant="h3"
                          fontWeight={700}
                          color={category.color}
                        >
                          {categoryScore.composite}
                        </Typography>
                        <Typography variant="subtitle1" color="text.secondary">
                          {
                            getScoreInterpretation(categoryScore.composite)
                              .label
                          }
                        </Typography>
                      </Box>
                    </Box>

                    <Collapse in={isExpanded}>
                      <Divider sx={{ my: 2 }} />
                      <Box sx={{ mt: 2 }}>
                        <Typography
                          variant="subtitle2"
                          color="text.secondary"
                          gutterBottom
                        >
                          Component Analysis
                        </Typography>
                        {category.subScores.map((subScore) => {
                          const value = categoryScore[subScore.key] || 0;
                          return (
                            <Box key={subScore.key} sx={{ mb: 2 }}>
                              <Box
                                sx={{
                                  display: "flex",
                                  justifyContent: "space-between",
                                  mb: 0.5,
                                }}
                              >
                                <Tooltip title={subScore.description}>
                                  <Typography
                                    variant="body2"
                                    sx={{ cursor: "help" }}
                                  >
                                    {subScore.name}
                                  </Typography>
                                </Tooltip>
                                <Typography variant="body2" fontWeight={600}>
                                  {value} ({subScore.weight})
                                </Typography>
                              </Box>
                              <LinearProgress
                                variant="determinate"
                                value={value}
                                sx={{
                                  height: 8,
                                  borderRadius: 4,
                                  backgroundColor: alpha(category.color, 0.1),
                                  "& .MuiLinearProgress-bar": {
                                    backgroundColor: category.color,
                                    borderRadius: 4,
                                  },
                                }}
                              />
                            </Box>
                          );
                        })}
                      </Box>
                    </Collapse>
                  </CardContent>
                </Card>
              </Grid>
            );
          })}

          {/* Historical Trends Chart */}
          <Grid item xs={12} lg={8}>
            <Card>
              <CardHeader
                title="Score Trends"
                subheader="Historical performance across all factors"
                action={
                  <IconButton>
                    <Download />
                  </IconButton>
                }
              />
              <CardContent>
                <Box sx={{ height: 400 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={historicalScores}>
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke={alpha(theme.palette.divider, 0.5)}
                      />
                      <XAxis dataKey="date" />
                      <YAxis domain={[0, 100]} />
                      <RechartsTooltip />
                      <Legend />
                      <Line
                        type="monotone"
                        dataKey="composite"
                        stroke={theme.palette.primary.main}
                        strokeWidth={3}
                        name="Composite"
                      />
                      <Line
                        type="monotone"
                        dataKey="quality"
                        stroke={scoreCategories[0].color}
                        strokeWidth={2}
                        name="Quality"
                      />
                      <Line
                        type="monotone"
                        dataKey="growth"
                        stroke={scoreCategories[1].color}
                        strokeWidth={2}
                        name="Growth"
                      />
                      <Line
                        type="monotone"
                        dataKey="value"
                        stroke={scoreCategories[2].color}
                        strokeWidth={2}
                        name="Value"
                      />
                      <Line
                        type="monotone"
                        dataKey="momentum"
                        stroke={scoreCategories[3].color}
                        strokeWidth={2}
                        name="Momentum"
                      />
                      <Line
                        type="monotone"
                        dataKey="sentiment"
                        stroke={scoreCategories[4].color}
                        strokeWidth={2}
                        name="Sentiment"
                      />
                      <Line
                        type="monotone"
                        dataKey="positioning"
                        stroke={scoreCategories[5].color}
                        strokeWidth={2}
                        name="Positioning"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </Box>
              </CardContent>
            </Card>
          </Grid>

          {/* Radar Chart */}
          <Grid item xs={12} lg={4}>
            <Card>
              <CardHeader
                title="Factor Profile"
                subheader="Multi-dimensional analysis"
              />
              <CardContent>
                <Box sx={{ height: 400 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart
                      data={scoreCategories.map((cat) => ({
                        category: cat.title.replace(" Score", ""),
                        score: scores[cat.id].composite,
                        fullMark: 100,
                      }))}
                    >
                      <PolarGrid gridType="polygon" />
                      <PolarAngleAxis dataKey="category" />
                      <PolarRadiusAxis angle={90} domain={[0, 100]} />
                      <Radar
                        name="Current"
                        dataKey="score"
                        stroke={theme.palette.primary.main}
                        fill={theme.palette.primary.main}
                        fillOpacity={0.6}
                      />
                    </RadarChart>
                  </ResponsiveContainer>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </>
      )}
    </Grid>
  );

  const renderPeerComparison = () => (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Card>
          <CardHeader
            title="Peer Comparison"
            subheader="Compare scores across similar companies"
          />
          <CardContent>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Company</TableCell>
                    <TableCell align="center">Composite</TableCell>
                    <TableCell align="center">Quality</TableCell>
                    <TableCell align="center">Growth</TableCell>
                    <TableCell align="center">Value</TableCell>
                    <TableCell align="center">Momentum</TableCell>
                    <TableCell align="center">Sentiment</TableCell>
                    <TableCell align="center">Positioning</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {peerComparison.map((peer) => (
                    <TableRow
                      key={peer.symbol}
                      selected={peer.symbol === selectedStock?.symbol}
                    >
                      <TableCell>
                        <Box
                          sx={{ display: "flex", alignItems: "center", gap: 1 }}
                        >
                          <Typography fontWeight={600}>
                            {peer.symbol}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            {peer.name}
                          </Typography>
                        </Box>
                      </TableCell>
                      <TableCell align="center">
                        <Chip
                          label={peer.composite}
                          color={
                            peer.composite >= 80
                              ? "success"
                              : peer.composite >= 60
                                ? "warning"
                                : "error"
                          }
                          size="small"
                        />
                      </TableCell>
                      <TableCell align="center">{peer.quality}</TableCell>
                      <TableCell align="center">{peer.growth}</TableCell>
                      <TableCell align="center">{peer.value}</TableCell>
                      <TableCell align="center">{peer.momentum}</TableCell>
                      <TableCell align="center">{peer.sentiment}</TableCell>
                      <TableCell align="center">{peer.positioning}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      </Grid>

      {/* Peer Comparison Bar Chart */}
      <Grid item xs={12}>
        <Card>
          <CardHeader title="Visual Comparison" />
          <CardContent>
            <Box sx={{ height: 400 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={peerComparison}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="symbol" />
                  <YAxis domain={[0, 100]} />
                  <RechartsTooltip />
                  <Legend />
                  <Bar dataKey="quality" fill={scoreCategories[0].color} />
                  <Bar dataKey="growth" fill={scoreCategories[1].color} />
                  <Bar dataKey="value" fill={scoreCategories[2].color} />
                  <Bar dataKey="momentum" fill={scoreCategories[3].color} />
                  <Bar dataKey="sentiment" fill={scoreCategories[4].color} />
                  <Bar dataKey="positioning" fill={scoreCategories[5].color} />
                </BarChart>
              </ResponsiveContainer>
            </Box>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const _renderMethodology = () => (
    <Grid container spacing={3}>
      {scoreCategories.map((category) => (
        <Grid item xs={12} key={category.id}>
          <Accordion defaultExpanded={false}>
            <AccordionSummary expandIcon={<ExpandMore />}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
                <Avatar
                  sx={{
                    bgcolor: alpha(category.color, 0.1),
                    color: category.color,
                  }}
                >
                  {category.icon}
                </Avatar>
                <Box>
                  <Typography variant="h6">{category.title}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {category.academicBasis}
                  </Typography>
                </Box>
              </Box>
            </AccordionSummary>
            <AccordionDetails>
              <Typography paragraph>{category.description}</Typography>
              <Divider sx={{ my: 2 }} />
              <Grid container spacing={2}>
                {category.subScores.map((subScore) => (
                  <Grid item xs={12} md={6} key={subScore.key}>
                    <Paper
                      sx={{
                        p: 2,
                        backgroundColor: alpha(category.color, 0.05),
                      }}
                    >
                      <Typography
                        variant="subtitle1"
                        fontWeight={600}
                        gutterBottom
                      >
                        {subScore.name} ({subScore.weight})
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {subScore.description}
                      </Typography>
                    </Paper>
                  </Grid>
                ))}
              </Grid>
            </AccordionDetails>
          </Accordion>
        </Grid>
      ))}

      {/* Academic References */}
      <Grid item xs={12}>
        <Card>
          <CardHeader
            avatar={<School />}
            title="Academic Foundation"
            subheader="Research-based methodology"
          />
          <CardContent>
            <List>
              <ListItem>
                <ListItemAvatar>
                  <Avatar sx={{ bgcolor: "primary.main" }}>
                    <Lightbulb />
                  </Avatar>
                </ListItemAvatar>
                <ListItemText
                  primary="Fama-French Five-Factor Model (2015)"
                  secondary="Foundation for quality, value, and size factors in asset pricing"
                />
              </ListItem>
              <ListItem>
                <ListItemAvatar>
                  <Avatar sx={{ bgcolor: "secondary.main" }}>
                    <Lightbulb />
                  </Avatar>
                </ListItemAvatar>
                <ListItemText
                  primary="Jegadeesh & Titman Momentum Strategy (1993)"
                  secondary="12-1 month momentum strategy with risk-adjusted returns"
                />
              </ListItem>
              <ListItem>
                <ListItemAvatar>
                  <Avatar sx={{ bgcolor: "success.main" }}>
                    <Lightbulb />
                  </Avatar>
                </ListItemAvatar>
                <ListItemText
                  primary="Baker & Wurgler Sentiment Index (2006)"
                  secondary="Behavioral finance approach to sentiment impact on returns"
                />
              </ListItem>
              <ListItem>
                <ListItemAvatar>
                  <Avatar sx={{ bgcolor: "warning.main" }}>
                    <Lightbulb />
                  </Avatar>
                </ListItemAvatar>
                <ListItemText
                  primary="Piotroski F-Score (2000)"
                  secondary="Nine-point fundamental strength scoring system"
                />
              </ListItem>
            </List>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Box sx={{ textAlign: "center", mb: 4 }}>
        <Box
          sx={{
            background: `linear-gradient(135deg, ${theme.palette.primary.main}20, ${theme.palette.secondary.main}20)`,
            borderRadius: 2,
            p: 3,
            mb: 3,
          }}
        >
          <Typography variant="h3" component="h1" gutterBottom>
            Advanced Scoring Dashboard
          </Typography>
          <Typography variant="subtitle1" color="text.secondary">
            Comprehensive multi-factor analysis and scoring framework
          </Typography>
        </Box>
      </Box>

      <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 3 }}>
        <Tabs value={activeTab} onChange={(e, v) => setActiveTab(v)}>
          <Tab label="Dashboard" icon={<Assessment />} iconPosition="start" />
          <Tab
            label="Peer Comparison"
            icon={<CompareArrows />}
            iconPosition="start"
          />
          <Tab label="Methodology" icon={<School />} iconPosition="start" />
        </Tabs>
      </Box>

      <TabPanel value={activeTab} index={0}>
        {renderMainDashboard()}
      </TabPanel>

      <TabPanel value={activeTab} index={1}>
        {renderPeerComparison()}
      </TabPanel>

      <TabPanel value={activeTab} index={2}>
        {/* {renderMethodology()} */}
        <div>Methodology content temporarily disabled</div>
      </TabPanel>
    </Container>
  );
};

export default ScoresDashboard;
