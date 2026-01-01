import {
  Box,
  Card,
  CardContent,
  Grid,
  LinearProgress,
  Typography,
  Alert,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
} from "@mui/material";
import { TrendingUp, TrendingDown } from "@mui/icons-material";
import { useTheme } from "@mui/material/styles";

const MarketIndicators = ({ data, isLoading, error }) => {
  const theme = useTheme();

  if (isLoading) {
    return <LinearProgress />;
  }

  if (error || !data?.data) {
    return (
      <Alert severity="error">
        Unable to load market indicators data. {error?.message}
      </Alert>
    );
  }

  const indices = data.data.indices || [];

  // Handle case where indices might be empty
  if (!Array.isArray(indices) || indices.length === 0) {
    return (
      <Alert severity="info">
        No market indicator data available yet.
      </Alert>
    );
  }

  // Get unique symbols and find top gainers/losers (latest day)
  const symbolMap = {};
  indices.forEach((item) => {
    if (!symbolMap[item.symbol]) {
      symbolMap[item.symbol] = [];
    }
    symbolMap[item.symbol].push(item);
  });

  // Sort by date desc and get latest
  const latestData = Object.values(symbolMap).map((items) => {
    items.sort((a, b) => new Date(b.date) - new Date(a.date));
    return items[0];
  });

  const topGainers = [...latestData]
    .sort((a, b) => (b.change_percent || 0) - (a.change_percent || 0))
    .slice(0, 10);

  const topLosers = [...latestData]
    .sort((a, b) => (a.change_percent || 0) - (b.change_percent || 0))
    .slice(0, 10);

  const getChangeColor = (changePercent) => {
    if ((changePercent || 0) > 0) return theme.palette.success.main;
    if ((changePercent || 0) < 0) return theme.palette.error.main;
    return theme.palette.grey[600];
  };

  const formatNumber = (num) => {
    if (num >= 1000000) {
      return (num / 1000000).toFixed(1) + "M";
    }
    if (num >= 1000) {
      return (num / 1000).toFixed(1) + "K";
    }
    return num.toFixed(0);
  };

  return (
    <Box>
      <Grid container spacing={3}>
        {/* Top Gainers */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
                <TrendingUp sx={{ color: theme.palette.success.main, fontSize: 28 }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>
                  Top Gainers
                </Typography>
              </Box>

              <TableContainer component={Paper} elevation={0}>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ backgroundColor: "grey.50" }}>
                      <TableCell sx={{ fontWeight: 600 }}>Symbol</TableCell>
                      <TableCell sx={{ fontWeight: 600 }}>Price</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 600 }}>
                        Change %
                      </TableCell>
                      <TableCell sx={{ fontWeight: 600 }}>Sector</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {topGainers.map((stock, idx) => (
                      <TableRow key={`${stock.symbol}-${idx}`} hover>
                        <TableCell sx={{ fontWeight: 600 }}>{stock.symbol}</TableCell>
                        <TableCell>${parseFloat(stock.close).toFixed(2)}</TableCell>
                        <TableCell
                          align="right"
                          sx={{
                            color: getChangeColor(stock.change_percent),
                            fontWeight: 600,
                          }}
                        >
                          +{parseFloat(stock.change_percent || 0).toFixed(2)}%
                        </TableCell>
                        <TableCell>
                          <Chip label={stock.sector} size="small" variant="outlined" />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* Top Losers */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
                <TrendingDown sx={{ color: theme.palette.error.main, fontSize: 28 }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>
                  Top Losers
                </Typography>
              </Box>

              <TableContainer component={Paper} elevation={0}>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ backgroundColor: "grey.50" }}>
                      <TableCell sx={{ fontWeight: 600 }}>Symbol</TableCell>
                      <TableCell sx={{ fontWeight: 600 }}>Price</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 600 }}>
                        Change %
                      </TableCell>
                      <TableCell sx={{ fontWeight: 600 }}>Sector</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {topLosers.map((stock, idx) => (
                      <TableRow key={`${stock.symbol}-${idx}`} hover>
                        <TableCell sx={{ fontWeight: 600 }}>{stock.symbol}</TableCell>
                        <TableCell>${parseFloat(stock.close).toFixed(2)}</TableCell>
                        <TableCell
                          align="right"
                          sx={{
                            color: getChangeColor(stock.change_percent),
                            fontWeight: 600,
                          }}
                        >
                          {parseFloat(stock.change_percent || 0).toFixed(2)}%
                        </TableCell>
                        <TableCell>
                          <Chip label={stock.sector} size="small" variant="outlined" />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* Market Stats */}
        <Grid item xs={12}>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent sx={{ textAlign: "center" }}>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                    Total Stocks
                  </Typography>
                  <Typography variant="h5" sx={{ fontWeight: 600 }}>
                    {latestData.length}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent sx={{ textAlign: "center" }}>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                    Gainers
                  </Typography>
                  <Typography
                    variant="h5"
                    sx={{ fontWeight: 600, color: theme.palette.success.main }}
                  >
                    {latestData.filter((s) => (s.change_percent || 0) > 0).length}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent sx={{ textAlign: "center" }}>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                    Losers
                  </Typography>
                  <Typography
                    variant="h5"
                    sx={{ fontWeight: 600, color: theme.palette.error.main }}
                  >
                    {latestData.filter((s) => (s.change_percent || 0) < 0).length}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent sx={{ textAlign: "center" }}>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                    Unchanged
                  </Typography>
                  <Typography
                    variant="h5"
                    sx={{ fontWeight: 600, color: theme.palette.grey[600] }}
                  >
                    {latestData.filter((s) => (s.change_percent || 0) === 0).length}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </Grid>
      </Grid>
    </Box>
  );
};

export default MarketIndicators;
