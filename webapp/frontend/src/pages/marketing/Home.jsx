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

  const articlesData = [
    {
      id: 'great-rotation',
      title: 'The Great Rotation: Capital Flows Signal Structural Market Shift Away From Concentration',
      date: 'February 7, 2026',
      author: 'Erik A.',
      excerpt: 'Market breadth expanding significantly as institutional capital rotates away from mega-cap concentration. Real data on valuations, flows, and structural drivers.',
      tags: ['Macro Analysis', 'Market Rotation', 'Institutional Flows'],
      tickers: [],
    },
    {
      id: 'ai-efficiencies',
      title: 'The AI Productivity Inflection: How AI Adoption is Creating a Multi-Year Economic Super-Cycle',
      date: 'February 5, 2026',
      author: 'Erik A.',
      excerpt: 'AI benefits spreading from software into manufacturing, logistics, healthcare sectors. Backed by real productivity data and sector-specific economic analysis.',
      tags: ['AI Economics', 'Productivity', 'Structural Trends'],
      tickers: [],
    },
  ];

  const dataCapabilities = [
    { label: 'Equity Research', detail: 'Systematic stock analysis, multi-factor valuation models, and institutional-grade comparative metrics' },
    { label: 'Earnings Dynamics', detail: 'Comprehensive earnings patterns, analyst revision analysis, and surprise probability assessment' },
    { label: 'Market Structure', detail: 'Real-time technical analysis, volume dynamics, and market microstructure patterns' },
    { label: 'Macro Policy', detail: 'Federal Reserve analysis, economic indicators, and interest rate impact assessment' },
    { label: 'Sector Rotation', detail: 'Industry relative performance, sector dynamics, and competitive positioning analysis' },
    { label: 'Quantitative Factors', detail: 'Advanced factor analysis, systematic pattern recognition, and historical performance validation' },
  ];

  const keyFeatures = [
    {
      icon: <AnalyticsIcon fontSize="large" />,
      title: 'Quantitative Equity Analysis',
      description:
        'Systematic multi-factor research models evaluating securities across valuation, earnings quality, momentum dynamics, and technical structure. Real-time comparative analytics for comprehensive security evaluation.',
      tags: ['Quantitative', 'Equity Research', 'Analytics'],
      link: '/app/scores',
    },
    {
      icon: <EventIcon fontSize="large" />,
      title: 'Earnings Fundamentals',
      description:
        'Rigorous earnings research integrating historical patterns, analyst estimate dynamics, surprise analysis, and revision trends. Over a decade of earnings data for systematic pattern identification.',
      tags: ['Earnings', 'Fundamentals', 'Research'],
      link: '/app/earnings',
    },
    {
      icon: <PsychologyIcon fontSize="large" />,
      title: 'Institutional Positioning',
      description:
        'Comprehensive positioning analysis tracking analyst sentiment, institutional allocations, and market structure indicators. Identify positioning extremes that historically signal market inflection points.',
      tags: ['Sentiment', 'Positioning', 'Research'],
      link: '/app/sentiment',
    },
    {
      icon: <BusinessIcon fontSize="large" />,
      title: 'Sector & Macro Analysis',
      description:
        'Systematic sector rotation analysis, macroeconomic research, and policy impact assessment. Integrate Fed policy, economic indicators, and market regime analysis for strategic positioning.',
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
            Bullseye Financial provides comprehensive equity research integrating fundamental valuation, earnings dynamics, technical market structure, sentiment positioning, and quantitative analysis. Our integrated research framework delivers the systematic, institutional-grade intelligence that professional investors require for disciplined capital allocation.
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
          <ImagePlaceholder
            src="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%271200%27 height=%27400%27%3E%3Crect fill=%27%234a5568%27 width=%271200%27 height=%27400%27/%3E%3Ctext x=%2750%25%27 y=%2750%25%27 font-size=%2732%27 fill=%27white%27 text-anchor=%27middle%27 dominant-baseline=%27middle%27 font-family=%27Arial%27%3EProfessional Market Analysis%3C/text%3E%3C/svg%3E"
            alt="Team collaborating on financial research"
            height={{ xs: '250px', md: '350px' }}
          />
        </Container>
      </Box>


      {/* Core Research Capabilities */}
      <FeatureGrid
        title="Core Research Capabilities"
        subtitle="Integrated equity research integrating fundamental analysis, technical market structure, sentiment positioning, and quantitative modeling"
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
            Current Research Analysis: Market Dynamics, Rotation Patterns, and Strategic Positioning
          </Typography>
          <Grid container spacing={4} justifyContent="center">
            {articlesData.map((insight, idx) => (
              <Grid item xs={12} md={4} key={idx}>
                <Card
                  onClick={() => navigate(`/articles/${insight.id}`)}
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
