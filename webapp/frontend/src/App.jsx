// UNIFIED ROUTING ARCHITECTURE - Single predictable flow
import { useState, lazy, Suspense } from 'react'
import { Routes, Route, useLocation } from 'react-router-dom'
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
  CircularProgress,
  Collapse
} from '@mui/material'
import {
  Menu as MenuIcon,
  Dashboard as DashboardIcon,
  TrendingUp as TrendingUpIcon,
  ShowChart as ShowChartIcon,
  Analytics as AnalyticsIcon,
  FilterList as FilterListIcon,
  Business as BusinessIcon,
  Timeline as TimelineIcon,
  Person as PersonIcon,
  Event as EventIcon,
  Storage as StorageIcon,
  AccountBalance as AccountBalanceIcon,
  HealthAndSafety as HealthAndSafetyIcon,
  Assessment as AssessmentIcon,
  PlayArrow,
  Login as LoginIcon,
  Logout as LogoutIcon,
  AccountCircle as AccountCircleIcon,
  Psychology as PsychologyIcon,
  Search as SearchIcon,
  Public as PublicIcon,
  Settings as SettingsIcon,
  ExpandLess,
  ExpandMore,
  Stars,
  History as HistoryIcon,
  Grain as GrainIcon,
  Bolt as BoltIcon
} from '@mui/icons-material'

// UNIFIED ROUTING IMPORTS
import { NavigationProvider, useNavigation } from './contexts/NavigationContext'
import { useAuth } from './contexts/AuthContext'
import { ROUTE_CONFIG } from './routing/routeConfig'
import RouteGuard from './components/routing/RouteGuard'
import AuthModal from './components/auth/AuthModal'
import SystemHealthMonitor from './components/SystemHealthMonitor'
import ErrorBoundary from './components/ErrorBoundary'

// LAZY LOADED PAGES - Keep existing lazy loading for performance
const Dashboard = lazy(() => import('./pages/Dashboard'))
const MarketOverview = lazy(() => import('./pages/MarketOverview'))
const StockExplorer = lazy(() => import('./pages/StockExplorer'))
const StockDetail = lazy(() => import('./pages/StockDetail'))
const SectorAnalysis = lazy(() => import('./pages/SectorAnalysis'))
const Commodities = lazy(() => import('./pages/Commodities'))
const EconomicModeling = lazy(() => import('./pages/EconomicModeling'))
const Portfolio = lazy(() => import('./pages/Portfolio'))
const PortfolioPerformance = lazy(() => import('./pages/PortfolioPerformance'))
const PortfolioOptimization = lazy(() => import('./pages/PortfolioOptimization'))
const TradeHistory = lazy(() => import('./pages/TradeHistory'))
const TechnicalAnalysis = lazy(() => import('./pages/TechnicalAnalysis'))
const AnalystInsights = lazy(() => import('./pages/AnalystInsights'))
const MetricsDashboard = lazy(() => import('./pages/MetricsDashboard'))
const FinancialData = lazy(() => import('./pages/FinancialData'))
const EarningsCalendar = lazy(() => import('./pages/EarningsCalendar'))
const TechnicalHistory = lazy(() => import('./pages/TechnicalHistory'))
const ScoresDashboard = lazy(() => import('./pages/ScoresDashboard'))
const TradingSignals = lazy(() => import('./pages/TradingSignals'))
const Backtest = lazy(() => import('./pages/Backtest'))
const AdvancedScreener = lazy(() => import('./pages/AdvancedScreener'))
const SentimentAnalysis = lazy(() => import('./pages/SentimentAnalysis'))
const SocialMediaSentiment = lazy(() => import('./pages/SocialMediaSentiment'))
const NewsSentiment = lazy(() => import('./pages/NewsSentiment'))
const OptionsAnalytics = lazy(() => import('./pages/options/OptionsAnalytics'))
const OptionsStrategies = lazy(() => import('./pages/options/OptionsStrategies'))
const OptionsFlow = lazy(() => import('./pages/options/OptionsFlow'))
const VolatilitySurface = lazy(() => import('./pages/options/VolatilitySurface'))
const GreeksMonitor = lazy(() => import('./pages/options/GreeksMonitor'))
const CryptoMarketOverview = lazy(() => import('./pages/CryptoMarketOverview'))
const CryptoPortfolio = lazy(() => import('./pages/CryptoPortfolio'))
const CryptoRealTimeTracker = lazy(() => import('./pages/CryptoRealTimeTracker'))
const CryptoAdvancedAnalytics = lazy(() => import('./pages/CryptoAdvancedAnalytics'))
const LiveDataAdmin = lazy(() => import('./pages/LiveDataAdmin'))
const HFTTrading = lazy(() => import('./pages/HFTTrading'))
const NeuralHFTCommandCenter = lazy(() => import('./pages/NeuralHFTCommandCenter'))
const ServiceHealth = lazy(() => import('./pages/ServiceHealth'))
const Settings = lazy(() => import('./pages/Settings'))
const Watchlist = lazy(() => import('./pages/Watchlist'))
const MarketCommentary = lazy(() => import('./pages/MarketCommentary'))
const EducationalContent = lazy(() => import('./pages/EducationalContent'))
const PatternRecognition = lazy(() => import('./pages/PatternRecognition'))
const AIAssistant = lazy(() => import('./pages/AIAssistant'))
const WelcomeLanding = lazy(() => import('./pages/WelcomeLanding'))

