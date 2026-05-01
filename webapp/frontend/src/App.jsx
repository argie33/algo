import React, { useState, useEffect } from "react";
import { Routes, Route, useNavigate, useLocation } from "react-router-dom";
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
  Stars,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  Business as BusinessIcon,
  Public as PublicIcon,
  Event as EventIcon,
  Psychology as PsychologyIcon,
  SwapHoriz as SwapHorizIcon,
  Storage as StorageIcon,
  Grain as GrainIcon,
} from "@mui/icons-material";

// Dashboard pages - ALL 18 pages
import MarketOverview from "./pages/MarketOverview";
import FinancialData from "./pages/FinancialData";
import DeepValueStocks from "./pages/DeepValueStocks";
import TradingSignals from "./pages/TradingSignals";
import BacktestResults from "./pages/BacktestResults";
import EconomicDashboard from "./pages/EconomicDashboard";
import EarningsCalendar from "./pages/EarningsCalendar";
import SectorAnalysis from "./pages/SectorAnalysis";
import Sentiment from "./pages/Sentiment";
import CommoditiesAnalysis from "./pages/CommoditiesAnalysis";
import ScoresDashboard from "./pages/ScoresDashboard";
import MetricsDashboard from "./pages/MetricsDashboard";
import TradeHistory from "./pages/TradeHistory";
import PortfolioDashboard from "./pages/PortfolioDashboard";
import HedgeHelper from "./pages/HedgeHelper";
import PortfolioOptimizerNew from "./pages/PortfolioOptimizerNew";
import ETFSignals from "./pages/ETFSignals";
import ServiceHealth from "./pages/ServiceHealth";
import Settings from "./pages/Settings";

import { useAuth } from "./contexts/AuthContext";
import AuthModal from "./components/auth/AuthModal";
import ErrorBoundary from "./components/ErrorBoundary";

// Marketing pages - Only keep main pages and their dropdown pages
import Home from "./pages/marketing/Home";
import Firm from "./pages/marketing/Firm";
import Contact from "./pages/marketing/Contact";
import About from "./pages/marketing/About";
import OurTeam from "./pages/marketing/OurTeam";
import MissionValues from "./pages/marketing/MissionValues";
import ResearchInsights from "./pages/marketing/ResearchInsights";
import ArticleDetail from "./pages/marketing/ArticleDetail";
import Terms from "./pages/marketing/Terms";
import Privacy from "./pages/marketing/Privacy";
import InvestmentTools from "./pages/marketing/InvestmentTools";
import WealthManagement from "./pages/marketing/WealthManagement";

// Layout components
import AppLayout from "./components/AppLayout";

const drawerWidth = 240;

