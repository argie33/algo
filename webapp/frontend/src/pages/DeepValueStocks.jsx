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
  TableSortLabel,
} from "@mui/material";
import {
  TrendingUp,
  Download as DownloadIcon,
  Info as InfoIcon,
  Verified as VerifiedIcon,
} from "@mui/icons-material";
import api from "../services/api";

const DeepValueStocks = () => {
  const [stocks, setStocks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedStock, setSelectedStock] = useState(null);
  const [infoOpen, setInfoOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(100);
  const [sortBy, setSortBy] = useState("generational_score");
  const [sortOrder, setSortOrder] = useState("desc");

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
        generational_score: parseFloat(s.generational_score) || 0,
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
        historical_avg_pe: s.historical_avg_pe != null ? parseFloat(s.historical_avg_pe) : null,
        historical_avg_pb: s.historical_avg_pb != null ? parseFloat(s.historical_avg_pb) : null,
        sector_median_pe: s.sector_median_pe != null ? parseFloat(s.sector_median_pe) : null,
        market_median_pe: s.market_median_pe != null ? parseFloat(s.market_median_pe) : null,
        discount_vs_historical_pe_pct: s.discount_vs_historical_pe_pct != null ? parseFloat(s.discount_vs_historical_pe_pct) : null,
        discount_vs_historical_pb_pct: s.discount_vs_historical_pb_pct != null ? parseFloat(s.discount_vs_historical_pb_pct) : null,
        discount_vs_sector_pe_pct: s.discount_vs_sector_pe_pct != null ? parseFloat(s.discount_vs_sector_pe_pct) : null,
        discount_vs_market_pe_pct: s.discount_vs_market_pe_pct != null ? parseFloat(s.discount_vs_market_pe_pct) : null,
      })));
    } catch (err) {
      console.error("Error fetching deep value stocks:", err);
      setError(err.message || "Failed to load deep value stocks");
      setStocks([]);
    } finally {
      setLoading(false);
    }
  };

  const sorted = [...stocks].sort((a, b) => {
    const aVal = a[sortBy];
    const bVal = b[sortBy];
    if (aVal == null) return 1;
    if (bVal == null) return -1;
    const cmp = aVal > bVal ? 1 : aVal < bVal ? -1 : 0;
    return sortOrder === "desc" ? -cmp : cmp;
  });

  const handleSort = (field) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === "desc" ? "asc" : "desc");
    } else {
      setSortBy(field);
      setSortOrder("desc");
    }
    setPage(0);
  };

  const fmt = (v, dec = 2) => v != null ? parseFloat(v).toFixed(dec) : "—";
  const fmtPct = (v, dec = 1) => v != null ? `${parseFloat(v).toFixed(dec)}%` : "—";
  const fmtDiscount = (v) => v != null ? `${parseFloat(v).toFixed(1)}%` : "—";

  const avg = (arr, key) => {
    const vals = arr.map(s => s[key]).filter(v => v != null && !isNaN(v));
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  };

  const scoreColor = (score) => {
    if (score >= 80) return "#1b5e20";
    if (score >= 70) return "#2e7d32";
    if (score >= 60) return "#558b2f";
    if (score >= 50) return "#9ccc65";
    return "#f44336";
  };

  const qualityBadge = (tier) => {
    if (tier === "tier1") return { label: "Tier 1", color: "#1b5e20", bg: "#c8e6c9" };
    if (tier === "tier2") return { label: "Tier 2", color: "#2e7d32", bg: "#e8f5e9" };
    return { label: "Other", color: "#999", bg: "#f5f5f5" };
  };

  const StockDetailDialog = ({ stock, open, onClose }) => {
    if (!stock) return null;
    const tier = qualityBadge(stock.quality_rank);
    return (
      <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
        <DialogTitle sx={{ fontWeight: 700, display: "flex", alignItems: "center", gap: 1 }}>
          {stock.symbol} {stock.company_name ? `— ${stock.company_name}` : ""}
          {(stock.quality_rank === "tier1" || stock.quality_rank === "tier2") && (
            <VerifiedIcon sx={{ fontSize: 20, color: tier.color }} />
          )}
        </DialogTitle>
        <DialogContent>
          <Box sx={{ mb: 2, display: "flex", gap: 1, flexWrap: "wrap" }}>
            <Chip label={`Generational Score: ${fmt(stock.generational_score, 1)}`}
              sx={{ backgroundColor: scoreColor(stock.generational_score), color: "#fff", fontWeight: 700 }} />
            <Chip label={tier.label} sx={{ backgroundColor: tier.bg, color: tier.color, fontWeight: 700 }} />
            {stock.current_price != null && (
              <Chip label={`Price: $${stock.current_price.toFixed(2)}`} variant="outlined" />
            )}
          </Box>
          {stock.sector && <Typography variant="caption" color="text.secondary">{stock.sector} • {stock.industry}</Typography>}

          <Divider sx={{ my: 2 }} />
          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>Current Valuation</Typography>
          <Grid container spacing={1} sx={{ mb: 3 }}>
            {[
              ["P/E Ratio", fmt(stock.trailing_pe)],
              ["P/B Ratio", fmt(stock.price_to_book)],
              ["P/S Ratio", fmt(stock.price_to_sales)],
              ["EV/EBITDA", fmt(stock.ev_to_ebitda)],
              ["PEG Ratio", fmt(stock.peg_ratio)],
              ["Dividend Yield", fmtPct(stock.dividend_yield)],
            ].map(([label, val]) => (
              <Grid item xs={6} sm={4} key={label}>
                <Typography variant="caption" color="text.secondary">{label}</Typography>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>{val}</Typography>
              </Grid>
            ))}
          </Grid>

          <Divider sx={{ my: 2 }} />
          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>Historical & Peer Comparisons</Typography>
          <Grid container spacing={1} sx={{ mb: 3 }}>
            {[
              ["Historical Avg P/E", fmt(stock.historical_avg_pe)],
              ["Discount vs History (P/E)", fmtDiscount(stock.discount_vs_historical_pe_pct)],
              ["Sector Median P/E", fmt(stock.sector_median_pe)],
              ["Discount vs Sector (P/E)", fmtDiscount(stock.discount_vs_sector_pe_pct)],
              ["Market Median P/E", fmt(stock.market_median_pe)],
              ["Discount vs Market (P/E)", fmtDiscount(stock.discount_vs_market_pe_pct)],
            ].map(([label, val]) => (
              <Grid item xs={6} sm={4} key={label}>
                <Typography variant="caption" color="text.secondary">{label}</Typography>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>{val}</Typography>
              </Grid>
            ))}
          </Grid>

          <Divider sx={{ my: 2 }} />
          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>Quality & Profitability</Typography>
          <Grid container spacing={1} sx={{ mb: 3 }}>
            {[
              ["ROE", fmtPct(stock.roe_pct)],
              ["ROA", fmtPct(stock.roa_pct)],
              ["Gross Margin", fmtPct(stock.gross_margin_pct)],
              ["Operating Margin", fmtPct(stock.op_margin_pct)],
              ["Net Margin", fmtPct(stock.net_margin_pct)],
              ["Debt / Equity", fmt(stock.debt_to_equity)],
              ["Current Ratio", fmt(stock.current_ratio)],
            ].map(([label, val]) => (
              <Grid item xs={6} sm={4} key={label}>
                <Typography variant="caption" color="text.secondary">{label}</Typography>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>{val}</Typography>
              </Grid>
            ))}
          </Grid>

          <Box sx={{ p: 2, backgroundColor: "#e3f2fd", borderRadius: 1 }}>
            <Typography variant="body2" sx={{ fontWeight: 600, color: "#1565c0" }}>
              Generational Score combines: Valuation cheapness (PE, PB) with quality strength (ROE, margins) and financial fortress (liquidity, debt).
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

  const paginated = sorted.slice(page * rowsPerPage, (page + 1) * rowsPerPage);
  const avgGScore = avg(stocks, "generational_score");
  const avgPE = avg(stocks, "trailing_pe");
  const avgROE = avg(stocks, "roe_pct");

  return (
    <Box sx={{ padding: 3 }}>
      <Box sx={{ mb: 4 }}>
        <Typography variant="h3" sx={{ fontWeight: 700, mb: 1 }}>
          Generational Opportunities
        </Typography>
        <Typography variant="body1" color="textSecondary" sx={{ maxWidth: 800 }}>
          Tier-1 quality companies trading at anomaly prices. These stocks combine exceptional fundamentals (ROE &gt; 25%,
          margins &gt; 15%) with extreme valuations discounts relative to their own history, sector peers, and the market.
          This is where true generational wealth is built.
        </Typography>
      </Box>

      <Grid container spacing={2} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>Opportunities Found</Typography>
              <Typography variant="h4" sx={{ fontWeight: 700, color: "#1b5e20" }}>{stocks.length}</Typography>
              <Typography variant="caption" color="textSecondary">Tier 1 & 2 quality stocks</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>Avg Gen. Score</Typography>
              <Typography variant="h4" sx={{ fontWeight: 700, color: "#2e7d32" }}>{avgGScore != null ? avgGScore.toFixed(0) : "—"}</Typography>
              <Typography variant="caption" color="textSecondary">Anomaly strength (0-100)</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>Avg P/E</Typography>
              <Typography variant="h4" sx={{ fontWeight: 700 }}>{avgPE != null ? avgPE.toFixed(1) : "—"}</Typography>
              <Typography variant="caption" color="textSecondary">Valuation multiple</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>Avg ROE</Typography>
              <Typography variant="h4" sx={{ fontWeight: 700 }}>{avgROE != null ? avgROE.toFixed(1) + "%" : "—"}</Typography>
              <Typography variant="caption" color="textSecondary">Quality metric</Typography>
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
              label="Sort By"
              value={sortBy}
              onChange={(e) => { setSortBy(e.target.value); setPage(0); }}
              size="small"
            >
              <MenuItem value="generational_score">Generational Score</MenuItem>
              <MenuItem value="discount_vs_historical_pe_pct">Historical Discount</MenuItem>
              <MenuItem value="roe_pct">ROE</MenuItem>
              <MenuItem value="trailing_pe">P/E Ratio</MenuItem>
              <MenuItem value="op_margin_pct">Op. Margin</MenuItem>
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
              <MenuItem value={20}>20</MenuItem>
              <MenuItem value={50}>50</MenuItem>
              <MenuItem value={100}>100</MenuItem>
            </TextField>
          </Grid>
          <Grid item xs={12} sm={6} md={4}>
            <Button
              variant="outlined"
              fullWidth
              startIcon={<DownloadIcon />}
              onClick={() => {
                const csv = [
                  ["Symbol", "Company", "Quality", "Gen.Score", "P/E", "ROE%", "OpM%", "Hist Disc%", "Sector Disc%", "Market Disc%", "D/E", "Cur.Ratio"],
                  ...sorted.map(s => [
                    s.symbol,
                    s.company_name || "",
                    s.quality_rank || "",
                    fmt(s.generational_score, 1),
                    fmt(s.trailing_pe),
                    fmtPct(s.roe_pct),
                    fmtPct(s.op_margin_pct),
                    fmtDiscount(s.discount_vs_historical_pe_pct),
                    fmtDiscount(s.discount_vs_sector_pe_pct),
                    fmtDiscount(s.discount_vs_market_pe_pct),
                    fmt(s.debt_to_equity),
                    fmt(s.current_ratio),
                  ]),
                ].map(r => r.join(",")).join("\n");
                const blob = new Blob([csv], { type: "text/csv" });
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = "generational_opportunities.csv";
                a.click();
              }}
            >
              Export CSV
            </Button>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Button variant="outlined" fullWidth startIcon={<InfoIcon />} onClick={() => setInfoOpen(true)}>
              How It Works
            </Button>
          </Grid>
        </Grid>
      </Paper>

      {stocks.length === 0 ? (
        <Alert severity="info">No generational opportunities found at this time. Market conditions may need to create deeper dislocations.</Alert>
      ) : (
        <>
          <Box sx={{ mb: 1, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <Typography variant="body2" color="text.secondary">
              Showing {page * rowsPerPage + 1}–{Math.min((page + 1) * rowsPerPage, sorted.length)} of {sorted.length} opportunities
            </Typography>
            <Box sx={{ display: "flex", gap: 1 }}>
              <Button size="small" variant="outlined" disabled={page === 0} onClick={() => setPage(p => p - 1)}>Prev</Button>
              <Button size="small" variant="outlined" disabled={(page + 1) * rowsPerPage >= sorted.length} onClick={() => setPage(p => p + 1)}>Next</Button>
            </Box>
          </Box>
          <TableContainer component={Paper} sx={{ overflowX: "auto" }}>
            <Table size="small">
              <TableHead sx={{ backgroundColor: "#f5f5f5" }}>
                <TableRow>
                  <TableCell sx={{ fontWeight: 700, position: "sticky", left: 0, zIndex: 2, backgroundColor: "#f5f5f5" }}>Symbol</TableCell>
                  <TableCell sx={{ fontWeight: 700, minWidth: 180 }}>Company</TableCell>
                  <TableCell sx={{ fontWeight: 700, minWidth: 90 }}>Sector</TableCell>
                  <TableCell sx={{ fontWeight: 700, minWidth: 70 }}>Quality</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700, cursor: "pointer" }}>
                    <TableSortLabel active={sortBy === "trailing_pe"} direction={sortOrder === "asc" ? "asc" : "desc"} onClick={() => handleSort("trailing_pe")}>Price</TableSortLabel>
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700, cursor: "pointer" }}>
                    <TableSortLabel active={sortBy === "trailing_pe"} direction={sortOrder === "asc" ? "asc" : "desc"} onClick={() => handleSort("trailing_pe")}>P/E</TableSortLabel>
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700, cursor: "pointer" }}>
                    <TableSortLabel active={sortBy === "roe_pct"} direction={sortOrder === "asc" ? "asc" : "desc"} onClick={() => handleSort("roe_pct")}>ROE%</TableSortLabel>
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700, cursor: "pointer" }}>
                    <TableSortLabel active={sortBy === "op_margin_pct"} direction={sortOrder === "asc" ? "asc" : "desc"} onClick={() => handleSort("op_margin_pct")}>OpM%</TableSortLabel>
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>Hist Disc%</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>Sect Disc%</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>D/E</TableCell>
                  <TableCell align="center" sx={{ fontWeight: 700, cursor: "pointer" }}>
                    <TableSortLabel active={sortBy === "generational_score"} direction={sortOrder === "asc" ? "asc" : "desc"} onClick={() => handleSort("generational_score")}>Gen. Score</TableSortLabel>
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {paginated.map((stock, idx) => {
                  const globalIdx = page * rowsPerPage + idx;
                  const tier = qualityBadge(stock.quality_rank);
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
                      <TableCell sx={{ fontSize: "0.85rem" }}>
                        <Typography variant="body2" sx={{ fontWeight: 500, fontSize: "0.8rem" }}>{stock.company_name || "—"}</Typography>
                      </TableCell>
                      <TableCell sx={{ fontSize: "0.8rem" }}>
                        <Typography variant="caption" color="text.secondary">{stock.sector || "—"}</Typography>
                      </TableCell>
                      <TableCell sx={{ fontSize: "0.8rem" }}>
                        <Chip label={tier.label} size="small" sx={{ backgroundColor: tier.bg, color: tier.color, fontWeight: 700, minWidth: 50 }} />
                      </TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem", fontWeight: 600 }}>
                        {stock.current_price != null ? `$${stock.current_price.toFixed(2)}` : "—"}
                      </TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem" }}>{fmt(stock.trailing_pe)}</TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem", color: stock.roe_pct != null && stock.roe_pct > 25 ? "#1b5e20" : "inherit", fontWeight: stock.roe_pct > 25 ? 700 : 400 }}>
                        {fmtPct(stock.roe_pct)}
                      </TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem", color: stock.op_margin_pct != null && stock.op_margin_pct > 15 ? "#1b5e20" : "inherit", fontWeight: stock.op_margin_pct > 15 ? 700 : 400 }}>
                        {fmtPct(stock.op_margin_pct)}
                      </TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem", color: stock.discount_vs_historical_pe_pct > 30 ? "#2e7d32" : "inherit", fontWeight: stock.discount_vs_historical_pe_pct > 30 ? 600 : 400 }}>
                        {fmtDiscount(stock.discount_vs_historical_pe_pct)}
                      </TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem", color: stock.discount_vs_sector_pe_pct > 20 ? "#558b2f" : "inherit" }}>
                        {fmtDiscount(stock.discount_vs_sector_pe_pct)}
                      </TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem", color: stock.debt_to_equity > 2 ? "#c62828" : "inherit" }}>
                        {fmt(stock.debt_to_equity)}
                      </TableCell>
                      <TableCell align="center">
                        <Chip
                          label={fmt(stock.generational_score, 0)}
                          size="small"
                          sx={{ backgroundColor: scoreColor(stock.generational_score), color: "#fff", fontWeight: 700, minWidth: 50 }}
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
            <Button size="small" variant="outlined" disabled={(page + 1) * rowsPerPage >= sorted.length} onClick={() => { setPage(p => p + 1); window.scrollTo({ top: 0, behavior: "smooth" }); }}>Next</Button>
          </Box>
        </>
      )}

      <StockDetailDialog stock={selectedStock} open={detailOpen} onClose={() => setDetailOpen(false)} />

      <Dialog open={infoOpen} onClose={() => setInfoOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>How Generational Opportunities Are Identified</DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 2 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>Quality Criteria (Tier 1 & 2 Only)</Typography>
            <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
              • <strong>Tier 1:</strong> ROE ≥ 25% + Operating Margin ≥ 15%<br/>
              • <strong>Tier 2:</strong> ROE ≥ 20% + Operating Margin ≥ 12%<br/>
              • Current Ratio &gt; 1.5 (financial fortress)<br/>
              • Debt/Equity &lt; 2.0 (sustainable leverage)
            </Typography>

            <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>Anomaly Detection (Valuation Mismatch)</Typography>
            <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
              Compares current valuation to three baselines:
            </Typography>
            <Box sx={{ ml: 2, mb: 2 }}>
              <Typography variant="body2" sx={{ mb: 1 }}>
                <strong>1. Historical (Its Own Past):</strong> Current P/E vs 3-year average P/E. Finding: Stock trading 40%+ below its historical average indicates temporary market panic.
              </Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>
                <strong>2. Sector Peers:</strong> Current P/E vs sector median. Finding: Similar quality company trading cheaper than sector suggests market misprice.
              </Typography>
              <Typography variant="body2">
                <strong>3. Overall Market:</strong> Current P/E vs S&P 500 median. Finding: Isolates stock-specific opportunity from market-wide valuation resets.
              </Typography>
            </Box>

            <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>Generational Score (0-100)</Typography>
            <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
              Combines:<br/>
              • PE Cheapness (30%) — How low is current P/E<br/>
              • PB Cheapness (20%) — How low is current P/B<br/>
              • ROE Quality (25%) — How strong is return on equity<br/>
              • Margin Quality (15%) — How strong are operating margins<br/>
              • Liquidity (10%) — Current ratio strength
            </Typography>

            <Box sx={{ p: 2, backgroundColor: "#fff3e0", borderRadius: 1 }}>
              <Typography variant="body2" sx={{ fontWeight: 600, color: "#e65100" }}>
                🎯 Result: A stock qualifies as a "generational opportunity" only when EXCEPTIONAL QUALITY meets ANOMALY PRICING.
                This combination is rare — perhaps 5-30 stocks across the entire market at any moment. These are where generational wealth compounds.
              </Typography>
            </Box>
          </Box>
        </DialogContent>
      </Dialog>
    </Box>
  );
};

export default DeepValueStocks;
