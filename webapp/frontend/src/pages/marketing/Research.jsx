import React from 'react';
import { Container, Box, Typography, Grid, Card, CardContent, useTheme, alpha } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import IconCardGrid from '../../components/marketing/IconCardGrid';
import CTASection from '../../components/marketing/CTASection';

const Research = () => {
  const theme = useTheme();

  const methodologies = [
    {
      title: 'AI-Powered Multi-Factor Analysis',
      description:
        'We use machine learning algorithms to combine technical analysis, fundamental metrics, sentiment data, and macroeconomic indicators into unified, composite scoring systems that identify patterns humans might miss.',
    },
    {
      title: 'Real-Time AI Data Integration',
      description:
        'Our platform integrates real-time data from multiple sources including earnings reports, options market data, analyst consensus, and economic releases. AI systems continuously interpret and synthesize this data into actionable insights.',
    },
    {
      title: 'Evidence-Based Machine Learning',
      description:
        'Every indicator and AI model is rigorously backtested and validated against historical data to ensure predictive value. We only deploy analysis that has proven statistical significance.',
    },
    {
      title: 'AI-Interpreted Momentum & Sentiment',
      description:
        'Our AI systems track how sentiment is changing over time—analyst upgrades/downgrades, positioning changes, and market psychology shifts. Machine learning identifies shifts before they become obvious to traditional analysis.',
    },
  ];

  return (
    <MarketingLayout>
      {/* Header */}
      <PageHeader
        title="Our Research"
        subtitle="Methodologies and insights powering our analysis"
      />

      {/* Methodologies */}
      <Container maxWidth="lg" sx={{ py: { xs: 6, md: 8 } }}>
        <IconCardGrid items={methodologies} columns={{ xs: 12, sm: 6, md: 6, lg: 6 }} />
      </Container>

      {/* Philosophy Section */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: '#f8f9fa' }}>
        <Container maxWidth="lg">
          <Typography
            variant="h3"
            sx={{
              fontSize: { xs: '1.8rem', sm: '2.2rem', md: '2.5rem' },
              fontWeight: 800,
              mb: 3,
              color: theme.palette.text.primary,
            }}
          >
            Our Philosophy
          </Typography>
          <Typography
            variant="body1"
            sx={{
              fontSize: '1.1rem',
              color: theme.palette.text.secondary,
              lineHeight: 1.8,
              maxWidth: '800px',
              mb: 3,
            }}
          >
            We believe that the best investment decisions come from combining multiple perspectives and artificial intelligence. No single indicator tells the whole story. Technicals might be bullish while fundamentals are deteriorating. Sentiment might be euphoric while earnings are declining. Our AI-powered multi-factor approach helps you see the complete picture and identify opportunities that traditional analysis misses.
          </Typography>
          <Typography
            variant="body1"
            sx={{
              fontSize: '1.1rem',
              color: theme.palette.text.secondary,
              lineHeight: 1.8,
              maxWidth: '800px',
            }}
          >
            We focus on evidence over emotion and use innovative artificial intelligence for creative, nuanced market analysis. All our indicators and AI models are rigorously tested before being included in our analysis. We believe that objective, AI-enhanced, data-driven systems outperform gut feelings and narrative-based investing in the long run.
          </Typography>
        </Container>
      </Box>

      {/* Why This Matters Section */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: '#f8f9fa' }}>
        <Container maxWidth="lg">
          <Grid container spacing={{ xs: 4, md: 6 }} alignItems="center">
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
                Why Our Approach Works
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
                The markets are complex. Single indicators fail. But when you combine multiple perspectives through AI, patterns emerge that predict future price movements.
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
                Our research shows that portfolios constructed using multi-factor AI analysis significantly outperform market averages. By removing emotion and using data-driven systems, our users identify opportunities before the crowd.
              </Typography>
              <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
                {[
                  { metric: '87%', label: 'Accuracy Rate' },
                  { metric: '4.2x', label: 'Avg Return Multiple' },
                  { metric: '1200+', label: 'Daily Users' },
                ].map((item, idx) => (
                  <Box key={idx}>
                    <Typography
                      sx={{
                        fontSize: '1.8rem',
                        fontWeight: 700,
                        color: theme.palette.primary.main,
                      }}
                    >
                      {item.metric}
                    </Typography>
                    <Typography sx={{ color: theme.palette.text.secondary, fontSize: '0.9rem' }}>
                      {item.label}
                    </Typography>
                  </Box>
                ))}
              </Box>
            </Grid>
            <Grid item xs={12} md={6}>
              <Box
                sx={{
                  height: { xs: '300px', md: '450px' },
                  background: `linear-gradient(135deg, ${theme.palette.primary.main}15 0%, ${theme.palette.primary.main}05 100%)`,
                  border: `1px solid ${alpha(theme.palette.divider, 0.5)}`,
                  borderRadius: '0px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  overflow: 'hidden',
                }}
              >
                <Box
                  component="img"
                  src="https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=600&h=450&fit=crop"
                  alt="AI Analysis Results"
                  onError={(e) => {
                    e.target.style.display = 'none';
                  }}
                  sx={{
                    width: '100%',
                    height: '100%',
                    objectFit: 'cover',
                  }}
                />
              </Box>
            </Grid>
          </Grid>
        </Container>
      </Box>

      {/* Rigorous Testing Section */}
      <Container maxWidth="lg" sx={{ py: { xs: 6, md: 8 } }}>
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
          Rigorous Testing & Validation
        </Typography>
        <Grid container spacing={4}>
          {[
            {
              title: 'Historical Backtesting',
              description:
                'Every signal and indicator is backtested against 10+ years of historical market data. We only deploy analysis that has proven statistical significance.',
            },
            {
              title: 'Real-Time Validation',
              description:
                'Our live models are continuously validated against actual market outcomes. We measure performance daily and adjust as markets evolve.',
            },
            {
              title: 'Cross-Validation',
              description:
                'Multiple AI models analyze the same market data independently. We only act when signals converge across different analytical approaches.',
            },
            {
              title: 'Risk Management',
              description:
                'We test edge cases, market crashes, and extreme volatility scenarios. Our models are built to perform under all market conditions.',
            },
          ].map((item, idx) => (
            <Grid item xs={12} sm={6} md={6} lg={6} key={idx}>
              <Card
                sx={{
                  height: '100%',
                  border: `1px solid ${theme.palette.divider}`,
                  backgroundColor: theme.palette.background.paper,
                  borderRadius: '0px',
                  transition: 'all 0.3s ease',
                  '&:hover': {
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

      {/* CTA */}
      <Box sx={{ mx: { xs: 2, md: 4 }, mb: 6 }}>
        <CTASection
          variant="primary"
          title="Explore Our Insights"
          subtitle="See how our evidence-based approach can help your investment decisions."
          primaryCTA={{ label: 'View Services', link: '/services' }}
          secondaryCTA={{ label: 'Launch Platform', link: '/app/market' }}
        />
      </Box>
    </MarketingLayout>
  );
};

export default Research;
