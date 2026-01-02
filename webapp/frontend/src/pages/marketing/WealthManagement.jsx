import React from 'react';
import { Container, Box, Typography, Grid, Card, CardContent, useTheme, alpha } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import CTASection from '../../components/marketing/CTASection';
import PromoBanner from '../../components/marketing/PromoBanner';
import ImagePlaceholder from '../../components/marketing/ImagePlaceholder';
import { TrendingUp as TrendingUpIcon } from '@mui/icons-material';

const WealthManagement = () => {
  const theme = useTheme();

  const features = [
    {
      title: 'Portfolio Optimization',
      description: 'Use AI-powered analysis to optimize asset allocation and sector rotation. Make data-driven decisions for your entire portfolio.',
    },
    {
      title: 'Risk Management',
      description: 'Identify risks before they materialize. Our AI reveals hidden correlations and warning signs across your holdings.',
    },
    {
      title: 'Performance Tracking',
      description: 'Monitor portfolio performance against benchmarks. Track which analysis dimensions are driving your returns.',
    },
    {
      title: 'Sector Rotation Intelligence',
      description: 'Identify emerging sector trends and rotation patterns. Shift allocations with confidence based on AI-powered insights.',
    },
    {
      title: 'Economic Impact Analysis',
      description: 'Understand how macro trends and economic changes impact your portfolio. Prepare for market shifts before they happen.',
    },
    {
      title: 'Hedging Strategies',
      description: 'Implement intelligent hedging strategies to protect your wealth. Use AI to identify optimal hedge instruments and timing.',
    },
  ];

  return (
    <MarketingLayout>
      <PageHeader
        title="Wealth Management"
        subtitle="AI-powered portfolio management for serious investors"
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
                Wealth Management Solutions
              </Typography>
              <Typography
                variant="body1"
                sx={{
                  fontSize: '1.1rem',
                  color: theme.palette.text.secondary,
                  lineHeight: 1.8,
                }}
              >
                Sophisticated portfolio management tools that give you edge in managing your wealth. Portfolio optimization, risk analysis, and intelligent hedging strategies all powered by AI.
              </Typography>
            </Grid>
            <Grid item xs={12} md={6}>
              <ImagePlaceholder
                src="https://images.unsplash.com/photo-1559027615-cd4628902d4a?w=800&h=500&fit=crop&auto=format&q=80"
                alt="Wealth Management Solutions"
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
          Intelligent Portfolio Management
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
          Whether you're managing a personal portfolio or institutional assets, Bullseye provides the tools to optimize returns and manage risk effectively.
        </Typography>

        <Grid container spacing={4}>
          {features.map((feature, idx) => (
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
        title="Manage Wealth with Confidence"
        subtitle="Use AI-powered insights to optimize your portfolio and protect your wealth"
        primaryCTA={{ label: 'Launch Platform', href: '/app/market' }}
        secondaryCTA={{ label: 'Schedule Consultation', href: '/become-client' }}
      />

      <Box sx={{ mx: { xs: 2, md: 4 }, mb: 6 }}>
        <CTASection
          variant="primary"
          title="Transform Your Wealth Management"
          subtitle="Access institutional-grade portfolio management tools designed for serious investors."
          primaryCTA={{ label: 'Become a Client', link: '/become-client' }}
          secondaryCTA={{ label: 'View Services', link: '/services' }}
        />
      </Box>
    </MarketingLayout>
  );
};

export default WealthManagement;
