import React, { useState, useEffect, Suspense } from "react";
import { Routes, Route, useNavigate, useLocation, Navigate } from "react-router-dom";
import {
  Toolbar,
  Typography,
  useTheme,
  useMediaQuery,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
} from "@mui/material";
import {
  ExpandLess,
  ExpandMore,
  TrendingUp as TrendingUpIcon,
  Business as BusinessIcon,
  SwapHoriz as SwapHorizIcon,
} from "@mui/icons-material";

// Dashboard pages - Lazy-loaded for code splitting
const MarketsHealth = React.lazy(() => import("./pages/MarketsHealth"));
const StockDetail = React.lazy(() => import("./pages/StockDetail"));
const DeepValueStocks = React.lazy(() => import("./pages/DeepValueStocks"));
const TradingSignals = React.lazy(() => import("./pages/TradingSignals"));
const SwingCandidates = React.lazy(() => import("./pages/SwingCandidates"));
const BacktestResults = React.lazy(() => import("./pages/BacktestResults"));
const EconomicDashboard = React.lazy(() => import("./pages/EconomicDashboard"));
const SectorAnalysis = React.lazy(() => import("./pages/SectorAnalysis"));
const Sentiment = React.lazy(() => import("./pages/Sentiment"));
const ScoresDashboard = React.lazy(() => import("./pages/ScoresDashboard"));
const TradeTracker = React.lazy(() => import("./pages/TradeTracker"));
const PortfolioDashboard = React.lazy(() => import("./pages/PortfolioDashboard"));
const PerformanceMetrics = React.lazy(() => import("./pages/PerformanceMetrics"));
const ServiceHealth = React.lazy(() => import("./pages/ServiceHealth"));
const Settings = React.lazy(() => import("./pages/Settings"));
const AlgoTradingDashboard = React.lazy(() => import("./pages/AlgoTradingDashboard"));
const AuditViewer = React.lazy(() => import("./pages/AuditViewer"));
const PreTradeSimulator = React.lazy(() => import("./pages/PreTradeSimulator"));
const NotificationCenter = React.lazy(() => import("./pages/NotificationCenter"));
const NotFound = React.lazy(() => import("./pages/NotFound"));

import { useAuth } from "./contexts/AuthContext";
import ProtectedRoute from "./components/auth/ProtectedRoute";
import AuthModal from "./components/auth/AuthModal";
import ErrorBoundary from "./components/ErrorBoundary";
import APIHealthCheck from "./components/APIHealthCheck";

// Marketing pages - Only keep main pages and their dropdown pages
const Home = React.lazy(() => import("./pages/marketing/Home"));
const Firm = React.lazy(() => import("./pages/marketing/Firm"));
const Contact = React.lazy(() => import("./pages/marketing/Contact"));
const About = React.lazy(() => import("./pages/marketing/About"));
const OurTeam = React.lazy(() => import("./pages/marketing/OurTeam"));
const MissionValues = React.lazy(() => import("./pages/marketing/MissionValues"));
const ResearchInsights = React.lazy(() => import("./pages/marketing/ResearchInsights"));
const ArticleDetail = React.lazy(() => import("./pages/marketing/ArticleDetail"));
const Terms = React.lazy(() => import("./pages/marketing/Terms"));
const Privacy = React.lazy(() => import("./pages/marketing/Privacy"));
const InvestmentTools = React.lazy(() => import("./pages/marketing/InvestmentTools"));
const WealthManagement = React.lazy(() => import("./pages/marketing/WealthManagement"));
const LoginPage = React.lazy(() => import("./pages/LoginPage"));

// Layout components
import AppLayout from "./components/AppLayout";

const _drawerWidth = 240;

