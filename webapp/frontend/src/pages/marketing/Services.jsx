import React from 'react';
import { Container, Box, Typography, useTheme, Grid, alpha, Card, CardContent } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import CTASection from '../../components/marketing/CTASection';
import PromoBanner from '../../components/marketing/PromoBanner';
import { Rocket as RocketIcon, TrendingUp as TrendingUpIcon } from '@mui/icons-material';
import {
  Star as StarIcon,
  Event as EventIcon,
  Psychology as PsychologyIcon,
  Business as BusinessIcon,
  Public as PublicIcon,
  ShowChart as ShowChartIcon,
  HealthAndSafety as HealthAndSafetyIcon,
  Timeline as TimelineIcon,
  DataUsage as DataUsageIcon,
} from '@mui/icons-material';

const Services = () => {
  const theme = useTheme();

  const researchDimensions = [
    {
      icon: <StarIcon fontSize="large" />,
      title: 'AI-Powered Stock Analysis',
      subtitle: 'Composite Scoring & Multi-Factor Evaluation',
      description:
        'Our proprietary machine learning model analyzes each stock across multiple dimensions—fundamentals, technicals, sentiment, and valuation—to generate comprehensive composite scores. The AI engine identifies patterns and correlations invisible to traditional analysis.',
      details: [
        'Multi-factor composite scoring engine',
        'Real-time score updates as market data changes',
        'Comparative ranking across all covered stocks',
        'Underlying factor breakdown and transparency',
        'Historical score trends and performance tracking',
      ],
      dataTypes: ['Fundamentals', 'Technicals', 'Sentiment', 'Valuations'],
      image: 'https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=600&h=400&fit=crop',
      ideal: 'Portfolio managers, active traders, value investors',
    },
    {
      icon: <EventIcon fontSize="large" />,
      title: 'Earnings Intelligence System',
      subtitle: 'Estimate Tracking & Surprise Analysis',
      description:
        'Our earnings intelligence platform processes historical earnings data spanning 10+ years to identify surprise patterns, estimate revision trends, and forward-looking catalysts. Machine learning models predict earnings surprises before they occur.',
      details: [
        'Live earnings calendar with analyst estimates',
        '10+ years of historical earnings data',
        'Earnings surprise pattern analysis',
        'Estimate revision tracking and trends',
        'Forward earnings surprise predictions',
        'Management guidance analysis',
      ],
      dataTypes: ['Financial Data', 'Analyst Estimates', 'Historical Patterns', 'Macro Context'],
      image: 'https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=600&h=400&fit=crop',
      ideal: 'Fundamental analysts, earnings-focused traders, fund managers',
    },
    {
      icon: <PsychologyIcon fontSize="large" />,
      title: 'Sentiment & Positioning Analytics',
      subtitle: 'Market Psychology & Institutional Positioning',
      description:
        'We analyze sentiment data from multiple sources—analyst ratings, positioning metrics, and market psychology signals—to reveal hidden market shifts and investor sentiment extremes. AI interprets these signals to identify contrarian opportunities.',
      details: [
        'Analyst rating analysis and change tracking',
        'Institutional positioning metrics',
        'Sentiment extremes identification',
        'Contrarian signal detection',
        'Market psychology interpretation',
        'Positioning divergence analysis',
      ],
      dataTypes: ['Analyst Sentiment', 'Positioning Data', 'Market Psychology', 'Alternative Signals'],
      image: 'https://images.unsplash.com/photo-1552664730-d307ca884978?w=600&h=400&fit=crop',
      ideal: 'Contrarian investors, sentiment-driven traders, macro strategists',
    },
    {
      icon: <TimelineIcon fontSize="large" />,
      title: 'Technical Analysis & Trading Signals',
      subtitle: 'Price Action & AI-Generated Signals',
      description:
        'Our technical analysis engine combines traditional price action analysis with AI-powered pattern recognition to generate real-time trading signals. Machine learning models identify optimal entry and exit points based on technical patterns and momentum.',
      details: [
        'Advanced technical indicators and patterns',
        'AI-generated buy/sell signals',
        'Support and resistance level detection',
        'Momentum and breadth analysis',
        'Volume and liquidity analysis',
        'Price pattern recognition',
      ],
      dataTypes: ['Price Data', 'Volume', 'Technical Patterns', 'Momentum Indicators'],
      image: 'https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?w=600&h=400&fit=crop',
      ideal: 'Active traders, swing traders, day traders, technical analysts',
    },
    {
      icon: <BusinessIcon fontSize="large" />,
      title: 'Sector & Industry Research',
      subtitle: 'Rotation Analysis & Relative Strength',
      description:
        'Track sector rotation, relative strength, and industry-specific trends. Our AI monitors macro data and economic indicators to identify which sectors are likely to outperform. Real-time sector momentum and rotation signals guide allocation decisions.',
      details: [
        'Sector performance tracking and ranking',
        'Relative strength analysis',
        'Sector rotation signals',
        'Industry trend identification',
        'Competitive positioning analysis',
        'Macro-to-sector mapping',
      ],
      dataTypes: ['Market Data', 'Economic Indicators', 'Industry Data', 'Macro Trends'],
      image: 'https://images.unsplash.com/photo-1611432579699-484f7990f17a?w=600&h=400&fit=crop',
      ideal: 'Portfolio managers, asset allocators, strategic investors',
    },
    {
      icon: <Public as PublicIcon fontSize="large" />,
      title: 'Economic & Macro Intelligence',
      subtitle: 'Macro Trends & Economic Impact Analysis',
      description:
        'Monitor key economic indicators, macro trends, and their direct impact on markets and individual stocks. Our platform integrates employment data, GDP trends, inflation metrics, and Fed policy to provide comprehensive macro context for investment decisions.',
      details: [
        'Key economic indicator tracking',
        'Macro trend analysis and forecasting',
        'Federal Reserve policy monitoring',
        'Economic impact on sector/stock performance',
        'Leading vs. lagging indicator analysis',
        'Cross-asset correlations',
      ],
      dataTypes: ['Economic Data', 'Fed Signals', 'Policy Analysis', 'Market Data'],
      image: 'https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=600&h=400&fit=crop',
      ideal: 'Macro strategists, portfolio managers, economic analysts',
    },
    {
      icon: <ShowChartIcon fontSize="large" />,
      title: 'Market & Portfolio Overview',
      subtitle: 'Breadth Analysis & Market Health',
      description:
        'Comprehensive market overview tools provide real-time insights into overall market health, breadth analysis, and portfolio positioning. Monitor market participation, momentum, and relative performance across asset classes.',
      details: [
        'Market breadth indicators',
        'Advance/decline analysis',
        'Market momentum metrics',
        'Portfolio performance tracking',
        'Risk metrics and VIX analysis',
        'Market regime identification',
      ],
      dataTypes: ['Market Data', 'Breadth Data', 'Volatility Metrics', 'Performance Data'],
      image: 'https://images.unsplash.com/photo-1535320903710-d4fdf713ebcb?w=600&h=400&fit=crop',
      ideal: 'Portfolio managers, risk managers, market strategists',
    },
    {
      icon: <HealthAndSafetyIcon fontSize="large" />,
      title: 'Hedge Helper & Risk Management',
      subtitle: 'Portfolio Protection & Risk Analysis',
      description:
        'AI-powered hedging recommendations and portfolio protection strategies. Identify optimal hedging instruments and timing based on risk metrics, market regime, and portfolio composition. Manage downside risk while maintaining upside potential.',
      details: [
        'Risk metric calculations',
        'Hedging strategy recommendations',
        'Put option analysis',
        'Correlation analysis',
        'Portfolio stress testing',
        'Max drawdown analysis',
      ],
      dataTypes: ['Portfolio Data', 'Options Data', 'Risk Metrics', 'Correlations'],
      image: 'https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?w=600&h=400&fit=crop',
      ideal: 'Risk managers, wealth managers, institutional investors',
    },
  ];

  const clientOfferings = [
    {
      client: 'Institutional Investors',
      description: 'Asset managers, hedge funds, institutional advisors',
      research: [
        'Enterprise research data feeds',
        'Customized analysis dashboards',
        'Dedicated research team support',
        'API access for integration',
        'Custom report generation',
        'Performance attribution',
      ],
    },
    {
      client: 'Wealth Advisors & RIAs',
      description: 'Financial advisors, wealth managers, portfolio managers',
      research: [
        'Client-ready research reports',
        'Customizable analysis tools',
        'Portfolio monitoring dashboards',
        'Client communication materials',
        'Co-branded research',
        'Advisor education programs',
      ],
    },
    {
      client: 'Active Investors',
      description: 'Individual traders, active investors, sophisticated investors',
      research: [
        'Real-time stock analysis',
        'Trading signals and alerts',
        'Portfolio optimization tools',
        'Educational research content',
        'Technical analysis courses',
        'Community insights',
      ],
    },
  ];

  return (
    <MarketingLayout>
      {/* Header */}
      <PageHeader
        title="Professional Research & Advisory Services"
        subtitle="Six comprehensive research dimensions powering institutional-grade analysis and customized advisory solutions"
      />

      {/* Research Philosophy Section */}
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
            Our Research Approach
          </Typography>
          <Typography
            sx={{
              fontSize: '1.05rem',
              color: theme.palette.text.secondary,
              textAlign: 'center',
              mb: 6,
              maxWidth: '800px',
              mx: 'auto',
              lineHeight: 1.8,
            }}
          >
            We combine deep market knowledge with cutting-edge artificial intelligence and big data quantitative techniques to analyze six independent research dimensions. This multi-dimensional approach reveals opportunities and risks that traditional analysis misses.
          </Typography>

          <Grid container spacing={4}>
            {[
              {
                number: '6',
                label: 'Research Dimensions',
                detail: 'Fundamentals, Technicals, Sentiment, Macro, Sector, Positioning',
              },
              {
                number: '10+',
                label: 'Years of Data',
                detail: 'Historical perspective for pattern recognition',
              },
              {
                number: '5,300+',
                label: 'Stocks Analyzed',
                detail: 'Comprehensive US equity coverage',
              },
              {
                number: '24/7',
                label: 'Real-Time Updates',
                detail: 'Continuous data feeds and AI analysis',
              },
            ].map((item, idx) => (
              <Grid item xs={12} sm={6} md={3} key={idx}>
                <Card
                  sx={{
                    height: '100%',
                    border: `1px solid ${theme.palette.divider}`,
                    backgroundColor: theme.palette.background.paper,
                    borderRadius: '0px',
                    transition: 'all 0.3s ease',
                    '&:hover': {
                      boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
                      borderColor: theme.palette.primary.main,
                    },
                  }}
                >
                  <CardContent sx={{ textAlign: 'center', p: 3 }}>
                    <Typography
                      sx={{
                        fontSize: '2.5rem',
                        fontWeight: 700,
                        color: theme.palette.primary.main,
                        mb: 0.5,
                      }}
                    >
                      {item.number}
                    </Typography>
                    <Typography
                      sx={{
                        fontWeight: 600,
                        color: theme.palette.text.primary,
                        mb: 1,
                      }}
                    >
                      {item.label}
                    </Typography>
                    <Typography
                      sx={{
                        fontSize: '0.9rem',
                        color: theme.palette.text.secondary,
                        lineHeight: 1.5,
                      }}
                    >
                      {item.detail}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Detailed Research Dimensions */}
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
            Our Research Dimensions
          </Typography>
          <Typography
            sx={{
              fontSize: '1.05rem',
              color: theme.palette.text.secondary,
              textAlign: 'center',
              mb: 6,
              maxWidth: '800px',
              mx: 'auto',
            }}
          >
            Professional-grade research across eight independent market analysis dimensions
          </Typography>

          {researchDimensions.map((dimension, idx) => (
            <Box
              key={idx}
              sx={{
                mb: 6,
                pb: 6,
                borderBottom: idx < researchDimensions.length - 1 ? `1px solid ${theme.palette.divider}` : 'none',
              }}
            >
              <Grid container spacing={4} alignItems="flex-start">
                {/* Left Content */}
                <Grid item xs={12} md={6}>
                  <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 2, mb: 3 }}>
                    <Box sx={{ color: theme.palette.primary.main, flexShrink: 0 }}>
                      {dimension.icon}
                    </Box>
                    <Box>
                      <Typography
                        variant="h5"
                        sx={{
                          fontWeight: 700,
                          color: theme.palette.text.primary,
                          mb: 0.5,
                        }}
                      >
                        {dimension.title}
                      </Typography>
                      <Typography
                        sx={{
                          color: theme.palette.primary.main,
                          fontWeight: 600,
                          fontSize: '0.95rem',
                          mb: 2,
                        }}
                      >
                        {dimension.subtitle}
                      </Typography>
                    </Box>
                  </Box>

                  <Typography
                    sx={{
                      fontSize: '1rem',
                      color: theme.palette.text.secondary,
                      mb: 2.5,
                      lineHeight: 1.8,
                    }}
                  >
                    {dimension.description}
                  </Typography>

                  <Typography
                    sx={{
                      fontWeight: 600,
                      color: theme.palette.text.primary,
                      mb: 1.5,
                      fontSize: '0.9rem',
                      textTransform: 'uppercase',
                      letterSpacing: 0.5,
                    }}
                  >
                    Key Capabilities:
                  </Typography>
                  <Box component="ul" sx={{ pl: 2, m: 0, mb: 3 }}>
                    {dimension.details.map((detail, didx) => (
                      <Typography
                        component="li"
                        key={didx}
                        sx={{
                          color: theme.palette.text.secondary,
                          fontSize: '0.95rem',
                          mb: 1,
                          lineHeight: 1.6,
                        }}
                      >
                        {detail}
                      </Typography>
                    ))}
                  </Box>

                  <Box>
                    <Typography
                      sx={{
                        fontWeight: 600,
                        color: theme.palette.text.primary,
                        mb: 1,
                        fontSize: '0.9rem',
                      }}
                    >
                      Data Types: {dimension.dataTypes.join(', ')}
                    </Typography>
                    <Typography
                      sx={{
                        fontWeight: 600,
                        color: theme.palette.primary.main,
                        fontSize: '0.9rem',
                      }}
                    >
                      Ideal for: {dimension.ideal}
                    </Typography>
                  </Box>
                </Grid>

                {/* Right Image */}
                <Grid item xs={12} md={6}>
                  <Box
                    component="img"
                    src={dimension.image}
                    alt={dimension.title}
                    sx={{
                      width: '100%',
                      height: 350,
                      objectFit: 'cover',
                      border: `1px solid ${theme.palette.divider}`,
                      borderRadius: '0px',
                    }}
                    onError={(e) => {
                      e.target.style.display = 'none';
                    }}
                  />
                </Grid>
              </Grid>
            </Box>
          ))}
        </Container>
      </Box>

      {/* Customized Solutions by Client Type */}
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
            Customized Research Solutions
          </Typography>
          <Typography
            sx={{
              fontSize: '1.05rem',
              color: theme.palette.text.secondary,
              textAlign: 'center',
              mb: 6,
              maxWidth: '800px',
              mx: 'auto',
            }}
          >
            Different investor types require different research and advisory approaches. We customize our research offerings for each client segment.
          </Typography>

          <Grid container spacing={4}>
            {clientOfferings.map((offering, idx) => (
              <Grid item xs={12} md={4} key={idx}>
                <Card
                  sx={{
                    height: '100%',
                    border: `1px solid ${theme.palette.divider}`,
                    backgroundColor: theme.palette.background.paper,
                    borderRadius: '0px',
                    transition: 'all 0.3s ease',
                    '&:hover': {
                      boxShadow: '0 6px 16px rgba(0,0,0,0.1)',
                      transform: 'translateY(-4px)',
                    },
                  }}
                >
                  <CardContent sx={{ p: 4 }}>
                    <Typography
                      variant="h6"
                      sx={{
                        fontWeight: 700,
                        mb: 0.5,
                        color: theme.palette.text.primary,
                        fontSize: '1.25rem',
                      }}
                    >
                      {offering.client}
                    </Typography>
                    <Typography
                      sx={{
                        color: theme.palette.text.secondary,
                        mb: 3,
                        fontSize: '0.95rem',
                      }}
                    >
                      {offering.description}
                    </Typography>
                    <Typography
                      sx={{
                        fontWeight: 600,
                        color: theme.palette.text.primary,
                        mb: 2,
                        fontSize: '0.9rem',
                        textTransform: 'uppercase',
                        letterSpacing: 0.5,
                      }}
                    >
                      Research Offerings:
                    </Typography>
                    <Box component="ul" sx={{ pl: 2, m: 0 }}>
                      {offering.research.map((item, ridx) => (
                        <Typography
                          component="li"
                          key={ridx}
                          sx={{
                            color: theme.palette.text.secondary,
                            fontSize: '0.9rem',
                            mb: 1,
                            lineHeight: 1.5,
                          }}
                        >
                          {item}
                        </Typography>
                      ))}
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Platform Preview */}
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
            See Bullseye's Research Platform In Action
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
            Professional research tools powered by AI and big data analytics
          </Typography>
          <Grid container spacing={4}>
            {[
              {
                title: 'Multi-Dimensional Stock Research',
                desc: 'AI-powered composite analysis across fundamentals, technicals, sentiment, and macro',
                image: 'https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=600&h=400&fit=crop',
              },
              {
                title: 'Research Data Dashboards',
                desc: 'Customizable dashboards for institutions, advisors, and active investors',
                image: 'https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=600&h=400&fit=crop',
              },
              {
                title: 'Real-Time Research Updates',
                desc: 'Continuous data processing and AI analysis for actionable market intelligence',
                image: 'https://images.unsplash.com/photo-1552664730-d307ca884978?w=600&h=400&fit=crop',
              },
            ].map((item, idx) => (
              <Grid item xs={12} md={4} key={idx}>
                <Box
                  sx={{
                    position: 'relative',
                    overflow: 'hidden',
                    borderRadius: '0px',
                    border: `1px solid ${theme.palette.divider}`,
                    transition: 'all 0.3s ease',
                    '&:hover': {
                      boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
                      transform: 'translateY(-4px)',
                    },
                  }}
                >
                  <Box
                    component="img"
                    src={item.image}
                    alt={item.title}
                    sx={{
                      width: '100%',
                      height: 280,
                      objectFit: 'cover',
                      display: 'block',
                    }}
                    onError={(e) => {
                      e.target.style.display = 'none';
                    }}
                  />
                  <Box
                    sx={{
                      p: 3,
                      backgroundColor: theme.palette.background.paper,
                      borderTop: `1px solid ${theme.palette.divider}`,
                    }}
                  >
                    <Typography
                      variant="h6"
                      sx={{
                        fontWeight: 700,
                        mb: 1,
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
                      {item.desc}
                    </Typography>
                  </Box>
                </Box>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Why Choose Bullseye Research */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: theme.palette.background.default }}>
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
            Why Choose Bullseye for Your Research
          </Typography>

          <Grid container spacing={4}>
            {[
              {
                title: 'AI & Machine Learning Advantage',
                description: 'Our proprietary ML models identify patterns and correlations across 10+ years of data that traditional analysis misses.',
              },
              {
                title: 'Multi-Dimensional Analysis',
                description: 'We analyze 6+ independent dimensions simultaneously, providing comprehensive market perspective.',
              },
              {
                title: 'Evidence-Based Research',
                description: 'Every analysis is rigorously tested and validated. We focus on data-driven insights, not opinions.',
              },
              {
                title: 'Customized Solutions',
                description: 'Different investors need different research. We tailor offerings for institutions, advisors, and individuals.',
              },
              {
                title: 'Real-Time Intelligence',
                description: '24/7 data processing and AI analysis deliver actionable insights as markets move.',
              },
              {
                title: 'Comprehensive Coverage',
                description: 'Analysis of 5,300+ stocks with deep historical data going back 10+ years.',
              },
            ].map((item, idx) => (
              <Grid item xs={12} md={6} key={idx}>
                <Card
                  sx={{
                    height: '100%',
                    border: `1px solid ${theme.palette.divider}`,
                    backgroundColor: theme.palette.background.paper,
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
                      {item.title}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        color: theme.palette.text.secondary,
                        lineHeight: 1.7,
                      }}
                    >
                      {item.description}
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
        title="Ready to Access Professional Research?"
        subtitle="Explore our research dimensions and customize your analysis approach."
        primaryCTA={{ label: 'Launch Research Platform', href: '/app/market' }}
        secondaryCTA={{ label: 'Learn About Our Team', href: '/our-team' }}
      />

      {/* CTA Section */}
      <Box sx={{ mx: { xs: 2, md: 4 }, mb: 6 }}>
        <CTASection
          variant="primary"
          title="Experience Institutional-Grade Research"
          subtitle="Get comprehensive, multi-dimensional market analysis powered by AI and big data. Customize your research approach based on your investment strategy."
          primaryCTA={{ label: 'Explore Platform', link: '/app/market' }}
          secondaryCTA={{ label: 'View Pricing', link: '/become-client' }}
        />
      </Box>
    </MarketingLayout>
  );
};

export default Services;
