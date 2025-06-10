import React, { useState } from 'react'
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
  useMediaQuery
} from '@mui/material'
import {
  Menu as MenuIcon,
  Dashboard as DashboardIcon,
  TrendingUp as TrendingUpIcon,
  Assessment as AssessmentIcon,
  FilterList as FilterListIcon,
  Business as BusinessIcon,
  Timeline as TimelineIcon,
  Person as PersonIcon
} from '@mui/icons-material'
import { useNavigate, useLocation } from 'react-router-dom'

// Pages
import Dashboard from './pages/Dashboard'
import StockList from './pages/StockList'
import StockDetail from './pages/StockDetail'
import MarketOverview from './pages/MarketOverview'
import StockScreener from './pages/StockScreener'
import TradingSignals from './pages/TradingSignals'
import AnalystInsights from './pages/AnalystInsights'

const drawerWidth = 240

const menuItems = [
  { text: 'Dashboard', icon: <DashboardIcon />, path: '/' },
  { text: 'Market Overview', icon: <TrendingUpIcon />, path: '/market' },
  { text: 'Stock List', icon: <BusinessIcon />, path: '/stocks' },
  { text: 'Stock Screener', icon: <FilterListIcon />, path: '/screener' },
  { text: 'Trading Signals', icon: <TimelineIcon />, path: '/trading' },
  { text: 'Analyst Insights', icon: <PersonIcon />, path: '/analysts' },
  { text: 'Analytics', icon: <AssessmentIcon />, path: '/analytics' },
]

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
            <Route path="/stocks" element={<StockList />} />
            <Route path="/stocks/:ticker" element={<StockDetail />} />
            <Route path="/stock/:ticker" element={<StockDetail />} />
            <Route path="/screener" element={<StockScreener />} />
            <Route path="/trading" element={<TradingSignals />} />
            <Route path="/analysts" element={<AnalystInsights />} />
            <Route path="/analytics" element={<Dashboard />} />
          </Routes>
        </Container>
      </Box>
    </Box>
  )
}

export default App
