import React, { useMemo } from "react";
import {
  Box,
  Card,
  CardContent,
  Grid,
  Typography,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  CircularProgress,
} from "@mui/material";
import { TrendingDown } from "@mui/icons-material";

/**
 * BottomPerformersByCategory Component
 * Displays bottom (worst) stocks grouped by performance category/metric
 * Shows Quality Laggards, Momentum Laggards, Value Laggards, Growth Laggards,
 * Positioning Laggards, and Stability Laggards (bottom 5 in each category)
 */
function BottomPerformersByCategory({ signals = [], isLoading = false }) {
  // Group stocks by performance category (Quality, Momentum, Value, etc.)
  const categorizedData = useMemo(() => {
    if (!signals || signals.length === 0) {
      return {};
    }

    // Define performance categories with their scoring attributes
    const categories = {
      "Quality Laggards": "quality_score",
      "Momentum Laggards": "momentum_score",
      "Positioning Laggards": "positioning_score",
      "Stability Laggards": "stability_score",
    };

    // Initialize grouped data structure
    const grouped = {};
    Object.keys(categories).forEach((cat) => {
      grouped[cat] = [];
    });

    // Populate each category with stocks sorted by their respective scores (ascending) - ONLY real data
    Object.entries(categories).forEach(([categoryName, scoreField]) => {
      // Filter signals that have the score field and sort by it ASCENDING (lowest scores first)
      const rankedSignals = signals
        .filter((signal) => signal[scoreField] != null && signal[scoreField] !== undefined)
        .sort((a, b) => a[scoreField] - b[scoreField]) // ASCENDING for bottom performers
        .slice(0, 5); // Keep bottom 5 per category

      grouped[categoryName] = rankedSignals;
    });

    return grouped;
  }, [signals]);

  if (isLoading) {
    return (
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Box display="flex" justifyContent="center" p={4}>
            <CircularProgress />
          </Box>
        </CardContent>
      </Card>
    );
  }

  const categories = Object.keys(categorizedData).sort();

  if (categories.length === 0 || !categorizedData) {
    return (
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Typography color="text.secondary">
            No category data available
          </Typography>
        </CardContent>
      </Card>
    );
  }

  // Color map for laggard categories (red/warning colors)
  const categoryColors = {
    "Quality Laggards": "#EF4444",
    "Momentum Laggards": "#F97316",
    "Positioning Laggards": "#EC4899",
    "Stability Laggards": "#8B5CF6",
  };

  return (
    <Grid container spacing={3} sx={{ mb: 4 }}>
      <Grid item xs={12}>
        <Typography variant="h5" sx={{ fontWeight: 700, mb: 3 }}>
          <TrendingDown sx={{ mr: 1, verticalAlign: "middle" }} />
          Bottom Performers by Category
        </Typography>
      </Grid>

      {categories.map((categoryName, idx) => {
        const stocksInCategory = categorizedData[categoryName];
        const categoryColor =
          categoryColors[categoryName] || categoryColors["Quality Laggards"];

        return (
          <Grid item xs={12} md={6} key={idx}>
            <Card sx={{ height: "100%", backgroundColor: `${categoryColor}05` }}>
              <CardContent>
                {/* Category Header */}
                <Box
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    gap: 1.5,
                    mb: 2,
                    pb: 2,
                    borderBottom: `2px solid ${categoryColor}40`,
                  }}
                >
                  <Box
                    sx={{
                      width: 12,
                      height: 12,
                      borderRadius: "50%",
                      backgroundColor: categoryColor,
                    }}
                  />
                  <Typography
                    variant="h6"
                    sx={{ fontWeight: 700, flex: 1, color: categoryColor }}
                  >
                    {categoryName}
                  </Typography>
                  <Chip
                    label={stocksInCategory.length}
                    size="small"
                    sx={{
                      backgroundColor: `${categoryColor}20`,
                      color: categoryColor,
                      fontWeight: "bold",
                    }}
                  />
                </Box>

                {/* Stocks Table */}
                <TableContainer component={Paper} elevation={0} sx={{ mt: 2 }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow sx={{ backgroundColor: `${categoryColor}10` }}>
                        <TableCell sx={{ fontWeight: 700 }}>Rank</TableCell>
                        <TableCell sx={{ fontWeight: 700 }}>Symbol</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>
                          Score
                        </TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {stocksInCategory.map((stock, stockIdx) => {
                        // Get the score based on category
                        let scoreValue = null;
                        if (categoryName === "Quality Laggards") {
                          scoreValue = stock.quality_score;
                        } else if (categoryName === "Momentum Laggards") {
                          scoreValue = stock.momentum_score;
                        } else if (categoryName === "Positioning Laggards") {
                          scoreValue = stock.positioning_score;
                        } else if (categoryName === "Stability Laggards") {
                          scoreValue = stock.stability_score;
                        }

                        return (
                          <TableRow key={`${categoryName}-${stockIdx}`} hover>
                            <TableCell sx={{ fontWeight: 600 }}>
                              {stockIdx + 1}
                            </TableCell>
                            <TableCell sx={{ fontWeight: 600 }}>
                              {stock.symbol}
                            </TableCell>
                            <TableCell align="right">
                              <Typography
                                variant="body2"
                                sx={{
                                  fontWeight: 600,
                                  color:
                                    scoreValue <= 20
                                      ? "#DC2626"
                                      : scoreValue <= 40
                                        ? "#F97316"
                                        : "#F59E0B",
                                }}
                              >
                                {scoreValue ? scoreValue.toFixed(1) : "—"}
                              </Typography>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </TableContainer>

                {/* Summary Stats */}
                <Box sx={{ mt: 2, display: "flex", gap: 2, flexWrap: "wrap" }}>
                  {stocksInCategory.length > 0 && (
                    <>
                      <Box sx={{ textAlign: "center", flex: "1 1 auto" }}>
                        <Typography variant="caption" color="text.secondary">
                          Count
                        </Typography>
                        <Typography
                          variant="body2"
                          sx={{
                            fontWeight: 700,
                            color: categoryColor,
                            mt: 0.5,
                          }}
                        >
                          {stocksInCategory.length}
                        </Typography>
                      </Box>
                      <Box sx={{ textAlign: "center", flex: "1 1 auto" }}>
                        <Typography variant="caption" color="text.secondary">
                          Avg Score
                        </Typography>
                        <Typography
                          variant="body2"
                          sx={{
                            fontWeight: 700,
                            color: categoryColor,
                            mt: 0.5,
                          }}
                        >
                          {(() => {
                            let scores = [];
                            if (categoryName === "Quality Laggards") {
                              scores = stocksInCategory
                                .map((s) => s.quality_score)
                                .filter((s) => s);
                            } else if (categoryName === "Momentum Laggards") {
                              scores = stocksInCategory
                                .map((s) => s.momentum_score)
                                .filter((s) => s);
                            } else if (categoryName === "Positioning Laggards") {
                              scores = stocksInCategory
                                .map((s) => s.positioning_score)
                                .filter((s) => s);
                            } else if (categoryName === "Stability Laggards") {
                              scores = stocksInCategory
                                .map((s) => s.stability_score)
                                .filter((s) => s);
                            }
                            return scores.length > 0
                              ? (
                                  scores.reduce((a, b) => a + b) / scores.length
                                ).toFixed(1)
                              : "—";
                          })()}
                        </Typography>
                      </Box>
                    </>
                  )}
                </Box>
              </CardContent>
            </Card>
          </Grid>
        );
      })}
    </Grid>
  );
}

export default BottomPerformersByCategory;
