import React, { useState, useEffect } from "react";
import {
  Box,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  MenuItem,
  Button,
  Grid,
  Card,
  CardContent,
  Typography,
  CircularProgress,
  Alert,
  Chip,
  LinearProgress,
  Dialog,
  DialogTitle,
  DialogContent,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  Download as DownloadIcon,
  Info as InfoIcon,
} from "@mui/icons-material";

const DeepValueStocks = () => {
  const [stocks, setStocks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [qualityThreshold, setQualityThreshold] = useState(51);
  const [selectedStock, setSelectedStock] = useState(null);
  const [infoOpen, setInfoOpen] = useState(false);

  useEffect(() => {
    fetchDeepValueStocks();
  }, []);

  const fetchDeepValueStocks = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await fetch("/api/stocks/deep-value?limit=5000");

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const result = await response.json();
      const stocksData = result.data || result;

      if (Array.isArray(stocksData)) {
        setStocks(stocksData);
      } else {
        throw new Error("Invalid response format");
      }
    } catch (err) {
      console.error("Error fetching deep value stocks:", err);
      setError(err.message || "Failed to load deep value stocks");
      setStocks([]);
    } finally {
      setLoading(false);
    }
  };

  // Deep Value Criteria: HIGH quality + HIGH growth + REASONABLE price = BEST PICKS
  const getBestPicks = () => {
    return stocks
      .filter((stock) => {
        const quality = stock.quality_score || 0;
        const growth = stock.growth_score || 0;
        const composite = stock.composite_score || 50;

        // SELECTIVE: Only stocks with BOTH strong quality AND growth
        // Thresholds: quality >= threshold (default 51 for top quartile), growth >= 50 (top half), composite <= 52 (fair value)
        return quality >= qualityThreshold && growth >= 50 && composite <= 52;
      })
      .sort((a, b) => {
        // Sort by best quality-to-composite ratio (highest fundamentals relative to price)
        const ratioA = ((a.quality_score || 0) + (a.growth_score || 0)) / Math.max(a.composite_score || 50, 1);
        const ratioB = ((b.quality_score || 0) + (b.growth_score || 0)) / Math.max(b.composite_score || 50, 1);
        return ratioB - ratioA;
      });
  };

  const bestPicks = getBestPicks();

  const ScoreBar = ({ score, label }) => {
    const getColor = (value) => {
      if (value >= 80) return "#4caf50"; // Green
      if (value >= 60) return "#2196f3"; // Blue
      if (value >= 50) return "#ff9800"; // Orange
      return "#f44336"; // Red
    };

    return (
      <Box sx={{ mb: 1 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
          <Typography variant="caption" sx={{ fontWeight: 500 }}>
            {label}
          </Typography>
          <Typography variant="caption" sx={{ fontWeight: 600, color: getColor(score || 0) }}>
            {score ? score.toFixed(1) : "N/A"}
          </Typography>
        </Box>
        <LinearProgress
          variant="determinate"
          value={Math.min(score || 0, 100)}
          sx={{
            height: 6,
            borderRadius: 3,
            backgroundColor: "#e0e0e0",
            "& .MuiLinearProgress-bar": {
              backgroundColor: getColor(score || 0),
              borderRadius: 3,
            },
          }}
        />
      </Box>
    );
  };

  const StockDetailDialog = ({ stock, open, onClose }) => {
    if (!stock) return null;

    return (
      <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
        <DialogTitle>{stock.symbol}</DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 2 }}>
            <ScoreBar score={stock.composite_score} label="Composite Score" />
            <ScoreBar score={stock.quality_score} label="Quality (Fundamentals)" />
            <ScoreBar score={stock.growth_score} label="Growth Potential" />
            <ScoreBar score={stock.momentum_score} label="Momentum" />
            <ScoreBar score={stock.value_score} label="Value (Price to Metrics)" />
            <ScoreBar score={stock.stability_score} label="Stability (Risk)" />
            <ScoreBar score={stock.positioning_score} label="Positioning (Ownership)" />

            <Box sx={{ mt: 3, p: 2, backgroundColor: "#f5f5f5", borderRadius: 1 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                Why This Stock?
              </Typography>
              <Typography variant="body2" color="textSecondary">
                Excellent fundamentals with quality score of {stock.quality_score?.toFixed(1)} and growth of{" "}
                {stock.growth_score?.toFixed(1)}, trading at fair value ({stock.composite_score?.toFixed(1)}).
                This combination of quality + growth at reasonable valuations is rare and attractive for long-term investors.
              </Typography>
            </Box>
          </Box>
        </DialogContent>
      </Dialog>
    );
  };

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", height: 400 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  return (
    <Box sx={{ padding: 3 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h3" sx={{ fontWeight: 700, mb: 1 }}>
          💎 Best Stocks On Sale
        </Typography>
        <Typography variant="body1" color="textSecondary" sx={{ maxWidth: 600 }}>
          Highly selective list of quality companies trading below their fundamental value.
          We only show stocks with excellent fundamentals AND growth at reasonable prices.
        </Typography>
      </Box>

      {/* Stats Cards */}
      <Grid container spacing={2} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Best Picks Found
              </Typography>
              <Typography variant="h4" sx={{ fontWeight: 700, color: "#4caf50" }}>
                {bestPicks.length}
              </Typography>
              <Typography variant="caption" color="textSecondary">
                Out of {stocks.length} total stocks
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Quality Filter
              </Typography>
              <Typography variant="h6">{qualityThreshold}+</Typography>
              <Typography variant="caption" color="textSecondary">
                {qualityThreshold === 51 ? "Top quartile" : qualityThreshold === 52 ? "Top 10%" : "All stocks"}
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Average Quality
              </Typography>
              <Typography variant="h6">
                {(
                  bestPicks.reduce((sum, s) => sum + (s.quality_score || 0), 0) /
                    bestPicks.length || 0
                ).toFixed(1)}
              </Typography>
              <Typography variant="caption" color="textSecondary">
                Among selected stocks
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Avg Discount
              </Typography>
              <Typography variant="h6">
                {(
                  (bestPicks.reduce((sum, s) => sum + Math.max(0, 70 - (s.composite_score || 0)), 0) /
                    bestPicks.length) || 0
                ).toFixed(0)}
                %
              </Typography>
              <Typography variant="caption" color="textSecondary">
                Below intrinsic value
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Filters */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={6} md={4}>
            <TextField
              select
              fullWidth
              label="Minimum Quality Score"
              value={qualityThreshold}
              onChange={(e) => setQualityThreshold(Number(e.target.value))}
              size="small"
            >
              <MenuItem value={50}>All Stocks (50+)</MenuItem>
              <MenuItem value={51}>Excellent (51+) - Top Quartile</MenuItem>
              <MenuItem value={52}>Outstanding (52+) - Top 10%</MenuItem>
            </TextField>
          </Grid>
          <Grid item xs={12} sm={6} md={4}>
            <Button
              variant="outlined"
              fullWidth
              startIcon={<DownloadIcon />}
              onClick={() => {
                const csv = [
                  ["Symbol", "Composite", "Quality", "Growth", "Value", "Discount %"],
                  ...bestPicks.map((s) => [
                    s.symbol,
                    s.composite_score?.toFixed(2),
                    s.quality_score?.toFixed(2),
                    s.growth_score?.toFixed(2),
                    s.value_score?.toFixed(2),
                    Math.max(0, 70 - (s.composite_score || 0)).toFixed(0),
                  ]),
                ]
                  .map((r) => r.join(","))
                  .join("\n");
                const blob = new Blob([csv], { type: "text/csv" });
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = "best_stocks_on_sale.csv";
                a.click();
              }}
            >
              Export CSV
            </Button>
          </Grid>
          <Grid item xs={12} sm={6} md={4}>
            <Button
              variant="outlined"
              fullWidth
              startIcon={<InfoIcon />}
              onClick={() => setInfoOpen(true)}
            >
              How It Works
            </Button>
          </Grid>
        </Grid>
      </Paper>

      {/* Results */}
      {bestPicks.length === 0 ? (
        <Alert severity="info">
          No stocks match your criteria. Try lowering the quality threshold to find more opportunities.
        </Alert>
      ) : (
        <TableContainer component={Paper}>
          <Table>
            <TableHead sx={{ backgroundColor: "#f5f5f5" }}>
              <TableRow>
                <TableCell sx={{ fontWeight: 700 }}>Symbol</TableCell>
                <TableCell align="center" sx={{ fontWeight: 700 }}>
                  Quality
                </TableCell>
                <TableCell align="center" sx={{ fontWeight: 700 }}>
                  Growth
                </TableCell>
                <TableCell align="center" sx={{ fontWeight: 700 }}>
                  Value
                </TableCell>
                <TableCell align="center" sx={{ fontWeight: 700 }}>
                  Price
                </TableCell>
                <TableCell align="center" sx={{ fontWeight: 700 }}>
                  Discount
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {bestPicks.slice(0, 100).map((stock, idx) => {
                const discount = Math.max(0, 70 - (stock.composite_score || 0));
                return (
                  <TableRow
                    key={stock.symbol}
                    hover
                    sx={{
                      cursor: "pointer",
                      backgroundColor: idx === 0 ? "#f0f4ff" : undefined,
                    }}
                    onClick={() => {
                      setSelectedStock(stock);
                      setInfoOpen(true);
                    }}
                  >
                    <TableCell
                      sx={{
                        fontWeight: 700,
                        fontSize: "1.1em",
                        color: idx === 0 ? "#1976d2" : "inherit",
                      }}
                    >
                      {idx === 0 && "🏆 "}
                      {stock.symbol}
                    </TableCell>
                    <TableCell align="center">
                      <Chip
                        label={stock.quality_score?.toFixed(1)}
                        size="small"
                        color={stock.quality_score >= 80 ? "success" : "primary"}
                        variant={stock.quality_score >= 80 ? "filled" : "outlined"}
                      />
                    </TableCell>
                    <TableCell align="center">
                      <Chip
                        label={stock.growth_score?.toFixed(1)}
                        size="small"
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell align="center">
                      <Chip
                        label={stock.value_score?.toFixed(1)}
                        size="small"
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell align="center">
                      <Chip
                        label={stock.composite_score?.toFixed(1)}
                        size="small"
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell align="center">
                      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 0.5 }}>
                        <TrendingDown sx={{ color: "#4caf50", fontSize: 18 }} />
                        <Typography sx={{ fontWeight: 600, color: "#4caf50" }}>
                          {discount.toFixed(0)}%
                        </Typography>
                      </Box>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <Dialog open={infoOpen} onClose={() => setInfoOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>How We Find Quality Stocks At Fair Value</DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 2, space: 2 }}>
            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                ✅ Excellent Fundamentals (Quality 51+)
              </Typography>
              <Typography variant="body2" color="textSecondary">
                Top quartile quality scores: strong earnings, solid cash flow, healthy balance sheet, good margins
              </Typography>
            </Box>

            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                📈 Growth Momentum (Growth 50+)
              </Typography>
              <Typography variant="body2" color="textSecondary">
                Top half growth potential: expanding revenues, earnings momentum, improving margins
              </Typography>
            </Box>

            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                💰 Fair Valuation (Composite 52 or less)
              </Typography>
              <Typography variant="body2" color="textSecondary">
                Trading at reasonable prices relative to fundamentals - not overvalued
              </Typography>
            </Box>

            <Box sx={{ p: 2, backgroundColor: "#e8f5e9", borderRadius: 1 }}>
              <Typography variant="body2" sx={{ fontWeight: 600, color: "#2e7d32" }}>
                💡 This combination of quality + growth + fair valuation is selective and attractive for long-term
                investors seeking established companies with good prospects at reasonable prices.
              </Typography>
            </Box>
          </Box>
        </DialogContent>
      </Dialog>

      <StockDetailDialog stock={selectedStock} open={infoOpen && selectedStock} onClose={() => setInfoOpen(false)} />
    </Box>
  );
};

export default DeepValueStocks;
