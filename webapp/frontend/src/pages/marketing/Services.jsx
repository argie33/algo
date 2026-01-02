import React from 'react';
import { Container, Box, Typography, useTheme, Grid, alpha, Card, CardContent } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import FeatureGrid from '../../components/marketing/FeatureGrid';
import CTASection from '../../components/marketing/CTASection';
import PromoBanner from '../../components/marketing/PromoBanner';
import { Rocket as RocketIcon } from '@mui/icons-material';
import {
  Star as StarIcon,
  Event as EventIcon,
  Psychology as PsychologyIcon,
  TrendingUp as TrendingUpIcon,
  Business as BusinessIcon,
  Public as PublicIcon,
  ShowChart as ShowChartIcon,
  HealthAndSafety as HealthAndSafetyIcon,
  Timeline as TimelineIcon,
} from '@mui/icons-material';

const Services = () => {
  const theme = useTheme();

  const allCapabilities = [
    {
      icon: <StarIcon fontSize="large" />,
      title: 'Stock Scoring',
      description:
        'AI-powered composite scoring system analyzing stocks across multiple dimensions using machine learning.',
      bullets: [
        'AI-generated composite scores',
        'Real-time updates',
        'Comparable rankings',
      ],
      tags: ['AI', 'Scoring', 'ML'],
      link: '/app/scores',
    },
    {
      icon: <EventIcon fontSize="large" />,
      title: 'Earnings Calendar',
      description:
        'Track upcoming earnings announcements, view historical data, and analyze earnings surprises.',
      bullets: [
        'Live earnings calendar',
        'Historical earnings data',
        'Surprise patterns',
      ],
      tags: ['Calendar', 'Data', 'Analysis'],
      link: '/app/earnings',
    },
    {
      icon: <PsychologyIcon fontSize="large" />,
      title: 'Sentiment Analytics',
      description:
        'AI-interpreted sentiment data, analyst positioning, and market psychology indicators.',
      bullets: [
        'Sentiment metrics',
        'Positioning analysis',
        'AI interpretation',
      ],
      tags: ['Sentiment', 'AI', 'Psychology'],
      link: '/app/sentiment',
    },
    {
      icon: <TimelineIcon fontSize="large" />,
      title: 'Trading Signals',
      description:
        'Technical analysis with price action tracking and AI-generated trading signals.',
      bullets: [
        'Technical indicators',
        'AI signal generation',
        'Price analysis',
      ],
      tags: ['Technicals', 'AI', 'Signals'],
      link: '/app/trading-signals',
    },
    {
      icon: <BusinessIcon fontSize="large" />,
      title: 'Sector Analysis',
      description:
        'Monitor sector performance, relative strength, and economic sector trends.',
      bullets: [
        'Sector performance',
        'Relative strength',
        'Market overview',
      ],
      tags: ['Sectors', 'Analysis', 'Markets'],
      link: '/app/sectors',
    },
    {
      icon: <PublicIcon fontSize="large" />,
      title: 'Economic Indicators',
      description:
        'Track key economic indicators, market conditions, and macro data.',
      bullets: [
        'Economic data',
        'Market overview',
        'Trend analysis',
      ],
      tags: ['Macro', 'Economics', 'Indicators'],
      link: '/app/economic',
    },
    {
      icon: <ShowChartIcon fontSize="large" />,
      title: 'Market Overview',
      description:
        'Real-time market data, breadth analysis, and overall market health metrics.',
      bullets: [
        'Market data',
        'Breadth analysis',
        'Performance tracking',
      ],
      tags: ['Markets', 'Data', 'Analysis'],
      link: '/app/market',
    },
    {
      icon: <HealthAndSafetyIcon fontSize="large" />,
      title: 'Hedge Helper',
      description:
        'AI-powered hedging suggestions and risk management strategies for portfolios.',
      bullets: [
        'Hedge suggestions',
        'Risk analysis',
        'Portfolio protection',
      ],
      tags: ['Hedging', 'AI', 'Risk'],
      link: '/app/hedge-helper',
    },
  ];

  return (
    <MarketingLayout>
      {/* Header */}
      <PageHeader
        title="Our Services"
        subtitle="Eight comprehensive analysis dimensions to give you a complete view of the market, stocks, and economic conditions."
      />

      {/* Visual Showcase - Key Services */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: theme.palette.background.paper }}>
        <Container maxWidth="lg">
          <Typography
            variant="h3"
            sx={{
              fontSize: { xs: '1.8rem', sm: '2.2rem', md: '2.5rem' },
              fontWeight: 800,
              mb: 1,
              color: theme.palette.text.primary,
              textAlign: 'center',
            }}
          >
            Core Capabilities
          </Typography>
          <Typography
            sx={{
              fontSize: '1.05rem',
              color: theme.palette.text.secondary,
              textAlign: 'center',
              mb: 6,
              maxWidth: '600px',
              mx: 'auto',
            }}
          >
            Professional-grade analysis tools for every dimension of market research
          </Typography>

          {/* Featured Services with Images */}
          <Grid container spacing={4} sx={{ mb: 8 }}>
            {[
              {
                title: 'Stock Scoring',
                desc: 'Multi-factor composite analysis',
                image: 'https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=600&h=400&fit=crop'
              },
              {
                title: 'Earnings Intel',
                desc: 'Real-time estimate tracking',
                image: 'https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=600&h=400&fit=crop'
              },
              {
                title: 'Sentiment Data',
                desc: 'Market psychology analysis',
                image: 'https://images.unsplash.com/photo-1552664730-d307ca884978?w=600&h=400&fit=crop'
              },
              {
                title: 'Technical Analysis',
                desc: 'Price action and signals',
                image: 'https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?w=600&h=400&fit=crop'
              },
            ].map((service, idx) => (
              <Grid item xs={12} sm={6} md={6} lg={3} key={idx}>
                <Box
                  sx={{
                    height: '280px',
                    background: `linear-gradient(135deg, ${theme.palette.primary.main}10 0%, ${theme.palette.primary.main}05 100%)`,
                    border: `1px solid ${alpha(theme.palette.divider, 0.5)}`,
                    borderRadius: '0px',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'flex-end',
                    padding: 0,
                    textAlign: 'center',
                    cursor: 'pointer',
                    transition: 'all 0.3s ease',
                    overflow: 'hidden',
                    position: 'relative',
                    '&:hover': {
                      borderColor: alpha(theme.palette.primary.main, 0.4),
                      boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
                      '& .service-overlay': {
                        backgroundColor: alpha('#000', 0.55),
                      },
                    },
                  }}
                >
                  {/* Background Image */}
                  <Box
                    component="img"
                    src={service.image}
                    alt={service.title}
                    onError={(e) => {
                      e.target.style.display = 'none';
                    }}
                    sx={{
                      position: 'absolute',
                      inset: 0,
                      width: '100%',
                      height: '100%',
                      objectFit: 'cover',
                      zIndex: 0,
                    }}
                  />
                  {/* Overlay */}
                  <Box
                    className="service-overlay"
                    sx={{
                      position: 'absolute',
                      inset: 0,
                      backgroundColor: alpha('#000', 0.4),
                      transition: 'all 0.3s ease',
                      zIndex: 1,
                    }}
                  />
                  {/* Content */}
                  <Box sx={{ position: 'relative', zIndex: 2, p: 3 }}>
                    <Typography
                      variant="h6"
                      sx={{
                        fontWeight: 700,
                        color: '#fff',
                        mb: 0.5,
                        textShadow: '0 2px 4px rgba(0,0,0,0.3)',
                      }}
                    >
                      {service.title}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        color: '#fff',
                        textShadow: '0 1px 2px rgba(0,0,0,0.3)',
                      }}
                    >
                      {service.desc}
                    </Typography>
                  </Box>
                </Box>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Services Grid */}
      <FeatureGrid
        features={allCapabilities}
        columns={{ xs: 1, sm: 2, md: 3, lg: 3 }}
      />

      {/* Detailed Benefits Section */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: '#f8f9fa' }}>
        <Container maxWidth="lg">
          <Typography
            variant="h3"
            sx={{
              fontSize: { xs: '1.8rem', sm: '2.2rem', md: '2.5rem' },
              fontWeight: 800,
              mb: 2,
              color: theme.palette.text.primary,
            }}
          >
            Why Professional Investors Choose Bullseye
          </Typography>
          <Typography
            sx={{
              fontSize: '1.05rem',
              color: theme.palette.text.secondary,
              mb: 6,
              maxWidth: '800px',
            }}
          >
            Our comprehensive analysis platform delivers the intelligence you need to make confident investment decisions
          </Typography>
          <Grid container spacing={4}>
            {[
              {
                benefit: 'Save Time',
                detail: 'Analyze multiple dimensions in seconds instead of hours. Our AI does the heavy lifting so you can focus on strategy.',
              },
              {
                benefit: 'Reduce Risk',
                detail: 'Identify risks before they materialize. Our multi-factor analysis reveals hidden correlations and warning signs.',
              },
              {
                benefit: 'Beat Consensus',
                detail: 'Our AI uncovers opportunities before the market recognizes them. Stay ahead of the crowd with proprietary analysis.',
              },
              {
                benefit: 'Trade Smarter',
                detail: 'Real-time signals and technical analysis help you execute at optimal entry and exit points.',
              },
              {
                benefit: 'Manage Portfolios',
                detail: 'Monitor sector rotation, macro trends, and hedging opportunities across your entire portfolio.',
              },
              {
                benefit: 'Learn Constantly',
                detail: 'Our platform evolves with the market. AI models continuously learn and improve from every trade and outcome.',
              },
            ].map((item, idx) => (
              <Grid item xs={12} sm={6} md={4} key={idx}>
                <Box
                  sx={{
                    p: 3,
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: '0px',
                    backgroundColor: theme.palette.background.paper,
                    transition: 'all 0.3s ease',
                    '&:hover': {
                      boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
                      transform: 'translateY(-2px)',
                    },
                  }}
                >
                  <Typography
                    variant="h6"
                    sx={{
                      fontWeight: 700,
                      mb: 1.5,
                      color: theme.palette.primary.main,
                    }}
                  >
                    {item.benefit}
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{
                      color: theme.palette.text.secondary,
                      lineHeight: 1.7,
                    }}
                  >
                    {item.detail}
                  </Typography>
                </Box>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Use Cases Section */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: theme.palette.background.paper }}>
        <Container maxWidth="lg">
          <Typography
            variant="h3"
            sx={{
              fontSize: { xs: '1.8rem', sm: '2.2rem', md: '2.5rem' },
              fontWeight: 800,
              mb: 6,
              textAlign: 'center',
              color: theme.palette.text.primary,
            }}
          >
            Built for Different Strategies
          </Typography>
          <Grid container spacing={4}>
            {[
              {
                strategy: 'Active Traders',
                use: 'Use real-time signals and technical analysis to identify entry/exit points and maximize profit on intraday moves.',
              },
              {
                strategy: 'Swing Traders',
                use: 'Leverage sentiment shifts and momentum indicators to catch 3-5 day moves with precision timing.',
              },
              {
                strategy: 'Value Investors',
                use: 'Analyze fundamental metrics and valuation alongside sentiment to find undervalued opportunities.',
              },
              {
                strategy: 'Portfolio Managers',
                use: 'Monitor sector rotation, macro trends, and economic indicators to optimize asset allocation.',
              },
              {
                strategy: 'Risk Managers',
                use: 'Use hedging strategies and risk metrics to protect portfolios from market downturns.',
              },
              {
                strategy: 'Growth Investors',
                use: 'Identify emerging trends and growth catalysts before they become mainstream.',
              },
            ].map((item, idx) => (
              <Grid item xs={12} sm={6} md={4} key={idx}>
                <Card
                  sx={{
                    height: '100%',
                    border: `1px solid ${theme.palette.divider}`,
                    backgroundColor: theme.palette.background.paper,
                    borderRadius: '0px',
                    transition: 'all 0.3s ease',
                    '&:hover': {
                      borderColor: alpha(theme.palette.primary.main, 0.5),
                      boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
                    },
                  }}
                >
                  <CardContent>
                    <Typography
                      variant="h6"
                      sx={{
                        fontWeight: 700,
                        mb: 2,
                        color: theme.palette.primary.main,
                      }}
                    >
                      {item.strategy}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        color: theme.palette.text.secondary,
                        lineHeight: 1.7,
                      }}
                    >
                      {item.use}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Promotional Banner */}
      <PromoBanner
        icon={<RocketIcon sx={{ color: theme.palette.primary.main }} />}
        title="Ready to Get Started?"
        subtitle="Explore our AI-powered analysis platform and start making informed investment decisions today."
        primaryCTA={{ label: 'Launch Platform', href: '/app/market' }}
        secondaryCTA={{ label: 'Schedule Demo', href: '/become-client' }}
      />

      {/* CTA Section */}
      <Box sx={{ mx: { xs: 2, md: 4 }, mb: 6 }}>
        <CTASection
          variant="primary"
          title="Start Analyzing Today"
          subtitle="Access all analysis dimensions immediately with our comprehensive platform."
          primaryCTA={{ label: 'Explore Platform', link: '/app/market' }}
          secondaryCTA={{ label: 'Learn About Us', link: '/firm' }}
        />
      </Box>
    </MarketingLayout>
  );
};

export default Services;
