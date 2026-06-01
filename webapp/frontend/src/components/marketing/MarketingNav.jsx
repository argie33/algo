import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  AppBar,
  Toolbar,
  Box,
  Button,
  Container,
  IconButton,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  useTheme,
  useMediaQuery,
  Typography,
  Collapse,
  Divider,
  alpha,
} from '@mui/material';
import {
  Menu as MenuIcon,
  Close as CloseIcon,
  Launch as LaunchIcon,
  ExpandLess,
  ExpandMore,
} from '@mui/icons-material';

const MarketingNav = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [expandedMobileItem, setExpandedMobileItem] = useState(null);
  const [desktopMenuAnchor, setDesktopMenuAnchor] = useState(null);
  const [activeDesktopMenu, setActiveDesktopMenu] = useState(null);

  const navItems = [
    { label: 'Home', path: '/' },
    {
      label: 'Firm',
      path: '/firm',
      submenu: [
        { label: 'About', path: '/about' },
        { label: 'Our Team', path: '/our-team' },
        { label: 'Mission & Values', path: '/mission-values' },
      ]
    },
    {
      label: 'Services',
      submenu: [
        { label: 'Research & Insights', path: '/research-insights' },
        { label: 'Investment Tools', path: '/investment-tools' },
        { label: 'Wealth Management', path: '/wealth-management' },
      ]
    },
    { label: 'Contact', path: '/contact' },
  ];

  const isActive = (path) => location.pathname === path;

  const handleNavClick = (path) => {
    navigate(path);
    setMobileMenuOpen(false);
  };

  const mobileDrawer = (
    <Drawer
      anchor="right"
      open={mobileMenuOpen}
      onClose={() => setMobileMenuOpen(false)}
    >
      <Box
        sx={{
          width: 280,
          pt: 2,
        }}
      >
        <Box sx={{ display: 'flex', justifyContent: 'flex-end', pr: 2, mb: 2 }}>
          <IconButton onClick={() => setMobileMenuOpen(false)}>
            <CloseIcon />
          </IconButton>
        </Box>
        <List>
          {navItems.map((item) => (
            <React.Fragment key={item.label}>
              <ListItem disablePadding>
                <ListItemButton
                  selected={isActive(item.path)}
                  onClick={
                    item.submenu
                      ? () => setExpandedMobileItem(expandedMobileItem === item.label ? null : item.label)
                      : () => handleNavClick(item.path)
                  }
                  sx={{
                    '&.Mui-selected': {
                      backgroundColor: `${theme.palette.primary.main}20`,
                      '& .MuiListItemText-primary': {
                        color: theme.palette.primary.main,
                        fontWeight: 600,
                      },
                    },
                  }}
                >
                  <ListItemText primary={item.label} />
                  {item.submenu && (
                    expandedMobileItem === item.label ? <ExpandLess /> : <ExpandMore />
                  )}
                </ListItemButton>
              </ListItem>

              {/* Mobile Submenu */}
              {item.submenu && (
                <Collapse in={expandedMobileItem === item.label} timeout="auto" unmountOnExit>
                  <List component="div" disablePadding>
                    {item.submenu.map((subitem) => (
                      <ListItem key={subitem.label} disablePadding sx={{ pl: 4 }}>
                        <ListItemButton
                          onClick={() => {
                            handleNavClick(subitem.path);
                            setExpandedMobileItem(null);
                          }}
                          sx={{
                            fontSize: '0.9rem',
                          }}
                        >
                          <ListItemText primary={subitem.label} />
                        </ListItemButton>
                      </ListItem>
                    ))}
                  </List>
                </Collapse>
              )}
            </React.Fragment>
          ))}
          <Divider sx={{ my: 2 }} />
          <ListItem sx={{ mt: 1 }}>
            <Button
              variant="contained"
              fullWidth
              endIcon={<LaunchIcon />}
              onClick={() => {
                navigate('/app/markets');
                setMobileMenuOpen(false);
              }}
            >
              Launch Platform
            </Button>
          </ListItem>
        </List>
      </Box>
    </Drawer>
  );

  return (
    <>
      <AppBar
        position="sticky"
        elevation={0}
        sx={{
          borderBottom: `1px solid ${theme.palette.divider}`,
          backgroundColor: theme.palette.background.paper,
          backdropFilter: 'blur(8px)',
        }}
      >
        <Container maxWidth="xl">
          <Toolbar
            disableGutters
            sx={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              py: 1,
            }}
          >
            {/* Logo / Brand */}
            <Box
              onClick={() => navigate('/')}
              sx={{
                display: 'flex',
                alignItems: 'center',
                cursor: 'pointer',
                '&:hover': {
                  opacity: 0.8,
                },
              }}
            >
              <Typography
                variant="h6"
                sx={{
                  fontWeight: 700,
                  color: theme.palette.primary.main,
                  fontSize: { xs: '1.1rem', sm: '1.25rem' },
                }}
              >
                Bullseye
              </Typography>
              <Typography
                variant="h6"
                sx={{
                  fontWeight: 400,
                  color: theme.palette.text.secondary,
                  ml: 0.5,
                  fontSize: { xs: '0.9rem', sm: '1rem' },
                }}
              >
                Financial
              </Typography>
            </Box>

            {/* Desktop Navigation */}
            {!isMobile && (
              <Box
                sx={{
                  display: 'flex',
                  gap: 3,
                  alignItems: 'center',
                  flex: 1,
                  ml: 4,
                }}
              >
                {navItems.map((item, idx) => (
                  <Box key={item.label || idx} sx={{ position: 'relative' }}>
                    <Button
                      color={isActive(item.path) ? 'primary' : 'inherit'}
                      onClick={
                        item.submenu
                          ? (e) => {
                              setDesktopMenuAnchor(e.currentTarget);
                              setActiveDesktopMenu(item.label);
                            }
                          : () => handleNavClick(item.path)
                      }
                      onMouseEnter={
                        item.submenu
                          ? (e) => {
                              setDesktopMenuAnchor(e.currentTarget);
                              setActiveDesktopMenu(item.label);
                            }
                          : undefined
                      }
                      sx={{
                        fontWeight: isActive(item.path) ? 600 : 500,
                        fontSize: '0.95rem',
                        position: 'relative',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 0.5,
                        '&:after': {
                          content: '""',
                          position: 'absolute',
                          bottom: 0,
                          left: 0,
                          width: isActive(item.path) ? '100%' : '0%',
                          height: 2,
                          backgroundColor: theme.palette.primary.main,
                          transition: 'width 0.3s ease',
                        },
                        '&:hover:after': {
                          width: item.submenu ? '0%' : '100%',
                        },
                      }}
                    >
                      {item.label}
                      {item.submenu && (
                        <Box sx={{ fontSize: '0.65rem', ml: 0.5, opacity: 0.7 }}>&#9660;</Box>
                      )}
                    </Button>

                    {/* Desktop Dropdown Menu - CSS based, no MUI Modal */}
                    {item.submenu && activeDesktopMenu === item.label && (
                      <Box
                        onMouseLeave={() => {
                          setActiveDesktopMenu(null);
                          setDesktopMenuAnchor(null);
                        }}
                        sx={{
                          position: 'absolute',
                          top: '100%',
                          left: 0,
                          mt: 1,
                          minWidth: 200,
                          backgroundColor: theme.palette.background.paper,
                          border: `1px solid ${theme.palette.divider}`,
                          borderRadius: 1,
                          boxShadow: theme.shadows[8],
                          zIndex: 1200,
                        }}
                      >
                        {item.submenu.map((subitem) => (
                          <Box
                            key={subitem.label}
                            onClick={() => {
                              handleNavClick(subitem.path);
                              setActiveDesktopMenu(null);
                              setDesktopMenuAnchor(null);
                            }}
                            sx={{
                              px: 2,
                              py: 1,
                              fontSize: '0.9rem',
                              cursor: 'pointer',
                              '&:hover': {
                                backgroundColor: alpha(theme.palette.primary.main, 0.08),
                              },
                              '&:first-of-type': {
                                borderRadius: '4px 4px 0 0',
                              },
                              '&:last-of-type': {
                                borderRadius: '0 0 4px 4px',
                              },
                            }}
                          >
                            {subitem.label}
                          </Box>
                        ))}
                      </Box>
                    )}
                  </Box>
                ))}
              </Box>
            )}

            {/* Desktop CTA Buttons */}
            {!isMobile && (
              <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                <Button
                  variant="outlined"
                  onClick={() => navigate('/contact')}
                  sx={{
                    borderRadius: 1,
                    textTransform: 'none',
                    fontSize: '0.95rem',
                    fontWeight: 600,
                    whiteSpace: 'nowrap',
                    borderColor: theme.palette.primary.main,
                    color: theme.palette.primary.main,
                    '&:hover': {
                      backgroundColor: alpha(theme.palette.primary.main, 0.05),
                    },
                  }}
                >
                  Get in Touch
                </Button>
                <Button
                  variant="contained"
                  endIcon={<LaunchIcon />}
                  onClick={() => navigate('/app/markets')}
                  sx={{
                    borderRadius: 1,
                    textTransform: 'none',
                    fontSize: '0.95rem',
                    fontWeight: 600,
                    whiteSpace: 'nowrap',
                  }}
                >
                  Launch Platform
                </Button>
              </Box>
            )}

            {/* Mobile Menu Toggle */}
            {isMobile && (
              <IconButton
                onClick={() => setMobileMenuOpen(true)}
                sx={{ color: 'primary.main' }}
              >
                <MenuIcon />
              </IconButton>
            )}
          </Toolbar>
        </Container>
      </AppBar>
      {mobileDrawer}
    </>
  );
};

export default MarketingNav;

