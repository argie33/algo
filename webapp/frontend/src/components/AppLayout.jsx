/**
 * AppLayout — Bullseye Trading platform shell
 *
 * Light-theme-default platform shell (Stripe / Koyfin / IBM Carbon aesthetic),
 * with dark mode optional via toggle. Per FRONTEND_DESIGN_SYSTEM.md, retail/
 * end-customer fintech defaults light (NN/g + Apple HIG + finance industry
 * convention).
 *
 * Sleek left nav, header status bar with live market exposure indicator,
 * footer with build info. All visual tokens come from algoTheme.js's `C` proxy
 * which resolves to the active palette (light or dark).
 */

import React, { useState, useMemo, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  AppBar, Box, Toolbar, Typography, Drawer, List, ListItem, ListItemButton,
  ListItemIcon, ListItemText, IconButton, useMediaQuery, useTheme as useMuiTheme,
  Button, Menu, MenuItem, Divider, Chip, Tooltip, Snackbar, Alert,
} from '@mui/material';
import {
  Menu as MenuIcon, Settings as SettingsIcon, Stars,
  TrendingUp as TrendingUpIcon, Business as BusinessIcon, Public as PublicIcon,
  Event as EventIcon, Timeline as TimelineIcon,
  Psychology as PsychologyIcon, Analytics as AnalyticsIcon,
  HealthAndSafety as HealthAndSafetyIcon, Storage as StorageIcon,
  AccountCircle as AccountCircleIcon, Login as LoginIcon, Logout as LogoutIcon,
  SwapHoriz as SwapHorizIcon, Home as HomeIcon, Grain as GrainIcon,
  ShieldOutlined, Dashboard as DashboardIcon, FiberManualRecord,
  AutoGraph, Bolt, AccountBalance,
} from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';
import { api } from '../services/api';
import { C, F, S, tierColor, pnlColor } from '../theme/algoTheme';
import { StatusDot } from './ui/AlgoUI';

const drawerWidth = S.navWidth;

// ============================================================================
// NAVIGATION STRUCTURE
// ============================================================================
const navSections = [
  {
    title: 'Markets',
    items: [
      { text: 'Market Overview', icon: <TrendingUpIcon />, path: '/app/market' },
      { text: 'Sector Analysis', icon: <BusinessIcon />, path: '/app/sectors' },
      { text: 'Sentiment', icon: <PsychologyIcon />, path: '/app/sentiment' },
      { text: 'Economic Data', icon: <PublicIcon />, path: '/app/economic' },
      { text: 'Commodities', icon: <GrainIcon />, path: '/app/commodities' },
    ],
  },
  {
    title: 'Stocks',
    items: [
      { text: 'Stock Scores', icon: <Stars />, path: '/app/scores' },
      { text: 'Trading Signals', icon: <Bolt />, path: '/app/trading-signals' },
      { text: 'Deep Value Picks', icon: <AccountBalance />, path: '/app/deep-value' },
      { text: 'ETF Signals', icon: <AnalyticsIcon />, path: '/app/etf-signals' },
    ],
  },
  {
    title: 'Portfolio & Trading',
    items: [
      { text: 'Portfolio', icon: <SwapHorizIcon />, path: '/app/portfolio' },
      { text: 'Trade Tracker', icon: <TimelineIcon />, path: '/app/trades' },
      { text: 'Optimizer', icon: <Stars />, path: '/app/optimizer' },
      { text: 'Hedge Helper', icon: <BusinessIcon />, path: '/app/hedge-helper' },
    ],
  },
  {
    title: 'Research',
    items: [
      { text: 'Backtests', icon: <AutoGraph />, path: '/app/backtests' },
    ],
  },
  {
    title: 'System',
    items: [
      { text: 'Service Health', icon: <HealthAndSafetyIcon />, path: '/app/health' },
    ],
  },
];

