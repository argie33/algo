// UNIFIED ROUTING ARCHITECTURE - Eliminates competing navigation systems
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
  CircularProgress
} from '@mui/material'
import {
  Menu as MenuIcon,
  Login as LoginIcon,
  Logout as LogoutIcon,
  AccountCircle as AccountCircleIcon,
  Settings as SettingsIcon,
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
const Portfolio = lazy(() => import('./pages/Portfolio'))
const Settings = lazy(() => import('./pages/Settings'))
// ... (keep all other lazy imports)

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

// Navigation menu items (kept from original)
const menuItems = [
  // ... (keep existing menu structure)
];

// Main App Component with Unified Navigation
function AppContent() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [userMenuAnchor, setUserMenuAnchor] = useState(null)
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

  // Render component for route
  const renderRouteComponent = (route) => {
    const Component = getComponentByName(route.component);
    
    return (
      <RouteGuard path={route.path}>
        <Component />
      </RouteGuard>
    );
  };

  return (
    <Box sx={{ display: 'flex' }}>
      {/* App Bar - Simplified */}
      <AppBar
        position="fixed"
        sx={{
          width: { md: `calc(100% - 240px)` },
          ml: { md: '240px' },
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
          
          {/* SIMPLIFIED AUTH UI */}
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

      {/* Navigation Drawer - Simplified */}
      <Box component="nav" sx={{ width: { md: 240 }, flexShrink: { md: 0 } }}>
        {/* Drawer content with unified navigation */}
      </Box>

      {/* Main Content */}
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: 3,
          width: { md: `calc(100% - 240px)` },
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
                
                {/* SPECIAL ROUTES - Handle via NavigationContext */}
                {ROUTE_CONFIG.SPECIAL_ROUTES.map(route => (
                  <Route 
                    key={route.path} 
                    path={route.path} 
                    element={<SpecialRouteHandler route={route} />}
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

// Special route handler for redirects and actions
const SpecialRouteHandler = ({ route }) => {
  const { handleSpecialRoute } = useNavigation();
  
  React.useEffect(() => {
    handleSpecialRoute(route.path);
  }, [route.path, handleSpecialRoute]);
  
  return null;
};

// Utility functions
const getPageTitle = (pathname) => {
  const route = [...ROUTE_CONFIG.PUBLIC_ROUTES, ...ROUTE_CONFIG.PROTECTED_ROUTES]
    .find(r => r.path === pathname);
  return route?.component || 'Financial Platform';
};

const getComponentByName = (componentName) => {
  const components = {
    Dashboard,
    MarketOverview,
    Portfolio,
    Settings,
    // ... map all lazy loaded components
  };
  return components[componentName] || (() => <div>Component not found</div>);
};

// Root App with Navigation Provider
function App() {
  return (
    <NavigationProvider>
      <AppContent />
    </NavigationProvider>
  );
}

export default App;