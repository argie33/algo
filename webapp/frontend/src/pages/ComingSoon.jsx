import React from 'react';
import { Container, Paper, Box, Typography, Button } from '@mui/material';
import { Construction } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

function ComingSoon({ pageName = 'This Page', description = 'This feature is currently under development.' }) {
  const navigate = useNavigate();

  return (
    <Container maxWidth="sm">
      <Paper elevation={3} sx={{ p: 4, mt: 8, textAlign: 'center' }}>
        <Construction sx={{ fontSize: 64, color: 'primary.main', mb: 2 }} />
        <Typography variant="h3" component="h3" gutterBottom>
          {pageName} Coming Soon
        </Typography>
        <Typography variant="body1" color="textSecondary" sx={{ mb: 2 }}>
          {description}
        </Typography>
        <Typography variant="body2" sx={{ mb: 3 }}>
          We're working hard to bring you this feature. Please check back later.
        </Typography>
        <Button
          variant="contained"
          color="primary"
          onClick={() => navigate('/')}
        >
          Return to Dashboard
        </Button>
      </Paper>
    </Container>
  );
}

export default ComingSoon;
