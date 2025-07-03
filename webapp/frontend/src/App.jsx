import React, { useState } from 'react'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary'
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
  Alert,
  Button,
  Menu,
  MenuItem,
  Avatar,
  Divider
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
  Security as SecurityIcon
} from '@mui/icons-material'

// All real page imports
import Dashboard from './pages/Dashboard'
import MarketOverview from './pages/MarketOverview'
import StockExplorer from './pages/StockExplorer'
import StockDetail from './pages/StockDetail'
import MetricsDashboard from './pages/MetricsDashboard'
import TechnicalAnalysis from './pages/TechnicalAnalysis'
import AnalystInsights from './pages/AnalystInsights'
import EarningsCalendar from './pages/EarningsCalendar'
import FinancialData from './pages/FinancialData'
import ServiceHealth from './pages/ServiceHealth'
import TechnicalHistory from './pages/TechnicalHistory'
import Backtest from './pages/Backtest'
import TradingSignals from './pages/TradingSignals'
import Portfolio from './pages/Portfolio'
import SentimentAnalysis from './pages/SentimentAnalysis'
import AdvancedScreener from './pages/AdvancedScreener'
import EconomicModeling from './pages/EconomicModeling'
import { useAuth } from './contexts/AuthContext'
import AuthModal from './components/auth/AuthModal'
import ProtectedRoute from './components/auth/ProtectedRoute'

const drawerWidth = 240

const menuItems = [
  { text: 'Dashboard', icon: <DashboardIcon />, path: '/' },
  { text: 'Portfolio', icon: <BusinessIcon />, path: '/portfolio' },
  { text: 'Market Overview', icon: <TrendingUpIcon />, path: '/market' },
  { text: 'Advanced Screener', icon: <SearchIcon />, path: '/screener-advanced' },
  { text: 'Stock Explorer', icon: <FilterListIcon />, path: '/stocks' },
  { text: 'Stock Metrics', icon: <AssessmentIcon />, path: '/metrics' },
  { text: 'Sentiment Analysis', icon: <PsychologyIcon />, path: '/sentiment' },
  { text: 'Economic Modeling', icon: <PublicIcon />, path: '/economic' },
  { text: 'Financial Data', icon: <AccountBalanceIcon />, path: '/financial-data' },
  { text: 'Trading Signals', icon: <TimelineIcon />, path: '/trading' },
  { text: 'Technical Analysis', icon: <AnalyticsIcon />, path: '/technical' },
  { text: 'Backtester', icon: <PlayArrow />, path: '/backtest' },
  { text: 'Analyst Insights', icon: <PersonIcon />, path: '/analysts' },
  { text: 'Earnings', icon: <EventIcon />, path: '/earnings' },
  { text: 'Service Health', icon: <HealthAndSafetyIcon />, path: '/service-health' },
]


function App() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [authModalOpen, setAuthModalOpen] = useState(false)
  const [userMenuAnchor, setUserMenuAnchor] = useState(null)
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('md'))
  const { isAuthenticated, user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

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
  }

  const handleNavigation = (path) => {
    navigate(path)
    if (isMobile) {
      setMobileOpen(false)
    }
  }

  const drawer = (
    <div>
      <Toolbar>
        <Typography variant="h6" noWrap component="div" sx={{ fontWeight: 700 }}>
          Financial Dashboard
        </Typography>
      </Toolbar>
      <List>
        {menuItems.map((item) => (
          <ListItem key={item.text} disablePadding>
            <ListItemButton
              selected={location.pathname === item.path}
              onClick={() => handleNavigation(item.path)}
              sx={{
                '&.Mui-selected': {
                  backgroundColor: theme.palette.primary.main + '20',
                  borderRight: `3px solid ${theme.palette.primary.main}`,
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
        ))}
      </List>
    </div>
  )

  return (
    <ErrorBoundary>
      <Box sx={{ display: 'flex' }}>
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
              {menuItems.find(item => item.path === location.pathname)?.text || 'Dashboard'}
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
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/portfolio" element={<Portfolio />} />
              <Route path="/market" element={<MarketOverview />} />
              <Route path="/screener-advanced" element={<AdvancedScreener />} />
              <Route path="/sentiment" element={<SentimentAnalysis />} />
              <Route path="/economic" element={<EconomicModeling />} />
              <Route path="/metrics" element={<MetricsDashboard />} />
              <Route path="/stocks" element={<StockExplorer />} />
              <Route path="/stocks/:ticker" element={<StockDetail />} />
              <Route path="/screener" element={<StockExplorer />} />
              <Route path="/trading" element={<TradingSignals />} />
              <Route path="/technical" element={<TechnicalAnalysis />} />
              <Route path="/analysts" element={<AnalystInsights />} />
              <Route path="/earnings" element={<EarningsCalendar />} />
              <Route path="/backtest" element={<Backtest />} />
              <Route path="/financial-data" element={<FinancialData />} />
              <Route path="/service-health" element={<ServiceHealth />} />
              <Route path="/technical-history/:symbol" element={<TechnicalHistory />} />
            </Routes>
          </Container>
        </Box>
        
        {/* Authentication Modal */}
        <AuthModal
          open={authModalOpen}
          onClose={() => setAuthModalOpen(false)}
        />
      </Box>
    </ErrorBoundary>
  )
}

export default App
