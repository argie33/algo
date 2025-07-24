import React from 'react';
import {
  Box,
  CircularProgress,
  Typography,
  Fade,
  useTheme,
  alpha,
  keyframes
} from '@mui/material';
import { TrendingUp, Analytics, Security } from '@mui/icons-material';

const pulseAnimation = keyframes`
  0% {
    transform: scale(1);
    opacity: 0.8;
  }
  50% {
    transform: scale(1.1);
    opacity: 1;
  }
  100% {
    transform: scale(1);
    opacity: 0.8;
  }
`;

const floatAnimation = keyframes`
  0%, 100% {
    transform: translateY(0px);
  }
  50% {
    transform: translateY(-10px);
  }
`;

const LoadingTransition = ({ 
  message = "Loading your dashboard...", 
  submessage = "Preparing your personalized financial insights",
  type = "default" 
}) => {
  const theme = useTheme();

  const icons = [
    <TrendingUp key="trending" sx={{ fontSize: 40 }} />,
    <Analytics key="analytics" sx={{ fontSize: 40 }} />,
    <Security key="security" sx={{ fontSize: 40 }} />
  ];

  const getGradient = () => {
    switch (type) {
      case 'auth':
        return `linear-gradient(135deg, ${theme.palette.primary.main} 0%, ${theme.palette.secondary.main} 100%)`;
      case 'welcome':
        return `linear-gradient(135deg, ${theme.palette.success.main} 0%, ${theme.palette.info.main} 100%)`;
      default:
        return `linear-gradient(135deg, ${theme.palette.primary.main} 0%, ${theme.palette.secondary.main} 100%)`;
    }
  };

  return (
    <Fade in={true} timeout={500}>
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '100vh',
          background: `linear-gradient(135deg, 
            ${alpha(theme.palette.primary.main, 0.05)} 0%, 
            ${alpha(theme.palette.secondary.main, 0.02)} 100%)`,
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
            background: `url("data:image/svg+xml,%3Csvg width='100' height='100' viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M20 20h60v60H20z' fill='none' stroke='%23${theme.palette.primary.main.replace('#', '')}' stroke-width='1'/%3E%3Cpath d='M30 30l40 40M70 30L30 70' stroke='%23${theme.palette.primary.main.replace('#', '')}' stroke-width='0.5'/%3E%3C/svg%3E")`,
            backgroundRepeat: 'repeat',
            backgroundSize: '100px 100px',
            animation: `${floatAnimation} 20s ease-in-out infinite`
          }}
        />

        {/* Main Loading Content */}
        <Box sx={{ textAlign: 'center', position: 'relative', zIndex: 1 }}>
          {/* Animated Icons */}
          <Box
            sx={{
              display: 'flex',
              justifyContent: 'center',
              gap: 3,
              mb: 4,
              '& > *': {
                animation: `${pulseAnimation} 2s ease-in-out infinite`,
                color: theme.palette.primary.main
              },
              '& > *:nth-of-type(2)': {
                animationDelay: '0.5s'
              },
              '& > *:nth-of-type(3)': {
                animationDelay: '1s'
              }
            }}
          >
            {icons}
          </Box>

          {/* Loading Spinner */}
          <Box sx={{ position: 'relative', display: 'inline-flex', mb: 3 }}>
            <CircularProgress
              size={60}
              thickness={4}
              sx={{
                color: theme.palette.primary.main,
                '& .MuiCircularProgress-circle': {
                  strokeLinecap: 'round',
                }
              }}
            />
            <Box
              sx={{
                position: 'absolute',
                top: 0,
                left: 0,
                bottom: 0,
                right: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Box
                sx={{
                  width: 24,
                  height: 24,
                  borderRadius: '50%',
                  background: getGradient(),
                  animation: `${pulseAnimation} 1.5s ease-in-out infinite`
                }}
              />
            </Box>
          </Box>

          {/* Loading Text */}
          <Typography
            variant="h5"
            sx={{
              fontWeight: 600,
              mb: 1,
              background: getGradient(),
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text'
            }}
          >
            {message}
          </Typography>
          
          <Typography
            variant="body1"
            color="text.secondary"
            sx={{ maxWidth: '400px', mx: 'auto' }}
          >
            {submessage}
          </Typography>

          {/* Progress Dots */}
          <Box
            sx={{
              display: 'flex',
              justifyContent: 'center',
              gap: 1,
              mt: 3,
              '& > *': {
                width: 8,
                height: 8,
                borderRadius: '50%',
                backgroundColor: theme.palette.primary.main,
                animation: `${pulseAnimation} 1.5s ease-in-out infinite`
              },
              '& > *:nth-of-type(2)': {
                animationDelay: '0.3s'
              },
              '& > *:nth-of-type(3)': {
                animationDelay: '0.6s'
              }
            }}
          >
            <Box />
            <Box />
            <Box />
          </Box>
        </Box>
      </Box>
    </Fade>
  );
};

export default LoadingTransition;