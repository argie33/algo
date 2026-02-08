import React from 'react';
import { Container, Box, Typography, useTheme, Grid, alpha } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import CTASection from '../../components/marketing/CTASection';
import PromoBanner from '../../components/marketing/PromoBanner';
import ImagePlaceholder from '../../components/marketing/ImagePlaceholder';
import CommunitySignup from '../../components/marketing/CommunitySignup';
import { Info as InfoIcon } from '@mui/icons-material';

const About = () => {
  const theme = useTheme();

  return (
    <MarketingLayout>
      <PageHeader
        title="About Bullseye Financial"
        subtitle="Our story and commitment to AI-powered market intelligence"
      />

      {/* Who We Are Section */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: alpha(theme.palette.primary.main, 0.02) }}>
        <Container maxWidth="lg">
          <Grid container spacing={6} alignItems="center">
            {/* Left Content */}
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
                Who We Are
              </Typography>
              <Typography
                variant="body1"
                sx={{
                  fontSize: '1.05rem',
                  color: theme.palette.text.secondary,
                  mb: 3,
                  lineHeight: 1.8,
                }}
              >
                Bullseye Financial represents a fundamental advancement in how institutional-quality investment research is delivered. Our platform integrates comprehensive equity analysis, quantitative modeling, and real-time market intelligence into a single, coherent research framework. We serve investment professionals who require institutional-grade analysis to drive capital allocation decisions.
              </Typography>
              <Typography
                variant="body1"
                sx={{
                  fontSize: '1.05rem',
                  color: theme.palette.text.secondary,
                  mb: 3,
                  lineHeight: 1.8,
                }}
              >
                Our systematic approach covers 5,300+ equities across six integrated research dimensions: fundamental valuation, earnings dynamics, technical market structure, sentiment positioning, sector rotation, and quantitative factors. By combining over a decade of historical market data with real-time feeds and proprietary analytical models, we deliver the comprehensive, evidence-based research framework that professional investors require.
              </Typography>
              <Typography
                variant="body1"
                sx={{
                  fontSize: '1.05rem',
                  color: theme.palette.text.secondary,
                  mb: 3,
                  lineHeight: 1.8,
                }}
              >
                Investment professionals and institutional advisors rely on Bullseye to identify superior opportunities, manage portfolio construction more precisely, and execute decisions with institutional-caliber analysis. Our commitment remains focused on delivering the analytical rigor and comprehensive coverage that define professional investment research.
              </Typography>
            </Grid>

            {/* Right Image */}
            <Grid item xs={12} md={6}>
              <ImagePlaceholder
                src="https://picsum.photos/1200/400?random"
                alt="Professional team collaborating on market research"
                height={{ xs: '300px', md: '450px' }}
              />
            </Grid>
          </Grid>
        </Container>
      </Box>

      {/* Our Journey Section */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: alpha(theme.palette.primary.main, 0.02) }}>
        <Container maxWidth="lg">
          <Grid container spacing={6} alignItems="center">
            {/* Left Content */}
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
                Our Journey
              </Typography>
              <Typography
                variant="body1"
                sx={{
                  fontSize: '1.05rem',
                  color: theme.palette.text.secondary,
                  mb: 3,
                  lineHeight: 1.8,
                }}
              >
                Bullseye Financial was established by investment professionals and technology experts who recognized a critical gap in how market research reaches the investment community. Our founders combined deep capital markets expertise with advanced technology capabilities to build a research platform meeting institutional standards.
              </Typography>
              <Typography
                variant="body1"
                sx={{
                  fontSize: '1.05rem',
                  color: theme.palette.text.secondary,
                  lineHeight: 1.8,
                }}
              >
                Our platform represents years of research infrastructure development, integrating over a decade of market data, advanced analytical models, and systematic research methodology. The result is comprehensive equity coverage underpinned by rigorous quantitative frameworks and institutional-grade research practices—delivering the analysis that professional investors require for disciplined capital allocation.
              </Typography>
            </Grid>

            {/* Right Image */}
            <Grid item xs={12} md={6}>
              <ImagePlaceholder
                src="https://picsum.photos/1200/400?random"
                alt="Analytics dashboard with market data and performance metrics"
                height={{ xs: '300px', md: '450px' }}
              />
            </Grid>
          </Grid>
        </Container>
      </Box>

      <PromoBanner
        icon={<InfoIcon sx={{ color: theme.palette.primary.main }} />}
        title="Learn More About Our Platform"
        subtitle="Discover how AI-powered analysis can transform your investment strategy"
        primaryCTA={{ label: 'Explore Services', href: '/services' }}
      />

      {/* Community Signup Section */}
      <CommunitySignup />

      <Box sx={{ mx: { xs: 2, md: 4 }, mb: 6 }}>
        <CTASection
          variant="primary"
          title="Ready to Get Started?"
          subtitle="Join investors using Bullseye Financial for evidence-based market analysis."
          primaryCTA={{ label: 'Launch Platform', link: '/app/market' }}
          secondaryCTA={{ label: 'Become a Client', link: '/contact' }}
        />
      </Box>
    </MarketingLayout>
  );
};

export default About;
