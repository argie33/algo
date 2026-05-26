import React from 'react';
import { Container, Box, Typography, useTheme, Grid, Card, CardContent, alpha } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import CTASection from '../../components/marketing/CTASection';
import CommunitySignup from '../../components/marketing/CommunitySignup';
import ImagePlaceholder from '../../components/marketing/ImagePlaceholder';

const About = () => {
  const theme = useTheme();

  const journey = [
    {
      heading: 'The Problem',
      body: 'Institutional investors get Bloomberg terminals, sell-side research desks, and quant teams. Individual investors get financial TV and social media. The information asymmetry is enormous&#8212;and it shows in most retail investors\' returns.',
    },
    {
      heading: 'The Approach',
      body: 'We built the same research infrastructure that institutional desks use&#8212;automated data pipelines, systematic scoring models, backtested signals, and market health monitoring&#8212;and made it free. No paywall. No subscription. No catch.',
    },
    {
      heading: 'The Result',
      body: 'A platform covering 5,300+ US equities across six research dimensions: fundamental valuation, earnings dynamics, technical structure, sentiment positioning, sector rotation, and quantitative factors. Updated every trading day before market open.',
    },
  ];

  return (
    <MarketingLayout>
      <PageHeader
        title="About Bullseye Financial"
        subtitle="Our story, our mission, and our commitment to giving every investor institutional-grade research tools"
      />

      {/* Origin Story */}
      <Box sx={{ py: { xs: 8, md: 10 }, backgroundColor: theme.palette.background.default }}>
        <Container maxWidth="lg">
          <Grid container spacing={7} alignItems="center">
            <Grid item xs={12} md={6}>
              <Typography
                variant="overline"
                sx={{ color: theme.palette.primary.main, fontWeight: 700, letterSpacing: '3px', display: 'block', mb: 1.5 }}
              >
                Our Story
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
                Leveling the Playing Field
              </Typography>
              <Typography
                sx={{ fontSize: '1.05rem', color: theme.palette.text.secondary, mb: 3, lineHeight: 1.8 }}
              >
                Bullseye Financial was built by investors who were frustrated watching Wall Street
                have all the advantages. The systematic tools that drive institutional returns&#8212;quantitative
                screening, earnings analytics, market health monitoring, trend analysis&#8212;shouldn&apos;t
                require a six-figure budget.
              </Typography>
              <Typography
                sx={{ fontSize: '1.05rem', color: theme.palette.text.secondary, lineHeight: 1.8 }}
              >
                So we built them. From the ground up. The entire platform&#8212;data pipeline,
                research models, trading algorithm, and web interface&#8212;was designed and
                built in-house. Every piece reflects years of research into what actually
                works in equity markets.
              </Typography>
            </Grid>
            <Grid item xs={12} md={6}>
              <ImagePlaceholder
                src="https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=900&h=650&fit=crop&auto=format&q=80"
                alt="Analytics dashboard with market research data"
                height={{ xs: '280px', md: '400px' }}
              />
            </Grid>
          </Grid>
        </Container>
      </Box>

      {/* The Journey */}
      <Box sx={{ py: { xs: 8, md: 10 }, backgroundColor: theme.palette.background.paper }}>
        <Container maxWidth="lg">
          <Box sx={{ textAlign: 'center', mb: 7 }}>
            <Typography
              variant="overline"
              sx={{ color: theme.palette.primary.main, fontWeight: 700, letterSpacing: '3px', display: 'block', mb: 1.5 }}
            >
              Our Mission
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
              The Problem We&apos;re Solving
            </Typography>
          </Box>
          <Grid container spacing={4}>
            {journey.map((item, idx) => (
              <Grid item xs={12} md={4} key={idx}>
                <Card
                  sx={{
                    height: '100%',
                    border: `1px solid ${theme.palette.divider}`,
                    backgroundColor: theme.palette.background.default,
                    borderRadius: '0px',
                    borderTop: `4px solid ${theme.palette.primary.main}`,
                    boxShadow: 'none',
                    transition: 'all 0.25s ease',
                    '&:hover': {
                      boxShadow: '0 8px 24px rgba(0,0,0,0.09)',
                    },
                  }}
                >
                  <CardContent sx={{ p: 3.5 }}>
                    <Typography
                      sx={{
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        letterSpacing: '2px',
                        color: theme.palette.primary.main,
                        mb: 1.5,
                      }}
                    >
                      {String(idx + 1).padStart(2, '0')}
                    </Typography>
                    <Typography variant="h6" sx={{ fontWeight: 800, mb: 2, color: theme.palette.text.primary, fontSize: '1.1rem' }}>
                      {item.heading}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{ color: theme.palette.text.secondary, lineHeight: 1.8 }}
                      dangerouslySetInnerHTML={{ __html: item.body }}
                    />
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Commitment Block */}
      <Box
        sx={{
          py: { xs: 8, md: 10 },
          background: `linear-gradient(135deg, ${theme.palette.primary.main} 0%, ${alpha(theme.palette.primary.main, 0.8)} 100%)`,
        }}
      >
        <Container maxWidth="md">
          <Typography
            variant="overline"
            sx={{ color: alpha('#fff', 0.7), fontWeight: 700, letterSpacing: '3px', display: 'block', mb: 2, textAlign: 'center' }}
          >
            Our Commitment
          </Typography>
          <Typography
            variant="h3"
            sx={{
              fontSize: { xs: '1.8rem', md: '2.5rem' },
              fontWeight: 800,
              color: '#fff',
              textAlign: 'center',
              mb: 3,
              lineHeight: 1.3,
            }}
          >
            Institutional Research, Always Free
          </Typography>
          <Typography
            sx={{
              fontSize: '1.1rem',
              color: alpha('#fff', 0.85),
              textAlign: 'center',
              lineHeight: 1.8,
            }}
          >
            We believe independent, evidence-based research drives better investment decisions.
            By removing conflicts of interest and keeping the platform free, we empower every
            investor&#8212;from active traders to long-term investors&#8212;to compete on the
            same footing as the professionals.
          </Typography>
        </Container>
      </Box>

      {/* Platform Metrics */}
      <Box sx={{ py: { xs: 7, md: 8 }, backgroundColor: theme.palette.background.default }}>
        <Container maxWidth="lg">
          <Grid container spacing={3}>
            {[
              { metric: '5,300+', label: 'US Equities Covered', detail: 'Comprehensive coverage across all market caps and sectors' },
              { metric: '10+', label: 'Years of Historical Data', detail: 'Deep history for backtesting and pattern validation' },
              { metric: '6', label: 'Research Dimensions', detail: 'Fundamental, technical, earnings, sentiment, sector, quant' },
              { metric: '24', label: 'Automated Data Loaders', detail: 'Running daily before market open, every trading day' },
            ].map((item, idx) => (
              <Grid item xs={12} sm={6} md={3} key={idx}>
                <Box
                  sx={{
                    textAlign: 'center',
                    py: 4,
                    px: 3,
                    backgroundColor: theme.palette.background.paper,
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: '0px',
                    transition: 'all 0.25s ease',
                    '&:hover': {
                      transform: 'translateY(-3px)',
                      boxShadow: '0 6px 20px rgba(0,0,0,0.08)',
                    },
                  }}
                >
                  <Typography sx={{ fontSize: '2.5rem', fontWeight: 900, color: theme.palette.primary.main, lineHeight: 1, mb: 0.5 }}>
                    {item.metric}
                  </Typography>
                  <Typography sx={{ fontWeight: 700, color: theme.palette.text.primary, mb: 1, fontSize: '1rem' }}>
                    {item.label}
                  </Typography>
                  <Typography sx={{ color: theme.palette.text.secondary, fontSize: '0.85rem', lineHeight: 1.6 }}>
                    {item.detail}
                  </Typography>
                </Box>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      <CommunitySignup />

      <CTASection
        variant="primary"
        title="Ready to Get Started?"
        subtitle="Join investors using Bullseye Financial for evidence-based market analysis&#8212;completely free."
        primaryCTA={{ label: 'Launch Platform', link: '/app/markets' }}
        secondaryCTA={{ label: 'Contact Us', link: '/contact' }}
      />
    </MarketingLayout>
  );
};

export default About;
