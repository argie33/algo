import React from 'react';
import { Container, Box, Typography, Grid, Card, CardContent, Button, useTheme } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import { ArrowForward as ArrowForwardIcon } from '@mui/icons-material';

const Media = () => {
  const theme = useTheme();

  const resources = [
    {
      title: 'Getting Started Guide',
      description: 'Learn how to navigate the platform and access all analysis tools.',
      type: 'Guide',
    },
    {
      title: 'Stock Scoring Methodology',
      description: 'Deep dive into how we calculate composite scores from multiple factors.',
      type: 'Tutorial',
    },
    {
      title: 'Earnings Analysis Primer',
      description: 'Understanding earnings estimates, revisions, and post-earnings momentum.',
      type: 'Educational',
    },
    {
      title: 'Sentiment Analysis Explained',
      description: 'How to interpret analyst sentiment, positioning, and market psychology data.',
      type: 'Tutorial',
    },
  ];

  const insights = [
    {
      title: 'What Earnings Estimate Revisions Tell Us',
      description: 'How analyst upgrades and downgrades correlate with future stock performance.',
    },
    {
      title: 'Seasonality Patterns in the Market',
      description: 'Historical seasonal trends and how to incorporate them into your strategy.',
    },
    {
      title: 'Multi-Factor vs Single Indicator Analysis',
      description: 'Why combining multiple signals provides better risk-adjusted returns.',
    },
  ];

  return (
    <MarketingLayout>
      {/* Header */}
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
            Resources & Insights
          </Typography>
          <Typography
            variant="h6"
            sx={{
              fontSize: { xs: '1rem', md: '1.1rem' },
              color: theme.palette.text.secondary,
              fontWeight: 400,
              maxWidth: '700px',
            }}
          >
            Educational resources and market insights to help you make better investment decisions
          </Typography>
        </Container>
      </Box>

      <Container maxWidth="lg" sx={{ py: { xs: 6, md: 8 } }}>
        {/* Resources Section */}
        <Box sx={{ mb: 8 }}>
          <Typography
            variant="h3"
            sx={{
              fontSize: { xs: '1.8rem', sm: '2.2rem', md: '2.5rem' },
              fontWeight: 800,
              mb: 4,
              color: theme.palette.text.primary,
            }}
          >
            Learning Resources
          </Typography>
          <Grid container spacing={3}>
            {resources.map((resource, idx) => (
              <Grid item xs={12} sm={6} md={6} lg={6} key={idx}>
                <Card
                  sx={{
                    height: '100%',
                    border: `1px solid ${theme.palette.divider}`,
                    display: 'flex',
                    flexDirection: 'column',
                    '&:hover': {
                      boxShadow: theme.shadows[4],
                      transform: 'translateY(-4px)',
                      transition: 'all 0.3s ease',
                    },
                  }}
                >
                  <CardContent sx={{ flexGrow: 1 }}>
                    <Box sx={{ mb: 1 }}>
                      <Typography
                        variant="caption"
                        sx={{
                          backgroundColor: `${theme.palette.primary.main}15`,
                          color: theme.palette.primary.main,
                          fontWeight: 600,
                          px: 1.5,
                          py: 0.5,
                          borderRadius: 1,
                          display: 'inline-block',
                        }}
                      >
                        {resource.type}
                      </Typography>
                    </Box>
                    <Typography
                      variant="h6"
                      sx={{
                        fontWeight: 700,
                        mb: 1,
                        mt: 1,
                        color: theme.palette.text.primary,
                      }}
                    >
                      {resource.title}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        color: theme.palette.text.secondary,
                        lineHeight: 1.6,
                      }}
                    >
                      {resource.description}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Box>

        {/* Insights Section */}
        <Box>
          <Typography
            variant="h3"
            sx={{
              fontSize: { xs: '1.8rem', sm: '2.2rem', md: '2.5rem' },
              fontWeight: 800,
              mb: 4,
              color: theme.palette.text.primary,
            }}
          >
            Market Insights
          </Typography>
          <Grid container spacing={3}>
            {insights.map((insight, idx) => (
              <Grid item xs={12} sm={6} md={4} key={idx}>
                <Card
                  sx={{
                    height: '100%',
                    border: `1px solid ${theme.palette.divider}`,
                    display: 'flex',
                    flexDirection: 'column',
                    '&:hover': {
                      boxShadow: theme.shadows[4],
                      transform: 'translateY(-4px)',
                      transition: 'all 0.3s ease',
                    },
                  }}
                >
                  <CardContent sx={{ flexGrow: 1 }}>
                    <Typography
                      variant="h6"
                      sx={{
                        fontWeight: 700,
                        mb: 1.5,
                        color: theme.palette.text.primary,
                      }}
                    >
                      {insight.title}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        color: theme.palette.text.secondary,
                        lineHeight: 1.6,
                        mb: 2,
                      }}
                    >
                      {insight.description}
                    </Typography>
                    <Button
                      size="small"
                      endIcon={<ArrowForwardIcon />}
                      sx={{
                        textTransform: 'none',
                        fontWeight: 600,
                      }}
                    >
                      Read More
                    </Button>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Box>
      </Container>
    </MarketingLayout>
  );
};

export default Media;
