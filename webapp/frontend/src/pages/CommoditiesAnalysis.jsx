import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Box,
  Card,
  CardContent,
  Chip,
  Container,
  Grid,
  Tab,
  Tabs,
  Typography,
  CircularProgress,
  Alert,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from "@mui/material";
import { TrendingUp, TrendingDown } from "@mui/icons-material";
import api from "../services/api";
import { getChangeColor, formatPercentage } from "../utils/formatters";

function TabPanel({ children, value, index }) {
  return (
    <div hidden={value !== index}>
      {value === index && <Box sx={{ py: 2 }}>{children}</Box>}
    </div>
  );
}

export default function CommoditiesAnalysis() {
  const [tabValue, setTabValue] = useState(0);

  // Fetch categories
  const categoriesQuery = useQuery({
    queryKey: ["commodities-categories"],
    queryFn: async () => {
      const response = await api.get("/api/commodities/categories");
      return response.data.data;
    },
    staleTime: 5 * 60 * 1000,
  });

  // Fetch prices
  const pricesQuery = useQuery({
    queryKey: ["commodities-prices"],
    queryFn: async () => {
      const response = await api.get("/api/commodities/prices?limit=100");
      return response.data.data;
    },
    staleTime: 5 * 60 * 1000,
  });

  // Fetch market summary
  const summaryQuery = useQuery({
    queryKey: ["commodities-summary"],
    queryFn: async () => {
      const response = await api.get("/api/commodities/market-summary");
      return response.data.data;
    },
    staleTime: 5 * 60 * 1000,
  });

  // Fetch correlations
  const correlationsQuery = useQuery({
    queryKey: ["commodities-correlations"],
    queryFn: async () => {
      const response = await api.get(
        "/api/commodities/correlations?minCorrelation=0.5"
      );
      return response.data.data.correlations;
    },
    staleTime: 30 * 60 * 1000,
  });

  const isLoading =
    categoriesQuery.isLoading ||
    pricesQuery.isLoading ||
    summaryQuery.isLoading ||
    correlationsQuery.isLoading;

  const hasError =
    categoriesQuery.error ||
    pricesQuery.error ||
    summaryQuery.error ||
    correlationsQuery.error;

  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" component="h1" sx={{ fontWeight: 700, mb: 1 }}>
          Commodities Analysis
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Real-time commodity prices, market trends, and correlations
        </Typography>
      </Box>

      {isLoading && (
        <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
          <Box sx={{ textAlign: "center" }}>
            <CircularProgress />
            <Typography sx={{ mt: 2 }}>Loading commodities data...</Typography>
          </Box>
        </Box>
      )}

      {hasError && !isLoading && (
        <Alert severity="error">
          Failed to load commodities data. Please try again later.
        </Alert>
      )}

      {!isLoading && !hasError && (
        <>
          {/* Market Summary Cards */}
          {summaryQuery.data && (
            <Grid container spacing={2} sx={{ mb: 4 }}>
              <Grid item xs={12} sm={6} md={3}>
                <Card>
                  <CardContent>
                    <Typography color="textSecondary" gutterBottom>
                      Active Contracts
                    </Typography>
                    <Typography variant="h5">
                      {summaryQuery.data.overview?.activeContracts || 0}
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
                      {(summaryQuery.data.overview?.totalVolume / 1e6).toFixed(
                        1
                      )}
                      M
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Card>
                  <CardContent>
                    <Typography color="textSecondary" gutterBottom>
                      Top Gainer
                    </Typography>
                    {summaryQuery.data.topGainers?.[0] && (
                      <>
                        <Typography
                          variant="body2"
                          sx={{ fontWeight: 600, mb: 1 }}
                        >
                          {summaryQuery.data.topGainers[0].name}
                        </Typography>
                        <Chip
                          icon={<TrendingUp />}
                          label={`+${summaryQuery.data.topGainers[0].change}%`}
                          color="success"
                          size="small"
                        />
                      </>
                    )}
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Card>
                  <CardContent>
                    <Typography color="textSecondary" gutterBottom>
                      Top Loser
                    </Typography>
                    {summaryQuery.data.topLosers?.[0] && (
                      <>
                        <Typography
                          variant="body2"
                          sx={{ fontWeight: 600, mb: 1 }}
                        >
                          {summaryQuery.data.topLosers[0].name}
                        </Typography>
                        <Chip
                          icon={<TrendingDown />}
                          label={`${summaryQuery.data.topLosers[0].change}%`}
                          color="error"
                          size="small"
                        />
                      </>
                    )}
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          )}

          {/* Tabs */}
          <Card>
            <Box sx={{ borderBottom: 1, borderColor: "divider" }}>
              <Tabs value={tabValue} onChange={(e, val) => setTabValue(val)}>
                <Tab label="Categories" />
                <Tab label="Top Movers" />
                <Tab label="All Prices" />
                <Tab label="Correlations" />
              </Tabs>
            </Box>

            {/* Categories Tab */}
            <TabPanel value={tabValue} index={0}>
              {categoriesQuery.data && categoriesQuery.data.length > 0 ? (
                <TableContainer>
                  <Table>
                    <TableHead>
                      <TableRow sx={{ backgroundColor: "#f5f5f5" }}>
                        <TableCell sx={{ fontWeight: 600 }}>
                          Category
                        </TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>
                          Count
                        </TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>
                          Avg Change (1D)
                        </TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>
                          High (52W)
                        </TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>
                          Low (52W)
                        </TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {categoriesQuery.data.map((cat) => (
                        <TableRow key={cat.category}>
                          <TableCell sx={{ fontWeight: 500 }}>
                            {cat.name}
                          </TableCell>
                          <TableCell align="right">
                            {cat.commodityCount}
                          </TableCell>
                          <TableCell
                            align="right"
                            sx={{
                              color: getChangeColor(cat.avgChange1d),
                              fontWeight: 500,
                            }}
                          >
                            {cat.avgChange1d}%
                          </TableCell>
                          <TableCell align="right">
                            ${cat.highestPrice?.toFixed(2)}
                          </TableCell>
                          <TableCell align="right">
                            ${cat.lowestPrice?.toFixed(2)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : (
                <Alert severity="info">No category data available</Alert>
              )}
            </TabPanel>

            {/* Top Movers Tab */}
            <TabPanel value={tabValue} index={1}>
              <Box sx={{ mb: 3 }}>
                <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                  Top Gainers
                </Typography>
                {summaryQuery.data?.topGainers &&
                summaryQuery.data.topGainers.length > 0 ? (
                  <TableContainer>
                    <Table size="small">
                      <TableHead>
                        <TableRow sx={{ backgroundColor: "#f5f5f5" }}>
                          <TableCell sx={{ fontWeight: 600 }}>Symbol</TableCell>
                          <TableCell sx={{ fontWeight: 600 }}>Name</TableCell>
                          <TableCell align="right" sx={{ fontWeight: 600 }}>
                            Price
                          </TableCell>
                          <TableCell align="right" sx={{ fontWeight: 600 }}>
                            Change
                          </TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {summaryQuery.data.topGainers.map((item) => (
                          <TableRow key={item.symbol}>
                            <TableCell sx={{ fontWeight: 500 }}>
                              {item.symbol}
                            </TableCell>
                            <TableCell>{item.name}</TableCell>
                            <TableCell align="right">
                              ${item.price?.toFixed(2)}
                            </TableCell>
                            <TableCell
                              align="right"
                              sx={{
                                color: getChangeColor(item.change),
                                fontWeight: 500,
                              }}
                            >
                              +{item.change}%
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                ) : (
                  <Alert severity="info">No data available</Alert>
                )}
              </Box>

              <Box>
                <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                  Top Losers
                </Typography>
                {summaryQuery.data?.topLosers &&
                summaryQuery.data.topLosers.length > 0 ? (
                  <TableContainer>
                    <Table size="small">
                      <TableHead>
                        <TableRow sx={{ backgroundColor: "#f5f5f5" }}>
                          <TableCell sx={{ fontWeight: 600 }}>Symbol</TableCell>
                          <TableCell sx={{ fontWeight: 600 }}>Name</TableCell>
                          <TableCell align="right" sx={{ fontWeight: 600 }}>
                            Price
                          </TableCell>
                          <TableCell align="right" sx={{ fontWeight: 600 }}>
                            Change
                          </TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {summaryQuery.data.topLosers.map((item) => (
                          <TableRow key={item.symbol}>
                            <TableCell sx={{ fontWeight: 500 }}>
                              {item.symbol}
                            </TableCell>
                            <TableCell>{item.name}</TableCell>
                            <TableCell align="right">
                              ${item.price?.toFixed(2)}
                            </TableCell>
                            <TableCell
                              align="right"
                              sx={{
                                color: getChangeColor(item.change),
                                fontWeight: 500,
                              }}
                            >
                              {item.change}%
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                ) : (
                  <Alert severity="info">No data available</Alert>
                )}
              </Box>
            </TabPanel>

            {/* All Prices Tab */}
            <TabPanel value={tabValue} index={2}>
              {pricesQuery.data && pricesQuery.data.length > 0 ? (
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow sx={{ backgroundColor: "#f5f5f5" }}>
                        <TableCell sx={{ fontWeight: 600 }}>Symbol</TableCell>
                        <TableCell sx={{ fontWeight: 600 }}>Name</TableCell>
                        <TableCell sx={{ fontWeight: 600 }}>Category</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>
                          Price
                        </TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>
                          Change
                        </TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>
                          Volume
                        </TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {pricesQuery.data.map((item) => (
                        <TableRow key={item.symbol}>
                          <TableCell sx={{ fontWeight: 500 }}>
                            {item.symbol}
                          </TableCell>
                          <TableCell>{item.name}</TableCell>
                          <TableCell>
                            <Chip
                              label={item.category}
                              size="small"
                              variant="outlined"
                            />
                          </TableCell>
                          <TableCell align="right">
                            ${item.price?.toFixed(2)}
                          </TableCell>
                          <TableCell
                            align="right"
                            sx={{
                              color: getChangeColor(item.changePercent),
                              fontWeight: 500,
                            }}
                          >
                            {item.changePercent}%
                          </TableCell>
                          <TableCell align="right">
                            {(item.volume / 1e6).toFixed(2)}M
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : (
                <Alert severity="info">No price data available</Alert>
              )}
            </TabPanel>

            {/* Correlations Tab */}
            <TabPanel value={tabValue} index={3}>
              {correlationsQuery.data && correlationsQuery.data.length > 0 ? (
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow sx={{ backgroundColor: "#f5f5f5" }}>
                        <TableCell sx={{ fontWeight: 600 }}>Pair</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>
                          Correlation
                        </TableCell>
                        <TableCell sx={{ fontWeight: 600 }}>Strength</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {correlationsQuery.data.map((item) => (
                        <TableRow
                          key={`${item.symbol1}-${item.symbol2}`}
                        >
                          <TableCell>{item.pair}</TableCell>
                          <TableCell align="right" sx={{ fontWeight: 500 }}>
                            {item.coefficient}
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={item.strength}
                              size="small"
                              color={
                                item.strength === "strong"
                                  ? "error"
                                  : item.strength === "moderate"
                                  ? "warning"
                                  : "default"
                              }
                              variant="outlined"
                            />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : (
                <Alert severity="info">No correlation data available</Alert>
              )}
            </TabPanel>
          </Card>
        </>
      )}
    </Container>
  );
}
