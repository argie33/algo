import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Chip,
  CircularProgress,
  Container,
  Grid,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  TextField,
  MenuItem,
  Alert,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
} from "@mui/icons-material";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from "recharts";
import api from "../services/api";
import { formatCurrency, formatPercentage, getChangeColor } from "../utils/formatters";

function CommoditiesAnalysis() {
  const [selectedCommodity, setSelectedCommodity] = useState("GC=F");
  const [filterCategory, setFilterCategory] = useState("all");

  // Fetch all commodity data
  const pricesQuery = useQuery({
    queryKey: ["commodities-prices"],
    queryFn: async () => {
      const response = await api.get("/api/commodities/prices?limit=100");
      return response.data.data || [];
    },
    staleTime: 2 * 60 * 1000,
  });

  const categoriesQuery = useQuery({
    queryKey: ["commodities-categories"],
    queryFn: async () => {
      const response = await api.get("/api/commodities/categories");
      return response.data.data || [];
    },
    staleTime: 5 * 60 * 1000,
  });

  const correlationsQuery = useQuery({
    queryKey: ["commodities-correlations"],
    queryFn: async () => {
      const response = await api.get("/api/commodities/correlations?minCorrelation=0.3");
      return response.data.data?.correlations || [];
    },
    staleTime: 30 * 60 * 1000,
  });

  const summaryQuery = useQuery({
    queryKey: ["commodities-summary"],
    queryFn: async () => {
      const response = await api.get("/api/commodities/market-summary");
      return response.data.data;
    },
    staleTime: 2 * 60 * 1000,
  });

  const seasonalityQuery = useQuery({
    queryKey: ["commodities-seasonality", selectedCommodity],
    queryFn: async () => {
      try {
        const response = await api.get(`/api/commodities/seasonality/${selectedCommodity}`);
        return response.data.data || [];
      } catch {
        return [];
      }
    },
    staleTime: 7 * 24 * 60 * 60 * 1000,
  });

  const cotQuery = useQuery({
    queryKey: ["commodities-cot", selectedCommodity],
    queryFn: async () => {
      try {
        const response = await api.get(`/api/commodities/cot/${selectedCommodity}`);
        return response.data.data || [];
      } catch {
        return [];
      }
    },
    staleTime: 24 * 60 * 60 * 1000,
  });

  // Filter commodities by category
  const filteredCommodities = useMemo(() => {
    if (!pricesQuery.data) return [];
    if (filterCategory === "all") return pricesQuery.data;

    return pricesQuery.data.filter(p => {
      const cat = categoriesQuery.data?.find(c => c.symbol === p.symbol);
      return cat?.category === filterCategory;
    });
  }, [pricesQuery.data, filterCategory, categoriesQuery.data]);

  // Get unique categories
  const categories = useMemo(() => {
    if (!categoriesQuery.data) return [];
    const unique = new Set(categoriesQuery.data.map(c => c.category));
    return Array.from(unique).sort();
  }, [categoriesQuery.data]);

  // Get selected commodity details
  const selectedCommodityData = useMemo(() => {
    return pricesQuery.data?.find(c => c.symbol === selectedCommodity);
  }, [pricesQuery.data, selectedCommodity]);

  const selectedCommodityCategory = useMemo(() => {
    return categoriesQuery.data?.find(c => c.symbol === selectedCommodity);
  }, [categoriesQuery.data, selectedCommodity]);

  // Get correlations for selected commodity
  const selectedCorrelations = useMemo(() => {
    if (!correlationsQuery.data) return [];
    return correlationsQuery.data
      .filter(c => c.symbol1 === selectedCommodity || c.symbol2 === selectedCommodity)
      .slice(0, 5);
  }, [correlationsQuery.data, selectedCommodity]);

  const isLoading =
    pricesQuery.isLoading ||
    categoriesQuery.isLoading ||
    correlationsQuery.isLoading ||
    summaryQuery.isLoading;

  if (isLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "60vh" }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" sx={{ fontWeight: 700, mb: 1 }}>
          Commodities Trading
        </Typography>
        <Typography variant="body2" color="textSecondary">
          Real-time prices, correlations, and market data for trading decisions
        </Typography>
      </Box>

      {/* Market Overview Cards */}
      <Grid container spacing={2} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Active Commodities
              </Typography>
              <Typography variant="h5">
                {summaryQuery.data?.totalCommodities || 0}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Total Volume
              </Typography>
              <Typography variant="h5">
                {summaryQuery.data?.overview?.totalVolume
                  ? `${(summaryQuery.data.overview.totalVolume / 1000000).toFixed(1)}M`
                  : "N/A"
                }
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Correlations
              </Typography>
              <Typography variant="h5">
                {summaryQuery.data?.totalCorrelations || 0}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Data Freshness
              </Typography>
              <Typography variant="body2">
                {summaryQuery.data?.lastUpdated
                  ? new Date(summaryQuery.data.lastUpdated).toLocaleTimeString()
                  : "N/A"
                }
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* All Commodities Table */}
      <Card sx={{ mb: 4 }}>
        <CardHeader
          title="Commodities Overview"
          subheader="Click a row to view detailed analysis"
          action={
            <TextField
              select
              size="small"
              label="Category"
              value={filterCategory}
              onChange={(e) => setFilterCategory(e.target.value)}
              sx={{ minWidth: 150 }}
            >
              <MenuItem value="all">All</MenuItem>
              {categories.map(cat => (
                <MenuItem key={cat} value={cat}>{cat}</MenuItem>
              ))}
            </TextField>
          }
        />
        <TableContainer>
          <Table>
            <TableHead>
              <TableRow sx={{ backgroundColor: "#f5f5f5" }}>
                <TableCell sx={{ fontWeight: 600 }}>Symbol</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Name</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Category</TableCell>
                <TableCell align="right" sx={{ fontWeight: 600 }}>Price</TableCell>
                <TableCell align="right" sx={{ fontWeight: 600 }}>Change</TableCell>
                <TableCell align="right" sx={{ fontWeight: 600 }}>Change %</TableCell>
                <TableCell align="right" sx={{ fontWeight: 600 }}>52W High</TableCell>
                <TableCell align="right" sx={{ fontWeight: 600 }}>52W Low</TableCell>
                <TableCell align="right" sx={{ fontWeight: 600 }}>Volume</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filteredCommodities.map((commodity) => {
                const category = categoriesQuery.data?.find(c => c.symbol === commodity.symbol);
                const changeColor = getChangeColor(commodity.change_percent || 0);

                return (
                  <TableRow
                    key={commodity.symbol}
                    onClick={() => setSelectedCommodity(commodity.symbol)}
                    sx={{
                      cursor: "pointer",
                      backgroundColor: selectedCommodity === commodity.symbol ? "rgba(0, 136, 254, 0.05)" : "inherit",
                      "&:hover": { backgroundColor: "rgba(0, 0, 0, 0.02)" }
                    }}
                  >
                    <TableCell sx={{ fontWeight: 600 }}>{commodity.symbol}</TableCell>
                    <TableCell>{commodity.name}</TableCell>
                    <TableCell>
                      <Chip
                        label={category?.category || "Unknown"}
                        size="small"
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell align="right">{formatCurrency(commodity.price)}</TableCell>
                    <TableCell align="right" sx={{ color: changeColor }}>
                      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 0.5 }}>
                        {commodity.change_amount > 0 ? <TrendingUp fontSize="small" /> : commodity.change_amount < 0 ? <TrendingDown fontSize="small" /> : null}
                        {formatCurrency(commodity.change_amount || 0)}
                      </Box>
                    </TableCell>
                    <TableCell align="right" sx={{ color: changeColor, fontWeight: 600 }}>
                      {formatPercentage(commodity.change_percent || 0)}
                    </TableCell>
                    <TableCell align="right">{formatCurrency(commodity.high_52w)}</TableCell>
                    <TableCell align="right">{formatCurrency(commodity.low_52w)}</TableCell>
                    <TableCell align="right">{commodity.volume ? (commodity.volume / 1000000).toFixed(1) + "M" : "N/A"}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      </Card>

      {/* Selected Commodity Analysis */}
      {selectedCommodityData && (
        <>
          <Grid container spacing={3}>
            {/* Key Metrics */}
            <Grid item xs={12} md={6}>
              <Card>
                <CardHeader
                  title={`${selectedCommodityData.name}`}
                  subheader={`${selectedCommodityData.symbol} • ${selectedCommodityCategory?.category || "Unknown"}`}
                />
                <CardContent>
                  <Grid container spacing={2}>
                    <Grid item xs={6}>
                      <Typography color="textSecondary" variant="caption">
                        Current Price
                      </Typography>
                      <Typography variant="h5" sx={{ fontWeight: 700 }}>
                        {formatCurrency(selectedCommodityData.price)}
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography color="textSecondary" variant="caption">
                        24h Change
                      </Typography>
                      <Typography
                        variant="h5"
                        sx={{
                          fontWeight: 700,
                          color: getChangeColor(selectedCommodityData.change_percent || 0)
                        }}
                      >
                        {formatPercentage(selectedCommodityData.change_percent || 0)}
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography color="textSecondary" variant="caption">
                        52 Week High
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {formatCurrency(selectedCommodityData.high_52w)}
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography color="textSecondary" variant="caption">
                        52 Week Low
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {formatCurrency(selectedCommodityData.low_52w)}
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography color="textSecondary" variant="caption">
                        Volume (24h)
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {selectedCommodityData.volume ? (selectedCommodityData.volume / 1000000).toFixed(2) + "M" : "N/A"}
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography color="textSecondary" variant="caption">
                        Unit
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {selectedCommodityCategory?.unit || "Unknown"}
                      </Typography>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>
            </Grid>

            {/* Correlations */}
            <Grid item xs={12} md={6}>
              <Card>
                <CardHeader
                  title="Market Correlations"
                  subheader="How this commodity moves with others"
                />
                <CardContent>
                  {selectedCorrelations.length > 0 ? (
                    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
                      {selectedCorrelations.map((corr, idx) => {
                        const otherSymbol = corr.symbol1 === selectedCommodity ? corr.symbol2 : corr.symbol1;
                        const coefficient = corr.correlation_1y || corr.correlation_90d || corr.correlation_30d || 0;
                        const strength = Math.abs(coefficient);
                        let strengthLabel = "Weak";
                        if (strength > 0.7) strengthLabel = "Strong";
                        else if (strength > 0.4) strengthLabel = "Moderate";

                        const direction = coefficient > 0 ? "+" : "";

                        return (
                          <Box key={idx} sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", p: 1, backgroundColor: "#f9f9f9", borderRadius: 1 }}>
                            <Box>
                              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                {otherSymbol}
                              </Typography>
                              <Typography variant="caption" color="textSecondary">
                                {strengthLabel}
                              </Typography>
                            </Box>
                            <Typography
                              variant="body2"
                              sx={{
                                fontWeight: 700,
                                color: coefficient > 0 ? "#10b981" : "#ef4444"
                              }}
                            >
                              {direction}{(coefficient).toFixed(2)}
                            </Typography>
                          </Box>
                        );
                      })}
                    </Box>
                  ) : (
                    <Typography color="textSecondary" variant="body2">
                      No correlation data
                    </Typography>
                  )}
                </CardContent>
              </Card>
            </Grid>

            {/* Seasonality */}
            {seasonalityQuery.data && seasonalityQuery.data.length > 0 && (
              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader
                    title="Seasonal Pattern"
                    subheader="Average monthly performance"
                  />
                  <CardContent>
                    <ResponsiveContainer width="100%" height={280}>
                      <BarChart data={seasonalityQuery.data}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                        <XAxis dataKey="month" label={{ value: "Month", position: "bottom" }} />
                        <YAxis label={{ value: "Avg Return (%)", angle: -90, position: "insideLeft" }} />
                        <Tooltip formatter={(value) => `${value?.toFixed(2)}%`} />
                        <Bar dataKey="avg_return" fill="#8884d8" radius={[4, 4, 0, 0]}>
                          {seasonalityQuery.data.map((entry, index) => (
                            <Cell
                              key={`cell-${index}`}
                              fill={entry.avg_return > 0 ? "#10b981" : "#ef4444"}
                            />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>
            )}

            {/* COT Data */}
            {cotQuery.data && cotQuery.data.length > 0 && (
              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader
                    title="Commitment of Traders"
                    subheader="Large trader positioning data"
                  />
                  <CardContent>
                    {cotQuery.data.slice(0, 1).map((cot, idx) => (
                      <Box key={idx}>
                        <Alert severity="info" sx={{ mb: 2 }}>
                          Showing latest available COT report
                        </Alert>
                        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                          <Box>
                            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                              Commercial Traders
                            </Typography>
                            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1, mt: 1 }}>
                              <Box>
                                <Typography variant="caption" color="textSecondary">Long</Typography>
                                <Typography variant="body2">{cot.commercial_long?.toLocaleString()}</Typography>
                              </Box>
                              <Box>
                                <Typography variant="caption" color="textSecondary">Short</Typography>
                                <Typography variant="body2">{cot.commercial_short?.toLocaleString()}</Typography>
                              </Box>
                              <Box>
                                <Typography variant="caption" color="textSecondary">Net</Typography>
                                <Typography variant="body2" sx={{ color: cot.commercial_net > 0 ? "#10b981" : "#ef4444", fontWeight: 600 }}>
                                  {cot.commercial_net?.toLocaleString()}
                                </Typography>
                              </Box>
                            </Box>
                          </Box>
                          <Box>
                            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                              Non-Commercial Traders
                            </Typography>
                            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1, mt: 1 }}>
                              <Box>
                                <Typography variant="caption" color="textSecondary">Long</Typography>
                                <Typography variant="body2">{cot.non_commercial_long?.toLocaleString()}</Typography>
                              </Box>
                              <Box>
                                <Typography variant="caption" color="textSecondary">Short</Typography>
                                <Typography variant="body2">{cot.non_commercial_short?.toLocaleString()}</Typography>
                              </Box>
                              <Box>
                                <Typography variant="caption" color="textSecondary">Net</Typography>
                                <Typography variant="body2" sx={{ color: cot.non_commercial_net > 0 ? "#10b981" : "#ef4444", fontWeight: 600 }}>
                                  {cot.non_commercial_net?.toLocaleString()}
                                </Typography>
                              </Box>
                            </Box>
                          </Box>
                        </Box>
                      </Box>
                    ))}
                  </CardContent>
                </Card>
              </Grid>
            )}
          </Grid>
        </>
      )}
    </Container>
  );
}

export default CommoditiesAnalysis;
