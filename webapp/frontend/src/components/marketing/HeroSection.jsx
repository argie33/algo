import React from 'react';
import { Box, Container, Typography, Button, Grid, useTheme, alpha } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { ArrowForward as ArrowForwardIcon } from '@mui/icons-material';

const HeroSection = () => {
  const navigate = useNavigate();
  const theme = useTheme();

  const stats = [
    { value: '5,300+', label: 'Stocks Covered' },
    { value: '10+', label: 'Years of Data' },
    { value: 'Daily', label: 'Research Updates' },
    { value: 'Free', label: 'Platform Access' },
  ];

  return (
    <Box
      sx={{
        position: 'relative',
        overflow: 'hidden',
        py: { xs: 10, sm: 12, md: 16 },
        borderBottom: `1px solid ${theme.palette.divider}`,
        backgroundImage: `url('https://images.unsplash.com/photo-1518391846015-55a9cc003b25?w=1400&h=800&fit=crop&auto=format&q=80')`,
        backgroundSize: 'cover',
        backgroundPosition: 'center top',
        '&::before': {
          content: '""',
          position: 'absolute',
          inset: 0,
          background: `linear-gradient(105deg,
            ${alpha(theme.palette.background.default, 0.97)} 0%,
            ${alpha(theme.palette.background.default, 0.92)} 35%,
            ${alpha(theme.palette.background.default, 0.75)} 60%,
            transparent 100%)`,
          zIndex: 1,
        },
      }}
    >
      <Container maxWidth="xl" sx={{ position: 'relative', zIndex: 2 }}>
        <Grid container spacing={{ xs: 4, md: 6 }} alignItems="center">
          <Grid item xs={12} md={7}>
            <Box>
              <Typography
                variant="overline"
                sx={{
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  letterSpacing: '3px',
                  color: theme.palette.primary.main,
                  display: 'block',
                  mb: 2,
                }}
              >
                Independent Equity Research
              </Typography>

              <Typography
                variant="h1"
                component="h1"
                sx={{
                  fontWeight: 900,
                  fontSize: { xs: '2.4rem', sm: '3.4rem', md: '4.2rem' },
                  lineHeight: 1.1,
                  mb: 3,
                  color: theme.palette.text.primary,
                  letterSpacing: '-1px',
                }}
              >
                Research Without
                <Box
                  component="span"
                  sx={{
                    display: 'block',
                    color: theme.palette.primary.main,
                  }}
                >
                  the Guesswork
                </Box>
              </Typography>

              <Typography
                variant="body1"
                sx={{
                  fontSize: { xs: '1.05rem', md: '1.2rem' },
                  color: theme.palette.text.secondary,
                  mb: 2,
                  lineHeight: 1.8,
                  maxWidth: '580px',
                  fontWeight: 500,
                }}
              >
                We&apos;re tired of watching Wall Street have all the advantages. That ends now.
              </Typography>

              <Typography
                variant="body1"
                sx={{
                  fontSize: { xs: '0.95rem', md: '1.05rem' },
                  color: theme.palette.text.secondary,
                  mb: 5,
                  lineHeight: 1.8,
                  maxWidth: '560px',
                }}
              >
                Bullseye delivers institutional-grade equity research completely free&#8212;quantitative
                scoring, fundamental analysis, technical signals, and market intelligence that the
                big firms pay millions for. We built it for serious investors.
              </Typography>

              <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', mb: 6 }}>
                <Button
                  variant="contained"
                  size="large"
                  endIcon={<ArrowForwardIcon />}
                  onClick={() => navigate('/app/markets')}
                  sx={{
                    fontSize: '1rem',
                    fontWeight: 700,
                    py: 1.75,
                    px: 4,
                    borderRadius: '0px',
                    textTransform: 'none',
                    boxShadow: `0 4px 16px ${alpha(theme.palette.primary.main, 0.35)}`,
                    '&:hover': {
                      boxShadow: `0 6px 24px ${alpha(theme.palette.primary.main, 0.5)}`,
                    },
                  }}
                >
                  Launch Platform
                </Button>
                <Button
                  variant="outlined"
                  size="large"
                  onClick={() => navigate('/research-insights')}
                  sx={{
                    fontSize: '1rem',
                    fontWeight: 600,
                    py: 1.75,
                    px: 4,
                    borderRadius: '0px',
                    textTransform: 'none',
                    borderColor: alpha(theme.palette.primary.main, 0.5),
                    '&:hover': {
                      backgroundColor: alpha(theme.palette.primary.main, 0.05),
                      borderColor: theme.palette.primary.main,
                    },
                  }}
                >
                  How It Works
                </Button>
              </Box>

              {/* Stats Row */}
              <Box
                sx={{
                  display: 'flex',
                  gap: { xs: 3, sm: 5 },
                  flexWrap: 'wrap',
                  pt: 4,
                  borderTop: `1px solid ${theme.palette.divider}`,
                }}
              >
                {stats.map((stat) => (
                  <Box key={stat.label}>
                    <Typography
                      sx={{
                        fontSize: { xs: '1.5rem', md: '1.8rem' },
                        fontWeight: 800,
                        color: theme.palette.primary.main,
                        lineHeight: 1,
                      }}
                    >
                      {stat.value}
                    </Typography>
                    <Typography
                      sx={{
                        fontSize: '0.8rem',
                        color: theme.palette.text.secondary,
                        fontWeight: 500,
                        mt: 0.5,
                        textTransform: 'uppercase',
                        letterSpacing: '0.5px',
                      }}
                    >
                      {stat.label}
                    </Typography>
                  </Box>
                ))}
              </Box>
            </Box>
          </Grid>
        </Grid>
      </Container>
    </Box>
  );
};

export default HeroSection;
