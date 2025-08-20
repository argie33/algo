import React, { useState, useEffect, useMemo } from "react";
import { useAuth } from "../contexts/AuthContext";
import {
  Box,
  Container,
  Typography,
  Card,
  CardContent,
  Button,
  TextField,
  MenuItem,
  Grid,
  CircularProgress,
  Alert,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  CardHeader,
  Divider,
  LinearProgress,
  Badge,
  IconButton,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  FormControl,
  InputLabel,
  Select,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
} from "@mui/material";
import {
  PlayArrow, Refresh, Assessment, TrendingUp, TrendingDown, Warning, CheckCircle, Info, ExpandMore, Download as DownloadIcon, Save as SaveIcon, HelpOutline, Stop, Share, Delete, Edit, Add, FolderOpen, Person, } from "@mui/icons-material";
import Autocomplete from "@mui/material/Autocomplete";
import { Line } from "react-chartjs-2";
import { Bar } from "react-chartjs-2";
import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import Switch from "@mui/material/Switch";
import FormControlLabel from "@mui/material/FormControlLabel";
import Tooltip from "@mui/material/Tooltip";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip as ChartTooltip,
  Legend,
  ArcElement,
} from "chart.js";

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  ChartTooltip,
  Legend,
  ArcElement
);

const API_BASE = import.meta.env.VITE_API_URL || "";

// Helper function to calculate advanced metrics
const getAdvancedMetrics = (result) => {
  if (!result?.equity || !result?.trades) return {};

  const equity = result.equity;
  const trades = result.trades;
  const returns = equity
    .slice(1)
    .map((val, i) => (val.value - equity[i].value) / equity[i].value);

  // Sortino Ratio
  const downside = returns.filter((r) => r < 0);
  const downsideStd = Math.sqrt(
    downside.reduce((sum, r) => sum + r * r, 0) / downside.length
  );
  const sortinoRatio =
    returns.length > 0
      ? returns.reduce((a, b) => a + b, 0) / returns.length / (downsideStd || 1)
      : 0;

  // Calmar Ratio
  const maxDD = result.metrics?.maxDrawdown || 0;
  const calmarRatio =
    maxDD !== 0 ? (result.metrics?.annualizedReturn || 0) / Math.abs(maxDD) : 0;

  // Information Ratio (assuming benchmark return of 8%)
  const benchmarkReturn = 0.08;
  const excessReturns = returns.map((r) => r - benchmarkReturn / 252); // Daily benchmark
  const trackingError = Math.sqrt(
    excessReturns.reduce((sum, r) => sum + r * r, 0) / excessReturns.length
  );
  const informationRatio =
    trackingError !== 0
      ? excessReturns.reduce((a, b) => a + b, 0) /
        excessReturns.length /
        trackingError
      : 0;

  // Average Trade Duration
  const avgTradeDuration =
    trades.length > 1
      ? trades.slice(1).reduce((sum, trade, i) => {
          const prevDate = new Date(trades[i].date);
          const currDate = new Date(trade.date);
          return sum + (currDate - prevDate) / (1000 * 60 * 60 * 24);
        }, 0) /
        (trades.length - 1)
      : 0;

  // Profit Factor
  const winners = trades.filter((t) => (t.pnl || 0) > 0);
  const losers = trades.filter((t) => (t.pnl || 0) < 0);
  const grossProfit = winners.reduce((sum, t) => sum + (t.pnl || 0), 0);
  const grossLoss = Math.abs(losers.reduce((sum, t) => sum + (t.pnl || 0), 0));
  const profitFactor = grossLoss !== 0 ? grossProfit / grossLoss : 0;

  // Expectancy
  const avgWin = winners.length > 0 ? grossProfit / winners.length : 0;
  const avgLoss = losers.length > 0 ? grossLoss / losers.length : 0;
  const winRate =
    trades.length > 0 ? (winners.length / trades.length) * 100 : 0;
  const expectancy =
    (winRate / 100) * avgWin - ((100 - winRate) / 100) * avgLoss;

  return {
    sortinoRatio,
    calmarRatio,
    informationRatio: informationRatio * Math.sqrt(252), // Annualized
    avgTradeDuration,
    profitFactor,
    expectancy,
    avgWin,
    avgLoss,
    grossProfit,
    grossLoss,
  };
};

const defaultParams = {
  symbol: "",
  strategy: "",
  startDate: "",
  endDate: "",
};

