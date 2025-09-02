import React, { useState, useEffect } from "react";
import { Routes, Route, useNavigate, useLocation } from "react-router-dom";
import {
  AppBar,
  Box,
  Toolbar,
  Typography,
  Container,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  IconButton,
  useTheme,
  useMediaQuery,
  Button,
  Menu,
  MenuItem,
  Avatar,
  Divider,
} from "@mui/material";
import {
  Menu as MenuIcon,
  Dashboard as DashboardIcon,
  PlayArrow,
  Settings as SettingsIcon,
  ExpandLess,
  ExpandMore,
  Stars,
  TrendingUp as TrendingUpIcon,
  Business as BusinessIcon,
  Public as PublicIcon,
  Search as SearchIcon,
  FilterList as FilterListIcon,
  ShowChart as ShowChartIcon,
  Event as EventIcon,
  Timeline as TimelineIcon,
  Psychology as PsychologyIcon,
  Person as PersonIcon,
  AccountBalance as AccountBalanceIcon,
  Assessment as AssessmentIcon,
  Analytics as AnalyticsIcon,
  HealthAndSafety as HealthAndSafetyIcon,
  Storage as StorageIcon,
  AccountCircle as AccountCircleIcon,
  Login as LoginIcon,
  Logout as LogoutIcon,
} from "@mui/icons-material";

// All real page imports
import Dashboard from "./pages/Dashboard";
import MarketOverview from "./pages/MarketOverview";
import StockExplorer from "./pages/StockExplorer";
import StockDetail from "./pages/StockDetail";
import MetricsDashboard from "./pages/MetricsDashboard";
import TechnicalAnalysis from "./pages/TechnicalAnalysis";
import AnalystInsights from "./pages/AnalystInsights";
import EarningsCalendar from "./pages/EarningsCalendar";
import FinancialData from "./pages/FinancialData";
import ServiceHealth from "./pages/ServiceHealth";
import TechnicalHistory from "./pages/TechnicalHistory";
import Backtest from "./pages/Backtest";
import TradingSignals from "./pages/TradingSignals";
import Portfolio from "./pages/Portfolio";
import PortfolioPerformance from "./pages/PortfolioPerformance";
import PortfolioOptimization from "./pages/PortfolioOptimization";
import TradeHistory from "./pages/TradeHistory";
import OrderManagement from "./pages/OrderManagement";
import SentimentAnalysis from "./pages/SentimentAnalysis";
import NewsAnalysis from "./pages/NewsAnalysis";
import PatternRecognition from "./pages/PatternRecognition";
import AdvancedScreener from "./pages/AdvancedScreener";
import EconomicModeling from "./pages/EconomicModeling";
import Settings from "./pages/Settings";
import ScoresDashboard from "./pages/ScoresDashboard";
import { useAuth } from "./contexts/AuthContext";
import AuthModal from "./components/auth/AuthModal";
import OnboardingWizard from "./components/onboarding/OnboardingWizard";
import { useOnboarding } from "./hooks/useOnboarding";
import ComingSoon from "./pages/ComingSoon";
import Watchlist from "./pages/Watchlist";
import SectorAnalysis from "./pages/SectorAnalysis";
import RealTimeDashboard from "./pages/RealTimeDashboard";
import TestApiPage from "./pages/TestApiPage";
import PortfolioPerformanceSimple from "./pages/PortfolioPerformanceSimple";
import PortfolioPerformanceDebug from "./pages/PortfolioPerformanceDebug";
import AuthTest from "./pages/AuthTest";
import AIAssistant from "./pages/AIAssistant";
import { createComponentLogger } from "./utils/errorLogger";

const drawerWidth = 240;

