import React from 'react';
import { Box, Container, Typography, useTheme, alpha } from '@mui/material';

const PageHeader = ({ title, subtitle }) => {
  const theme = useTheme();

  return (
    <Box
      sx={{
        py: { xs: 8, md: 10 },
        position: 'relative',
        overflow: 'hidden',
        background: `linear-gradient(135deg, ${theme.palette.primary.main} 0%, ${alpha(theme.palette.primary.dark || theme.palette.primary.main, 0.85)} 50%, ${alpha(theme.palette.primary.main, 0.7)} 100%)`,
        borderBottom: `1px solid ${alpha(theme.palette.primary.main, 0.3)}`,
        '&::before': {
          content: '""',
          position: 'absolute',
          inset: 0,
          background: `radial-gradient(ellipse at 0% 50%, ${alpha('#000', 0.3)} 0%, transparent 70%)`,
        },
        '&::after': {
          content: '""',
          position: 'absolute',
          inset: 0,
          backgroundImage: 'repeating-linear-gradient(90deg, transparent, transparent 60px, rgba(255,255,255,0.02) 60px, rgba(255,255,255,0.02) 61px)',
          pointerEvents: 'none',
        },
      }}
    >
      <Container maxWidth="lg" sx={{ position: 'relative', zIndex: 1, textAlign: 'center' }}>
        <Typography
          variant="overline"
          sx={{
            fontSize: '0.75rem',
            fontWeight: 700,
            letterSpacing: '3px',
            color: alpha('#fff', 0.7),
            display: 'block',
            mb: 2,
          }}
        >
          Bullseye Financial
        </Typography>
        <Typography
          variant="h2"
          component="h1"
          sx={{
            fontSize: { xs: '2.2rem', sm: '2.8rem', md: '3.5rem' },
            fontWeight: 900,
            mb: subtitle ? 2.5 : 0,
            color: '#fff',
            letterSpacing: '-0.5px',
            lineHeight: 1.1,
          }}
        >
          {title}
        </Typography>
        {subtitle && (
          <Typography
            variant="h6"
            sx={{
              fontSize: { xs: '1rem', md: '1.15rem' },
              color: alpha('#fff', 0.8),
              fontWeight: 400,
              maxWidth: '640px',
              mx: 'auto',
              lineHeight: 1.7,
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
