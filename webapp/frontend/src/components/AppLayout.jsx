import React, { useState, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
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
  Collapse,
} from '@mui/material';
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
  Analytics as AnalyticsIcon,
  HealthAndSafety as HealthAndSafetyIcon,
  Storage as StorageIcon,
  AccountCircle as AccountCircleIcon,
  Login as LoginIcon,
  Logout as LogoutIcon,
  SwapHoriz as SwapHorizIcon,
  Home as HomeIcon,
  Grain as GrainIcon,
} from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';

const drawerWidth = 240;

const menuItems = [
  // Markets Section
  {
    text: 'Market Overview',
    icon: <TrendingUpIcon />,
    path: '/app/market',
    category: 'markets',
  },
  {
    text: 'Sector Analysis',
    icon: <BusinessIcon />,
    path: '/app/sectors',
    category: 'markets',
  },
  {
    text: 'Commodities',
    icon: <GrainIcon />,
    path: '/app/commodities',
    category: 'markets',
  },
  {
    text: 'Economic Indicators',
    icon: <PublicIcon />,
    path: '/app/economic',
    category: 'markets',
  },

  // Stocks Section
  {
    text: 'Stock Scores',
    icon: <Stars />,
    path: '/app/scores',
    category: 'stocks',
    premium: true,
  },
  {
    text: 'Earnings Hub',
    icon: <EventIcon />,
    path: '/app/earnings',
    category: 'stocks',
  },
  {
    text: 'Financial Data',
    icon: <ShowChartIcon />,
    path: '/app/financial-data',
    category: 'stocks',
  },
  {
    text: 'Trading Signals',
    icon: <TimelineIcon />,
    path: '/app/trading-signals',
    category: 'stocks',
  },
  {
    text: 'ETF Trading Signals',
    icon: <AnalyticsIcon />,
    path: '/app/etf-trading-signals',
    category: 'stocks',
  },

  // Sentiment Analysis
  {
    text: 'Sentiment Analysis',
    icon: <PsychologyIcon />,
    path: '/app/sentiment',
    category: 'sentiment',
  },

  // Tools
  {
    text: 'Hedge Helper',
    icon: <HealthAndSafetyIcon />,
    path: '/app/hedge-helper',
    category: 'tools',
  },
];

const AppLayout = ({ children, pageTitle }) => {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [userMenuAnchor, setUserMenuAnchor] = useState(null);
  const [expandedSections, setExpandedSections] = useState({
    markets: true,
    stocks: true,
    sentiment: false,
    tools: false,
  });

  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, user, logout } = useAuth();

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

  const groupedMenuItems = useMemo(() => {
    return menuItems.reduce((acc, item) => {
      if (!acc[item.category]) {
        acc[item.category] = [];
      }
      acc[item.category].push(item);
      return acc;
    }, {});
  }, []);

  const sectionTitles = {
    main: 'Dashboard',
    markets: 'Markets',
    stocks: 'Stocks',
    sentiment: 'Sentiment Analysis',
    research: 'Research & Education',
    tools: 'Tools',
  };

  const drawer = (
    <div>
      <Toolbar>
        <Box
          onClick={() => {
            navigate('/');
            if (isMobile) setMobileOpen(false);
          }}
          sx={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 1 }}
        >
          <HomeIcon sx={{ color: 'primary.main' }} />
          <Typography
            variant="h6"
            noWrap
            component="div"
            sx={{ fontWeight: 700, color: 'primary.main', fontSize: '0.95rem' }}
          >
            Bullseye
          </Typography>
        </Box>
      </Toolbar>
      <List sx={{ px: 1 }}>
        {Object.entries(groupedMenuItems).map(([category, items]) => (
          <React.Fragment key={category}>
            {category === 'main' ? (
              (items || []).map((item) => (
                <ListItem key={item.text} disablePadding sx={{ mb: 1 }}>
                  <ListItemButton
                    selected={location.pathname === item.path}
                    onClick={() => handleNavigation(item.path, item.premium)}
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
                    <ListItemText
                      primary={item.text}
                      primaryTypographyProps={{
                        sx: { fontSize: '0.85rem' }
                      }}
                    />
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
                      '&:hover': { backgroundColor: 'transparent' },
                    }}
                  >
                    <ListItemText
                      primary={sectionTitles[category]}
                      primaryTypographyProps={{
                        sx: {
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          color: 'text.secondary',
                          textTransform: 'uppercase',
                          letterSpacing: 0.5,
                        },
                      }}
                    />
                    {expandedSections[category] ? <ExpandLess /> : <ExpandMore />}
                  </ListItemButton>
                </ListItem>

                {/* Section Items */}
                <Collapse
                  in={expandedSections[category]}
                  timeout="auto"
                  unmountOnExit
                >
                  <List component="div" disablePadding sx={{ pl: 1 }}>
                    {(items || []).map((item) => (
                      <ListItem key={item.text} disablePadding sx={{ mb: 1 }}>
                        <ListItemButton
                          selected={location.pathname === item.path}
                          onClick={() => handleNavigation(item.path, item.premium)}
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
                          <ListItemIcon sx={{ minWidth: 40 }}>
                            {item.icon}
                          </ListItemIcon>
                          <ListItemText
                            primary={item.text}
                            primaryTypographyProps={{
                              sx: { fontSize: '0.85rem' }
                            }}
                          />
                        </ListItemButton>
                      </ListItem>
                    ))}
                  </List>
                </Collapse>
              </>
            )}
          </React.Fragment>
        ))}
      </List>
    </div>
  );

  return (
    <Box sx={{ display: 'flex' }}>
      <AppBar
        position="fixed"
        sx={{
          width: { md: `calc(100% - ${drawerWidth}px)` },
          ml: { md: `${drawerWidth}px` },
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
            {pageTitle || 'Bullseye Financial'}
          </Typography>

          {/* User Menu */}
          {isAuthenticated ? (
            <>
              <IconButton
                onClick={handleUserMenuOpen}
                size="small"
                sx={{ ml: 2 }}
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
              sx={{ ml: 2 }}
              onClick={() => navigate('/')}
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
            keepMounted: true,
          }}
          sx={{
            display: { xs: 'block', md: 'none' },
            '& .MuiDrawer-paper': {
              boxSizing: 'border-box',
              width: drawerWidth,
            },
          }}
        >
          {drawer}
        </Drawer>
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', md: 'block' },
            '& .MuiDrawer-paper': {
              boxSizing: 'border-box',
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
          width: { xs: '100%', md: `calc(100% - ${drawerWidth}px)` },
          backgroundColor: theme.palette.background.default,
          minHeight: '100vh',
          overflowX: 'hidden',
        }}
      >
        <Toolbar />
        <Container maxWidth="xl" sx={{ px: { xs: 1, sm: 2, md: 3 } }}>
          {children}
        </Container>
      </Box>
    </Box>
  );
};

export default AppLayout;
