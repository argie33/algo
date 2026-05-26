import React from 'react';
import { Box, Container, Grid, Typography, Link, Divider, useTheme, alpha } from '@mui/material';
import { useNavigate } from 'react-router-dom';

const Footer = () => {
  const navigate = useNavigate();
  const theme = useTheme();
  const currentYear = new Date().getFullYear();

  const footerSections = [
    {
      title: 'Company',
      links: [
        { label: 'About Us', path: '/about' },
        { label: 'The Firm', path: '/firm' },
        { label: 'Our Team', path: '/our-team' },
        { label: 'Mission & Values', path: '/mission-values' },
        { label: 'Contact', path: '/contact' },
      ],
    },
    {
      title: 'Research',
      links: [
        { label: 'Research & Insights', path: '/research-insights' },
        { label: 'Investment Tools', path: '/investment-tools' },
        { label: 'Portfolio & Risk', path: '/wealth-management' },
      ],
    },
    {
      title: 'Platform',
      links: [
        { label: 'Market Health', path: '/app/markets' },
        { label: 'Trading Signals', path: '/app/trading-signals' },
        { label: 'Stock Scores', path: '/app/scores' },
        { label: 'Sector Analysis', path: '/app/sectors' },
        { label: 'Economic Data', path: '/app/economic' },
        { label: 'Portfolio Dashboard', path: '/app/portfolio' },
      ],
    },
  ];

  return (
    <Box
      component="footer"
      sx={{
        backgroundColor: theme.palette.background.paper,
        borderTop: `1px solid ${theme.palette.divider}`,
        mt: 12,
        pt: 7,
        pb: 4,
      }}
    >
      <Container maxWidth="xl">
        <Grid container spacing={5} sx={{ mb: 5 }}>
          {/* Brand */}
          <Grid item xs={12} sm={6} md={3}>
            <Box
              onClick={() => navigate('/')}
              sx={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'baseline', gap: 0.5, mb: 1.5 }}
            >
              <Typography
                variant="h6"
                sx={{ fontWeight: 800, color: theme.palette.primary.main, fontSize: '1.15rem' }}
              >
                Bullseye
              </Typography>
              <Typography
                variant="h6"
                sx={{ fontWeight: 400, color: theme.palette.text.secondary, fontSize: '1rem' }}
              >
                Financial
              </Typography>
            </Box>
            <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.8, mb: 2 }}>
              Institutional-grade equity research&mdash;systematic signals, multi-factor scoring,
              and market intelligence&mdash;completely free.
            </Typography>
            <Box
              sx={{
                display: 'inline-block',
                px: 1.5,
                py: 0.5,
                fontSize: '0.7rem',
                fontWeight: 700,
                letterSpacing: '1px',
                textTransform: 'uppercase',
                color: '#22c55e',
                backgroundColor: alpha('#22c55e', 0.1),
                border: `1px solid ${alpha('#22c55e', 0.25)}`,
              }}
            >
              100% Free &bull; No Paywall
            </Box>
          </Grid>

          {/* Footer Links */}
          {footerSections.map((section) => (
            <Grid item xs={6} sm={4} md={3} key={section.title}>
              <Typography
                variant="subtitle2"
                sx={{
                  fontWeight: 700,
                  mb: 2,
                  color: theme.palette.text.primary,
                  fontSize: '0.82rem',
                  textTransform: 'uppercase',
                  letterSpacing: '1px',
                }}
              >
                {section.title}
              </Typography>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.1 }}>
                {section.links.map((link) => (
                  <Link
                    key={link.path}
                    component="button"
                    onClick={() => navigate(link.path)}
                    variant="body2"
                    sx={{
                      textAlign: 'left',
                      color: theme.palette.text.secondary,
                      textDecoration: 'none',
                      cursor: 'pointer',
                      fontSize: '0.88rem',
                      '&:hover': {
                        color: theme.palette.primary.main,
                      },
                      transition: 'color 0.2s ease',
                    }}
                  >
                    {link.label}
                  </Link>
                ))}
              </Box>
            </Grid>
          ))}
        </Grid>

        <Divider sx={{ my: 3 }} />

        {/* Copyright */}
        <Box
          sx={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexDirection: { xs: 'column', sm: 'row' },
            gap: 2,
          }}
        >
          <Typography variant="body2" color="text.secondary">
            &copy; {currentYear} Bullseye Financial. All rights reserved.
          </Typography>
          <Box sx={{ display: 'flex', gap: 3 }}>
            <Link
              component="button"
              onClick={() => navigate('/privacy')}
              variant="body2"
              sx={{
                color: theme.palette.text.secondary,
                textDecoration: 'none',
                cursor: 'pointer',
                '&:hover': { color: theme.palette.primary.main },
              }}
            >
              Privacy Policy
            </Link>
            <Link
              component="button"
              onClick={() => navigate('/terms')}
              variant="body2"
              sx={{
                color: theme.palette.text.secondary,
                textDecoration: 'none',
                cursor: 'pointer',
                '&:hover': { color: theme.palette.primary.main },
              }}
            >
              Terms of Service
            </Link>
          </Box>
        </Box>

        <Typography
          variant="caption"
          sx={{ display: 'block', mt: 3, color: theme.palette.text.secondary, fontSize: '0.75rem', lineHeight: 1.6 }}
        >
          Bullseye Financial provides equity research and market analysis for informational purposes only.
          Nothing on this platform constitutes investment advice. Past performance is not indicative of future results.
          All data is updated daily before market open.
        </Typography>
      </Container>
    </Box>
  );
};

export default Footer;
