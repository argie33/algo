import React from 'react';
import { Container, Box, Typography, useTheme, Grid, alpha } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import CTASection from '../../components/marketing/CTASection';
import PromoBanner from '../../components/marketing/PromoBanner';
import ImagePlaceholder from '../../components/marketing/ImagePlaceholder';
import { Info as InfoIcon } from '@mui/icons-material';

const About = () => {
  const theme = useTheme();

  return (
    <MarketingLayout>
      <PageHeader
        title="About Bullseye Financial"
        subtitle="Our story and commitment to AI-powered market intelligence"
      />

      {/* Hero Section with Image */}
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
                Bullseye Financial was founded by a team frustrated with the gap between what's possible and what exists. Our founders—former hedge fund managers, Goldman Sachs quants, and published ML researchers—knew there had to be a better way.
              </Typography>
              <Typography
                variant="body1"
                sx={{
                  fontSize: '1.05rem',
                  color: theme.palette.text.secondary,
                  lineHeight: 1.8,
                }}
              >
                We built Bullseye to level the playing field. 10+ years of market data. 6+ research dimensions. 100+ analytical factors. All processed through proprietary AI algorithms. Institutional-grade intelligence. Actually accessible.
              </Typography>
            </Grid>

            {/* Right Image */}
            <Grid item xs={12} md={6}>
              <ImagePlaceholder
                src="https://images.unsplash.com/photo-1552664730-d307ca884978?w=700&h=500&fit=crop"
                alt="Bullseye Financial Team"
                height={{ xs: '300px', md: '450px' }}
              />
            </Grid>
          </Grid>
        </Container>
      </Box>

      {/* Who We Are Section */}
      <Container maxWidth="lg" sx={{ py: { xs: 6, md: 8 } }}>
        <Typography
          variant="h3"
          sx={{
            fontSize: { xs: '1.8rem', sm: '2.2rem', md: '2.5rem' },
            fontWeight: 800,
            mb: 4,
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
          Bullseye Financial is a fintech platform dedicated to democratizing access to institutional-grade market intelligence. We combine cutting-edge artificial intelligence with real-time market data to provide investors with the tools they need to make informed decisions.
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
          Today, Bullseye serves thousands of professional investors and traders worldwide, providing them with AI-powered analysis across 6+ research dimensions. We're committed to transparency, accuracy, and innovation in everything we do.
        </Typography>
      </Container>

      <PromoBanner
        icon={<InfoIcon sx={{ color: theme.palette.primary.main }} />}
        title="Learn More About Our Platform"
        subtitle="Discover how AI-powered analysis can transform your investment strategy"
        primaryCTA={{ label: 'Explore Services', href: '/services' }}
        secondaryCTA={{ label: 'View Team', href: '/our-team' }}
      />

      <Box sx={{ mx: { xs: 2, md: 4 }, mb: 6 }}>
        <CTASection
          variant="primary"
          title="Ready to Get Started?"
          subtitle="Join investors using Bullseye Financial for evidence-based market analysis."
          primaryCTA={{ label: 'Launch Platform', link: '/app/market' }}
          secondaryCTA={{ label: 'Become a Client', link: '/become-client' }}
        />
      </Box>
    </MarketingLayout>
  );
};

export default About;
