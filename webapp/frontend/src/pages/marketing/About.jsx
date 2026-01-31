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
                Bullseye Financial is built by finance and technology experts who got tired of watching the same information available to Wall Street get hidden from everyone else. We didn't just build another charting tool or sentiment aggregator. We built a research platform that does what professional investors actually need: connects the dots between fundamentals, technicals, sentiment, earnings, economic trends, and positioning.
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
                Our platform analyzes 5,300+ stocks across 6 research dimensions in real-time. We integrate 10+ years of historical market data with live feeds from earnings, economic indicators, sentiment sources, and technical analysis. Our AI models learn which patterns actually predict future moves. No black boxes. No fluff. Just institutional-grade analysis accessible to every investor.
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
                Today, thousands of professional investors, traders, and advisors use Bullseye to find better opportunities, manage risk more intelligently, and make faster decisions. We're committed to staying focused on what matters: helping you make better investment decisions faster than the crowd.
              </Typography>
            </Grid>

            {/* Right Image */}
            <Grid item xs={12} md={6}>
              <ImagePlaceholder
                src="https://images.unsplash.com/photo-1552664730-d307ca884978?w=800&h=600&fit=crop&auto=format&q=80"
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
                Bullseye Financial was founded by a team of finance and technology experts who saw an opportunity to improve how market research and analysis is delivered. Our founders combined expertise in financial markets and technology development to create a better platform for investor research.
              </Typography>
              <Typography
                variant="body1"
                sx={{
                  fontSize: '1.05rem',
                  color: theme.palette.text.secondary,
                  lineHeight: 1.8,
                }}
              >
                We built Bullseye to provide accessible market research. 10+ years of historical market data. 6 research dimensions. Multiple analytical factors. All processed through AI algorithms. Professional-grade research accessible to different investor types.
              </Typography>
            </Grid>

            {/* Right Image */}
            <Grid item xs={12} md={6}>
              <ImagePlaceholder
                src="https://images.unsplash.com/photo-1552664730-d307ca884978?w=800&h=600&fit=crop&auto=format&q=80"
                alt="Professional team collaborating on market research"
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
        secondaryCTA={{ label: 'View Team', href: '/our-team' }}
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