const menuItems = [
  // Dashboard Section
  { text: "Dashboard", icon: <DashboardIcon />, path: "/", category: "main" },

  // Markets Section
  {
    text: "Market Overview",
    icon: <TrendingUpIcon />,
    path: "/market",
    category: "markets",
  },
  {
    text: "Sector Analysis",
    icon: <BusinessIcon />,
    path: "/sectors",
    category: "markets",
  },
  {
    text: "Economic Indicators",
    icon: <PublicIcon />,
    path: "/economic",
    category: "markets",
  },

  // Stocks Section
  {
    text: "Stock Screener",
    icon: <SearchIcon />,
    path: "/screener-advanced",
    category: "stocks",
  },
  {
    text: "Stock Analysis",
    icon: <FilterListIcon />,
    path: "/stocks",
    category: "stocks",
  },
  {
    text: "Technical Analysis",
    icon: <ShowChartIcon />,
    path: "/technical",
    category: "stocks",
  },
  {
    text: "Stock Scores",
    icon: <Stars />,
    path: "/scores",
    category: "stocks",
    premium: true,
  },
  {
    text: "Earnings Calendar",
    icon: <EventIcon />,
    path: "/earnings",
    category: "stocks",
  },
  {
    text: "Watchlist",
    icon: <TimelineIcon />,
    path: "/watchlist",
    category: "stocks",
  },

  // Sentiment Analysis Section (Premium)
  {
    text: "Market Sentiment",
    icon: <PsychologyIcon />,
    path: "/sentiment",
    category: "sentiment",
    premium: true,
  },
  {
    text: "Social Media Sentiment",
    icon: <PsychologyIcon />,
    path: "/sentiment/social",
    category: "sentiment",
    premium: true,
  },
  {
    text: "News Sentiment",
    icon: <PsychologyIcon />,
    path: "/sentiment/news",
    category: "sentiment",
    premium: true,
  },
  {
    text: "Analyst Insights",
    icon: <PersonIcon />,
    path: "/sentiment/analysts",
    category: "sentiment",
    premium: true,
  },

  // Portfolio Section
  {
    text: "Portfolio Overview",
    icon: <AccountBalanceIcon />,
    path: "/portfolio",
    category: "portfolio",
  },
  {
    text: "Trade History",
    icon: <TimelineIcon />,
    path: "/trade-history",
    category: "portfolio",
  },
  {
    text: "Order Management",
    icon: <PlayArrow />,
    path: "/orders",
    category: "portfolio",
  },
  {
    text: "Performance Analysis",
    icon: <AssessmentIcon />,
    path: "/portfolio/performance",
    category: "portfolio",
    premium: true,
  },
  {
    text: "Optimization Tools",
    icon: <AnalyticsIcon />,
    path: "/portfolio/optimize",
    category: "portfolio",
    premium: true,
  },

  // Research & Education Section
  {
    text: "Market Commentary",
    icon: <EventIcon />,
    path: "/research/commentary",
    category: "research",
  },
  {
    text: "Educational Content",
    icon: <HealthAndSafetyIcon />,
    path: "/research/education",
    category: "research",
  },
  {
    text: "Research Reports",
    icon: <AnalyticsIcon />,
    path: "/research/reports",
    category: "research",
    premium: true,
  },
  {
    text: "Financial Data",
    icon: <StorageIcon />,
    path: "/financial-data",
    category: "research",
  },

  // Tools Section
  {
    text: "Real-Time Data",
    icon: <PlayArrow />,
    path: "/realtime",
    category: "tools",
  },
  {
    text: "Settings",
    icon: <SettingsIcon />,
    path: "/settings",
    category: "tools",
  },
  {
    text: "Health",
    icon: <HealthAndSafetyIcon />,
    path: "/service-health",
    category: "tools",
  },
  {
    text: "Pattern Recognition",
    icon: <AnalyticsIcon />,
    path: "/tools/patterns",
    category: "tools",
    premium: true,
  },
  {
    text: "Backtester",
    icon: <PlayArrow />,
    path: "/backtest",
    category: "tools",
    premium: true,
  },
  {
    text: "AI Assistant",
    icon: <PsychologyIcon />,
    path: "/tools/ai",
    category: "tools",
    premium: true,
  },

];

