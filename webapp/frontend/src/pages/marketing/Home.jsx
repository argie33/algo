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
  Event as EventIcon,
  Psychology as PsychologyIcon,
  Business as BusinessIcon,
  Analytics as AnalyticsIcon,
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

  const keyFeatures = [
    {
      icon: <AnalyticsIcon fontSize="large" />,
      title: 'Quantitative Stock Analysis',
      description:
        'Multi-factor research models evaluate stocks across valuation, quality, momentum, and technical metrics. Comparative rankings updated during market hours.',
      tags: ['Quantitative', 'Equity Research', 'Analytics'],
      link: '/app/scores',
    },
    {
      icon: <EventIcon fontSize="large" />,
      title: 'Earnings Research',
      description:
        'Comprehensive earnings analysis including historical patterns, estimate revisions, and surprise trends. 10+ years of earnings data for pattern recognition.',
      tags: ['Earnings', 'Fundamentals', 'Research'],
      link: '/app/earnings',
    },
    {
      icon: <PsychologyIcon fontSize="large" />,
      title: 'Market Sentiment Research',
      description:
        'Track analyst ratings, institutional positioning, and market sentiment indicators. Identify extremes that historically precede reversals.',
      tags: ['Sentiment', 'Contrarian', 'Research'],
      link: '/app/sentiment',
    },
    {
      icon: <BusinessIcon fontSize="large" />,
      title: 'Sector & Macro Research',
      description:
        'Sector rotation analysis, economic research, and macro trend monitoring. Understand how Fed policy and economic data impact markets.',
      tags: ['Sectors', 'Economics', 'Macro'],
      link: '/app/market',
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

      {/* Compact Visual Section */}
      <Box sx={{ py: { xs: 4, md: 6 }, backgroundColor: theme.palette.background.default }}>
        <Container maxWidth="lg">
          <Box
            sx={{
              height: { xs: '250px', md: '350px' },
              background: `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.1)} 0%, ${alpha(theme.palette.secondary.main, 0.08)} 100%)`,
              border: `1px solid ${alpha(theme.palette.divider, 0.5)}`,
              borderRadius: '0px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              overflow: 'hidden',
              position: 'relative',
            }}
          >
            <Box sx={{
              textAlign: 'center',
              color: theme.palette.text.secondary,
              fontSize: '1.1rem',
              fontWeight: 500,
            }}>
              Team collaborating on financial research
            </Box>
          </Box>
        </Container>
      </Box>


      {/* Core Research Capabilities */}
      <FeatureGrid
        title="Core Research Capabilities"
        subtitle="Independent equity research across fundamentals, technicals, and quantitative analysis"
        features={keyFeatures}
        columns={{ xs: 1, sm: 2, md: 2, lg: 2 }}
      />

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

      {/* Community Signup Section */}
      <CommunitySignup />

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

      {/* CTA Section */}
      <CTASection
        variant="dark"
        title="Ready to Access Professional Research?"
        subtitle="Get institutional-grade market research and advisory insights."
        primaryCTA={{ label: 'Launch Platform', link: '/app/market' }}
      />
    </MarketingLayout>
  );
};

export default Home;
