import React from 'react';
import { Container, Box, Typography, Grid, Card, CardContent, useTheme } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import CTASection from '../../components/marketing/CTASection';
import PromoBanner from '../../components/marketing/PromoBanner';
import { Build as BuildIcon } from '@mui/icons-material';

const InvestmentTools = () => {
  const theme = useTheme();

  const toolCategories = [
    {
      title: 'Real-Time Stock Scoring',
      description: 'AI-powered composite scores that update in real-time. Analyze individual stocks across multiple dimensions and compare them instantly.',
    },
    {
      title: 'Earnings Calendar & Analysis',
      description: 'Track upcoming earnings, view historical surprise patterns, and identify stocks with positive estimate revisions using AI analysis.',
    },
    {
      title: 'Technical Analysis Engine',
      description: 'Advanced technical indicators, pattern recognition, and AI-generated trading signals. Identify entry and exit opportunities with precision.',
    },
    {
      title: 'Sector & Market Tools',
      description: 'Monitor sector rotation, relative strength analysis, and overall market health. Make informed allocation decisions across different asset classes.',
    },
    {
      title: 'Economic Dashboard',
      description: 'Track key economic indicators, macro trends, and their impact on markets. Understand the broader economic context for your trades.',
    },
    {
      title: 'Hedge Helper',
      description: 'AI-powered hedging suggestions and risk management strategies. Protect your portfolio with intelligent portfolio protection recommendations.',
    },
  ];

  return (
    <MarketingLayout>
      <PageHeader
        title="Investment Tools"
        subtitle="Complete toolkit for active investors and traders"
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
          Professional-Grade Analysis Tools
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
          A complete suite of tools designed for active traders, swing traders, and investors who want real-time analysis and actionable signals.
        </Typography>

        <Grid container spacing={4}>
          {toolCategories.map((tool, idx) => (
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
                    {tool.title}
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{
                      color: theme.palette.text.secondary,
                      lineHeight: 1.7,
                    }}
                  >
                    {tool.description}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Container>

      <PromoBanner
        icon={<BuildIcon sx={{ color: theme.palette.primary.main }} />}
        title="Built for Active Investors"
        subtitle="Get real-time analysis and AI-powered signals for informed trading decisions"
        primaryCTA={{ label: 'Launch Platform', href: '/app/market' }}
        secondaryCTA={{ label: 'View Pricing', href: '/become-client' }}
      />

      <Box sx={{ mx: { xs: 2, md: 4 }, mb: 6 }}>
        <CTASection
          variant="primary"
          title="Start Using Professional Tools Today"
          subtitle="Access all investment tools immediately and start analyzing like a pro."
          primaryCTA={{ label: 'Get Started', link: '/become-client' }}
          secondaryCTA={{ label: 'Learn More', link: '/services' }}
        />
      </Box>
    </MarketingLayout>
  );
};

export default InvestmentTools;
