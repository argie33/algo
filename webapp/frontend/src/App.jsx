import React, { useState, useEffect } from 'react'
import { Routes, Route } from 'react-router-dom'
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
  Paper,
  Accordion,
  AccordionSummary,
  AccordionDetails
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
  ExpandMore as ExpandMoreIcon,
  BugReport as BugReportIcon
} from '@mui/icons-material'
import { useNavigate, useLocation } from 'react-router-dom'

// Pages
import Dashboard from './pages/Dashboard'
import StockDetail from './pages/StockDetail'
import MarketOverview from './pages/MarketOverview'
import StockExplorer from './pages/StockExplorer'
import TradingSignals from './pages/TradingSignals'
import TechnicalAnalysis from './pages/TechnicalAnalysis'
import AnalystInsights from './pages/AnalystInsights'
import EarningsCalendar from './pages/EarningsCalendar'
import DataValidation from './pages/DataValidation'
import FinancialData from './pages/FinancialData'

// API Service
import { testApiConnection } from './services/api'

// Debug Component
const DebugInfo = () => {
  const [apiTest, setApiTest] = useState(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    const testApi = async () => {
      try {
        // Test with current API URL
        const currentUrl = 'https://lzq5jfiv9b.execute-api.us-east-1.amazonaws.com/Prod'
        console.log('Testing current API URL:', currentUrl)
        
        const response = await fetch(`${currentUrl}/health`)
        const data = await response.json()
        
        setApiTest({
          success: true,
          currentUrl,
          status: response.status,
          data: data
        })
      } catch (error) {
        console.error('API Test Failed:', error)
        setApiTest({
          success: false,
          error: error.message,
          currentUrl: 'https://lzq5jfiv9b.execute-api.us-east-1.amazonaws.com/Prod'
        })
      } finally {
        setLoading(false)
      }
    }

    testApi()
  }, [])

  const envInfo = {
    VITE_API_URL: import.meta.env.VITE_API_URL,
    MODE: import.meta.env.MODE,
    DEV: import.meta.env.DEV,
    PROD: import.meta.env.PROD,
    BASE_URL: import.meta.env.BASE_URL,
    location: window.location.href
  }

  return (
    <Box sx={{ position: 'fixed', top: 0, right: 0, zIndex: 9999, width: 400, m: 1 }}>
      <Accordion>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <BugReportIcon sx={{ mr: 1 }} />
          <Typography variant="body2">
            Debug Info {apiTest?.success ? '✅' : apiTest?.success === false ? '❌' : '⏳'}
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Paper sx={{ p: 2, fontSize: '12px', fontFamily: 'monospace' }}>
            <Typography variant="subtitle2" gutterBottom>Environment:</Typography>
            <pre>{JSON.stringify(envInfo, null, 2)}</pre>
            
            <Typography variant="subtitle2" gutterBottom sx={{ mt: 2 }}>API Test:</Typography>
            <pre>
              {loading ? 'Testing API...' : JSON.stringify(apiTest, null, 2)}
            </pre>
          </Paper>
        </AccordionDetails>
      </Accordion>
    </Box>  )
}

const drawerWidth = 240

const menuItems = [
  { text: 'Dashboard', icon: <DashboardIcon />, path: '/' },
  { text: 'Market Overview', icon: <TrendingUpIcon />, path: '/market' },
  { text: 'Stock Explorer', icon: <FilterListIcon />, path: '/stocks' },
  { text: 'Financial Data', icon: <AccountBalanceIcon />, path: '/financial-data' },
  { text: 'Trading Signals', icon: <TimelineIcon />, path: '/trading' },
  { text: 'Technical Analysis', icon: <AssessmentIcon />, path: '/technical' },
  { text: 'Analyst Insights', icon: <PersonIcon />, path: '/analysts' },
  { text: 'Earnings Calendar', icon: <EventIcon />, path: '/earnings' },
  { text: 'Data Validation', icon: <StorageIcon />, path: '/data-validation' },
]

// Error boundary component
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('App Error Boundary caught an error:', error, errorInfo)
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
  console.log('🚀 App component loading...');
  
  const [mobileOpen, setMobileOpen] = useState(false)
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('md'))
  const navigate = useNavigate()
  const location = useLocation()

  console.log('✅ App component hooks initialized successfully');

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
    <ErrorBoundary>
      <DebugInfo />
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
          <Container maxWidth="xl">          <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/market" element={<MarketOverview />} />
              <Route path="/stocks" element={<StockExplorer />} />
              <Route path="/stocks/screen" element={<StockExplorer />} />
              <Route path="/stocks/:ticker" element={<StockDetail />} />
              <Route path="/stock/:ticker" element={<StockDetail />} />
              <Route path="/screener" element={<StockExplorer />} />
              <Route path="/trading" element={<TradingSignals />} />
              <Route path="/technical" element={<TechnicalAnalysis />} />
              <Route path="/analysts" element={<AnalystInsights />} />
              <Route path="/earnings" element={<EarningsCalendar />} />
              <Route path="/data-validation" element={<DataValidation />} />
              <Route path="/financial-data" element={<FinancialData />} />
            </Routes>
          </Container>
        </Box>
      </Box>
    </ErrorBoundary>
  )
}

export default App
