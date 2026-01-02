import React from 'react';
import { Box, Container, Typography, Button, Grid, useTheme, useMediaQuery, alpha } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import ImagePlaceholder from './ImagePlaceholder';
import {
  TrendingUp as TrendingUpIcon,
  Psychology as PsychologyIcon,
  Analytics as AnalyticsIcon,
  Event as EventIcon,
  ArrowForward as ArrowForwardIcon,
} from '@mui/icons-material';

const HeroSection = () => {
  const navigate = useNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));

  return (
    <Box
      sx={{
        background: `linear-gradient(180deg, #ffffff 0%, #f5f7fa 100%)`,
        py: { xs: 8, sm: 10, md: 14 },
        position: 'relative',
        overflow: 'hidden',
        borderBottom: `1px solid ${alpha(theme.palette.divider, 0.5)}`,
      }}
    >
      <Container maxWidth="xl">
        <Grid container spacing={{ xs: 4, md: 6 }} alignItems="stretch">
          {/* Left Content */}
          <Grid item xs={12} md={5}>
            <Box sx={{ position: 'relative', zIndex: 1 }}>
              <Typography
                variant="h1"
                component="h1"
                sx={{
                  fontWeight: 800,
                  fontSize: { xs: '2.2rem', sm: '3.2rem', md: '3.8rem' },
                  lineHeight: 1.15,
                  mb: 3,
                  color: theme.palette.text.primary,
                  letterSpacing: '-0.5px',
                }}
              >
                Institutional-Grade Research
                <br />
                <span style={{ color: theme.palette.primary.main }}>Powered by AI. Accessible to All.</span>
              </Typography>

              <Typography
                variant="body1"
                sx={{
                  fontSize: { xs: '1.05rem', sm: '1.15rem', md: '1.25rem' },
                  color: theme.palette.text.secondary,
                  mb: 4,
                  fontWeight: 400,
                  lineHeight: 1.7,
                  maxWidth: '95%',
                }}
              >
                Stop relying on gut instinct and outdated analysis. Bullseye combines 10+ years of market data, advanced AI algorithms, and 6+ research dimensions to reveal the opportunities traditional analysis misses. Get institutional-grade intelligence in real-time.
              </Typography>

              {/* CTA Buttons */}
              <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap', mb: 5 }}>
                <Button
                  variant="contained"
                  size="large"
                  onClick={() => navigate('/app/market')}
                  sx={{
                    fontSize: '1.05rem',
                    fontWeight: 600,
                    py: 1.75,
                    px: 4,
                    borderRadius: '6px',
                    textTransform: 'none',
                    boxShadow: `0 4px 12px ${alpha(theme.palette.primary.main, 0.3)}`,
                    '&:hover': {
                      boxShadow: `0 6px 20px ${alpha(theme.palette.primary.main, 0.4)}`,
                    },
                  }}
                >
                  Explore AI Analysis
                </Button>
                <Button
                  variant="outlined"
                  size="large"
                  onClick={() => navigate('/services')}
                  sx={{
                    fontSize: '1.05rem',
                    fontWeight: 600,
                    py: 1.75,
                    px: 4,
                    borderRadius: '6px',
                    textTransform: 'none',
                    borderColor: alpha(theme.palette.primary.main, 0.5),
                    color: theme.palette.primary.main,
                    '&:hover': {
                      backgroundColor: alpha(theme.palette.primary.main, 0.05),
                      borderColor: theme.palette.primary.main,
                    },
                  }}
                >
                  View Capabilities
                </Button>
              </Box>

              {/* Stats */}
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: { xs: '1fr 1fr', md: '1fr 1fr 1fr' },
                  gap: 3,
                  pt: 3,
                  borderTop: `1px solid ${theme.palette.divider}`,
                }}
              >
                {[
                  { label: '10+ Analysis Dimensions', value: '10+' },
                  { label: 'Real-Time Market Data', value: '24/7' },
                  { label: 'Institutional-Grade Tools', value: 'Enterprise' },
                ].map((stat, idx) => (
                  <Box key={idx}>
                    <Typography
                      sx={{
                        fontSize: '1.8rem',
                        fontWeight: 700,
                        color: theme.palette.primary.main,
                        mb: 0.5,
                      }}
                    >
                      {stat.value}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{ color: theme.palette.text.secondary, fontWeight: 500 }}
                    >
                      {stat.label}
                    </Typography>
                  </Box>
                ))}
              </Box>
            </Box>
          </Grid>

          {/* Right Visual - Hero Image */}
          <Grid item xs={12} md={7}>
            <ImagePlaceholder
              src="https://images.unsplash.com/photo-1502175353174-42a94ce44156?w=1400&h=800&fit=crop&auto=format&q=80"
              alt="Black and White New York City Skyline"
              height={{ xs: '300px', sm: '400px', md: '500px' }}
            />
          </Grid>
        </Grid>
      </Container>
    </Box>
  );
};

export default HeroSection;
