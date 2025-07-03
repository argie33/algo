import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import {
  Box,
  Container,
  Typography,
  Card,
  CardContent,
  Grid,
  Chip
} from '@mui/material';

const Dashboard = () => {
  const { isAuthenticated, user } = useAuth();

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Box mb={4}>
        <Typography variant="h3" component="h1" gutterBottom>
          Institutional Trading Platform
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Professional-grade analytics, real-time insights, and algorithmic trading
        </Typography>
      </Box>

      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Welcome to the Dashboard
              </Typography>
              <Typography variant="body2" color="text.secondary">
                This is a simplified version of the dashboard. The full version is being fixed.
              </Typography>
              <Box mt={2}>
                <Chip label="Live Data" color="success" size="small" variant="outlined" />
                <Chip label="AI Analytics" color="primary" size="small" variant="outlined" sx={{ ml: 1 }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>
        
        {isAuthenticated && user && (
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  User Info
                </Typography>
                <Typography variant="body2">
                  Welcome, {user.username || user.email || 'User'}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        )}
      </Grid>
    </Container>
  );
};

export default Dashboard;