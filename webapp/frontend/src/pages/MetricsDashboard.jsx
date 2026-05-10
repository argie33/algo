import { useState, useMemo } from "react";
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Container,
  FormControl,
  Grid,
  IconButton,
  InputLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Select,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import {
  TrendingUp,
  Info,
  Assessment,
  AttachMoney,
  AccountBalance,
} from "@mui/icons-material";
import { useApiQuery } from "../hooks/useApiQuery";
import api from "../services/api";

const MetricsDashboard = () => {
  const [activeTab, setActiveTab] = useState(0);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedSector, setSelectedSector] = useState("");
  const [minMetric, setMinMetric] = useState(0);
  const [maxMetric, setMaxMetric] = useState(1);
  const [sortBy, setSortBy] = useState("composite_metric");
  const [sortOrder, setSortOrder] = useState("desc");
  const [page, setPage] = useState(1);

  const { data: allStocks = [], loading, error } = useApiQuery(
    ['stockscores'],
    () => api.get("/api/scores/stockscores?limit=10000")
  );

  const stocks = useMemo(() => {
    let filtered = Array.isArray(allStocks) ? allStocks : [];

    if (searchTerm) {
      filtered = filtered.filter(s =>
        s.symbol.toLowerCase().includes(searchTerm.toLowerCase())
      );
    }

    if (selectedSector) {
      filtered = filtered.filter(s => s.sector === selectedSector);
    }

    filtered.sort((a, b) => {
      const sortKey = sortBy === "composite_metric" ? "composite_score" : sortBy.replace("_metric", "_score");
      const aVal = a[sortKey] || 0;
      const bVal = b[sortKey] || 0;
      return sortOrder === "desc" ? bVal - aVal : aVal - bVal;
    });

    return filtered;
  }, [allStocks, searchTerm, selectedSector, sortBy, sortOrder]);

  const totalPages = useMemo(() => Math.ceil(stocks.length / 50), [stocks]);

  const sectors = useMemo(() => {
    const sectorData = {};
    allStocks.forEach(stock => {
      if (stock.sector) {
        if (!sectorData[stock.sector]) {
          sectorData[stock.sector] = [];
        }
        sectorData[stock.sector].push(stock);
      }
    });

    return Object.entries(sectorData).map(([name, stocks]) => ({
      name,
      count: stocks.length,
      avgComposite: (stocks.reduce((sum, s) => sum + (s.composite_score || 0), 0) / stocks.length).toFixed(2),
    }));
  }, [allStocks]);

  const topStocksData = useMemo(() => {
    const allList = Array.isArray(allStocks) ? allStocks : [];
    const compositeList = [...allList].filter(s => s.composite_score !== null).sort((a, b) => b.composite_score - a.composite_score);
    const qualityList = [...allList].filter(s => s.quality_score !== null).sort((a, b) => b.quality_score - a.quality_score);
    const valueList = [...allList].filter(s => s.value_score !== null).sort((a, b) => b.value_score - a.value_score);
    return {
      composite: { items: compositeList.slice(0, 10), total: compositeList.length },
      quality: { items: qualityList.slice(0, 10), total: qualityList.length },
      value: { items: valueList.slice(0, 10), total: valueList.length },
    };
  }, [allStocks]);

  const getMetricColor = (metric) => {
    if (metric >= 0.8) return "#4caf50"; // Green
    if (metric >= 0.7) return "#8bc34a"; // Light green
    if (metric >= 0.6) return "#ffeb3b"; // Yellow
    if (metric >= 0.5) return "#ff9800"; // Orange
    return "#f44336"; // Red
  };

  const getMetricChip = (metric, label) => (
    <Chip
      label={`${label}: ${metric.toFixed(3)}`}
      size="small"
      style={{
        backgroundColor: getMetricColor(metric),
        color: metric >= 0.6 ? "#000" : "#fff",
        fontWeight: "bold",
        margin: "2px",
      }}
    />
  );

  const MetricProgressBar = ({ metric, label, icon }) => (
    <Box sx={{ mb: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", mb: 1 }}>
        {icon}
        <Typography variant="body2" sx={{ ml: 1, flex: 1 }}>
          {label}
        </Typography>
        <Typography variant="body2" sx={{ fontWeight: "bold" }}>
          {metric.toFixed(3)}
        </Typography>
      </Box>
      <LinearProgress
        variant="determinate"
        value={metric * 100}
        sx={{
          height: 8,
          borderRadius: 4,
          "& .MuiLinearProgress-bar": {
            backgroundColor: getMetricColor(metric),
            borderRadius: 4,
          },
        }}
      />
    </Box>
  );

  const MainMetricsTable = () => (
    <TableContainer component={Paper} sx={{ mt: 3 }}>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>
              <strong>Symbol</strong>
            </TableCell>
            <TableCell>
              <strong>Company</strong>
            </TableCell>
            <TableCell>
              <strong>Sector</strong>
            </TableCell>
            <TableCell align="center">
              <strong>Composite Metric</strong>
            </TableCell>
            <TableCell align="center">
              <strong>Quality</strong>
            </TableCell>
            <TableCell align="center">
              <strong>Value</strong>
            </TableCell>
            <TableCell align="center">
              <strong>Growth</strong>
            </TableCell>
            <TableCell>
              <strong>Price</strong>
            </TableCell>
            <TableCell>
              <strong>Market Cap</strong>
            </TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {(stocks || []).map((stock, _index) => (
            <TableRow key={stock.symbol} hover>
              <TableCell>
                <Typography
                  variant="subtitle2"
                  sx={{ fontWeight: "bold", color: "#1976d2" }}
                >
                  {stock.symbol}
                </Typography>
              </TableCell>
              <TableCell>
                <Typography variant="body2">
                  {stock.company_name?.substring(0, 30)}
                  {stock.company_name?.length > 30 ? "..." : ""}
                </Typography>
              </TableCell>
              <TableCell>
                <Chip label={stock.sector} size="small" variant="outlined" />
              </TableCell>
              <TableCell align="center">
                <Typography
                  variant="h6"
                  sx={{
                    color: getMetricColor(stock.composite_score || 0),
                    fontWeight: "bold",
                  }}
                >
                  {(stock.composite_score || 0).toFixed(3)}
                </Typography>
              </TableCell>
              <TableCell align="center">
                <Typography
                  sx={{ color: getMetricColor(stock.quality_score || 0) }}
                >
                  {(stock.quality_score || 0).toFixed(3)}
                </Typography>
              </TableCell>
              <TableCell align="center">
                <Typography sx={{ color: getMetricColor(stock.value_score || 0) }}>
                  {(stock.value_score || 0).toFixed(3)}
                </Typography>
              </TableCell>
              <TableCell align="center">
                <Typography
                  sx={{ color: getMetricColor(stock.growth_score || 0) }}
                >
                  {(stock.growth_score || 0).toFixed(3)}
                </Typography>
              </TableCell>
              <TableCell>${stock.current_price?.toFixed(2) || "N/A"}</TableCell>
              <TableCell>
                {stock.market_cap
                  ? `$${(stock.market_cap / 1e9).toFixed(1)}B`
                  : "N/A"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );

  const SectorAnalysis = () => (
    <Grid container spacing={3} sx={{ mt: 2 }}>
      {(sectors || []).map((sector) => (
        <Grid item xs={12} md={6} lg={4} key={sector.name}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                {sector.name}
              </Typography>
              <Typography variant="body2" color="textSecondary" gutterBottom>
                {sector.count} stocks
              </Typography>

              <MetricProgressBar
                metric={parseFloat(sector.avgComposite) || 0}
                label="Composite"
                icon={<Assessment />}
              />

              <Box
                sx={{ mt: 2, display: "flex", justifyContent: "center" }}
              >
                <Typography variant="caption" color="text.secondary">
                  Average metric score
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      ))}
    </Grid>
  );

  const TopStocks = () => (
    <Grid container spacing={3} sx={{ mt: 2 }}>
      {Object.entries(topStocksData).map(([category, data]) => {
        const stocks = data?.items || [];
        const total = data?.total || 0;
        return (
        <Grid item xs={12} md={6} key={category}>
          <Card>
            <CardContent>
              <Typography
                variant="h6"
                gutterBottom
                sx={{ textTransform: "capitalize" }}
              >
                Top {category === "composite" ? "Overall" : category} Stocks
                {total > 10 && <span style={{ fontSize: '0.75em', marginLeft: 8, color: '#999' }}>({stocks.length} of {total})</span>}
              </Typography>
              <Box sx={{ maxHeight: 400, overflow: "auto" }}>
                {(stocks || []).map((stock, index) => {
                  const scoreKey = category === "composite" ? "composite_score" : category === "quality" ? "quality_score" : "value_score";
                  const scoreValue = stock[scoreKey] || 0;
                  return (
                    <Box
                      key={stock.symbol}
                      sx={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        py: 1,
                        borderBottom: index < 9 ? "1px solid #eee" : "none",
                      }}
                    >
                      <Box>
                        <Typography variant="subtitle2" sx={{ fontWeight: "bold" }}>
                          {index + 1}. {stock.symbol}
                        </Typography>
                        <Typography variant="caption" color="textSecondary">
                          {stock.company_name?.substring(0, 25)}
                          {stock.company_name?.length > 25 ? "..." : ""}
                        </Typography>
                      </Box>
                      <Box sx={{ textAlign: "right" }}>
                        <Typography
                          variant="body2"
                          sx={{
                            color: getMetricColor(scoreValue),
                            fontWeight: "bold",
                          }}
                        >
                          {scoreValue.toFixed(3)}
                        </Typography>
                        <Typography variant="caption" color="textSecondary">
                          {stock.sector}
                        </Typography>
                      </Box>
                    </Box>
                  );
                })}
              </Box>
            </CardContent>
          </Card>
        </Grid>
      );
      })}
    </Grid>
  );

  if (error) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4 }}>
        <Alert severity="error">Error loading metrics: {error}</Alert>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ mt: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h3" component="h1" gutterBottom>
          Institutional-Grade Stock Metrics
        </Typography>
        <Typography variant="subtitle1" color="textSecondary">
          Advanced multi-factor analysis based on academic research and
          institutional methodology
        </Typography>
      </Box>

      {/* Navigation Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 3 }}>
        <Tabs
          value={activeTab}
          onChange={(e, newValue) => setActiveTab(newValue)}
        >
          <Tab value={0} label="Stock Metrics" />
          <Tab value={1} label="Sector Analysis" />
          <Tab value={2} label="Top Performers" />
        </Tabs>
      </Box>

      {/* Filters for Stock Metrics Tab */}
      {activeTab === 0 && (
        <Paper sx={{ p: 3, mb: 3 }}>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} sm={3}>
              <TextField
                fullWidth
                label="Search Symbol/Company"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                size="small"
              />
            </Grid>
            <Grid item xs={12} sm={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Sector</InputLabel>
                <Select
                  value={selectedSector}
                  label="Sector"
                  onChange={(e) => setSelectedSector(e.target.value)}
                >
                  <MenuItem value="">All Sectors</MenuItem>
                  <MenuItem value="Technology">Technology</MenuItem>
                  <MenuItem value="Healthcare">Healthcare</MenuItem>
                  <MenuItem value="Financial Services">
                    Financial Services
                  </MenuItem>
                  <MenuItem value="Consumer Cyclical">
                    Consumer Cyclical
                  </MenuItem>
                  <MenuItem value="Industrials">Industrials</MenuItem>
                  <MenuItem value="Communication Services">
                    Communication Services
                  </MenuItem>
                  <MenuItem value="Consumer Defensive">
                    Consumer Defensive
                  </MenuItem>
                  <MenuItem value="Energy">Energy</MenuItem>
                  <MenuItem value="Utilities">Utilities</MenuItem>
                  <MenuItem value="Real Estate">Real Estate</MenuItem>
                  <MenuItem value="Basic Materials">Basic Materials</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={2}>
              <TextField
                fullWidth
                label="Min Metric"
                type="number"
                value={minMetric}
                onChange={(e) => setMinMetric(Number(e.target.value))}
                size="small"
                inputProps={{ min: 0, max: 1, step: 0.01 }}
              />
            </Grid>
            <Grid item xs={12} sm={2}>
              <TextField
                fullWidth
                label="Max Metric"
                type="number"
                value={maxMetric}
                onChange={(e) => setMaxMetric(Number(e.target.value))}
                size="small"
                inputProps={{ min: 0, max: 1, step: 0.01 }}
              />
            </Grid>
            <Grid item xs={12} sm={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Sort By</InputLabel>
                <Select
                  value={sortBy}
                  label="Sort By"
                  onChange={(e) => setSortBy(e.target.value)}
                >
                  <MenuItem value="composite_metric">Composite Metric</MenuItem>
                  <MenuItem value="quality_metric">Quality Metric</MenuItem>
                  <MenuItem value="value_metric">Value Metric</MenuItem>
                  <MenuItem value="market_cap">Market Cap</MenuItem>
                  <MenuItem value="symbol">Symbol</MenuItem>
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </Paper>
      )}

      {/* Content based on active tab */}
      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", mt: 4 }}>
          <CircularProgress />
        </Box>
      ) : (
        <>
          {activeTab === 0 && <MainMetricsTable />}
          {activeTab === 1 && <SectorAnalysis />}
          {activeTab === 2 && <TopStocks />}
        </>
      )}

      {/* Pagination for Stock Metrics */}
      {activeTab === 0 && totalPages > 1 && (
        <Box sx={{ display: "flex", justifyContent: "center", mt: 3 }}>
          <Typography variant="body2" sx={{ mt: 1 }}>
            Page {page} of {totalPages}
          </Typography>
          {/* Add pagination controls here if needed */}
        </Box>
      )}

      {/* Legend */}
      <Paper sx={{ p: 2, mt: 4, backgroundColor: "#f5f5f5" }}>
        <Typography variant="h6" gutterBottom>
          Metrics Methodology
        </Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6} md={6}>
            <Typography variant="subtitle2">Quality Metric</Typography>
            <Typography variant="caption">
              Financial statement quality, balance sheet strength,
              profitability, management effectiveness using Piotroski F-Score,
              Altman Z-Score analysis
            </Typography>
          </Grid>
          <Grid item xs={12} sm={6} md={6}>
            <Typography variant="subtitle2">Value Metric</Typography>
            <Typography variant="caption">
              Traditional multiples (P/E, P/B, EV/EBITDA), DCF intrinsic value,
              dividend discount model, and peer comparison analysis
            </Typography>
          </Grid>
          <Grid item xs={12} sm={6} md={6}>
            <Typography variant="subtitle2">Growth Metric</Typography>
            <Typography variant="caption">
              Revenue growth analysis, earnings growth quality, fundamental
              growth drivers, and market expansion potential based on academic
              research
            </Typography>
          </Grid>
        </Grid>

        <Box sx={{ mt: 2 }}>
          <Typography variant="subtitle2" gutterBottom>
            Metric Ranges (0-1 Scale):
          </Typography>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
            {getMetricChip(0.9, "Excellent (0.8-1.0)")}
            {getMetricChip(0.75, "Good (0.7-0.79)")}
            {getMetricChip(0.65, "Fair (0.6-0.69)")}
            {getMetricChip(0.55, "Below Average (0.5-0.59)")}
            {getMetricChip(0.4, "Poor (0.0-0.49)")}
          </Box>
        </Box>
      </Paper>
    </Container>
  );
};

export default MetricsDashboard;
