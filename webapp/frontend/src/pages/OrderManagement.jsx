import React, { useState, useEffect, useMemo } from "react";
import { useAuth } from "../contexts/AuthContext";
import { useNavigate } from "react-router-dom";
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Tabs,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  CircularProgress,
  Alert,
  Button,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  InputAdornment,
  IconButton,
  FormControlLabel,
  Switch,
  Tooltip,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  Cancel,
  Edit,
  Add,
  Refresh,
  Settings,
  Info,
  AttachMoney,
  Speed,
  Gavel,
  AccountBalance,
  Timeline,
  Assessment,
  Search,
  Download,
  ShowChart,
  Error,
} from "@mui/icons-material";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import { AdapterDateFns } from "@mui/x-date-pickers/AdapterDateFns";

const OrderManagement = () => {
  const { user, isAuthenticated } = useAuth();
  const navigate = useNavigate();

  // State management
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tabValue, setTabValue] = useState(0);
  const [orderDialogOpen, setOrderDialogOpen] = useState(false);
  const [confirmDialogOpen, setConfirmDialogOpen] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [orderPreview, setOrderPreview] = useState(null);
  const [accountInfo, setAccountInfo] = useState(null);
  const [positions, setPositions] = useState([]);
  const [marketData, setMarketData] = useState({});
  const [watchlist, setWatchlist] = useState([]);

  // Order form state
  const [orderForm, setOrderForm] = useState({
    symbol: "",
    side: "buy", // buy or sell
    quantity: "",
    orderType: "market", // market, limit, stop, stop_limit
    timeInForce: "day", // day, gtc, ioc, fok
    limitPrice: "",
    stopPrice: "",
    expiration: null,
    extendedHours: false,
    allOrNone: false,
    notes: "",
  });

  // Filters and search
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sideFilter, setSideFilter] = useState("all");
  const [_dateRange, _setDateRange] = useState({ start: null, end: null });

  // Real-time updates
  const [_orderUpdates, _setOrderUpdates] = useState({});
  const [executionAlerts, setExecutionAlerts] = useState([]);

  // Fetch initial data
  useEffect(() => {
    if (!isAuthenticated) {
      navigate("/");
      return;
    }

    fetchOrders();
    fetchAccountInfo();
    fetchPositions();
    fetchWatchlist();

    // Setup real-time updates
    const interval = setInterval(() => {
      fetchOrderUpdates();
      fetchMarketData();
    }, 5000);

    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, navigate]);

  const fetchOrders = async () => {
    try {
      setLoading(true);
      const response = await fetch("/api/orders", {
        headers: { Authorization: `Bearer ${user.token}` },
      });

      if (!response.ok) throw new Error("Failed to fetch orders");

      const data = await response.json();
      setOrders(data.orders || []);
    } catch (err) {
      setError(err.message);
      // Mock data for demo
      setOrders([
        {
          id: "ORD-001",
          symbol: "AAPL",
          side: "buy",
          quantity: 100,
          orderType: "limit",
          limitPrice: 185.5,
          status: "pending",
          timeInForce: "gtc",
          submittedAt: new Date().toISOString(),
          filledQuantity: 0,
          averagePrice: 0,
          estimatedValue: 18550,
          broker: "alpaca",
        },
        {
          id: "ORD-002",
          symbol: "MSFT",
          side: "sell",
          quantity: 50,
          orderType: "market",
          status: "filled",
          timeInForce: "day",
          submittedAt: new Date(Date.now() - 3600000).toISOString(),
          filledQuantity: 50,
          averagePrice: 308.25,
          estimatedValue: 15412.5,
          broker: "alpaca",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const fetchAccountInfo = async () => {
    try {
      const response = await fetch("/api/account", {
        headers: { Authorization: `Bearer ${user.token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setAccountInfo(data);
      }
    } catch (err) {
      // Mock account info
      setAccountInfo({
        accountId: "ACC-12345",
        status: "active",
        buyingPower: 50000,
        cash: 25000,
        portfolioValue: 125000,
        dayTradingBuyingPower: 100000,
        dayTrades: 2,
        patternDayTrader: false,
      });
    }
  };

  const fetchPositions = async () => {
    try {
      const response = await fetch("/api/portfolio/holdings", {
        headers: { Authorization: `Bearer ${user.token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setPositions(data.data?.holdings || []);
      }
    } catch (err) {
      console.error("Failed to fetch positions:", err);
    }
  };

  const fetchWatchlist = async () => {
    try {
      const response = await fetch("/api/watchlist", {
        headers: { Authorization: `Bearer ${user.token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setWatchlist(data.symbols || ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]);
      }
    } catch (err) {
      setWatchlist(["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]);
    }
  };

  const fetchOrderUpdates = async () => {
    try {
      const response = await fetch("/api/orders/updates", {
        headers: { Authorization: `Bearer ${user.token}` },
      });

      if (response.ok) {
        const data = await response.json();
        _setOrderUpdates(data.updates || {});

        // Check for execution alerts
        const newAlerts = data.executions || [];
        if (newAlerts.length > 0) {
          setExecutionAlerts((prev) => [...prev, ...newAlerts]);
        }
      }
    } catch (err) {
      console.error("Failed to fetch order updates:", err);
    }
  };

  const fetchMarketData = async () => {
    try {
      const symbols = [
        ...new Set([...watchlist, ...orders.map((o) => o.symbol)]),
      ];
      const response = await fetch(`/api/quotes?symbols=${symbols.join(",")}`, {
        headers: { Authorization: `Bearer ${user.token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setMarketData(data.quotes || {});
      }
    } catch (err) {
      console.error("Failed to fetch market data:", err);
    }
  };

  const handleSubmitOrder = async () => {
    try {
      setLoading(true);

      // Validate order
      const validation = validateOrder(orderForm);
      if (!validation.valid) {
        setError(validation.message);
        return;
      }

      // Get order preview
      const preview = await getOrderPreview(orderForm);
      setOrderPreview(preview);
      setConfirmDialogOpen(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const confirmOrder = async () => {
    try {
      setLoading(true);

      const response = await fetch("/api/orders", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${user.token}`,
        },
        body: JSON.stringify(orderForm),
      });

      if (!response.ok) throw new Error("Failed to submit order");

      const result = await response.json();

      // Update orders list
      await fetchOrders();

      // Reset form
      setOrderForm({
        symbol: "",
        side: "buy",
        quantity: "",
        orderType: "market",
        timeInForce: "day",
        limitPrice: "",
        stopPrice: "",
        expiration: null,
        extendedHours: false,
        allOrNone: false,
        notes: "",
      });

      setOrderDialogOpen(false);
      setConfirmDialogOpen(false);

      // Show success message
      setExecutionAlerts((prev) => [
        ...prev,
        {
          type: "success",
          message: `Order submitted successfully: ${result.orderId}`,
          timestamp: new Date().toISOString(),
        },
      ]);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const cancelOrder = async (orderId) => {
    try {
      const response = await fetch(`/api/orders/${orderId}/cancel`, {
        method: "POST",
        headers: { Authorization: `Bearer ${user.token}` },
      });

      if (!response.ok) throw new Error("Failed to cancel order");

      await fetchOrders();

      setExecutionAlerts((prev) => [
        ...prev,
        {
          type: "info",
          message: `Order ${orderId} cancelled`,
          timestamp: new Date().toISOString(),
        },
      ]);
    } catch (err) {
      setError(err.message);
    }
  };

  const _modifyOrder = async (orderId, modifications) => {
    try {
      const response = await fetch(`/api/orders/${orderId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${user.token}`,
        },
        body: JSON.stringify(modifications),
      });

      if (!response.ok) throw new Error("Failed to modify order");

      await fetchOrders();
    } catch (err) {
      setError(err.message);
    }
  };

  const getOrderPreview = async (orderData) => {
    try {
      const response = await fetch("/api/orders/preview", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${user.token}`,
        },
        body: JSON.stringify(orderData),
      });

      if (!response.ok) throw new Error("Failed to get order preview");

      const preview = await response.json();
      return preview;
    } catch (err) {
      // Mock preview data
      return {
        symbol: orderData.symbol,
        side: orderData.side,
        quantity: parseFloat(orderData.quantity),
        estimatedPrice:
          orderData.orderType === "market"
            ? marketData[orderData.symbol]?.price || 0
            : parseFloat(orderData.limitPrice || 0),
        estimatedValue:
          parseFloat(orderData.quantity) *
          (orderData.orderType === "market"
            ? marketData[orderData.symbol]?.price || 0
            : parseFloat(orderData.limitPrice || 0)),
        estimatedCommission: 0,
        buyingPowerRequired:
          parseFloat(orderData.quantity) *
          (orderData.orderType === "market"
            ? marketData[orderData.symbol]?.price || 0
            : parseFloat(orderData.limitPrice || 0)),
        warningMessages: [],
        riskAssessment: "Low",
      };
    }
  };

  const validateOrder = (orderData) => {
    if (!orderData.symbol)
      return { valid: false, message: "Symbol is required" };
    if (!orderData.quantity || parseFloat(orderData.quantity) <= 0)
      return { valid: false, message: "Quantity must be greater than 0" };
    if (
      orderData.orderType === "limit" &&
      (!orderData.limitPrice || parseFloat(orderData.limitPrice) <= 0)
    ) {
      return {
        valid: false,
        message: "Limit price is required for limit orders",
      };
    }
    if (
      orderData.orderType === "stop" &&
      (!orderData.stopPrice || parseFloat(orderData.stopPrice) <= 0)
    ) {
      return {
        valid: false,
        message: "Stop price is required for stop orders",
      };
    }

    return { valid: true };
  };

  const getOrderStatusColor = (status) => {
    switch (status?.toLowerCase()) {
      case "filled":
        return "success";
      case "pending":
        return "warning";
      case "cancelled":
        return "error";
      case "partial":
        return "info";
      case "rejected":
        return "error";
      default:
        return "default";
    }
  };

  const getSideColor = (side) => {
    return side === "buy" ? "success" : "error";
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
    }).format(amount || 0);
  };

  const _formatPercentage = (value) => {
    return `${(value * 100).toFixed(2)}%`;
  };

  // Filter orders
  const filteredOrders = useMemo(() => {
    return orders.filter((order) => {
      const matchesSearch =
        !searchTerm ||
        order.symbol.toLowerCase().includes(searchTerm.toLowerCase()) ||
        order.id.toLowerCase().includes(searchTerm.toLowerCase());

      const matchesStatus =
        statusFilter === "all" || order.status === statusFilter;
      const matchesSide = sideFilter === "all" || order.side === sideFilter;

      return matchesSearch && matchesStatus && matchesSide;
    });
  }, [orders, searchTerm, statusFilter, sideFilter]);

  const TabPanel = ({ children, value, index, ...other }) => (
    <div role="tabpanel" hidden={value !== index} {...other}>
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );

  if (!isAuthenticated) {
    return (
      <Container maxWidth="md" sx={{ mt: 4 }}>
        <Alert severity="warning">
          Please log in to access order management.
        </Alert>
      </Container>
    );
  }

  return (
    <LocalizationProvider dateAdapter={AdapterDateFns}>
      <Container maxWidth="xl" sx={{ py: 3 }}>
        {/* Header */}
        <Box sx={{ mb: 3 }}>
          <Typography
            variant="h4"
            component="h1"
            gutterBottom
            sx={{ fontWeight: "bold" }}
          >
            Order Management
          </Typography>
          <Typography variant="subtitle1" color="text.secondary">
            Execute trades, manage orders, and monitor positions
          </Typography>
        </Box>

        {error && (
          <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {/* Execution Alerts */}
        {executionAlerts.length > 0 && (
          <Box sx={{ mb: 3 }}>
            {executionAlerts.slice(-3).map((alert, index) => (
              <Alert
                key={index}
                severity={alert.type}
                sx={{ mb: 1 }}
                onClose={() =>
                  setExecutionAlerts((prev) =>
                    prev.filter((_, i) => i !== index)
                  )
                }
              >
                {alert.message}
              </Alert>
            ))}
          </Box>
        )}

        {/* Account Summary */}
        {accountInfo && (
          <Grid container spacing={3} sx={{ mb: 3 }}>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box sx={{ display: "flex", alignItems: "center" }}>
                    <AccountBalance color="primary" sx={{ mr: 1 }} />
                    <Typography variant="h6">Buying Power</Typography>
                  </Box>
                  <Typography variant="h4" sx={{ mt: 1 }}>
                    {formatCurrency(accountInfo.buyingPower)}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box sx={{ display: "flex", alignItems: "center" }}>
                    <AttachMoney color="success" sx={{ mr: 1 }} />
                    <Typography variant="h6">Cash</Typography>
                  </Box>
                  <Typography variant="h4" sx={{ mt: 1 }}>
                    {formatCurrency(accountInfo.cash)}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box sx={{ display: "flex", alignItems: "center" }}>
                    <Timeline color="info" sx={{ mr: 1 }} />
                    <Typography variant="h6">Portfolio Value</Typography>
                  </Box>
                  <Typography variant="h4" sx={{ mt: 1 }}>
                    {formatCurrency(accountInfo.portfolioValue)}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box sx={{ display: "flex", alignItems: "center" }}>
                    <Speed color="warning" sx={{ mr: 1 }} />
                    <Typography variant="h6">Day Trades</Typography>
                  </Box>
                  <Typography variant="h4" sx={{ mt: 1 }}>
                    {accountInfo.dayTrades}/3
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {accountInfo.patternDayTrader
                      ? "PDT Account"
                      : "Standard Account"}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        )}

        {/* Action Buttons */}
        <Box sx={{ mb: 3, display: "flex", gap: 2, flexWrap: "wrap" }}>
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={() => setOrderDialogOpen(true)}
            sx={{ background: "linear-gradient(45deg, #1976d2, #42a5f5)" }}
          >
            New Order
          </Button>
          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={fetchOrders}
          >
            Refresh
          </Button>
          <Button
            variant="outlined"
            startIcon={<Download />}
            onClick={() => {
              /* Export orders */
            }}
          >
            Export Orders
          </Button>
        </Box>

        {/* Tabs */}
        <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 3 }}>
          <Tabs
            value={tabValue}
            onChange={(e, newValue) => setTabValue(newValue)}
          >
            <Tab icon={<Gavel />} label="Open Orders" />
            <Tab icon={<Assessment />} label="Order History" />
            <Tab icon={<ShowChart />} label="Positions" />
            <Tab icon={<Settings />} label="Settings" />
          </Tabs>
        </Box>

        {/* Tab Content */}
        <TabPanel value={tabValue} index={0}>
          {/* Open Orders */}
          <Card>
            <CardHeader title="Open Orders" />
            <CardContent>
              {/* Filters */}
              <Box sx={{ mb: 3, display: "flex", gap: 2, flexWrap: "wrap" }}>
                <TextField
                  size="small"
                  placeholder="Search orders..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        <Search />
                      </InputAdornment>
                    ),
                  }}
                />

                <FormControl size="small" sx={{ minWidth: 120 }}>
                  <InputLabel>Status</InputLabel>
                  <Select
                    value={statusFilter}
                    label="Status"
                    onChange={(e) => setStatusFilter(e.target.value)}
                  >
                    <MenuItem value="all">All Status</MenuItem>
                    <MenuItem value="pending">Pending</MenuItem>
                    <MenuItem value="filled">Filled</MenuItem>
                    <MenuItem value="cancelled">Cancelled</MenuItem>
                    <MenuItem value="partial">Partial</MenuItem>
                  </Select>
                </FormControl>

                <FormControl size="small" sx={{ minWidth: 120 }}>
                  <InputLabel>Side</InputLabel>
                  <Select
                    value={sideFilter}
                    label="Side"
                    onChange={(e) => setSideFilter(e.target.value)}
                  >
                    <MenuItem value="all">All</MenuItem>
                    <MenuItem value="buy">Buy</MenuItem>
                    <MenuItem value="sell">Sell</MenuItem>
                  </Select>
                </FormControl>
              </Box>

              {/* Orders Table */}
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Order ID</TableCell>
                      <TableCell>Symbol</TableCell>
                      <TableCell>Side</TableCell>
                      <TableCell>Quantity</TableCell>
                      <TableCell>Order Type</TableCell>
                      <TableCell>Price</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Submitted</TableCell>
                      <TableCell>Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {loading ? (
                      <TableRow>
                        <TableCell colSpan={9} align="center">
                          <CircularProgress />
                        </TableCell>
                      </TableRow>
                    ) : filteredOrders.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={9} align="center">
                          <Typography variant="body2" color="text.secondary">
                            No orders found
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ) : (
                      filteredOrders.map((order) => (
                        <TableRow key={order.id} hover>
                          <TableCell>
                            <Typography variant="body2" fontWeight="bold">
                              {order.id}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2" fontWeight="bold">
                              {order.symbol}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={order.side.toUpperCase()}
                              color={getSideColor(order.side)}
                              size="small"
                              icon={
                                order.side === "buy" ? (
                                  <TrendingUp />
                                ) : (
                                  <TrendingDown />
                                )
                              }
                            />
                          </TableCell>
                          <TableCell>
                            {order.filledQuantity > 0 ? (
                              <Box>
                                <Typography variant="body2">
                                  {order.filledQuantity}/{order.quantity}
                                </Typography>
                                <Typography
                                  variant="caption"
                                  color="text.secondary"
                                >
                                  {(
                                    (order.filledQuantity / order.quantity) *
                                    100
                                  ).toFixed(1)}
                                  % filled
                                </Typography>
                              </Box>
                            ) : (
                              order.quantity
                            )}
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={order.orderType.toUpperCase()}
                              size="small"
                              variant="outlined"
                            />
                          </TableCell>
                          <TableCell>
                            {order.orderType === "market" ? (
                              <Typography variant="body2">Market</Typography>
                            ) : (
                              <Typography variant="body2">
                                {formatCurrency(
                                  order.limitPrice || order.stopPrice
                                )}
                              </Typography>
                            )}
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={order.status.toUpperCase()}
                              color={getOrderStatusColor(order.status)}
                              size="small"
                            />
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2">
                              {new Date(order.submittedAt).toLocaleString()}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Box sx={{ display: "flex", gap: 1 }}>
                              {order.status === "pending" && (
                                <>
                                  <Tooltip title="Modify Order">
                                    <IconButton
                                      size="small"
                                      onClick={() => {
                                        setSelectedOrder(order);
                                        setOrderForm({
                                          ...order,
                                          limitPrice:
                                            order.limitPrice?.toString() || "",
                                          stopPrice:
                                            order.stopPrice?.toString() || "",
                                          quantity: order.quantity.toString(),
                                        });
                                        setOrderDialogOpen(true);
                                      }}
                                    >
                                      <Edit />
                                    </IconButton>
                                  </Tooltip>
                                  <Tooltip title="Cancel Order">
                                    <IconButton
                                      size="small"
                                      color="error"
                                      onClick={() => cancelOrder(order.id)}
                                    >
                                      <Cancel />
                                    </IconButton>
                                  </Tooltip>
                                </>
                              )}
                              <Tooltip title="Order Details">
                                <IconButton
                                  size="small"
                                  onClick={() => {
                                    setSelectedOrder(order);
                                    // Open order details dialog
                                  }}
                                >
                                  <Info />
                                </IconButton>
                              </Tooltip>
                            </Box>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </TabPanel>

        <TabPanel value={tabValue} index={1}>
          {/* Order History */}
          <Card>
            <CardHeader title="Order History" />
            <CardContent>
              <Typography variant="body2" color="text.secondary">
                Complete order history with execution details and performance
                analytics.
              </Typography>
              {/* Similar table structure as open orders but with historical data */}
            </CardContent>
          </Card>
        </TabPanel>

        <TabPanel value={tabValue} index={2}>
          {/* Positions */}
          <Card>
            <CardHeader title="Current Positions" />
            <CardContent>
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Symbol</TableCell>
                      <TableCell>Quantity</TableCell>
                      <TableCell>Avg Cost</TableCell>
                      <TableCell>Market Value</TableCell>
                      <TableCell>P&L</TableCell>
                      <TableCell>Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {positions.map((position) => (
                      <TableRow key={position.symbol}>
                        <TableCell>
                          <Typography variant="body2" fontWeight="bold">
                            {position.symbol}
                          </Typography>
                        </TableCell>
                        <TableCell>{position.quantity}</TableCell>
                        <TableCell>
                          {formatCurrency(position.avgCost)}
                        </TableCell>
                        <TableCell>
                          {formatCurrency(position.marketValue)}
                        </TableCell>
                        <TableCell>
                          <Typography
                            variant="body2"
                            color={
                              position.unrealizedPnl >= 0
                                ? "success.main"
                                : "error.main"
                            }
                            fontWeight="bold"
                          >
                            {formatCurrency(position.unrealizedPnl)}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Button
                            size="small"
                            variant="outlined"
                            onClick={() => {
                              setOrderForm({
                                ...orderForm,
                                symbol: position.symbol,
                                side: "sell",
                                quantity: position.quantity.toString(),
                                orderType: "market",
                              });
                              setOrderDialogOpen(true);
                            }}
                          >
                            Close Position
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </TabPanel>

        <TabPanel value={tabValue} index={3}>
          {/* Settings */}
          <Card>
            <CardHeader title="Order Settings" />
            <CardContent>
              <Typography variant="body2" color="text.secondary">
                Configure default order settings and risk management parameters.
              </Typography>
              {/* Settings form */}
            </CardContent>
          </Card>
        </TabPanel>

        {/* New Order Dialog */}
        <Dialog
          open={orderDialogOpen}
          onClose={() => setOrderDialogOpen(false)}
          maxWidth="md"
          fullWidth
        >
          <DialogTitle>
            {selectedOrder ? "Modify Order" : "New Order"}
          </DialogTitle>
          <DialogContent>
            <Grid container spacing={3} sx={{ mt: 1 }}>
              <Grid item xs={12} sm={6}>
                <TextField
                  label="Symbol"
                  value={orderForm.symbol}
                  onChange={(e) =>
                    setOrderForm({
                      ...orderForm,
                      symbol: e.target.value.toUpperCase(),
                    })
                  }
                  fullWidth
                  required
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <FormControl fullWidth>
                  <InputLabel>Side</InputLabel>
                  <Select
                    value={orderForm.side}
                    label="Side"
                    onChange={(e) =>
                      setOrderForm({ ...orderForm, side: e.target.value })
                    }
                  >
                    <MenuItem value="buy">Buy</MenuItem>
                    <MenuItem value="sell">Sell</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  label="Quantity"
                  type="number"
                  value={orderForm.quantity}
                  onChange={(e) =>
                    setOrderForm({ ...orderForm, quantity: e.target.value })
                  }
                  fullWidth
                  required
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <FormControl fullWidth>
                  <InputLabel>Order Type</InputLabel>
                  <Select
                    value={orderForm.orderType}
                    label="Order Type"
                    onChange={(e) =>
                      setOrderForm({ ...orderForm, orderType: e.target.value })
                    }
                  >
                    <MenuItem value="market">Market</MenuItem>
                    <MenuItem value="limit">Limit</MenuItem>
                    <MenuItem value="stop">Stop</MenuItem>
                    <MenuItem value="stop_limit">Stop Limit</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              {(orderForm.orderType === "limit" ||
                orderForm.orderType === "stop_limit") && (
                <Grid item xs={12} sm={6}>
                  <TextField
                    label="Limit Price"
                    type="number"
                    value={orderForm.limitPrice}
                    onChange={(e) =>
                      setOrderForm({ ...orderForm, limitPrice: e.target.value })
                    }
                    fullWidth
                    InputProps={{
                      startAdornment: (
                        <InputAdornment position="start">$</InputAdornment>
                      ),
                    }}
                  />
                </Grid>
              )}

              {(orderForm.orderType === "stop" ||
                orderForm.orderType === "stop_limit") && (
                <Grid item xs={12} sm={6}>
                  <TextField
                    label="Stop Price"
                    type="number"
                    value={orderForm.stopPrice}
                    onChange={(e) =>
                      setOrderForm({ ...orderForm, stopPrice: e.target.value })
                    }
                    fullWidth
                    InputProps={{
                      startAdornment: (
                        <InputAdornment position="start">$</InputAdornment>
                      ),
                    }}
                  />
                </Grid>
              )}

              <Grid item xs={12} sm={6}>
                <FormControl fullWidth>
                  <InputLabel>Time in Force</InputLabel>
                  <Select
                    value={orderForm.timeInForce}
                    label="Time in Force"
                    onChange={(e) =>
                      setOrderForm({
                        ...orderForm,
                        timeInForce: e.target.value,
                      })
                    }
                  >
                    <MenuItem value="day">Day</MenuItem>
                    <MenuItem value="gtc">Good Till Cancelled</MenuItem>
                    <MenuItem value="ioc">Immediate or Cancel</MenuItem>
                    <MenuItem value="fok">Fill or Kill</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              <Grid item xs={12}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={orderForm.extendedHours}
                      onChange={(e) =>
                        setOrderForm({
                          ...orderForm,
                          extendedHours: e.target.checked,
                        })
                      }
                    />
                  }
                  label="Extended Hours Trading"
                />
              </Grid>

              <Grid item xs={12}>
                <TextField
                  label="Notes"
                  multiline
                  rows={3}
                  value={orderForm.notes}
                  onChange={(e) =>
                    setOrderForm({ ...orderForm, notes: e.target.value })
                  }
                  fullWidth
                  placeholder="Optional notes about this order..."
                />
              </Grid>
            </Grid>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setOrderDialogOpen(false)}>Cancel</Button>
            <Button variant="contained" onClick={handleSubmitOrder}>
              {selectedOrder ? "Modify Order" : "Preview Order"}
            </Button>
          </DialogActions>
        </Dialog>

        {/* Order Confirmation Dialog */}
        <Dialog
          open={confirmDialogOpen}
          onClose={() => setConfirmDialogOpen(false)}
          maxWidth="sm"
          fullWidth
        >
          <DialogTitle>Order Confirmation</DialogTitle>
          <DialogContent>
            {orderPreview && (
              <Box>
                <Typography variant="h6" gutterBottom>
                  {orderPreview.side.toUpperCase()} {orderPreview.quantity}{" "}
                  {orderPreview.symbol}
                </Typography>

                <Grid container spacing={2}>
                  <Grid item xs={6}>
                    <Typography variant="body2" color="text.secondary">
                      Estimated Price:
                    </Typography>
                    <Typography variant="body1">
                      {formatCurrency(orderPreview.estimatedPrice)}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="body2" color="text.secondary">
                      Estimated Value:
                    </Typography>
                    <Typography variant="body1">
                      {formatCurrency(orderPreview.estimatedValue)}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="body2" color="text.secondary">
                      Commission:
                    </Typography>
                    <Typography variant="body1">
                      {formatCurrency(orderPreview.estimatedCommission)}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="body2" color="text.secondary">
                      Buying Power Required:
                    </Typography>
                    <Typography variant="body1">
                      {formatCurrency(orderPreview.buyingPowerRequired)}
                    </Typography>
                  </Grid>
                </Grid>

                {orderPreview.warningMessages?.length > 0 && (
                  <Alert severity="warning" sx={{ mt: 2 }}>
                    {orderPreview.warningMessages.join(". ")}
                  </Alert>
                )}

                <Box sx={{ mt: 2 }}>
                  <Typography variant="body2" color="text.secondary">
                    Risk Assessment: {orderPreview.riskAssessment}
                  </Typography>
                </Box>
              </Box>
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setConfirmDialogOpen(false)}>Cancel</Button>
            <Button variant="contained" color="primary" onClick={confirmOrder}>
              Confirm Order
            </Button>
          </DialogActions>
        </Dialog>
      </Container>
    </LocalizationProvider>
  );
};

export default OrderManagement;
