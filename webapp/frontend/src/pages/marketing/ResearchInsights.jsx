import React from 'react';
import { Container, Box, Typography, Grid, Card, CardContent, useTheme, alpha } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import CTASection from '../../components/marketing/CTASection';
import ImagePlaceholder from '../../components/marketing/ImagePlaceholder';
import {
  TrendingUp as TrendingUpIcon,
  DataObject as DataObjectIcon,
  FilterList as FilterListIcon,
  Verified as VerifiedIcon,
} from '@mui/icons-material';

const ResearchInsights = () => {
  const theme = useTheme();

  const researchDimensions = [
    {
      icon: <TrendingUpIcon />,
      title: 'Trend Analysis',
      description: 'Minervini-style trend template requiring stocks to be above the 150 and 200-day SMA, with the 50-day above the 150, within a specific 52-week range position, and showing relative strength vs. the S&P 500.',
    },
    {
      icon: <DataObjectIcon />,
      title: 'Fundamental Quality',
      description: 'Multi-factor fundamental filters evaluating earnings growth rate, revenue acceleration, profit margins, return on equity, and debt levels. The system favors companies with actual earnings, not story stocks.',
    },
    {
      icon: <FilterListIcon />,
      title: 'Market Health Gating',
      description: 'Before any signal reaches the execution layer, the broader market must clear health thresholds: advance/decline breadth, distribution day count, VIX conditions, and market stage analysis.',
    },
    {
      icon: <VerifiedIcon />,
      title: 'Signal Validation',
      description: 'Every scoring model is backtested against 10+ years of historical data. Out-of-sample performance is tracked continuously, and models are updated when market conditions change their predictive validity.',
    },
  ];

  const processSteps = [
    {
      step: '01',
      title: 'Data Collection',
      description: 'Twenty-four automated loaders run daily before market open, pulling prices, technicals, fundamentals, earnings, sentiment, sector data, and economic indicators from authoritative sources.',
    },
    {
      step: '02',
      title: 'Multi-Factor Scoring',
      description: 'Each stock in the 5,300+ universe is scored across valuation, momentum, trend strength, earnings quality, and fundamental health. Composite scores update every trading day.',
    },
    {
      step: '03',
      title: 'Signal Generation',
      description: 'The top-ranked stocks are run through six sequential filters: market health, trend template, fundamental quality, earnings signals, portfolio constraints, and advanced technical criteria.',
    },
    {
      step: '04',
      title: 'Research Delivery',
      description: 'Signals, scores, sector analysis, earnings calendar, and economic data are surfaced through the research platform&#8212;updated before market open and after market close.',
    },
  ];

  const differentiators = [
    {
      number: '01',
      title: 'Minervini Stage Analysis',
      description: 'Our trend template is based on Mark Minervini\'s Stage Analysis framework, one of the most rigorously backtested approaches to identifying stocks in Stage 2 uptrends. Seven specific conditions must all be met simultaneously.',
    },
    {
      number: '02',
      title: 'Fundamentals-First Filter',
      description: 'Technical setups without fundamental support don\'t pass. The research screens for earnings acceleration, revenue growth, and profit margin expansion&#8212;the hallmarks of stocks that sustain their moves.',
    },
    {
      number: '03',
      title: 'Market Regime Awareness',
      description: 'No new longs in declining markets. The system evaluates distribution days, breadth deterioration, and VIX expansion before allowing any new position. Capital preservation during corrections is explicit.',
    },
    {
      number: '04',
      title: 'Transparent, Verifiable Methodology',
      description: 'Every filter, every scoring weight, every threshold is documented and observable. You can see exactly why a stock passes or fails any stage of the process&#8212;no black box.',
    },
  ];

  return (
    <MarketingLayout>
      <PageHeader
        title="Research & Insights"
        subtitle="How we find high-quality setups: transparent methodology, systematic process, backtested validation"
      />

      {/* Hero */}
      <Box sx={{ py: { xs: 8, md: 10 }, backgroundColor: theme.palette.background.default }}>
        <Container maxWidth="lg">
          <Grid container spacing={7} alignItems="center">
            <Grid item xs={12} md={6}>
              <Typography
                variant="overline"
                sx={{ color: theme.palette.primary.main, fontWeight: 700, letterSpacing: '3px', display: 'block', mb: 1.5 }}
              >
                Evidence-Based Methodology
              </Typography>
              <Typography
                variant="h3"
                sx={{
                  fontSize: { xs: '2rem', sm: '2.5rem', md: '3rem' },
                  fontWeight: 800,
                  mb: 3,
                  color: theme.palette.text.primary,
                  letterSpacing: '-0.5px',
                  lineHeight: 1.2,
                }}
              >
                Systematic Research. No Guesswork.
              </Typography>
              <Typography
                variant="body1"
                sx={{ fontSize: '1.1rem', color: theme.palette.text.secondary, lineHeight: 1.8, mb: 3 }}
              >
                Our research process is built on a single premise: the best stocks to own are
                in Stage 2 uptrends with accelerating fundamentals, entered only when the
                broader market is in a healthy condition. Everything else is noise.
              </Typography>
              <Typography
                variant="body1"
                sx={{ fontSize: '1rem', color: theme.palette.text.secondary, lineHeight: 1.8 }}
              >
                That premise has been validated across decades of market data. The Minervini
                Trend Template, combined with fundamental quality filters and market health gating,
                produces a signal set with historically high win rates and favorable risk/reward ratios.
              </Typography>
            </Grid>
            <Grid item xs={12} md={6}>
              <ImagePlaceholder
                src="https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=900&h=650&fit=crop&auto=format&q=80"
                alt="Research analytics dashboard with market data"
                height={{ xs: '300px', md: '420px' }}
              />
            </Grid>
          </Grid>
        </Container>
      </Box>

      {/* Research Dimensions */}
      <Box
        sx={{
          py: { xs: 8, md: 10 },
          backgroundColor: theme.palette.background.paper,
          borderTop: `1px solid ${theme.palette.divider}`,
        }}
      >
        <Container maxWidth="lg">
          <Box sx={{ textAlign: 'center', mb: 7 }}>
            <Typography
              variant="overline"
              sx={{ color: theme.palette.primary.main, fontWeight: 700, letterSpacing: '3px', display: 'block', mb: 1.5 }}
            >
              Core Research Framework
            </Typography>
            <Typography
              variant="h3"
              sx={{
                fontSize: { xs: '1.9rem', sm: '2.3rem', md: '2.8rem' },
                fontWeight: 800,
                mb: 2,
                color: theme.palette.text.primary,
                letterSpacing: '-0.5px',
              }}
            >
              Four Pillars of Our Analysis
            </Typography>
            <Typography sx={{ fontSize: '1.05rem', color: theme.palette.text.secondary, maxWidth: '620px', mx: 'auto', lineHeight: 1.8 }}>
              The research engine applies all four simultaneously. A stock must pass every pillar to generate a signal.
            </Typography>
          </Box>

          <Grid container spacing={3}>
            {researchDimensions.map((dim, idx) => (
              <Grid item xs={12} sm={6} key={idx}>
                <Card
                  sx={{
                    height: '100%',
                    border: `1px solid ${theme.palette.divider}`,
                    backgroundColor: theme.palette.background.default,
                    borderRadius: '0px',
                    boxShadow: 'none',
                    transition: 'all 0.25s ease',
                    '&:hover': {
                      borderColor: theme.palette.primary.main,
                      boxShadow: '0 4px 16px rgba(0,0,0,0.07)',
                    },
                  }}
                >
                  <CardContent sx={{ p: 3.5 }}>
                    <Box
                      sx={{
                        width: 44,
                        height: 44,
                        borderRadius: '0px',
                        backgroundColor: alpha(theme.palette.primary.main, 0.1),
                        color: theme.palette.primary.main,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        mb: 2,
                        border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`,
                      }}
                    >
                      {dim.icon}
                    </Box>
                    <Typography variant="h6" sx={{ fontWeight: 700, mb: 1.5, color: theme.palette.text.primary, fontSize: '1.05rem' }}>
                      {dim.title}
                    </Typography>
                    <Typography variant="body2" sx={{ color: theme.palette.text.secondary, lineHeight: 1.7 }}>
                      {dim.description}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Process Steps */}
      <Box
        sx={{
          py: { xs: 8, md: 10 },
          backgroundColor: alpha(theme.palette.primary.main, 0.03),
          borderTop: `1px solid ${theme.palette.divider}`,
        }}
      >
        <Container maxWidth="lg">
          <Box sx={{ textAlign: 'center', mb: 7 }}>
            <Typography
              variant="overline"
              sx={{ color: theme.palette.primary.main, fontWeight: 700, letterSpacing: '3px', display: 'block', mb: 1.5 }}
            >
              Daily Process
            </Typography>
            <Typography
              variant="h3"
              sx={{
                fontSize: { xs: '1.9rem', sm: '2.3rem', md: '2.8rem' },
                fontWeight: 800,
                mb: 2,
                color: theme.palette.text.primary,
                letterSpacing: '-0.5px',
              }}
            >
              From Data to Signal Every Day
            </Typography>
            <Typography sx={{ fontSize: '1.05rem', color: theme.palette.text.secondary, maxWidth: '600px', mx: 'auto', lineHeight: 1.8 }}>
              The research pipeline runs automatically before market open. Here&apos;s how raw data becomes actionable signals.
            </Typography>
          </Box>

          <Grid container spacing={3}>
            {processSteps.map((item, idx) => (
              <Grid item xs={12} sm={6} md={3} key={idx}>
                <Box sx={{ position: 'relative', height: '100%' }}>
                  <Box
                    sx={{
                      position: 'absolute',
                      top: -1,
                      left: -1,
                      backgroundColor: theme.palette.primary.main,
                      color: '#fff',
                      px: 1.5,
                      py: 0.5,
                      fontWeight: 900,
                      fontSize: '0.8rem',
                      letterSpacing: '1px',
                      zIndex: 1,
                    }}
                  >
                    {item.step}
                  </Box>
                  <Box
                    sx={{
                      pt: 5,
                      px: 3,
                      pb: 3,
                      border: `1px solid ${theme.palette.divider}`,
                      backgroundColor: theme.palette.background.paper,
                      height: '100%',
                    }}
                  >
                    <Typography variant="h6" sx={{ fontWeight: 700, mb: 1.5, color: theme.palette.text.primary, fontSize: '1rem' }}>
                      {item.title}
                    </Typography>
                    <Typography variant="body2" sx={{ color: theme.palette.text.secondary, lineHeight: 1.7 }}
                      dangerouslySetInnerHTML={{ __html: item.description }}
                    />
                  </Box>
                </Box>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* What Sets It Apart */}
      <Box sx={{ py: { xs: 8, md: 10 }, backgroundColor: theme.palette.background.default }}>
        <Container maxWidth="lg">
          <Box sx={{ textAlign: 'center', mb: 7 }}>
            <Typography
              variant="overline"
              sx={{ color: theme.palette.primary.main, fontWeight: 700, letterSpacing: '3px', display: 'block', mb: 1.5 }}
            >
              Why It Works
            </Typography>
            <Typography
              variant="h3"
              sx={{
                fontSize: { xs: '1.9rem', sm: '2.3rem', md: '2.8rem' },
                fontWeight: 800,
                mb: 2,
                color: theme.palette.text.primary,
                letterSpacing: '-0.5px',
              }}
            >
              What Sets Our Research Apart
            </Typography>
            <Typography sx={{ fontSize: '1.05rem', color: theme.palette.text.secondary, maxWidth: '600px', mx: 'auto', lineHeight: 1.8 }}>
              Most research platforms generate noise. Ours generates signal.
            </Typography>
          </Box>

          <Grid container spacing={3}>
            {differentiators.map((item, idx) => (
              <Grid item xs={12} sm={6} key={idx}>
                <Card
                  sx={{
                    height: '100%',
                    border: `1px solid ${theme.palette.divider}`,
                    backgroundColor: theme.palette.background.paper,
                    borderRadius: '0px',
                    boxShadow: 'none',
                    transition: 'all 0.25s ease',
                    '&:hover': {
                      boxShadow: '0 4px 16px rgba(0,0,0,0.07)',
                    },
                  }}
                >
                  <CardContent sx={{ p: 3.5 }}>
                    <Typography
                      sx={{
                        fontSize: '2.2rem',
                        fontWeight: 900,
                        color: alpha(theme.palette.primary.main, 0.25),
                        lineHeight: 1,
                        mb: 1,
                        fontVariantNumeric: 'tabular-nums',
                      }}
                    >
                      {item.number}
                    </Typography>
                    <Typography variant="h6" sx={{ fontWeight: 700, mb: 1.5, color: theme.palette.text.primary, fontSize: '1.05rem' }}>
                      {item.title}
                    </Typography>
                    <Typography variant="body2" sx={{ color: theme.palette.text.secondary, lineHeight: 1.7 }}>
                      {item.description}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      <CTASection
        variant="dark"
        title="See the Research in Action"
        subtitle="Access trading signals, stock scores, and market analysis built on this methodology&#8212;free."
        primaryCTA={{ label: 'Launch Platform', link: '/app/markets' }}
        secondaryCTA={{ label: 'View Trading Signals', link: '/app/trading-signals' }}
      />
    </MarketingLayout>
  );
};

export default ResearchInsights;
