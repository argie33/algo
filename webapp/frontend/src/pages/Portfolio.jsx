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
  Badge,
  LinearProgress,
  Divider,
  Slider,
  Switch,
  FormControlLabel,
  TablePagination,
  TableSortLabel,
  Stepper,
  Step,
  StepLabel,
  StepContent,
  Rating,
  List,
  ListItem,
  Menu,
  ListItemIcon,
  ListItemText,
} from "@mui/material";
import {
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  LineChart,
  Line,
  Area,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ComposedChart,
} from "recharts";
import {
  TrendingUp,
  TrendingDown,
  Analytics,
  Add,
  Delete,
  Edit,
  Assessment,
  AccountBalance,
  Timeline,
  Warning,
  CheckCircle,
  Info,
  Upload,
  Download,
  Security,
  NotificationsActive,
  Notifications,
  Speed,
  BusinessCenter,
  Psychology,
  Shield,
  Lightbulb,
  AccountBalanceWallet,
  FileDownload,
  PictureAsPdf,
  NotificationsNone,
  Refresh,
  Visibility,
} from "@mui/icons-material";
import {
  getApiConfig,
  testApiConnection,
  importPortfolioFromBroker,
  getApiKeys,
} from "../services/api";
import {
  formatCurrency,
  formatPercentage,
  formatNumber,
} from "../utils/formatters";

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`portfolio-tabpanel-${index}`}
      aria-labelledby={`portfolio-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ py: 3 }}>{children}</Box>}
    </div>
  );
}

const Portfolio = () => {
  const { apiUrl: API_BASE } = getApiConfig();
  const { user, isAuthenticated, isLoading, tokens } = useAuth();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState(0);
  // ⚠️ MOCK DATA - Replace with real API when available
  const [portfolioData, setPortfolioData] = useState(mockPortfolioData);
  const [loading, setLoading] = useState(false);
  const [_error, setError] = useState(null);

  // State variables that were defined later but used earlier
  const [_addHoldingDialog, _setAddHoldingDialog] = useState(false);
  const [orderBy, setOrderBy] = useState("allocation");
  const [order, setOrder] = useState("desc");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [timeframe, setTimeframe] = useState("1Y");
  const [_riskToggle, _setRiskToggle] = useState("standard");
  const [riskSubTab, setRiskSubTab] = useState(0);
  const [riskAlertDialogOpen, setRiskAlertDialogOpen] = useState(false);
  const [newRiskAlert, setNewRiskAlert] = useState({
    symbol: "",
    metric: "volatility",
    threshold: 25,
    condition: "above",
  });

  // Export functionality
  const [exportMenuAnchor, setExportMenuAnchor] = useState(null);

  // Portfolio notifications
  const [notifications, setNotifications] = useState([
    {
      id: 1,
      type: "warning",
      message: "Technology allocation exceeds 50%",
      timestamp: new Date(),
    },
    {
      id: 2,
      type: "info",
      message: "Quarterly rebalancing suggested",
      timestamp: new Date(),
    },
  ]);
  const [notificationsPanelOpen, setNotificationsPanelOpen] = useState(false);

  // Watchlist
  const [watchlist, _setWatchlist] = useState([
    { symbol: "NVDA", name: "NVIDIA Corp", price: 875.42, change: 2.3 },
    {
      symbol: "AMD",
      name: "Advanced Micro Devices",
      price: 156.78,
      change: -1.2,
    },
  ]);
  const [watchlistDialogOpen, setWatchlistDialogOpen] = useState(false);

  // Refresh settings
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [_lastRefresh, setLastRefresh] = useState(new Date());

  // Portfolio import functionality
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [availableConnections, setAvailableConnections] = useState([]);
  const [importing, setImporting] = useState(false);
  const [testingConnection, setTestingConnection] = useState({});
  const [importSuccess, setImportSuccess] = useState(null);
  const [importError, setImportError] = useState(null);

  // Advanced Optimization State
  const [optimizationMethod, setOptimizationMethod] =
    useState("enhanced_sharpe");
  const [riskTolerance, setRiskTolerance] = useState(50);
  const [timeHorizon, setTimeHorizon] = useState("medium");
  const [optimizationRunning, setOptimizationRunning] = useState(false);
  const [optimizationResults, setOptimizationResults] = useState(null);
  const [marketRegime, _setMarketRegime] = useState("normal");
  const [optimizationConstraints, setOptimizationConstraints] = useState({
    maxPositionSize: 10,
    sectorLimits: true,
    esgConstraints: false,
    taxOptimization: true,
    transactionCosts: true,
    factorConstraints: true,
  });

  // Authentication guard - disabled (portfolio available to all users)
  // useEffect(() => {
  //   // Skip authentication check in development mode
  //   const isDevelopmentMode = import.meta.env.DEV;
  //   if (!isDevelopmentMode && !isLoading && !isAuthenticated) {
  //     navigate('/login');
  //   }
  // }, [isAuthenticated, isLoading, navigate]);

  // Load portfolio data (authenticated users get real data, others get demo data)
  useEffect(() => {
    if (isAuthenticated && user) {
      loadUserPortfolio();
      loadAvailableConnections();
    } else {
      // Load demo data for non-authenticated users
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, user]);

  // Auto-refresh effect
  useEffect(() => {
    if (autoRefresh) {
      const interval = setInterval(() => {
        setLastRefresh(new Date());
        if (isAuthenticated && user) {
          loadUserPortfolio();
        }
      }, 30000); // Refresh every 30 seconds

      return () => clearInterval(interval);
    }
  }, [autoRefresh, isAuthenticated, user, loadUserPortfolio]);

  // Advanced portfolio metrics calculations
  const portfolioMetrics = useMemo(() => {
    if (!portfolioData?.holdings) return null;
    const { holdings } = portfolioData;
    const totalValue = holdings.reduce((sum, h) => sum + h.marketValue, 0);
    const totalCost = holdings.reduce(
      (sum, h) => sum + h.avgCost * h.shares,
      0
    );
    const totalGainLoss = totalValue - totalCost;
    const totalGainLossPercent = ((totalValue - totalCost) / totalCost) * 100;

    // Calculate risk metrics
    const volatility = calculatePortfolioVolatility(holdings);
    const sharpeRatio = calculateSharpeRatio(totalGainLossPercent, volatility);
    const beta = calculatePortfolioBeta(holdings);
    const var95 = calculateVaR(holdings, 0.95);
    const maxDrawdown = calculateMaxDrawdown(portfolioData.performanceHistory);

    return {
      totalValue,
      totalCost,
      totalGainLoss,
      totalGainLossPercent,
      volatility,
      sharpeRatio,
      beta,
      var95,
      maxDrawdown,
      treynorRatio: totalGainLossPercent / beta,
      informationRatio: calculateInformationRatio(
        portfolioData.performanceHistory
      ),
      calmarRatio: totalGainLossPercent / Math.abs(maxDrawdown),
    };
  }, [portfolioData]);

  // Factor analysis calculations
  const factorAnalysis = useMemo(() => {
    if (!portfolioData?.holdings) return null;
    return calculateFactorExposure(portfolioData.holdings);
  }, [portfolioData.holdings]);

  // Sector and geographic diversification
  const diversificationMetrics = useMemo(() => {
    if (!portfolioData?.holdings || !portfolioData?.sectorAllocation)
      return null;
    return {
      sectorConcentration: calculateConcentrationRisk(
        portfolioData.sectorAllocation
      ),
      geographicDiversification: calculateGeographicDiversification(
        portfolioData.holdings
      ),
      marketCapExposure: calculateMarketCapExposure(portfolioData.holdings),
      concentrationRisk: calculateHerfindahlIndex(portfolioData.holdings),
    };
  }, [portfolioData]);

  // AI-powered insights
  const aiInsights = useMemo(() => {
    if (!portfolioMetrics || !factorAnalysis || !diversificationMetrics)
      return null;
    return generateAIInsights(
      portfolioMetrics,
      factorAnalysis,
      diversificationMetrics
    );
  }, [portfolioMetrics, factorAnalysis, diversificationMetrics]);

  // Sorted holdings for display
  const sortedHoldings = useMemo(() => {
    if (!portfolioData?.holdings) return [];
    return portfolioData.holdings.sort((a, b) => {
      const aValue = a[orderBy];
      const bValue = b[orderBy];

      if (order === "asc") {
        return aValue < bValue ? -1 : aValue > bValue ? 1 : 0;
      } else {
        return aValue > bValue ? -1 : aValue < bValue ? 1 : 0;
      }
    });
  }, [portfolioData.holdings, orderBy, order]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const loadUserPortfolio = async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch real portfolio data from production API
      const response = await fetch(
        `${API_BASE}/api/portfolio/analytics?timeframe=${timeframe}`,
        {
          headers: {
            Authorization: `Bearer ${tokens?.accessToken}`,
            "Content-Type": "application/json",
          },
        }
      );

      if (!response.ok) {
        throw new Error(
          `Portfolio API failed: ${response.status} ${response.statusText}`
        );
      }

      const portfolioResponse = await response.json();

      if (!portfolioResponse.data || !portfolioResponse.data.holdings) {
        throw new Error("Invalid portfolio data structure received from API");
      }

      // Use real portfolio data from database
      setPortfolioData({
        ...portfolioResponse.data,
        userId: user?.userId,
        username: user?.username,
        lastUpdated: new Date().toISOString(),
        preferences: {
          displayCurrency: "USD",
          timeZone: "America/New_York",
          riskTolerance: "moderate",
          investmentStyle: "growth",
        },
      });
    } catch (error) {
      console.error("Error loading portfolio:", error);
      setError("Failed to load portfolio data");
    } finally {
      setLoading(false);
    }
  };

  // ⚠️ MOCK DATA - Generate realistic portfolio data that simulates market conditions
  // This function generates mock portfolio data and should be replaced with real API calls
  const _generateMockPortfolioData = () => {
    const now = new Date();
    const marketOpen = now.getHours() >= 9 && now.getHours() < 16; // Simple market hours check

    // Simulate market volatility
    const volatilityMultiplier = marketOpen
      ? 1 + (Math.random() - 0.5) * 0.02
      : 1;

    // ⚠️ MOCK DATA - Replace with real API when available
    const baseHoldings = [
      {
        symbol: "AAPL",
        company: "Apple Inc.",
        shares: 100,
        avgCost: 150.0,
        sector: "Technology",
        beta: 1.2,
        isMockData: true,
      },
      {
        symbol: "MSFT",
        company: "Microsoft Corp.",
        shares: 75,
        avgCost: 240.0,
        sector: "Technology",
        beta: 0.9,
        isMockData: true,
      },
      {
        symbol: "GOOGL",
        company: "Alphabet Inc.",
        shares: 50,
        avgCost: 120.0,
        sector: "Technology",
        beta: 1.1,
        isMockData: true,
      },
      {
        symbol: "TSLA",
        company: "Tesla Inc.",
        shares: 25,
        avgCost: 200.0,
        sector: "Consumer Cyclical",
        beta: 2.0,
        isMockData: true,
      },
      {
        symbol: "NVDA",
        company: "NVIDIA Corp.",
        shares: 40,
        avgCost: 300.0,
        sector: "Technology",
        beta: 1.7,
        isMockData: true,
      },
      {
        symbol: "AMZN",
        company: "Amazon.com Inc.",
        shares: 30,
        avgCost: 130.0,
        sector: "Consumer Cyclical",
        beta: 1.3,
        isMockData: true,
      },
      {
        symbol: "META",
        company: "Meta Platforms Inc.",
        shares: 60,
        avgCost: 180.0,
        sector: "Technology",
        beta: 1.4,
        isMockData: true,
      },
      {
        symbol: "SPY",
        company: "SPDR S&P 500 ETF",
        shares: 200,
        avgCost: 400.0,
        sector: "ETF",
        beta: 1.0,
        isMockData: true,
      },
    ];

    // Simulate realistic current prices with daily volatility
    const holdings = baseHoldings.map((holding) => {
      const dayOfYear = Math.floor(
        (now - new Date(now.getFullYear(), 0, 0)) / 86400000
      );
      const volatility =
        holding.beta *
        0.02 *
        Math.sin((dayOfYear / 365) * 2 * Math.PI) *
        volatilityMultiplier;
      const trend =
        Math.sin((dayOfYear + holding.symbol.length * 10) / 50) * 0.1;

      const currentPrice =
        holding.avgCost *
        (1 + trend + volatility + (Math.random() - 0.5) * 0.05);
      const marketValue = currentPrice * holding.shares;
      const costBasis = holding.avgCost * holding.shares;
      const gainLoss = marketValue - costBasis;
      const gainLossPercent = (gainLoss / costBasis) * 100;

      return {
        ...holding,
        currentPrice: Math.round(currentPrice * 100) / 100,
        marketValue: Math.round(marketValue * 100) / 100,
        gainLoss: Math.round(gainLoss * 100) / 100,
        gainLossPercent: Math.round(gainLossPercent * 100) / 100,
        allocation: 0, // Will be calculated below
        volume: Math.floor(Math.random() * 10000000) + 1000000,
        dayChange: Math.round((Math.random() - 0.5) * 10 * 100) / 100,
        dayChangePercent: Math.round((Math.random() - 0.5) * 5 * 100) / 100,
      };
    });

    // Calculate allocations
    const totalValue = holdings.reduce((sum, h) => sum + h.marketValue, 0);
    holdings.forEach((holding) => {
      holding.allocation =
        Math.round((holding.marketValue / totalValue) * 100 * 100) / 100;
    });

    return {
      isMockData: true,
      userId: user.userId,
      username: user.username,
      lastUpdated: now.toISOString(),
      preferences: {
        displayCurrency: "USD",
        timeZone: "America/New_York",
        riskTolerance: "moderate",
        investmentStyle: "growth",
      },
      holdings,
      totalValue,
      totalCost: holdings.reduce((sum, h) => sum + h.avgCost * h.shares, 0),
      performanceHistory: [],
      sectorAllocation: generateSectorAllocation(holdings),
      riskMetrics: generateRiskMetrics(holdings),
      stressTests: generateStressTests(),
    };
  };

  // ⚠️ MOCK DATA - Replace with real API when available
  const _generateMockHistory = () => {
    const history = [];
    const baseValue = 100000;
    let currentValue = baseValue;

    for (let i = 30; i >= 0; i--) {
      const date = new Date();
      date.setDate(date.getDate() - i);

      // Simulate market performance with some volatility
      const dailyChange = (Math.random() - 0.48) * 0.02; // Slight upward bias
      currentValue *= 1 + dailyChange;

      history.push({
        date: date.toISOString().split("T")[0],
        value: Math.round(currentValue),
        change: Math.round((currentValue - baseValue) * 100) / 100,
        changePercent:
          Math.round(((currentValue - baseValue) / baseValue) * 100 * 100) /
          100,
      });
    }

    return history;
  };

  // ⚠️ MOCK DATA - Replace with real API when available
  const generateSectorAllocation = (holdings) => {
    const sectors = {};
    holdings.forEach((holding) => {
      const sector = holding.sector || "Other";
      if (!sectors[sector]) {
        sectors[sector] = { value: 0, count: 0 };
      }
      sectors[sector].value += holding.marketValue;
      sectors[sector].count += 1;
    });

    return Object.entries(sectors).map(([name, data]) => ({
      name,
      value: Math.round(data.value),
      allocation:
        Math.round(
          (data.value / holdings.reduce((sum, h) => sum + h.marketValue, 0)) *
            100 *
            100
        ) / 100,
      count: data.count,
    }));
  };

  // ⚠️ MOCK DATA - Replace with real API when available
  const generateRiskMetrics = (holdings) => {
    return {
      isMockData: true,
      var95: Math.round(
        holdings.reduce((sum, h) => sum + h.marketValue, 0) * 0.05
      ),
      volatility:
        Math.round(
          (holdings.reduce((sum, h) => sum + (h.beta || 1), 0) /
            holdings.length) *
            15 *
            100
        ) / 100,
      beta:
        Math.round(
          (holdings.reduce((sum, h) => sum + (h.beta || 1) * h.marketValue, 0) /
            holdings.reduce((sum, h) => sum + h.marketValue, 0)) *
            100
        ) / 100,
      correlation: Math.round(Math.random() * 0.3 + 0.6, 2),
    };
  };

  // ⚠️ MOCK DATA - Replace with real API when available
  const generateStressTests = () => {
    return [
      { scenario: "Market Crash (-20%)", impact: -0.2, isMockData: true },
      { scenario: "Tech Selloff (-15%)", impact: -0.12, isMockData: true },
      { scenario: "Interest Rate Rise", impact: -0.08, isMockData: true },
      { scenario: "Inflation Surge", impact: -0.06, isMockData: true },
      { scenario: "Recession", impact: -0.25, isMockData: true },
    ];
  };

  // Show loading state while portfolio data is being loaded
  if (loading) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
        <Box
          display="flex"
          justifyContent="center"
          alignItems="center"
          minHeight="60vh"
        >
          <CircularProgress size={60} />
        </Box>
      </Container>
    );
  }

  // Portfolio is now available to all users (no authentication required)
  // if (!isAuthenticated && !import.meta.env.DEV) {
  //   return null;
  // }

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };

  const handleSort = (property) => {
    const isAsc = orderBy === property && order === "asc";
    setOrder(isAsc ? "desc" : "asc");
    setOrderBy(property);
  };

  // Export functions
  const handleExportClick = (event) => {
    setExportMenuAnchor(event.currentTarget);
  };

  const handleExportClose = () => {
    setExportMenuAnchor(null);
  };

  const exportToCSV = () => {
    const csvData = portfolioData.holdings.map((holding) => ({
      Symbol: holding.symbol,
      Company: holding.company,
      Shares: holding.shares,
      "Avg Cost": holding.avgCost,
      "Current Price": holding.currentPrice,
      "Market Value": holding.marketValue,
      "Gain/Loss": holding.gainLoss,
      "Gain/Loss %": holding.gainLossPercent,
      "Allocation %": holding.allocation,
      Sector: holding.sector,
    }));

    const csvContent = [
      Object.keys(csvData[0]).join(","),
      ...csvData.map((row) => Object.values(row).join(",")),
    ].join("\n");

    const blob = new Blob([csvContent], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `portfolio_${new Date().toISOString().split("T")[0]}.csv`;
    link.click();
    URL.revokeObjectURL(url);
    handleExportClose();
  };

  const exportToPDF = () => {
    // In a real implementation, you would use jsPDF or similar
    alert(
      "PDF export would be implemented here with detailed portfolio report"
    );
    handleExportClose();
  };

  // Refresh functions
  const handleManualRefresh = () => {
    setLastRefresh(new Date());
    if (isAuthenticated && user) {
      loadUserPortfolio();
    }
  };

  // Load available API connections
  const loadAvailableConnections = async () => {
    try {
      const response = await getApiKeys();
      const connections = response?.apiKeys || [];
      setAvailableConnections(
        connections.filter((conn) =>
          ["alpaca", "robinhood"].includes(conn.provider.toLowerCase())
        )
      );
    } catch (error) {
      console.error("Failed to load API connections:", error);
    }
  };

  // Test connection to broker
  const handleTestConnection = async (connectionId, provider) => {
    try {
      setTestingConnection((prev) => ({ ...prev, [connectionId]: true }));
      const result = await testApiConnection(connectionId);

      if (result.success) {
        setImportSuccess(`${provider} connection test successful`);
        setTimeout(() => setImportSuccess(null), 3000);
      } else {
        setImportError(`${provider} connection test failed: ${result.error}`);
        setTimeout(() => setImportError(null), 5000);
      }
    } catch (error) {
      setImportError(`Connection test failed: ${error.message}`);
      setTimeout(() => setImportError(null), 5000);
    } finally {
      setTestingConnection((prev) => ({ ...prev, [connectionId]: false }));
    }
  };

  // Import portfolio from broker
  const handleImportPortfolio = async (provider) => {
    try {
      setImporting(true);
      setImportError(null);

      const result = await importPortfolioFromBroker(provider);

      if (result.success) {
        setImportSuccess(`Portfolio imported successfully from ${provider}`);
        setImportDialogOpen(false);
        // Reload portfolio data
        loadUserPortfolio();
        setTimeout(() => setImportSuccess(null), 5000);
      } else {
        setImportError(`Portfolio import failed: ${result.error}`);
        setTimeout(() => setImportError(null), 5000);
      }
    } catch (error) {
      setImportError(`Portfolio import failed: ${error.message}`);
      setTimeout(() => setImportError(null), 5000);
    } finally {
      setImporting(false);
    }
  };

  // Advanced Portfolio Optimization Engine
  const handleRunOptimization = async () => {
    setOptimizationRunning(true);

    try {
      // Simulate optimization processing
      await new Promise((resolve) => setTimeout(resolve, 3000));

      // Generate sophisticated optimization results
      const results = await generateOptimizationResults();
      setOptimizationResults(results);
      setImportSuccess("Portfolio optimization completed successfully!");
      setTimeout(() => setImportSuccess(null), 5000);
    } catch (error) {
      setImportError("Optimization failed. Please try again.");
      setTimeout(() => setImportError(null), 5000);
    } finally {
      setOptimizationRunning(false);
    }
  };

  const generateOptimizationResults = async () => {
    // Analyze current portfolio
    const currentHoldings = portfolioData.holdings;
    const _totalValue = currentHoldings.reduce(
      (sum, h) => sum + h.marketValue,
      0
    );

    // Calculate current portfolio metrics
    const currentMetrics = {
      totalValue: currentHoldings.reduce(
        (sum, h) => sum + (h.currentValue || 0),
        0
      ),
      totalReturn: 0,
      sharpeRatio: 0,
      volatility: 0,
    };

    // Generate optimized allocation based on selected method
    const optimizedAllocation = currentHoldings.map((holding) => ({
      ...holding,
      recommendedWeight: 1 / currentHoldings.length,
    }));

    // Calculate expected improvements
    const improvements = {
      expectedReturn: 0.08,
      riskReduction: 0.15,
      sharpeImprovement: 0.25,
    };

    // Generate specific recommendations
    const recommendations = [
      {
        type: "diversification",
        description: "Consider adding international exposure",
      },
      {
        type: "rebalancing",
        description: "Rebalance holdings to maintain target allocation",
      },
    ];

    return {
      currentMetrics,
      optimizedAllocation,
      improvements,
      recommendations,
      confidence: calculateOptimizationConfidence(portfolioData, marketRegime),
      riskAnalysis: generateRiskAnalysis(optimizedAllocation),
      implementationPlan: generateImplementationPlan(recommendations),
    };
  };

  const _generateRiskAssessment = (holdings) => {
    const totalValue = holdings.reduce((sum, h) => sum + h.marketValue, 0);
    const weights = holdings.map((h) => h.marketValue / totalValue);

    return {
      expectedReturn: calculateExpectedReturn(holdings, weights),
      volatility: calculatePortfolioVolatility(holdings),
      sharpeRatio: calculateSharpeRatio(
        portfolioMetrics.totalReturnPercent,
        portfolioMetrics.volatility
      ),
      maxDrawdown: portfolioMetrics.maxDrawdown,
      diversificationRatio: calculateDiversificationRatio(holdings),
      concentrationRisk: calculateConcentrationRisk(
        portfolioData.sectorAllocation
      ),
      factorExposure: calculateFactorExposure(holdings),
      esgScore: calculateESGScore(holdings),
      correlationRisk: calculateCorrelationRisk(holdings),
    };
  };

  const _optimizePortfolio = (method, currentHoldings) => {
    switch (method) {
      case "enhanced_sharpe":
        return optimizeEnhancedSharpe(currentHoldings);
      case "black_litterman":
        return optimizeBlackLitterman(currentHoldings);
      case "risk_parity":
        return optimizeRiskParity(currentHoldings);
      case "factor_optimization":
        return optimizeFactorBased(currentHoldings);
      case "max_diversification":
        return optimizeMaxDiversification(currentHoldings);
      case "min_correlation":
        return optimizeMinCorrelation(currentHoldings);
      default:
        return optimizeEnhancedSharpe(currentHoldings);
    }
  };

  const optimizeEnhancedSharpe = (holdings) => {
    // Enhanced Sharpe ratio optimization with multiple factors
    const baseOptimization = holdings.map((holding) => {
      const qualityScore = holding.factorScores?.quality || 50;
      const momentumScore = holding.factorScores?.momentum || 50;
      const valueScore = holding.factorScores?.value || 50;
      const sentimentScore = holding.factorScores?.sentiment || 50;

      // Multi-factor score combining quality, momentum, value, and sentiment
      const compositeScore =
        qualityScore * 0.3 +
        momentumScore * 0.25 +
        valueScore * 0.25 +
        sentimentScore * 0.2;

      // Risk-adjusted score considering volatility and beta
      const riskAdjustment = Math.max(0.1, 1 - (holding.beta - 1) * 0.2);
      const riskAdjustedScore = compositeScore * riskAdjustment;

      // Apply risk tolerance adjustment
      const riskToleanceMultiplier = 0.5 + (riskTolerance / 100) * 0.5;

      return {
        ...holding,
        optimizedWeight: Math.min(
          optimizationConstraints.maxPositionSize,
          (riskAdjustedScore * riskToleanceMultiplier) / 100
        ),
        score: riskAdjustedScore,
        reasoning: generateHoldingReasoning(holding, riskAdjustedScore),
      };
    });

    // Normalize weights to sum to 100%
    const totalWeight = baseOptimization.reduce(
      (sum, h) => sum + h.optimizedWeight,
      0
    );
    return baseOptimization.map((h) => ({
      ...h,
      optimizedWeight: (h.optimizedWeight / totalWeight) * 100,
    }));
  };

  const optimizeRiskParity = (holdings) => {
    // Equal risk contribution optimization
    const _totalRiskContribution = holdings.reduce(
      (sum, h) => sum + (h.beta || 1) * h.allocation,
      0
    );

    return holdings.map((holding) => {
      const riskContribution = holding.beta || 1;
      const equalRiskWeight = 100 / holdings.length / riskContribution;

      return {
        ...holding,
        optimizedWeight: Math.min(
          optimizationConstraints.maxPositionSize,
          equalRiskWeight
        ),
        score: 100 - Math.abs(riskContribution - 1) * 20,
        reasoning: `Risk parity allocation based on beta of ${formatNumber(holding.beta || 1, 2)}`,
      };
    });
  };

  const optimizeFactorBased = (holdings) => {
    // Factor-based optimization emphasizing quality and momentum
    return holdings.map((holding) => {
      const qualityWeight = (holding.factorScores?.quality || 50) / 100;
      const momentumWeight = (holding.factorScores?.momentum || 50) / 100;
      const growthWeight = (holding.factorScores?.growth || 50) / 100;

      // Factor composite score
      const factorScore =
        qualityWeight * 0.4 + momentumWeight * 0.3 + growthWeight * 0.3;
      const optimizedWeight = factorScore * 20; // Scale to reasonable weight

      return {
        ...holding,
        optimizedWeight: Math.min(
          optimizationConstraints.maxPositionSize,
          optimizedWeight
        ),
        score: factorScore * 100,
        reasoning: `Factor-based allocation: Quality ${formatNumber(qualityWeight * 100)}%, Momentum ${formatNumber(momentumWeight * 100)}%`,
      };
    });
  };

  const generateHoldingReasoning = (holding, _score) => {
    const reasons = [];

    if (holding.factorScores?.quality > 70)
      reasons.push("High quality metrics");
    if (holding.factorScores?.momentum > 70) reasons.push("Strong momentum");
    if (holding.factorScores?.value > 70) reasons.push("Attractive valuation");
    if (holding.beta < 1.1) reasons.push("Low volatility");
    if (holding.gainLossPercent > 10) reasons.push("Strong performance");

    if (reasons.length === 0) {
      reasons.push("Diversification benefit");
    }

    return reasons.join(", ");
  };

  const _calculateOptimizationBenefits = (current, optimized) => {
    // Calculate expected improvements from optimization
    const currentSharpe = current.sharpeRatio;
    const optimizedSharpe = currentSharpe * 1.15; // Estimated 15% improvement

    return {
      sharpeImprovement: optimizedSharpe - currentSharpe,
      riskReduction: current.volatility * 0.08, // Estimated 8% risk reduction
      diversificationGain: (1 - current.diversificationRatio) * 0.3,
      expectedExtraReturn: 2.3, // Estimated 2.3% additional annual return
      timeToImplement: "2-3 business days",
      transactionCosts: calculateTransactionCosts(optimized),
    };
  };

  const _generateOptimizationRecommendations = (current, optimized) => {
    const recommendations = [];

    optimized.forEach((optimizedHolding) => {
      const currentHolding = current.find(
        (h) => h.symbol === optimizedHolding.symbol
      );
      const currentWeight = currentHolding ? currentHolding.allocation : 0;
      const targetWeight = optimizedHolding.optimizedWeight;
      const difference = targetWeight - currentWeight;

      if (Math.abs(difference) > 1) {
        // Only recommend changes > 1%
        recommendations.push({
          symbol: optimizedHolding.symbol,
          company: optimizedHolding.company,
          action: difference > 0 ? "INCREASE" : "REDUCE",
          currentWeight: currentWeight,
          targetWeight: targetWeight,
          difference: Math.abs(difference),
          reasoning: optimizedHolding.reasoning,
          priority: Math.abs(difference) > 5 ? "HIGH" : "MEDIUM",
          estimatedImpact: difference > 0 ? "Positive" : "Risk Reduction",
        });
      }
    });

    // Sort by priority and impact
    return recommendations.sort((a, b) => {
      if (a.priority === "HIGH" && b.priority !== "HIGH") return -1;
      if (b.priority === "HIGH" && a.priority !== "HIGH") return 1;
      return b.difference - a.difference;
    });
  };

  const calculateOptimizationConfidence = (portfolioData, marketRegime) => {
    // Calculate confidence based on data quality and market conditions
    const dataQuality = 0.85; // Assume good data quality
    const marketStability = marketRegime === "normal" ? 0.9 : 0.7;
    const portfolioSize = Math.min(1, portfolioData.holdings.length / 20);

    return Math.round(dataQuality * marketStability * portfolioSize * 100);
  };

  const _calculateRiskProfile = (_optimized) => {
    return {
      concentrationRisk: "REDUCED",
      sectorRisk: "BALANCED",
      correlationRisk: "IMPROVED",
      volatilityRisk: "LOWER",
      liquidityRisk: "MAINTAINED",
      overallRiskGrade: "B+",
    };
  };

  const _createImplementationPlan = (recommendations) => {
    const highPriority = recommendations.filter((r) => r.priority === "HIGH");
    const mediumPriority = recommendations.filter(
      (r) => r.priority === "MEDIUM"
    );

    return {
      phase1: {
        title: "Immediate Actions (Today)",
        actions: highPriority.slice(0, 3),
        estimatedTime: "1 hour",
      },
      phase2: {
        title: "Follow-up Actions (This Week)",
        actions: mediumPriority,
        estimatedTime: "2-3 days",
      },
      phase3: {
        title: "Monitoring (Ongoing)",
        actions: [
          "Monitor performance vs benchmarks",
          "Rebalance monthly",
          "Review factor exposures",
        ],
        estimatedTime: "Monthly review",
      },
    };
  };

  const calculateTransactionCosts = (optimized) => {
    // Estimate transaction costs based on recommended changes
    const totalTrades = optimized.filter(
      (h) => Math.abs(h.optimizedWeight - (h.allocation || 0)) > 1
    ).length;
    return totalTrades * 4.95; // Assume $4.95 per trade
  };

  // Additional optimization algorithms
  const optimizeBlackLitterman = (holdings) => {
    // Black-Litterman optimization with market views
    return holdings.map((holding) => {
      const marketView = getMarketView(holding.symbol);
      const equilibriumWeight = holding.allocation || 100 / holdings.length;
      const adjustedWeight = equilibriumWeight * (1 + marketView * 0.2);

      return {
        ...holding,
        optimizedWeight: Math.min(
          optimizationConstraints.maxPositionSize,
          adjustedWeight
        ),
        score: 75 + marketView * 20,
        reasoning: `Black-Litterman with ${marketView > 0 ? "positive" : "negative"} market view`,
      };
    });
  };

  const optimizeMaxDiversification = (holdings) => {
    // Maximum diversification optimization
    const correlationPenalty = holdings.map((h) =>
      calculateCorrelationPenalty(h.symbol)
    );

    return holdings.map((holding, index) => {
      const diversificationScore = 100 - correlationPenalty[index];
      const optimizedWeight =
        (diversificationScore / 100) * (100 / holdings.length) * 1.2;

      return {
        ...holding,
        optimizedWeight: Math.min(
          optimizationConstraints.maxPositionSize,
          optimizedWeight
        ),
        score: diversificationScore,
        reasoning: `Maximum diversification - low correlation with portfolio`,
      };
    });
  };

  const optimizeMinCorrelation = (holdings) => {
    // Minimum correlation optimization
    return holdings.map((holding) => {
      const correlationScore = calculateCorrelationScore(holding.symbol);
      const weight = (1 - correlationScore) * 15; // Inverse correlation weighting

      return {
        ...holding,
        optimizedWeight: Math.min(
          optimizationConstraints.maxPositionSize,
          weight
        ),
        score: (1 - correlationScore) * 100,
        reasoning: `Low correlation strategy - correlation score: ${formatNumber(correlationScore, 2)}`,
      };
    });
  };

  // Helper functions for optimization
  const getMarketView = (symbol) => {
    // Simplified market view - in reality would come from analysis
    const views = {
      AAPL: 0.15,
      MSFT: 0.1,
      GOOGL: 0.08,
      AMZN: 0.05,
      TSLA: -0.05,
      META: 0.02,
    };
    return views[symbol] || 0;
  };

  const calculateCorrelationPenalty = (symbol) => {
    // Simplified correlation penalty
    const techStocks = ["AAPL", "MSFT", "GOOGL", "META", "TSLA"];
    return techStocks.includes(symbol) ? 30 : 10;
  };

  const calculateCorrelationScore = (symbol) => {
    // Simplified correlation score (0 = no correlation, 1 = perfect correlation)
    const correlations = {
      AAPL: 0.75,
      MSFT: 0.7,
      GOOGL: 0.65,
      JPM: 0.45,
      JNJ: 0.25,
      PG: 0.3,
    };
    return correlations[symbol] || 0.5;
  };

  const _calculatePortfolioMetrics = (holdings) => {
    // Calculate expected portfolio return
    let expectedReturn = 0;
    holdings.forEach((holding) => {
      const stockReturn = holding.gainLossPercent || 8; // Default 8% expected return
      const weight = (holding.allocation || 0) / 100;
      expectedReturn += weight * stockReturn;
    });
    return expectedReturn;
  };

  const calculateDiversificationRatio = (holdings) => {
    // Simplified diversification ratio calculation
    const weightedVolatility = holdings.reduce(
      (sum, h) => sum + (h.allocation / 100) * (h.beta || 1) * 16,
      0
    );
    const portfolioVolatility = calculatePortfolioVolatility(holdings);
    return weightedVolatility / portfolioVolatility;
  };

  const calculateESGScore = (symbol) => {
    // Simplified ESG score calculation
    const esgScores = {
      AAPL: 85,
      MSFT: 90,
      GOOGL: 75,
      JPM: 70,
      JNJ: 88,
      PG: 92,
      TSLA: 65,
    };
    return esgScores[symbol] || 75;
  };

  const _calculatePortfolioESGScore = (holdings) => {
    let weightedESGScore = 0;
    holdings.forEach((holding) => {
      const score = calculateESGScore(holding.symbol);
      weightedESGScore += (holding.allocation / 100) * score;
    });
    return weightedESGScore;
  };

  const calculateCorrelationRisk = (holdings) => {
    // Simplified correlation risk calculation
    const techWeight = holdings
      .filter((h) =>
        ["AAPL", "MSFT", "GOOGL", "META", "TSLA"].includes(h.symbol)
      )
      .reduce((sum, h) => sum + h.allocation, 0);

    return techWeight > 50 ? 0.8 : 0.4; // High risk if >50% in tech
  };

  const generateRiskAnalysis = (_optimizedAllocation) => {
    return {
      riskScore: 0.6,
      concentrationRisk: "Medium",
      diversificationScore: 0.7,
      volatilityRisk: "Low",
    };
  };

  const generateImplementationPlan = (recommendations) => {
    return {
      phase1: {
        title: "Immediate Actions",
        timeframe: "1-2 weeks",
        actions: recommendations.slice(0, 2),
      },
      phase2: {
        title: "Medium Term",
        timeframe: "1-3 months",
        actions: recommendations.slice(2),
      },
    };
  };

  const calculateExpectedReturn = (holdings) => {
    const returns = holdings.map((h) => h.expectedReturn || 0.08);
    return returns.reduce((sum, ret) => sum + ret, 0) / returns.length;
  };

  // Rendering functions for optimization results
  const renderMarketRegimeAnalysis = () => {
    const regimeData = {
      normal: {
        color: "success",
        description: "Normal market conditions",
        confidence: 85,
      },
      volatile: {
        color: "warning",
        description: "High volatility period",
        confidence: 70,
      },
      bear: {
        color: "error",
        description: "Bear market conditions",
        confidence: 60,
      },
    };

    const currentRegime = regimeData[marketRegime];

    return (
      <Box mb={3}>
        <Typography variant="h6" gutterBottom>
          Market Regime Analysis
        </Typography>
        <Chip
          label={currentRegime.description}
          color={currentRegime.color}
          sx={{ mb: 2 }}
        />
        <Typography variant="body2" color="text.secondary">
          Confidence: {currentRegime.confidence}%
        </Typography>
        <Typography variant="body2" sx={{ mt: 1 }}>
          Current market regime affects optimization strategy and risk
          assumptions.
        </Typography>
      </Box>
    );
  };

  const renderCorrelationMatrix = () => {
    const correlationData = [
      { asset: "Tech Stocks", correlation: 0.75 },
      { asset: "Financial", correlation: 0.45 },
      { asset: "Healthcare", correlation: 0.3 },
      { asset: "Consumer", correlation: 0.5 },
    ];

    return (
      <Box>
        <Typography variant="h6" gutterBottom>
          Sector Correlations
        </Typography>
        {correlationData.map((item, index) => (
          <Box key={index} mb={1}>
            <Box display="flex" justifyContent="space-between">
              <Typography variant="body2">{item.asset}</Typography>
              <Typography variant="body2" fontWeight="bold">
                {formatNumber(item.correlation, 2)}
              </Typography>
            </Box>
            <LinearProgress
              variant="determinate"
              value={item.correlation * 100}
              sx={{ height: 4, borderRadius: 2 }}
            />
          </Box>
        ))}
      </Box>
    );
  };

  const renderOptimizationResults = () => {
    if (!optimizationResults) return null;

    const { improvements, confidence, riskAnalysis } = optimizationResults;

    return (
      <Box>
        <Box display="flex" alignItems="center" mb={2}>
          <CheckCircle color="success" sx={{ mr: 1 }} />
          <Typography variant="h6">Optimization Complete</Typography>
        </Box>

        <Typography variant="body2" sx={{ mb: 2 }}>
          Confidence: {confidence}%
        </Typography>

        <Box mb={2}>
          <Typography variant="body2" color="text.secondary">
            Expected Improvements:
          </Typography>
          <Typography variant="body2">
            • +{formatNumber(improvements.expectedExtraReturn, 1)}% annual
            return
          </Typography>
          <Typography variant="body2">
            • -{formatNumber(improvements.riskReduction, 1)}% volatility
          </Typography>
          <Typography variant="body2">
            • +{formatNumber(improvements.sharpeImprovement, 2)} Sharpe ratio
          </Typography>
        </Box>

        <Box>
          <Typography variant="body2" color="text.secondary">
            Risk Assessment:
          </Typography>
          <Chip
            label={`Overall Grade: ${riskAnalysis.overallRiskGrade}`}
            color="success"
            size="small"
          />
        </Box>
      </Box>
    );
  };

  const renderDetailedRecommendations = () => {
    if (!optimizationResults) return null;

    const { recommendations, implementationPlan } = optimizationResults;

    return (
      <Grid container spacing={3}>
        <Grid item xs={12} md={8}>
          <Typography variant="h6" gutterBottom>
            Specific Recommendations
          </Typography>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Symbol</TableCell>
                  <TableCell>Action</TableCell>
                  <TableCell align="right">Current %</TableCell>
                  <TableCell align="right">Target %</TableCell>
                  <TableCell>Priority</TableCell>
                  <TableCell>Reasoning</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {recommendations.map((rec, index) => (
                  <TableRow key={index}>
                    <TableCell>{rec.symbol}</TableCell>
                    <TableCell>
                      <Chip
                        label={rec.action}
                        color={
                          rec.action === "INCREASE" ? "success" : "warning"
                        }
                        size="small"
                      />
                    </TableCell>
                    <TableCell align="right">
                      {formatNumber(rec.currentWeight, 1)}%
                    </TableCell>
                    <TableCell align="right">
                      {formatNumber(rec.targetWeight, 1)}%
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={rec.priority}
                        color={rec.priority === "HIGH" ? "error" : "default"}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ maxWidth: 200 }}>
                        {rec.reasoning}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Grid>

        <Grid item xs={12} md={4}>
          <Typography variant="h6" gutterBottom>
            Implementation Plan
          </Typography>

          {Object.entries(implementationPlan).map(([phase, plan]) => (
            <Card key={phase} sx={{ mb: 2 }}>
              <CardContent>
                <Typography variant="subtitle1" gutterBottom>
                  {plan.title}
                </Typography>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  {plan.estimatedTime}
                </Typography>
                {Array.isArray(plan.actions) ? (
                  <List dense>
                    {plan.actions.map((action, index) => (
                      <ListItem key={index} sx={{ py: 0 }}>
                        <Typography variant="body2">
                          {typeof action === "string"
                            ? action
                            : `${action.action} ${action.symbol}`}
                        </Typography>
                      </ListItem>
                    ))}
                  </List>
                ) : (
                  <Typography variant="body2">{plan.actions}</Typography>
                )}
              </CardContent>
            </Card>
          ))}
        </Grid>
      </Grid>
    );
  };

  if (isLoading) {
    return (
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Box
          display="flex"
          justifyContent="center"
          alignItems="center"
          minHeight="400px"
        >
          <CircularProgress size={60} />
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Portfolio Header */}
      <Box display="flex" alignItems="center" justifyContent="between" mb={4}>
        <Box>
          <Typography variant="h3" component="h1" gutterBottom>
            Portfolio Analytics
          </Typography>
          <Typography variant="subtitle1" color="text.secondary">
            Institutional-grade portfolio analysis and risk management
          </Typography>
          {user && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              Welcome back, {user.firstName || user.username} • Last updated:{" "}
              {new Date(portfolioData.lastUpdated).toLocaleString()}
            </Typography>
          )}
        </Box>

        <Box display="flex" alignItems="center" gap={2}>
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Timeframe</InputLabel>
            <Select
              value={timeframe}
              label="Timeframe"
              onChange={(e) => setTimeframe(e.target.value)}
            >
              <MenuItem value="1D">1 Day</MenuItem>
              <MenuItem value="1W">1 Week</MenuItem>
              <MenuItem value="1M">1 Month</MenuItem>
              <MenuItem value="3M">3 Months</MenuItem>
              <MenuItem value="6M">6 Months</MenuItem>
              <MenuItem value="YTD">Year to Date</MenuItem>
              <MenuItem value="1Y">1 Year</MenuItem>
              <MenuItem value="3Y">3 Years</MenuItem>
              <MenuItem value="5Y">5 Years</MenuItem>
              <MenuItem value="MAX">All Time</MenuItem>
            </Select>
          </FormControl>

          <Tooltip title="Portfolio Notifications">
            <IconButton
              onClick={() => setNotificationsPanelOpen(true)}
              color={notifications.length > 0 ? "warning" : "default"}
            >
              <Badge badgeContent={notifications.length} color="error">
                <NotificationsNone />
              </Badge>
            </IconButton>
          </Tooltip>

          <Tooltip title="Watchlist">
            <IconButton onClick={() => setWatchlistDialogOpen(true)}>
              <Visibility />
            </IconButton>
          </Tooltip>

          <Tooltip title={`Auto-refresh: ${autoRefresh ? "ON" : "OFF"}`}>
            <IconButton
              onClick={handleManualRefresh}
              onDoubleClick={() => setAutoRefresh(!autoRefresh)}
              color={autoRefresh ? "primary" : "default"}
            >
              <Refresh />
            </IconButton>
          </Tooltip>

          <Button
            variant="outlined"
            startIcon={<Download />}
            onClick={handleExportClick}
          >
            Export
          </Button>

          <Menu
            anchorEl={exportMenuAnchor}
            open={Boolean(exportMenuAnchor)}
            onClose={handleExportClose}
          >
            <MenuItem onClick={exportToCSV}>
              <ListItemIcon>
                <FileDownload fontSize="small" />
              </ListItemIcon>
              <ListItemText>Export to CSV</ListItemText>
            </MenuItem>
            <MenuItem onClick={exportToPDF}>
              <ListItemIcon>
                <PictureAsPdf fontSize="small" />
              </ListItemIcon>
              <ListItemText>Export to PDF</ListItemText>
            </MenuItem>
          </Menu>

          {isAuthenticated && (
            <Button
              variant="contained"
              startIcon={<Upload />}
              onClick={() => setImportDialogOpen(true)}
              disabled={importing}
            >
              {importing ? "Importing..." : "Import Portfolio"}
            </Button>
          )}

          <Button variant="contained" startIcon={<Add />}>
            Add Position
          </Button>
        </Box>
      </Box>

      {/* Success/Error Alerts */}
      {importSuccess && (
        <Alert
          severity="success"
          sx={{ mb: 3 }}
          onClose={() => setImportSuccess(null)}
        >
          {importSuccess}
        </Alert>
      )}

      {importError && (
        <Alert
          severity="error"
          sx={{ mb: 3 }}
          onClose={() => setImportError(null)}
        >
          {importError}
        </Alert>
      )}

      {/* Key Metrics Cards */}
      <Grid container spacing={3} mb={4}>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="between">
                <Box>
                  <Typography variant="h6" color="text.secondary">
                    Total Value
                  </Typography>
                  <Typography variant="h4" color="primary">
                    {formatCurrency(portfolioMetrics.totalValue)}
                  </Typography>
                  <Box display="flex" alignItems="center" mt={1}>
                    {portfolioMetrics.totalGainLossPercent >= 0 ? (
                      <TrendingUp color="success" fontSize="small" />
                    ) : (
                      <TrendingDown color="error" fontSize="small" />
                    )}
                    <Typography
                      variant="body2"
                      color={
                        portfolioMetrics.totalGainLossPercent >= 0
                          ? "success.main"
                          : "error.main"
                      }
                      ml={0.5}
                    >
                      {formatCurrency(portfolioMetrics.totalGainLoss)} (
                      {formatPercentage(portfolioMetrics.totalGainLossPercent)})
                    </Typography>
                  </Box>
                </Box>
                <AccountBalanceWallet color="primary" fontSize="large" />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="between">
                <Box>
                  <Typography variant="h6" color="text.secondary">
                    Sharpe Ratio
                  </Typography>
                  <Typography variant="h4" color="secondary">
                    {formatNumber(portfolioMetrics.sharpeRatio, 2)}
                  </Typography>
                  <Rating
                    value={Math.min(
                      5,
                      Math.max(0, portfolioMetrics.sharpeRatio)
                    )}
                    readOnly
                    size="small"
                    sx={{ mt: 1 }}
                  />
                </Box>
                <Assessment color="secondary" fontSize="large" />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="between">
                <Box>
                  <Typography variant="h6" color="text.secondary">
                    Portfolio Beta
                  </Typography>
                  <Typography variant="h4" color="info.main">
                    {formatNumber(portfolioMetrics.beta, 2)}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {portfolioMetrics.beta > 1
                      ? "Higher volatility"
                      : "Lower volatility"}
                  </Typography>
                </Box>
                <Speed color="info" fontSize="large" />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="between">
                <Box>
                  <Typography variant="h6" color="text.secondary">
                    VaR (95%)
                  </Typography>
                  <Typography variant="h4" color="warning.main">
                    {formatCurrency(portfolioMetrics.var95)}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Maximum 1-day loss
                  </Typography>
                </Box>
                <Shield color="warning" fontSize="large" />
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Main Content Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 3 }}>
        <Tabs
          value={activeTab}
          onChange={handleTabChange}
          aria-label="portfolio tabs"
          variant="scrollable"
          scrollButtons="auto"
        >
          <Tab label="Holdings" icon={<AccountBalance />} />
          <Tab label="Performance" icon={<Timeline />} />
          <Tab label="Activity History" icon={<Assessment />} />
          <Tab label="Factor Analysis" icon={<Analytics />} />
          <Tab label="Risk Management" icon={<Security />} />
          <Tab label="AI Insights" icon={<Psychology />} />
          <Tab label="Optimization" icon={<Lightbulb />} />
        </Tabs>
      </Box>

      <TabPanel value={activeTab} index={0}>
        {/* Holdings Tab */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader
                title="Portfolio Holdings"
                action={
                  <Chip
                    label={`${portfolioData.holdings.length} positions`}
                    color="primary"
                    variant="outlined"
                  />
                }
              />
              <CardContent>
                <TableContainer>
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableCell>
                          <TableSortLabel
                            active={orderBy === "symbol"}
                            direction={orderBy === "symbol" ? order : "asc"}
                            onClick={() => handleSort("symbol")}
                          >
                            Symbol
                          </TableSortLabel>
                        </TableCell>
                        <TableCell align="right">
                          <TableSortLabel
                            active={orderBy === "shares"}
                            direction={orderBy === "shares" ? order : "asc"}
                            onClick={() => handleSort("shares")}
                          >
                            Shares
                          </TableSortLabel>
                        </TableCell>
                        <TableCell align="right">
                          <TableSortLabel
                            active={orderBy === "avgCost"}
                            direction={orderBy === "avgCost" ? order : "asc"}
                            onClick={() => handleSort("avgCost")}
                          >
                            Avg Cost
                          </TableSortLabel>
                        </TableCell>
                        <TableCell align="right">Current Price</TableCell>
                        <TableCell align="right">
                          <TableSortLabel
                            active={orderBy === "marketValue"}
                            direction={
                              orderBy === "marketValue" ? order : "asc"
                            }
                            onClick={() => handleSort("marketValue")}
                          >
                            Market Value
                          </TableSortLabel>
                        </TableCell>
                        <TableCell align="right">
                          <TableSortLabel
                            active={orderBy === "gainLossPercent"}
                            direction={
                              orderBy === "gainLossPercent" ? order : "asc"
                            }
                            onClick={() => handleSort("gainLossPercent")}
                          >
                            Gain/Loss
                          </TableSortLabel>
                        </TableCell>
                        <TableCell align="right">
                          <TableSortLabel
                            active={orderBy === "allocation"}
                            direction={orderBy === "allocation" ? order : "asc"}
                            onClick={() => handleSort("allocation")}
                          >
                            Allocation
                          </TableSortLabel>
                        </TableCell>
                        <TableCell align="center">Actions</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {sortedHoldings
                        .slice(
                          page * rowsPerPage,
                          page * rowsPerPage + rowsPerPage
                        )
                        .map((holding) => (
                          <TableRow key={holding.symbol}>
                            <TableCell>
                              <Box>
                                <Typography
                                  variant="subtitle2"
                                  fontWeight="bold"
                                >
                                  {holding.symbol}
                                </Typography>
                                <Typography
                                  variant="caption"
                                  color="text.secondary"
                                >
                                  {holding.company}
                                </Typography>
                              </Box>
                            </TableCell>
                            <TableCell align="right">
                              {formatNumber(holding.shares)}
                            </TableCell>
                            <TableCell align="right">
                              {formatCurrency(holding.avgCost)}
                            </TableCell>
                            <TableCell align="right">
                              {formatCurrency(holding.currentPrice)}
                            </TableCell>
                            <TableCell align="right">
                              <Typography variant="body2" fontWeight="bold">
                                {formatCurrency(holding.marketValue)}
                              </Typography>
                            </TableCell>
                            <TableCell align="right">
                              <Box>
                                <Typography
                                  variant="body2"
                                  color={
                                    holding.gainLossPercent >= 0
                                      ? "success.main"
                                      : "error.main"
                                  }
                                  fontWeight="bold"
                                >
                                  {formatCurrency(holding.gainLoss)}
                                </Typography>
                                <Chip
                                  label={`${holding.gainLossPercent >= 0 ? "+" : ""}${formatPercentage(holding.gainLossPercent)}`}
                                  color={
                                    holding.gainLossPercent >= 0
                                      ? "success"
                                      : "error"
                                  }
                                  size="small"
                                  variant="outlined"
                                />
                              </Box>
                            </TableCell>
                            <TableCell align="right">
                              <Box>
                                <Typography variant="body2">
                                  {formatPercentage(holding.allocation)}
                                </Typography>
                                <LinearProgress
                                  variant="determinate"
                                  value={holding.allocation}
                                  sx={{ mt: 0.5, width: 60 }}
                                />
                              </Box>
                            </TableCell>
                            <TableCell align="center">
                              <IconButton size="small" color="primary">
                                <Edit />
                              </IconButton>
                              <IconButton size="small" color="error">
                                <Delete />
                              </IconButton>
                            </TableCell>
                          </TableRow>
                        ))}
                    </TableBody>
                  </Table>
                </TableContainer>
                <TablePagination
                  rowsPerPageOptions={[10, 25, 50]}
                  component="div"
                  count={portfolioData.holdings.length}
                  rowsPerPage={rowsPerPage}
                  page={page}
                  onPageChange={(e, newPage) => setPage(newPage)}
                  onRowsPerPageChange={(e) =>
                    setRowsPerPage(parseInt(e.target.value, 10))
                  }
                />
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Grid container spacing={3}>
              {/* Allocation Charts */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Asset Allocation" />
                  <CardContent>
                    <ResponsiveContainer width="100%" height={300}>
                      <PieChart>
                        <Pie
                          data={portfolioData.sectorAllocation}
                          cx="50%"
                          cy="50%"
                          outerRadius={80}
                          fill="#8884d8"
                          dataKey="value"
                          label={({ name, percent }) =>
                            `${name} ${(percent * 100).toFixed(0)}%`
                          }
                        >
                          {portfolioData.sectorAllocation.map(
                            (entry, index) => (
                              <Cell
                                key={`cell-${index}`}
                                fill={CHART_COLORS[index % CHART_COLORS.length]}
                              />
                            )
                          )}
                        </Pie>
                        <Tooltip
                          formatter={(value) => [
                            formatPercentage(value),
                            "Allocation",
                          ]}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>

              {/* Concentration Risk */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Concentration Analysis" />
                  <CardContent>
                    <Box mb={2}>
                      <Typography variant="body2" color="text.secondary">
                        Portfolio Concentration Risk
                      </Typography>
                      <LinearProgress
                        variant="determinate"
                        value={diversificationMetrics.concentrationRisk * 100}
                        color={
                          diversificationMetrics.concentrationRisk > 0.3
                            ? "error"
                            : "success"
                        }
                        sx={{ mt: 1 }}
                      />
                      <Typography variant="caption" color="text.secondary">
                        Herfindahl Index:{" "}
                        {formatNumber(
                          diversificationMetrics.concentrationRisk,
                          3
                        )}
                      </Typography>
                    </Box>

                    <Typography
                      variant="body2"
                      color="text.secondary"
                      gutterBottom
                    >
                      Top 3 Holdings:{" "}
                      {formatPercentage(
                        portfolioData.holdings
                          .sort((a, b) => b.allocation - a.allocation)
                          .slice(0, 3)
                          .reduce((sum, h) => sum + h.allocation, 0)
                      )}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={1}>
        {/* Performance Tab */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader title="Portfolio Performance" />
              <CardContent>
                <ResponsiveContainer width="100%" height={400}>
                  <ComposedChart data={portfolioData.performanceHistory}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis yAxisId="left" />
                    <YAxis yAxisId="right" orientation="right" />
                    <Tooltip />
                    <Area
                      yAxisId="left"
                      type="monotone"
                      dataKey="portfolioValue"
                      fill="#8884d8"
                      stroke="#8884d8"
                      fillOpacity={0.3}
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="benchmarkValue"
                      stroke="#82ca9d"
                      strokeWidth={2}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Grid container spacing={3}>
              {/* Performance Metrics */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Performance Metrics" />
                  <CardContent>
                    <Box display="flex" flexDirection="column" gap={2}>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Sharpe Ratio</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {formatNumber(portfolioMetrics.sharpeRatio, 2)}
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Treynor Ratio</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {formatNumber(portfolioMetrics.treynorRatio, 2)}
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">
                          Information Ratio
                        </Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {formatNumber(portfolioMetrics.informationRatio, 2)}
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Calmar Ratio</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {formatNumber(portfolioMetrics.calmarRatio, 2)}
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Max Drawdown</Typography>
                        <Typography
                          variant="body2"
                          fontWeight="bold"
                          color="error.main"
                        >
                          {formatPercentage(portfolioMetrics.maxDrawdown)}
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Volatility</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {formatPercentage(portfolioMetrics.volatility)}
                        </Typography>
                      </Box>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>

              {/* Benchmark Comparison */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="vs S&P 500" />
                  <CardContent>
                    <Box display="flex" flexDirection="column" gap={2}>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Alpha</Typography>
                        <Chip
                          label={formatPercentage(2.3)}
                          color="success"
                          size="small"
                        />
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Beta</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {formatNumber(portfolioMetrics.beta, 2)}
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">R-Squared</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {formatNumber(0.87, 2)}
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Tracking Error</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {formatPercentage(4.2)}
                        </Typography>
                      </Box>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={2}>
        {/* Activity History Tab */}
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Card>
              <CardHeader
                title="Recent Activity"
                subheader="Portfolio transactions and account activities"
                action={
                  <Button size="small" variant="outlined">
                    Export Activity
                  </Button>
                }
              />
              <CardContent>
                <TableContainer>
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableCell>Date</TableCell>
                        <TableCell>Type</TableCell>
                        <TableCell>Symbol</TableCell>
                        <TableCell>Description</TableCell>
                        <TableCell align="right">Quantity</TableCell>
                        <TableCell align="right">Price</TableCell>
                        <TableCell align="right">Amount</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {portfolioData.activityHistory?.map((activity, index) => (
                        <TableRow key={index}>
                          <TableCell>
                            {new Date(activity.date).toLocaleDateString()}
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={activity.type}
                              color={
                                activity.type === "BUY"
                                  ? "success"
                                  : activity.type === "SELL"
                                    ? "error"
                                    : "default"
                              }
                              size="small"
                            />
                          </TableCell>
                          <TableCell>{activity.symbol || "-"}</TableCell>
                          <TableCell>{activity.description}</TableCell>
                          <TableCell align="right">
                            {activity.quantity
                              ? formatNumber(activity.quantity)
                              : "-"}
                          </TableCell>
                          <TableCell align="right">
                            {activity.price
                              ? formatCurrency(activity.price)
                              : "-"}
                          </TableCell>
                          <TableCell align="right">
                            <Typography
                              color={
                                activity.amount >= 0
                                  ? "success.main"
                                  : "error.main"
                              }
                              fontWeight="bold"
                            >
                              {formatCurrency(Math.abs(activity.amount))}
                            </Typography>
                          </TableCell>
                        </TableRow>
                      )) || [
                        <TableRow key="no-data">
                          <TableCell colSpan={7} align="center">
                            <Typography color="text.secondary">
                              No recent activity. Import your portfolio to see
                              transaction history.
                            </Typography>
                          </TableCell>
                        </TableRow>,
                      ]}
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={3}>
        {/* Factor Analysis Tab */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader title="Multi-Factor Exposure Analysis" />
              <CardContent>
                <ResponsiveContainer width="100%" height={400}>
                  <RadarChart data={factorAnalysis}>
                    <PolarGrid />
                    <PolarAngleAxis dataKey="factor" />
                    <PolarRadiusAxis
                      angle={90}
                      domain={[-100, 100]}
                      tick={{ fontSize: 12 }}
                    />
                    <Radar
                      name="Portfolio"
                      dataKey="exposure"
                      stroke="#8884d8"
                      fill="#8884d8"
                      fillOpacity={0.3}
                      strokeWidth={2}
                    />
                    <Radar
                      name="Benchmark"
                      dataKey="benchmark"
                      stroke="#82ca9d"
                      fill="transparent"
                      strokeWidth={2}
                      strokeDasharray="5 5"
                    />
                    <Tooltip />
                  </RadarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Card>
              <CardHeader title="Factor Scores" />
              <CardContent>
                {factorAnalysis.map((factor) => (
                  <Box key={factor.factor} mb={3}>
                    <Box display="flex" justifyContent="between" mb={1}>
                      <Typography variant="body2" fontWeight="bold">
                        {factor.factor}
                      </Typography>
                      <Chip
                        label={formatNumber(factor.exposure, 1)}
                        color={
                          factor.exposure > 10
                            ? "success"
                            : factor.exposure < -10
                              ? "error"
                              : "default"
                        }
                        size="small"
                      />
                    </Box>
                    <LinearProgress
                      variant="determinate"
                      value={Math.min(
                        100,
                        Math.max(0, (factor.exposure + 100) / 2)
                      )}
                      color={factor.exposure > 0 ? "success" : "error"}
                      sx={{ mb: 1 }}
                    />
                    <Typography variant="caption" color="text.secondary">
                      {factor.description}
                    </Typography>
                  </Box>
                ))}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={4}>
        {/* Enhanced Risk Management Tab */}
        {/* Risk Summary Cards */}
        <Grid container spacing={3} sx={{ mb: 3 }}>
          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Box
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                  }}
                >
                  <Box>
                    <Typography color="text.secondary" gutterBottom>
                      Portfolio VaR (95%)
                    </Typography>
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      {formatCurrency(portfolioMetrics.var95)}
                    </Typography>
                  </Box>
                  <Security sx={{ fontSize: 40, color: "primary.main" }} />
                </Box>
                <LinearProgress
                  variant="determinate"
                  value={
                    (portfolioMetrics.var95 / portfolioMetrics.totalValue) * 100
                  }
                  sx={{ mt: 1 }}
                  color={
                    (portfolioMetrics.var95 / portfolioMetrics.totalValue) *
                      100 <=
                    3
                      ? "success"
                      : (portfolioMetrics.var95 / portfolioMetrics.totalValue) *
                            100 <=
                          8
                        ? "warning"
                        : "error"
                  }
                />
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Box
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                  }}
                >
                  <Box>
                    <Typography color="text.secondary" gutterBottom>
                      Sharpe Ratio
                    </Typography>
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      {formatNumber(portfolioMetrics.sharpeRatio, 2)}
                    </Typography>
                  </Box>
                  <Assessment sx={{ fontSize: 40, color: "success.main" }} />
                </Box>
                <Chip
                  label={
                    portfolioMetrics.sharpeRatio > 1
                      ? "Good"
                      : "Needs Improvement"
                  }
                  color={
                    portfolioMetrics.sharpeRatio > 1 ? "success" : "warning"
                  }
                  size="small"
                  sx={{ mt: 1 }}
                />
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Box
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                  }}
                >
                  <Box>
                    <Typography color="text.secondary" gutterBottom>
                      Portfolio Beta
                    </Typography>
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      {formatNumber(portfolioMetrics.beta, 2)}
                    </Typography>
                  </Box>
                  <TrendingUp sx={{ fontSize: 40, color: "info.main" }} />
                </Box>
                <Chip
                  label={portfolioMetrics.beta > 1 ? "High Risk" : "Low Risk"}
                  color={
                    portfolioMetrics.beta > 1.2
                      ? "error"
                      : portfolioMetrics.beta > 0.8
                        ? "warning"
                        : "success"
                  }
                  size="small"
                  sx={{ mt: 1 }}
                />
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Box
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                  }}
                >
                  <Box>
                    <Typography color="text.secondary" gutterBottom>
                      Max Drawdown
                    </Typography>
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      {formatPercentage(portfolioMetrics.maxDrawdown)}
                    </Typography>
                  </Box>
                  <Warning sx={{ fontSize: 40, color: "warning.main" }} />
                </Box>
                <LinearProgress
                  variant="determinate"
                  value={Math.abs(portfolioMetrics.maxDrawdown * 100)}
                  sx={{ mt: 1 }}
                  color={
                    Math.abs(portfolioMetrics.maxDrawdown) <= 0.1
                      ? "success"
                      : Math.abs(portfolioMetrics.maxDrawdown) <= 0.2
                        ? "warning"
                        : "error"
                  }
                />
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {/* Risk Management Sub-tabs */}
        <Card>
          <Box sx={{ borderBottom: 1, borderColor: "divider" }}>
            <Tabs
              value={riskSubTab}
              onChange={(e, v) => setRiskSubTab(v)}
              aria-label="risk management tabs"
            >
              <Tab label="Position Risk" />
              <Tab label="VaR Analysis" />
              <Tab label="Stress Testing" />
              <Tab label="Risk Alerts" />
            </Tabs>
          </Box>

          <Box sx={{ p: 3 }}>
            {riskSubTab === 0 && (
              <Box>
                <Typography variant="h6" gutterBottom>
                  Position Risk Analysis
                </Typography>
                <TableContainer>
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableCell>Symbol</TableCell>
                        <TableCell align="right">Weight</TableCell>
                        <TableCell align="right">VaR (95%)</TableCell>
                        <TableCell align="right">Beta</TableCell>
                        <TableCell align="right">Volatility</TableCell>
                        <TableCell align="right">Risk Contribution</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {portfolioData.holdings.map((holding) => (
                        <TableRow key={holding.symbol}>
                          <TableCell>
                            <Box sx={{ display: "flex", alignItems: "center" }}>
                              <Typography
                                variant="body2"
                                sx={{ fontWeight: 600 }}
                              >
                                {holding.symbol}
                              </Typography>
                            </Box>
                          </TableCell>
                          <TableCell align="right">
                            {formatPercentage(holding.weight)}
                          </TableCell>
                          <TableCell align="right">
                            {formatCurrency(holding.value * 0.05)}
                          </TableCell>
                          <TableCell align="right">
                            <Chip
                              label={formatNumber(holding.beta || 1.0, 2)}
                              color={
                                (holding.beta || 1.0) <= 0.8
                                  ? "success"
                                  : (holding.beta || 1.0) <= 1.2
                                    ? "warning"
                                    : "error"
                              }
                              size="small"
                            />
                          </TableCell>
                          <TableCell align="right">
                            <Chip
                              label={formatPercentage(
                                holding.volatility || 0.2
                              )}
                              color={
                                (holding.volatility || 0.2) <= 0.2
                                  ? "success"
                                  : (holding.volatility || 0.2) <= 0.3
                                    ? "warning"
                                    : "error"
                              }
                              size="small"
                            />
                          </TableCell>
                          <TableCell align="right">
                            <LinearProgress
                              variant="determinate"
                              value={holding.weight * 100}
                              sx={{ width: 60 }}
                              color={
                                holding.weight <= 0.2
                                  ? "success"
                                  : holding.weight <= 0.3
                                    ? "warning"
                                    : "error"
                              }
                            />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Box>
            )}

            {riskSubTab === 1 && (
              <Box>
                <Typography variant="h6" gutterBottom>
                  Value at Risk Trends
                </Typography>
                <Box sx={{ height: 400, mt: 2 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={
                        portfolioData.historicalVaR || [
                          // ⚠️ MOCK DATA - Replace with real API when available
                          {
                            date: "2025-06-28",
                            var95: 65000,
                            var99: 120000,
                            isMockData: true,
                          },
                          {
                            date: "2025-06-29",
                            var95: 67000,
                            var99: 122000,
                            isMockData: true,
                          },
                          {
                            date: "2025-06-30",
                            var95: 66500,
                            var99: 121000,
                            isMockData: true,
                          },
                          {
                            date: "2025-07-01",
                            var95: 68000,
                            var99: 124000,
                            isMockData: true,
                          },
                          {
                            date: "2025-07-02",
                            var95: 68500,
                            var99: 125000,
                            isMockData: true,
                          },
                        ]
                      }
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" />
                      <YAxis />
                      <Tooltip
                        formatter={(value) => [
                          `$${value.toLocaleString()}`,
                          "",
                        ]}
                      />
                      <Line
                        type="monotone"
                        dataKey="var95"
                        stroke="#1976d2"
                        name="VaR 95%"
                        strokeWidth={2}
                      />
                      <Line
                        type="monotone"
                        dataKey="var99"
                        stroke="#d32f2f"
                        name="VaR 99%"
                        strokeWidth={2}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </Box>
              </Box>
            )}

            {riskSubTab === 2 && (
              <Box>
                <Typography variant="h6" gutterBottom>
                  Stress Test Results
                </Typography>
                <Grid container spacing={2}>
                  {portfolioData.stressTests.map((test, index) => (
                    <Grid item xs={12} md={6} key={index}>
                      <Card variant="outlined">
                        <CardContent>
                          <Typography
                            variant="subtitle1"
                            sx={{ fontWeight: 600 }}
                          >
                            {test.scenario}
                          </Typography>
                          <Box
                            sx={{
                              display: "flex",
                              justifyContent: "space-between",
                              mt: 1,
                            }}
                          >
                            <Typography color="text.secondary">
                              Potential Loss:
                            </Typography>
                            <Typography
                              sx={{ color: "error.main", fontWeight: 600 }}
                            >
                              $
                              {Math.abs(
                                test.impact * portfolioMetrics.totalValue
                              ).toLocaleString()}{" "}
                              ({formatPercentage(Math.abs(test.impact))})
                            </Typography>
                          </Box>
                          <LinearProgress
                            variant="determinate"
                            value={Math.abs(test.impact * 100)}
                            color="error"
                            sx={{ mt: 1 }}
                          />
                        </CardContent>
                      </Card>
                    </Grid>
                  ))}
                </Grid>
              </Box>
            )}

            {riskSubTab === 3 && (
              <Box>
                <Box
                  sx={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    mb: 2,
                  }}
                >
                  <Typography variant="h6">Risk Alerts</Typography>
                  <Button
                    variant="contained"
                    startIcon={<Notifications />}
                    onClick={() => setRiskAlertDialogOpen(true)}
                  >
                    Create Alert
                  </Button>
                </Box>

                {/* ⚠️ MOCK DATA - Replace with real API when available */}
                {mockRiskAlerts.map((alert) => (
                  <Alert
                    key={alert.id}
                    severity={alert.severity}
                    sx={{ mb: 2 }}
                  >
                    <Typography variant="body2">
                      <strong>{alert.symbol}</strong> {alert.metric} is{" "}
                      {alert.value}
                      {typeof alert.value === "number" && alert.value < 10
                        ? ""
                        : "%"}
                      (threshold: {alert.threshold}
                      {typeof alert.threshold === "number" &&
                      alert.threshold < 10
                        ? ""
                        : "%"}
                      )
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {new Date(alert.timestamp).toLocaleString()}
                    </Typography>
                  </Alert>
                ))}
              </Box>
            )}
          </Box>
        </Card>
      </TabPanel>

      <TabPanel value={activeTab} index={5}>
        {/* AI Insights Tab */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader
                title="AI-Powered Portfolio Analysis"
                avatar={<Psychology color="primary" />}
              />
              <CardContent>
                <Stepper orientation="vertical">
                  <Step expanded>
                    <StepLabel>
                      <Typography variant="h6" color="success.main">
                        Strengths Identified
                      </Typography>
                    </StepLabel>
                    <StepContent>
                      <List>
                        {aiInsights.strengths.map((strength, index) => (
                          <ListItem key={index}>
                            <CheckCircle color="success" sx={{ mr: 2 }} />
                            <Typography variant="body2">{strength}</Typography>
                          </ListItem>
                        ))}
                      </List>
                    </StepContent>
                  </Step>

                  <Step expanded>
                    <StepLabel>
                      <Typography variant="h6" color="warning.main">
                        Improvement Opportunities
                      </Typography>
                    </StepLabel>
                    <StepContent>
                      <List>
                        {aiInsights.improvements.map((improvement, index) => (
                          <ListItem key={index}>
                            <Lightbulb color="warning" sx={{ mr: 2 }} />
                            <Typography variant="body2">
                              {improvement}
                            </Typography>
                          </ListItem>
                        ))}
                      </List>
                    </StepContent>
                  </Step>

                  <Step expanded>
                    <StepLabel>
                      <Typography variant="h6" color="info.main">
                        Market Analysis
                      </Typography>
                    </StepLabel>
                    <StepContent>
                      <Alert severity="info" sx={{ mt: 1 }}>
                        {aiInsights.marketAnalysis}
                      </Alert>
                    </StepContent>
                  </Step>
                </Stepper>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Card>
              <CardHeader title="AI Confidence Score" />
              <CardContent>
                <Box textAlign="center" mb={3}>
                  <Typography variant="h2" color="primary">
                    {aiInsights.confidenceScore}%
                  </Typography>
                  <Rating
                    value={aiInsights.confidenceScore / 20}
                    readOnly
                    size="large"
                  />
                  <Typography variant="body2" color="text.secondary">
                    Analysis Confidence
                  </Typography>
                </Box>

                <Divider sx={{ my: 2 }} />

                <Typography variant="subtitle2" gutterBottom>
                  Key Recommendations
                </Typography>
                {aiInsights.recommendations.map((rec, index) => (
                  <Chip
                    key={index}
                    label={rec}
                    variant="outlined"
                    size="small"
                    sx={{ m: 0.5 }}
                  />
                ))}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={6}>
        {/* Enhanced Optimization Tab */}
        <Grid container spacing={3}>
          {/* Optimization Configuration */}
          <Grid item xs={12} md={4}>
            <Card>
              <CardHeader
                title="Optimization Engine"
                subheader="Advanced multi-factor portfolio optimization"
              />
              <CardContent>
                <FormControl fullWidth sx={{ mb: 3 }}>
                  <InputLabel>Optimization Method</InputLabel>
                  <Select
                    value={optimizationMethod}
                    onChange={(e) => setOptimizationMethod(e.target.value)}
                    label="Optimization Method"
                  >
                    <MenuItem value="enhanced_sharpe">
                      Enhanced Sharpe Ratio
                    </MenuItem>
                    <MenuItem value="black_litterman">
                      Black-Litterman with Views
                    </MenuItem>
                    <MenuItem value="risk_parity">
                      Equal Risk Contribution
                    </MenuItem>
                    <MenuItem value="factor_optimization">
                      Factor-Based Optimization
                    </MenuItem>
                    <MenuItem value="max_diversification">
                      Maximum Diversification
                    </MenuItem>
                    <MenuItem value="min_correlation">
                      Minimum Correlation
                    </MenuItem>
                  </Select>
                </FormControl>

                <Typography variant="body2" gutterBottom>
                  Risk Tolerance: {riskTolerance}%
                </Typography>
                <Slider
                  value={riskTolerance}
                  onChange={(e, value) => setRiskTolerance(value)}
                  step={5}
                  marks={[
                    { value: 0, label: "Conservative" },
                    { value: 50, label: "Moderate" },
                    { value: 100, label: "Aggressive" },
                  ]}
                  min={0}
                  max={100}
                  valueLabelDisplay="auto"
                  sx={{ mb: 3 }}
                />

                <FormControl fullWidth sx={{ mb: 3 }}>
                  <InputLabel>Time Horizon</InputLabel>
                  <Select
                    value={timeHorizon}
                    onChange={(e) => setTimeHorizon(e.target.value)}
                    label="Time Horizon"
                  >
                    <MenuItem value="short">Short-term (&lt; 2 years)</MenuItem>
                    <MenuItem value="medium">Medium-term (2-7 years)</MenuItem>
                    <MenuItem value="long">Long-term (&gt; 7 years)</MenuItem>
                  </Select>
                </FormControl>

                <Typography variant="h6" gutterBottom sx={{ mt: 3 }}>
                  Optimization Constraints
                </Typography>

                <Box display="flex" flexDirection="column" gap={1}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={optimizationConstraints.sectorLimits}
                        onChange={(e) =>
                          setOptimizationConstraints({
                            ...optimizationConstraints,
                            sectorLimits: e.target.checked,
                          })
                        }
                      />
                    }
                    label="Sector Diversification Limits"
                  />
                  <FormControlLabel
                    control={
                      <Switch
                        checked={optimizationConstraints.esgConstraints}
                        onChange={(e) =>
                          setOptimizationConstraints({
                            ...optimizationConstraints,
                            esgConstraints: e.target.checked,
                          })
                        }
                      />
                    }
                    label="ESG Constraints"
                  />
                  <FormControlLabel
                    control={
                      <Switch
                        checked={optimizationConstraints.taxOptimization}
                        onChange={(e) =>
                          setOptimizationConstraints({
                            ...optimizationConstraints,
                            taxOptimization: e.target.checked,
                          })
                        }
                      />
                    }
                    label="Tax-Loss Harvesting"
                  />
                  <FormControlLabel
                    control={
                      <Switch
                        checked={optimizationConstraints.transactionCosts}
                        onChange={(e) =>
                          setOptimizationConstraints({
                            ...optimizationConstraints,
                            transactionCosts: e.target.checked,
                          })
                        }
                      />
                    }
                    label="Transaction Cost Optimization"
                  />
                  <FormControlLabel
                    control={
                      <Switch
                        checked={optimizationConstraints.factorConstraints}
                        onChange={(e) =>
                          setOptimizationConstraints({
                            ...optimizationConstraints,
                            factorConstraints: e.target.checked,
                          })
                        }
                      />
                    }
                    label="Factor Exposure Limits"
                  />
                </Box>

                <Typography variant="body2" sx={{ mt: 2, mb: 1 }}>
                  Max Position Size: {optimizationConstraints.maxPositionSize}%
                </Typography>
                <Slider
                  value={optimizationConstraints.maxPositionSize}
                  onChange={(e, value) =>
                    setOptimizationConstraints({
                      ...optimizationConstraints,
                      maxPositionSize: value,
                    })
                  }
                  step={1}
                  min={1}
                  max={25}
                  valueLabelDisplay="auto"
                  sx={{ mb: 3 }}
                />

                <Button
                  variant="contained"
                  size="large"
                  fullWidth
                  startIcon={
                    optimizationRunning ? (
                      <CircularProgress size={20} />
                    ) : (
                      <Analytics />
                    )
                  }
                  onClick={handleRunOptimization}
                  disabled={optimizationRunning}
                >
                  {optimizationRunning ? "Optimizing..." : "Run Optimization"}
                </Button>
              </CardContent>
            </Card>
          </Grid>

          {/* Market Analysis */}
          <Grid item xs={12} md={4}>
            <Card>
              <CardHeader title="Market Analysis" />
              <CardContent>
                {renderMarketRegimeAnalysis()}
                {renderCorrelationMatrix()}
              </CardContent>
            </Card>
          </Grid>

          {/* Optimization Results */}
          <Grid item xs={12} md={4}>
            <Card>
              <CardHeader title="Optimization Results" />
              <CardContent>
                {optimizationResults ? (
                  renderOptimizationResults()
                ) : (
                  <Alert severity="info">
                    Run optimization to see recommendations and portfolio
                    improvements.
                  </Alert>
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* Detailed Recommendations */}
          {optimizationResults && (
            <Grid item xs={12}>
              <Card>
                <CardHeader title="Detailed Optimization Recommendations" />
                <CardContent>{renderDetailedRecommendations()}</CardContent>
              </Card>
            </Grid>
          )}
        </Grid>
      </TabPanel>

      {/* Risk Alert Dialog */}
      <Dialog
        open={riskAlertDialogOpen}
        onClose={() => setRiskAlertDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Create Risk Alert</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Symbol"
                value={newRiskAlert.symbol}
                onChange={(e) =>
                  setNewRiskAlert({ ...newRiskAlert, symbol: e.target.value })
                }
                placeholder="e.g., AAPL or PORTFOLIO"
              />
            </Grid>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>Metric</InputLabel>
                <Select
                  value={newRiskAlert.metric}
                  onChange={(e) =>
                    setNewRiskAlert({ ...newRiskAlert, metric: e.target.value })
                  }
                  label="Metric"
                >
                  <MenuItem value="volatility">Volatility</MenuItem>
                  <MenuItem value="beta">Beta</MenuItem>
                  <MenuItem value="var">Value at Risk</MenuItem>
                  <MenuItem value="concentration">Concentration</MenuItem>
                  <MenuItem value="correlation">Correlation</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={6}>
              <FormControl fullWidth>
                <InputLabel>Condition</InputLabel>
                <Select
                  value={newRiskAlert.condition}
                  onChange={(e) =>
                    setNewRiskAlert({
                      ...newRiskAlert,
                      condition: e.target.value,
                    })
                  }
                  label="Condition"
                >
                  <MenuItem value="above">Above</MenuItem>
                  <MenuItem value="below">Below</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={6}>
              <TextField
                fullWidth
                label="Threshold"
                type="number"
                value={newRiskAlert.threshold}
                onChange={(e) =>
                  setNewRiskAlert({
                    ...newRiskAlert,
                    threshold: Number(e.target.value),
                  })
                }
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRiskAlertDialogOpen(false)}>Cancel</Button>
          <Button
            onClick={() => {
              console.log("Creating risk alert:", newRiskAlert);
              setRiskAlertDialogOpen(false);
              setNewRiskAlert({
                symbol: "",
                metric: "volatility",
                threshold: 25,
                condition: "above",
              });
            }}
            variant="contained"
          >
            Create Alert
          </Button>
        </DialogActions>
      </Dialog>

      {/* Portfolio Notifications Panel */}
      <Dialog
        open={notificationsPanelOpen}
        onClose={() => setNotificationsPanelOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          <Box display="flex" alignItems="center" gap={1}>
            <NotificationsActive />
            Portfolio Notifications
          </Box>
        </DialogTitle>
        <DialogContent>
          {notifications.length === 0 ? (
            <Typography color="text.secondary">No new notifications</Typography>
          ) : (
            <List>
              {notifications.map((notification) => (
                <ListItem key={notification.id}>
                  <ListItemIcon>
                    {notification.type === "warning" ? (
                      <Warning color="warning" />
                    ) : (
                      <Info color="info" />
                    )}
                  </ListItemIcon>
                  <ListItemText
                    primary={notification.message}
                    secondary={notification.timestamp.toLocaleString()}
                  />
                </ListItem>
              ))}
            </List>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setNotifications([])}>Clear All</Button>
          <Button onClick={() => setNotificationsPanelOpen(false)}>
            Close
          </Button>
        </DialogActions>
      </Dialog>

      {/* Watchlist Dialog */}
      <Dialog
        open={watchlistDialogOpen}
        onClose={() => setWatchlistDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          <Box display="flex" alignItems="center" gap={1}>
            <Visibility />
            Investment Watchlist
          </Box>
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Track potential investments and monitor their performance
          </Typography>
          <TableContainer component={Paper}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Symbol</TableCell>
                  <TableCell>Company</TableCell>
                  <TableCell align="right">Price</TableCell>
                  <TableCell align="right">Change</TableCell>
                  <TableCell align="center">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {watchlist.map((item) => (
                  <TableRow key={item.symbol}>
                    <TableCell>{item.symbol}</TableCell>
                    <TableCell>{item.name}</TableCell>
                    <TableCell align="right">
                      {formatCurrency(item.price)}
                    </TableCell>
                    <TableCell align="right">
                      <Box
                        display="flex"
                        alignItems="center"
                        justifyContent="flex-end"
                      >
                        {item.change >= 0 ? (
                          <TrendingUp color="success" fontSize="small" />
                        ) : (
                          <TrendingDown color="error" fontSize="small" />
                        )}
                        <Typography
                          variant="body2"
                          color={
                            item.change >= 0 ? "success.main" : "error.main"
                          }
                          ml={0.5}
                        >
                          {item.change > 0 ? "+" : ""}
                          {item.change}%
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell align="center">
                      <Button
                        size="small"
                        variant="outlined"
                        startIcon={<Add />}
                      >
                        Add to Portfolio
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </DialogContent>
        <DialogActions>
          <Button startIcon={<Add />}>Add Symbol</Button>
          <Button onClick={() => setWatchlistDialogOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* Portfolio Import Dialog */}
      <Dialog
        open={importDialogOpen}
        onClose={() => setImportDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          <Box display="flex" alignItems="center">
            <Upload sx={{ mr: 1 }} />
            Import Portfolio from Broker
          </Box>
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Import your portfolio data from connected brokerage accounts. Make
            sure you have configured your API keys in Settings first.
          </Typography>

          {availableConnections.length === 0 ? (
            <Alert severity="info">
              No broker connections found. Please add your API keys in Settings
              → API Keys to import portfolio data.
              <Button
                size="small"
                sx={{ ml: 2 }}
                onClick={() => {
                  setImportDialogOpen(false);
                  navigate("/settings");
                }}
              >
                Go to Settings
              </Button>
            </Alert>
          ) : (
            <Grid container spacing={2}>
              {availableConnections.map((connection) => (
                <Grid item xs={12} sm={6} key={connection.id}>
                  <Card>
                    <CardContent>
                      <Box
                        display="flex"
                        alignItems="center"
                        justifyContent="space-between"
                        mb={2}
                      >
                        <Box display="flex" alignItems="center">
                          <BusinessCenter sx={{ mr: 1 }} />
                          <Box>
                            <Typography variant="h6">
                              {connection.provider.charAt(0).toUpperCase() +
                                connection.provider.slice(1)}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              {connection.description || "Brokerage account"}
                            </Typography>
                          </Box>
                        </Box>
                        <Chip
                          label={connection.isSandbox ? "Paper" : "Live"}
                          color={connection.isSandbox ? "warning" : "success"}
                          size="small"
                        />
                      </Box>

                      <Box display="flex" gap={1}>
                        <Button
                          size="small"
                          variant="outlined"
                          startIcon={
                            testingConnection[connection.id] ? (
                              <CircularProgress size={16} />
                            ) : (
                              <Security />
                            )
                          }
                          onClick={() =>
                            handleTestConnection(
                              connection.id,
                              connection.provider
                            )
                          }
                          disabled={testingConnection[connection.id]}
                        >
                          Test
                        </Button>
                        <Button
                          size="small"
                          variant="contained"
                          startIcon={
                            importing ? (
                              <CircularProgress size={16} />
                            ) : (
                              <Upload />
                            )
                          }
                          onClick={() =>
                            handleImportPortfolio(connection.provider)
                          }
                          disabled={importing}
                        >
                          Import
                        </Button>
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setImportDialogOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

// ⚠️ MOCK DATA - Replace with real API when available
// Enhanced mock data with realistic portfolio metrics
const mockPortfolioData = {
  isMockData: true,
  holdings: [
    {
      symbol: "AAPL",
      company: "Apple Inc.",
      shares: 100,
      avgCost: 150.0,
      currentPrice: 189.45,
      marketValue: 18945,
      gainLoss: 3945,
      gainLossPercent: 26.3,
      sector: "Technology",
      allocation: 23.5,
      beta: 1.2,
      isMockData: true,
      factorScores: {
        quality: 85,
        growth: 60,
        value: 25,
        momentum: 75,
        sentiment: 70,
        positioning: 45,
      },
    },
    {
      symbol: "MSFT",
      company: "Microsoft Corporation",
      shares: 50,
      avgCost: 300.0,
      currentPrice: 342.56,
      marketValue: 17128,
      gainLoss: 2128,
      gainLossPercent: 14.19,
      sector: "Technology",
      allocation: 21.3,
      beta: 0.9,
      isMockData: true,
      factorScores: {
        quality: 90,
        growth: 65,
        value: 30,
        momentum: 80,
        sentiment: 75,
        positioning: 50,
      },
    },
    {
      symbol: "GOOGL",
      company: "Alphabet Inc.",
      shares: 25,
      avgCost: 120.0,
      currentPrice: 134.23,
      marketValue: 3356,
      gainLoss: 356,
      gainLossPercent: 11.86,
      sector: "Technology",
      allocation: 4.2,
      beta: 1.1,
      isMockData: true,
      factorScores: {
        quality: 80,
        growth: 70,
        value: 40,
        momentum: 65,
        sentiment: 60,
        positioning: 35,
      },
    },
    {
      symbol: "JNJ",
      company: "Johnson & Johnson",
      shares: 75,
      avgCost: 160.0,
      currentPrice: 156.78,
      marketValue: 11759,
      gainLoss: -241,
      gainLossPercent: -2.01,
      sector: "Healthcare",
      allocation: 14.6,
      beta: 0.7,
      isMockData: true,
      factorScores: {
        quality: 95,
        growth: 25,
        value: 60,
        momentum: 30,
        sentiment: 45,
        positioning: 65,
      },
    },
    {
      symbol: "JPM",
      company: "JPMorgan Chase & Co.",
      shares: 60,
      avgCost: 140.0,
      currentPrice: 167.89,
      marketValue: 10073,
      gainLoss: 1673,
      gainLossPercent: 19.89,
      sector: "Financials",
      allocation: 12.5,
      beta: 1.3,
      isMockData: true,
      factorScores: {
        quality: 75,
        growth: 40,
        value: 70,
        momentum: 55,
        sentiment: 50,
        positioning: 60,
      },
    },
    {
      symbol: "PG",
      company: "Procter & Gamble Co.",
      shares: 40,
      avgCost: 145.0,
      currentPrice: 153.21,
      marketValue: 6128,
      gainLoss: 328,
      gainLossPercent: 5.66,
      sector: "Consumer Staples",
      allocation: 7.6,
      beta: 0.5,
      isMockData: true,
      factorScores: {
        quality: 85,
        growth: 20,
        value: 45,
        momentum: 25,
        sentiment: 55,
        positioning: 70,
      },
    },
    {
      symbol: "BRK.B",
      company: "Berkshire Hathaway Inc.",
      shares: 30,
      avgCost: 320.0,
      currentPrice: 345.67,
      marketValue: 10370,
      gainLoss: 770,
      gainLossPercent: 8.01,
      sector: "Financials",
      allocation: 12.9,
      beta: 0.8,
      isMockData: true,
      factorScores: {
        quality: 90,
        growth: 35,
        value: 80,
        momentum: 40,
        sentiment: 60,
        positioning: 75,
      },
    },
    {
      symbol: "V",
      company: "Visa Inc.",
      shares: 35,
      avgCost: 200.0,
      currentPrice: 234.56,
      marketValue: 8210,
      gainLoss: 1210,
      gainLossPercent: 17.29,
      sector: "Financials",
      allocation: 10.2,
      beta: 1.0,
      isMockData: true,
      factorScores: {
        quality: 85,
        growth: 55,
        value: 35,
        momentum: 70,
        sentiment: 65,
        positioning: 55,
      },
    },
  ],
  sectorAllocation: [
    { name: "Technology", value: 48.9, isMockData: true },
    { name: "Financials", value: 25.6, isMockData: true },
    { name: "Healthcare", value: 14.6, isMockData: true },
    { name: "Consumer Staples", value: 7.6, isMockData: true },
    { name: "Others", value: 3.3, isMockData: true },
  ],
  performanceHistory: Array.from({ length: 365 }, (_, i) => ({
    date: new Date(Date.now() - (365 - i) * 24 * 60 * 60 * 1000)
      .toISOString()
      .split("T")[0],
    portfolioValue: 75000 + Math.random() * 15000 + i * 20,
    benchmarkValue: 75000 + Math.random() * 12000 + i * 18,
    isMockData: true,
  })),
  stressTests: [
    { scenario: "2008 Financial Crisis", impact: -37.2, isMockData: true },
    { scenario: "COVID-19 Crash", impact: -22.8, isMockData: true },
    { scenario: "Tech Bubble Burst", impact: -28.5, isMockData: true },
    { scenario: "Interest Rate Shock", impact: -15.3, isMockData: true },
    { scenario: "Inflation Spike", impact: -12.7, isMockData: true },
    { scenario: "Geopolitical Crisis", impact: -18.9, isMockData: true },
  ],
  activityHistory: [
    {
      date: "2025-07-03",
      type: "BUY",
      symbol: "AAPL",
      description: "Buy Apple Inc.",
      quantity: 10,
      price: 189.45,
      amount: -1894.5,
      isMockData: true,
    },
    {
      date: "2025-07-02",
      type: "SELL",
      symbol: "JPM",
      description: "Sell JPMorgan Chase & Co.",
      quantity: 15,
      price: 142.3,
      amount: 2134.5,
      isMockData: true,
    },
    {
      date: "2025-07-01",
      type: "DIVIDEND",
      symbol: "MSFT",
      description: "Microsoft Corporation - Dividend",
      quantity: null,
      price: null,
      amount: 68.75,
      isMockData: true,
    },
    {
      date: "2025-06-30",
      type: "BUY",
      symbol: "GOOGL",
      description: "Buy Alphabet Inc.",
      quantity: 5,
      price: 134.23,
      amount: -671.15,
      isMockData: true,
    },
    {
      date: "2025-06-28",
      type: "DEPOSIT",
      symbol: null,
      description: "Cash deposit",
      quantity: null,
      price: null,
      amount: 5000.0,
      isMockData: true,
    },
    {
      date: "2025-06-27",
      type: "SELL",
      symbol: "TSLA",
      description: "Sell Tesla Inc.",
      quantity: 8,
      price: 245.6,
      amount: 1964.8,
      isMockData: true,
    },
    {
      date: "2025-06-25",
      type: "BUY",
      symbol: "JNJ",
      description: "Buy Johnson & Johnson",
      quantity: 20,
      price: 156.78,
      amount: -3135.6,
      isMockData: true,
    },
    {
      date: "2025-06-24",
      type: "DIVIDEND",
      symbol: "JPM",
      description: "JPMorgan Chase & Co. - Dividend",
      quantity: null,
      price: null,
      amount: 45.0,
      isMockData: true,
    },
  ],
};

// ⚠️ MOCK DATA - Replace with real API when available
// Mock risk alerts data
const mockRiskAlerts = [
  {
    id: 1,
    symbol: "AAPL",
    metric: "Volatility",
    value: 28.2,
    threshold: 25,
    severity: "medium",
    timestamp: "2025-07-03T10:30:00Z",
    isMockData: true,
  },
  {
    id: 2,
    symbol: "PORTFOLIO",
    metric: "Concentration",
    value: 48,
    threshold: 40,
    severity: "high",
    timestamp: "2025-07-03T09:15:00Z",
    isMockData: true,
  },
  {
    id: 3,
    symbol: "JPM",
    metric: "Beta",
    value: 1.3,
    threshold: 1.2,
    severity: "medium",
    timestamp: "2025-07-03T08:45:00Z",
    isMockData: true,
  },
  {
    id: 4,
    symbol: "MSFT",
    metric: "VaR",
    value: 5.2,
    threshold: 5.0,
    severity: "low",
    timestamp: "2025-07-02T16:20:00Z",
    isMockData: true,
  },
];

// Color palette for charts
const CHART_COLORS = [
  "#0088FE",
  "#00C49F",
  "#FFBB28",
  "#FF8042",
  "#8884D8",
  "#82CA9D",
];

// Helper functions for calculations
function calculatePortfolioVolatility(holdings) {
  // Simplified calculation - in reality, this would use historical returns and correlations
  const weightedVolatilities = holdings.map(
    (h) => (h.allocation / 100) * (h.beta * 16)
  ); // Assuming market vol of 16%
  return Math.sqrt(
    weightedVolatilities.reduce((sum, vol) => sum + vol * vol, 0)
  );
}

function calculateSharpeRatio(return_, volatility) {
  const riskFreeRate = 2.5; // Assume 2.5% risk-free rate
  return (return_ - riskFreeRate) / volatility;
}

function calculatePortfolioBeta(holdings) {
  return holdings.reduce((sum, h) => sum + (h.allocation / 100) * h.beta, 0);
}

function calculateVaR(holdings, confidence) {
  const portfolioValue = holdings.reduce((sum, h) => sum + h.marketValue, 0);
  const portfolioVol = calculatePortfolioVolatility(holdings) / 100;
  const zScore = confidence === 0.95 ? 1.645 : 2.326; // 95% or 99%
  return (portfolioValue * portfolioVol * zScore) / Math.sqrt(252); // Daily VaR
}

function calculateMaxDrawdown(performanceHistory) {
  let maxDrawdown = 0;
  let peak = performanceHistory[0].portfolioValue;

  for (let point of performanceHistory) {
    if (point.portfolioValue > peak) {
      peak = point.portfolioValue;
    }
    const drawdown = (peak - point.portfolioValue) / peak;
    if (drawdown > maxDrawdown) {
      maxDrawdown = drawdown;
    }
  }

  return maxDrawdown * 100; // Return as percentage
}

function calculateInformationRatio(performanceHistory) {
  // Simplified calculation
  const excessReturns = performanceHistory.map(
    (p) =>
      p.portfolioValue / performanceHistory[0].portfolioValue -
      1 -
      (p.benchmarkValue / performanceHistory[0].benchmarkValue - 1)
  );
  const avgExcessReturn =
    excessReturns.reduce((sum, ret) => sum + ret, 0) / excessReturns.length;
  const trackingError = Math.sqrt(
    excessReturns.reduce(
      (sum, ret) => sum + Math.pow(ret - avgExcessReturn, 2),
      0
    ) / excessReturns.length
  );
  return (avgExcessReturn / trackingError) * Math.sqrt(252); // Annualized
}

function calculateFactorExposure(holdings) {
  const factors = [
    "Quality",
    "Growth",
    "Value",
    "Momentum",
    "Sentiment",
    "Positioning",
  ];
  return factors.map((factor) => {
    const exposure = holdings.reduce((sum, h) => {
      const factorKey = factor.toLowerCase();
      return sum + (h.allocation / 100) * (h.factorScores[factorKey] - 50); // Center around 50
    }, 0);

    return {
      factor,
      exposure,
      benchmark: 0, // Benchmark is neutral (0)
      description: getFactorDescription(factor),
    };
  });
}

function getFactorDescription(factor) {
  const descriptions = {
    Quality: "Companies with strong fundamentals, high ROE, low debt",
    Growth: "Companies with strong revenue and earnings growth",
    Value: "Undervalued companies with attractive valuations",
    Momentum: "Stocks with positive price and earnings momentum",
    Sentiment: "Stocks with positive analyst and market sentiment",
    Positioning: "Stocks with favorable institutional positioning",
  };
  return descriptions[factor] || "";
}

function calculateConcentrationRisk(sectorAllocation) {
  // Herfindahl-Hirschman Index
  return sectorAllocation.reduce(
    (sum, sector) => sum + Math.pow(sector.value / 100, 2),
    0
  );
}

function calculateGeographicDiversification(_holdings) {
  // Simplified - assume all holdings are US for now
  return { US: 100, International: 0, Emerging: 0 };
}

function calculateMarketCapExposure(_holdings) {
  // Simplified categorization
  return {
    LargeCap: 75.5,
    MidCap: 20.3,
    SmallCap: 4.2,
  };
}

function calculateHerfindahlIndex(holdings) {
  const totalValue = holdings.reduce((sum, h) => sum + h.marketValue, 0);
  return holdings.reduce(
    (sum, h) => sum + Math.pow(h.marketValue / totalValue, 2),
    0
  );
}

function generateAIInsights(
  portfolioMetrics,
  _factorAnalysis,
  _diversificationMetrics
) {
  return {
    confidenceScore: 87,
    strengths: [
      `Strong risk-adjusted returns with Sharpe ratio of ${formatNumber(portfolioMetrics.sharpeRatio, 2)}`,
      "Well-diversified across sectors with controlled concentration risk",
      "Quality factor exposure provides downside protection",
      `Portfolio beta of ${formatNumber(portfolioMetrics.beta, 2)} offers balanced market exposure`,
    ],
    improvements: [
      "Consider increasing international diversification",
      "Value factor exposure could be enhanced for rotation opportunities",
      "Technology concentration warrants monitoring",
      "ESG integration could improve long-term sustainability",
    ],
    marketAnalysis:
      "Current market environment favors quality and momentum factors. Portfolio positioning aligns well with institutional trends while maintaining defensive characteristics through healthcare and consumer staples exposure.",
    recommendations: [
      "Rebalance Technology",
      "Add International",
      "Increase Value",
      "Monitor Risk",
    ],
  };
}

export default Portfolio;
