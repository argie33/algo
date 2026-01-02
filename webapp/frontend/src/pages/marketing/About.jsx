import React from 'react';
import { Container, Box, Typography, useTheme } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import CTASection from '../../components/marketing/CTASection';
import PromoBanner from '../../components/marketing/PromoBanner';
import { Info as InfoIcon } from '@mui/icons-material';

const About = () => {
  const theme = useTheme();

  return (
    <MarketingLayout>
      <PageHeader
        title="About Bullseye Financial"
        subtitle="Our story and commitment to AI-powered market intelligence"
      />

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
          Founded by experienced traders and AI researchers, our platform represents years of research and development in quantitative finance and machine learning. We're committed to transparency, accuracy, and innovation in everything we do.
        </Typography>
        <Typography
          variant="body1"
          sx={{
            fontSize: '1.05rem',
            color: theme.palette.text.secondary,
            lineHeight: 1.8,
          }}
        >
          Today, Bullseye serves thousands of professional investors and traders worldwide, providing them with AI-powered analysis across 8 different market dimensions.
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