function App() {
  console.log("🎯 APP COMPONENT: Starting App component render...");
  
  try {
    const [mobileOpen, setMobileOpen] = useState(false);
    const [authModalOpen, setAuthModalOpen] = useState(false);
    const [userMenuAnchor, setUserMenuAnchor] = useState(null);
    const [expandedSections, setExpandedSections] = useState({
      markets: true,
      stocks: true,
      sentiment: false,
      portfolio: true,
      research: false,
      tools: false,
    });
    
    console.log("🎯 APP COMPONENT: State initialized");
    
    const theme = useTheme();
    console.log("🎯 APP COMPONENT: Theme loaded:", theme ? "✅" : "❌");
    
    const isMobile = useMediaQuery(theme.breakpoints.down("md"));
    console.log("🎯 APP COMPONENT: isMobile:", isMobile);
    
    console.log("🎯 APP COMPONENT: About to call useAuth...");
    const { isAuthenticated, user, logout } = useAuth();
    console.log("🎯 APP COMPONENT: Auth state loaded - isAuthenticated:", isAuthenticated, "user:", user);
    
    const navigate = useNavigate();
    console.log("🎯 APP COMPONENT: Navigate loaded");
    
    const location = useLocation();
    console.log("🎯 APP COMPONENT: Location loaded:", location?.pathname);
    
    console.log("🎯 APP COMPONENT: About to call useOnboarding...");
    const {
      showOnboarding,
      completeOnboarding,
      skipOnboarding,
      loading: onboardingLoading,
    } = useOnboarding();
    console.log("🎯 APP COMPONENT: Onboarding loaded - loading:", onboardingLoading, "show:", showOnboarding);

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
    // All features are now available - no premium restrictions
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

  const groupedMenuItems = menuItems.reduce((acc, item) => {
    if (!acc[item.category]) {
      acc[item.category] = [];
    }
    acc[item.category].push(item);
    return acc;
  }, {});

  const sectionTitles = {
    main: "Dashboard",
    markets: "Markets",
    stocks: "Stocks",
    sentiment: "Sentiment Analysis",
    portfolio: "Portfolio",
    research: "Research & Education",
    tools: "Tools",
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
          Financial Platform
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
                    aria-label={`${expandedSections[category] ? 'Collapse' : 'Expand'} ${sectionTitles[category]} section`}
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
  
  } catch (error) {
    console.error("🚨 APP COMPONENT ERROR:", error);
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh" }}>
        <Typography color="error">Application Error: {error.message}</Typography>
      </Box>
    );
  }
  
  return (
    <Box sx={{ display: "flex" }}>
      <AppBar
        position="fixed"
        sx={{
          width: { md: `calc(100% - ${drawerWidth}px)` },
          ml: { md: `${drawerWidth}px` },
          backgroundColor: "white",
          color: "text.primary",
          boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
        }}
      >
        <Toolbar>
          <IconButton
            color="inherit"
            aria-label="open drawer"
            edge="start"
            onClick={handleDrawerToggle}
            sx={{ mr: 2, display: { md: "none" } }}
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" noWrap component="div" sx={{ flexGrow: 1 }}>
            {menuItems.find((item) => item.path === location.pathname)?.text ||
              "Dashboard"}
          </Typography>

          {/* Authentication UI */}
          {isAuthenticated ? (
            <>
              <IconButton
                onClick={handleUserMenuOpen}
                size="large"
                edge="end"
                color="inherit"
              >
                <Avatar sx={{ width: 32, height: 32, bgcolor: "primary.main" }}>
                  {user?.username?.[0]?.toUpperCase() || "U"}
                </Avatar>
              </IconButton>
              <Menu
                anchorEl={userMenuAnchor}
                open={Boolean(userMenuAnchor)}
                onClose={handleUserMenuClose}
                anchorOrigin={{
                  vertical: "bottom",
                  horizontal: "right",
                }}
                transformOrigin={{
                  vertical: "top",
                  horizontal: "right",
                }}
              >
                <MenuItem onClick={handleUserMenuClose}>
                  <AccountCircleIcon sx={{ mr: 1 }} />
                  {user?.username || "User"}
                </MenuItem>
                <Divider />
                <MenuItem
                  onClick={() => {
                    handleUserMenuClose();
                    navigate("/settings");
                  }}
                >
                  <SettingsIcon sx={{ mr: 1 }} />
                  Settings
                </MenuItem>
                <MenuItem onClick={handleLogout}>
                  <LogoutIcon sx={{ mr: 1 }} />
                  Sign Out
                </MenuItem>
              </Menu>
            </>
          ) : (
            <Button
              color="inherit"
              startIcon={<LoginIcon />}
              onClick={() => setAuthModalOpen(true)}
              sx={{ ml: 2 }}
            >
              Sign In
            </Button>
          )}
        </Toolbar>
      </AppBar>

      <Box
        component="nav"
        sx={{ width: { md: drawerWidth }, flexShrink: { md: 0 } }}
      >
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={handleDrawerToggle}
          ModalProps={{
            keepMounted: true, // Better open performance on mobile.
          }}
          sx={{
            display: { xs: "block", md: "none" },
            "& .MuiDrawer-paper": {
              boxSizing: "border-box",
              width: drawerWidth,
            },
          }}
        >
          {drawer}
        </Drawer>
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: "none", md: "block" },
            "& .MuiDrawer-paper": {
              boxSizing: "border-box",
              width: drawerWidth,
            },
          }}
          open
        >
          {drawer}
        </Drawer>
      </Box>

      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: 3,
          width: { md: `calc(100% - ${drawerWidth}px)` },
          backgroundColor: theme.palette.background.default,
          minHeight: "100vh",
        }}
      >
        <Toolbar />
        <Container maxWidth="xl">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/realtime" element={<RealTimeDashboard />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/trade-history" element={<TradeHistory />} />
            <Route path="/orders" element={<OrderManagement />} />
            <Route
              path="/portfolio/performance"
              element={<PortfolioPerformance />}
            />
            <Route
              path="/portfolio/optimize"
              element={<PortfolioOptimization />}
            />
            <Route path="/market" element={<MarketOverview />} />
            <Route path="/screener-advanced" element={<AdvancedScreener />} />
            <Route path="/scores" element={<ScoresDashboard />} />
            <Route path="/sentiment" element={<SentimentAnalysis />} />
            <Route path="/economic" element={<EconomicModeling />} />
            <Route path="/metrics" element={<MetricsDashboard />} />
            <Route path="/stocks" element={<StockExplorer />} />
            <Route path="/stock-explorer" element={<StockExplorer />} />
            <Route path="/stocks/:ticker" element={<StockDetail />} />
            <Route path="/screener" element={<StockExplorer />} />
            <Route path="/trading" element={<TradingSignals />} />
            <Route path="/trading-signals" element={<TradingSignals />} />
            <Route path="/technical" element={<TechnicalAnalysis />} />
            <Route path="/technical-analysis" element={<TechnicalAnalysis />} />
            <Route path="/analysts" element={<AnalystInsights />} />
            <Route path="/earnings" element={<EarningsCalendar />} />
            <Route path="/backtest" element={<Backtest />} />
            <Route path="/financial-data" element={<FinancialData />} />
            <Route path="/service-health" element={<ServiceHealth />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/test-api" element={<TestApiPage />} />
            <Route
              path="/portfolio/performance-simple"
              element={<PortfolioPerformanceSimple />}
            />
            <Route
              path="/portfolio/performance-debug"
              element={<PortfolioPerformanceDebug />}
            />
            <Route path="/auth-test" element={<AuthTest />} />
            <Route
              path="/technical-history/:symbol"
              element={<TechnicalHistory />}
            />

            {/* Missing pages - Coming Soon */}
            <Route path="/sectors" element={<SectorAnalysis />} />
            <Route path="/watchlist" element={<Watchlist />} />
            <Route path="/sentiment/social" element={<SentimentAnalysis />} />
            <Route path="/sentiment/news" element={<NewsAnalysis />} />
            <Route path="/sentiment/analysts" element={<AnalystInsights />} />
            <Route
              path="/research/commentary"
              element={
                <ComingSoon
                  pageName="Market Commentary"
                  description="Expert market commentary and analysis."
                />
              }
            />
            <Route
              path="/research/education"
              element={
                <ComingSoon
                  pageName="Educational Content"
                  description="Learn about investing and market analysis."
                />
              }
            />
            <Route
              path="/research/reports"
              element={
                <ComingSoon
                  pageName="Research Reports"
                  description="In-depth research reports and market insights."
                />
              }
            />
            <Route path="/tools/patterns" element={<PatternRecognition />} />
            <Route path="/tools/ai" element={<AIAssistant />} />
          </Routes>
        </Container>
      </Box>

      {/* Authentication Modal */}
      <AuthModal open={authModalOpen} onClose={() => setAuthModalOpen(false)} />

      {/* Onboarding Wizard */}
      {isAuthenticated && showOnboarding && !onboardingLoading && (
        <OnboardingWizard
          open={true}
          onClose={skipOnboarding}
          onComplete={completeOnboarding}
        />
      )}
    </Box>
  );
}

export default App;
