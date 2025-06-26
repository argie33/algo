import React, { useState } from 'react'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
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
  Alert
} from '@mui/material'
import {
  Menu as MenuIcon,
  Dashboard as DashboardIcon,
  TrendingUp as TrendingUpIcon,
  Assessment as AssessmentIcon,
  FilterList as FilterListIcon,
  Business as BusinessIcon,
  Timeline as TimelineIcon,
  Person as PersonIcon,
  Event as EventIcon,
  Storage as StorageIcon,
  AccountBalance as AccountBalanceIcon,
  HealthAndSafety as HealthAndSafetyIcon,
  PlayArrow
} from '@mui/icons-material'

// All real page imports
import Dashboard from './pages/Dashboard'
import MarketOverview from './pages/MarketOverview'
import StockExplorer from './pages/StockExplorer'
import StockDetail from './pages/StockDetail'
import TechnicalAnalysis from './pages/TechnicalAnalysis'
import AnalystInsights from './pages/AnalystInsights'
import EarningsCalendar from './pages/EarningsCalendar'
import DataValidation from './pages/DataValidation'
import FinancialData from './pages/FinancialData'
import ServiceHealth from './pages/ServiceHealth'
import TechnicalHistory from './pages/TechnicalHistory'
import Backtest from './pages/Backtest'
import TradingSignals from './pages/TradingSignals'

const drawerWidth = 240

const menuItems = [
  { text: 'Dashboard', icon: <DashboardIcon />, path: '/' },
  { text: 'Market Overview', icon: <TrendingUpIcon />, path: '/market' },
  { text: 'Stock Explorer', icon: <FilterListIcon />, path: '/stocks' },
  { text: 'Financial Data', icon: <AccountBalanceIcon />, path: '/financial-data' },
  { text: 'Trading Signals', icon: <TimelineIcon />, path: '/trading' },
  { text: 'Technical Analysis', icon: <AssessmentIcon />, path: '/technical' },
  { text: 'Backtester', icon: <PlayArrow />, path: '/backtest' },
  { text: 'Analyst Insights', icon: <PersonIcon />, path: '/analysts' },
  { text: 'Earnings', icon: <EventIcon />, path: '/earnings' },
  { text: 'Service Health', icon: <HealthAndSafetyIcon />, path: '/service-health' },
]

// Global error boundary to catch and show errors
class GlobalErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }
  componentDidCatch(error, errorInfo) {
    // You can log errorInfo to a service here
    // eslint-disable-next-line no-console
    console.error('Global error boundary caught:', error, errorInfo)
  }
  render() {
    if (this.state.hasError) {
      return (
        <Box sx={{ p: 3 }}>
          <Alert severity="error" sx={{ mb: 2 }}>
            <Typography variant="h6">Application Error</Typography>
            <Typography variant="body2">
              The application encountered an error. Please refresh the page or contact support.
            </Typography>
            <details style={{ marginTop: '10px' }}>
              <summary>Error Details</summary>
              <pre style={{ fontSize: '12px', overflow: 'auto' }}>
                {this.state.error ? this.state.error.toString() : 'Unknown error'}
              </pre>
            </details>
          </Alert>
        </Box>
      )
    }
    return this.props.children
  }
}

function App() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('md'))
  const navigate = useNavigate()
  const location = useLocation()

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen)
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
    <GlobalErrorBoundary>
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
              <Route path="/market" element={<MarketOverview />} />
              <Route path="/stocks" element={<StockExplorer />} />
              <Route path="/stocks/:ticker" element={<StockDetail />} />
              <Route path="/screener" element={<StockExplorer />} />
              <Route path="/trading" element={<TradingSignals />} />
              <Route path="/technical" element={<TechnicalAnalysis />} />
              <Route path="/analysts" element={<AnalystInsights />} />
              <Route path="/earnings" element={<EarningsCalendar />} />
              <Route path="/backtest" element={<Backtest />} />
              <Route path="/data-validation" element={<DataValidation />} />
              <Route path="/financial-data" element={<FinancialData />} />
              <Route path="/service-health" element={<ServiceHealth />} />
              <Route path="/technical-history/:symbol" element={<TechnicalHistory />} />
            </Routes>
          </Container>
        </Box>
      </Box>
    </GlobalErrorBoundary>
  )
}

export default App