const menuItems = [
  // Markets Section
  {
    text: "Market Overview",
    icon: <TrendingUpIcon />,
    path: "/app/market",
    category: "markets",
  },
  {
    text: "Sectors",
    icon: <BusinessIcon />,
    path: "/app/sectors",
    category: "markets",
  },
  {
    text: "Commodities",
    icon: <GrainIcon />,
    path: "/app/commodities",
    category: "markets",
  },

  // Trading Signals Section
  {
    text: "Trading Signals",
    icon: <TrendingUpIcon />,
    path: "/app/trading-signals",
    category: "signals",
  },
  {
    text: "Earnings Calendar",
    icon: <EventIcon />,
    path: "/app/earnings",
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

  // Analysis Section
  {
    text: "Financials",
    icon: <StorageIcon />,
    path: "/app/financial-data",
    category: "analysis",
  },
  {
    text: "Backtest",
    icon: <TrendingUpIcon />,
    path: "/app/backtests",
    category: "analysis",
  },

];

function App() {
  console.log("🎯 APP COMPONENT: Starting App component render...");

  // All hooks must be at the top level - not inside try-catch
  const [mobileOpen, setMobileOpen] = useState(false);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [userMenuAnchor, setUserMenuAnchor] = useState(null);
  const [expandedSections, setExpandedSections] = useState({
    markets: true,
    stocks: true,
    portfolio: true,
    research: true,
    admin: true,
  });

  console.log("🎯 APP COMPONENT: State initialized");

  const theme = useTheme();
  console.log("🎯 APP COMPONENT: Theme loaded:", theme ? "✅" : "❌");

  const isMobile = useMediaQuery(theme.breakpoints.down("md"));
  console.log("🎯 APP COMPONENT: isMobile:", isMobile);

  console.log("🎯 APP COMPONENT: About to call useAuth...");

  // Safe auth context access - useAuth now has built-in fallback safety
  const { isAuthenticated, user, logout } = useAuth();
  console.log(
    "🎯 APP COMPONENT: Auth state loaded - isAuthenticated:",
    isAuthenticated,
    "user:",
    user
  );

  const navigate = useNavigate();
  console.log("🎯 APP COMPONENT: Navigate loaded");

  const location = useLocation();
  console.log("🎯 APP COMPONENT: Location loaded:", location?.pathname);

  // Auto-close auth modal when user successfully authenticates
  useEffect(() => {
    if (isAuthenticated && authModalOpen) {
      setAuthModalOpen(false);
    }
  }, [isAuthenticated, authModalOpen]);

  // Premium status functionality removed - all features available

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen);
  };

  const handleUserMenuOpen = (event) => {
    setUserMenuAnchor(event.currentTarget);
  };

  const handleUserMenuClose = () => {
    setUserMenuAnchor(null);
  };

  const handleLogout = async () => {
    handleUserMenuClose();
    await logout();
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
  };

  const drawer = (
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

  console.log("🎯 APP COMPONENT: About to render JSX...");

  // Determine if this is a marketing page or app page
  const isMarketingPage = !location.pathname.startsWith('/app');

  if (isMarketingPage) {
    // Marketing pages layout
    return (
      <ErrorBoundary>
        <Routes>
          {/* Main Marketing Pages */}
          <Route path="/" element={<Home />} />
          <Route path="/firm" element={<Firm />} />
          <Route path="/contact" element={<Contact />} />

          {/* Firm Dropdown Pages */}
          <Route path="/about" element={<About />} />
          <Route path="/our-team" element={<OurTeam />} />
          <Route path="/mission-values" element={<MissionValues />} />

          {/* Services Dropdown Pages */}
          <Route path="/research-insights" element={<ResearchInsights />} />
          <Route path="/articles/:articleId" element={<ArticleDetail />} />
          <Route path="/investment-tools" element={<InvestmentTools />} />
          <Route path="/wealth-management" element={<WealthManagement />} />

          {/* Legal Pages */}
          <Route path="/terms" element={<Terms />} />
          <Route path="/privacy" element={<Privacy />} />

          {/* Fallback for marketing - if route doesn't exist, redirect to home */}
          <Route path="*" element={<Home />} />
        </Routes>
      </ErrorBoundary>
    );
  }

  // App pages layout (with drawer navigation)
  return (
    <ErrorBoundary>
      <AppLayout>
        <Routes>
          {/* Markets & Analysis */}
          <Route path="/app/market" element={<MarketOverview />} />
          <Route path="/app/economic" element={<EconomicDashboard />} />
          <Route path="/app/sectors" element={<SectorAnalysis />} />
          <Route path="/app/sentiment" element={<Sentiment />} />
          <Route path="/app/commodities" element={<CommoditiesAnalysis />} />

          {/* Stocks Analysis */}
          <Route path="/app/deep-value" element={<DeepValueStocks />} />
          <Route path="/app/financial-data" element={<FinancialData />} />
          <Route path="/app/trading-signals" element={<TradingSignals />} />
          <Route path="/app/signals" element={<TradingSignals />} />
          <Route path="/app/range-signals" element={<TradingSignals />} />
          <Route path="/app/mean-reversion" element={<TradingSignals />} />
          <Route path="/app/etf-signals" element={<ETFSignals />} />
          <Route path="/app/earnings" element={<EarningsCalendar />} />
          <Route path="/app/scores" element={<ScoresDashboard />} />
          <Route path="/app/metrics" element={<MetricsDashboard />} />

          {/* Portfolio & Trading */}
          <Route path="/app/portfolio" element={<PortfolioDashboard />} />
          <Route path="/app/trades" element={<TradeHistory />} />
          <Route path="/app/optimizer" element={<PortfolioOptimizerNew />} />
          <Route path="/app/hedge-helper" element={<HedgeHelper />} />

          {/* Research & Testing */}
          <Route path="/app/backtests" element={<BacktestResults />} />

          {/* Admin & Settings */}
          <Route path="/app/health" element={<ServiceHealth />} />
          <Route path="/app/settings" element={<Settings />} />
        </Routes>

        {/* Authentication Modal */}
        <AuthModal open={authModalOpen} onClose={() => setAuthModalOpen(false)} />
      </AppLayout>
    </ErrorBoundary>
  );
}

export default App;
