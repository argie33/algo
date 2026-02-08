import React from 'react';
import { Container, Box, Typography, Grid, Card, CardContent, useTheme } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import CTASection from '../../components/marketing/CTASection';
import PromoBanner from '../../components/marketing/PromoBanner';
import ImagePlaceholder from '../../components/marketing/ImagePlaceholder';
import { People as PeopleIcon } from '@mui/icons-material';

const OurTeam = () => {
  const theme = useTheme();

  const teamMembers = [];

  return (
    <MarketingLayout>
      <PageHeader
        title="Our Team"
        subtitle="Meet the talented people behind Bullseye Financial"
      />

      <Container maxWidth="lg" sx={{ py: { xs: 6, md: 8 } }}>
        <Typography
          variant="h3"
          sx={{
            fontSize: { xs: '1.8rem', sm: '2.2rem', md: '2.5rem' },
            fontWeight: 800,
            mb: 3,
            textAlign: 'center',
            color: theme.palette.text.primary,
          }}
        >
          Experienced Leaders in AI & Finance
        </Typography>
        <Typography
          variant="body1"
          sx={{
            fontSize: '1.05rem',
            color: theme.palette.text.secondary,
            mb: 6,
            textAlign: 'center',
            maxWidth: '700px',
            mx: 'auto',
          }}
        >
          Our team combines finance expertise and technology innovation to bring institutional-grade market intelligence to every investor. We're dedicated to making sophisticated analysis accessible to all.
        </Typography>
      </Container>

      {/* Team Image Section */}
      <Box sx={{ py: { xs: 4, md: 6 }, backgroundColor: theme.palette.background.default }}>
        <Container maxWidth="lg">
          <ImagePlaceholder
            src="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%271200%27 height=%27400%27%3E%3Crect fill=%27%234a5568%27 width=%271200%27 height=%27400%27/%3E%3Ctext x=%2750%25%27 y=%2750%25%27 font-size=%2732%27 fill=%27white%27 text-anchor=%27middle%27 dominant-baseline=%27middle%27 font-family=%27Arial%27%3EProfessional Market Analysis%3C/text%3E%3C/svg%3E"
            alt="Professional team working on market analysis"
            height={{ xs: '250px', md: '350px' }}
          />
        </Container>
      </Box>

      <PromoBanner
        icon={<PeopleIcon sx={{ color: theme.palette.primary.main }} />}
        title="Interested in Joining Our Team?"
        subtitle="We're always looking for talented people passionate about AI and finance"
        secondaryCTA={{ label: 'Contact Us', href: '/contact' }}
      />

      <Box sx={{ mx: { xs: 2, md: 4 }, mb: 6 }}>
        <CTASection
          variant="primary"
          title="Experience the Bullseye Difference"
          subtitle="Meet the team that's revolutionizing market analysis with AI."
          primaryCTA={{ label: 'Launch Platform', link: '/app/market' }}
          secondaryCTA={{ label: 'Learn More', link: '/about' }}
        />
      </Box>
    </MarketingLayout>
  );
};

export default OurTeam;
