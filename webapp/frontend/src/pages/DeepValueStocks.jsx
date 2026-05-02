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
      const num = (v) => v != null ? parseFloat(v) : null;
      setStocks(stocksData.map(s => ({
        ...s,
        generational_score: parseFloat(s.generational_score) || 0,
        current_price: num(s.current_price),
        trailing_pe: num(s.trailing_pe),
        price_to_book: num(s.price_to_book),
        price_to_sales: num(s.price_to_sales),
        roe_pct: num(s.roe_pct),
        op_margin_pct: num(s.op_margin_pct),
        gross_margin_pct: num(s.gross_margin_pct),
        net_margin_pct: num(s.net_margin_pct),
        roa_pct: num(s.roa_pct),
        ev_to_ebitda: num(s.ev_to_ebitda),
        peg_ratio: num(s.peg_ratio),
        dividend_yield: num(s.dividend_yield),
        debt_to_equity: num(s.debt_to_equity),
        current_ratio: num(s.current_ratio),
        sector_median_pe: num(s.sector_median_pe),
        market_median_pe: num(s.market_median_pe),
        discount_vs_sector_pe_pct: num(s.discount_vs_sector_pe_pct),
        discount_vs_market_pe_pct: num(s.discount_vs_market_pe_pct),
        // Price action
        high_52w: num(s.high_52w),
        high_3y: num(s.high_3y),
        low_52w: num(s.low_52w),
        drop_from_52w_high_pct: num(s.drop_from_52w_high_pct),
        drop_from_3y_high_pct: num(s.drop_from_3y_high_pct),
        // DCF
        intrinsic_value_per_share: num(s.intrinsic_value_per_share),
        margin_of_safety_pct: num(s.margin_of_safety_pct),
        // Growth
        revenue_growth_3y_pct: num(s.revenue_growth_3y_pct),
        eps_growth_3y_pct: num(s.eps_growth_3y_pct),
        revenue_growth_yoy_pct: num(s.revenue_growth_yoy_pct),
        fcf_growth_yoy_pct: num(s.fcf_growth_yoy_pct),
        sustainable_growth_pct: num(s.sustainable_growth_pct),
        // Trends (trap detection)
        op_margin_trend_pp: num(s.op_margin_trend_pp),
        gross_margin_trend_pp: num(s.gross_margin_trend_pp),
        roe_trend_pp: num(s.roe_trend_pp),
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
          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1, color: "#1565c0" }}>📊 DCF / Intrinsic Value (Earnings Power Value)</Typography>
          <Grid container spacing={1} sx={{ mb: 3 }}>
            {[
              ["Current Price", stock.current_price != null ? `$${stock.current_price.toFixed(2)}` : "—"],
              ["Intrinsic Value (EPV)", stock.intrinsic_value_per_share != null ? `$${stock.intrinsic_value_per_share.toFixed(2)}` : "—"],
              ["Margin of Safety", stock.margin_of_safety_pct != null ? `${stock.margin_of_safety_pct.toFixed(1)}%` : "—", stock.margin_of_safety_pct >= 30 ? "#1b5e20" : stock.margin_of_safety_pct >= 0 ? "#558b2f" : "#c62828"],
            ].map(([label, val, color]) => (
              <Grid item xs={6} sm={4} key={label}>
                <Typography variant="caption" color="text.secondary">{label}</Typography>
                <Typography variant="body2" sx={{ fontWeight: 700, color: color || "inherit", fontSize: "1.05em" }}>{val}</Typography>
              </Grid>
            ))}
          </Grid>

          <Divider sx={{ my: 2 }} />
          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1, color: "#c62828" }}>🔥 Price Action / Fire Sale</Typography>
          <Grid container spacing={1} sx={{ mb: 3 }}>
            {[
              ["52-Week High", stock.high_52w != null ? `$${stock.high_52w.toFixed(2)}` : "—"],
              ["3-Year High", stock.high_3y != null ? `$${stock.high_3y.toFixed(2)}` : "—"],
              ["52-Week Low", stock.low_52w != null ? `$${stock.low_52w.toFixed(2)}` : "—"],
              ["Drop from 52w High", fmtPct(stock.drop_from_52w_high_pct), stock.drop_from_52w_high_pct >= 30 ? "#c62828" : "inherit"],
              ["Drop from 3y High", fmtPct(stock.drop_from_3y_high_pct), stock.drop_from_3y_high_pct >= 40 ? "#c62828" : "inherit"],
              ["Disc vs Sector P/E", fmtDiscount(stock.discount_vs_sector_pe_pct)],
              ["Disc vs Market P/E", fmtDiscount(stock.discount_vs_market_pe_pct)],
            ].map(([label, val, color]) => (
              <Grid item xs={6} sm={4} key={label}>
                <Typography variant="caption" color="text.secondary">{label}</Typography>
                <Typography variant="body2" sx={{ fontWeight: 600, color: color || "inherit" }}>{val}</Typography>
              </Grid>
            ))}
          </Grid>

          <Divider sx={{ my: 2 }} />
          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1, color: "#1b5e20" }}>💎 Quality & Profitability</Typography>
          <Grid container spacing={1} sx={{ mb: 3 }}>
            {[
              ["ROE", fmtPct(stock.roe_pct), stock.roe_pct >= 35 ? "#1b5e20" : "inherit"],
              ["ROA", fmtPct(stock.roa_pct)],
              ["Gross Margin", fmtPct(stock.gross_margin_pct), stock.gross_margin_pct >= 50 ? "#1b5e20" : "inherit"],
              ["Operating Margin", fmtPct(stock.op_margin_pct), stock.op_margin_pct >= 20 ? "#1b5e20" : "inherit"],
              ["Net Margin", fmtPct(stock.net_margin_pct)],
              ["Debt / Equity", fmt(stock.debt_to_equity), stock.debt_to_equity < 0.5 ? "#1b5e20" : "inherit"],
              ["Current Ratio", fmt(stock.current_ratio), stock.current_ratio > 2 ? "#1b5e20" : "inherit"],
            ].map(([label, val, color]) => (
              <Grid item xs={6} sm={4} key={label}>
                <Typography variant="caption" color="text.secondary">{label}</Typography>
                <Typography variant="body2" sx={{ fontWeight: 600, color: color || "inherit" }}>{val}</Typography>
              </Grid>
            ))}
          </Grid>

          <Divider sx={{ my: 2 }} />
          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1, color: "#2e7d32" }}>📈 Growth Engine</Typography>
          <Grid container spacing={1} sx={{ mb: 3 }}>
            {[
              ["Revenue 3Y CAGR", fmtPct(stock.revenue_growth_3y_pct), stock.revenue_growth_3y_pct >= 10 ? "#1b5e20" : "inherit"],
              ["EPS 3Y CAGR", fmtPct(stock.eps_growth_3y_pct), stock.eps_growth_3y_pct >= 15 ? "#1b5e20" : "inherit"],
              ["Revenue YoY", fmtPct(stock.revenue_growth_yoy_pct), stock.revenue_growth_yoy_pct >= 5 ? "#558b2f" : stock.revenue_growth_yoy_pct < 0 ? "#c62828" : "inherit"],
              ["FCF YoY", fmtPct(stock.fcf_growth_yoy_pct), stock.fcf_growth_yoy_pct >= 0 ? "#558b2f" : "#c62828"],
              ["Sustainable Growth", fmtPct(stock.sustainable_growth_pct)],
              ["PEG Ratio", fmt(stock.peg_ratio), stock.peg_ratio < 1 && stock.peg_ratio > 0 ? "#1b5e20" : "inherit"],
            ].map(([label, val, color]) => (
              <Grid item xs={6} sm={4} key={label}>
                <Typography variant="caption" color="text.secondary">{label}</Typography>
                <Typography variant="body2" sx={{ fontWeight: 600, color: color || "inherit" }}>{val}</Typography>
              </Grid>
            ))}
          </Grid>

          <Divider sx={{ my: 2 }} />
          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1, color: "#e65100" }}>⚠️ Trap Detection (Trends YoY)</Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
            Are quality metrics improving (✓) or declining (✗)? Negative = potential value trap warning.
          </Typography>
          <Grid container spacing={1} sx={{ mb: 3 }}>
            {[
              ["Op Margin Trend", stock.op_margin_trend_pp != null ? `${stock.op_margin_trend_pp >= 0 ? "+" : ""}${stock.op_margin_trend_pp.toFixed(2)}pp` : "—", stock.op_margin_trend_pp >= 0 ? "#1b5e20" : stock.op_margin_trend_pp > -3 ? "#f57c00" : "#c62828"],
              ["Gross Margin Trend", stock.gross_margin_trend_pp != null ? `${stock.gross_margin_trend_pp >= 0 ? "+" : ""}${stock.gross_margin_trend_pp.toFixed(2)}pp` : "—", stock.gross_margin_trend_pp >= 0 ? "#1b5e20" : stock.gross_margin_trend_pp > -3 ? "#f57c00" : "#c62828"],
              ["ROE Trend", stock.roe_trend_pp != null ? `${stock.roe_trend_pp >= 0 ? "+" : ""}${stock.roe_trend_pp.toFixed(2)}pp` : "—", stock.roe_trend_pp >= 0 ? "#1b5e20" : stock.roe_trend_pp > -10 ? "#f57c00" : "#c62828"],
            ].map(([label, val, color]) => (
              <Grid item xs={6} sm={4} key={label}>
                <Typography variant="caption" color="text.secondary">{label}</Typography>
                <Typography variant="body2" sx={{ fontWeight: 600, color: color || "inherit" }}>{val}</Typography>
              </Grid>
            ))}
          </Grid>
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
  const avgPE = avg(stocks, "trailing_pe");
  const avgROE = avg(stocks, "roe_pct");
  const avgMoS = avg(stocks, "margin_of_safety_pct");
  const avgDrop = avg(stocks, "drop_from_3y_high_pct");

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
          <Card sx={{ backgroundColor: "#e3f2fd" }}>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>Avg Margin of Safety</Typography>
              <Typography variant="h4" sx={{ fontWeight: 700, color: "#0d47a1" }}>{avgMoS != null ? avgMoS.toFixed(0) + "%" : "—"}</Typography>
              <Typography variant="caption" color="textSecondary">DCF intrinsic value vs price</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>Avg Drop from High</Typography>
              <Typography variant="h4" sx={{ fontWeight: 700, color: "#c62828" }}>{avgDrop != null ? avgDrop.toFixed(0) + "%" : "—"}</Typography>
              <Typography variant="caption" color="textSecondary">Fire sale magnitude (3y)</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>Avg ROE</Typography>
              <Typography variant="h4" sx={{ fontWeight: 700, color: "#1b5e20" }}>{avgROE != null ? avgROE.toFixed(1) + "%" : "—"}</Typography>
              <Typography variant="caption" color="textSecondary">Elite quality metric</Typography>
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
                  <TableCell align="right" sx={{ fontWeight: 700, cursor: "pointer" }}>
                    <TableSortLabel active={sortBy === "drop_from_52w_high_pct"} direction={sortOrder === "asc" ? "asc" : "desc"} onClick={() => handleSort("drop_from_52w_high_pct")}>↓52w</TableSortLabel>
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700, cursor: "pointer" }}>
                    <TableSortLabel active={sortBy === "drop_from_3y_high_pct"} direction={sortOrder === "asc" ? "asc" : "desc"} onClick={() => handleSort("drop_from_3y_high_pct")}>↓3y</TableSortLabel>
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700, cursor: "pointer", backgroundColor: "#e3f2fd" }}>
                    <TableSortLabel active={sortBy === "intrinsic_value_per_share"} direction={sortOrder === "asc" ? "asc" : "desc"} onClick={() => handleSort("intrinsic_value_per_share")}>Intrinsic $</TableSortLabel>
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700, cursor: "pointer", backgroundColor: "#e3f2fd" }}>
                    <TableSortLabel active={sortBy === "margin_of_safety_pct"} direction={sortOrder === "asc" ? "asc" : "desc"} onClick={() => handleSort("margin_of_safety_pct")}>MoS %</TableSortLabel>
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>RevYoY%</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>OpM Trend</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>D/E</TableCell>
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
                      <TableCell align="right" sx={{ fontSize: "0.8rem", color: stock.drop_from_52w_high_pct >= 30 ? "#c62828" : "inherit", fontWeight: stock.drop_from_52w_high_pct >= 25 ? 700 : 400 }}>
                        {fmtDiscount(stock.drop_from_52w_high_pct)}
                      </TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem", color: stock.drop_from_3y_high_pct >= 50 ? "#c62828" : "inherit", fontWeight: stock.drop_from_3y_high_pct >= 40 ? 700 : 400 }}>
                        {fmtDiscount(stock.drop_from_3y_high_pct)}
                      </TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem", fontWeight: 700, backgroundColor: "#e3f2fd", color: "#0d47a1" }}>
                        {stock.intrinsic_value_per_share != null ? `$${stock.intrinsic_value_per_share.toFixed(2)}` : "—"}
                      </TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.85rem", fontWeight: 700, backgroundColor: "#e3f2fd", color: stock.margin_of_safety_pct >= 30 ? "#1b5e20" : stock.margin_of_safety_pct >= 0 ? "#558b2f" : "#c62828" }}>
                        {stock.margin_of_safety_pct != null ? `${stock.margin_of_safety_pct.toFixed(1)}%` : "—"}
                      </TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem", color: stock.revenue_growth_yoy_pct >= 0 ? "#1b5e20" : "#c62828", fontWeight: 600 }}>
                        {fmtPct(stock.revenue_growth_yoy_pct)}
                      </TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem", color: stock.op_margin_trend_pp >= 0 ? "#1b5e20" : stock.op_margin_trend_pp > -3 ? "#f57c00" : "#c62828" }}>
                        {stock.op_margin_trend_pp != null ? `${stock.op_margin_trend_pp >= 0 ? "+" : ""}${stock.op_margin_trend_pp.toFixed(2)}pp` : "—"}
                      </TableCell>
                      <TableCell align="right" sx={{ fontSize: "0.8rem", color: stock.debt_to_equity > 2 ? "#c62828" : stock.debt_to_equity < 0.5 ? "#1b5e20" : "inherit" }}>
                        {fmt(stock.debt_to_equity)}
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
