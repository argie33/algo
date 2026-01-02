import React from 'react';
import { Container, Box, Typography, Grid, Card, CardContent, useTheme } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import CTASection from '../../components/marketing/CTASection';
import PromoBanner from '../../components/marketing/PromoBanner';
import { Insights as InsightsIcon } from '@mui/icons-material';

const ResearchInsights = () => {
  const theme = useTheme();

  const researchCategories = [
    {
      title: 'AI-Powered Stock Analysis',
      description: 'Our composite scoring system analyzes stocks across multiple dimensions using machine learning. Get comprehensive insights beyond traditional metrics.',
    },
    {
      title: 'Market Research & Reports',
      description: 'In-depth analysis of market trends, sector performance, and economic indicators. Actionable insights to inform your investment strategy.',
    },
    {
      title: 'Sentiment & Positioning Analysis',
      description: 'Track how institutional sentiment is shifting. Our AI interprets analyst positioning, upgrades/downgrades, and market psychology.',
    },
    {
      title: 'Technical Analysis & Trading Signals',
      description: 'AI-generated signals based on price action, technical patterns, and momentum indicators. Identify entry and exit opportunities.',
    },
  ];

  return (
    <MarketingLayout>
      <PageHeader
        title="Research & Insights"
        subtitle="AI-powered market analysis and intelligence"
      />

      <Container maxWidth="lg" sx={{ py: { xs: 6, md: 8 } }}>
        <Typography
          variant="h3"
          sx={{
            fontSize: { xs: '1.8rem', sm: '2.2rem', md: '2.5rem' },
            fontWeight: 800,
            mb: 4,
            textAlign: 'center',
            color: theme.palette.text.primary,
          }}
        >
          Comprehensive Research Tools
        </Typography>
        <Typography
          variant="body1"
          sx={{
            fontSize: '1.05rem',
            color: theme.palette.text.secondary,
            mb: 6,
            textAlign: 'center',
            maxWidth: '700px',
            mx: 'auto',
          }}
        >
          Access professional-grade research and analysis tools powered by artificial intelligence. Get insights that traditional analysis misses.
        </Typography>

        <Grid container spacing={4}>
          {researchCategories.map((category, idx) => (
            <Grid item xs={12} sm={6} key={idx}>
              <Card
                sx={{
                  height: '100%',
                  border: `1px solid ${theme.palette.divider}`,
                  backgroundColor: theme.palette.background.default,
                  borderRadius: '0px',
                  transition: 'all 0.3s ease',
                  '&:hover': {
                    boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
                    transform: 'translateY(-2px)',
                  },
                }}
              >
                <CardContent>
                  <Typography
                    variant="h6"
                    sx={{
                      fontWeight: 700,
                      mb: 1.5,
                      color: theme.palette.primary.main,
                    }}
                  >
                    {category.title}
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{
                      color: theme.palette.text.secondary,
                      lineHeight: 1.7,
                    }}
                  >
                    {category.description}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Container>

      <PromoBanner
        icon={<InsightsIcon sx={{ color: theme.palette.primary.main }} />}
        title="Ready for Professional-Grade Insights?"
        subtitle="Start leveraging AI-powered research to improve your investment decisions"
        primaryCTA={{ label: 'Launch Platform', href: '/app/market' }}
        secondaryCTA={{ label: 'Schedule Demo', href: '/become-client' }}
      />

      <Box sx={{ mx: { xs: 2, md: 4 }, mb: 6 }}>
        <CTASection
          variant="primary"
          title="Unlock Market Intelligence"
          subtitle="Access comprehensive research and insights to stay ahead of the market."
          primaryCTA={{ label: 'Get Started', link: '/become-client' }}
          secondaryCTA={{ label: 'Learn More', link: '/services' }}
        />
      </Box>
    </MarketingLayout>
  );
};

export default ResearchInsights;
