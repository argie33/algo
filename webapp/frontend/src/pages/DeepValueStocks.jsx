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
  Dialog,
  DialogTitle,
  DialogContent,
  Divider,
} from "@mui/material";
import {
  TrendingUp,
  Download as DownloadIcon,
  Info as InfoIcon,
} from "@mui/icons-material";
import api from "../services/api";

const DeepValueStocks = () => {
  const [stocks, setStocks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [minScore, setMinScore] = useState(0);
  const [selectedStock, setSelectedStock] = useState(null);
  const [infoOpen, setInfoOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(100);

  useEffect(() => {
    fetchDeepValueStocks();
  }, []);

  const fetchDeepValueStocks = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await api.get("/api/stocks/deep-value?limit=600");
      const result = response.data;
      let stocksData = result.items || result.data?.stocks || result.data || result;
      if (!Array.isArray(stocksData)) stocksData = [];
      setStocks(stocksData.map(s => ({
        ...s,
        deep_value_score: parseFloat(s.deep_value_score) || 0,
        current_price: s.current_price != null ? parseFloat(s.current_price) : null,
        trailing_pe: s.trailing_pe != null ? parseFloat(s.trailing_pe) : null,
        price_to_book: s.price_to_book != null ? parseFloat(s.price_to_book) : null,
        price_to_sales: s.price_to_sales != null ? parseFloat(s.price_to_sales) : null,
        roe_pct: s.roe_pct != null ? parseFloat(s.roe_pct) : null,
        op_margin_pct: s.op_margin_pct != null ? parseFloat(s.op_margin_pct) : null,
        gross_margin_pct: s.gross_margin_pct != null ? parseFloat(s.gross_margin_pct) : null,
        net_margin_pct: s.net_margin_pct != null ? parseFloat(s.net_margin_pct) : null,
        roa_pct: s.roa_pct != null ? parseFloat(s.roa_pct) : null,
        ev_to_ebitda: s.ev_to_ebitda != null ? parseFloat(s.ev_to_ebitda) : null,
        peg_ratio: s.peg_ratio != null ? parseFloat(s.peg_ratio) : null,
        dividend_yield: s.dividend_yield != null ? parseFloat(s.dividend_yield) : null,
        debt_to_equity: s.debt_to_equity != null ? parseFloat(s.debt_to_equity) : null,
        current_ratio: s.current_ratio != null ? parseFloat(s.current_ratio) : null,
      })));
    } catch (err) {
      console.error("Error fetching deep value stocks:", err);
      setError(err.message || "Failed to load deep value stocks");
      setStocks([]);
    } finally {
      setLoading(false);
    }
  };

  const filtered = stocks.filter(s => s.deep_value_score >= minScore);

  const fmt = (v, dec = 2) => v != null ? parseFloat(v).toFixed(dec) : "—";
  const fmtPct = (v, dec = 1) => v != null ? `${parseFloat(v).toFixed(dec)}%` : "—";

  const avg = (arr, key) => {
    const vals = arr.map(s => s[key]).filter(v => v != null && !isNaN(v));
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  };

  const scoreColor = (score) => {
    if (score >= 80) return "#4caf50";
    if (score >= 65) return "#2196f3";
    if (score >= 50) return "#ff9800";
    return "#f44336";
  };

  const StockDetailDialog = ({ stock, open, onClose }) => {
    if (!stock) return null;
    return (
      <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>
          {stock.symbol} {stock.company_name ? `— ${stock.company_name}` : ""}
        </DialogTitle>
        <DialogContent>
          <Box sx={{ mb: 1, display: "flex", gap: 1, flexWrap: "wrap" }}>
            <Chip label={`Deep Value Score: ${fmt(stock.deep_value_score, 1)}`}
              sx={{ backgroundColor: scoreColor(stock.deep_value_score), color: "#fff", fontWeight: 700 }} />
            {stock.current_price != null && (
              <Chip label={`Price: $${stock.current_price.toFixed(2)}`} variant="outlined" />
            )}
          </Box>
          {stock.sector && <Typography variant="caption" color="text.secondary">{stock.sector} • {stock.industry}</Typography>}
          <Divider sx={{ my: 2 }} />
          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>Valuation</Typography>
          <Grid container spacing={1} sx={{ mb: 2 }}>
            {[
              ["P/E Ratio", fmt(stock.trailing_pe)],
              ["P/B Ratio", fmt(stock.price_to_book)],
              ["P/S Ratio", fmt(stock.price_to_sales)],
              ["EV/EBITDA", fmt(stock.ev_to_ebitda)],
              ["PEG Ratio", fmt(stock.peg_ratio)],
              ["Dividend Yield", fmtPct(stock.dividend_yield)],
            ].map(([label, val]) => (
              <Grid item xs={6} key={label}>
                <Typography variant="caption" color="text.secondary">{label}</Typography>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>{val}</Typography>
              </Grid>
            ))}
          </Grid>
          <Divider sx={{ my: 2 }} />
          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>Quality & Profitability</Typography>
          <Grid container spacing={1} sx={{ mb: 2 }}>
            {[
              ["ROE", fmtPct(stock.roe_pct)],
              ["ROA", fmtPct(stock.roa_pct)],
              ["Gross Margin", fmtPct(stock.gross_margin_pct)],
              ["Operating Margin", fmtPct(stock.op_margin_pct)],
              ["Net Margin", fmtPct(stock.net_margin_pct)],
              ["Debt / Equity", fmt(stock.debt_to_equity)],
              ["Current Ratio", fmt(stock.current_ratio)],
            ].map(([label, val]) => (
              <Grid item xs={6} key={label}>
                <Typography variant="caption" color="text.secondary">{label}</Typography>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>{val}</Typography>
              </Grid>
            ))}
          </Grid>
          <Box sx={{ p: 2, backgroundColor: "#e8f5e9", borderRadius: 1 }}>
            <Typography variant="body2" sx={{ fontWeight: 600, color: "#2e7d32" }}>
              Score formula: PE percentile (25%) + PB percentile (15%) + ROE percentile (35%) + Operating Margin percentile (25%)
            </Typography>
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

  const paginated = filtered.slice(page * rowsPerPage, (page + 1) * rowsPerPage);
  const avgPE = avg(filtered, "trailing_pe");
  const avgROE = avg(filtered, "roe_pct");
  const avgMargin = avg(filtered, "op_margin_pct");

  return (
    <Box sx={{ padding: 3 }}>
      <Box sx={{ mb: 4 }}>
        <Typography variant="h3" sx={{ fontWeight: 700, mb: 1 }}>
          Deep Value Stocks
        </Typography>
        <Typography variant="body1" color="textSecondary" sx={{ maxWidth: 700 }}>
          Stocks ranked by a deep value formula: cheap valuations (low P/E, P/B) combined with strong fundamentals
          (high ROE, strong operating margins). Score is a percentile rank across all qualifying stocks — 100 = best.
        </Typography>
      </Box>

      <Grid container spacing={2} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>Qualifying Stocks</Typography>
              <Typography variant="h4" sx={{ fontWeight: 700, color: "#4caf50" }}>{filtered.length}</Typography>
              <Typography variant="caption" color="textSecondary">of {stocks.length} total with full data</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>Avg P/E Ratio</Typography>
              <Typography variant="h4" sx={{ fontWeight: 700 }}>{avgPE != null ? avgPE.toFixed(1) : "—"}</Typography>
              <Typography variant="caption" color="textSecondary">Among filtered results</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>Avg ROE</Typography>
              <Typography variant="h4" sx={{ fontWeight: 700 }}>{avgROE != null ? avgROE.toFixed(1) + "%" : "—"}</Typography>
              <Typography variant="caption" color="textSecondary">Return on equity</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>Avg Op. Margin</Typography>
              <Typography variant="h4" sx={{ fontWeight: 700 }}>{avgMargin != null ? avgMargin.toFixed(1) + "%" : "—"}</Typography>
              <Typography variant="caption" color="textSecondary">Operating profitability</Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Paper sx={{ p: 2, mb: 3 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={6} md={3}>
            <TextField
              select
              fullWidth
              label="Minimum Deep Value Score"
              value={minScore}
              onChange={(e) => { setMinScore(Number(e.target.value)); setPage(0); }}
              size="small"
            >
              <MenuItem value={0}>All Stocks</MenuItem>
              <MenuItem value={50}>Good Value (50+)</MenuItem>
              <MenuItem value={65}>Strong Value (65+)</MenuItem>
              <MenuItem value={80}>Deep Value (80+)</MenuItem>
            </TextField>
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <TextField
              select
              fullWidth
              label="Rows per page"
              value={rowsPerPage}
              onChange={(e) => { setRowsPerPage(Number(e.target.value)); setPage(0); }}
              size="small"
            >
              <MenuItem value={50}>50</MenuItem>
              <MenuItem value={100}>100</MenuItem>
              <MenuItem value={200}>200</MenuItem>
              <MenuItem value={500}>500</MenuItem>
            </TextField>
          </Grid>
          <Grid item xs={12} sm={6} md={4}>
            <Button
              variant="outlined"
              fullWidth
              startIcon={<DownloadIcon />}
              onClick={() => {
                const csv = [
                  ["Symbol", "Company", "Sector", "Industry", "P/E", "P/B", "P/S", "EV/EBITDA", "ROE%", "Gross M%", "Op.M%", "Net M%", "Div Yield%", "Debt/Equity", "Deep Value Score"],
                  ...filtered.map(s => [
                    s.symbol,
                    s.company_name || "",
                    s.sector || "",
                    s.industry || "",
                    fmt(s.trailing_pe),
                    fmt(s.price_to_book),
                    fmt(s.price_to_sales),
                    fmt(s.ev_to_ebitda),
                    fmtPct(s.roe_pct),
                    fmtPct(s.gross_margin_pct),
                    fmtPct(s.op_margin_pct),
                    fmtPct(s.net_margin_pct),
                    s.dividend_yield != null ? `${parseFloat(s.dividend_yield).toFixed(2)}%` : "—",
                    fmt(s.debt_to_equity),
                    fmt(s.deep_value_score, 1),
                  ]),
                ].map(r => r.join(",")).join("\n");
                const blob = new Blob([csv], { type: "text/csv" });
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = "deep_value_stocks.csv";
                a.click();
              }}
            >
              Export CSV
            </Button>
          </Grid>
          <Grid item xs={12} sm={6} md={4}>
            <Button variant="outlined" fullWidth startIcon={<InfoIcon />} onClick={() => setInfoOpen(true)}>
              How It Works
            </Button>
          </Grid>
        </Grid>
      </Paper>

      {filtered.length === 0 ? (
        <Alert severity="info">No stocks match your criteria. Try lowering the minimum score.</Alert>
      ) : (
        <>
          <Box sx={{ mb: 1, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <Typography variant="body2" color="text.secondary">
              Showing {page * rowsPerPage + 1}–{Math.min((page + 1) * rowsPerPage, filtered.length)} of {filtered.length} stocks
            </Typography>
            <Box sx={{ display: "flex", gap: 1 }}>
              <Button size="small" variant="outlined" disabled={page === 0} onClick={() => setPage(p => p - 1)}>Prev</Button>
              <Button size="small" variant="outlined" disabled={(page + 1) * rowsPerPage >= filtered.length} onClick={() => setPage(p => p + 1)}>Next</Button>
            </Box>
          </Box>
          <TableContainer component={Paper} sx={{ overflowX: "auto" }}>
            <Table size="small">
              <TableHead sx={{ backgroundColor: "#f5f5f5" }}>
                <TableRow>
                  <TableCell sx={{ fontWeight: 700, position: "sticky", left: 0, zIndex: 2, backgroundColor: "#f5f5f5" }}>Symbol</TableCell>
                  <TableCell sx={{ fontWeight: 700, minWidth: 170 }}>Company</TableCell>
                  <TableCell sx={{ fontWeight: 700, minWidth: 120 }}>Sector</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>Price</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>P/E</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>P/B</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>P/S</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>EV/EBITDA</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>ROE%</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>Gross M%</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>Op.M%</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>Net M%</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>Div%</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>Debt/Eq</TableCell>
                  <TableCell align="center" sx={{ fontWeight: 700 }}>Score</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {paginated.map((stock, idx) => {
                  const globalIdx = page * rowsPerPage + idx;
                  return (
                    <TableRow
                      key={stock.symbol}
                      hover
                      sx={{ cursor: "pointer", backgroundColor: globalIdx === 0 ? "#f0f4ff" : undefined }}
                      onClick={() => { setSelectedStock(stock); setDetailOpen(true); }}
                    >
                      <TableCell sx={{
                        fontWeight: 700, fontSize: "1.05em", color: globalIdx === 0 ? "#1976d2" : "inherit",
                        position: "sticky", left: 0, backgroundColor: idx % 2 === 0 ? (globalIdx === 0 ? "#f0f4ff" : "#fff") : "#fafafa", zIndex: 1
                      }}>
                        {globalIdx === 0 && <TrendingUp sx={{ fontSize: 14, mr: 0.5, verticalAlign: "middle", color: "#4caf50" }} />}
                        {stock.symbol}
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" sx={{ fontWeight: 500, fontSize: "0.8rem" }}>{stock.company_name || "—"}</Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>{stock.sector || "—"}</Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.68rem", opacity: 0.8 }}>{stock.industry || ""}</Typography>
                      </TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem", fontWeight: 600 }}>
                        {stock.current_price != null ? `$${stock.current_price.toFixed(2)}` : "—"}
                      </TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem" }}>{fmt(stock.trailing_pe)}</TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem" }}>{fmt(stock.price_to_book)}</TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem" }}>{fmt(stock.price_to_sales)}</TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem" }}>{fmt(stock.ev_to_ebitda)}</TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem", color: stock.roe_pct != null && stock.roe_pct > 20 ? "#2e7d32" : "inherit" }}>
                        {fmtPct(stock.roe_pct)}
                      </TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem" }}>{fmtPct(stock.gross_margin_pct)}</TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem" }}>{fmtPct(stock.op_margin_pct)}</TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem" }}>{fmtPct(stock.net_margin_pct)}</TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem", color: stock.dividend_yield != null && stock.dividend_yield > 2 ? "#1565c0" : "inherit" }}>
                        {stock.dividend_yield != null ? `${parseFloat(stock.dividend_yield).toFixed(2)}%` : "—"}
                      </TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem", color: stock.debt_to_equity != null && stock.debt_to_equity > 2 ? "#c62828" : "inherit" }}>
                        {fmt(stock.debt_to_equity)}
                      </TableCell>
                      <TableCell align="center">
                        <Chip
                          label={fmt(stock.deep_value_score, 1)}
                          size="small"
                          sx={{ backgroundColor: scoreColor(stock.deep_value_score), color: "#fff", fontWeight: 700, minWidth: 50 }}
                        />
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
          <Box sx={{ mt: 1, display: "flex", justifyContent: "flex-end", gap: 1 }}>
            <Button size="small" variant="outlined" disabled={page === 0} onClick={() => { setPage(p => p - 1); window.scrollTo({ top: 0, behavior: "smooth" }); }}>Prev</Button>
            <Button size="small" variant="outlined" disabled={(page + 1) * rowsPerPage >= filtered.length} onClick={() => { setPage(p => p + 1); window.scrollTo({ top: 0, behavior: "smooth" }); }}>Next</Button>
          </Box>
        </>
      )}

      <StockDetailDialog stock={selectedStock} open={detailOpen} onClose={() => setDetailOpen(false)} />

      <Dialog open={infoOpen} onClose={() => setInfoOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>How Deep Value Score Is Calculated</DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 2 }}>
            {[
              ["PE Percentile (25%)", "Stocks with low P/E ratios rank higher — cheaper relative to earnings"],
              ["PB Percentile (15%)", "Stocks with low P/B ratios rank higher — trading closer to book value"],
              ["ROE Percentile (35%)", "Stocks with high ROE rank higher — more efficient use of equity capital"],
              ["Op. Margin Percentile (25%)", "Stocks with high operating margins rank higher — more profitable businesses"],
            ].map(([title, desc]) => (
              <Box sx={{ mb: 2 }} key={title}>
                <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5 }}>{title}</Typography>
                <Typography variant="body2" color="textSecondary">{desc}</Typography>
              </Box>
            ))}
            <Box sx={{ p: 2, backgroundColor: "#e8f5e9", borderRadius: 1 }}>
              <Typography variant="body2" sx={{ fontWeight: 600, color: "#2e7d32" }}>
                Each metric is ranked as a percentile (0–100) across all qualifying stocks. A score of 80+ means the
                stock is in the top 20% for the combined cheap-valuation + strong-fundamentals combination.
              </Typography>
            </Box>
          </Box>
        </DialogContent>
      </Dialog>
    </Box>
  );
};

export default DeepValueStocks;
