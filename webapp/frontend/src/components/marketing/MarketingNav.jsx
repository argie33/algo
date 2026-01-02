import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  AppBar,
  Toolbar,
  Box,
  Button,
  Container,
  IconButton,
  Menu,
  MenuItem,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  useTheme,
  useMediaQuery,
  Typography,
} from '@mui/material';
import {
  Menu as MenuIcon,
  Close as CloseIcon,
  Launch as LaunchIcon,
} from '@mui/icons-material';

const MarketingNav = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navItems = [
    { label: 'Home', path: '/' },
    { label: 'Firm', path: '/firm' },
    { label: 'Services', path: '/services' },
    { label: 'Research', path: '/research' },
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
          width: 250,
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
            <ListItem key={item.path} disablePadding>
              <ListItemButton
                selected={isActive(item.path)}
                onClick={() => handleNavClick(item.path)}
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
              </ListItemButton>
            </ListItem>
          ))}
          <ListItem sx={{ mt: 2 }}>
            <Button
              variant="contained"
              fullWidth
              endIcon={<LaunchIcon />}
              onClick={() => {
                navigate('/app/market');
                setMobileMenuOpen(false);
              }}
            >
              Enter App
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
                {navItems.map((item) => (
                  <Button
                    key={item.path}
                    color={isActive(item.path) ? 'primary' : 'inherit'}
                    onClick={() => handleNavClick(item.path)}
                    sx={{
                      fontWeight: isActive(item.path) ? 600 : 500,
                      fontSize: '0.95rem',
                      position: 'relative',
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
                        width: '100%',
                      },
                    }}
                  >
                    {item.label}
                  </Button>
                ))}
              </Box>
            )}

            {/* Desktop CTA Button */}
            {!isMobile && (
              <Button
                variant="contained"
                endIcon={<LaunchIcon />}
                onClick={() => navigate('/app/market')}
                sx={{
                  borderRadius: 1,
                  textTransform: 'none',
                  fontSize: '0.95rem',
                  fontWeight: 600,
                  whiteSpace: 'nowrap',
                }}
              >
                Enter App
              </Button>
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