export default function Backtest() {
  // Authentication
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();

  const [params, setParams] = useState(defaultParams);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [symbols, setSymbols] = useState([]);
  const [strategies, setStrategies] = useState([]);
  const [strategyParams, setStrategyParams] = useState({});
  const [strategyCode, setStrategyCode] = useState("");
  const [pythonCode, setPythonCode] = useState("");
  const [useCustomCode, setUseCustomCode] = useState(false);
  const [logs, setLogs] = useState("");
  const [savedStrategies, setSavedStrategies] = useState([]);
  const [showApiExample, setShowApiExample] = useState(false);
  const [validateStatus, setValidateStatus] = useState(null);
  const [validateMsg, setValidateMsg] = useState("");
  const [activeTab, setActiveTab] = useState("equity");
  const [isRunning, setIsRunning] = useState(false);
  const [customMetricTab, setCustomMetricTab] = useState(null);

  // Enhanced strategy management
  const [strategyDialogOpen, setStrategyDialogOpen] = useState(false);
  const [newStrategy, setNewStrategy] = useState({
    name: "",
    description: "",
    code: "",
    isPublic: false,
  });
  const [selectedStrategy, setSelectedStrategy] = useState(null);
  const [strategyTags, setStrategyTags] = useState([]);
  const [strategyFilter, setStrategyFilter] = useState("all"); // 'all', 'mine', 'public', 'favorites'

  // Parameter sweep state
  const [sweepParams, setSweepParams] = useState({});
  const [sweepResults, setSweepResults] = useState([]);
  const [sweepRunning, setSweepRunning] = useState(false);
  const [sweepProgress, setSweepProgress] = useState({ current: 0, total: 0 });

  // --- BATCH QUEUE STATE ---
  const [batchQueue, setBatchQueue] = useState([]); // [{params, status, result, error}]
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchProgress, setBatchProgress] = useState(0);
  const [batchCancelled, setBatchCancelled] = useState(false);

  // --- STRATEGY VERSIONING ---
  const [strategyHistory, setStrategyHistory] = useState({}); // {strategyId: [versions]}

  // Helper: get param config for selected strategy (could be from backend or hardcoded)
  const paramConfig = useMemo(() => {
    const strat = Array.isArray(strategies)
      ? strategies.find((s) => s.id === params.strategy)
      : null;
    if (!strat) return [];
    // Example: parse from strat.code or attach config in backend
    if (strat.id === "moving_average_crossover") {
      return [
        {
          name: "shortPeriod",
          label: "Short MA Period",
          type: "number",
          default: 20,
        },
        {
          name: "longPeriod",
          label: "Long MA Period",
          type: "number",
          default: 50,
        },
      ];
    }
    if (strat.id === "rsi_strategy") {
      return [
        {
          name: "rsiOversold",
          label: "RSI Oversold",
          type: "number",
          default: 30,
        },
        {
          name: "rsiOverbought",
          label: "RSI Overbought",
          type: "number",
          default: 70,
        },
      ];
    }
    return [];
  }, [strategies, params.strategy]);

  useEffect(() => {
    // Fetch symbols
    fetch(`${API_BASE}/backtest/symbols`)
      .then((r) => r.json())
      .then((d) => setSymbols(d.symbols || []))
      .catch(() => {
        // Fallback data
        setSymbols([
          "AAPL",
          "MSFT",
          "GOOGL",
          "TSLA",
          "NVDA",
          "AMZN",
          "META",
          "SPY",
          "QQQ",
        ]);
      });
    // Fetch strategies/templates
    fetch(`${API_BASE}/backtest/templates`)
      .then((r) => r.json())
      .then((d) => setStrategies(d.templates || []))
      .catch(() => {
        // Fallback templates
        setStrategies([
          {
            id: "moving_average_crossover",
            name: "Moving Average Crossover",
            code: "MA_CROSSOVER_CODE",
          },
          {
            id: "rsi_strategy",
            name: "RSI Strategy",
            code: "RSI_STRATEGY_CODE",
          },
          {
            id: "mean_reversion",
            name: "Mean Reversion",
            code: "MEAN_REVERSION_CODE",
          },
        ]);
      });
    // Fetch user strategies from backend (only if authenticated)
    if (isAuthenticated && user) {
      fetchUserStrategies();
    } else {
      // Load from localStorage for non-authenticated users
      const localStrategies = JSON.parse(
        localStorage.getItem("backtester_strategies") || "[]"
      );
      setSavedStrategies(localStrategies);
    }
  }, [isAuthenticated, user]);

  // Enhanced: Fetch user-specific strategies
  const fetchUserStrategies = async () => {
    try {
      const headers = { "Content-Type": "application/json" };
      if (user?.token) {
        headers["Authorization"] = `Bearer ${user.token}`;
      }

      const response = await fetch(`${API_BASE}/backtest/strategies`, {
        headers,
      });
      if (response.ok) {
        const data = await response.json();
        setSavedStrategies(data.strategies || []);
      }
    } catch (error) {
      console.error("Error fetching user strategies:", error);
      // Fallback to localStorage
      const localStrategies = JSON.parse(
        localStorage.getItem("backtester_strategies") || "[]"
      );
      setSavedStrategies(localStrategies);
    }
  };

  // Enhanced: Save strategy with authentication support
  const handleSaveStrategy = async () => {
    if (!newStrategy.name.trim()) {
      alert("Please enter a strategy name");
      return;
    }

    const strategyData = {
      ...newStrategy,
      code: useCustomCode ? pythonCode : strategyCode,
      params: strategyParams,
      createdAt: new Date().toISOString(),
      author: user?.username || user?.email || "Anonymous",
      userId: user?.id || null,
    };

    try {
      if (isAuthenticated && user) {
        // Save to backend
        const headers = { "Content-Type": "application/json" };
        if (user?.token) {
          headers["Authorization"] = `Bearer ${user.token}`;
        }

        const response = await fetch(`${API_BASE}/backtest/strategies`, {
          method: "POST",
          headers,
          body: JSON.stringify(strategyData),
        });

        if (response.ok) {
          await fetchUserStrategies();
        } else {
          throw new Error("Failed to save strategy to server");
        }
      } else {
        // Save to localStorage for non-authenticated users
        const localStrategies = JSON.parse(
          localStorage.getItem("backtester_strategies") || "[]"
        );
        const newId = Date.now().toString();
        localStrategies.push({ ...strategyData, id: newId });
        localStorage.setItem(
          "backtester_strategies",
          JSON.stringify(localStrategies)
        );
        setSavedStrategies(localStrategies);
      }

      setStrategyDialogOpen(false);
      setNewStrategy({ name: "", description: "", code: "", isPublic: false });
    } catch (error) {
      console.error("Error saving strategy:", error);
      alert("Failed to save strategy. Please try again.");
    }
  };

  // Enhanced: Load strategy with versioning
  const handleLoadStrategy = (strategy) => {
    if (strategy.code) {
      if (strategy.language === "python" || useCustomCode) {
        setPythonCode(strategy.code);
        setUseCustomCode(true);
      } else {
        setStrategyCode(strategy.code);
      }
    }
    if (strategy.params) {
      setStrategyParams(strategy.params);
    }
    setSelectedStrategy(strategy);
  };

  // Enhanced: Delete strategy with confirmation
  const handleDeleteStrategy = async (strategyId) => {
    if (!confirm("Are you sure you want to delete this strategy?")) {
      return;
    }

    try {
      if (isAuthenticated && user) {
        const headers = { "Content-Type": "application/json" };
        if (user?.token) {
          headers["Authorization"] = `Bearer ${user.token}`;
        }

        const response = await fetch(
          `${API_BASE}/backtest/strategies/${strategyId}`,
          {
            method: "DELETE",
            headers,
          }
        );

        if (response.ok) {
          await fetchUserStrategies();
        }
      } else {
        // Remove from localStorage
        const localStrategies = JSON.parse(
          localStorage.getItem("backtester_strategies") || "[]"
        );
        const filtered = localStrategies.filter((s) => s.id !== strategyId);
        localStorage.setItem("backtester_strategies", JSON.stringify(filtered));
        setSavedStrategies(filtered);
      }
    } catch (error) {
      console.error("Error deleting strategy:", error);
    }
  };

  useEffect(() => {
    const strat = Array.isArray(strategies)
      ? strategies.find((s) => s.id === params.strategy)
      : null;
    setStrategyCode(strat?.code || "");
    // Set default param values
    if (paramConfig.length) {
      const defaults = {};
      paramConfig.forEach((p) => {
        defaults[p.name] = p.default;
      });
      setStrategyParams(defaults);
    }
  }, [params.strategy, strategies, paramConfig]);

  const handleChange = (field, value) => {
    setParams((prev) => ({ ...prev, [field]: value }));
  };

  const handleStrategyParamChange = (name, value) => {
    setStrategyParams((prev) => ({ ...prev, [name]: value }));
  };

  const handleRun = async () => {
    setLoading(true);
    setIsRunning(true);
    setError(null);
    setResult(null);
    setLogs("");
    try {
      let res, data;
      if (useCustomCode) {
        // Custom code mode: send to /run-python
        res = await fetch(`${API_BASE}/backtest/run-python`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ strategy: pythonCode }),
        });
        data = await res.json();
      } else {
        const body = {
          ...params,
          ...strategyParams,
          strategy: params.strategy,
        };
        res = await fetch(`${API_BASE}/backtest/run`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        data = await res.json();
      }
      if (!data.success) throw new Error(data.error || "Backtest failed");
      setResult(data);
      setLogs(data.logs || data.stdout || "");
      setActiveTab("equity");
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
      setIsRunning(false);
    }
  };

  const handleStop = () => {
    // For now, just set running to false and loading to false (simulate stop)
    setIsRunning(false);
    setLoading(false);
    setError("Backtest stopped by user.");
  };

  const handleExport = () => {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `backtest_${params.symbol}_${params.strategy}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleDownloadLogs = () => {
    if (!logs) return;
    const blob = new Blob([logs], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `backtest_logs_${params.symbol}_${params.strategy || "custom"}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleStrategyChange = (id) => {
    const strat = Array.isArray(strategies)
      ? strategies.find((s) => s.id === id)
      : null;
    handleChange("strategy", id);
    // Optionally parse params from strat.code or add UI for params
  };

  const handleExportTrades = () => {
    if (!result?.trades?.length) return;
    const csv = [
      "Date,Action,Price,Shares,PnL",
      ...result.trades.map(
        (t) => `${t.date},${t.action},${t.price},${t.shares},${t.pnl}`
      ),
    ].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `backtest_trades_${params.symbol}_${params.strategy || "custom"}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const apiExample = `import requests\n\nurl = '${API_BASE}/backtest/run'\npayload = {\n    'symbol': '${params.symbol}',\n    'strategy_code': '''\n${pythonCode.replace(/'/g, "''")}\n''',\n    'language': 'python'\n}\nresponse = requests.post(url, json=payload)\nprint(response.json())`;
  const curlExample = `curl -X POST '${API_BASE}/backtest/run' \\\n  -H 'Content-Type: application/json' \\\n  -d '{\n    "symbol": "${params.symbol}",\n    "strategy_code": """\n${pythonCode.replace(/"/g, '"')}\n""",\n    "language": "python"\n  }'`;

  const handleCopyApiExample = () => {
    navigator.clipboard.writeText(apiExample);
  };

  // Validate custom code (Python or JS)
  const handleValidate = async () => {
    setValidateStatus("pending");
    setValidateMsg("");
    try {
      const res = await fetch(`${API_BASE}/backtest/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy: pythonCode }),
      });
      const data = await res.json();
      if (data.valid) {
        setValidateStatus("success");
        setValidateMsg("Code is valid!");
      } else {
        setValidateStatus("error");
        setValidateMsg(data.error || "Invalid code");
      }
    } catch (e) {
      setValidateStatus("error");
      setValidateMsg(e.message);
    }
  };

  // Helper to compute drawdown series from equity
  const getDrawdownSeries = (equity) => {
    if (!equity || equity.length === 0) return [];
    let peak = equity[0].value;
    return equity.map((point) => {
      if (point.value > peak) peak = point.value;
      return {
        date: point.date,
        drawdown: ((point.value - peak) / peak) * 100,
      };
    });
  };

  // Helper: get trade markers for equity curve
  const getTradeMarkers = (equity, trades) => {
    if (!equity || !trades) return [];
    return trades
      .map((trade) => {
        const idx = equity.findIndex((e) => e.date === trade.date);
        return idx >= 0
          ? {
              x: idx,
              y: equity[idx].value,
              action: trade.action,
              price: trade.price,
            }
          : null;
      })
      .filter(Boolean);
  };

  const handleRenameStrategy = async (id) => {
    const strategy = savedStrategies.find((s) => s.id === id);
    if (!strategy) return;
    const newName = prompt(
      "Enter a new name for this strategy:",
      strategy.name
    );
    if (!newName || newName === strategy.name) return;
    // Update backend (simulate PATCH by delete+add)
    await fetch(`${API_BASE}/backtest/strategies/${id}`, { method: "DELETE" });
    const res = await fetch(`${API_BASE}/backtest/strategies`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: newName,
        code: strategy.code,
        language: strategy.language,
      }),
    });
    const data = await res.json();
    setSavedStrategies((prev) =>
      prev.filter((s) => s.id !== id).concat(data.strategy)
    );
  };

  // Helper: generate all combinations of sweep parameters
  const getSweepCombinations = () => {
    if (!paramConfig.length) return [];
    const keys = paramConfig.map((p) => p.name);
    const values = keys.map((k) => {
      const val = sweepParams[k];
      if (!val)
        return [
          strategyParams[k] ?? paramConfig.find((p) => p.name === k)?.default,
        ];
      // Support comma-separated lists or ranges (e.g. 10,20,30 or 10-30:5)
      if (val.includes(","))
        return val.split(",").map((v) => parseFloat(v.trim()));
      if (val.includes("-") && val.includes(":")) {
        const [start, rest] = val.split("-");
        const [end, step] = rest.split(":");
        const arr = [];
        for (
          let i = parseFloat(start);
          i <= parseFloat(end);
          i += parseFloat(step)
        )
          arr.push(i);
        return arr;
      }
      return [parseFloat(val)];
    });
    // Cartesian product
    return values
      .reduce((a, b) => a.flatMap((d) => b.map((e) => [].concat(d, e))), [[]])
      .map((arr) => {
        const obj = {};
        arr.forEach((v, i) => {
          obj[keys[i]] = v;
        });
        return obj;
      });
  };

  const handleSweepParamChange = (name, value) => {
    setSweepParams((prev) => ({ ...prev, [name]: value }));
  };

  const handleRunSweep = async () => {
    const combos = getSweepCombinations();
    if (!combos.length) return;
    setSweepRunning(true);
    setSweepProgress({ current: 0, total: combos.length });
    setSweepResults([]);
    for (let i = 0; i < combos.length; ++i) {
      if (!sweepRunning) break;
      const combo = combos[i];
      const body = { ...params, ...combo, strategy: params.strategy };
      try {
        const res = await fetch(`${API_BASE}/backtest/run`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = await res.json();
        setSweepResults((prev) => [
          ...prev,
          {
            params: combo,
            metrics: data.metrics,
            success: data.success,
            error: data.error,
          },
        ]);
      } catch (e) {
        setSweepResults((prev) => [
          ...prev,
          { params: combo, metrics: null, success: false, error: e.message },
        ]);
      }
      setSweepProgress({ current: i + 1, total: combos.length });
    }
    setSweepRunning(false);
  };

  const handleStopSweep = () => {
    setSweepRunning(false);
  };

  // --- BATCH RUN LOGIC ---
    setBatchQueue(
      paramGrid.map((p) => ({
        params: p,
        status: "pending",
        result: null,
        error: null,
      }))
    );
    setBatchRunning(true);
    setBatchProgress(0);
    setBatchCancelled(false);
    let completed = 0;
    for (let i = 0; i < paramGrid.length; ++i) {
      if (batchCancelled) break;
      setBatchQueue((q) =>
        q.map((item, idx) =>
          idx === i ? { ...item, status: "running" } : item
        )
      );
      try {
        const res = await fetch(`${API_BASE}/backtest/run`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...paramGrid[i], strategy: params.strategy }),
        });
        const data = await res.json();
        setBatchQueue((q) =>
          q.map((item, idx) =>
            idx === i
              ? {
                  ...item,
                  status: data.success ? "done" : "error",
                  result: data.success ? data : null,
                  error: data.success ? null : data.error || "Error",
                }
              : item
          )
        );
      } catch (e) {
        setBatchQueue((q) =>
          q.map((item, idx) =>
            idx === i ? { ...item, status: "error", error: e.message } : item
          )
        );
      }
      completed++;
      setBatchProgress(completed / paramGrid.length);
    }
    setBatchRunning(false);
  };
  const handleBatchCancel = () => {
    setBatchCancelled(true);
    setBatchRunning(false);
  };

  // --- STRATEGY VERSIONING LOGIC ---
    setStrategyHistory((h) => ({
      ...h,
      [id]: [...(h[id] || []), { code, date: new Date().toISOString() }],
    }));
  };

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box display="flex" alignItems="center" justifyContent="between" mb={4}>
        <Box>
          <Typography variant="h3" component="h1" gutterBottom>
            Institutional Backtester
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Professional-grade strategy testing with advanced analytics and risk
            management
          </Typography>
          <Box display="flex" gap={1} mt={1}>
            <Chip
              label="Live Execution"
              color="primary"
              size="small"
              variant="outlined"
            />
            <Chip
              label="Risk Analytics"
              color="success"
              size="small"
              variant="outlined"
            />
            <Chip
              label="Advanced Metrics"
              color="info"
              size="small"
              variant="outlined"
            />
            <Chip
              label="Multi-Asset"
              color="warning"
              size="small"
              variant="outlined"
            />
          </Box>
        </Box>

        <Box display="flex" alignItems="center" gap={2}>
          {/* Authentication Status */}
          {authLoading ? (
            <CircularProgress size={24} />
          ) : isAuthenticated ? (
            <Box display="flex" alignItems="center" gap={1}>
              <Person color="primary" />
              <Typography variant="body2" color="primary">
                {user?.username || user?.email || "User"}
              </Typography>
            </Box>
          ) : (
            <Chip
              label="Guest Mode"
              color="warning"
              size="small"
              variant="outlined"
            />
          )}

          {/* Strategy Management */}
          <Badge badgeContent={savedStrategies.length} color="primary">
            <Button
              variant="outlined"
              startIcon={<FolderOpen />}
              onClick={() => setStrategyDialogOpen(true)}
              size="small"
            >
              My Strategies
            </Button>
          </Badge>

          <Tooltip title="Save current strategy" arrow>
            <Button
              variant="outlined"
              startIcon={<Save />}
              onClick={() => {
                setNewStrategy({
                  name: "",
                  description: "",
                  code: useCustomCode ? pythonCode : strategyCode,
                  isPublic: false,
                });
                setStrategyDialogOpen(true);
              }}
              size="small"
            >
              Save Strategy
            </Button>
          </Tooltip>

          <Tooltip title="Start a new blank strategy" arrow>
            <Button
              variant="outlined"
              startIcon={<Add />}
              onClick={() => {
                setPythonCode("");
                setParams(defaultParams);
                setStrategyParams({});
                setResult(null);
                setError(null);
                setSelectedStrategy(null);
              }}
              size="small"
            >
              New Strategy
            </Button>
          </Tooltip>
        </Box>
      </Box>
      <Card sx={{ mb: 4 }}>
        <CardHeader
          title="Strategy Configuration"
          subheader="Configure your backtesting parameters and strategy logic"
          action={
            <Box display="flex" gap={1}>
              <Chip
                label={params.symbol || "No Symbol"}
                color="primary"
                variant="outlined"
              />
              <Chip
                label={params.strategy || "No Strategy"}
                color="secondary"
                variant="outlined"
              />
            </Box>
          }
        />
        <Divider />
        <CardContent>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6}>
              <Tooltip title="Choose a symbol to backtest" arrow>
                <Autocomplete
                  options={symbols.map((s) => s.symbol)}
                  value={params.symbol}
                  onChange={(_, v) => handleChange("symbol", v || "")}
                  renderInput={(props) => (
                    <TextField
                      {...props}
                      label="Symbol"
                      fullWidth
                      size="small"
                    />
                  )}
                />
              </Tooltip>
            </Grid>
            <Grid item xs={12} sm={6}>
              <Tooltip title="Select a strategy template or your own" arrow>
                <TextField
                  select
                  label="Strategy"
                  value={params.strategy}
                  onChange={(e) => handleStrategyChange(e.target.value)}
                  fullWidth
                  size="small"
                >
                  {strategies.map((s) => (
                    <MenuItem key={s.id} value={s.id}>
                      {s.name}
                    </MenuItem>
                  ))}
                </TextField>
              </Tooltip>
            </Grid>
            <Grid item xs={12} sm={6}>
              <Tooltip title="Backtest start date" arrow>
                <TextField
                  label="Start Date"
                  type="date"
                  value={params.startDate}
                  onChange={(e) => handleChange("startDate", e.target.value)}
                  fullWidth
                  size="small"
                  InputLabelProps={{ shrink: true }}
                />
              </Tooltip>
            </Grid>
            <Grid item xs={12} sm={6}>
              <Tooltip title="Backtest end date" arrow>
                <TextField
                  label="End Date"
                  type="date"
                  value={params.endDate}
                  onChange={(e) => handleChange("endDate", e.target.value)}
                  fullWidth
                  size="small"
                  InputLabelProps={{ shrink: true }}
                />
              </Tooltip>
            </Grid>
            <Grid item xs={12}>
              <Box display="flex" flexWrap="wrap" gap={2}>
                {paramConfig.map((param) => (
                  <Tooltip key={param.name} title={param.label} arrow>
                    <TextField
                      label={param.label}
                      type={param.type}
                      value={strategyParams[param.name] ?? param.default}
                      onChange={(e) =>
                        handleStrategyParamChange(param.name, e.target.value)
                      }
                      size="small"
                      sx={{ width: 180 }}
                    />
                  </Tooltip>
                ))}
              </Box>
            </Grid>
            <Grid item xs={12}>
              <Box display="flex" alignItems="center" gap={1}>
                <Typography
                  variant="subtitle2"
                  color="text.secondary"
                  sx={{ mb: 1 }}
                >
                  Strategy Code
                </Typography>
                <Tooltip
                  title="Paste or edit your strategy code here. Python only."
                  arrow
                >
                  <HelpOutline fontSize="small" color="action" />
                </Tooltip>
              </Box>
              <Paper sx={{ p: 0, mb: 2, background: "#f7f7f7" }}>
                <CodeMirror
                  value={pythonCode}
                  height="300px"
                  extensions={[python()]}
                  onChange={(v) => setPythonCode(v)}
                  theme="light"
                />
              </Paper>
              <Button
                variant="outlined"
                startIcon={<SaveIcon />}
                onClick={handleSaveStrategy}
                sx={{ mb: 2, mr: 2 }}
              >
                Save Strategy
              </Button>
              <Button
                variant="outlined"
                startIcon={<ContentCopyIcon />}
                sx={{ mb: 2, mr: 2 }}
                onClick={() => setPythonCode(strategyCode)}
                disabled={!strategyCode}
              >
                Clone from Selected
              </Button>
              <Button
                variant="outlined"
                startIcon={<ContentCopyIcon />}
                sx={{ mb: 2 }}
                onClick={() => setPythonCode("")}
              >
                Clear
              </Button>
            </Grid>
            <Grid item xs={12}>
              <Box display="flex" alignItems="center" gap={2}>
                <Button
                  variant="contained"
                  color="primary"
                  startIcon={
                    loading || isRunning ? (
                      <CircularProgress size={16} color="inherit" />
                    ) : (
                      <PlayArrow />
                    )
                  }
                  onClick={handleRun}
                  disabled={loading || isRunning || !params.symbol}
                  size="large"
                  sx={{ minWidth: 180, height: 48 }}
                >
                  {loading || isRunning ? "Running..." : "Run Backtest"}
                </Button>

                <Button
                  variant="outlined"
                  startIcon={<Stop />}
                  onClick={handleStop}
                  disabled={!isRunning}
                  color="error"
                  size="large"
                >
                  Stop
                </Button>

                <Button
                  variant="outlined"
                  startIcon={<Refresh />}
                  onClick={() => {
                    setParams(defaultParams);
                    setResult(null);
                    setError(null);
                    setPythonCode("");
                    setStrategyParams({});
                  }}
                  disabled={loading || isRunning}
                  size="large"
                >
                  Reset
                </Button>

                <Tooltip title="Quick validation check">
                  <IconButton
                    onClick={handleValidate}
                    disabled={
                      !pythonCode.trim() || validateStatus === "pending"
                    }
                    color={
                      validateStatus === "success"
                        ? "success"
                        : validateStatus === "error"
                          ? "error"
                          : "default"
                    }
                  >
                    {validateStatus === "pending" ? (
                      <CircularProgress size={20} />
                    ) : validateStatus === "success" ? (
                      <CheckCircle />
                    ) : validateStatus === "error" ? (
                      <Warning />
                    ) : (
                      <Info />
                    )}
                  </IconButton>
                </Tooltip>
              </Box>

              {validateMsg && (
                <Alert
                  severity={validateStatus === "success" ? "success" : "error"}
                  sx={{ mt: 2 }}
                  variant="outlined"
                >
                  {validateMsg}
                </Alert>
              )}
            </Grid>
          </Grid>
        </CardContent>
      </Card>
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}
      {/* Performance Dashboard */}
      {result && (
        <Card
          sx={{ mb: 4, bgcolor: "primary.dark", color: "primary.contrastText" }}
        >
          <CardHeader
            title="Performance Dashboard"
            subheader="Real-time strategy performance metrics"
            action={
              <Box display="flex" alignItems="center" gap={1}>
                <Chip
                  label={
                    result.metrics?.totalReturn >= 0 ? "PROFITABLE" : "LOSS"
                  }
                  color={result.metrics?.totalReturn >= 0 ? "success" : "error"}
                  size="small"
                />
                <Typography variant="caption" sx={{ opacity: 0.8 }}>
                  Last Updated: {new Date().toLocaleTimeString()}
                </Typography>
              </Box>
            }
          />
          <CardContent>
            <Grid container spacing={3}>
              {/* Primary Metrics */}
              <Grid item xs={12} md={3}>
                <Box textAlign="center">
                  <Typography variant="h4" fontWeight="bold">
                    {result.metrics?.totalReturn?.toFixed(2) ?? "--"}%
                  </Typography>
                  <Typography variant="body2" sx={{ opacity: 0.8 }}>
                    Total Return
                  </Typography>
                  <Box
                    display="flex"
                    alignItems="center"
                    justifyContent="center"
                    mt={1}
                  >
                    {(result.metrics?.totalReturn ?? 0) >= 0 ? (
                      <TrendingUp color="success" />
                    ) : (
                      <TrendingDown color="error" />
                    )}
                  </Box>
                </Box>
              </Grid>

              <Grid item xs={12} md={3}>
                <Box textAlign="center">
                  <Typography variant="h4" fontWeight="bold">
                    {result.metrics?.sharpeRatio?.toFixed(2) ?? "--"}
                  </Typography>
                  <Typography variant="body2" sx={{ opacity: 0.8 }}>
                    Sharpe Ratio
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={Math.min(
                      (result.metrics?.sharpeRatio ?? 0) * 50,
                      100
                    )}
                    sx={{ mt: 1, bgcolor: "rgba(255,255,255,0.2)" }}
                  />
                </Box>
              </Grid>

              <Grid item xs={12} md={3}>
                <Box textAlign="center">
                  <Typography variant="h4" fontWeight="bold">
                    {result.metrics?.maxDrawdown?.toFixed(2) ?? "--"}%
                  </Typography>
                  <Typography variant="body2" sx={{ opacity: 0.8 }}>
                    Max Drawdown
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={Math.min(
                      Math.abs(result.metrics?.maxDrawdown ?? 0),
                      100
                    )}
                    color="error"
                    sx={{ mt: 1, bgcolor: "rgba(255,255,255,0.2)" }}
                  />
                </Box>
              </Grid>

              <Grid item xs={12} md={3}>
                <Box textAlign="center">
                  <Typography variant="h4" fontWeight="bold">
                    {result.metrics?.totalTrades ?? "--"}
                  </Typography>
                  <Typography variant="body2" sx={{ opacity: 0.8 }}>
                    Total Trades
                  </Typography>
                  <Typography variant="body2" sx={{ opacity: 0.6, mt: 1 }}>
                    {result.metrics?.winRate?.toFixed(1) ?? "--"}% Win Rate
                  </Typography>
                </Box>
              </Grid>
            </Grid>

            {/* Secondary Metrics */}
            <Divider sx={{ my: 3, bgcolor: "rgba(255,255,255,0.2)" }} />
            <Grid container spacing={2}>
              <Grid item>
                <Chip
                  label={`Annualized: ${result.metrics?.annualizedReturn?.toFixed(2) ?? "--"}%`}
                  variant="outlined"
                  sx={{
                    color: "inherit",
                    borderColor: "rgba(255,255,255,0.5)",
                  }}
                />
              </Grid>
              <Grid item>
                <Chip
                  label={`Volatility: ${result.metrics?.volatility?.toFixed(2) ?? "--"}%`}
                  variant="outlined"
                  sx={{
                    color: "inherit",
                    borderColor: "rgba(255,255,255,0.5)",
                  }}
                />
              </Grid>
              <Grid item>
                <Chip
                  label={`Profit Factor: ${result.metrics?.profitFactor?.toFixed(2) ?? "--"}`}
                  variant="outlined"
                  sx={{
                    color: "inherit",
                    borderColor: "rgba(255,255,255,0.5)",
                  }}
                />
              </Grid>
              <Grid item>
                <Chip
                  label={`Sortino: ${getAdvancedMetrics(result).sortinoRatio?.toFixed(2) ?? "--"}`}
                  variant="outlined"
                  sx={{
                    color: "inherit",
                    borderColor: "rgba(255,255,255,0.5)",
                  }}
                />
              </Grid>
              <Grid item>
                <Chip
                  label={`Calmar: ${getAdvancedMetrics(result).calmarRatio?.toFixed(2) ?? "--"}`}
                  variant="outlined"
                  sx={{
                    color: "inherit",
                    borderColor: "rgba(255,255,255,0.5)",
                  }}
                />
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      )}
      <Paper sx={{ p: 3, position: "relative", minHeight: 400 }}>
        {(loading || isRunning) && (
          <Box
            sx={{
              position: "absolute",
              top: 0,
              left: 0,
              width: "100%",
              height: "100%",
              bgcolor: "rgba(255,255,255,0.7)",
              zIndex: 2,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <CircularProgress size={48} />
          </Box>
        )}
        {result && (
          <Tabs
            value={activeTab}
            onChange={(_, v) => setActiveTab(v)}
            sx={{ mb: 2 }}
          >
            <Tab label="Equity Curve" value="equity" />
            <Tab label="Drawdown" value="drawdown" />
            <Tab label="Trades" value="trades" />
            <Tab label="Logs" value="logs" />
            <Tab label="Summary" value="summary" />
            {result?.metrics?.custom &&
              Object.keys(result.metrics.custom).length > 0 &&
              Object.keys(result.metrics.custom).map((k, i) => (
                <Tab key={k} label={`Metric: ${k}`} value={`custom_${k}`} />
              ))}
          </Tabs>
        )}
        {result && activeTab === "equity" && result.equity && (
          <Box mb={2}>
            <Typography variant="subtitle2">Equity Curve</Typography>
            <Line
              data={{
                labels: result.equity.map((p) => p.date),
                datasets: [
                  {
                    label: "Equity Curve",
                    data: result.equity.map((p) => p.value),
                    borderColor: "#1976d2",
                    fill: false,
                    pointRadius: 0,
                  },
                  ...getTradeMarkers(result.equity, result.trades).map(
                    (marker) => ({
                      label: marker.action,
                      data: [{ x: marker.x, y: marker.y }],
                      pointBackgroundColor:
                        marker.action === "BUY" ? "#43a047" : "#e53935",
                      pointBorderColor:
                        marker.action === "BUY" ? "#43a047" : "#e53935",
                      pointRadius: 6,
                      type: "scatter",
                      showLine: false,
                    })
                  ),
                ],
              }}
              options={{
                responsive: true,
                plugins: { legend: { display: false } },
                scales: { x: { display: false } },
              }}
            />
          </Box>
        )}
        {result && activeTab === "drawdown" && result.equity && (
          <Box mb={2}>
            <Typography variant="subtitle2">Drawdown Chart</Typography>
            <Bar
              data={{
                labels: getDrawdownSeries(result.equity).map((p) => p.date),
                datasets: [
                  {
                    label: "Drawdown (%)",
                    data: getDrawdownSeries(result.equity).map(
                      (p) => p.drawdown
                    ),
                    backgroundColor: "#ff7043",
                  },
                ],
              }}
              options={{
                responsive: true,
                plugins: { legend: { display: false } },
                scales: {
                  y: {
                    min: Math.min(
                      ...getDrawdownSeries(result.equity).map((p) => p.drawdown)
                    ),
                    max: 0,
                  },
                },
              }}
            />
          </Box>
        )}
        {result &&
          activeTab === "trades" &&
          result.trades &&
          result.trades.length > 0 && (
            <Box mt={3}>
              <Typography variant="subtitle2">Trade Statistics</Typography>
              <TableContainer component={Paper} sx={{ mb: 2 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Date</TableCell>
                      <TableCell>Symbol</TableCell>
                      <TableCell>Action</TableCell>
                      <TableCell>Price</TableCell>
                      <TableCell>Shares</TableCell>
                      <TableCell>PnL</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {result.trades.map((t, i) => (
                      <TableRow key={i}>
                        <TableCell>{t.date}</TableCell>
                        <TableCell>{t.symbol}</TableCell>
                        <TableCell>{t.action}</TableCell>
                        <TableCell>{t.price}</TableCell>
                        <TableCell>{t.quantity || t.shares}</TableCell>
                        <TableCell>
                          {t.pnl !== undefined ? t.pnl.toFixed(2) : ""}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              <Button
                variant="outlined"
                sx={{ mb: 2 }}
                onClick={handleExportTrades}
              >
                Export Trades (CSV)
              </Button>
            </Box>
          )}
        {result && activeTab === "logs" && (
          <Box mt={2}>
            <Typography variant="subtitle2" color="text.secondary">
              Backtest Logs / Output
            </Typography>
            <Paper
              sx={{
                p: 2,
                fontFamily: "monospace",
                fontSize: 13,
                whiteSpace: "pre",
                overflowX: "auto",
                background: "#f7f7f7",
              }}
            >
              {logs}
            </Paper>
            <Button
              variant="outlined"
              startIcon={<DownloadIcon />}
              sx={{ mb: 2, mt: 2 }}
              onClick={handleDownloadLogs}
            >
              Download Logs
            </Button>
          </Box>
        )}
        {result && activeTab === "summary" && result.metrics && (
          <Box mb={2}>
            <Typography variant="subtitle1" fontWeight="bold">
              Performance Summary
            </Typography>
            <Grid container spacing={2}>
              <Grid item xs={6} md={3}>
                <Chip
                  label={`Total Return: ${result.metrics.totalReturn?.toFixed(2)}%`}
                  color="success"
                />
              </Grid>
              <Grid item xs={6} md={3}>
                <Chip
                  label={`Annualized: ${result.metrics.annualizedReturn?.toFixed(2)}%`}
                  color="info"
                />
              </Grid>
              <Grid item xs={6} md={3}>
                <Chip
                  label={`Sharpe: ${result.metrics.sharpeRatio?.toFixed(2)}`}
                  color="primary"
                />
              </Grid>
              <Grid item xs={6} md={3}>
                <Chip
                  label={`Max Drawdown: ${result.metrics.maxDrawdown?.toFixed(2)}%`}
                  color="warning"
                />
              </Grid>
              <Grid item xs={6} md={3}>
                <Chip
                  label={`Volatility: ${result.metrics.volatility?.toFixed(2)}%`}
                  color="default"
                />
              </Grid>
              <Grid item xs={6} md={3}>
                <Chip
                  label={`Win Rate: ${result.metrics.winRate?.toFixed(2)}%`}
                  color="success"
                />
              </Grid>
              <Grid item xs={6} md={3}>
                <Chip
                  label={`Profit Factor: ${result.metrics.profitFactor?.toFixed(2)}`}
                  color="info"
                />
              </Grid>
              <Grid item xs={6} md={3}>
                <Chip
                  label={`Trades: ${result.metrics.totalTrades}`}
                  color="secondary"
                />
              </Grid>
            </Grid>
          </Box>
        )}
        {result && (
          <Button
            variant="outlined"
            startIcon={<FileDownloadIcon />}
            sx={{ mb: 2, mr: 2 }}
            onClick={handleExport}
          >
            Export Results
          </Button>
        )}
        {result && (
          <Button
            variant="text"
            startIcon={<ContentCopyIcon />}
            sx={{ mb: 2, ml: 2 }}
            onClick={() => setShowApiExample((v) => !v)}
          >
            {showApiExample ? "Hide" : "Show"} API Example
          </Button>
        )}
        {result && showApiExample && (
          <Paper
            sx={{
              p: 2,
              fontFamily: "monospace",
              fontSize: 13,
              whiteSpace: "pre",
              overflowX: "auto",
              background: "#f7f7f7",
              mb: 2,
            }}
          >
            <Box
              display="flex"
              alignItems="center"
              justifyContent="space-between"
            >
              <span>Python API Example</span>
              <Button
                size="small"
                startIcon={<ContentCopyIcon />}
                onClick={handleCopyApiExample}
              >
                Copy
              </Button>
            </Box>
            {apiExample}
            <Box mt={2} />
            <Box
              display="flex"
              alignItems="center"
              justifyContent="space-between"
            >
              <span>cURL API Example</span>
              <Button
                size="small"
                startIcon={<ContentCopyIcon />}
                onClick={() => navigator.clipboard.writeText(curlExample)}
              >
                Copy
              </Button>
            </Box>
            {curlExample}
          </Paper>
        )}
        {activeTab.startsWith("custom_") &&
          result?.metrics?.custom &&
          (() => {
            const metricKey = activeTab.replace("custom_", "");
            const metric = result.metrics.custom[metricKey];
            if (!metric) return null;
            return (
              <Box mb={2}>
                <Typography variant="subtitle2">
                  Custom Metric: {metricKey}
                </Typography>
                <Line
                  data={{
                    labels: metric.map((p) => p.date || p[0]),
                    datasets: [
                      {
                        label: metricKey,
                        data: metric.map((p) => p.value ?? p[1]),
                        borderColor: "#8e24aa",
                        fill: false,
                        pointRadius: 0,
                      },
                    ],
                  }}
                  options={{
                    responsive: true,
                    plugins: { legend: { display: false } },
                    scales: { x: { display: false } },
                  }}
                />
              </Box>
            );
          })()}
      </Paper>
      {batchQueue.length > 0 && (
        <Card sx={{ mt: 4 }}>
          <CardContent>
            <Typography variant="h6">Batch Run Progress</Typography>
            <Box sx={{ width: "100%", mb: 2 }}>
              <LinearProgress
                variant="determinate"
                value={batchProgress * 100}
              />
              <Typography variant="body2">
                {Math.round(batchProgress * 100)}% complete
              </Typography>
            </Box>
            <Button
              variant="outlined"
              color="error"
              onClick={handleBatchCancel}
              disabled={!batchRunning}
            >
              Cancel Batch
            </Button>
            <TableContainer component={Paper} sx={{ mt: 2 }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Params</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Result</TableCell>
                    <TableCell>Error</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {batchQueue.map((item, i) => (
                    <TableRow key={i}>
                      <TableCell>{JSON.stringify(item.params)}</TableCell>
                      <TableCell>{item.status}</TableCell>
                      <TableCell>{item.result ? "✅" : ""}</TableCell>
                      <TableCell>{item.error}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            <Button
              variant="outlined"
              sx={{ mt: 2 }}
              onClick={() => {
                // Export all batch results as CSV
                const rows = batchQueue
                  .filter((b) => b.result)
                  .map((b) => ({ ...b.params, ...b.result.metrics }));
                const header = Object.keys(rows[0] || {}).join(",");
                const csv = [
                  header,
                  ...rows.map((r) => Object.values(r).join(",")),
                ].join("\n");
                const blob = new Blob([csv], { type: "text/csv" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = "batch_results.csv";
                a.click();
                URL.revokeObjectURL(url);
              }}
            >
              Export All Results (CSV)
            </Button>
          </CardContent>
        </Card>
      )}
      {/* Advanced Analytics Section */}
      {result && (
        <Card sx={{ mb: 4 }}>
          <CardHeader
            title="Advanced Risk Analytics"
            subheader="Institutional-grade performance and risk metrics"
            action={
              <Button
                variant="outlined"
                startIcon={<Download />}
                onClick={handleExport}
                size="small"
              >
                Export
              </Button>
            }
          />
          <CardContent>
            <Accordion>
              <AccordionSummary expandIcon={<ExpandMore />}>
                <Typography variant="h6">Risk-Adjusted Returns</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Grid container spacing={3}>
                  <Grid item xs={12} md={4}>
                    <Paper sx={{ p: 2, textAlign: "center" }}>
                      <Typography variant="h5" color="primary">
                        {getAdvancedMetrics(result).sortinoRatio?.toFixed(3) ??
                          "--"}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Sortino Ratio
                      </Typography>
                      <Typography variant="caption" display="block">
                        Downside risk-adjusted return
                      </Typography>
                    </Paper>
                  </Grid>
                  <Grid item xs={12} md={4}>
                    <Paper sx={{ p: 2, textAlign: "center" }}>
                      <Typography variant="h5" color="secondary">
                        {getAdvancedMetrics(result).calmarRatio?.toFixed(3) ??
                          "--"}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Calmar Ratio
                      </Typography>
                      <Typography variant="caption" display="block">
                        Return vs maximum drawdown
                      </Typography>
                    </Paper>
                  </Grid>
                  <Grid item xs={12} md={4}>
                    <Paper sx={{ p: 2, textAlign: "center" }}>
                      <Typography variant="h5" color="info.main">
                        {getAdvancedMetrics(result).informationRatio?.toFixed(
                          3
                        ) ?? "--"}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Information Ratio
                      </Typography>
                      <Typography variant="caption" display="block">
                        Active return vs tracking error
                      </Typography>
                    </Paper>
                  </Grid>
                </Grid>
              </AccordionDetails>
            </Accordion>

            <Accordion>
              <AccordionSummary expandIcon={<ExpandMore />}>
                <Typography variant="h6">Trade Analytics</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Grid container spacing={3}>
                  <Grid item xs={12} md={6}>
                    <Paper sx={{ p: 2 }}>
                      <Typography variant="h6" gutterBottom>
                        Trade Distribution
                      </Typography>
                      <Box display="flex" justifyContent="between" mb={1}>
                        <Typography variant="body2">Average Win</Typography>
                        <Typography variant="body2" color="success.main">
                          $
                          {getAdvancedMetrics(result).avgWin?.toFixed(2) ??
                            "--"}
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="between" mb={1}>
                        <Typography variant="body2">Average Loss</Typography>
                        <Typography variant="body2" color="error.main">
                          $
                          {getAdvancedMetrics(result).avgLoss?.toFixed(2) ??
                            "--"}
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="between" mb={1}>
                        <Typography variant="body2">Expectancy</Typography>
                        <Typography
                          variant="body2"
                          color={
                            getAdvancedMetrics(result).expectancy >= 0
                              ? "success.main"
                              : "error.main"
                          }
                        >
                          $
                          {getAdvancedMetrics(result).expectancy?.toFixed(2) ??
                            "--"}
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">
                          Avg Trade Duration
                        </Typography>
                        <Typography variant="body2">
                          {getAdvancedMetrics(result).avgTradeDuration?.toFixed(
                            1
                          ) ?? "--"}{" "}
                          days
                        </Typography>
                      </Box>
                    </Paper>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Paper sx={{ p: 2 }}>
                      <Typography variant="h6" gutterBottom>
                        Profit Analysis
                      </Typography>
                      <Box display="flex" justifyContent="between" mb={1}>
                        <Typography variant="body2">Gross Profit</Typography>
                        <Typography variant="body2" color="success.main">
                          $
                          {getAdvancedMetrics(result).grossProfit?.toFixed(2) ??
                            "--"}
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="between" mb={1}>
                        <Typography variant="body2">Gross Loss</Typography>
                        <Typography variant="body2" color="error.main">
                          $
                          {getAdvancedMetrics(result).grossLoss?.toFixed(2) ??
                            "--"}
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Profit Factor</Typography>
                        <Typography
                          variant="body2"
                          color={
                            getAdvancedMetrics(result).profitFactor >= 1
                              ? "success.main"
                              : "error.main"
                          }
                        >
                          {getAdvancedMetrics(result).profitFactor?.toFixed(
                            2
                          ) ?? "--"}
                        </Typography>
                      </Box>
                    </Paper>
                  </Grid>
                </Grid>
              </AccordionDetails>
            </Accordion>
          </CardContent>
        </Card>
      )}
      <Card sx={{ mt: 4 }}>
        <CardHeader
          title="Strategy Library"
          subheader="Manage and version your trading strategies"
          action={
            <Badge badgeContent={savedStrategies.length} color="primary">
              <Button variant="outlined" startIcon={<Save />} size="small">
                Strategies
              </Button>
            </Badge>
          }
        />
        <CardContent>
          <TableContainer component={Paper} sx={{ mb: 2 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell>Actions</TableCell>
                  <TableCell>History</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {savedStrategies.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell>{s.name}</TableCell>
                    <TableCell>
                      <Button
                        size="small"
                        onClick={() => handleLoadStrategy(s.code)}
                      >
                        Load
                      </Button>
                      <Button
                        size="small"
                        onClick={() => handleRenameStrategy(s.id)}
                      >
                        Rename
                      </Button>
                      <Button
                        size="small"
                        onClick={() => {
                          setPythonCode(s.code);
                          setUseCustomCode(true);
                        }}
                      >
                        Clone
                      </Button>
                      <Button
                        size="small"
                        color="error"
                        onClick={() => handleDeleteStrategy(s.id)}
                      >
                        Delete
                      </Button>
                    </TableCell>
                    <TableCell>
                      <Button
                        size="small"
                        onClick={() =>
                          alert(
                            JSON.stringify(strategyHistory[s.id] || [], null, 2)
                          )
                        }
                      >
                        Show Versions
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>
      <Card sx={{ mb: 4 }}>
        <CardHeader
          title="Parameter Optimization"
          subheader="Grid search and parameter sweep functionality"
          action={
            <Box display="flex" alignItems="center" gap={1}>
              <Chip
                label={`${sweepResults.length} results`}
                color="primary"
                size="small"
                variant="outlined"
              />
              <Tooltip
                title="Run a grid search over parameter values. Use comma-separated lists (e.g. 10,20,30) or range (e.g. 10-30:5 for 10,15,20,25,30)."
                arrow
              >
                <IconButton size="small">
                  <HelpOutline />
                </IconButton>
              </Tooltip>
            </Box>
          }
        />
        <CardContent>
          <Grid container spacing={2}>
            {paramConfig.map((param) => (
              <Grid item key={param.name} xs={12} sm={4} md={3}>
                <Tooltip title={param.label} arrow>
                  <TextField
                    label={param.label}
                    value={sweepParams[param.name] ?? ""}
                    onChange={(e) =>
                      handleSweepParamChange(param.name, e.target.value)
                    }
                    size="small"
                    fullWidth
                    placeholder={String(param.default)}
                    helperText="List: 10,20,30 or Range: 10-30:5"
                  />
                </Tooltip>
              </Grid>
            ))}
          </Grid>
          <Box mt={2} display="flex" alignItems="center" gap={2}>
            <Button
              variant="contained"
              color="primary"
              onClick={handleRunSweep}
              disabled={sweepRunning || !paramConfig.length}
            >
              Run Sweep
            </Button>
            <Button
              variant="outlined"
              color="error"
              onClick={handleStopSweep}
              disabled={!sweepRunning}
            >
              Stop
            </Button>
            {sweepRunning && (
              <Typography variant="body2">
                Progress: {sweepProgress.current} / {sweepProgress.total}
              </Typography>
            )}
          </Box>
          {sweepResults.length > 0 && (
            <Box mt={3}>
              <Typography variant="subtitle2">Sweep Results</Typography>
              <TableContainer component={Paper} sx={{ mb: 2 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      {paramConfig.map((p) => (
                        <TableCell key={p.name}>{p.label}</TableCell>
                      ))}
                      <TableCell>Total Return</TableCell>
                      <TableCell>Sharpe</TableCell>
                      <TableCell>Max Drawdown</TableCell>
                      <TableCell>Success</TableCell>
                      <TableCell>Error</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {sweepResults.map((r, i) => (
                      <TableRow
                        key={i}
                        sx={{ bgcolor: r.success ? undefined : "#ffebee" }}
                      >
                        {paramConfig.map((p) => (
                          <TableCell key={p.name}>{r.params[p.name]}</TableCell>
                        ))}
                        <TableCell>
                          {r.metrics?.totalReturn?.toFixed(2) ?? "--"}
                        </TableCell>
                        <TableCell>
                          {r.metrics?.sharpeRatio?.toFixed(2) ?? "--"}
                        </TableCell>
                        <TableCell>
                          {r.metrics?.maxDrawdown?.toFixed(2) ?? "--"}
                        </TableCell>
                        <TableCell>{r.success ? "Yes" : "No"}</TableCell>
                        <TableCell
                          sx={{
                            maxWidth: 120,
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {r.error || ""}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              <Button
                variant="outlined"
                startIcon={<FileDownloadIcon />}
                onClick={() => {
                  const csv = [
                    [
                      ...paramConfig.map((p) => p.label),
                      "Total Return",
                      "Sharpe",
                      "Max Drawdown",
                      "Success",
                      "Error",
                    ].join(","),
                    ...sweepResults.map((r) =>
                      [
                        ...paramConfig.map((p) => r.params[p.name]),
                        r.metrics?.totalReturn ?? "",
                        r.metrics?.sharpeRatio ?? "",
                        r.metrics?.maxDrawdown ?? "",
                        r.success ? "Yes" : "No",
                        r.error ? '"' + r.error.replace(/"/g, '""') + '"' : "",
                      ].join(",")
                    ),
                  ].join("\n");
                  const blob = new Blob([csv], { type: "text/csv" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `sweep_results_${params.symbol}_${params.strategy}.csv`;
                  a.click();
                  URL.revokeObjectURL(url);
                }}
              >
                Export Sweep Results (CSV)
              </Button>
            </Box>
          )}
        </CardContent>
      </Card>

      {/* Enhanced Strategy Management Dialog */}
      <Dialog
        open={strategyDialogOpen}
        onClose={() => setStrategyDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          <Box
            display="flex"
            alignItems="center"
            justifyContent="space-between"
          >
            <Typography variant="h6">Strategy Management</Typography>
            <Box display="flex" gap={1}>
              <Chip
                label={isAuthenticated ? "Cloud Storage" : "Local Storage"}
                color={isAuthenticated ? "success" : "warning"}
                size="small"
              />
              <Badge badgeContent={savedStrategies.length} color="primary">
                <Assessment />
              </Badge>
            </Box>
          </Box>
        </DialogTitle>
        <DialogContent>
          {/* Strategy Filter */}
          <Box sx={{ mb: 2 }}>
            <FormControl size="small" sx={{ minWidth: 120, mr: 2 }}>
              <InputLabel>Filter</InputLabel>
              <Select
                value={strategyFilter}
                onChange={(e) => setStrategyFilter(e.target.value)}
                label="Filter"
              >
                <MenuItem value="all">All Strategies</MenuItem>
                <MenuItem value="mine">My Strategies</MenuItem>
                {isAuthenticated && (
                  <MenuItem value="public">Public Strategies</MenuItem>
                )}
              </Select>
            </FormControl>
          </Box>

          {/* Save New Strategy Form */}
          {newStrategy.name !== undefined && (
            <Card sx={{ mb: 2, bgcolor: "grey.50" }}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Save New Strategy
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth
                      label="Strategy Name"
                      value={newStrategy.name}
                      onChange={(e) =>
                        setNewStrategy({ ...newStrategy, name: e.target.value })
                      }
                      placeholder="e.g., My RSI Strategy"
                    />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={newStrategy.isPublic}
                          onChange={(e) =>
                            setNewStrategy({
                              ...newStrategy,
                              isPublic: e.target.checked,
                            })
                          }
                          disabled={!isAuthenticated}
                        />
                      }
                      label="Make Public"
                    />
                  </Grid>
                  <Grid item xs={12}>
                    <TextField
                      fullWidth
                      label="Description (Optional)"
                      value={newStrategy.description}
                      onChange={(e) =>
                        setNewStrategy({
                          ...newStrategy,
                          description: e.target.value,
                        })
                      }
                      multiline
                      rows={2}
                      placeholder="Describe your strategy..."
                    />
                  </Grid>
                  <Grid item xs={12}>
                    <Box display="flex" gap={1}>
                      <Button variant="contained" onClick={handleSaveStrategy}>
                        Save Strategy
                      </Button>
                      <Button
                        variant="outlined"
                        onClick={() =>
                          setNewStrategy({
                            name: "",
                            description: "",
                            code: "",
                            isPublic: false,
                          })
                        }
                      >
                        Cancel
                      </Button>
                    </Box>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          )}

          {/* Saved Strategies List */}
          <TableContainer component={Paper}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell>Author</TableCell>
                  <TableCell>Created</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {savedStrategies
                  .filter((strategy) => {
                    if (strategyFilter === "mine")
                      return strategy.userId === user?.id || !strategy.userId;
                    if (strategyFilter === "public") return strategy.isPublic;
                    return true;
                  })
                  .map((strategy) => (
                    <TableRow key={strategy.id}>
                      <TableCell>
                        <Box>
                          <Typography variant="body2" fontWeight="bold">
                            {strategy.name}
                          </Typography>
                          {strategy.description && (
                            <Typography
                              variant="caption"
                              color="text.secondary"
                            >
                              {strategy.description}
                            </Typography>
                          )}
                        </Box>
                      </TableCell>
                      <TableCell>
                        <Box display="flex" alignItems="center" gap={1}>
                          <Person fontSize="small" />
                          <Typography variant="body2">
                            {strategy.author || "Anonymous"}
                          </Typography>
                          {strategy.isPublic && (
                            <Chip label="Public" size="small" color="info" />
                          )}
                        </Box>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">
                          {strategy.createdAt
                            ? new Date(strategy.createdAt).toLocaleDateString()
                            : "Unknown"}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Box display="flex" gap={1}>
                          <Tooltip title="Load Strategy">
                            <IconButton
                              size="small"
                              onClick={() => {
                                handleLoadStrategy(strategy);
                                setStrategyDialogOpen(false);
                              }}
                            >
                              <PlayArrow />
                            </IconButton>
                          </Tooltip>
                          {(strategy.userId === user?.id ||
                            !isAuthenticated) && (
                            <>
                              <Tooltip title="Edit Strategy">
                                <IconButton size="small">
                                  <Edit />
                                </IconButton>
                              </Tooltip>
                              <Tooltip title="Delete Strategy">
                                <IconButton
                                  size="small"
                                  color="error"
                                  onClick={() =>
                                    handleDeleteStrategy(strategy.id)
                                  }
                                >
                                  <Delete />
                                </IconButton>
                              </Tooltip>
                            </>
                          )}
                          <Tooltip title="Share Strategy">
                            <IconButton size="small">
                              <Share />
                            </IconButton>
                          </Tooltip>
                        </Box>
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </TableContainer>

          {!isAuthenticated && (
            <Alert severity="info" sx={{ mt: 2 }}>
              <Typography variant="body2">
                Sign in to save strategies to the cloud and access advanced
                features like sharing and collaboration.
              </Typography>
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setStrategyDialogOpen(false)}>Close</Button>
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={() =>
              setNewStrategy({
                name: "",
                description: "",
                code: "",
                isPublic: false,
              })
            }
          >
            New Strategy
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
}
