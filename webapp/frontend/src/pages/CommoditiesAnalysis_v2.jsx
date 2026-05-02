import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Box, Container, Card, CardContent, CardHeader, Chip, CircularProgress,
  Grid, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Typography, TextField, MenuItem, Tab, Tabs, Alert
} from "@mui/material";
import { TrendingUp, TrendingDown } from "@mui/icons-material";
import {
  LineChart, Line, BarChart, Bar, ComposedChart, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, Cell, ReferenceLine
} from "recharts";
import api, { extractData } from "../services/api";
import { formatCurrency, formatPercentage, getChangeColor, getTechStatus } from "../utils/formatters";

function TabPanel(props) {
  const { children, value, index, ...other } = props;
  return (
    <div role="tabpanel" hidden={value !== index} {...other}>
      {value === index && <Box sx={{ pt: 3 }}>{children}</Box>}
    </div>
  );
}

function CommoditiesAnalysis() {
  const [tabValue, setTabValue] = useState(0);
  const [selectedCommodity, setSelectedCommodity] = useState("GC=F");
  const [filterCategory, setFilterCategory] = useState("all");

  // Data queries
  const pricesQuery = useQuery({
    queryKey: ["commodities-prices"],
    queryFn: async () => {
      const response = await api.get("/api/commodities/prices?limit=100");
      return extractData(response).items || extractData(response).data || [];
    },
    staleTime: 2 * 60 * 1000,
  });

  const categoriesQuery = useQuery({
    queryKey: ["commodities-categories"],
    queryFn: async () => {
      const response = await api.get("/api/commodities/categories");
      return extractData(response).items || extractData(response).data || [];
    },
    staleTime: 5 * 60 * 1000,
  });

  const technicalsQuery = useQuery({
    queryKey: ["commodities-technicals", selectedCommodity],
    queryFn: async () => {
      try {
        const response = await api.get(`/api/commodities/technicals/${selectedCommodity}`);
        return extractData(response).technicals || [];
      } catch {
        return [];
      }
    },
    staleTime: 60 * 60 * 1000,
  });

  const macroQuery = useQuery({
    queryKey: ["commodities-macro"],
    queryFn: async () => {
      try {
        const response = await api.get("/api/commodities/macro");
        return extractData(response).macroDrivers || [];
      } catch {
        return [];
      }
    },
    staleTime: 24 * 60 * 60 * 1000,
  });

  const eventsQuery = useQuery({
    queryKey: ["commodities-events"],
    queryFn: async () => {
      try {
        const response = await api.get("/api/commodities/events");
        return extractData(response).events || [];
      } catch {
        return [];
      }
    },
    staleTime: 24 * 60 * 60 * 1000,
  });

  const seasonalityQuery = useQuery({
    queryKey: ["commodities-seasonality", selectedCommodity],
    queryFn: async () => {
      try {
        const response = await api.get(`/api/commodities/seasonality/${selectedCommodity}`);
        return extractData(response).seasonality || [];
      } catch {
        return [];
      }
    },
    staleTime: 7 * 24 * 60 * 60 * 1000,
  });

  const correlationsQuery = useQuery({
    queryKey: ["commodities-correlations"],
    queryFn: async () => {
      try {
        const response = await api.get("/api/commodities/correlations?minCorrelation=0.3");
        return extractData(response).correlations || [];
      } catch {
        return [];
      }
    },
    staleTime: 30 * 60 * 1000,
  });

  // Memoized computations
  const filteredCommodities = useMemo(() => {
    const prices = Array.isArray(pricesQuery.data) ? pricesQuery.data : [];
    if (!prices.length) return [];
    if (filterCategory === "all") return prices;
    return prices.filter(p => {
      const cat = categoriesQuery.data?.find(c => c.symbol === p.symbol);
      return cat?.category === filterCategory;
    });
  }, [pricesQuery.data, filterCategory, categoriesQuery.data]);

  const categories = useMemo(() => {
    if (!categoriesQuery.data) return [];
    return [...new Set(categoriesQuery.data.map(c => c.category))].sort();
  }, [categoriesQuery.data]);

  const selectedCommodityData = useMemo(() => {
    const prices = Array.isArray(pricesQuery.data) ? pricesQuery.data : [];
    return prices.find(c => c.symbol === selectedCommodity);
  }, [pricesQuery.data, selectedCommodity]);

  const selectedCommodityCategory = useMemo(() => {
    return categoriesQuery.data?.find(c => c.symbol === selectedCommodity);
  }, [categoriesQuery.data, selectedCommodity]);

  const isLoading = pricesQuery.isLoading || categoriesQuery.isLoading;

  if (isLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "60vh" }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" sx={{ fontWeight: 700, mb: 1 }}>
          Commodities Intelligence Dashboard
        </Typography>
        <Typography variant="body2" color="textSecondary">
          Real-time prices, technicals, macro drivers, and market data for trading decisions
        </Typography>
      </Box>

      {/* Tabs Navigation */}
      <Paper sx={{ mb: 4 }}>
        <Tabs value={tabValue} onChange={(e, v) => setTabValue(v)} sx={{ borderBottom: 1, borderColor: "divider" }}>
          <Tab label="Overview" />
          <Tab label="Technicals" />
          <Tab label="Macro Drivers" />
          <Tab label="Events Calendar" />
          <Tab label="Seasonality" />
        </Tabs>
      </Paper>

      {/* TAB 0: OVERVIEW */}
      <TabPanel value={tabValue} index={0}>
        <Grid container spacing={2} sx={{ mb: 4 }}>
          <Grid item xs={6} sm={3}><Card><CardContent><Typography color="textSecondary" variant="caption">Active Commodities</Typography><Typography variant="h5">{filteredCommodities.length}</Typography></CardContent></Card></Grid>
          <Grid item xs={6} sm={3}><Card><CardContent><Typography color="textSecondary" variant="caption">Categories</Typography><Typography variant="h5">{categories.length}</Typography></CardContent></Card></Grid>
          <Grid item xs={6} sm={3}><Card><CardContent><Typography color="textSecondary" variant="caption">Correlations Found</Typography><Typography variant="h5">{correlationsQuery.data?.length || 0}</Typography></CardContent></Card></Grid>
          <Grid item xs={6} sm={3}><Card><CardContent><Typography color="textSecondary" variant="caption">Last Updated</Typography><Typography variant="caption">{new Date().toLocaleTimeString()}</Typography></CardContent></Card></Grid>
        </Grid>

        <Card>
          <CardHeader
            title="Commodities Overview"
            subheader="Click a row to see detailed analysis"
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
                  <TableCell align="right" sx={{ fontWeight: 600 }}>Change %</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 600 }}>52W High/Low</TableCell>
                  <TableCell align="center" sx={{ fontWeight: 600 }}>Signal</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredCommodities.map((commodity) => {
                  const category = categoriesQuery.data?.find(c => c.symbol === commodity.symbol);
                  const changeColor = getChangeColor(commodity.change_percent || 0);
                  const techData = technicalsQuery.data?.[0]; // Latest technical
                  let signal = "—";
                  let signalColor = "default";

                  if (techData?.signal === "BUY") {
                    signal = "🟢 BUY";
                    signalColor = "success";
                  } else if (techData?.signal === "SELL") {
                    signal = "🔴 SELL";
                    signalColor = "error";
                  } else if (techData?.signal === "BULLISH") {
                    signal = "↗ BULLISH";
                    signalColor = "success";
                  } else if (techData?.signal === "BEARISH") {
                    signal = "↘ BEARISH";
                    signalColor = "error";
                  }

                  return (
                    <TableRow
                      key={commodity.symbol}
                      onClick={() => {
                        setSelectedCommodity(commodity.symbol);
                        setTabValue(1);
                      }}
                      sx={{
                        cursor: "pointer",
                        backgroundColor: selectedCommodity === commodity.symbol ? "rgba(0, 136, 254, 0.05)" : "inherit",
                        "&:hover": { backgroundColor: "rgba(0, 0, 0, 0.02)" }
                      }}
                    >
                      <TableCell sx={{ fontWeight: 600 }}>{commodity.symbol}</TableCell>
                      <TableCell>{commodity.name}</TableCell>
                      <TableCell>
                        <Chip label={category?.category || "Unknown"} size="small" variant="outlined" />
                      </TableCell>
                      <TableCell align="right">{formatCurrency(commodity.price)}</TableCell>
                      <TableCell align="right" sx={{ color: changeColor, fontWeight: 600 }}>
                        {formatPercentage(commodity.change_percent || 0)}
                      </TableCell>
                      <TableCell align="right">{formatCurrency(commodity.high_52w)} / {formatCurrency(commodity.low_52w)}</TableCell>
                      <TableCell align="center"><Chip label={signal} size="small" color={signalColor} variant="outlined" /></TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        </Card>
      </TabPanel>

      {/* TAB 1: TECHNICALS */}
      <TabPanel value={tabValue} index={1}>
        {selectedCommodityData ? (
          <Grid container spacing={3}>
            <Grid item xs={12}>
              <Card>
                <CardHeader title={`${selectedCommodityData.name} (${selectedCommodityData.symbol})`} subheader={`${selectedCommodityCategory?.category || "Unknown"} • ${selectedCommodityCategory?.exchange || "Unknown"}`} />
                <CardContent>
                  <Grid container spacing={2}>
                    {[{label: "Current Price", value: formatCurrency(selectedCommodityData.price)},
                      {label: "24h Change", value: formatPercentage(selectedCommodityData.change_percent)},
                      {label: "52W High", value: formatCurrency(selectedCommodityData.high_52w)},
                      {label: "52W Low", value: formatCurrency(selectedCommodityData.low_52w)}
                    ].map(({label, value}) => (
                      <Grid item xs={6} key={label}>
                        <Typography color="textSecondary" variant="caption">{label}</Typography>
                        <Typography variant="h6">{value}</Typography>
                      </Grid>
                    ))}
                  </Grid>
                </CardContent>
              </Card>
            </Grid>

            {technicalsQuery.data && technicalsQuery.data.length > 0 && (
              <>
                <Grid item xs={12} md={6}>
                  <Card>
                    <CardHeader title="RSI (14)" subheader="Overbought >70, Oversold <30" />
                    <CardContent>
                      <ResponsiveContainer width="100%" height={250}>
                        <LineChart data={technicalsQuery.data}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="date" />
                          <YAxis domain={[0, 100]} />
                          <Tooltip />
                          <ReferenceLine y={70} stroke="#ff7300" label="Overbought" />
                          <ReferenceLine y={30} stroke="#82ca9d" label="Oversold" />
                          <Line type="monotone" dataKey="rsi" stroke="#8884d8" isAnimationActive={false} />
                        </LineChart>
                      </ResponsiveContainer>
                    </CardContent>
                  </Card>
                </Grid>

                <Grid item xs={12} md={6}>
                  <Card>
                    <CardHeader title="MACD" subheader="Signal line crossovers" />
                    <CardContent>
                      <ResponsiveContainer width="100%" height={250}>
                        <ComposedChart data={technicalsQuery.data}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="date" />
                          <YAxis />
                          <Tooltip />
                          <Bar dataKey="macdHist" fill="#8884d8" radius={[2, 2, 0, 0]}>
                            {technicalsQuery.data.map((entry, index) => (
                              <Cell key={`cell-${index}`} fill={entry.macdHist > 0 ? "#10b981" : "#ef4444"} />
                            ))}
                          </Bar>
                          <Line type="monotone" dataKey="macd" stroke="#ffc658" isAnimationActive={false} />
                          <Line type="monotone" dataKey="macdSignal" stroke="#82ca9d" isAnimationActive={false} />
                        </ComposedChart>
                      </ResponsiveContainer>
                    </CardContent>
                  </Card>
                </Grid>

                <Grid item xs={12}>
                  <Card>
                    <CardHeader title="Price & Moving Averages" subheader="SMA 20 / 50 / 200" />
                    <CardContent>
                      <ResponsiveContainer width="100%" height={300}>
                        <LineChart data={technicalsQuery.data}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="date" />
                          <YAxis />
                          <Tooltip />
                          <Legend />
                          <Line type="monotone" dataKey="sma20" stroke="#ff7300" strokeWidth={2} isAnimationActive={false} />
                          <Line type="monotone" dataKey="sma50" stroke="#8884d8" strokeWidth={2} isAnimationActive={false} />
                          <Line type="monotone" dataKey="sma200" stroke="#82ca9d" strokeWidth={2} isAnimationActive={false} />
                        </LineChart>
                      </ResponsiveContainer>
                    </CardContent>
                  </Card>
                </Grid>
              </>
            )}
          </Grid>
        ) : (
          <Alert severity="info">Select a commodity to view technicals</Alert>
        )}
      </TabPanel>

      {/* TAB 2: MACRO DRIVERS */}
      <TabPanel value={tabValue} index={2}>
        <Grid container spacing={3}>
          {macroQuery.data && macroQuery.data.length > 0 ? (
            macroQuery.data.map((series) => (
              <Grid item xs={12} md={6} key={series.seriesId}>
                <Card>
                  <CardHeader title={series.seriesName} subheader={`Latest: ${series.history[series.history.length - 1]?.value || "—"}`} />
                  <CardContent>
                    <ResponsiveContainer width="100%" height={200}>
                      <LineChart data={series.history}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" />
                        <YAxis />
                        <Tooltip />
                        <Line type="monotone" dataKey="value" stroke="#8884d8" isAnimationActive={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>
            ))
          ) : (
            <Grid item xs={12}><Alert severity="info">Macro driver data loading...</Alert></Grid>
          )}
        </Grid>
      </TabPanel>

      {/* TAB 3: EVENTS CALENDAR */}
      <TabPanel value={tabValue} index={3}>
        <Card>
          <CardHeader title="Economic Event Calendar" subheader="Upcoming reports and releases" />
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow sx={{ backgroundColor: "#f5f5f5" }}>
                  <TableCell sx={{ fontWeight: 600 }}>Date & Time</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Event</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Type</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Description</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Impact</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {eventsQuery.data && eventsQuery.data.length > 0 ? (
                  eventsQuery.data.slice(0, 20).map((event, idx) => (
                    <TableRow key={idx}>
                      <TableCell>{new Date(event.date).toLocaleString()}</TableCell>
                      <TableCell sx={{ fontWeight: 600 }}>{event.name}</TableCell>
                      <TableCell><Chip label={event.type} size="small" /></TableCell>
                      <TableCell>{event.description}</TableCell>
                      <TableCell>
                        <Chip
                          label={event.impact}
                          size="small"
                          color={event.impact === "CRITICAL" ? "error" : event.impact === "HIGH" ? "warning" : "default"}
                        />
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow><TableCell colSpan={5}><Alert severity="info">No upcoming events</Alert></TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Card>
      </TabPanel>

      {/* TAB 4: SEASONALITY */}
      <TabPanel value={tabValue} index={4}>
        {seasonalityQuery.data && seasonalityQuery.data.length > 0 ? (
          <Card>
            <CardHeader title={`${selectedCommodityData?.name} Seasonality`} subheader="Average monthly performance" />
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={seasonalityQuery.data}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="monthName" />
                  <YAxis label={{ value: "Avg Return (%)", angle: -90, position: "insideLeft" }} />
                  <Tooltip />
                  <Bar dataKey="avgReturn" radius={[4, 4, 0, 0]}>
                    {seasonalityQuery.data.map((entry, idx) => (
                      <Cell key={`cell-${idx}`} fill={entry.avgReturn > 0 ? "#10b981" : "#ef4444"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        ) : (
          <Alert severity="info">Seasonality data not available for this commodity</Alert>
        )}
      </TabPanel>
    </Container>
  );
}

export default CommoditiesAnalysis;