// ============================================================================
// MAIN COMPONENT
// ============================================================================
const AppLayout = ({ children, pageTitle }) => {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [userMenuAnchor, setUserMenuAnchor] = useState(null);
  const [exposure, setExposure] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [activeNotif, setActiveNotif] = useState(null);

  const muiTheme = useMuiTheme();
  const isMobile = useMediaQuery(muiTheme.breakpoints.down('md'));
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, user, logout } = useAuth();

  // Poll market exposure + notifications every 30s
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const [expRes, notifRes] = await Promise.all([
          api.get('/algo/markets').catch(() => null),
          api.get('/algo/notifications').catch(() => null),
        ]);
        if (expRes?.data?.success) {
          setExposure(expRes.data.data?.current);
        }
        if (notifRes?.data?.success) {
          const newNotifs = notifRes.data.items || [];
          setNotifications(newNotifs);
          // Show the highest-severity unseen notification
          if (newNotifs.length > 0 && !activeNotif) {
            setActiveNotif(newNotifs[0]);
          }
        }
      } catch (e) {
        // Silent fail — header just won't show fresh status
      }
    };
    fetchStatus();
    const id = setInterval(fetchStatus, 30000);
    return () => clearInterval(id);
  }, []);

  const handleDrawerToggle = () => setMobileOpen(!mobileOpen);
  const handleUserMenuOpen = (e) => setUserMenuAnchor(e.currentTarget);
  const handleUserMenuClose = () => setUserMenuAnchor(null);
  const handleLogout = async () => { handleUserMenuClose(); await logout(); };
  const handleNavigation = (path) => {
    navigate(path);
    if (isMobile) setMobileOpen(false);
  };

  const dismissNotif = async () => {
    if (activeNotif?.id) {
      try {
        await api.post('/algo/notifications/seen', { ids: [activeNotif.id] });
      } catch (e) {}
    }
    setActiveNotif(null);
  };

  // ============================================================================
  // DRAWER (left nav)
  // ============================================================================
  const drawer = (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', bgcolor: C.bgElev }}>
      {/* Brand — sleek, refined */}
      <Box sx={{
        px: 2.5, py: 2, borderBottom: `1px solid ${C.border}`,
        cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 1.5,
        background: `linear-gradient(135deg, ${C.bgElev} 0%, ${C.brandTint} 100%)`,
        '&:hover': {
          background: `linear-gradient(135deg, ${C.brandTint} 0%, ${C.brandSoft} 100%)`,
        },
        transition: 'background 200ms ease',
      }} onClick={() => handleNavigation('/')}>
        <Box sx={{
          width: 36, height: 36, borderRadius: 2,
          background: `linear-gradient(135deg, ${C.brand} 0%, ${C.brandDark} 100%)`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: `0 4px 12px ${C.brand}40`,
        }}>
          <ShieldOutlined sx={{ fontSize: 22, color: '#fff' }} />
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{
            fontWeight: F.weight.black, fontSize: F.xl, color: C.textBright,
            letterSpacing: '-0.03em', lineHeight: 1, fontFamily: F.sans,
          }}>
            BULLSEYE
          </Typography>
          <Typography sx={{
            fontSize: F.xxs, color: C.textDim,
            letterSpacing: '0.12em', textTransform: 'uppercase',
            fontWeight: F.weight.semibold, mt: 0.25,
          }}>
            Swing Trading
          </Typography>
        </Box>
      </Box>

      {/* Nav sections */}
      <Box sx={{ flex: 1, overflowY: 'auto', pt: 1, pb: 2 }}>
        {navSections.map((section) => (
          <Box key={section.title} sx={{ mb: 2 }}>
            <Typography sx={{
              ...F.overline, color: C.textFaint, px: 2, py: 0.5, fontSize: F.xxs,
            }}>
              {section.title}
            </Typography>
            <List dense disablePadding>
              {section.items.map((item) => {
                const selected = location.pathname === item.path ||
                                 location.pathname.startsWith(item.path + '/');
                return (
                  <ListItem key={item.text} disablePadding>
                    <ListItemButton
                      selected={selected}
                      onClick={() => handleNavigation(item.path)}
                      sx={{
                        mx: 1, borderRadius: 1, py: 0.5,
                        '&.Mui-selected': {
                          bgcolor: item.accent === 'brand'
                            ? `${C.brand}25`
                            : `${C.blue}25`,
                          color: item.accent === 'brand' ? C.brand : C.blue,
                          '& .MuiListItemIcon-root': {
                            color: item.accent === 'brand' ? C.brand : C.blue,
                          },
                        },
                        '&:hover': {
                          bgcolor: `${C.cardAlt}`,
                        },
                      }}
                    >
                      <ListItemIcon sx={{ minWidth: 32, color: selected ? undefined : C.textDim }}>
                        {React.cloneElement(item.icon, { sx: { fontSize: 18 } })}
                      </ListItemIcon>
                      <ListItemText
                        primary={item.text}
                        primaryTypographyProps={{
                          sx: {
                            fontSize: F.sm,
                            fontWeight: selected ? F.weight.semibold : F.weight.regular,
                            color: selected
                              ? (item.accent === 'brand' ? C.brand : C.blue)
                              : C.text,
                          },
                        }}
                      />
                    </ListItemButton>
                  </ListItem>
                );
              })}
            </List>
          </Box>
        ))}
      </Box>

      {/* User box at bottom — click to open user menu (settings / sign out) */}
      <Box
        onClick={isAuthenticated ? handleUserMenuOpen : null}
        sx={{
          borderTop: `1px solid ${C.border}`,
          px: 2, py: 1.5,
          bgcolor: C.bgElev,
          cursor: isAuthenticated ? 'pointer' : 'default',
          display: 'flex', alignItems: 'center', gap: 1.5,
          transition: 'background 150ms',
          '&:hover': isAuthenticated ? { bgcolor: C.cardAlt } : undefined,
        }}
      >
        {isAuthenticated ? (
          <>
            <Box sx={{
              width: 32, height: 32, borderRadius: '50%',
              bgcolor: C.brandSoft, color: C.brand,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontWeight: F.weight.bold, fontSize: F.sm,
              border: `1px solid ${C.brand}30`, flexShrink: 0,
            }}>
              {(user?.email || user?.username || '?')[0].toUpperCase()}
            </Box>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography sx={{
                fontSize: F.sm, fontWeight: F.weight.semibold, color: C.textBright,
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              }}>
                {user?.email || user?.username || 'Account'}
              </Typography>
              <Typography sx={{ fontSize: F.xxs, color: C.textDim }}>
                Signed in · click for settings
              </Typography>
            </Box>
            <SettingsIcon sx={{ fontSize: 16, color: C.textFaint, flexShrink: 0 }} />
          </>
        ) : (
          <Button
            fullWidth variant="contained"
            startIcon={<LoginIcon />}
            onClick={() => handleNavigation('/login')}
            sx={{
              bgcolor: C.brand, color: '#fff', textTransform: 'none',
              fontSize: F.sm, fontWeight: F.weight.semibold, py: 0.75,
              '&:hover': { bgcolor: C.brandDark },
            }}
          >
            Sign In
          </Button>
        )}
      </Box>
    </Box>
  );

  // ============================================================================
  // HEADER STATUS BAR (right side)
  // ============================================================================
  // Only show exposure chip when we have real data — no placeholder pills.
  const exposureChip = exposure ? (
    <Tooltip title={`Market exposure: ${exposure.exposure_pct}% (${exposure.regime?.replace(/_/g, ' ')})`}>
      <Chip
        size="small"
        label={`EXP ${exposure.exposure_pct}%`}
        sx={{
          bgcolor: tierColor(exposure.regime?.replace(/uptrend_under_pressure/, 'pressure')),
          color: 'white', fontWeight: F.weight.bold, fontFamily: F.mono,
          fontSize: F.xs, letterSpacing: '0.05em',
        }}
      />
    </Tooltip>
  ) : null;

  const notifCount = notifications.length;

  // ============================================================================
  // RENDER
  // ============================================================================
  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: C.bg }}>
      {/* APP BAR (header) */}
      <AppBar
        position="fixed"
        elevation={0}
        sx={{
          width: { md: `calc(100% - ${drawerWidth}px)` },
          ml: { md: `${drawerWidth}px` },
          bgcolor: C.bgElev,
          borderBottom: `1px solid ${C.border}`,
          color: C.text,
        }}
      >
        <Toolbar sx={{ minHeight: '56px !important', px: 2 }}>
          <IconButton
            edge="start"
            onClick={handleDrawerToggle}
            sx={{ display: { md: 'none' }, mr: 2, color: C.text }}
          >
            <MenuIcon />
          </IconButton>

          <Typography sx={{
            color: C.textBright, fontWeight: F.weight.semibold, fontSize: F.md,
            letterSpacing: '-0.01em', flex: 1,
          }}>
            {pageTitle || ''}
          </Typography>

          {/* Status indicators */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {/* Market exposure pill — only when we have real data */}
            {exposureChip}

            {/* Notifications badge */}
            {notifCount > 0 && (
              <Tooltip title={`${notifCount} unseen notification${notifCount > 1 ? 's' : ''}`}>
                <Chip
                  size="small"
                  label={`! ${notifCount}`}
                  sx={{
                    bgcolor: C.bear, color: 'white', fontWeight: F.weight.bold,
                    fontFamily: F.mono, fontSize: F.xs,
                  }}
                  onClick={() => setActiveNotif(notifications[0])}
                />
              </Tooltip>
            )}

            <Divider orientation="vertical" flexItem sx={{ borderColor: C.border, mx: 0.5 }} />

            {/* User menu */}
            {isAuthenticated ? (
              <>
                <IconButton onClick={handleUserMenuOpen} sx={{ color: C.text, p: 0.5 }}>
                  <AccountCircleIcon />
                </IconButton>
                <Menu
                  anchorEl={userMenuAnchor}
                  open={Boolean(userMenuAnchor)}
                  onClose={handleUserMenuClose}
                  PaperProps={{ sx: { bgcolor: C.card, color: C.text, border: `1px solid ${C.border}` } }}
                >
                  <MenuItem disabled>
                    <Typography sx={{ fontSize: F.xs, color: C.textDim }}>
                      {user?.email || 'Signed in'}
                    </Typography>
                  </MenuItem>
                  <Divider sx={{ borderColor: C.border }} />
                  <MenuItem onClick={() => { handleNavigation('/app/settings'); handleUserMenuClose(); }}>
                    <SettingsIcon sx={{ mr: 1, fontSize: 18, color: C.textDim }} /> Settings
                  </MenuItem>
                  <MenuItem onClick={handleLogout}>
                    <LogoutIcon sx={{ mr: 1, fontSize: 18, color: C.textDim }} /> Logout
                  </MenuItem>
                </Menu>
              </>
            ) : (
              <Button
                size="small"
                startIcon={<LoginIcon />}
                onClick={() => navigate('/login')}
                sx={{
                  color: C.text, textTransform: 'none', fontSize: F.sm,
                  '&:hover': { bgcolor: C.cardAlt },
                }}
              >
                Login
              </Button>
            )}
          </Box>
        </Toolbar>
      </AppBar>

      {/* DRAWER */}
      <Box component="nav" sx={{ width: { md: drawerWidth }, flexShrink: { md: 0 } }}>
        {/* Mobile drawer */}
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={handleDrawerToggle}
          ModalProps={{ keepMounted: true }}
          sx={{
            display: { xs: 'block', md: 'none' },
            '& .MuiDrawer-paper': {
              boxSizing: 'border-box', width: drawerWidth, bgcolor: C.bgElev,
              borderRight: `1px solid ${C.border}`,
            },
          }}
        >
          {drawer}
        </Drawer>
        {/* Desktop drawer (permanent) */}
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', md: 'block' },
            '& .MuiDrawer-paper': {
              boxSizing: 'border-box', width: drawerWidth, bgcolor: C.bgElev,
              borderRight: `1px solid ${C.border}`,
            },
          }}
          open
        >
          {drawer}
        </Drawer>
      </Box>

      {/* MAIN CONTENT */}
      <Box component="main" sx={{
        flexGrow: 1, width: { md: `calc(100% - ${drawerWidth}px)` },
        minHeight: '100vh', bgcolor: C.bg, color: C.text,
      }}>
        <Toolbar sx={{ minHeight: '56px !important' }} /> {/* spacer */}
        {children}
      </Box>

      {/* NOTIFICATION TOAST */}
      {activeNotif && (
        <Snackbar
          open
          autoHideDuration={activeNotif.severity === 'critical' ? null : 8000}
          onClose={dismissNotif}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        >
          <Alert
            severity={
              activeNotif.severity === 'critical' || activeNotif.severity === 'error'
                ? 'error'
                : activeNotif.severity === 'warning' ? 'warning' : 'info'
            }
            onClose={dismissNotif}
            variant="filled"
            sx={{ minWidth: 320, fontFamily: F.body }}
          >
            <Typography sx={{ fontWeight: F.weight.bold }}>{activeNotif.title}</Typography>
            {activeNotif.message && (
              <Typography sx={{ fontSize: F.sm, mt: 0.5 }}>{activeNotif.message}</Typography>
            )}
          </Alert>
        </Snackbar>
      )}
    </Box>
  );
};

export default AppLayout;
