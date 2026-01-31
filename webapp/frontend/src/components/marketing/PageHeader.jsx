import React from 'react';
import { Box, Container, Typography, useTheme, alpha } from '@mui/material';

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
      position: 'relative',
      overflow: 'hidden',
      borderBottom: `3px solid ${theme.palette.primary.main}`,
      backgroundImage: `url('https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=1200&h=700&fit=crop&auto=format&q=80')`,
      backgroundSize: 'cover',
      backgroundPosition: 'center',
      '&::before': {
        content: '""',
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: `linear-gradient(90deg, ${alpha(theme.palette.background.default, 0.75)} 0%, ${alpha(theme.palette.background.default, 0.65)} 40%, ${alpha(theme.palette.background.default, 0.4)} 70%, transparent 100%)`,
        zIndex: 1,
      }
    }}>
      <Container maxWidth="lg" sx={{ position: 'relative', zIndex: 1, textAlign: 'center' }}>
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
              mx: 'auto',
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