// Component mapping for routes
const COMPONENT_MAP = {
  Dashboard,
  MarketOverview,
  StockExplorer,
  StockDetail,
  SectorAnalysis,
  Commodities,
  EconomicModeling,
  Portfolio,
  PortfolioPerformance,
  PortfolioOptimization,
  TradeHistory,
  TechnicalAnalysis,
  AnalystInsights,
  MetricsDashboard,
  FinancialData,
  EarningsCalendar,
  TechnicalHistory,
  ScoresDashboard,
  TradingSignals,
  Backtest,
  AdvancedScreener,
  SentimentAnalysis,
  SocialMediaSentiment,
  NewsSentiment,
  OptionsAnalytics,
  OptionsStrategies,
  OptionsFlow,
  VolatilitySurface,
  GreeksMonitor,
  CryptoMarketOverview,
  CryptoPortfolio,
  CryptoRealTimeTracker,
  CryptoAdvancedAnalytics,
  LiveDataAdmin,
  HFTTrading,
  NeuralHFTCommandCenter,
  ServiceHealth,
  Settings,
  Watchlist,
  MarketCommentary,
  EducationalContent,
  PatternRecognition,
  AIAssistant,
  WelcomeLanding
};

// Centralized loading component
const PageLoader = () => (
  <Box 
    display="flex" 
    justifyContent="center" 
    alignItems="center" 
    minHeight="60vh"
    flexDirection="column"
    gap={2}
  >
    <CircularProgress size={40} />
    <Typography variant="body2" color="textSecondary">
      Loading page...
    </Typography>
  </Box>
)

const drawerWidth = 240

