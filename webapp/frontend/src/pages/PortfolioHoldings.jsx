import React, { useState, useEffect } from "react";
import { useAuth } from "../contexts/AuthContext";
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  CircularProgress,
  Alert,
  Button,
  TextField,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Tooltip,
  LinearProgress,
  Fab,
  TableSortLabel,
  TablePagination,
} from "@mui/material";
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Treemap,
} from "recharts";
import {
  Add,
  Delete,
  Edit,
  TrendingUp,
  TrendingDown,
  AccountBalance,
  PieChart as PieChartIcon,
  Download,
  Upload,
  Sync,
  FilterList,
} from "@mui/icons-material";
import {
  getPortfolioData,
  addHolding,
  updateHolding,
  deleteHolding,
  importPortfolioFromBroker,
} from "../services/api";

const PortfolioHoldings = () => {
  const { user } = useAuth();
  const [holdings, setHoldings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [selectedHolding, setSelectedHolding] = useState(null);
  const [orderBy, setOrderBy] = useState("marketValue");
  const [order, setOrder] = useState("desc");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [filterText, setFilterText] = useState("");

  // New holding form state
  const [newHolding, setNewHolding] = useState({
    symbol: "",
    quantity: "",
    costBasis: "",
    purchaseDate: new Date().toISOString().split("T")[0],
  });

  const [portfolioSummary, setPortfolioSummary] = useState({
    totalValue: 0,
    totalCost: 0,
    totalGainLoss: 0,
    totalGainLossPercent: 0,
    dayGainLoss: 0,
    dayGainLossPercent: 0,
    cashBalance: 0,
  });

  useEffect(() => {
    fetchHoldings();
  }, []);

  const fetchHoldings = async () => {
    try {
      setLoading(true);
      const response = await getPortfolioData();

      // Handle both direct data and wrapped response structures
      const data = response?.data || response;

      if (data?.holdings && Array.isArray(data.holdings)) {
        // Transform API data to component format
        const transformedHoldings = data.holdings.map((holding) => ({
          id: holding.id || holding.symbol,
          symbol: holding.symbol,
          companyName: holding.name || holding.company || holding.companyName,
          quantity: holding.quantity,
          costBasis:
            holding.avgCost ||
            holding.cost_basis ||
            holding.averageEntryPrice ||
            holding.average_entry_price,
          currentPrice: holding.currentPrice || holding.current_price,
          marketValue: holding.marketValue || holding.market_value,
          gainLoss: holding.unrealizedPnl || holding.pnl || holding.gainLoss,
          gainLossPercent:
            holding.unrealizedPnlPercent ||
            holding.pnl_percent ||
            holding.gainLossPercent,
          dayChange: holding.dayChange || holding.day_change,
          dayChangePercent:
            holding.dayChangePercent || holding.day_change_percent,
          sector: holding.sector,
          weight: holding.weight,
          purchaseDate: holding.purchaseDate,
        }));

        setHoldings(transformedHoldings);

        // Transform summary data
        const transformedSummary = {
          totalValue:
            data.summary?.totalValue ||
            data.totalValue ||
            transformedHoldings.reduce(
              (sum, h) => sum + (h.marketValue || 0),
              0
            ),
          totalCost:
            data.summary?.totalCost ||
            transformedHoldings.reduce(
              (sum, h) => sum + (h.costBasis || 0) * (h.quantity || 0),
              0
            ),
          totalGainLoss:
            data.summary?.totalPnl ||
            data.summary?.totalGainLoss ||
            transformedHoldings.reduce((sum, h) => sum + (h.gainLoss || 0), 0),
          totalGainLossPercent:
            data.summary?.totalPnlPercent ||
            data.summary?.totalGainLossPercent ||
            0,
          dayGainLoss:
            data.summary?.dayPnl ||
            data.summary?.dayGainLoss ||
            transformedHoldings.reduce((sum, h) => sum + (h.dayChange || 0), 0),
          dayGainLossPercent:
            data.summary?.dayPnlPercent ||
            data.summary?.dayGainLossPercent ||
            0,
          cashBalance: data.summary?.cash || data.summary?.cashBalance || 0,
        };

        setPortfolioSummary(transformedSummary);
      } else {
        // If no holdings data, show empty state
        setHoldings([]);
        setPortfolioSummary({
          totalValue: 0,
          totalCost: 0,
          totalGainLoss: 0,
          totalGainLossPercent: 0,
          dayGainLoss: 0,
          dayGainLossPercent: 0,
          cashBalance: 0,
        });
      }
    } catch (err) {
      console.error("Holdings fetch error:", err);
      setError("Failed to fetch portfolio holdings");

      // Set empty state on error
      setHoldings([]);
      setPortfolioSummary({
        totalValue: 0,
        totalCost: 0,
        totalGainLoss: 0,
        totalGainLossPercent: 0,
        dayGainLoss: 0,
        dayGainLossPercent: 0,
        cashBalance: 0,
      });
    } finally {
      setLoading(false);
    }
  };

  const handleAddHolding = async () => {
    try {
      if (!newHolding.symbol || !newHolding.quantity || !newHolding.costBasis) {
        setError("Please fill in all required fields");
        return;
      }

      await addHolding({
        ...newHolding,
        quantity: parseFloat(newHolding.quantity),
        costBasis: parseFloat(newHolding.costBasis),
      });

      setAddDialogOpen(false);
      setNewHolding({
        symbol: "",
        quantity: "",
        costBasis: "",
        purchaseDate: new Date().toISOString().split("T")[0],
      });
      fetchHoldings();
    } catch (err) {
      setError("Failed to add holding");
      console.error("Add holding error:", err);
    }
  };

  const handleEditHolding = async () => {
    try {
      await updateHolding(selectedHolding.id, {
        quantity: parseFloat(selectedHolding.quantity),
        costBasis: parseFloat(selectedHolding.costBasis),
        purchaseDate: selectedHolding.purchaseDate,
      });

      setEditDialogOpen(false);
      setSelectedHolding(null);
      fetchHoldings();
    } catch (err) {
      setError("Failed to update holding");
      console.error("Update holding error:", err);
    }
  };

  const handleDeleteHolding = async (holdingId) => {
    try {
      await deleteHolding(holdingId);
      fetchHoldings();
    } catch (err) {
      setError("Failed to delete holding");
      console.error("Delete holding error:", err);
    }
  };

  const handleImportFromBroker = async (broker) => {
    try {
      setLoading(true);
      await importPortfolioFromBroker(broker);
      setImportDialogOpen(false);
      fetchHoldings();
    } catch (err) {
      setError(`Failed to import from ${broker}`);
      console.error("Import error:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleRequestSort = (property) => {
    const isAsc = orderBy === property && order === "asc";
    setOrder(isAsc ? "desc" : "asc");
    setOrderBy(property);
  };

  const getSectorColor = (sector) => {
    const colors = {
      Technology: "#2196F3",
      Healthcare: "#4CAF50",
      Financial: "#FF9800",
      Consumer: "#9C27B0",
      Industrial: "#795548",
      Energy: "#F44336",
      Utilities: "#607D8B",
      Materials: "#3F51B5",
      "Real Estate": "#E91E63",
      Communication: "#00BCD4",
    };
    return colors[sector] || "#9E9E9E";
  };

  const filteredHoldings = holdings.filter(
    (holding) =>
      holding.symbol.toLowerCase().includes(filterText.toLowerCase()) ||
      holding.companyName?.toLowerCase().includes(filterText.toLowerCase()) ||
      holding.sector?.toLowerCase().includes(filterText.toLowerCase())
  );

  const sortedHoldings = [...filteredHoldings].sort((a, b) => {
    let aValue = a[orderBy];
    let bValue = b[orderBy];

    if (typeof aValue === "string") {
      aValue = aValue.toLowerCase();
      bValue = bValue.toLowerCase();
    }

    if (order === "desc") {
      return bValue > aValue ? 1 : -1;
    }
    return aValue > bValue ? 1 : -1;
  });

  const paginatedHoldings = sortedHoldings.slice(
    page * rowsPerPage,
    page * rowsPerPage + rowsPerPage
  );

  // Prepare sector allocation data
  const sectorAllocation = holdings.reduce((acc, holding) => {
    const sector = holding.sector || "Unknown";
    if (!acc[sector]) {
      acc[sector] = { value: 0, count: 0 };
    }
    acc[sector].value += holding.marketValue || 0;
    acc[sector].count += 1;
    return acc;
  }, {});

  const sectorData = Object.entries(sectorAllocation).map(([sector, data]) => ({
    name: sector,
    value: data.value,
    count: data.count,
    percentage: ((data.value / portfolioSummary.totalValue) * 100).toFixed(1),
  }));

  // Top holdings for treemap
  const topHoldings = holdings
    .sort((a, b) => (b.marketValue || 0) - (a.marketValue || 0))
    .slice(0, 10)
    .map((holding) => ({
      name: holding.symbol,
      size: holding.marketValue || 0,
      gainLoss: holding.gainLoss || 0,
    }));

  if (loading) {
    return (
      <Container maxWidth="xl">
        <Box
          display="flex"
          justifyContent="center"
          alignItems="center"
          minHeight="60vh"
        >
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl">
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" gutterBottom>
          Portfolio Holdings
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Track and manage your investment holdings
        </Typography>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Portfolio Summary Cards */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="text.secondary" gutterBottom>
                Total Value
              </Typography>
              <Typography variant="h5">
                $
                {portfolioSummary.totalValue.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                })}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="text.secondary" gutterBottom>
                Total Gain/Loss
              </Typography>
              <Typography
                variant="h5"
                color={
                  portfolioSummary.totalGainLoss >= 0
                    ? "success.main"
                    : "error.main"
                }
              >
                $
                {portfolioSummary.totalGainLoss.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                })}
              </Typography>
              <Typography
                variant="body2"
                color={
                  portfolioSummary.totalGainLoss >= 0
                    ? "success.main"
                    : "error.main"
                }
              >
                ({portfolioSummary.totalGainLossPercent.toFixed(2)}%)
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="text.secondary" gutterBottom>
                Day Gain/Loss
              </Typography>
              <Typography
                variant="h5"
                color={
                  portfolioSummary.dayGainLoss >= 0
                    ? "success.main"
                    : "error.main"
                }
              >
                $
                {portfolioSummary.dayGainLoss.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                })}
              </Typography>
              <Typography
                variant="body2"
                color={
                  portfolioSummary.dayGainLoss >= 0
                    ? "success.main"
                    : "error.main"
                }
              >
                ({portfolioSummary.dayGainLossPercent.toFixed(2)}%)
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="text.secondary" gutterBottom>
                Cash Balance
              </Typography>
              <Typography variant="h5">
                $
                {portfolioSummary.cashBalance.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                })}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Charts Row */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Sector Allocation
              </Typography>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={sectorData}
                    cx="50%"
                    cy="50%"
                    outerRadius={100}
                    fill="#8884d8"
                    dataKey="value"
                    label={({ name, percentage }) => `${name} ${percentage}%`}
                  >
                    {sectorData.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={getSectorColor(entry.name)}
                      />
                    ))}
                  </Pie>
                  <RechartsTooltip
                    formatter={(value) => [
                      `$${value.toLocaleString()}`,
                      "Value",
                    ]}
                  />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Top Holdings
              </Typography>
              <ResponsiveContainer width="100%" height={300}>
                <Treemap
                  data={topHoldings}
                  dataKey="size"
                  aspectRatio={4 / 3}
                  stroke="#fff"
                  fill="#8884d8"
                />
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Actions Bar */}
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          mb: 3,
        }}
      >
        <Box sx={{ display: "flex", gap: 1 }}>
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={() => setAddDialogOpen(true)}
          >
            Add Holding
          </Button>
          <Button
            variant="outlined"
            startIcon={<Upload />}
            onClick={() => setImportDialogOpen(true)}
          >
            Import
          </Button>
          <Button
            variant="outlined"
            startIcon={<Sync />}
            onClick={fetchHoldings}
          >
            Refresh
          </Button>
        </Box>
        <TextField
          size="small"
          placeholder="Filter holdings..."
          value={filterText}
          onChange={(e) => setFilterText(e.target.value)}
          InputProps={{
            startAdornment: (
              <FilterList sx={{ mr: 1, color: "text.secondary" }} />
            ),
          }}
        />
      </Box>

      {/* Holdings Table */}
      <Card>
        <TableContainer>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>
                  <TableSortLabel
                    active={orderBy === "symbol"}
                    direction={orderBy === "symbol" ? order : "asc"}
                    onClick={() => handleRequestSort("symbol")}
                  >
                    Symbol
                  </TableSortLabel>
                </TableCell>
                <TableCell>Company</TableCell>
                <TableCell align="right">
                  <TableSortLabel
                    active={orderBy === "quantity"}
                    direction={orderBy === "quantity" ? order : "asc"}
                    onClick={() => handleRequestSort("quantity")}
                  >
                    Quantity
                  </TableSortLabel>
                </TableCell>
                <TableCell align="right">Avg Cost</TableCell>
                <TableCell align="right">Current Price</TableCell>
                <TableCell align="right">
                  <TableSortLabel
                    active={orderBy === "marketValue"}
                    direction={orderBy === "marketValue" ? order : "asc"}
                    onClick={() => handleRequestSort("marketValue")}
                  >
                    Market Value
                  </TableSortLabel>
                </TableCell>
                <TableCell align="right">
                  <TableSortLabel
                    active={orderBy === "gainLoss"}
                    direction={orderBy === "gainLoss" ? order : "asc"}
                    onClick={() => handleRequestSort("gainLoss")}
                  >
                    Gain/Loss
                  </TableSortLabel>
                </TableCell>
                <TableCell align="right">% Change</TableCell>
                <TableCell>Sector</TableCell>
                <TableCell align="center">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {paginatedHoldings.map((holding) => (
                <TableRow key={holding.id || holding.symbol}>
                  <TableCell>
                    <Typography variant="body2" fontWeight="bold">
                      {holding.symbol}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2">
                      {holding.companyName || "N/A"}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">{holding.quantity}</TableCell>
                  <TableCell align="right">
                    ${(holding.costBasis || 0).toFixed(2)}
                  </TableCell>
                  <TableCell align="right">
                    ${(holding.currentPrice || 0).toFixed(2)}
                  </TableCell>
                  <TableCell align="right">
                    $
                    {(holding.marketValue || 0).toLocaleString("en-US", {
                      minimumFractionDigits: 2,
                    })}
                  </TableCell>
                  <TableCell
                    align="right"
                    sx={{
                      color:
                        (holding.gainLoss || 0) >= 0
                          ? "success.main"
                          : "error.main",
                    }}
                  >
                    $
                    {(holding.gainLoss || 0).toLocaleString("en-US", {
                      minimumFractionDigits: 2,
                    })}
                  </TableCell>
                  <TableCell
                    align="right"
                    sx={{
                      color:
                        (holding.gainLossPercent || 0) >= 0
                          ? "success.main"
                          : "error.main",
                    }}
                  >
                    {(holding.gainLossPercent || 0) >= 0 ? "+" : ""}
                    {(holding.gainLossPercent || 0).toFixed(2)}%
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={holding.sector || "Unknown"}
                      size="small"
                      sx={{
                        backgroundColor: getSectorColor(holding.sector) + "20",
                        color: getSectorColor(holding.sector),
                      }}
                    />
                  </TableCell>
                  <TableCell align="center">
                    <IconButton
                      size="small"
                      onClick={() => {
                        setSelectedHolding(holding);
                        setEditDialogOpen(true);
                      }}
                    >
                      <Edit />
                    </IconButton>
                    <IconButton
                      size="small"
                      color="error"
                      onClick={() => handleDeleteHolding(holding.id)}
                    >
                      <Delete />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
        <TablePagination
          rowsPerPageOptions={[5, 10, 25, 50]}
          component="div"
          count={filteredHoldings.length}
          rowsPerPage={rowsPerPage}
          page={page}
          onPageChange={(event, newPage) => setPage(newPage)}
          onRowsPerPageChange={(event) => {
            setRowsPerPage(parseInt(event.target.value, 10));
            setPage(0);
          }}
        />
      </Card>

      {/* Add Holding Dialog */}
      <Dialog
        open={addDialogOpen}
        onClose={() => setAddDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Add New Holding</DialogTitle>
        <DialogContent>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
            <TextField
              label="Symbol"
              value={newHolding.symbol}
              onChange={(e) =>
                setNewHolding({
                  ...newHolding,
                  symbol: e.target.value.toUpperCase(),
                })
              }
              required
            />
            <TextField
              label="Quantity"
              type="number"
              value={newHolding.quantity}
              onChange={(e) =>
                setNewHolding({ ...newHolding, quantity: e.target.value })
              }
              required
            />
            <TextField
              label="Cost Basis (per share)"
              type="number"
              step="0.01"
              value={newHolding.costBasis}
              onChange={(e) =>
                setNewHolding({ ...newHolding, costBasis: e.target.value })
              }
              required
            />
            <TextField
              label="Purchase Date"
              type="date"
              value={newHolding.purchaseDate}
              onChange={(e) =>
                setNewHolding({ ...newHolding, purchaseDate: e.target.value })
              }
              InputLabelProps={{ shrink: true }}
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleAddHolding} variant="contained">
            Add Holding
          </Button>
        </DialogActions>
      </Dialog>

      {/* Edit Holding Dialog */}
      <Dialog
        open={editDialogOpen}
        onClose={() => setEditDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Edit Holding</DialogTitle>
        <DialogContent>
          {selectedHolding && (
            <Box
              sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}
            >
              <TextField
                label="Symbol"
                value={selectedHolding.symbol}
                disabled
              />
              <TextField
                label="Quantity"
                type="number"
                value={selectedHolding.quantity}
                onChange={(e) =>
                  setSelectedHolding({
                    ...selectedHolding,
                    quantity: e.target.value,
                  })
                }
              />
              <TextField
                label="Cost Basis (per share)"
                type="number"
                step="0.01"
                value={selectedHolding.costBasis}
                onChange={(e) =>
                  setSelectedHolding({
                    ...selectedHolding,
                    costBasis: e.target.value,
                  })
                }
              />
              <TextField
                label="Purchase Date"
                type="date"
                value={selectedHolding.purchaseDate}
                onChange={(e) =>
                  setSelectedHolding({
                    ...selectedHolding,
                    purchaseDate: e.target.value,
                  })
                }
                InputLabelProps={{ shrink: true }}
              />
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleEditHolding} variant="contained">
            Save Changes
          </Button>
        </DialogActions>
      </Dialog>

      {/* Import Dialog */}
      <Dialog
        open={importDialogOpen}
        onClose={() => setImportDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Import Portfolio</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            Import your portfolio from a supported broker:
          </Typography>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <Button
              variant="outlined"
              onClick={() => handleImportFromBroker("alpaca")}
              disabled={loading}
            >
              Import from Alpaca
            </Button>
            <Button
              variant="outlined"
              onClick={() => handleImportFromBroker("robinhood")}
              disabled={loading}
            >
              Import from Robinhood
            </Button>
            <Button
              variant="outlined"
              onClick={() => handleImportFromBroker("fidelity")}
              disabled={loading}
            >
              Import from Fidelity
            </Button>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setImportDialogOpen(false)}>Cancel</Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default PortfolioHoldings;