const menuItems = [
  // Markets Section
  {
    text: "Market Overview",
    icon: <TrendingUpIcon />,
    path: "/app/markets",
    category: "markets",
  },
  {
    text: "Sectors",
    icon: <BusinessIcon />,
    path: "/app/sectors",
    category: "markets",
  },
  {
    text: "Economic Data",
    icon: <TrendingUpIcon />,
    path: "/app/economic",
    category: "markets",
  },
  {
    text: "Sentiment",
    icon: <TrendingUpIcon />,
    path: "/app/sentiment",
    category: "markets",
  },

  // Trading Signals Section
  {
    text: "Trading Signals",
    icon: <TrendingUpIcon />,
    path: "/app/trading-signals",
    category: "signals",
  },

  // Portfolio Section
  {
    text: "Portfolio",
    icon: <SwapHorizIcon />,
    path: "/app/portfolio",
    category: "portfolio",
  },
  {
    text: "Trade History",
    icon: <SwapHorizIcon />,
    path: "/app/trades",
    category: "portfolio",
  },
  {
    text: "Performance",
    icon: <TrendingUpIcon />,
    path: "/app/performance",
    category: "portfolio",
  },
  {
    text: "Pre-Trade Simulator",
    icon: <TrendingUpIcon />,
    path: "/app/pre-trade-simulator",
    category: "portfolio",
    adminOnly: true,
  },

  // Analysis Section
  {
    text: "Backtest",
    icon: <TrendingUpIcon />,
    path: "/app/backtests",
    category: "analysis",
  },
  {
    text: "Scores",
    icon: <TrendingUpIcon />,
    path: "/app/scores",
    category: "analysis",
  },

  // Algo Trading Section
  {
    text: "Algo Trading",
    icon: <TrendingUpIcon />,
    path: "/app/algo-dashboard",
    category: "algo",
    requireAuth: true,
  },

  // Admin Section
  {
    text: "System Health",
    icon: <TrendingUpIcon />,
    path: "/app/health",
    category: "admin",
    adminOnly: true,
  },
  {
    text: "Audit Log",
    icon: <TrendingUpIcon />,
    path: "/app/audit",
    category: "admin",
    adminOnly: true,
  },

];