const menuItems = [
  // Dashboard Section
  { text: 'Dashboard', icon: <DashboardIcon />, path: '/dashboard', category: 'main' },
  
  // Markets Section
  { text: 'Market Overview', icon: <TrendingUpIcon />, path: '/market', category: 'markets' },
  { text: 'Sector Analysis', icon: <BusinessIcon />, path: '/sectors', category: 'markets' },
  { text: 'Commodities', icon: <GrainIcon />, path: '/commodities', category: 'markets' },
  { text: 'Economic Indicators', icon: <PublicIcon />, path: '/economic', category: 'markets' },
  
  // Cryptocurrency Section
  { text: 'Crypto Market', icon: <TrendingUpIcon />, path: '/crypto', category: 'crypto' },
  { text: 'Crypto Portfolio', icon: <AccountBalanceIcon />, path: '/crypto/portfolio', category: 'crypto' },
  { text: 'Real-Time Tracker', icon: <ShowChartIcon />, path: '/crypto/realtime', category: 'crypto' },
  { text: 'Advanced Analytics', icon: <AnalyticsIcon />, path: '/crypto/analytics', category: 'crypto' },
  
  // Stocks Section
  { text: 'Stock Screener', icon: <SearchIcon />, path: '/screener-advanced', category: 'stocks' },
  { text: 'Stock Analysis', icon: <FilterListIcon />, path: '/stocks', category: 'stocks' },
  { text: 'Technical Analysis', icon: <ShowChartIcon />, path: '/technical', category: 'stocks' },
  { text: 'Pattern Recognition', icon: <AnalyticsIcon />, path: '/stocks/patterns', category: 'stocks' },
  { text: 'Trading Signals', icon: <TrendingUpIcon />, path: '/trading', category: 'stocks' },
  { text: 'Stock Scores', icon: <Stars />, path: '/scores', category: 'stocks' },
  { text: 'Financial Data', icon: <StorageIcon />, path: '/financial-data', category: 'stocks' },
  { text: 'Earnings Calendar', icon: <EventIcon />, path: '/earnings', category: 'stocks' },
  { text: 'Watchlist', icon: <TimelineIcon />, path: '/watchlist', category: 'stocks' },
  
  // Options Trading Section
  { text: 'Options Analytics', icon: <AssessmentIcon />, path: '/options', category: 'options' },
  { text: 'Options Strategies', icon: <AnalyticsIcon />, path: '/options/strategies', category: 'options' },
  { text: 'Options Flow', icon: <TimelineIcon />, path: '/options/flow', category: 'options' },
  { text: 'Volatility Surface', icon: <ShowChartIcon />, path: '/options/volatility', category: 'options' },
  { text: 'Greeks Monitor', icon: <AnalyticsIcon />, path: '/options/greeks', category: 'options' },
  
  // Sentiment Analysis Section
  { text: 'Market Sentiment', icon: <PsychologyIcon />, path: '/sentiment', category: 'sentiment' },
  { text: 'Social Media Sentiment', icon: <PsychologyIcon />, path: '/sentiment/social', category: 'sentiment' },
  { text: 'News Sentiment', icon: <PsychologyIcon />, path: '/sentiment/news', category: 'sentiment' },
  { text: 'Analyst Insights', icon: <PersonIcon />, path: '/sentiment/analysts', category: 'sentiment' },
  
  // Portfolio Section
  { text: 'Portfolio Overview', icon: <AccountBalanceIcon />, path: '/portfolio', category: 'portfolio' },
  { text: 'Trade History', icon: <HistoryIcon />, path: '/portfolio/trade-history', category: 'portfolio' },
  { text: 'Performance Analysis', icon: <AssessmentIcon />, path: '/portfolio/performance', category: 'portfolio' },
  { text: 'Optimization Tools', icon: <AnalyticsIcon />, path: '/portfolio/optimize', category: 'portfolio' },
  
  // Research & Education Section
  { text: 'Market Commentary', icon: <EventIcon />, path: '/research/commentary', category: 'research' },
  { text: 'Educational Content', icon: <HealthAndSafetyIcon />, path: '/research/education', category: 'research' },
  
  // Tools Section
  { text: 'Backtester', icon: <PlayArrow />, path: '/backtest', category: 'tools' },
  { text: 'Live Data Manager', icon: <TrendingUpIcon />, path: '/live-data', category: 'tools' },
  { text: 'HFT Trading', icon: <ShowChartIcon />, path: '/hft-trading', category: 'tools' },
  { text: 'Neural HFT Command Center', icon: <BoltIcon />, path: '/neural-hft', category: 'tools' },
  { text: 'AI Assistant', icon: <PsychologyIcon />, path: '/tools/ai', category: 'tools' },
  { text: 'Service Health', icon: <HealthAndSafetyIcon />, path: '/service-health', category: 'tools' },
  { text: 'Settings', icon: <SettingsIcon />, path: '/settings', category: 'tools' },
]

