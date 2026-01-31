import React from 'react';
import { Box, Container, Typography, useTheme } from '@mui/material';

/**
 * PageHeader Component
 * Reusable header section for all marketing pages
 * Eliminates duplicate code across Contact, Firm, Services, Research, Media pages
 */
const PageHeader = ({ title, subtitle }) => {
  const theme = useTheme();

  return (
    <Box sx={{
      py: { xs: 6, md: 8 },
      background: `linear-gradient(135deg, ${theme.palette.primary.main}15 0%, ${theme.palette.primary.main}05 100%)`,
      borderBottom: `3px solid ${theme.palette.primary.main}`,
      position: 'relative',
      overflow: 'hidden',
      '&::before': {
        content: '""',
        position: 'absolute',
        top: 0,
        right: '-100px',
        width: '300px',
        height: '300px',
        background: `radial-gradient(circle, ${theme.palette.primary.main}20 0%, transparent 70%)`,
        borderRadius: '50%',
        pointerEvents: 'none',
      }
    }}>
      <Container maxWidth="lg" sx={{ position: 'relative', zIndex: 1 }}>
        <Typography
          variant="h2"
          component="h1"
          sx={{
            fontSize: { xs: '2rem', sm: '2.5rem', md: '3.5rem' },
            fontWeight: 900,
            mb: 2,
            color: theme.palette.text.primary,
            letterSpacing: '-0.5px',
            background: `linear-gradient(135deg, ${theme.palette.primary.main} 0%, ${theme.palette.text.primary} 100%)`,
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
          }}
        >
          {title}
        </Typography>
        {subtitle && (
          <Typography
            variant="h6"
            sx={{
              fontSize: { xs: '1rem', md: '1.15rem' },
              color: theme.palette.text.secondary,
              fontWeight: 500,
              maxWidth: '700px',
              lineHeight: 1.6,
            }}
          >
            {subtitle}
          </Typography>
        )}
      </Container>
    </Box>
  );
};

export default PageHeader;
