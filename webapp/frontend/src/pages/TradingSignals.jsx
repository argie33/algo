import React, { useState } from "react";
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
  TablePagination,
  TableRow,
  TextField,
  Tooltip,
  Typography,
  useTheme,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  Remove,
  MoreVert,
  Info,
} from "@mui/icons-material";
import TradingSignal from "../components/TradingSignal";
import { getTradingSignalsDaily } from "../services/api";

function TradingSignals() {
  const theme = useTheme();
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [filterSymbol, setFilterSymbol] = useState("");

  // Fetch trading signals
  const { data: signalsData, isLoading, error } = useQuery({
    queryKey: ["tradingSignals"],
    queryFn: () => getTradingSignalsDaily({ limit: 500 }),
    staleTime: 60000,
  });

  if (isLoading) {
    return (
      <Container maxWidth="xl">
        <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
          <CircularProgress size={40} />
        </Box>
      </Container>
    );
  }

  if (error) {
    return (
      <Container maxWidth="xl">
        <Card sx={{ mt: 2, backgroundColor: theme.palette.error.light }}>
          <CardContent>
            <Typography color="error" variant="h6">
              Error loading trading signals: {error?.message}
            </Typography>
          </CardContent>
        </Card>
      </Container>
    );
  }

  // Parse signals data
  const signals = Array.isArray(signalsData?.data) ? signalsData.data : [];

  // Filter by symbol
  const filteredSignals = filterSymbol
    ? signals.filter((s) =>
        s.symbol?.toUpperCase().includes(filterSymbol.toUpperCase())
      )
    : signals;

  // Paginate
  const paginatedSignals = filteredSignals.slice(
    page * rowsPerPage,
    (page + 1) * rowsPerPage
  );

  const handleChangePage = (event, newPage) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  // Signal type distribution
  const signalCounts = {
    BUY: signals.filter((s) => s.signal?.toUpperCase() === "BUY").length,
    SELL: signals.filter((s) => s.signal?.toUpperCase() === "SELL").length,
    HOLD: signals.filter((s) => s.signal?.toUpperCase() === "HOLD").length,
  };

  return (
    <Container maxWidth="xl">
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" sx={{ mb: 1, fontWeight: 600 }}>
          Trading Signals
        </Typography>
        <Typography color="textSecondary" variant="body1">
          Real-time trading signal analysis and recommendations
        </Typography>
      </Box>

      {/* Signal Summary Cards */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        {Object.entries(signalCounts).map(([signal, count]) => {
          let color = "info";
          let icon = <Remove />;
          if (signal === "BUY") {
            color = "success";
            icon = <TrendingUp />;
          } else if (signal === "SELL") {
            color = "error";
            icon = <TrendingDown />;
          }

          return (
            <Grid item xs={12} sm={6} md={4} key={signal}>
              <Card>
                <CardContent>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                    <Box
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        width: 48,
                        height: 48,
                        borderRadius: "50%",
                        backgroundColor: theme.palette[color].light,
                        color: theme.palette[color].dark,
                      }}
                    >
                      {icon}
                    </Box>
                    <Box sx={{ flex: 1 }}>
                      <Typography color="textSecondary" variant="caption">
                        {signal} Signals
                      </Typography>
                      <Typography variant="h6" sx={{ fontWeight: 600 }}>
                        {count}
                      </Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          );
        })}
      </Grid>

      {/* Signals Table */}
      <Paper>
        <Box sx={{ p: 2, display: "flex", gap: 2, alignItems: "center" }}>
          <TextField
            placeholder="Filter by symbol (e.g., AAPL)..."
            size="small"
            value={filterSymbol}
            onChange={(e) => {
              setFilterSymbol(e.target.value);
              setPage(0);
            }}
            sx={{ minWidth: 250 }}
          />
          <Typography color="textSecondary" variant="body2">
            {filteredSignals.length} of {signals.length} signals
          </Typography>
        </Box>

        {paginatedSignals.length === 0 ? (
          <Box sx={{ p: 4, textAlign: "center" }}>
            <Typography color="textSecondary">No signals found</Typography>
          </Box>
        ) : (
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ backgroundColor: theme.palette.background.alt }}>
                  <TableCell sx={{ fontWeight: 600 }}>Symbol</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Signal</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Confidence</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Entry</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Target</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Stop Loss</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Date</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {paginatedSignals.map((signal, idx) => (
                  <TableRow key={idx} hover>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {signal.symbol}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <TradingSignal
                        signal={signal.signal}
                        confidence={signal.confidence || 0.75}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>
                      <Tooltip title={`${((signal.confidence || 0.75) * 100).toFixed(1)}% confidence`}>
                        <Chip
                          label={`${((signal.confidence || 0.75) * 100).toFixed(0)}%`}
                          size="small"
                          variant="outlined"
                        />
                      </Tooltip>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {signal.entry_price ? `$${signal.entry_price.toFixed(2)}` : "—"}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography
                        variant="body2"
                        sx={{
                          color: signal.target_price ? theme.palette.success.main : "inherit",
                        }}
                      >
                        {signal.target_price ? `$${signal.target_price.toFixed(2)}` : "—"}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography
                        variant="body2"
                        sx={{
                          color: signal.stop_loss ? theme.palette.error.main : "inherit",
                        }}
                      >
                        {signal.stop_loss ? `$${signal.stop_loss.toFixed(2)}` : "—"}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color="textSecondary">
                        {signal.date
                          ? new Date(signal.date).toLocaleDateString()
                          : "—"}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}

        <TablePagination
          rowsPerPageOptions={[10, 25, 50, 100]}
          component="div"
          count={filteredSignals.length}
          rowsPerPage={rowsPerPage}
          page={page}
          onPageChange={handleChangePage}
          onRowsPerPageChange={handleChangeRowsPerPage}
        />
      </Paper>

      {/* Info Card */}
      <Card sx={{ mt: 4, backgroundColor: theme.palette.info.light }}>
        <CardHeader
          avatar={<Info />}
          title="About Trading Signals"
          titleTypographyProps={{ variant: "subtitle1" }}
        />
        <CardContent>
          <Typography variant="body2" color="textSecondary">
            Trading signals are generated based on technical analysis, machine learning models,
            and market sentiment. Confidence levels indicate the probability of signal accuracy.
            Always conduct your own due diligence before making trading decisions.
          </Typography>
        </CardContent>
      </Card>
    </Container>
  );
}

export default TradingSignals;
