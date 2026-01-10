import React from 'react';
import { Box, Container, Typography, Grid, alpha, useTheme, Card, CardContent } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import HeroSection from '../../components/marketing/HeroSection';
import FeatureGrid from '../../components/marketing/FeatureGrid';
import ImagePlaceholder from '../../components/marketing/ImagePlaceholder';
import CTAButtonGroup from '../../components/marketing/CTAButtonGroup';
import CTASection from '../../components/marketing/CTASection';
import CommunitySignup from '../../components/marketing/CommunitySignup';
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
    { label: 'Equity Research', detail: 'Comprehensive stock analysis, valuation models, and comparative rankings' },
    { label: 'Earnings Analysis', detail: 'Historical trends, estimate revisions, surprise patterns' },
    { label: 'Market Intelligence', detail: 'Price action, volume analysis, technical patterns during market hours' },
    { label: 'Economic Research', detail: 'Fed policy, macro indicators, interest rate impacts' },
    { label: 'Sector Coverage', detail: 'Industry rotation, relative strength, competitive dynamics' },
    { label: 'Quantitative Models', detail: 'Factor analysis, pattern recognition, historical backtesting' },
  ];

  const stats = [
    { number: '5,300+', label: 'Stocks Covered', description: 'Full US equity market coverage' },
    { number: '10+ Years', label: 'Historical Data', description: 'Backtested research methodology' },
    { number: 'Multi-Factor', label: 'Research Model', description: 'Fundamental, technical, and quantitative analysis' },
    { number: 'Independent', label: 'Research', description: 'No investment banking conflicts' },
  ];

  const keyFeatures = [
    {
      icon: <AnalyticsIcon fontSize="large" />,
      title: 'Quantitative Stock Analysis',
      description:
        'Multi-factor research models evaluate stocks across valuation, quality, momentum, and technical metrics. Comparative rankings updated during market hours.',
      bullets: [
        'Multi-factor quantitative models',
        'Updated during market hours',
        'Comparative rankings across universe',
      ],
      tags: ['Quantitative', 'Equity Research', 'Analytics'],
      link: '/app/scores',
    },
    {
      icon: <EventIcon fontSize="large" />,
      title: 'Earnings Research',
      description:
        'Comprehensive earnings analysis including historical patterns, estimate revisions, and surprise trends. 10+ years of earnings data for pattern recognition.',
      bullets: [
        'Earnings calendar and estimates',
        '10+ years historical analysis',
        'Estimate revision tracking',
      ],
      tags: ['Earnings', 'Fundamentals', 'Research'],
      link: '/app/earnings',
    },
    {
      icon: <PsychologyIcon fontSize="large" />,
      title: 'Market Sentiment Research',
      description:
        'Track analyst ratings, institutional positioning, and market sentiment indicators. Identify extremes that historically precede reversals.',
      bullets: [
        'Analyst rating analysis',
        'Positioning metrics',
        'Sentiment extremes',
      ],
      tags: ['Sentiment', 'Contrarian', 'Research'],
      link: '/app/sentiment',
    },
    {
      icon: <BusinessIcon fontSize="large" />,
      title: 'Sector & Macro Research',
      description:
        'Sector rotation analysis, economic research, and macro trend monitoring. Understand how Fed policy and economic data impact markets.',
      bullets: [
        'Sector rotation signals',
        'Economic indicator tracking',
        'Fed policy analysis',
      ],
      tags: ['Sectors', 'Economics', 'Macro'],
      link: '/app/market',
    },
  ];

  const clientSegments = [
    {
      segment: 'Institutional Investors',
      description: 'Asset managers, hedge funds, and institutional advisors',
      offerings: [
        'Full research platform access',
        'Quantitative stock scoring',
        'Earnings analysis and calendar',
        'API access for integration',
      ],
      icon: <GroupsIcon fontSize="large" />,
    },
    {
      segment: 'Financial Advisors',
      description: 'RIAs, wealth managers, and financial advisors',
      offerings: [
        'Research platform access',
        'Stock screening and analysis',
        'Portfolio monitoring tools',
        'Market and sector research',
      ],
      icon: <SchoolIcon fontSize="large" />,
    },
    {
      segment: 'Active Traders',
      description: 'Individual investors and active traders',
      offerings: [
        'Stock analysis and scoring',
        'Technical research tools',
        'Earnings calendar and data',
        'Sector rotation signals',
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
            Independent Equity Research
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
            Bullseye Financial delivers evidence-based equity research combining quantitative analysis, fundamental research, and technical insights. Our multi-dimensional approach helps institutional investors, RIAs, and active traders make better-informed decisions.
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
            5,300+ stocks covered • 10+ years historical data • Analysis updated during market hours
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
                image: 'https://images.unsplash.com/photo-1517694712202-14dd9538aa97?w=600&h=400&fit=crop',
              },
              {
                number: '2',
                title: 'Evidence-Based Methodology',
                description: 'Every signal is backtested against 10+ years of market data. We validate our models against real market outcomes and continuously refine our research process based on performance.',
                image: 'https://images.unsplash.com/photo-1552664730-d307ca884978?w=600&h=400&fit=crop',
              },
              {
                number: '3',
                title: 'Institutional-Grade Tools',
                description: 'Access the same caliber of research tools used by professional investors. Our platform provides detailed analytics, stock screening, and portfolio monitoring for serious investors.',
                image: 'https://images.unsplash.com/photo-1552664730-d307ca884978?w=600&h=400&fit=crop',
              },
              {
                number: '4',
                title: 'Independent & Transparent',
                description: 'We publish independent research without investment banking conflicts. Our methodology is transparent, and we explain the factors driving our analysis and recommendations.',
                image: 'https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=600&h=400&fit=crop',
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
                  <ImagePlaceholder
                    src={item.image}
                    alt={item.title}
                    height={{ xs: '200px', md: '200px' }}
                  />
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
        title="Core Research Capabilities"
        subtitle="Independent equity research across fundamentals, technicals, and quantitative analysis"
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
            Bullseye combines fundamental analysis, quantitative research, and technical insights to deliver comprehensive equity coverage. Our methodology integrates multiple data sources and is validated through rigorous backtesting.
          </Typography>

          <Grid container spacing={4}>
            {[
              {
                title: 'Fundamental Research',
                description: 'Comprehensive analysis of financial statements, valuation metrics, earnings quality, and competitive positioning. We evaluate companies using traditional metrics alongside proprietary screening models.',
              },
              {
                title: 'Quantitative Analysis',
                description: 'Multi-factor models evaluate stocks across value, quality, momentum, and technical factors. All models are backtested against 10+ years of data and validated for statistical significance.',
              },
              {
                title: 'Technical Research',
                description: 'Price action analysis, support/resistance identification, and momentum indicators. We track technical patterns that have historically preceded significant moves.',
              },
              {
                title: 'Earnings Intelligence',
                description: 'Historical earnings analysis, estimate revision tracking, and surprise pattern recognition. We identify stocks with improving fundamentals before consensus catches on.',
              },
              {
                title: 'Economic & Sector Analysis',
                description: 'Macro research covering Fed policy, economic indicators, and sector rotation. We analyze how changing economic conditions impact different industries and investment styles.',
              },
              {
                title: 'Independent Research',
                description: 'We maintain independence from investment banking and operate without conflicts of interest. Our research is based on data and analysis, not Wall Street relationships.',
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
            Our research platform serves institutions, advisors, and individual investors with comprehensive equity analysis
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
                      Platform Access:
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
              },
              {
                title: 'Earnings Season Preview: 15 Stocks With High Surprise Probability',
                date: 'December 22, 2025',
                author: 'Earnings Intelligence',
                excerpt: 'With earnings season approaching, our AI scoring system has identified 15 stocks with high probability of positive earnings surprises based on revision trends and analyst positioning...',
                tags: ['Earnings', 'Forecasts', 'Stock Picks'],
                tickers: ['AMZN', 'CRM', 'ASML', 'META'],
              },
              {
                title: 'Sentiment Divergence Creating Opportunity in Energy Sector',
                date: 'December 20, 2025',
                author: 'Sentiment Analytics',
                excerpt: 'Despite bearish headlines, our sentiment tracking shows institutional accumulation in select energy names. This divergence between narrative and actual positioning suggests contrarian opportunity...',
                tags: ['Sentiment', 'Contrarian', 'Energy'],
                tickers: ['XLE', 'XOM', 'CVX', 'MPC'],
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
                name: 'Portfolio Manager',
                role: 'Mid-sized Asset Manager',
                quote: 'The quantitative scoring models help us identify opportunities across our coverage universe. The earnings analysis has been particularly useful for timing positions around quarterly reports.',
              },
              {
                name: 'Registered Investment Advisor',
                role: 'Independent RIA',
                quote: 'Bullseye\'s research saves me hours of analysis time. The multi-factor approach gives me confidence in stock selection, and the sector rotation signals help with tactical allocation decisions.',
              },
              {
                name: 'Active Investor',
                role: 'Individual Trader',
                quote: 'The platform gives me access to institutional-caliber research at a fraction of the cost. The technical analysis tools combined with fundamental metrics help me make better-informed trading decisions.',
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

      {/* Community Signup Section */}
      <CommunitySignup />

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
