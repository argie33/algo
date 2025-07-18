import React from 'react';
import { Box, Typography, Paper, Container } from '@mui/material';

const Commodities = () => {
  return (
    <Container maxWidth="xl">
      <Box sx={{ py: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          Commodities
        </Typography>
        <Paper sx={{ p: 3 }}>
          <Typography variant="body1">
            Commodities analysis and trading tools coming soon...
          </Typography>
        </Paper>
      </Box>
    </Container>
  );
};

export default Commodities;