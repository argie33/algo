import React from 'react';
import { Box, Container, Typography, Grid, alpha, useTheme } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import HeroSection from '../../components/marketing/HeroSection';
import FeatureGrid from '../../components/marketing/FeatureGrid';
import ImagePlaceholder from '../../components/marketing/ImagePlaceholder';
import CTAButtonGroup from '../../components/marketing/CTAButtonGroup';
import CTASection from '../../components/marketing/CTASection';
import {
  TrendingUp as TrendingUpIcon,
  Event as EventIcon,
  Psychology as PsychologyIcon,
  Business as BusinessIcon,
} from '@mui/icons-material';

const Home = () => {
  const theme = useTheme();
  const navigate = useNavigate();

  const stats = [
    { number: '5,300+', label: 'Stocks Analyzed', description: 'Comprehensive US equity coverage' },
    { number: '8', label: 'Analysis Modules', description: 'Market, Sectors, Earnings, Sentiment, and more' },
    { number: 'AI-Powered', label: 'Data Interpretation', description: 'Machine learning for pattern recognition' },
    { number: 'Real-Time', label: 'Market Updates', description: 'Live data feeds and instant insights' },
  ];

  const keyFeatures = [
    {
      icon: <TrendingUpIcon fontSize="large" />,
      title: 'Stock Scoring Dashboard',
      description:
        'AI-powered composite scores analyzing stocks across multiple dimensions with machine learning algorithms.',
      bullets: [
        'Multi-factor AI scoring',
        'Real-time score updates',
        'Comparable metric rankings',
      ],
      tags: ['AI Analysis', 'Scoring', 'Rankings'],
      link: '/app/scores',
    },
    {
      icon: <EventIcon fontSize="large" />,
      title: 'Earnings Calendar',
      description:
        'Track upcoming earnings, view historical data, and analyze earnings surprises and momentum patterns.',
      bullets: [
        'Live earnings calendar',
        'Historical earnings data',
        'Surprise analysis',
      ],
      tags: ['Calendar', 'Historical Data', 'Analysis'],
      link: '/app/earnings',
    },
    {
      icon: <PsychologyIcon fontSize="large" />,
      title: 'Sentiment Analytics',
      description:
        'Analyze market sentiment, analyst positioning, and psychological indicators using AI interpretation.',
      bullets: [
        'Sentiment metrics',
        'Positioning data',
        'AI interpretation',
      ],
      tags: ['Sentiment', 'Psychology', 'AI'],
      link: '/app/sentiment',
    },
    {
      icon: <BusinessIcon fontSize="large" />,
      title: 'Market & Sectors',
      description:
        'Monitor sector rotation, economic indicators, and macro trends with intelligent data analysis.',
      bullets: [
        'Market overview',
        'Sector performance',
        'Economic data tracking',
      ],
      tags: ['Markets', 'Sectors', 'Macro'],
      link: '/app/market',
    },
  ];

  return (
    <MarketingLayout>
      {/* Hero Section */}
      <HeroSection />

      {/* Stats Section */}
      <Box
        sx={{
          py: { xs: 6, md: 8 },
          backgroundColor: theme.palette.background.default,
          borderTop: `1px solid ${alpha(theme.palette.divider, 0.5)}`,
          borderBottom: `1px solid ${alpha(theme.palette.divider, 0.5)}`,
        }}
      >
        <Container maxWidth="lg">
          <Grid container spacing={{ xs: 3, md: 4 }}>
            {stats.map((stat, idx) => (
              <Grid item xs={6} sm={6} md={3} key={idx}>
                <Box sx={{ textAlign: 'center', py: 2 }}>
                  <Typography
                    sx={{
                      fontSize: { xs: '2rem', sm: '2.5rem', md: '2.8rem' },
                      fontWeight: 700,
                      color: theme.palette.primary.main,
                      mb: 0.5,
                      letterSpacing: '-0.5px',
                    }}
                  >
                    {stat.number}
                  </Typography>
                  <Typography
                    sx={{
                      fontSize: { xs: '0.95rem', sm: '1rem', md: '1.05rem' },
                      fontWeight: 600,
                      color: theme.palette.text.primary,
                      mb: 0.75,
                    }}
                  >
                    {stat.label}
                  </Typography>
                  <Typography
                    sx={{
                      fontSize: '0.85rem',
                      color: theme.palette.text.secondary,
                      lineHeight: 1.5,
                    }}
                  >
                    {stat.description}
                  </Typography>
                </Box>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Key Features */}
      <FeatureGrid
        title="Powerful Analysis Capabilities"
        subtitle="Everything you need to make informed investment decisions"
        features={keyFeatures}
        columns={{ xs: 1, sm: 2, md: 2, lg: 2 }}
      />

      {/* Why Choose Bullseye Section */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: theme.palette.background.paper }}>
        <Container maxWidth="lg">
          <Grid container spacing={{ xs: 4, md: 6 }} alignItems="center">
            {/* Left Content */}
            <Grid item xs={12} md={6}>
              <Typography
                variant="h3"
                sx={{
                  fontSize: { xs: '1.8rem', sm: '2.2rem', md: '2.5rem' },
                  fontWeight: 800,
                  mb: 3,
                  color: theme.palette.text.primary,
                }}
              >
                Why Choose Bullseye Financial
              </Typography>
              <Typography
                variant="body1"
                sx={{
                  fontSize: '1.05rem',
                  color: theme.palette.text.secondary,
                  mb: 2.5,
                  lineHeight: 1.8,
                }}
              >
                Professional investors and traders rely on Bullseye Financial for advanced AI-powered market analysis. Our platform combines artificial intelligence with real-time data to deliver actionable insights you won&apos;t find elsewhere.
              </Typography>
              <Box sx={{ mb: 3 }}>
                {[
                  'AI-driven analysis across 8 different market dimensions',
                  'Real-time data feeds with institutional-grade accuracy',
                  'Machine learning models trained on years of market data',
                  'Intuitive interface for both professionals and active traders',
                ].map((item, idx) => (
                  <Box
                    key={idx}
                    sx={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      mb: 2,
                    }}
                  >
                    <Box
                      sx={{
                        width: 24,
                        height: 24,
                        borderRadius: '50%',
                        backgroundColor: theme.palette.primary.main,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#fff',
                        fontSize: '0.8rem',
                        fontWeight: 'bold',
                        flexShrink: 0,
                        mr: 2,
                        mt: 0.3,
                      }}
                    >
                      ✓
                    </Box>
                    <Typography sx={{ color: theme.palette.text.secondary, fontSize: '1rem' }}>
                      {item}
                    </Typography>
                  </Box>
                ))}
              </Box>
              <CTAButtonGroup
                primaryCTA={{ label: 'Start Analyzing Now', link: '/app/market' }}
                centered={false}
              />
            </Grid>

            {/* Right Image */}
            <Grid item xs={12} md={6}>
              <ImagePlaceholder
                src="https://images.unsplash.com/photo-1552664730-d307ca884978?w=600&h=450&fit=crop"
                alt="Professional Analysis"
              />
            </Grid>
          </Grid>
        </Container>
      </Box>

      {/* How It Works Section */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: theme.palette.background.default }}>
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
            How Bullseye Works
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
            Our platform processes real-time market data through advanced AI models to deliver comprehensive analysis
          </Typography>
          <Grid container spacing={4}>
            {[
              {
                step: '1',
                title: 'Real-Time Data Collection',
                description: 'We aggregate data from multiple sources including stock prices, earnings reports, analyst sentiment, and economic indicators in real-time.',
              },
              {
                step: '2',
                title: 'AI Processing & Analysis',
                description: 'Our machine learning models analyze patterns across 8 different dimensions simultaneously, identifying opportunities and risks.',
              },
              {
                step: '3',
                title: 'Actionable Insights',
                description: 'Complex analysis is synthesized into clear, actionable insights you can use immediately for investment decisions.',
              },
              {
                step: '4',
                title: 'Continuous Learning',
                description: 'Our AI models continuously learn from market outcomes, becoming smarter and more accurate over time.',
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

      {/* CTA Section */}
      <CTASection
        variant="dark"
        title="Ready to Explore?"
        subtitle="Get access to institutional-grade market intelligence and start analyzing stocks like a professional."
        primaryCTA={{ label: 'Launch Platform', link: '/app/market' }}
        secondaryCTA={{ label: 'View All Services', link: '/services' }}
      />
    </MarketingLayout>
  );
};

export default Home;
