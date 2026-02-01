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
        position: 'relative',
        overflow: 'hidden',
        py: { xs: 8, sm: 10, md: 14 },
        borderBottom: `1px solid ${alpha(theme.palette.divider, 0.5)}`,
        backgroundImage: `url('https://images.unsplash.com/photo-1518391846015-55a9cc003b25?w=1200&h=700&fit=crop&auto=format&q=80')`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        '&::before': {
          content: '""',
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: `linear-gradient(90deg, ${alpha(theme.palette.background.default, 0.95)} 0%, ${alpha(theme.palette.background.default, 0.85)} 40%, ${alpha(theme.palette.background.default, 0.6)} 70%, transparent 100%)`,
          zIndex: 1,
        },
      }}
    >
      <Container maxWidth="xl" sx={{ position: 'relative', zIndex: 2 }}>
        <Grid container spacing={{ xs: 4, md: 6 }} alignItems="center">
          {/* Left Content - Overlaid on Image */}
          <Grid item xs={12} md={6}>
            <Box>
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
                Research That Finds Better Opportunities
                <br />
                <span style={{ color: theme.palette.primary.main }}>AI-Powered Intelligence. Professional Results.</span>
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
                Stop guessing on stock picks. Bullseye analyzes 5,300+ companies across multiple dimensions in real-time, identifying patterns and opportunities that human analysis consistently misses. Get the edge institutional investors rely on.
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
            </Box>
          </Grid>
        </Grid>
      </Container>
    </Box>
  );
};

export default HeroSection;