function App() {

  // All hooks must be at the top level - not inside try-catch
  const [mobileOpen, setMobileOpen] = useState(false);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [_userMenuAnchor, _setUserMenuAnchor] = useState(null);
  const [expandedSections, setExpandedSections] = useState({
    markets: true,
    signals: true,
    portfolio: true,
    analysis: true,
    algo: true,
    admin: true,
  });


  const theme = useTheme();

  const isMobile = useMediaQuery(theme.breakpoints.down("md"));


  // Safe auth context access - useAuth now has built-in fallback safety
  const { isAuthenticated, user: _user, logout: _logout } = useAuth();

  const navigate = useNavigate();

  const location = useLocation();

  // Auto-close auth modal when user successfully authenticates
  useEffect(() => {
    if (isAuthenticated && authModalOpen) {
      setAuthModalOpen(false);
    }
  }, [isAuthenticated, authModalOpen]);

  // Premium status functionality removed - all features available

  const _handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen);
  };

  const _handleUserMenuOpen = (_event) => {
    _setUserMenuAnchor(_event.currentTarget);
  };

  const _handleUserMenuClose = () => {
    _setUserMenuAnchor(null);
  };

  const _handleLogout = async () => {
    _handleUserMenuClose();
    await _logout();
  };

  const handleNavigation = (path) => {
    navigate(path);
    if (isMobile) {
      setMobileOpen(false);
    }
  };

  const handleSectionToggle = (section) => {
    setExpandedSections((prev) => ({
      ...prev,
      [section]: !prev[section],
    }));
  };

  const groupedMenuItems = menuItems
    .reduce((acc, item) => {
      if (!acc[item.category]) {
        acc[item.category] = [];
      }
      acc[item.category].push(item);
      return acc;
    }, {});

  const sectionTitles = {
    main: "Dashboard",
    markets: "Markets",
    signals: "Trading Signals",
    portfolio: "Portfolio",
    analysis: "Analysis",
    algo: "Trading",
    admin: "Admin",
  };

  const _drawer = (
    <div>
      <Toolbar>
        <Typography
          variant="h6"
          noWrap
          component="div"
          sx={{ fontWeight: 700, color: "primary.main" }}
        >
          Bullseye Financial
        </Typography>
      </Toolbar>
      <List sx={{ px: 1 }}>
        {Object.entries(groupedMenuItems).map(([category, items]) => (
          <React.Fragment key={category}>
            {category === "main" ? (
              // Dashboard gets special treatment - no section header
              (items || []).map((item) => (
                <ListItem key={item.text} disablePadding sx={{ mb: 1 }}>
                  <ListItemButton
                    selected={location.pathname === item.path}
                    onClick={() => handleNavigation(item.path, item.premium)}
                    sx={{
                      borderRadius: 1,
                      "&.Mui-selected": {
                        backgroundColor: theme.palette.primary.main + "20",
                        "& .MuiListItemIcon-root": {
                          color: theme.palette.primary.main,
                        },
                        "& .MuiListItemText-primary": {
                          color: theme.palette.primary.main,
                          fontWeight: 600,
                        },
                      },
                    }}
                  >
                    <ListItemIcon>{item.icon}</ListItemIcon>
                    <ListItemText primary={item.text} />
                  </ListItemButton>
                </ListItem>
              ))
            ) : (
              <>
                {/* Section Header */}
                <ListItem disablePadding>
                  <ListItemButton
                    onClick={() => handleSectionToggle(category)}
                    aria-label={`${expandedSections[category] ? "Collapse" : "Expand"} ${sectionTitles[category]} section`}
                    sx={{
                      py: 0.5,
                      "&:hover": { backgroundColor: "transparent" },
                    }}
                  >
                    <ListItemText
                      primary={sectionTitles[category]}
                      primaryTypographyProps={{
                        variant: "subtitle2",
                        fontWeight: 600,
                        color: "text.secondary",
                        textTransform: "uppercase",
                        letterSpacing: 0.5,
                      }}
                    />
                    {expandedSections[category] ? (
                      <ExpandLess />
                    ) : (
                      <ExpandMore />
                    )}
                  </ListItemButton>
                </ListItem>

                {/* Section Items */}
                {expandedSections[category] &&
                  (items || []).map((item) => (
                    <ListItem key={item.text} disablePadding sx={{ pl: 2 }}>
                      <ListItemButton
                        selected={location.pathname === item.path}
                        onClick={() =>
                          handleNavigation(item.path, item.premium)
                        }
                        disabled={false}
                        sx={{
                          borderRadius: 1,
                          py: 0.5,
                          "&.Mui-selected": {
                            backgroundColor: theme.palette.primary.main + "20",
                            "& .MuiListItemIcon-root": {
                              color: theme.palette.primary.main,
                            },
                            "& .MuiListItemText-primary": {
                              color: theme.palette.primary.main,
                              fontWeight: 600,
                            },
                          },
                          "&.Mui-disabled": {
                            opacity: 0.6,
                          },
                        }}
                      >
                        <ListItemIcon sx={{ minWidth: 36 }}>
                          {item.icon}
                        </ListItemIcon>
                        <ListItemText
                          primary={item.text}
                          primaryTypographyProps={{
                            variant: "body2",
                          }}
                        />
                      </ListItemButton>
                    </ListItem>
                  ))}
              </>
            )}
          </React.Fragment>
        ))}
      </List>
    </div>
  );


  // Determine if this is a marketing page or app page
  const isMarketingPage = !location.pathname.startsWith('/app');

  if (isMarketingPage) {
    // Marketing pages layout
    return (
      <Routes>
        {/* Main Marketing Pages */}
        <Route path="/" element={<ErrorBoundary><Home /></ErrorBoundary>} />
        <Route path="/firm" element={<ErrorBoundary><Firm /></ErrorBoundary>} />
        <Route path="/contact" element={<ErrorBoundary><Contact /></ErrorBoundary>} />

        {/* Firm Dropdown Pages */}
        <Route path="/about" element={<ErrorBoundary><About /></ErrorBoundary>} />
        <Route path="/our-team" element={<ErrorBoundary><OurTeam /></ErrorBoundary>} />
        <Route path="/mission-values" element={<ErrorBoundary><MissionValues /></ErrorBoundary>} />

        {/* Services Dropdown Pages */}
        <Route path="/research-insights" element={<ErrorBoundary><ResearchInsights /></ErrorBoundary>} />
        <Route path="/articles/:articleId" element={<ErrorBoundary><ArticleDetail /></ErrorBoundary>} />
        <Route path="/investment-tools" element={<ErrorBoundary><InvestmentTools /></ErrorBoundary>} />
        <Route path="/wealth-management" element={<ErrorBoundary><WealthManagement /></ErrorBoundary>} />

        {/* Legal Pages */}
        <Route path="/terms" element={<ErrorBoundary><Terms /></ErrorBoundary>} />
        <Route path="/privacy" element={<ErrorBoundary><Privacy /></ErrorBoundary>} />

        {/* Authentication */}
        <Route path="/login" element={<ErrorBoundary><LoginPage /></ErrorBoundary>} />

        {/* Public Dashboard Routes - Redirect to /app/ versions */}
        <Route path="/stocks" element={<Navigate to="/app/deep-value" replace />} />
        <Route path="/dashboard" element={<Navigate to="/app/markets" replace />} />
        <Route path="/markets-health" element={<Navigate to="/app/markets" replace />} />
        <Route path="/economic" element={<Navigate to="/app/economic" replace />} />
        <Route path="/signals" element={<Navigate to="/app/trading-signals" replace />} />
        <Route path="/swing-candidates" element={<Navigate to="/app/swing" replace />} />
        <Route path="/sectors" element={<Navigate to="/app/sectors" replace />} />
        <Route path="/sentiment" element={<Navigate to="/app/sentiment" replace />} />
        <Route path="/scores" element={<Navigate to="/app/scores" replace />} />
        <Route path="/portfolio" element={<Navigate to="/app/portfolio" replace />} />
        <Route path="/trades" element={<Navigate to="/app/trades" replace />} />
        <Route path="/health" element={<Navigate to="/app/health" replace />} />

        {/* Fallback - page not found */}
        <Route path="*" element={<ErrorBoundary><NotFound /></ErrorBoundary>} />
      </Routes>
    );
  }

  // App pages layout (with drawer navigation)
  return (
    <ErrorBoundary>
      <APIHealthCheck>
        <AppLayout>
      <Suspense fallback={<div style={{ padding: '20px', textAlign: 'center' }}>Loading...</div>}>
        <Routes>
        {/* Markets & Analysis */}
        <Route path="/app/markets" element={<ErrorBoundary><MarketsHealth /></ErrorBoundary>} />
        <Route path="/app/economic" element={<ErrorBoundary><EconomicDashboard /></ErrorBoundary>} />
        <Route path="/app/sectors" element={<ErrorBoundary><SectorAnalysis /></ErrorBoundary>} />
        <Route path="/app/sentiment" element={<ErrorBoundary><Sentiment /></ErrorBoundary>} />

        {/* Stocks Analysis & Signals */}
        <Route path="/app/deep-value" element={<ErrorBoundary><DeepValueStocks /></ErrorBoundary>} />
        <Route path="/app/trading-signals" element={<ErrorBoundary><TradingSignals /></ErrorBoundary>} />
        <Route path="/app/swing" element={<ErrorBoundary><SwingCandidates /></ErrorBoundary>} />
        <Route path="/app/scores" element={<ErrorBoundary><ScoresDashboard /></ErrorBoundary>} />
        <Route path="/app/stock/:symbol" element={<ErrorBoundary><StockDetail /></ErrorBoundary>} />

        {/* Portfolio & Trading */}
        <Route path="/app/portfolio" element={<ErrorBoundary><ProtectedRoute requireAuth><PortfolioDashboard /></ProtectedRoute></ErrorBoundary>} />
        <Route path="/app/trades" element={<ErrorBoundary><ProtectedRoute requireAuth><TradeTracker /></ProtectedRoute></ErrorBoundary>} />
        <Route path="/app/performance" element={<ErrorBoundary><ProtectedRoute requireAuth><PerformanceMetrics /></ProtectedRoute></ErrorBoundary>} />

        {/* Research & Testing */}
        <Route path="/app/backtests" element={<ErrorBoundary><BacktestResults /></ErrorBoundary>} />

        {/* Algo */}
        <Route path="/app/algo-dashboard" element={<ErrorBoundary><ProtectedRoute requireAuth><AlgoTradingDashboard /></ProtectedRoute></ErrorBoundary>} />

        {/* Admin & Settings */}
        <Route path="/app/health" element={<ErrorBoundary><ProtectedRoute requireAuth requireRole="admin"><ServiceHealth /></ProtectedRoute></ErrorBoundary>} />
        <Route path="/app/notifications" element={<ErrorBoundary><ProtectedRoute requireAuth requireRole="admin"><NotificationCenter /></ProtectedRoute></ErrorBoundary>} />
        <Route path="/app/audit" element={<ErrorBoundary><ProtectedRoute requireAuth requireRole="admin"><AuditViewer /></ProtectedRoute></ErrorBoundary>} />
        <Route path="/app/pre-trade-simulator" element={<ErrorBoundary><ProtectedRoute requireAuth requireRole="admin"><PreTradeSimulator /></ProtectedRoute></ErrorBoundary>} />
        <Route path="/app/settings" element={<ErrorBoundary><ProtectedRoute requireAuth><Settings /></ProtectedRoute></ErrorBoundary>} />
      </Routes>
      </Suspense>

      {/* Authentication Modal */}
      <AuthModal open={authModalOpen} onClose={() => setAuthModalOpen(false)} />
    </AppLayout>
      </APIHealthCheck>
    </ErrorBoundary>
  );
}

export default App;

