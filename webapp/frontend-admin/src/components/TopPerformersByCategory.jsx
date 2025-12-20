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
import { EmojiEvents } from "@mui/icons-material";

/**
 * TopPerformersByCategory Component
 * Displays top stocks grouped by performance category/metric
 * Shows Quality Leaders, Momentum Leaders, Value Leaders, Growth Leaders,
 * Positioning Leaders, Sentiment Leaders, and Stability Leaders
 */
function TopPerformersByCategory({ signals = [], isLoading = false }) {
  // Group stocks by performance category (Quality, Momentum, Value, etc.)
  const categorizedData = useMemo(() => {
    if (!signals || signals.length === 0) {
      return {};
    }

    // Define performance categories with their scoring attributes
    const categories = {
      "Quality Leaders": "quality_score",
      "Momentum Leaders": "momentum_score",
      "Positioning Leaders": "positioning_score",
      "Stability Leaders": "stability_score",
    };

    // Initialize grouped data structure
    const grouped = {};
    Object.keys(categories).forEach((cat) => {
      grouped[cat] = [];
    });

    // Populate each category with stocks sorted by their respective scores - ONLY real data
    Object.entries(categories).forEach(([categoryName, scoreField]) => {
      // Filter signals that have the score field and sort by it - no fake defaults
      const rankedSignals = signals
        .filter((signal) => signal[scoreField] != null && signal[scoreField] !== undefined)
        .sort((a, b) => b[scoreField] - a[scoreField])
        .slice(0, 5); // Keep top 5 per category

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

  // Color map for performance categories
  const categoryColors = {
    "Quality Leaders": "#3B82F6",
    "Momentum Leaders": "#10B981",
    "Positioning Leaders": "#F59E0B",
    "Stability Leaders": "#6366F1",
  };

  return (
    <Grid container spacing={3} sx={{ mb: 4 }}>
      <Grid item xs={12}>
        <Typography variant="h5" sx={{ fontWeight: 700, mb: 3 }}>
          <EmojiEvents sx={{ mr: 1, verticalAlign: "middle" }} />
          Top Performers by Category
        </Typography>
      </Grid>

      {categories.map((categoryName, idx) => {
        const stocksInCategory = categorizedData[categoryName];
        const categoryColor =
          categoryColors[categoryName] || categoryColors["Quality Leaders"];

        return (
          <Grid item xs={12} md={6} key={idx}>
            <Card sx={{ height: "100%" }}>
              <CardContent>
                {/* Category Header */}
                <Box
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    gap: 1.5,
                    mb: 2,
                    pb: 2,
                    borderBottom: `2px solid ${categoryColor}20`,
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
                      <TableRow sx={{ backgroundColor: "rgba(0,0,0,0.02)" }}>
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
                        if (categoryName === "Quality Leaders") {
                          scoreValue = stock.quality_score;
                        } else if (categoryName === "Momentum Leaders") {
                          scoreValue = stock.momentum_score;
                        } else if (categoryName === "Positioning Leaders") {
                          scoreValue = stock.positioning_score;
                        } else if (categoryName === "Stability Leaders") {
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
                                    scoreValue >= 80
                                      ? "#059669"
                                      : scoreValue >= 60
                                        ? "#3B82F6"
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
                            if (categoryName === "Quality Leaders") {
                              scores = stocksInCategory
                                .map((s) => s.quality_score)
                                .filter((s) => s);
                            } else if (categoryName === "Momentum Leaders") {
                              scores = stocksInCategory
                                .map((s) => s.momentum_score)
                                .filter((s) => s);
                            } else if (categoryName === "Positioning Leaders") {
                              scores = stocksInCategory
                                .map((s) => s.positioning_score)
                                .filter((s) => s);
                            } else if (categoryName === "Stability Leaders") {
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

export default TopPerformersByCategory;
