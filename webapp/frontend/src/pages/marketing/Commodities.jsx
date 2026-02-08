import React from 'react';
import { Container, Box, Typography, Grid, Card, CardContent, useTheme, alpha } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import CTASection from '../../components/marketing/CTASection';
import PromoBanner from '../../components/marketing/PromoBanner';
import ImagePlaceholder from '../../components/marketing/ImagePlaceholder';
import { TrendingUp as TrendingUpIcon } from '@mui/icons-material';

const Commodities = () => {
  const theme = useTheme();

  const commodityFeatures = [
    {
      title: 'Real-Time Price Tracking',
      description: 'Monitor crude oil, natural gas, precious metals, and agricultural commodities with live updates and historical data analysis.',
    },
    {
      title: 'Technical Analysis',
      description: 'Apply advanced technical indicators and chart patterns to commodity markets for identifying trend changes and support/resistance levels.',
    },
    {
      title: 'Macro Context',
      description: 'Understand how economic indicators, geopolitical events, and Fed policy impact commodity prices and sector rotation.',
    },
    {
      title: 'Hedging Insights',
      description: 'Identify hedging opportunities using commodity futures and options strategies to protect portfolios against inflation and downside risk.',
    },
    {
      title: 'Cross-Asset Correlation',
      description: 'Analyze how commodities correlate with stocks, bonds, and currencies to optimize portfolio diversification.',
    },
    {
      title: 'Supply & Demand Analysis',
      description: 'Track inventory levels, production data, and geopolitical risks affecting commodity supply chains.',
    },
  ];

  return (
    <MarketingLayout>
      <PageHeader
        title="Commodities Analysis"
        subtitle="Professional-grade commodity market intelligence and analysis"
      />

      {/* Hero Section with Image */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: alpha(theme.palette.primary.main, 0.02) }}>
        <Container maxWidth="lg">
          <Grid container spacing={6} alignItems="center">
            <Grid item xs={12} md={6}>
              <Typography
                variant="h3"
                sx={{
                  fontSize: { xs: '2rem', sm: '2.5rem', md: '3rem' },
                  fontWeight: 800,
                  mb: 3,
                  color: theme.palette.text.primary,
                }}
              >
                Commodities Trading & Analysis
              </Typography>
              <Typography
                variant="body1"
                sx={{
                  fontSize: '1.1rem',
                  color: theme.palette.text.secondary,
                  lineHeight: 1.8,
                }}
              >
                Track crude oil, natural gas, metals, and agriculture commodities. Monitor geopolitical risks, supply chain dynamics, and macro impacts on commodity prices.
              </Typography>
            </Grid>
            <Grid item xs={12} md={6}>
              <ImagePlaceholder
                src="https://picsum.photos/1200/400?random"
                alt="Commodities Trading Analysis"
                height={{ xs: '300px', md: '450px' }}
              />
            </Grid>
          </Grid>
        </Container>
      </Box>

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
          Comprehensive Commodity Intelligence
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
          Real-time analysis of global commodity markets including energy, metals, and agriculture. Track supply dynamics, geopolitical risks, and macro drivers.
        </Typography>

        <Grid container spacing={4}>
          {commodityFeatures.map((feature, idx) => (
            <Grid item xs={12} sm={6} key={idx}>
              <Card
                sx={{
                  height: '100%',
                  border: `1px solid ${theme.palette.divider}`,
                  backgroundColor: theme.palette.background.default,
                  borderRadius: '0px',
                  transition: 'all 0.3s ease',
                  overflow: 'hidden',
                  '&:hover': {
                    boxShadow: '0 8px 20px rgba(0,0,0,0.12)',
                    transform: 'translateY(-4px)',
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
                    {feature.title}
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{
                      color: theme.palette.text.secondary,
                      lineHeight: 1.7,
                    }}
                  >
                    {feature.description}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Container>

      <PromoBanner
        icon={<TrendingUpIcon sx={{ color: theme.palette.primary.main }} />}
        title="Monitor Global Commodities"
        subtitle="Get real-time analysis and macro insights for commodity trading and portfolio hedging"
        primaryCTA={{ label: 'Launch Commodities Tool', href: '/app/commodities' }}
        secondaryCTA={{ label: 'View Pricing', href: '/contact' }}
      />

      <Box sx={{ mx: { xs: 2, md: 4 }, mb: 6 }}>
        <CTASection
          variant="primary"
          title="Start Analyzing Commodities Today"
          subtitle="Access professional-grade commodity market analysis and real-time data."
          primaryCTA={{ label: 'Get Started', link: '/contact' }}
          secondaryCTA={{ label: 'Learn More', link: '/services' }}
        />
      </Box>
    </MarketingLayout>
  );
};

export default Commodities;
