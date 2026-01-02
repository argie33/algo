import React from 'react';
import { Box, Container, Typography, Grid, alpha, useTheme, Card, CardContent } from '@mui/material';
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
  Storage as StorageIcon,
  Analytics as AnalyticsIcon,
  School as SchoolIcon,
  Groups as GroupsIcon,
} from '@mui/icons-material';

const Home = () => {
  const theme = useTheme();
  const navigate = useNavigate();

  const dataCapabilities = [
    { label: 'Market Data', detail: 'Real-time pricing, volume, and liquidity analysis' },
    { label: 'Economic Data', detail: 'Macro indicators, employment, GDP, inflation trends' },
    { label: 'Fundamentals', detail: 'Financial statements, valuation metrics, profitability' },
    { label: 'Technical', detail: 'Price patterns, momentum indicators, support/resistance' },
    { label: 'Sector Analysis', detail: 'Industry trends, competitive positioning, rotation signals' },
    { label: 'Sentiment Data', detail: 'Analyst ratings, positioning, market psychology signals' },
  ];

  const stats = [
    { number: '5,300+', label: 'Stocks Covered', description: 'Comprehensive US equity analysis' },
    { number: '10+ Years', label: 'Market Data', description: 'Deep historical perspective' },
    { number: '6 Dimensions', label: 'Data Analysis', description: 'Market, economy, fundamentals, technicals, sector, sentiment' },
    { number: 'AI-Powered', label: 'Research', description: 'Cutting-edge ML and quantitative techniques' },
  ];

  const keyFeatures = [
    {
      icon: <AnalyticsIcon fontSize="large" />,
      title: 'AI-Powered Stock Analysis',
      description:
        'Our proprietary composite scoring system applies machine learning across multiple dimensions to identify opportunities before the consensus.',
      bullets: [
        'Multi-factor AI scoring engine',
        'Real-time score updates',
        'Comparable ranking system',
      ],
      tags: ['AI Analysis', 'Scoring', 'Quantitative'],
      link: '/app/scores',
    },
    {
      icon: <EventIcon fontSize="large" />,
      title: 'Earnings Intelligence',
      description:
        'Track upcoming earnings, analyze historical surprise patterns, and identify estimate revision trends using historical and real-time data.',
      bullets: [
        'Live earnings calendar',
        '10+ years historical data',
        'Surprise and revision analysis',
      ],
      tags: ['Earnings', 'Fundamentals', 'Intelligence'],
      link: '/app/earnings',
    },
    {
      icon: <PsychologyIcon fontSize="large" />,
      title: 'Sentiment & Positioning Analysis',
      description:
        'AI-interpreted analysis of market psychology, analyst sentiment, and institutional positioning to reveal hidden market shifts.',
      bullets: [
        'Sentiment metrics and trends',
        'Institutional positioning data',
        'Market psychology signals',
      ],
      tags: ['Sentiment', 'Psychology', 'AI'],
      link: '/app/sentiment',
    },
    {
      icon: <BusinessIcon fontSize="large" />,
      title: 'Sector & Market Research',
      description:
        'Monitor sector rotation, relative strength, economic impacts, and macro trends for comprehensive portfolio positioning.',
      bullets: [
        'Sector performance tracking',
        'Macro trend analysis',
        'Economic indicator integration',
      ],
      tags: ['Markets', 'Sectors', 'Macro'],
      link: '/app/market',
    },
  ];

  const clientSegments = [
    {
      segment: 'Institutions',
      description: 'Asset managers, hedge funds, and institutional advisors',
      offerings: [
        'Enterprise research data feeds',
        'Customized analysis dashboards',
        'Dedicated research support',
        'API access for integration',
      ],
      icon: <GroupsIcon fontSize="large" />,
    },
    {
      segment: 'Advisors',
      description: 'RIAs, wealth managers, and financial advisors',
      offerings: [
        'Client-ready research reports',
        'Customizable analysis tools',
        'Portfolio monitoring solutions',
        'Client communication materials',
      ],
      icon: <SchoolIcon fontSize="large" />,
    },
    {
      segment: 'Individual Investors',
      description: 'Active traders and individual investors',
      offerings: [
        'Real-time stock analysis',
        'Trading signals and alerts',
        'Portfolio optimization tools',
        'Educational research content',
      ],
      icon: <TrendingUpIcon fontSize="large" />,
    },
  ];

  return (
    <MarketingLayout>
      {/* Hero Section */}
      <HeroSection />

      {/* Value Proposition Section */}
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
            Research Firm &amp; Advisory Platform
          </Typography>
          <Typography
            sx={{
              fontSize: '1.1rem',
              color: theme.palette.text.secondary,
              textAlign: 'center',
              mb: 3,
              maxWidth: '900px',
              mx: 'auto',
              lineHeight: 1.8,
              fontWeight: 500,
            }}
          >
            Transform how you make investment decisions. Our institutional-grade research platform combines decades of market expertise, cutting-edge AI, and comprehensive multi-dimensional data to uncover opportunities the traditional analysis misses.
          </Typography>
          <Typography
            sx={{
              fontSize: '0.95rem',
              color: theme.palette.text.secondary,
              textAlign: 'center',
              mb: 6,
              maxWidth: '800px',
              mx: 'auto',
              lineHeight: 1.7,
              fontStyle: 'italic',
            }}
          >
            6 research dimensions • 10+ years of data • 5,300+ stocks • Real-time AI-powered analysis
          </Typography>

          {/* Data Breadth Grid */}
          <Grid container spacing={3}>
            {dataCapabilities.map((item, idx) => (
              <Grid item xs={12} sm={6} md={4} key={idx}>
                <Box
                  sx={{
                    p: 3,
                    backgroundColor: theme.palette.background.paper,
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: '0px',
                    transition: 'all 0.3s ease',
                    '&:hover': {
                      boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
                      borderColor: theme.palette.primary.main,
                    },
                  }}
                >
                  <Typography
                    sx={{
                      fontWeight: 700,
                      color: theme.palette.primary.main,
                      mb: 1,
                      fontSize: '1rem',
                    }}
                  >
                    {item.label}
                  </Typography>
                  <Typography
                    sx={{
                      color: theme.palette.text.secondary,
                      fontSize: '0.95rem',
                      lineHeight: 1.6,
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

      {/* What Sets Us Apart Section */}
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
            Why Professional Investors Choose Bullseye
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
            We're not just another market data provider. We're your research partner.
          </Typography>
          <Grid container spacing={4}>
            {[
              {
                number: '1',
                title: 'Deeper Insights',
                description: 'Our AI models find correlations and patterns traditional analysis never sees. Multi-dimensional research reveals opportunities hidden in market noise.',
                icon: '🔍',
              },
              {
                number: '2',
                title: 'Faster Decisions',
                description: 'Real-time analysis powered by 24/7 data processing. Get actionable intelligence the moment market conditions change.',
                icon: '⚡',
              },
              {
                number: '3',
                title: 'Customized for You',
                description: 'Whether you manage billions or invest your own capital, we tailor our research to match your strategy and timeline.',
                icon: '🎯',
              },
              {
                number: '4',
                title: 'Evidence-Based',
                description: 'Every analysis is rigorously tested against 10+ years of historical data. We focus on what works, not what sounds good.',
                icon: '✓',
              },
            ].map((item, idx) => (
              <Grid item xs={12} sm={6} md={3} key={idx}>
                <Box
                  sx={{
                    p: 4,
                    backgroundColor: theme.palette.background.paper,
                    border: `2px solid ${theme.palette.divider}`,
                    borderRadius: '0px',
                    transition: 'all 0.3s ease',
                    textAlign: 'center',
                    '&:hover': {
                      borderColor: theme.palette.primary.main,
                      boxShadow: '0 8px 24px rgba(0,0,0,0.1)',
                      transform: 'translateY(-4px)',
                    },
                  }}
                >
                  <Box sx={{ fontSize: '3rem', mb: 2 }}>
                    {item.icon}
                  </Box>
                  <Typography
                    sx={{
                      fontSize: '2.5rem',
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

      {/* Comprehensive Data Stats */}
      <Box
        sx={{
          py: { xs: 6, md: 8 },
          backgroundColor: theme.palette.background.paper,
          borderTop: `1px solid ${alpha(theme.palette.divider, 0.5)}`,
          borderBottom: `1px solid ${alpha(theme.palette.divider, 0.5)}`,
        }}
      >
        <Container maxWidth="lg">
          <Typography
            variant="h3"
            sx={{
              fontSize: { xs: '1.8rem', sm: '2rem', md: '2.2rem' },
              fontWeight: 800,
              mb: 6,
              textAlign: 'center',
              color: theme.palette.text.primary,
            }}
          >
            Comprehensive Data &amp; Research Infrastructure
          </Typography>
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

      {/* Core Research Capabilities */}
      <FeatureGrid
        title="Research-Driven Analysis Capabilities"
        subtitle="Professional-grade research and analysis across multiple market dimensions"
        features={keyFeatures}
        columns={{ xs: 1, sm: 2, md: 2, lg: 2 }}
      />

      {/* Our Research Approach Section */}
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
            Our Research Methodology
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
            We combine traditional fundamental and technical analysis with cutting-edge artificial intelligence and big data quantitative techniques to identify market opportunities across different market conditions.
          </Typography>

          <Grid container spacing={4}>
            {[
              {
                title: 'Multi-Dimensional Analysis',
                description: 'We analyze markets across 6+ independent dimensions—fundamentals, technicals, sentiment, sector rotation, macroeconomics, and positioning—then synthesize findings into unified insights.',
              },
              {
                title: 'AI & Machine Learning',
                description: 'Our proprietary machine learning models identify patterns and correlations invisible to traditional analysis. Models are continuously trained on 10+ years of market data and validated against real-world outcomes.',
              },
              {
                title: 'Big Data Integration',
                description: 'We integrate traditional financial data with alternative data sources, including economic indicators, sentiment signals, and positioning metrics, to provide comprehensive market intelligence.',
              },
              {
                title: 'Evidence-Based Approach',
                description: 'Every analysis dimension is rigorously tested and validated. We focus on data-driven insights rather than opinions, and always explain our reasoning and confidence levels.',
              },
              {
                title: 'Customized Solutions',
                description: 'Each investor is different. We tailor our analysis and recommendations based on individual goals, risk tolerance, time horizon, and specific market mandates.',
              },
              {
                title: 'Continuous Learning',
                description: 'Our research team and AI models continuously learn from market outcomes. We adapt our methodology as market conditions evolve and new data becomes available.',
              },
            ].map((item, idx) => (
              <Grid item xs={12} md={6} key={idx}>
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

      {/* Client Segmentation Section */}
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
            Research &amp; Advisory Solutions for Every Investor Type
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
            We offer customized research data and advisory solutions tailored to institutions, advisors, and individual investors
          </Typography>

          <Grid container spacing={4}>
            {clientSegments.map((client, idx) => (
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
                    <Box sx={{ mb: 2, color: theme.palette.primary.main }}>
                      {client.icon}
                    </Box>
                    <Typography
                      variant="h6"
                      sx={{
                        fontWeight: 700,
                        mb: 0.5,
                        color: theme.palette.text.primary,
                        fontSize: '1.25rem',
                      }}
                    >
                      {client.segment}
                    </Typography>
                    <Typography
                      sx={{
                        color: theme.palette.text.secondary,
                        mb: 2.5,
                        fontSize: '0.95rem',
                      }}
                    >
                      {client.description}
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
                      Custom Offerings:
                    </Typography>
                    <Box component="ul" sx={{ pl: 2, m: 0 }}>
                      {client.offerings.map((offering, oidx) => (
                        <Typography
                          component="li"
                          key={oidx}
                          sx={{
                            color: theme.palette.text.secondary,
                            fontSize: '0.9rem',
                            mb: 1,
                            lineHeight: 1.5,
                          }}
                        >
                          {offering}
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
                title: 'Customized Delivery',
                description: 'Research is tailored to each client type—detailed reports for institutions, actionable summaries for advisors, real-time signals for active investors.',
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

      {/* Latest Market Insights Section */}
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
            Latest Market Insights
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
            Stay ahead of market moves with our latest AI-powered research and analysis
          </Typography>
          <Grid container spacing={4}>
            {[
              {
                title: 'Tech Sector Showing Renewed Strength Amid Macro Uncertainties',
                date: 'December 23, 2025',
                author: 'AI Research Team',
                excerpt: 'Our AI models detected a significant shift in technical momentum for mega-cap tech stocks this week. Analysis of sentiment data and positioning metrics suggests institutional accumulation...',
                tags: ['Technical Analysis', 'Sector Rotation', 'AI Signals'],
                tickers: ['AAPL', 'MSFT', 'GOOGL', 'NVDA'],
                image: 'https://picsum.photos/800/500?random=10
              },
              {
                title: 'Earnings Season Preview: 15 Stocks With High Surprise Probability',
                date: 'December 22, 2025',
                author: 'Earnings Intelligence',
                excerpt: 'With earnings season approaching, our AI scoring system has identified 15 stocks with high probability of positive earnings surprises based on revision trends and analyst positioning...',
                tags: ['Earnings', 'Forecasts', 'Stock Picks'],
                tickers: ['AMZN', 'CRM', 'ASML', 'META'],
                image: 'https://picsum.photos/800/500?random=10
              },
              {
                title: 'Sentiment Divergence Creating Opportunity in Energy Sector',
                date: 'December 20, 2025',
                author: 'Sentiment Analytics',
                excerpt: 'Despite bearish headlines, our sentiment tracking shows institutional accumulation in select energy names. This divergence between narrative and actual positioning suggests contrarian opportunity...',
                tags: ['Sentiment', 'Contrarian', 'Energy'],
                tickers: ['XLE', 'XOM', 'CVX', 'MPC'],
                image: 'https://picsum.photos/800/500?random=10
              },
            ].map((insight, idx) => (
              <Grid item xs={12} md={4} key={idx}>
                <Card
                  sx={{
                    height: '100%',
                    border: `1px solid ${theme.palette.divider}`,
                    backgroundColor: theme.palette.background.default,
                    borderRadius: '0px',
                    transition: 'all 0.3s ease',
                    overflow: 'hidden',
                    cursor: 'pointer',
                    '&:hover': {
                      boxShadow: '0 12px 30px rgba(0,0,0,0.12)',
                      transform: 'translateY(-6px)',
                    },
                  }}
                >
                  <Box
                    component="img"
                    src={insight.image}
                    alt={insight.title}
                    sx={{
                      width: '100%',
                      height: 200,
                      objectFit: 'cover',
                      display: 'block',
                    }}
                    onError={(e) => {
                      e.target.style.display = 'none';
                    }}
                  />
                  <CardContent sx={{ p: 3 }}>
                    <Typography
                      variant="body2"
                      sx={{
                        fontSize: '0.8rem',
                        color: theme.palette.primary.main,
                        fontWeight: 700,
                        mb: 1,
                        textTransform: 'uppercase',
                        letterSpacing: '0.5px',
                      }}
                    >
                      {insight.date} • {insight.author}
                    </Typography>
                    <Typography
                      variant="h6"
                      sx={{
                        fontWeight: 700,
                        mb: 1.5,
                        color: theme.palette.text.primary,
                        fontSize: '1.1rem',
                        lineHeight: 1.4,
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
                      {insight.excerpt}
                    </Typography>
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
                      {insight.tickers.map((ticker, i) => (
                        <Box
                          key={i}
                          sx={{
                            px: 1.5,
                            py: 0.5,
                            backgroundColor: alpha(theme.palette.primary.main, 0.1),
                            borderRadius: '2px',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            color: theme.palette.primary.main,
                          }}
                        >
                          {ticker}
                        </Box>
                      ))}
                    </Box>
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                      {insight.tags.map((tag, i) => (
                        <Box
                          key={i}
                          sx={{
                            fontSize: '0.7rem',
                            color: theme.palette.text.secondary,
                            fontStyle: 'italic',
                          }}
                        >
                          {tag}{i < insight.tags.length - 1 ? ',' : ''}
                        </Box>
                      ))}
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Testimonials Section */}
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
            Trusted by Professional Investors
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
            See what professional traders, advisors, and institutional investors are saying about Bullseye's research
          </Typography>
          <Grid container spacing={4}>
            {[
              {
                name: 'Robert Chen',
                role: 'Portfolio Manager, Wealth Advisors LLC',
                quote: 'Their AI scoring system has fundamentally changed how we evaluate opportunities. We\'re seeing better risk-adjusted returns and making faster, more confident investment decisions.',
                image: 'https://picsum.photos/800/500?random=10
              },
              {
                name: 'Jennifer Williams',
                role: 'Active Trader, Independent',
                quote: 'The multi-dimensional research is exceptional. Fundamentals, technicals, and sentiment all work together to confirm trading opportunities. No other research platform integrates data like this.',
                image: 'https://picsum.photos/800/500?random=10
              },
              {
                name: 'Marcus Johnson',
                role: 'Fund Manager, Macro Research Partners',
                quote: 'Bullseye\'s combination of traditional research expertise with AI-powered analysis is sophisticated and unique. It\'s become essential infrastructure for our entire research operation.',
                image: 'https://picsum.photos/800/500?random=10
              },
            ].map((testimonial, idx) => (
              <Grid item xs={12} sm={6} md={4} key={idx}>
                <Box
                  sx={{
                    p: 3,
                    backgroundColor: theme.palette.background.paper,
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: '0px',
                    height: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                    transition: 'all 0.3s ease',
                    '&:hover': {
                      boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
                      transform: 'translateY(-2px)',
                    },
                  }}
                >
                  <Typography
                    sx={{
                      fontSize: '1rem',
                      color: theme.palette.text.secondary,
                      mb: 3,
                      lineHeight: 1.7,
                      fontStyle: 'italic',
                      flex: 1,
                    }}
                  >
                    "{testimonial.quote}"
                  </Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mt: 2, pt: 2, borderTop: `1px solid ${theme.palette.divider}` }}>
                    <Box
                      component="img"
                      src={testimonial.image}
                      alt={testimonial.name}
                      sx={{
                        width: 50,
                        height: 50,
                        borderRadius: '50%',
                        objectFit: 'cover',
                      }}
                      onError={(e) => {
                        e.target.style.display = 'none';
                      }}
                    />
                    <Box>
                      <Typography
                        sx={{
                          fontWeight: 700,
                          color: theme.palette.text.primary,
                          fontSize: '0.95rem',
                        }}
                      >
                        {testimonial.name}
                      </Typography>
                      <Typography
                        sx={{
                          fontSize: '0.85rem',
                          color: theme.palette.text.secondary,
                        }}
                      >
                        {testimonial.role}
                      </Typography>
                    </Box>
                  </Box>
                </Box>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* CTA Section */}
      <CTASection
        variant="dark"
        title="Ready to Access Professional Research?"
        subtitle="Get institutional-grade market research and advisory insights. Choose the solution that fits your needs."
        primaryCTA={{ label: 'Launch Platform', link: '/app/market' }}
        secondaryCTA={{ label: 'View Services', link: '/services' }}
      />
    </MarketingLayout>
  );
};

export default Home;
