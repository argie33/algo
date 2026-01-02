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
  Business as BusinessIcon,
  Public as PublicIcon,
  Event as EventIcon,
  Psychology as PsychologyIcon,
  SwapHoriz as SwapHorizIcon,
  Storage as StorageIcon,
} from "@mui/icons-material";

// All real page imports (PUBLIC DATA ONLY)
import MarketOverview from "./pages/MarketOverview";
import EarningsCalendar from "./pages/EarningsCalendar";
import FinancialData from "./pages/FinancialData";
import Sentiment from "./pages/Sentiment";
import ScoresDashboard from "./pages/ScoresDashboard";
import { useAuth } from "./contexts/AuthContext";
import AuthModal from "./components/auth/AuthModal";
import ErrorBoundary from "./components/ErrorBoundary";
import SectorAnalysis from "./pages/SectorAnalysis";
import TradingSignals from "./pages/TradingSignals";
import ETFSignals from "./pages/ETFSignals";
import EconomicDashboard from "./pages/EconomicDashboard";
import HedgeHelper from "./pages/HedgeHelper";

// Marketing pages - Only keep main pages and their dropdown pages
import Home from "./pages/marketing/Home";
import Firm from "./pages/marketing/Firm";
import Services from "./pages/marketing/Services";
import Contact from "./pages/marketing/Contact";
import About from "./pages/marketing/About";
import OurTeam from "./pages/marketing/OurTeam";
import MissionValues from "./pages/marketing/MissionValues";
import ResearchInsights from "./pages/marketing/ResearchInsights";
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
          <Route path="/services" element={<Services />} />
          <Route path="/contact" element={<Contact />} />

          {/* Firm Dropdown Pages */}
          <Route path="/about" element={<About />} />
          <Route path="/our-team" element={<OurTeam />} />
          <Route path="/mission-values" element={<MissionValues />} />

          {/* Services Dropdown Pages */}
          <Route path="/research-insights" element={<ResearchInsights />} />
          <Route path="/investment-tools" element={<InvestmentTools />} />
          <Route path="/wealth-management" element={<WealthManagement />} />

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
          <Route path="/app/market" element={<MarketOverview />} />
          <Route path="/app/scores" element={<ScoresDashboard />} />
          <Route path="/app/earnings" element={<EarningsCalendar />} />
          <Route path="/app/financial-data" element={<FinancialData />} />
          <Route path="/app/sentiment" element={<Sentiment />} />
          <Route path="/app/sectors" element={<SectorAnalysis />} />
          <Route path="/app/trading-signals" element={<TradingSignals />} />
          <Route path="/app/etf-trading-signals" element={<ETFSignals />} />
          <Route path="/app/economic" element={<EconomicDashboard />} />
          <Route path="/app/hedge-helper" element={<HedgeHelper />} />
        </Routes>

        {/* Authentication Modal */}
        <AuthModal open={authModalOpen} onClose={() => setAuthModalOpen(false)} />
      </AppLayout>
    </ErrorBoundary>
  );
}

export default App;
