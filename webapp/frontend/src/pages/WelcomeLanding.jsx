import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Container,
  Typography,
  Button,
  Card,
  CardContent,
  Grid,
  Chip,
  alpha,
  useTheme,
  IconButton,
  Fade,
  Slide
} from '@mui/material';
import {
  TrendingUp,
  Analytics,
  Security,
  Speed,
  AccountBalance,
  Timeline,
  Login as LoginIcon,
  ArrowForward,
  ShowChart,
  Assessment
} from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';

const WelcomeLanding = ({ onSignInClick }) => {
  const theme = useTheme();
  const navigate = useNavigate();
  const { isAuthenticated, user } = useAuth();
  const [animationStep, setAnimationStep] = useState(0);

  // Redirect authenticated users
  useEffect(() => {
    if (isAuthenticated && user) {
      navigate('/');
    }
  }, [isAuthenticated, user, navigate]);

  // Stagger animations
  useEffect(() => {
    const timer = setTimeout(() => setAnimationStep(1), 300);
    const timer2 = setTimeout(() => setAnimationStep(2), 600);
    const timer3 = setTimeout(() => setAnimationStep(3), 900);
    return () => {
      clearTimeout(timer);
      clearTimeout(timer2);
      clearTimeout(timer3);
    };
  }, []);

  const features = [
    {
      icon: <TrendingUp />,
      title: 'Real-Time Market Data',
      description: 'Live market feeds, real-time price updates, and comprehensive market analysis',
      color: theme.palette.success.main
    },
    {
      icon: <Analytics />,
      title: 'Advanced Analytics',
      description: 'AI-powered insights, technical analysis, and predictive modeling',
      color: theme.palette.info.main
    },
    {
      icon: <AccountBalance />,
      title: 'Portfolio Management',
      description: 'Track performance, optimize allocations, and manage risk effectively',
      color: theme.palette.warning.main
    },
    {
      icon: <Security />,
      title: 'Enterprise Security',
      description: 'Bank-grade encryption, secure authentication, and data protection',
      color: theme.palette.error.main
    },
    {
      icon: <Timeline />,
      title: 'Trading Signals',
      description: 'Algorithmic trading signals, backtesting, and strategy optimization',
      color: theme.palette.secondary.main
    },
    {
      icon: <Speed />,
      title: 'Lightning Fast',
      description: 'Sub-millisecond execution, real-time data processing, and instant insights',
      color: theme.palette.primary.main
    }
  ];

  const marketStats = [
    { label: 'S&P 500', value: '4,185.47', change: '+1.2%', positive: true },
    { label: 'NASDAQ', value: '12,888.96', change: '+0.8%', positive: true },
    { label: 'DOW JONES', value: '33,677.27', change: '-0.3%', positive: false },
    { label: 'BTC/USD', value: '$43,567.89', change: '+2.4%', positive: true }
  ];

  return (
    <Box
      sx={{
        minHeight: '100vh',
        background: `linear-gradient(135deg, 
          ${alpha(theme.palette.primary.main, 0.1)} 0%, 
          ${alpha(theme.palette.secondary.main, 0.05)} 100%)`,
        position: 'relative',
        overflow: 'hidden'
      }}
    >
      {/* Background Animation */}
      <Box
        sx={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          opacity: 0.1,
          background: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23${theme.palette.primary.main.replace('#', '')}' fill-opacity='0.3'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`,
        }}
      />

      <Container maxWidth="lg" sx={{ py: 8, position: 'relative', zIndex: 1 }}>
        {/* Hero Section */}
        <Fade in={true} timeout={800}>
          <Box textAlign="center" mb={8}>
            <Slide direction="down" in={animationStep >= 0} timeout={600}>
              <Typography
                variant="h2"
                component="h1"
                fontWeight="bold"
                sx={{
                  background: `linear-gradient(45deg, ${theme.palette.primary.main}, ${theme.palette.secondary.main})`,
                  backgroundClip: 'text',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  mb: 3
                }}
              >
                Welcome to Your Financial Future
              </Typography>
            </Slide>

            <Slide direction="up" in={animationStep >= 1} timeout={600}>
              <Typography
                variant="h5"
                color="text.secondary"
                sx={{ mb: 4, maxWidth: '600px', mx: 'auto' }}
              >
                Advanced analytics, real-time data, and intelligent insights to power your investment decisions
              </Typography>
            </Slide>

            <Slide direction="up" in={animationStep >= 2} timeout={600}>
              <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center', flexWrap: 'wrap' }}>
                <Button
                  variant="contained"
                  size="large"
                  startIcon={<LoginIcon />}
                  onClick={onSignInClick}
                  sx={{
                    py: 2,
                    px: 4,
                    borderRadius: 3,
                    fontSize: '1.1rem',
                    background: `linear-gradient(45deg, ${theme.palette.primary.main}, ${theme.palette.secondary.main})`,
                    '&:hover': {
                      background: `linear-gradient(45deg, ${theme.palette.primary.dark}, ${theme.palette.secondary.dark})`,
                      transform: 'translateY(-2px)',
                      boxShadow: theme.shadows[8]
                    },
                    transition: 'all 0.3s ease'
                  }}
                >
                  Get Started
                </Button>
                <Button
                  variant="outlined"
                  size="large"
                  endIcon={<ArrowForward />}
                  onClick={() => navigate('/market')}
                  sx={{
                    py: 2,
                    px: 4,
                    borderRadius: 3,
                    fontSize: '1.1rem',
                    '&:hover': {
                      transform: 'translateY(-2px)',
                      boxShadow: theme.shadows[4]
                    },
                    transition: 'all 0.3s ease'
                  }}
                >
                  Explore Markets
                </Button>
              </Box>
            </Slide>
          </Box>
        </Fade>

        {/* Live Market Stats */}
        <Fade in={animationStep >= 3} timeout={800}>
          <Card sx={{ mb: 6, background: alpha(theme.palette.background.paper, 0.9) }}>
            <CardContent sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <ShowChart color="primary" />
                Live Market Overview
              </Typography>
              <Grid container spacing={3}>
                {marketStats.map((stat, index) => (
                  <Grid item xs={6} md={3} key={stat.label}>
                    <Box textAlign="center">
                      <Typography variant="body2" color="text.secondary">
                        {stat.label}
                      </Typography>
                      <Typography variant="h6" fontWeight="bold">
                        {stat.value}
                      </Typography>
                      <Chip
                        label={stat.change}
                        size="small"
                        color={stat.positive ? 'success' : 'error'}
                        sx={{ mt: 0.5 }}
                      />
                    </Box>
                  </Grid>
                ))}
              </Grid>
            </CardContent>
          </Card>
        </Fade>

        {/* Features Grid */}
        <Typography variant="h4" textAlign="center" mb={4} fontWeight="bold">
          Everything You Need to Succeed
        </Typography>

        <Grid container spacing={3}>
          {features.map((feature, index) => (
            <Grid item xs={12} md={6} lg={4} key={feature.title}>
              <Fade in={animationStep >= 3} timeout={800} style={{ transitionDelay: `${index * 100}ms` }}>
                <Card
                  sx={{
                    height: '100%',
                    transition: 'all 0.3s ease',
                    cursor: 'pointer',
                    '&:hover': {
                      transform: 'translateY(-8px)',
                      boxShadow: theme.shadows[12]
                    }
                  }}
                >
                  <CardContent sx={{ p: 3, height: '100%', display: 'flex', flexDirection: 'column' }}>
                    <Box
                      sx={{
                        width: 56,
                        height: 56,
                        borderRadius: 2,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        backgroundColor: alpha(feature.color, 0.1),
                        color: feature.color,
                        mb: 2
                      }}
                    >
                      {feature.icon}
                    </Box>
                    <Typography variant="h6" fontWeight="bold" mb={1}>
                      {feature.title}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" flexGrow={1}>
                      {feature.description}
                    </Typography>
                  </CardContent>
                </Card>
              </Fade>
            </Grid>
          ))}
        </Grid>

        {/* Call to Action */}
        <Fade in={animationStep >= 3} timeout={800}>
          <Box textAlign="center" mt={8}>
            <Typography variant="h5" mb={3} fontWeight="bold">
              Ready to Transform Your Trading Experience?
            </Typography>
            <Button
              variant="contained"
              size="large"
              startIcon={<LoginIcon />}
              onClick={onSignInClick}
              sx={{
                py: 2,
                px: 6,
                borderRadius: 3,
                fontSize: '1.2rem',
                background: `linear-gradient(45deg, ${theme.palette.primary.main}, ${theme.palette.secondary.main})`,
                '&:hover': {
                  background: `linear-gradient(45deg, ${theme.palette.primary.dark}, ${theme.palette.secondary.dark})`,
                  transform: 'translateY(-2px)',
                  boxShadow: theme.shadows[12]
                },
                transition: 'all 0.3s ease'
              }}
            >
              Start Your Journey
            </Button>
          </Box>
        </Fade>
      </Container>
    </Box>
  );
};

export default WelcomeLanding;