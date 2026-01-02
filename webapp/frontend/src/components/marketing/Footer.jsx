import React from 'react';
import { Box, Container, Grid, Typography, Link, Divider, useTheme } from '@mui/material';
import { useNavigate } from 'react-router-dom';

const Footer = () => {
  const navigate = useNavigate();
  const theme = useTheme();
  const currentYear = new Date().getFullYear();

  const footerSections = [
    {
      title: 'Company',
      links: [
        { label: 'Firm', path: '/firm' },
        { label: 'Services', path: '/services' },
        { label: 'Contact', path: '/contact' },
      ],
    },
    {
      title: 'Resources',
      links: [
        { label: 'Research', path: '/research' },
        { label: 'Media', path: '/media' },
      ],
    },
    {
      title: 'Application',
      links: [
        { label: 'Market Overview', path: '/app/market' },
        { label: 'Stock Scores', path: '/app/scores' },
        { label: 'Earnings Hub', path: '/app/earnings' },
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
        pt: 6,
        pb: 4,
      }}
    >
      <Container maxWidth="xl">
        {/* Footer Content */}
        <Grid container spacing={4} sx={{ mb: 4 }}>
          {/* Brand */}
          <Grid item xs={12} sm={6} md={3}>
            <Typography
              variant="h6"
              sx={{
                fontWeight: 700,
                color: theme.palette.primary.main,
                mb: 1,
              }}
            >
              Bullseye Financial
            </Typography>
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{ mb: 2 }}
            >
              Comprehensive market intelligence with evidence-based analysis across earnings, sentiment, technicals, and more.
            </Typography>
          </Grid>

          {/* Footer Links */}
          {footerSections.map((section) => (
            <Grid item xs={12} sm={6} md={3} key={section.title}>
              <Typography
                variant="subtitle2"
                sx={{
                  fontWeight: 600,
                  mb: 2,
                  color: theme.palette.text.primary,
                }}
              >
                {section.title}
              </Typography>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
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
                      '&:hover': {
                        color: theme.palette.primary.main,
                      },
                      transition: 'color 0.3s ease',
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
            color: theme.palette.text.secondary,
          }}
        >
          <Typography variant="body2">
            © {currentYear} Bullseye Financial. All rights reserved.
          </Typography>
          <Box sx={{ display: 'flex', gap: 3 }}>
            <Link
              href="#"
              variant="body2"
              sx={{
                color: theme.palette.text.secondary,
                textDecoration: 'none',
                '&:hover': {
                  color: theme.palette.primary.main,
                },
              }}
            >
              Privacy Policy
            </Link>
            <Link
              href="#"
              variant="body2"
              sx={{
                color: theme.palette.text.secondary,
                textDecoration: 'none',
                '&:hover': {
                  color: theme.palette.primary.main,
                },
              }}
            >
              Terms of Service
            </Link>
          </Box>
        </Box>
      </Container>
    </Box>
  );
};

export default Footer;
