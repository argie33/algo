import React from 'react';
import { Box } from '@mui/material';
import MarketingNav from './MarketingNav';
import Footer from './Footer';

const MarketingLayout = ({ children }) => {
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        minHeight: '100vh',
        backgroundColor: '#f8f9fa',
      }}
    >
      <MarketingNav />
      <Box
        component="main"
        sx={{
          flex: 1,
          width: '100%',
        }}
      >
        {children}
      </Box>
      <Footer />
    </Box>
  );
};

export default MarketingLayout;
