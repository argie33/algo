import React from 'react';
import { Container, Box, Typography, Grid, Card, CardContent, useTheme, alpha } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import CTASection from '../../components/marketing/CTASection';
import PromoBanner from '../../components/marketing/PromoBanner';
import ImagePlaceholder from '../../components/marketing/ImagePlaceholder';
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
                Research-Driven Intelligence
              </Typography>
              <Typography
                variant="body1"
                sx={{
                  fontSize: '1.1rem',
                  color: theme.palette.text.secondary,
                  lineHeight: 1.8,
                }}
              >
                Our AI-powered research platform analyzes markets across multiple dimensions - stocks, earnings, sentiment, technicals, sectors, and macro trends. Get institutional-grade insights in real-time.
              </Typography>
            </Grid>
            <Grid item xs={12} md={6}>
              <ImagePlaceholder
                src="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%271200%27 height=%27400%27%3E%3Crect fill=%27%234a5568%27 width=%271200%27 height=%27400%27/%3E%3Ctext x=%2750%25%27 y=%2750%25%27 font-size=%2732%27 fill=%27white%27 text-anchor=%27middle%27 dominant-baseline=%27middle%27 font-family=%27Arial%27%3EProfessional Market Analysis%3C/text%3E%3C/svg%3E"
                alt="Research Intelligence Dashboard showing data analytics"
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

      {/* How Our Research Works Section */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: theme.palette.background.paper }}>
        <Container maxWidth="lg">
          <Typography
            variant="h3"
            sx={{
              fontSize: { xs: '1.8rem', sm: '2.2rem', md: '2.5rem' },
              fontWeight: 800,
              mb: 2,
              textAlign: 'center',
              color: theme.palette.text.primary,
            }}
          >
            How Bullseye's Research Process Works
          </Typography>
          <Typography
            sx={{
              fontSize: '1.05rem',
              color: theme.palette.text.secondary,
              textAlign: 'center',
              mb: 6,
              maxWidth: '700px',
              mx: 'auto',
            }}
          >
            Our research engine processes comprehensive data through proprietary AI models to deliver actionable intelligence
          </Typography>
          <Grid container spacing={4}>
            {[
              {
                step: '1',
                title: 'Data Integration',
                description: 'We aggregate and normalize data across 6+ dimensions: market data, economic indicators, financial fundamentals, technical patterns, sector dynamics, and sentiment signals.',
              },
              {
                step: '2',
                title: 'AI Analysis',
                description: 'Our machine learning models analyze patterns, correlations, and anomalies across all dimensions simultaneously. Models adapt to changing market conditions in real-time.',
              },
              {
                step: '3',
                title: 'Research Synthesis',
                description: 'Complex AI outputs are synthesized into clear, actionable research insights. We explain the reasoning behind every recommendation.',
              },
              {
                step: '4',
                title: 'Platform Access',
                description: 'All research is available through our platform interface. Institutional clients can access data via API, while advisors and traders use the web platform for analysis and screening.',
              },
            ].map((item, idx) => (
              <Grid item xs={12} sm={6} md={3} key={idx}>
                <Box sx={{ textAlign: 'center' }}>
                  <Box
                    sx={{
                      width: 60,
                      height: 60,
                      borderRadius: '0px',
                      backgroundColor: theme.palette.primary.main,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: '#fff',
                      fontSize: '1.5rem',
                      fontWeight: 'bold',
                      mb: 2,
                      mx: 'auto',
                    }}
                  >
                    {item.step}
                  </Box>
                  <Typography
                    variant="h6"
                    sx={{
                      fontWeight: 700,
                      mb: 1.5,
                      color: theme.palette.text.primary,
                    }}
                  >
                    {item.title}
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{
                      color: theme.palette.text.secondary,
                      lineHeight: 1.6,
                    }}
                  >
                    {item.description}
                  </Typography>
                </Box>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* What Sets Our Research Apart Section */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: alpha(theme.palette.primary.main, 0.04) }}>
        <Container maxWidth="lg">
          <Typography
            variant="h3"
            sx={{
              fontSize: { xs: '1.8rem', sm: '2.2rem', md: '2.5rem' },
              fontWeight: 800,
              mb: 2,
              textAlign: 'center',
              color: theme.palette.text.primary,
            }}
          >
            What Sets Our Research Apart
          </Typography>
          <Typography
            sx={{
              fontSize: '1.05rem',
              color: theme.palette.text.secondary,
              textAlign: 'center',
              mb: 6,
              maxWidth: '700px',
              mx: 'auto',
            }}
          >
            Independent research built on rigorous quantitative analysis and fundamental insights
          </Typography>
          <Grid container spacing={4}>
            {[
              {
                number: '1',
                title: 'Multi-Dimensional Analysis',
                description: 'We combine fundamental analysis, technical research, and quantitative models to provide comprehensive stock coverage. Our approach integrates earnings data, valuation metrics, price action, and sector trends.',
              },
              {
                number: '2',
                title: 'Evidence-Based Methodology',
                description: 'Every signal is backtested against 10+ years of market data. We validate our models against real market outcomes and continuously refine our research process based on performance.',
              },
              {
                number: '3',
                title: 'Institutional-Grade Tools',
                description: 'Access the same caliber of research tools used by professional investors. Our platform provides detailed analytics, stock screening, and portfolio monitoring for serious investors.',
              },
              {
                number: '4',
                title: 'Independent & Transparent',
                description: 'We publish independent research without investment banking conflicts. Our methodology is transparent, and we explain the factors driving our analysis and recommendations.',
              },
            ].map((item, idx) => (
              <Grid item xs={12} sm={6} md={3} key={idx}>
                <Box
                  sx={{
                    backgroundColor: theme.palette.background.paper,
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: '0px',
                    transition: 'all 0.3s ease',
                    overflow: 'hidden',
                    height: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                    '&:hover': {
                      borderColor: theme.palette.primary.main,
                      boxShadow: '0 8px 24px rgba(0,0,0,0.1)',
                      transform: 'translateY(-4px)',
                    },
                  }}
                >
                  <Box
                    sx={{
                      height: { xs: '200px', md: '200px' },
                      background: `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.15)} 0%, ${alpha(theme.palette.secondary.main, 0.1)} 100%)`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <Typography sx={{ color: theme.palette.text.secondary, textAlign: 'center', px: 2, fontSize: '0.9rem' }}>
                      {item.title}
                    </Typography>
                  </Box>
                  <Box sx={{ p: 3, flex: 1, display: 'flex', flexDirection: 'column' }}>
                    <Typography
                      sx={{
                        fontSize: '1.8rem',
                        fontWeight: 800,
                        color: theme.palette.primary.main,
                        mb: 1,
                      }}
                    >
                      {item.number}
                    </Typography>
                    <Typography
                      variant="h6"
                      sx={{
                        fontWeight: 700,
                        mb: 1.5,
                        color: theme.palette.text.primary,
                        fontSize: '1.15rem',
                      }}
                    >
                      {item.title}
                    </Typography>
                    <Typography
                      sx={{
                        color: theme.palette.text.secondary,
                        lineHeight: 1.6,
                        fontSize: '0.95rem',
                        flex: 1,
                      }}
                    >
                      {item.description}
                    </Typography>
                  </Box>
                </Box>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      <PromoBanner
        icon={<InsightsIcon sx={{ color: theme.palette.primary.main }} />}
        title="Ready for Professional-Grade Insights?"
        subtitle="Start leveraging AI-powered research to improve your investment decisions"
        primaryCTA={{ label: 'Launch Platform', href: '/app/market' }}
        secondaryCTA={{ label: 'Schedule Demo', href: '/contact' }}
      />

      <Box sx={{ mx: { xs: 2, md: 4 }, mb: 6 }}>
        <CTASection
          variant="primary"
          title="Unlock Market Intelligence"
          subtitle="Access comprehensive research and insights to stay ahead of the market."
          primaryCTA={{ label: 'Get Started', link: '/app/market' }}
        />
      </Box>
    </MarketingLayout>
  );
};

export default ResearchInsights;
