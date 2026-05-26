import React from 'react';
import { Container, Box, Typography, Grid, Card, CardContent, useTheme, alpha } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import CTASection from '../../components/marketing/CTASection';
import ImagePlaceholder from '../../components/marketing/ImagePlaceholder';
import {
  AccountBalance as AccountBalanceIcon,
  TrackChanges as TrackChangesIcon,
  BarChart as BarChartIcon,
  Shield as ShieldIcon,
  ShowChart as ShowChartIcon,
  Assessment as AssessmentIcon,
} from '@mui/icons-material';

const WealthManagement = () => {
  const theme = useTheme();
  const navigate = useNavigate();

  const features = [
    {
      icon: <TrackChangesIcon />,
      title: 'Pre-Trade Simulation',
      description: 'Run hypothetical trades through our risk model before you place them. Evaluate position sizing, expected drawdown, and portfolio impact based on historical volatility and current market regime.',
      link: '/app/simulate',
    },
    {
      icon: <BarChartIcon />,
      title: 'Portfolio Dashboard',
      description: 'Track all open positions in one view. See real-time P&L, position sizing relative to portfolio, days held, and entry vs. current price&#8212;with automatic Alpaca reconciliation.',
      link: '/app/portfolio',
    },
    {
      icon: <ShowChartIcon />,
      title: 'Performance Metrics',
      description: 'Analyze your trading record with win rate, average gain/loss, expectancy, and trade-by-trade attribution. Understand which setups and conditions are actually producing returns.',
      link: '/app/performance',
    },
    {
      icon: <ShieldIcon />,
      title: 'Risk & Circuit Breakers',
      description: 'Automated circuit breakers evaluate drawdown, consecutive losses, daily P&L limits, and VIX conditions before any trade is placed. The system protects capital in adverse regimes.',
    },
    {
      icon: <AssessmentIcon />,
      title: 'Trade Tracker & History',
      description: 'Complete audit trail of every entry, exit, and hold decision&#8212;including the specific signals and scores that triggered each trade. Full transparency into your track record.',
      link: '/app/trades',
    },
    {
      icon: <AccountBalanceIcon />,
      title: 'Position Sizing Engine',
      description: 'Risk-based position sizing calculates trade size as a percentage of portfolio capital, calibrated to volatility (ATR) and account-level risk parameters set in the system configuration.',
    },
  ];

  const riskLevels = [
    { label: 'Drawdown Limit', detail: 'Maximum portfolio drawdown threshold before trading halts' },
    { label: 'Daily Loss Cap', detail: 'Single-session P&L floor that triggers a circuit breaker' },
    { label: 'Consecutive Losses', detail: 'Streak-based risk filter to pause after losing runs' },
    { label: 'VIX Gate', detail: 'Market volatility threshold that restricts new entries' },
    { label: 'ATR Sizing', detail: 'Position size scaled to each stock\'s average true range' },
    { label: 'Market Stage', detail: 'No new longs in Stage 4 (declining) market regimes' },
  ];

  return (
    <MarketingLayout>
      <PageHeader
        title="Portfolio & Risk Management"
        subtitle="Tools for sizing, tracking, and protecting your positions with systematic discipline"
      />

      {/* Hero Section */}
      <Box sx={{ py: { xs: 8, md: 10 }, backgroundColor: theme.palette.background.default }}>
        <Container maxWidth="lg">
          <Grid container spacing={7} alignItems="center">
            <Grid item xs={12} md={6}>
              <Typography
                variant="overline"
                sx={{ color: theme.palette.primary.main, fontWeight: 700, letterSpacing: '3px', display: 'block', mb: 1.5 }}
              >
                Capital Protection First
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
                Systematic Risk. Disciplined Execution.
              </Typography>
              <Typography
                variant="body1"
                sx={{
                  fontSize: '1.1rem',
                  color: theme.palette.text.secondary,
                  lineHeight: 1.8,
                  mb: 3,
                }}
              >
                The best trade is the one that doesn&apos;t blow up your portfolio. Bullseye&apos;s risk
                management layer enforces position sizing, monitors drawdown, and runs automated
                circuit breakers&#8212;so discipline is built into the system, not left to willpower.
              </Typography>
              <Typography
                variant="body1"
                sx={{
                  fontSize: '1rem',
                  color: theme.palette.text.secondary,
                  lineHeight: 1.8,
                }}
              >
                From pre-trade simulation to real-time P&amp;L tracking and full performance analytics,
                the portfolio tools give you the visibility and controls that professional traders rely on.
              </Typography>
            </Grid>
            <Grid item xs={12} md={6}>
              <ImagePlaceholder
                src="https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?w=900&h=650&fit=crop&auto=format&q=80"
                alt="Portfolio performance and risk analytics dashboard"
                height={{ xs: '300px', md: '420px' }}
              />
            </Grid>
          </Grid>
        </Container>
      </Box>

      {/* Risk Controls Strip */}
      <Box
        sx={{
          py: { xs: 6, md: 7 },
          backgroundColor: alpha(theme.palette.primary.main, 0.04),
          borderTop: `1px solid ${theme.palette.divider}`,
          borderBottom: `1px solid ${theme.palette.divider}`,
        }}
      >
        <Container maxWidth="lg">
          <Box sx={{ textAlign: 'center', mb: 5 }}>
            <Typography
              variant="overline"
              sx={{ color: theme.palette.primary.main, fontWeight: 700, letterSpacing: '3px', display: 'block', mb: 1 }}
            >
              Built-In Protection
            </Typography>
            <Typography variant="h4" sx={{ fontWeight: 800, color: theme.palette.text.primary, mb: 1.5 }}>
              Six-Layer Risk Framework
            </Typography>
            <Typography sx={{ color: theme.palette.text.secondary, fontSize: '1rem', maxWidth: '600px', mx: 'auto' }}>
              Every trade passes through automated risk checks before execution. No override, no exceptions.
            </Typography>
          </Box>
          <Grid container spacing={3}>
            {riskLevels.map((item, idx) => (
              <Grid item xs={12} sm={6} md={4} key={idx}>
                <Box
                  sx={{
                    p: 3,
                    backgroundColor: theme.palette.background.paper,
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: '0px',
                    borderLeft: `3px solid ${theme.palette.primary.main}`,
                    height: '100%',
                  }}
                >
                  <Typography sx={{ fontWeight: 700, color: theme.palette.text.primary, mb: 0.75, fontSize: '0.95rem' }}>
                    {item.label}
                  </Typography>
                  <Typography sx={{ color: theme.palette.text.secondary, fontSize: '0.88rem', lineHeight: 1.6 }}>
                    {item.detail}
                  </Typography>
                </Box>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Feature Cards */}
      <Container maxWidth="lg" sx={{ py: { xs: 8, md: 10 } }}>
        <Box sx={{ textAlign: 'center', mb: 7 }}>
          <Typography
            variant="overline"
            sx={{ color: theme.palette.primary.main, fontWeight: 700, letterSpacing: '3px', display: 'block', mb: 1.5 }}
          >
            Portfolio Tools
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
            Everything You Need to Manage Capital
          </Typography>
          <Typography
            sx={{ fontSize: '1.05rem', color: theme.palette.text.secondary, maxWidth: '600px', mx: 'auto', lineHeight: 1.8 }}
          >
            Professional-grade portfolio management tools built for active traders and systematic investors
          </Typography>
        </Box>

        <Grid container spacing={3}>
          {features.map((feature, idx) => (
            <Grid item xs={12} sm={6} key={idx}>
              <Card
                onClick={feature.link ? () => navigate(feature.link) : undefined}
                sx={{
                  height: '100%',
                  border: `1px solid ${theme.palette.divider}`,
                  backgroundColor: theme.palette.background.paper,
                  borderRadius: '0px',
                  boxShadow: 'none',
                  cursor: feature.link ? 'pointer' : 'default',
                  transition: 'all 0.25s ease',
                  '&:hover': {
                    boxShadow: '0 6px 20px rgba(0,0,0,0.09)',
                    borderColor: feature.link ? theme.palette.primary.main : theme.palette.divider,
                    transform: feature.link ? 'translateY(-3px)' : 'none',
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
                    {feature.icon}
                  </Box>
                  <Typography
                    variant="h6"
                    sx={{ fontWeight: 700, mb: 1.5, color: theme.palette.primary.main, fontSize: '1.05rem' }}
                  >
                    {feature.title}
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{ color: theme.palette.text.secondary, lineHeight: 1.7 }}
                    dangerouslySetInnerHTML={{ __html: feature.description }}
                  />
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Container>

      <CTASection
        variant="dark"
        title="Start Managing Risk the Right Way"
        subtitle="Access the full portfolio and risk management suite&#8212;pre-trade simulation, live P&L, and performance analytics."
        primaryCTA={{ label: 'Launch Platform', link: '/app/portfolio' }}
        secondaryCTA={{ label: 'View Trading Signals', link: '/app/trading-signals' }}
      />
    </MarketingLayout>
  );
};

export default WealthManagement;