// Main App Component with Unified Navigation
function AppContent() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [userMenuAnchor, setUserMenuAnchor] = useState(null)
  const [expandedSections, setExpandedSections] = useState({
    markets: true,
    crypto: true,
    stocks: true,
    options: true,
    sentiment: false,
    portfolio: true,
    research: false,
    tools: false
  })
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('md'))
  const location = useLocation()
  
  // UNIFIED NAVIGATION HOOKS
  const { isAuthenticated, user, logout } = useAuth()
  const { authModalOpen, closeAuthModal, navigateTo, handleSpecialRoute } = useNavigation()

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen)
  }

  const handleUserMenuOpen = (event) => {
    setUserMenuAnchor(event.currentTarget)
  }

  const handleUserMenuClose = () => {
    setUserMenuAnchor(null)
  }

  const handleLogout = async () => {
    handleUserMenuClose()
    await logout()
    // Navigation will be handled by NavigationContext
  }

  // UNIFIED NAVIGATION HANDLER
  const handleNavigation = (path) => {
    navigateTo(path)
    if (isMobile) {
      setMobileOpen(false)
    }
  }

  const handleSectionToggle = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }))
  }

  const groupedMenuItems = menuItems.reduce((acc, item) => {
    if (!acc[item.category]) {
      acc[item.category] = []
    }
    acc[item.category].push(item)
    return acc
  }, {})

  const sectionTitles = {
    main: 'Dashboard',
    markets: 'Markets',
    crypto: 'Cryptocurrency',
    stocks: 'Stocks',
    options: 'Options Trading',
    sentiment: 'Sentiment Analysis',
    portfolio: 'Portfolio',
    research: 'Research & Education',
    tools: 'Tools'
  }

  // Render component for route
  const renderRouteComponent = (route) => {
    const Component = COMPONENT_MAP[route.component];
    
    if (!Component) {
      return <div>Component {route.component} not found</div>;
    }
    
    return (
      <RouteGuard path={route.path}>
        <Component />
      </RouteGuard>
    );
  };

  // Get page title
  const getPageTitle = (pathname) => {
    if (pathname === '/') return 'Market Overview';
    if (pathname === '/dashboard') return 'Dashboard';
    
    const route = [...ROUTE_CONFIG.PUBLIC_ROUTES, ...ROUTE_CONFIG.PROTECTED_ROUTES]
      .find(r => r.path === pathname);
    return route?.component || 'Financial Platform';
  };

  const drawer = (
    <div>
      <Toolbar>
        <Typography variant="h6" noWrap component="div" sx={{ fontWeight: 700, color: 'primary.main' }}>
          Financial Platform
        </Typography>
      </Toolbar>
      <List sx={{ px: 1 }}>
        {Object.entries(groupedMenuItems).map(([category, items]) => (
          <div key={category}>
            {category === 'main' ? (
              // Dashboard gets special treatment - no section header
              items.map((item) => (
                <ListItem key={item.text} disablePadding sx={{ mb: 1 }}>
                  <ListItemButton
                    selected={location.pathname === item.path}
                    onClick={() => handleNavigation(item.path)}
                    sx={{
                      borderRadius: 1,
                      '&.Mui-selected': {
                        backgroundColor: theme.palette.primary.main + '20',
                        '& .MuiListItemIcon-root': {
                          color: theme.palette.primary.main,
                        },
                        '& .MuiListItemText-primary': {
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
                    sx={{ 
                      py: 0.5,
                      '&:hover': { backgroundColor: 'transparent' }
                    }}
                  >
                    <ListItemText 
                      primary={sectionTitles[category]} 
                      primaryTypographyProps={{
                        variant: 'subtitle2',
                        fontWeight: 600,
                        color: 'text.secondary',
                        textTransform: 'uppercase',
                        letterSpacing: 0.5
                      }}
                    />
                    {expandedSections[category] ? <ExpandLess /> : <ExpandMore />}
                  </ListItemButton>
                </ListItem>
                
                {/* Section Items */}
                <Collapse in={expandedSections[category]} timeout="auto" unmountOnExit>
                  {items.map((item) => (
                    <ListItem key={item.text} disablePadding sx={{ pl: 2 }}>
                      <ListItemButton
                        selected={location.pathname === item.path}
                        onClick={() => handleNavigation(item.path)}
                        sx={{
                          borderRadius: 1,
                          py: 0.5,
                          '&.Mui-selected': {
                            backgroundColor: theme.palette.primary.main + '20',
                            '& .MuiListItemIcon-root': {
                              color: theme.palette.primary.main,
                            },
                            '& .MuiListItemText-primary': {
                              color: theme.palette.primary.main,
                              fontWeight: 600,
                            },
                          },
                        }}
                      >
                        <ListItemIcon sx={{ minWidth: 36 }}>
                          {item.icon}
                        </ListItemIcon>
                        <ListItemText 
                          primary={item.text}
                          primaryTypographyProps={{
                            variant: 'body2'
                          }}
                        />
                      </ListItemButton>
                    </ListItem>
                  ))}
                </Collapse>
                <Divider sx={{ my: 1 }} />
              </>
            )}
          </div>
        ))}
      </List>
    </div>
  )

  return (
    <Box sx={{ display: 'flex' }}>
      {/* App Bar */}
      <AppBar
        position="fixed"
        sx={{
          width: { md: `calc(100% - ${drawerWidth}px)` },
          ml: { md: `${drawerWidth}px` },
          backgroundColor: 'white',
          color: 'text.primary',
          boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
        }}
      >
        <Toolbar>
          <IconButton
            color="inherit"
            aria-label="open drawer"
            edge="start"
            onClick={handleDrawerToggle}
            sx={{ mr: 2, display: { md: 'none' } }}
          >
            <MenuIcon />
          </IconButton>
          
          <Typography variant="h6" noWrap component="div" sx={{ flexGrow: 1 }}>
            {getPageTitle(location.pathname)}
          </Typography>
          
          <Box sx={{ mr: 2 }}>
            <SystemHealthMonitor compact={true} showDetails={false} />
          </Box>
          
          {/* UNIFIED AUTH UI */}
          {isAuthenticated ? (
            <>
              <IconButton onClick={handleUserMenuOpen} size="large" edge="end" color="inherit">
                <Avatar sx={{ width: 32, height: 32, bgcolor: 'primary.main' }}>
                  {user?.username?.[0]?.toUpperCase() || 'U'}
                </Avatar>
              </IconButton>
              <Menu
                anchorEl={userMenuAnchor}
                open={Boolean(userMenuAnchor)}
                onClose={handleUserMenuClose}
                anchorOrigin={{
                  vertical: 'bottom',
                  horizontal: 'right',
                }}
                transformOrigin={{
                  vertical: 'top',
                  horizontal: 'right',
                }}
              >
                <MenuItem onClick={handleUserMenuClose}>
                  <AccountCircleIcon sx={{ mr: 1 }} />
                  {user?.username || 'User'}
                </MenuItem>
                <Divider />
                <MenuItem onClick={() => { handleUserMenuClose(); handleNavigation('/settings'); }}>
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
              onClick={() => handleSpecialRoute('/login')}
              sx={{ ml: 2 }}
            >
              Sign In
            </Button>
          )}
        </Toolbar>
      </AppBar>

      {/* Navigation Drawer */}
      <Box component="nav" sx={{ width: { md: drawerWidth }, flexShrink: { md: 0 } }}>
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={handleDrawerToggle}
          ModalProps={{
            keepMounted: true,
          }}
          sx={{
            display: { xs: 'block', md: 'none' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth },
          }}
        >
          {drawer}
        </Drawer>
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', md: 'block' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth },
          }}
          open
        >
          {drawer}
        </Drawer>
      </Box>

      {/* Main Content */}
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: 3,
          width: { md: `calc(100% - ${drawerWidth}px)` },
          backgroundColor: theme.palette.background.default,
          minHeight: '100vh',
        }}
      >
        <Toolbar />
        <Container maxWidth="xl">
          <ErrorBoundary>
            <Suspense fallback={<PageLoader />}>
              <Routes>
                {/* PUBLIC ROUTES */}
                {ROUTE_CONFIG.PUBLIC_ROUTES.map(route => (
                  <Route 
                    key={route.path} 
                    path={route.path} 
                    element={renderRouteComponent(route)} 
                  />
                ))}
                
                {/* PROTECTED ROUTES */}
                {ROUTE_CONFIG.PROTECTED_ROUTES.map(route => (
                  <Route 
                    key={route.path} 
                    path={route.path} 
                    element={renderRouteComponent(route)} 
                  />
                ))}
              </Routes>
            </Suspense>
          </ErrorBoundary>
        </Container>
      </Box>
      
      {/* UNIFIED AUTH MODAL */}
      <AuthModal
        open={authModalOpen}
        onClose={closeAuthModal}
      />
    </Box>
  )
}

// Root App with Navigation Provider
function App() {
  return (
    <NavigationProvider>
      <AppContent />
    </NavigationProvider>
  );
}

export default App