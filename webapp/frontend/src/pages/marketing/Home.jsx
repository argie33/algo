import React from 'react';
import { Box, Container, Typography, Grid, alpha, useTheme, Card, CardContent, Chip, Button } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import HeroSection from '../../components/marketing/HeroSection';
import FeatureGrid from '../../components/marketing/FeatureGrid';
import CTASection from '../../components/marketing/CTASection';
import CommunitySignup from '../../components/marketing/CommunitySignup';
import {
  Event as EventIcon,
  Psychology as PsychologyIcon,
  Business as BusinessIcon,
  Analytics as AnalyticsIcon,
  Storage as StorageIcon,
  Scoreboard as ScoreboardIcon,
  FilterAlt as FilterAltIcon,
  ArrowForward as ArrowForwardIcon,
} from '@mui/icons-material';

const Home = () => {
  const theme = useTheme();
  const navigate = useNavigate();

  const articlesData = [
    {
      id: 'great-rotation',
      title: 'The Great Rotation: Capital Flows Signal a Structural Shift Away From Mega-Cap Concentration',
      date: 'May 12, 2026',
      author: 'Anthony Riga',
      excerpt: 'Market breadth expanding significantly as institutional capital rotates away from mega-cap concentration. Real data on valuations, flows, and structural drivers.',
      tags: ['Macro Analysis', 'Market Rotation', 'Institutional Flows'],
    },
    {
      id: 'ai-efficiencies',
      title: 'The AI Productivity Inflection: How Adoption is Creating a Multi-Year Economic Super-Cycle',
      date: 'May 5, 2026',
      author: 'Anthony Riga',
      excerpt: 'AI benefits spreading from software into manufacturing, logistics, and healthcare. Backed by real productivity data and sector-specific economic analysis.',
      tags: ['AI Economics', 'Productivity', 'Structural Trends'],
    },
  ];

  const dataCapabilities = [
    { label: 'Equity Research', detail: 'Systematic stock analysis, multi-factor valuation models, and institutional-grade comparative metrics across 5,300+ US equities' },
    { label: 'Earnings Dynamics', detail: 'Comprehensive earnings patterns, analyst revision analysis, and historical surprise data with 10+ years of context' },
    { label: 'Market Structure', detail: 'Real-time technical analysis, volume dynamics, advance/decline breadth, and distribution day tracking' },
    { label: 'Macro & Economic', detail: 'Federal Reserve data integration, FRED economic indicators, and yield curve analysis updated daily' },
    { label: 'Sector Rotation', detail: 'Industry relative performance, sector dynamics, and competitive positioning analysis with momentum filters' },
    { label: 'Quantitative Signals', detail: 'Minervini-style trend template scoring, systematic pattern recognition, and backtested entry/exit criteria' },
  ];

  const keyFeatures = [
    {
      icon: <AnalyticsIcon fontSize="large" />,
      title: 'Quantitative Equity Scoring',
      description:
        'Multi-factor scoring models evaluate securities across valuation, earnings quality, momentum, and technical structure. Screen and rank 5,300+ stocks by composite score in real time.',
      tags: ['Quantitative', 'Equity Research', 'Analytics'],
      link: '/app/scores',
    },
    {
      icon: <EventIcon fontSize="large" />,
      title: 'Earnings & Fundamental Analysis',
      description:
        'Rigorous earnings research integrating historical patterns, analyst estimate dynamics, surprise analysis, and revision trends. Over a decade of earnings data for systematic pattern identification.',
      tags: ['Earnings', 'Fundamentals', 'Research'],
      link: '/app/earnings',
    },
    {
      icon: <PsychologyIcon fontSize="large" />,
      title: 'Sentiment & Institutional Positioning',
      description:
        'Comprehensive positioning analysis tracking analyst sentiment shifts, institutional allocations, and market structure indicators. Identify positioning extremes that historically precede reversals.',
      tags: ['Sentiment', 'Positioning', 'Research'],
      link: '/app/sentiment',
    },
    {
      icon: <BusinessIcon fontSize="large" />,
      title: 'Sector & Macro Intelligence',
      description:
        'Systematic sector rotation analysis, macroeconomic research, and Fed policy impact assessment. Real FRED data integration for yield curve, credit spreads, and employment trends.',
      tags: ['Sectors', 'Economics', 'Macro'],
      link: '/app/markets',
    },
  ];

  return (
    <MarketingLayout>
      <HeroSection />

      {/* Value Proposition */}
      <Box sx={{ py: { xs: 8, md: 10 }, backgroundColor: theme.palette.background.default }}>
        <Container maxWidth="lg">
          <Box sx={{ textAlign: 'center', mb: 6 }}>
            <Typography
              variant="overline"
              sx={{ color: theme.palette.primary.main, fontWeight: 700, letterSpacing: '3px', display: 'block', mb: 1.5 }}
            >
              What We Cover
            </Typography>
            <Typography
              variant="h3"
              sx={{
                fontSize: { xs: '1.9rem', sm: '2.3rem', md: '2.8rem' },
                fontWeight: 800,
                mb: 2.5,
                color: theme.palette.text.primary,
                letterSpacing: '-0.5px',
              }}
            >
              Six Dimensions of Research
            </Typography>
            <Typography
              sx={{
                fontSize: '1.1rem',
                color: theme.palette.text.secondary,
                maxWidth: '700px',
                mx: 'auto',
                lineHeight: 1.8,
              }}
            >
              Bullseye integrates fundamental valuation, earnings dynamics, technical structure,
              sentiment positioning, sector rotation, and quantitative analysis into a single
              research framework&#8212;the same depth that institutional desks pay millions for, free.
            </Typography>
          </Box>

          <Grid container spacing={3}>
            {dataCapabilities.map((item, idx) => (
              <Grid item xs={12} sm={6} md={4} key={idx}>
                <Box
                  sx={{
                    p: 3,
                    height: '100%',
                    backgroundColor: theme.palette.background.paper,
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: '0px',
                    borderTop: `3px solid ${theme.palette.primary.main}`,
                    transition: 'all 0.25s ease',
                    '&:hover': {
                      boxShadow: '0 8px 24px rgba(0,0,0,0.09)',
                      borderTopColor: theme.palette.primary.main,
                    },
                  }}
                >
                  <Typography
                    sx={{
                      fontWeight: 700,
                      color: theme.palette.primary.main,
                      mb: 1,
                      fontSize: '0.95rem',
                      textTransform: 'uppercase',
                      letterSpacing: '0.5px',
                    }}
                  >
                    {item.label}
                  </Typography>
                  <Typography
                    sx={{
                      color: theme.palette.text.secondary,
                      fontSize: '0.92rem',
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

      {/* By the Numbers Strip */}
      <Box
        sx={{
          py: { xs: 5, md: 6 },
          backgroundColor: theme.palette.primary.main,
        }}
      >
        <Container maxWidth="lg">
          <Grid container spacing={0} justifyContent="center">
            {[
              { stat: '5,300+', label: 'US Equities Covered' },
              { stat: '10+', label: 'Years of Historical Data' },
              { stat: '6', label: 'Research Dimensions' },
              { stat: '100%', label: 'Free to Use' },
            ].map((item, idx) => (
              <Grid
                item
                xs={6}
                md={3}
                key={idx}
                sx={{
                  textAlign: 'center',
                  py: { xs: 2, md: 1 },
                  borderRight: { md: idx < 3 ? `1px solid ${alpha('#fff', 0.2)}` : 'none' },
                }}
              >
                <Typography
                  sx={{
                    fontSize: { xs: '2.2rem', md: '2.8rem' },
                    fontWeight: 900,
                    color: '#fff',
                    lineHeight: 1,
                  }}
                >
                  {item.stat}
                </Typography>
                <Typography
                  sx={{
                    fontSize: '0.85rem',
                    color: alpha('#fff', 0.8),
                    mt: 0.5,
                    fontWeight: 500,
                    textTransform: 'uppercase',
                    letterSpacing: '0.5px',
                  }}
                >
                  {item.label}
                </Typography>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* How It Works */}
      <Box sx={{ py: { xs: 8, md: 10 }, backgroundColor: theme.palette.background.paper }}>
        <Container maxWidth="lg">
          <Box sx={{ textAlign: 'center', mb: 7 }}>
            <Typography
              variant="overline"
              sx={{ color: theme.palette.primary.main, fontWeight: 700, letterSpacing: '3px', display: 'block', mb: 1.5 }}
            >
              How It Works
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
              From Raw Data to Actionable Signal
            </Typography>
            <Typography
              sx={{
                fontSize: '1.05rem',
                color: theme.palette.text.secondary,
                maxWidth: '620px',
                mx: 'auto',
                lineHeight: 1.8,
              }}
            >
              Bullseye runs the same systematic research pipeline institutional desks run every day&#8212;automatically,
              before market open, every trading day.
            </Typography>
          </Box>

          <Grid container spacing={0}>
            {[
              {
                step: '01',
                icon: <StorageIcon />,
                title: 'Data Pipeline Runs Nightly',
                description:
                  'Twenty-four automated loaders update prices, technicals, fundamentals, earnings, sentiment, and FRED economic data from authoritative sources before market open. No manual work required.',
              },
              {
                step: '02',
                icon: <ScoreboardIcon />,
                title: 'Every Stock Gets Scored',
                description:
                  'Each of the 5,300+ equities in our universe is scored across valuation, earnings quality, momentum, trend strength, and fundamental health. Composite scores updated every trading day.',
              },
              {
                step: '03',
                icon: <FilterAltIcon />,
                title: 'Signals Pass Six Rigorous Filters',
                description:
                  'Top-ranked candidates run through market health gating, Minervini trend template, fundamental quality screens, portfolio constraints, and advanced technical criteria. Only the highest-conviction setups reach your screen.',
              },
            ].map((item, idx) => (
              <Grid
                item
                xs={12}
                md={4}
                key={idx}
                sx={{
                  position: 'relative',
                  '&::after': {
                    content: idx < 2 ? '""' : 'none',
                    display: { xs: 'none', md: 'block' },
                    position: 'absolute',
                    top: 28,
                    right: 0,
                    width: '50%',
                    height: 2,
                    backgroundColor: alpha(theme.palette.primary.main, 0.18),
                    zIndex: 0,
                  },
                }}
              >
                <Box sx={{ p: { xs: 3, md: 4 }, textAlign: 'center', position: 'relative', zIndex: 1 }}>
                  <Box
                    sx={{
                      width: 60,
                      height: 60,
                      borderRadius: '50%',
                      backgroundColor: alpha(theme.palette.primary.main, 0.1),
                      border: `2px solid ${alpha(theme.palette.primary.main, 0.25)}`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      mx: 'auto',
                      mb: 2.5,
                      color: theme.palette.primary.main,
                      '& svg': { fontSize: '1.6rem' },
                    }}
                  >
                    {item.icon}
                  </Box>
                  <Typography
                    sx={{
                      fontSize: '0.68rem',
                      fontWeight: 800,
                      letterSpacing: '2.5px',
                      color: theme.palette.primary.main,
                      mb: 1.5,
                      textTransform: 'uppercase',
                    }}
                  >
                    Step {item.step}
                  </Typography>
                  <Typography
                    variant="h6"
                    sx={{ fontWeight: 700, mb: 1.5, color: theme.palette.text.primary, fontSize: '1.05rem' }}
                  >
                    {item.title}
                  </Typography>
                  <Typography variant="body2" sx={{ color: theme.palette.text.secondary, lineHeight: 1.75 }}>
                    {item.description}
                  </Typography>
                </Box>
              </Grid>
            ))}
          </Grid>

          <Box sx={{ textAlign: 'center', mt: 5 }}>
            <Button
              variant="outlined"
              endIcon={<ArrowForwardIcon />}
              onClick={() => navigate('/research-insights')}
              sx={{
                fontWeight: 600,
                textTransform: 'none',
                borderRadius: '0px',
                px: 4,
                py: 1.25,
                borderColor: alpha(theme.palette.primary.main, 0.4),
                '&:hover': {
                  backgroundColor: alpha(theme.palette.primary.main, 0.05),
                  borderColor: theme.palette.primary.main,
                },
              }}
            >
              See Full Research Methodology
            </Button>
          </Box>
        </Container>
      </Box>

      {/* Core Research Capabilities */}
      <FeatureGrid
        title="Platform Capabilities"
        subtitle="Integrated research tools spanning fundamentals, technicals, sentiment, and macro&#8212;built for investors who take their edge seriously"
        features={keyFeatures}
        columns={{ xs: 1, sm: 2, md: 2, lg: 2 }}
      />

      {/* Latest Market Insights */}
      <Box sx={{ py: { xs: 8, md: 10 }, backgroundColor: theme.palette.background.paper }}>
        <Container maxWidth="lg">
          <Box sx={{ textAlign: 'center', mb: 6 }}>
            <Typography
              variant="overline"
              sx={{ color: theme.palette.primary.main, fontWeight: 700, letterSpacing: '3px', display: 'block', mb: 1.5 }}
            >
              Research & Analysis
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
              Latest Market Insights
            </Typography>
            <Typography
              sx={{
                fontSize: '1.05rem',
                color: theme.palette.text.secondary,
                maxWidth: '600px',
                mx: 'auto',
              }}
            >
              Current research: market dynamics, rotation patterns, and strategic positioning
            </Typography>
          </Box>

          <Grid container spacing={4} justifyContent="center" sx={{ mb: 5 }}>
            {articlesData.map((insight, idx) => (
              <Grid item xs={12} md={6} key={idx}>
                <Card
                  onClick={() => navigate(`/articles/${insight.id}`)}
                  sx={{
                    height: '100%',
                    border: `1px solid ${theme.palette.divider}`,
                    backgroundColor: theme.palette.background.default,
                    borderRadius: '0px',
                    borderLeft: `4px solid ${theme.palette.primary.main}`,
                    transition: 'all 0.25s ease',
                    cursor: 'pointer',
                    boxShadow: 'none',
                    '&:hover': {
                      boxShadow: '0 8px 24px rgba(0,0,0,0.1)',
                      transform: 'translateY(-3px)',
                    },
                  }}
                >
                  <CardContent sx={{ p: 3.5 }}>
                    <Typography
                      variant="body2"
                      sx={{
                        fontSize: '0.78rem',
                        color: theme.palette.primary.main,
                        fontWeight: 700,
                        mb: 1.5,
                        textTransform: 'uppercase',
                        letterSpacing: '0.5px',
                      }}
                    >
                      {insight.date} &middot; {insight.author}
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
                        lineHeight: 1.7,
                        mb: 2.5,
                      }}
                    >
                      {insight.excerpt}
                    </Typography>
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, mb: 2.5 }}>
                      {insight.tags.map((tag, i) => (
                        <Chip
                          key={i}
                          label={tag}
                          size="small"
                          sx={{
                            borderRadius: '0px',
                            fontSize: '0.7rem',
                            fontWeight: 600,
                            backgroundColor: alpha(theme.palette.primary.main, 0.08),
                            color: theme.palette.primary.main,
                            border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`,
                            height: 24,
                          }}
                        />
                      ))}
                    </Box>
                    <Box
                      sx={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 0.5,
                        fontSize: '0.82rem',
                        fontWeight: 700,
                        color: theme.palette.primary.main,
                      }}
                    >
                      Read Article <ArrowForwardIcon sx={{ fontSize: '0.95rem' }} />
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>

          <Box sx={{ textAlign: 'center' }}>
            <Button
              variant="outlined"
              endIcon={<ArrowForwardIcon />}
              onClick={() => navigate('/research-insights')}
              sx={{
                fontWeight: 600,
                textTransform: 'none',
                borderRadius: '0px',
                px: 4,
                py: 1.25,
                borderColor: alpha(theme.palette.primary.main, 0.4),
                '&:hover': {
                  backgroundColor: alpha(theme.palette.primary.main, 0.05),
                  borderColor: theme.palette.primary.main,
                },
              }}
            >
              Explore Our Research Methodology
            </Button>
          </Box>
        </Container>
      </Box>

      <CommunitySignup />

      <CTASection
        variant="dark"
        title="Ready to Research Like a Pro?"
        subtitle="Access institutional-grade equity research, trading signals, and market intelligence&#8212;completely free."
        primaryCTA={{ label: 'Launch Platform', link: '/app/markets' }}
        secondaryCTA={{ label: 'Learn More', link: '/research-insights' }}
      />
    </MarketingLayout>
  );
};

export default Home;
