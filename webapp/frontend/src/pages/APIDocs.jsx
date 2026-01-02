import React from 'react';
import {
  Box,
  Card,
  CardContent,
  Container,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  useTheme,
} from '@mui/material';

const APIDocs = () => {
  const theme = useTheme();

  const endpoints = [
    {
      category: 'Health',
      items: [
        { method: 'GET', path: '/api/health', description: 'Health check and status', auth: false },
      ]
    },
    {
      category: 'Stocks',
      items: [
        { method: 'GET', path: '/api/market', description: 'Market overview data', auth: false },
        { method: 'GET', path: '/api/scores/stockscores', description: 'Stock scoring data', auth: false },
        { method: 'GET', path: '/api/earnings', description: 'Earnings information', auth: false },
        { method: 'GET', path: '/api/sentiment', description: 'Sentiment analysis', auth: false },
      ]
    },
    {
      category: 'Portfolio',
      items: [
        { method: 'GET', path: '/api/portfolio/health', description: 'Portfolio health status', auth: true },
        { method: 'POST', path: '/api/portfolio', description: 'Create portfolio', auth: true },
      ]
    },
    {
      category: 'Contact',
      items: [
        { method: 'POST', path: '/api/contact', description: 'Submit contact form', auth: false },
        { method: 'GET', path: '/api/contact/submissions', description: 'Get all submissions (admin)', auth: true },
      ]
    },
    {
      category: 'Market Data',
      items: [
        { method: 'GET', path: '/api/sectors', description: 'Sector analysis', auth: false },
        { method: 'GET', path: '/api/economic', description: 'Economic indicators', auth: false },
        { method: 'GET', path: '/api/financials', description: 'Financial data', auth: false },
      ]
    }
  ];

  const getMethodColor = (method) => {
    switch (method) {
      case 'GET': return 'info';
      case 'POST': return 'success';
      case 'PUT': return 'warning';
      case 'DELETE': return 'error';
      default: return 'default';
    }
  };

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Typography variant="h3" sx={{ mb: 1, fontWeight: 700 }}>
        API Documentation
      </Typography>
      <Typography variant="body1" sx={{ mb: 4, color: 'text.secondary' }}>
        Complete list of available API endpoints for the Financial Dashboard
      </Typography>

      {endpoints.map((section) => (
        <Card key={section.category} sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h5" sx={{ mb: 2, fontWeight: 700 }}>
              {section.category}
            </Typography>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow sx={{ backgroundColor: theme.palette.grey[100] }}>
                    <TableCell sx={{ fontWeight: 700 }}>Method</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>Endpoint</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>Description</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>Auth</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {section.items.map((item, idx) => (
                    <TableRow key={idx} hover>
                      <TableCell>
                        <Chip
                          label={item.method}
                          color={getMethodColor(item.method)}
                          size="small"
                          variant="outlined"
                        />
                      </TableCell>
                      <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.9em' }}>
                        {item.path}
                      </TableCell>
                      <TableCell>{item.description}</TableCell>
                      <TableCell>
                        {item.auth ? (
                          <Chip label="Required" size="small" variant="outlined" color="warning" />
                        ) : (
                          <Chip label="Public" size="small" variant="outlined" color="success" />
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      ))}

      <Card sx={{ mt: 4, backgroundColor: theme.palette.primary.main + '10' }}>
        <CardContent>
          <Typography variant="h6" sx={{ mb: 2, fontWeight: 700 }}>
            Base URL
          </Typography>
          <Typography variant="body2" sx={{ fontFamily: 'monospace', mb: 2 }}>
            http://localhost:3001
          </Typography>
          <Typography variant="h6" sx={{ mb: 2, fontWeight: 700 }}>
            Response Format
          </Typography>
          <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
            All responses are JSON with standard format:<br/>
            {'{'}success: boolean, data: {'{}'}, error: string?{'}'}
          </Typography>
        </CardContent>
      </Card>
    </Container>
  );
};

export default APIDocs;
