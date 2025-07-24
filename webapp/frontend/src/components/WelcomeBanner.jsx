import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  IconButton,
  Collapse,
  Grid,
  Chip,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  useTheme,
  alpha
} from '@mui/material';
import {
  Close,
  CheckCircle,
  TrendingUp,
  AccountBalance,
  Analytics,
  Security,
  AutoAwesome,
  ArrowForward
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

const WelcomeBanner = ({ user, isFirstTimeUser, onDismiss }) => {
  const theme = useTheme();
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(true);

  const quickActions = [
    {
      title: 'Set Up API Keys',
      description: 'Connect your broker account to start tracking your portfolio',
      icon: <Security />,
      path: '/settings',
      color: theme.palette.success.main
    },
    {
      title: 'Explore Markets',
      description: 'View real-time market data and discover investment opportunities',
      icon: <TrendingUp />,
      path: '/market',
      color: theme.palette.info.main
    },
    {
      title: 'Build Portfolio',
      description: 'Track your investments and analyze performance',
      icon: <AccountBalance />,
      path: '/portfolio',
      color: theme.palette.warning.main
    },
    {
      title: 'View Analytics',
      description: 'Access advanced analytics and trading insights',
      icon: <Analytics />,
      path: '/analytics',
      color: theme.palette.secondary.main
    }
  ];

  const features = [
    'Real-time market data and analytics',
    'Portfolio tracking and optimization',
    'Advanced trading signals and alerts',
    'Secure API key management',
    'Comprehensive performance reporting'
  ];

  if (!expanded) return null;

  return (
    <Collapse in={expanded} timeout={300}>
      <Card
        sx={{
          mb: 3,
          background: `linear-gradient(135deg, 
            ${alpha(theme.palette.primary.main, 0.1)} 0%, 
            ${alpha(theme.palette.secondary.main, 0.05)} 100%)`,
          border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`,
          borderRadius: 3,
          position: 'relative',
          overflow: 'hidden'
        }}
      >
        {/* Background Pattern */}
        <Box
          sx={{
            position: 'absolute',
            top: 0,
            right: 0,
            width: '300px',
            height: '100%',
            opacity: 0.05,
            background: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Cpath d='M20 20h60v60H20z' fill='none' stroke='%23${theme.palette.primary.main.replace('#', '')}' stroke-width='2'/%3E%3Cpath d='M30 30l40 40M70 30L30 70' stroke='%23${theme.palette.primary.main.replace('#', '')}' stroke-width='1'/%3E%3C/svg%3E")`,
            backgroundRepeat: 'repeat',
            backgroundSize: '50px 50px'
          }}
        />

        <CardContent sx={{ p: 4, position: 'relative', zIndex: 1 }}>
          <Box display="flex" justifyContent="space-between" alignItems="flex-start" mb={3}>
            <Box display="flex" alignItems="center">
              <AutoAwesome 
                sx={{ 
                  fontSize: 40, 
                  color: theme.palette.primary.main, 
                  mr: 2,
                  animation: 'pulse 2s infinite'
                }} 
              />
              <Box>
                <Typography variant="h4" fontWeight="bold" color="primary">
                  Welcome{isFirstTimeUser ? '' : ' back'}, {user?.firstName || user?.username}! 🎉
                </Typography>
                <Typography variant="h6" color="text.secondary">
                  {isFirstTimeUser 
                    ? 'Get started with your financial dashboard'
                    : 'Your personalized dashboard is ready'
                  }
                </Typography>
              </Box>
            </Box>
            <IconButton
              onClick={() => {
                setExpanded(false);
                setTimeout(onDismiss, 300);
              }}
              size="small"
              sx={{ 
                bgcolor: alpha(theme.palette.background.paper, 0.8),
                '&:hover': {
                  bgcolor: alpha(theme.palette.background.paper, 0.9)
                }
              }}
            >
              <Close />
            </IconButton>
          </Box>

          {isFirstTimeUser && (
            <>
              <Box mb={3}>
                <Typography variant="body1" paragraph>
                  Your account has been successfully created! Here's what you can do with your new financial dashboard:
                </Typography>
                
                <Grid container spacing={1} mb={2}>
                  {features.map((feature, index) => (
                    <Grid item xs={12} sm={6} key={index}>
                      <Box display="flex" alignItems="center">
                        <CheckCircle 
                          sx={{ 
                            color: theme.palette.success.main, 
                            fontSize: 16, 
                            mr: 1 
                          }} 
                        />
                        <Typography variant="body2" color="text.secondary">
                          {feature}
                        </Typography>
                      </Box>
                    </Grid>
                  ))}
                </Grid>
              </Box>

              <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
                🚀 Quick Start Actions
              </Typography>
              
              <Grid container spacing={2} mb={3}>
                {quickActions.map((action, index) => (
                  <Grid item xs={12} sm={6} md={3} key={index}>
                    <Card
                      sx={{
                        cursor: 'pointer',
                        transition: 'all 0.3s ease',
                        height: '100%',
                        '&:hover': {
                          transform: 'translateY(-4px)',
                          boxShadow: theme.shadows[8]
                        }
                      }}
                      onClick={() => navigate(action.path)}
                    >
                      <CardContent sx={{ p: 2, textAlign: 'center', height: '100%', display: 'flex', flexDirection: 'column' }}>
                        <Box
                          sx={{
                            width: 48,
                            height: 48,
                            borderRadius: 2,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            backgroundColor: alpha(action.color, 0.1),
                            color: action.color,
                            mx: 'auto',
                            mb: 1
                          }}
                        >
                          {action.icon}
                        </Box>
                        <Typography variant="subtitle2" fontWeight="bold" mb={1}>
                          {action.title}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" flexGrow={1}>
                          {action.description}
                        </Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                ))}
              </Grid>
            </>
          )}

          <Box display="flex" gap={2} alignItems="center" flexWrap="wrap">
            <Button
              variant="contained"
              size="large"
              endIcon={<ArrowForward />}
              onClick={() => navigate('/settings')}
              sx={{
                borderRadius: 2,
                px: 3,
                background: `linear-gradient(45deg, ${theme.palette.primary.main}, ${theme.palette.secondary.main})`,
                '&:hover': {
                  background: `linear-gradient(45deg, ${theme.palette.primary.dark}, ${theme.palette.secondary.dark})`,
                  transform: 'translateY(-1px)',
                  boxShadow: theme.shadows[6]
                },
                transition: 'all 0.3s ease'
              }}
            >
              {isFirstTimeUser ? 'Complete Setup' : 'Manage Settings'}
            </Button>
            
            <Button
              variant="outlined"
              size="large"
              onClick={() => navigate('/market')}
              sx={{
                borderRadius: 2,
                px: 3,
                '&:hover': {
                  transform: 'translateY(-1px)',
                  boxShadow: theme.shadows[4]
                },
                transition: 'all 0.3s ease'
              }}
            >
              Explore Markets
            </Button>

            <Box display="flex" gap={1} ml="auto">
              <Chip 
                label={isFirstTimeUser ? "New User" : "Welcome Back"} 
                color="primary" 
                size="small" 
              />
              <Chip 
                label="Pro Features Unlocked" 
                variant="outlined" 
                size="small" 
              />
            </Box>
          </Box>
        </CardContent>
      </Card>
    </Collapse>
  );
};

export default WelcomeBanner;