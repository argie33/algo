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
  Dashboard as _DashboardIcon,
  Settings as SettingsIcon,
  ExpandLess,
  ExpandMore,
  Stars,
  TrendingUp as TrendingUpIcon,
  Business as BusinessIcon,
  Public as PublicIcon,
  ShowChart as ShowChartIcon,
  Event as EventIcon,
  Timeline as TimelineIcon,
  Psychology as PsychologyIcon,
  AccountBalance as AccountBalanceIcon,
  Analytics as AnalyticsIcon,
  HealthAndSafety as HealthAndSafetyIcon,
  Storage as StorageIcon,
  AccountCircle as AccountCircleIcon,
  Login as LoginIcon,
  Logout as LogoutIcon,
  SwapHoriz as SwapHorizIcon,
} from "@mui/icons-material";

// All real page imports (PUBLIC DATA ONLY)
import MarketOverview from "./pages/MarketOverview";
import EarningsCalendar from "./pages/EarningsCalendar";
import FinancialData from "./pages/FinancialData";
import Sentiment from "./pages/Sentiment";
import ScoresDashboard from "./pages/ScoresDashboard";
import { useAuth } from "./contexts/AuthContext";
import AuthModal from "./components/auth/AuthModal";
import ProtectedRoute from "./components/auth/ProtectedRoute";
import ErrorBoundary from "./components/ErrorBoundary";
import RootRedirect from "./components/RootRedirect";
import SectorAnalysis from "./pages/SectorAnalysis";
import TradingSignals from "./pages/TradingSignals";
import ETFSignals from "./pages/ETFSignals";
import EconomicDashboard from "./pages/EconomicDashboard";
import HedgeHelper from "./pages/HedgeHelper";

const drawerWidth = 240;

const menuItems = [
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
    text: "Stock Scores",
    icon: <Stars />,
    path: "/scores",
    category: "stocks",
    premium: true,
  },
  {
    text: "Earnings Hub",
    icon: <EventIcon />,
    path: "/earnings",
    category: "stocks",
  },
  {
    text: "Financial Data",
    icon: <StorageIcon />,
    path: "/financial-data",
    category: "stocks",
  },
  {
    text: "Trading Signals",
    icon: <TrendingUpIcon />,
    path: "/trading-signals",
    category: "stocks",
  },
  {
    text: "ETF Trading Signals",
    icon: <PublicIcon />,
    path: "/etf-trading-signals",
    category: "stocks",
  },

  // Sentiment Analysis Section
  {
    text: "Sentiment Analysis",
    icon: <PsychologyIcon />,
    path: "/sentiment",
    category: "stocks",
  },

  // Hedge Helper - Options Strategies
  {
    text: "Hedge Helper",
    icon: <SwapHorizIcon />,
    path: "/hedge-helper",
    category: "stocks",
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
    sentiment: false,
    research: false,
    tools: false,
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
    stocks: "Stocks",
    sentiment: "Sentiment Analysis",
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

  return (
    <ErrorBoundary>
      <Box sx={{ display: "flex", width: "100%", overflowX: "hidden" }}>
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
          <Typography
            variant="h6"
            noWrap
            component="div"
            sx={{
              flexGrow: 1,
              mr: 2,
              pointerEvents: 'none'
            }}
          >
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
              sx={{
                ml: 2,
                zIndex: 1000,
                position: 'relative',
                flexShrink: 0
              }}
              data-testid="auth-sign-in-button"
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
          p: { xs: 1, sm: 2, md: 3 },
          width: { xs: "100%", md: `calc(100% - ${drawerWidth}px)` },
          backgroundColor: theme.palette.background.default,
          minHeight: "100vh",
          overflowX: "hidden",
        }}
      >
        <Toolbar />
        <Container maxWidth="xl" sx={{ px: { xs: 1, sm: 2, md: 3 } }}>
          <Routes>
            <Route path="/" element={<RootRedirect />} />
            <Route path="/market" element={<MarketOverview />} />
            <Route path="/scores" element={<ScoresDashboard />} />
            <Route path="/earnings" element={<EarningsCalendar />} />
            <Route path="/financial-data" element={<FinancialData />} />
            <Route path="/sentiment" element={<Sentiment />} />
            <Route path="/sectors" element={<SectorAnalysis />} />
            <Route path="/trading-signals" element={<TradingSignals />} />
            <Route path="/etf-trading-signals" element={<ETFSignals />} />
            <Route path="/economic" element={<EconomicDashboard />} />
            <Route path="/hedge-helper" element={<HedgeHelper />} />
          </Routes>
        </Container>
      </Box>

      {/* Authentication Modal */}
      <AuthModal open={authModalOpen} onClose={() => setAuthModalOpen(false)} />
      </Box>
    </ErrorBoundary>
  );
}

export default App;
