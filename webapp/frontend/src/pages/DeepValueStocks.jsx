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
  TablePagination,
} from "@mui/material";
import {
  TrendingDown as TrendingDownIcon,
  TrendingUp as TrendingUpIcon,
  Download as DownloadIcon,
} from "@mui/icons-material";

const DeepValueStocks = () => {
  const [stocks, setStocks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [sortBy, setSortBy] = useState("value_desc");
  const [filterQuality, setFilterQuality] = useState("all");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);

  useEffect(() => {
    fetchDeepValueStocks();
  }, []);

  const fetchDeepValueStocks = async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch from API - deep value = high value score + low composite score
      const response = await fetch("/api/stocks/deep-value?limit=5000");

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const result = await response.json();

      // Check if response has data property (success response) or is array directly
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

  const getScoreColor = (score) => {
    if (!score) return "#999";
    if (score > 70) return "#2ecc71"; // Green - Excellent
    if (score > 60) return "#27ae60"; // Dark Green - Good
    if (score > 50) return "#3498db"; // Blue - Fair
    if (score > 40) return "#f39c12"; // Orange - Poor
    return "#e74c3c"; // Red - Very Poor
  };

  const getValueBadge = (valueScore) => {
    if (!valueScore) return null;
    if (valueScore > 80) return "💎 Deep Value";
    if (valueScore > 70) return "✨ Undervalued";
    if (valueScore > 60) return "📊 Value Stock";
    return "💼 Fair Value";
  };

  const sortedAndFilteredStocks = stocks
    .filter((stock) => {
      // Search filter
      if (
        searchTerm &&
        !stock.symbol.toLowerCase().includes(searchTerm.toLowerCase())
      ) {
        return false;
      }

      // Quality filter
      if (filterQuality !== "all") {
        if (filterQuality === "quality_excellent" && stock.quality_score < 80)
          return false;
        if (filterQuality === "quality_good" && stock.quality_score < 60)
          return false;
        if (filterQuality === "quality_any" && !stock.quality_score)
          return false;
      }

      return true;
    })
    .sort((a, b) => {
      switch (sortBy) {
        case "value_desc":
          return (b.value_score || 0) - (a.value_score || 0);
        case "composite_asc":
          return (a.composite_score || 0) - (b.composite_score || 0);
        case "quality_desc":
          return (b.quality_score || 0) - (a.quality_score || 0);
        case "growth_desc":
          return (b.growth_score || 0) - (a.growth_score || 0);
        default:
          return 0;
      }
    });

  const paginatedStocks = sortedAndFilteredStocks.slice(
    page * rowsPerPage,
    page * rowsPerPage + rowsPerPage
  );

  const handleChangePage = (event, newPage) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const downloadCSV = () => {
    const headers = [
      "Symbol",
      "Composite Score",
      "Value Score",
      "Quality Score",
      "Growth Score",
      "Momentum Score",
      "Stability Score",
      "Positioning Score",
    ];

    const rows = sortedAndFilteredStocks.map((stock) => [
      stock.symbol,
      stock.composite_score?.toFixed(2) || "N/A",
      stock.value_score?.toFixed(2) || "N/A",
      stock.quality_score?.toFixed(2) || "N/A",
      stock.growth_score?.toFixed(2) || "N/A",
      stock.momentum_score?.toFixed(2) || "N/A",
      stock.stability_score?.toFixed(2) || "N/A",
      stock.positioning_score?.toFixed(2) || "N/A",
    ]);

    const csv = [headers, ...rows].map((row) => row.join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "deep_value_stocks.csv";
    a.click();
  };

  return (
    <Box sx={{ padding: 3 }}>
      <Typography variant="h4" gutterBottom sx={{ marginBottom: 3 }}>
        💎 Deep Value Stock Picks
      </Typography>

      <Typography variant="body1" paragraph sx={{ marginBottom: 2 }}>
        Discover undervalued stocks with strong fundamental value but lower
        composite scores - perfect for value investors seeking hidden gems.
      </Typography>

      {error && (
        <Alert severity="error" sx={{ marginBottom: 2 }}>
          {error}
        </Alert>
      )}

      <Grid container spacing={2} sx={{ marginBottom: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <TextField
            fullWidth
            label="Search Symbol"
            value={searchTerm}
            onChange={(e) => {
              setSearchTerm(e.target.value);
              setPage(0);
            }}
            placeholder="e.g., AAPL"
          />
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <TextField
            select
            fullWidth
            label="Sort By"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
          >
            <MenuItem value="value_desc">Value Score (High→Low)</MenuItem>
            <MenuItem value="composite_asc">Composite Score (Low→High)</MenuItem>
            <MenuItem value="quality_desc">Quality Score (High→Low)</MenuItem>
            <MenuItem value="growth_desc">Growth Score (High→Low)</MenuItem>
          </TextField>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <TextField
            select
            fullWidth
            label="Quality Filter"
            value={filterQuality}
            onChange={(e) => {
              setFilterQuality(e.target.value);
              setPage(0);
            }}
          >
            <MenuItem value="all">All Stocks</MenuItem>
            <MenuItem value="quality_excellent">Quality > 80</MenuItem>
            <MenuItem value="quality_good">Quality > 60</MenuItem>
            <MenuItem value="quality_any">Has Quality Score</MenuItem>
          </TextField>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Button
            variant="outlined"
            fullWidth
            startIcon={<DownloadIcon />}
            onClick={downloadCSV}
          >
            Export CSV
          </Button>
        </Grid>
      </Grid>

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", padding: 4 }}>
          <CircularProgress />
        </Box>
      ) : paginatedStocks.length === 0 ? (
        <Alert severity="info">
          No stocks match your filters. Try adjusting the search criteria.
        </Alert>
      ) : (
        <>
          <TableContainer component={Paper}>
            <Table>
              <TableHead sx={{ backgroundColor: "#f5f5f5" }}>
                <TableRow>
                  <TableCell sx={{ fontWeight: "bold" }}>Symbol</TableCell>
                  <TableCell align="right" sx={{ fontWeight: "bold" }}>
                    Composite
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: "bold" }}>
                    Value
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: "bold" }}>
                    Quality
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: "bold" }}>
                    Growth
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: "bold" }}>
                    Momentum
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: "bold" }}>
                    Stability
                  </TableCell>
                  <TableCell sx={{ fontWeight: "bold" }}>Rating</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {paginatedStocks.map((stock) => (
                  <TableRow key={stock.symbol} hover>
                    <TableCell sx={{ fontWeight: "bold" }}>
                      {stock.symbol}
                    </TableCell>
                    <TableCell
                      align="right"
                      sx={{
                        color: getScoreColor(stock.composite_score),
                        fontWeight: "bold",
                      }}
                    >
                      {stock.composite_score?.toFixed(2) || "N/A"}
                    </TableCell>
                    <TableCell
                      align="right"
                      sx={{
                        color: getScoreColor(stock.value_score),
                        fontWeight: "bold",
                      }}
                    >
                      {stock.value_score?.toFixed(2) || "N/A"}
                    </TableCell>
                    <TableCell
                      align="right"
                      sx={{
                        color: getScoreColor(stock.quality_score),
                      }}
                    >
                      {stock.quality_score?.toFixed(2) || "N/A"}
                    </TableCell>
                    <TableCell
                      align="right"
                      sx={{
                        color: getScoreColor(stock.growth_score),
                      }}
                    >
                      {stock.growth_score?.toFixed(2) || "N/A"}
                    </TableCell>
                    <TableCell
                      align="right"
                      sx={{
                        color: getScoreColor(stock.momentum_score),
                      }}
                    >
                      {stock.momentum_score?.toFixed(2) || "N/A"}
                    </TableCell>
                    <TableCell
                      align="right"
                      sx={{
                        color: getScoreColor(stock.stability_score),
                      }}
                    >
                      {stock.stability_score?.toFixed(2) || "N/A"}
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={getValueBadge(stock.value_score)}
                        size="small"
                        variant="outlined"
                        color={
                          (stock.value_score || 0) > 80
                            ? "success"
                            : (stock.value_score || 0) > 60
                            ? "primary"
                            : "default"
                        }
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          <TablePagination
            rowsPerPageOptions={[10, 25, 50, 100]}
            component="div"
            count={sortedAndFilteredStocks.length}
            rowsPerPage={rowsPerPage}
            page={page}
            onPageChange={handleChangePage}
            onRowsPerPageChange={handleChangeRowsPerPage}
          />

          <Box sx={{ marginTop: 2 }}>
            <Typography variant="caption" color="textSecondary">
              Showing {paginatedStocks.length} of{" "}
              {sortedAndFilteredStocks.length} stocks
            </Typography>
          </Box>
        </>
      )}
    </Box>
  );
};

export default DeepValueStocks;
