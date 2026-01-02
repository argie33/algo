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
    <Box sx={{ py: { xs: 4, md: 6 }, backgroundColor: '#f8f9fa' }}>
      <Container maxWidth="lg">
        <Typography
          variant="h2"
          component="h1"
          sx={{
            fontSize: { xs: '2rem', sm: '2.5rem', md: '3rem' },
            fontWeight: 800,
            mb: 2,
            color: theme.palette.text.primary,
          }}
        >
          {title}
        </Typography>
        {subtitle && (
          <Typography
            variant="h6"
            sx={{
              fontSize: { xs: '1rem', md: '1.1rem' },
              color: theme.palette.text.secondary,
              fontWeight: 400,
              maxWidth: '700px',
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
