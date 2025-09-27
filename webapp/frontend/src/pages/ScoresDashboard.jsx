import { useState, useEffect } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Container,
  Divider,
  Grid,
  LinearProgress,
  Paper,
  TextField,
  Typography,
  alpha,
  useTheme,
} from "@mui/material";
import {
  ExpandMore,
  TrendingUp,
  TrendingDown,
  Assessment,
  Speed,
  Psychology,
  Groups,
  Stars,
  AccountBalance,
  Security,
} from "@mui/icons-material";

// Custom styled components
const ScoreGauge = ({ score, size = 80, showGrade = false }) => {
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

  return (
    <Box
      sx={{
        position: "relative",
        width: size,
        height: size,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Box
        sx={{
          width: size,
          height: size,
          borderRadius: "50%",
          background: `conic-gradient(${getColor(score)} ${score * 3.6}deg, ${alpha(theme.palette.action.disabled, 0.1)} 0deg)`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Box
          sx={{
            width: size - 10,
            height: size - 10,
            borderRadius: "50%",
            backgroundColor: theme.palette.background.paper,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Typography variant="h6" fontWeight={700}>
            {score}
          </Typography>
          {showGrade && (
            <Typography variant="caption" color={getColor(score)} fontWeight={600}>
              {getGrade(score)}
            </Typography>
          )}
        </Box>
      </Box>
    </Box>
  );
};

const ScoresDashboard = () => {
  const theme = useTheme();
  const [loading, setLoading] = useState(true);
  const [scores, setScores] = useState([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedStock, setExpandedStock] = useState(null);

  // Load all scores on component mount
  useEffect(() => {
    loadAllScores();
  }, []);

  const loadAllScores = async () => {
    setLoading(true);
    try {
      // Import the API function
      const { default: api } = await import("../services/api");

      // Fetch scores data from our backend
      const response = await api.get("/scores");

      if (response?.data?.success && response.data.data?.stocks) {
        setScores(response.data.data.stocks);
      } else {
        console.error("Invalid API response format:", response);
        setScores([]);
      }
    } catch (error) {
      console.error("Error loading scores:", error);
      setScores([]);
    } finally {
      setLoading(false);
    }
  };

  // Filter scores based on search term
  const filteredScores = scores.filter((stock) =>
    stock.symbol.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleAccordionChange = (symbol) => (event, isExpanded) => {
    setExpandedStock(isExpanded ? symbol : null);
  };

  const getScoreColor = (score) => {
    if (score >= 80) return theme.palette.success.main;
    if (score >= 60) return theme.palette.warning.main;
    if (score >= 40) return theme.palette.info.main;
    return theme.palette.error.main;
  };

  const formatNumber = (num) => {
    if (num >= 1e12) return `$${(num / 1e12).toFixed(1)}T`;
    if (num >= 1e9) return `$${(num / 1e9).toFixed(1)}B`;
    if (num >= 1e6) return `$${(num / 1e6).toFixed(1)}M`;
    return `$${num}`;
  };

  const formatChange = (change) => {
    const isPositive = change >= 0;
    return (
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
        {isPositive ? (
          <TrendingUp sx={{ fontSize: 16, color: theme.palette.success.main }} />
        ) : (
          <TrendingDown sx={{ fontSize: 16, color: theme.palette.error.main }} />
        )}
        <Typography
          variant="body2"
          sx={{
            color: isPositive ? theme.palette.success.main : theme.palette.error.main,
            fontWeight: 600,
          }}
        >
          {isPositive ? "+" : ""}
          {change.toFixed(2)}%
        </Typography>
      </Box>
    );
  };

  if (loading) {
    return (
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: 400 }}>
          <CircularProgress size={60} />
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
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
            Stock Scores Dashboard
          </Typography>
          <Typography variant="subtitle1" color="text.secondary">
            Comprehensive six-factor scoring system for all stocks
          </Typography>
        </Box>
      </Box>

      {/* Search */}
      <Box sx={{ mb: 3 }}>
        <TextField
          fullWidth
          variant="outlined"
          placeholder="Search stocks by symbol..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          sx={{ maxWidth: 400 }}
        />
      </Box>

      {/* Summary Stats */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={3}>
          <Paper sx={{ p: 2, textAlign: "center" }}>
            <Typography variant="h4" color="primary" fontWeight={700}>
              {filteredScores.length}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Total Stocks
            </Typography>
          </Paper>
        </Grid>
        <Grid item xs={12} md={3}>
          <Paper sx={{ p: 2, textAlign: "center" }}>
            <Typography variant="h4" color="success.main" fontWeight={700}>
              {filteredScores.length > 0 ? Math.max(...filteredScores.map(s => s.compositeScore)).toFixed(1) : 0}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Top Score
            </Typography>
          </Paper>
        </Grid>
        <Grid item xs={12} md={3}>
          <Paper sx={{ p: 2, textAlign: "center" }}>
            <Typography variant="h4" color="info.main" fontWeight={700}>
              {filteredScores.length > 0 ? (filteredScores.reduce((sum, s) => sum + s.compositeScore, 0) / filteredScores.length).toFixed(1) : 0}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Average Score
            </Typography>
          </Paper>
        </Grid>
        <Grid item xs={12} md={3}>
          <Paper sx={{ p: 2, textAlign: "center" }}>
            <Typography variant="h4" color="warning.main" fontWeight={700}>
              {filteredScores.filter(s => s.compositeScore >= 80).length}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              High Quality (80+)
            </Typography>
          </Paper>
        </Grid>
      </Grid>

      {/* Stocks List */}
      <Typography variant="h5" gutterBottom sx={{ mb: 2 }}>
        All Stocks ({filteredScores.length})
      </Typography>

      {filteredScores.length === 0 ? (
        <Paper sx={{ p: 4, textAlign: "center" }}>
          <Typography variant="h6" color="text.secondary">
            No stocks found
          </Typography>
        </Paper>
      ) : (
        <Box>
          {filteredScores.map((stock) => (
            <Accordion
              key={stock.symbol}
              expanded={expandedStock === stock.symbol}
              onChange={handleAccordionChange(stock.symbol)}
              sx={{ mb: 1 }}
            >
              <AccordionSummary expandIcon={<ExpandMore />}>
                <Grid container alignItems="center" spacing={2} sx={{ width: "100%" }}>
                  <Grid item xs={12} sm={3}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
                      <ScoreGauge score={Math.round(stock.compositeScore)} size={70} />
                      <Box>
                        <Typography variant="h5" fontWeight={700}>
                          {stock.symbol}
                        </Typography>
                        <Typography variant="h6" color="primary" fontWeight={600}>
                          Score: {stock.compositeScore.toFixed(1)}
                        </Typography>
                        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                          <Typography variant="body2" color="text.secondary">
                            ${stock.currentPrice.toFixed(2)}
                          </Typography>
                          {formatChange(stock.priceChange1d)}
                        </Box>
                      </Box>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", justifyContent: "center" }}>
                      <Chip
                        icon={<Stars />}
                        label={`Quality: ${stock.factors.quality.score.toFixed(1)}`}
                        size="medium"
                        color={stock.factors.quality.score >= 80 ? "success" : stock.factors.quality.score >= 60 ? "warning" : "error"}
                        variant="filled"
                      />
                      <Chip
                        icon={<TrendingUp />}
                        label={`Momentum: ${stock.factors.momentum.score.toFixed(1)}`}
                        size="medium"
                        color={stock.factors.momentum.score >= 80 ? "success" : stock.factors.momentum.score >= 60 ? "warning" : "error"}
                        variant="filled"
                      />
                      <Chip
                        icon={<Assessment />}
                        label={`Trend: ${stock.factors.trend.score.toFixed(1)}`}
                        size="medium"
                        color={stock.factors.trend.score >= 80 ? "success" : stock.factors.trend.score >= 60 ? "warning" : "error"}
                        variant="filled"
                      />
                      <Chip
                        icon={<AccountBalance />}
                        label={`Value: ${stock.factors.value.score.toFixed(1)}`}
                        size="medium"
                        color={stock.factors.value.score >= 80 ? "success" : stock.factors.value.score >= 60 ? "warning" : "error"}
                        variant="filled"
                      />
                      <Chip
                        icon={<Psychology />}
                        label={`Technical: ${stock.factors.technical.priceChange30d?.toFixed(1) || 'N/A'}%`}
                        size="medium"
                        variant="outlined"
                      />
                      <Chip
                        icon={<Security />}
                        label={`Risk: ${stock.factors.risk.volatility30d?.toFixed(1) || 'N/A'}%`}
                        size="medium"
                        variant="outlined"
                      />
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={3}>
                    <Box sx={{ textAlign: "right" }}>
                      <Typography variant="body2" color="text.secondary">
                        Market Cap: {formatNumber(stock.marketCap)}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Volume: {(stock.volume / 1e6).toFixed(1)}M
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        Updated: {new Date(stock.lastUpdated).toLocaleDateString()}
                      </Typography>
                    </Box>
                  </Grid>
                </Grid>
              </AccordionSummary>
              <AccordionDetails>
                <Box>
                  <Typography variant="h6" gutterBottom sx={{ mb: 3 }}>
                    Factor Analysis for {stock.symbol}
                  </Typography>

                  <Grid container spacing={3}>
                    {/* Momentum Factor */}
                    <Grid item xs={12} md={6}>
                      <Card>
                        <CardContent>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                            <Speed sx={{ color: theme.palette.warning.main }} />
                            <Typography variant="h6">Momentum</Typography>
                            <Chip
                              label={stock.factors.momentum.score.toFixed(1)}
                              color={stock.factors.momentum.score >= 80 ? "success" : "warning"}
                              size="small"
                            />
                          </Box>
                          <Typography variant="body2" color="text.secondary" paragraph>
                            {stock.factors.momentum.description}
                          </Typography>
                          <Box sx={{ mb: 2 }}>
                            <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                              <Typography variant="body2">RSI</Typography>
                              <Typography variant="body2" fontWeight={600}>
                                {stock.factors.momentum.rsi.toFixed(1)}
                              </Typography>
                            </Box>
                            <LinearProgress
                              variant="determinate"
                              value={stock.factors.momentum.rsi}
                              sx={{
                                height: 8,
                                borderRadius: 4,
                                backgroundColor: alpha(theme.palette.warning.main, 0.1),
                                "& .MuiLinearProgress-bar": {
                                  backgroundColor: theme.palette.warning.main,
                                  borderRadius: 4,
                                },
                              }}
                            />
                          </Box>
                        </CardContent>
                      </Card>
                    </Grid>

                    {/* Trend Factor */}
                    <Grid item xs={12} md={6}>
                      <Card>
                        <CardContent>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                            <TrendingUp sx={{ color: theme.palette.success.main }} />
                            <Typography variant="h6">Trend</Typography>
                            <Chip
                              label={stock.factors.trend.score.toFixed(1)}
                              color={stock.factors.trend.score >= 80 ? "success" : "warning"}
                              size="small"
                            />
                          </Box>
                          <Typography variant="body2" color="text.secondary" paragraph>
                            {stock.factors.trend.description}
                          </Typography>
                          <Grid container spacing={2}>
                            <Grid item xs={6}>
                              <Typography variant="body2" color="text.secondary">SMA 20</Typography>
                              <Typography variant="body2" fontWeight={600}>${stock.factors.trend.sma20.toFixed(2)}</Typography>
                            </Grid>
                            <Grid item xs={6}>
                              <Typography variant="body2" color="text.secondary">SMA 50</Typography>
                              <Typography variant="body2" fontWeight={600}>${stock.factors.trend.sma50.toFixed(2)}</Typography>
                            </Grid>
                          </Grid>
                        </CardContent>
                      </Card>
                    </Grid>

                    {/* Value Factor */}
                    <Grid item xs={12} md={6}>
                      <Card>
                        <CardContent>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                            <AccountBalance sx={{ color: theme.palette.info.main }} />
                            <Typography variant="h6">Value</Typography>
                            <Chip
                              label={stock.factors.value.score.toFixed(1)}
                              color={stock.factors.value.score >= 80 ? "success" : "warning"}
                              size="small"
                            />
                          </Box>
                          <Typography variant="body2" color="text.secondary" paragraph>
                            {stock.factors.value.description}
                          </Typography>
                          {stock.factors.value.peRatio && (
                            <Box>
                              <Typography variant="body2" color="text.secondary">P/E Ratio</Typography>
                              <Typography variant="body2" fontWeight={600}>{stock.factors.value.peRatio.toFixed(1)}</Typography>
                            </Box>
                          )}
                        </CardContent>
                      </Card>
                    </Grid>

                    {/* Quality Factor */}
                    <Grid item xs={12} md={6}>
                      <Card>
                        <CardContent>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                            <Stars sx={{ color: theme.palette.primary.main }} />
                            <Typography variant="h6">Quality</Typography>
                            <Chip
                              label={stock.factors.quality.score.toFixed(1)}
                              color={stock.factors.quality.score >= 80 ? "success" : "warning"}
                              size="small"
                            />
                          </Box>
                          <Typography variant="body2" color="text.secondary" paragraph>
                            {stock.factors.quality.description}
                          </Typography>
                          <Box>
                            <Typography variant="body2" color="text.secondary">30-Day Volatility</Typography>
                            <Typography variant="body2" fontWeight={600}>{stock.factors.quality.volatility.toFixed(2)}%</Typography>
                          </Box>
                        </CardContent>
                      </Card>
                    </Grid>

                    {/* Technical Factor */}
                    <Grid item xs={12} md={6}>
                      <Card>
                        <CardContent>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                            <Assessment sx={{ color: theme.palette.secondary.main }} />
                            <Typography variant="h6">Technical</Typography>
                          </Box>
                          <Typography variant="body2" color="text.secondary" paragraph>
                            {stock.factors.technical.description}
                          </Typography>
                          <Grid container spacing={2}>
                            <Grid item xs={6}>
                              <Typography variant="body2" color="text.secondary">5-Day Change</Typography>
                              <Typography variant="body2" fontWeight={600}>{stock.factors.technical.priceChange5d.toFixed(2)}%</Typography>
                            </Grid>
                            <Grid item xs={6}>
                              <Typography variant="body2" color="text.secondary">30-Day Change</Typography>
                              <Typography variant="body2" fontWeight={600}>{stock.factors.technical.priceChange30d.toFixed(2)}%</Typography>
                            </Grid>
                          </Grid>
                        </CardContent>
                      </Card>
                    </Grid>

                    {/* Risk Factor */}
                    <Grid item xs={12} md={6}>
                      <Card>
                        <CardContent>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                            <Security sx={{ color: theme.palette.error.main }} />
                            <Typography variant="h6">Risk</Typography>
                          </Box>
                          <Typography variant="body2" color="text.secondary" paragraph>
                            {stock.factors.risk.description}
                          </Typography>
                          <Box>
                            <Typography variant="body2" color="text.secondary">30-Day Volatility</Typography>
                            <Typography variant="body2" fontWeight={600}>{stock.factors.risk.volatility30d.toFixed(2)}%</Typography>
                          </Box>
                        </CardContent>
                      </Card>
                    </Grid>
                  </Grid>

                  <Divider sx={{ my: 3 }} />

                  <Typography variant="body2" color="text.secondary">
                    Last Updated: {new Date(stock.lastUpdated).toLocaleDateString()}
                  </Typography>
                </Box>
              </AccordionDetails>
            </Accordion>
          ))}
        </Box>
      )}
    </Container>
  );
};

export default ScoresDashboard;