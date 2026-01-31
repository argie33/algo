import React from 'react';
import { Container, Box, Typography, Grid, Card, CardContent, useTheme, alpha } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import CTASection from '../../components/marketing/CTASection';
import PromoBanner from '../../components/marketing/PromoBanner';
import ImagePlaceholder from '../../components/marketing/ImagePlaceholder';
import { CheckCircle as CheckCircleIcon } from '@mui/icons-material';

const MissionValues = () => {
  const theme = useTheme();

  return (
    <MarketingLayout>
      <PageHeader
        title="Our Mission & Values"
        subtitle="What drives us to innovate and serve"
      />

      {/* Mission Section with Image */}
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
                  mb: 4,
                  color: theme.palette.text.primary,
                }}
              >
                Our Mission
              </Typography>
              <Typography
                variant="body1"
                sx={{
                  fontSize: '1.1rem',
                  color: theme.palette.text.secondary,
                  lineHeight: 1.8,
                  mb: 2,
                }}
              >
                The best edge in investing isn't secrets. It's better analysis. Wall Street spends millions on research you can't access. We built Bullseye so you don't have to. Same institutional data. Same AI sophistication. Same competitive advantage - without the premium pricing or gatekeeping.
              </Typography>
              <Typography
                variant="body1"
                sx={{
                  fontSize: '1.1rem',
                  color: theme.palette.text.secondary,
                  lineHeight: 1.8,
                }}
              >
                The game isn't rigged in your favor, but it doesn't have to be rigged against you. We combine 10+ years of market data, advanced machine learning, and transparent methodology to show you what institutional investors see. Compete on skill. On execution. On discipline. Not on access.
              </Typography>
            </Grid>

            {/* Right Image */}
            <Grid item xs={12} md={6}>
              <ImagePlaceholder
                src="https://images.unsplash.com/photo-1552664730-d307ca884978?w=700&h=500&fit=crop"
                alt="Our Mission and Values"
                height={{ xs: '300px', md: '450px' }}
              />
            </Grid>
          </Grid>
        </Container>
      </Box>

      {/* Core Values */}
      <Container maxWidth="lg" sx={{ py: { xs: 6, md: 8 } }}>
        <Typography
          variant="h3"
          sx={{
            fontSize: { xs: '1.8rem', sm: '2.2rem', md: '2.5rem' },
            fontWeight: 800,
            mb: 6,
            textAlign: 'center',
            color: theme.palette.text.primary,
          }}
        >
          Our Core Values
        </Typography>
        <Grid container spacing={4}>
          {[
            {
              title: 'Innovation First',
              description:
                'We constantly push boundaries with cutting-edge AI and machine learning. Our research team works tirelessly to improve our models and discover new insights.',
            },
            {
              title: 'Data-Driven Truth',
              description:
                'We follow the data, not narratives. Every indicator is rigorously tested. We prioritize accuracy over consensus and evidence over emotion.',
            },
            {
              title: 'Transparency Always',
              description:
                'Our users understand how our analysis works. We explain our methodology, data sources, and confidence levels. No black boxes, no hidden secrets.',
            },
            {
              title: 'Excellence Daily',
              description:
                'We measure success by our users\' success. Our platform is built by experienced traders and investors who understand what you need.',
            },
            {
              title: 'Accessibility & Inclusion',
              description:
                'We believe brilliant financial tools should be accessible to everyone. We work to lower barriers and empower diverse investors.',
            },
            {
              title: 'Continuous Learning',
              description:
                'Markets evolve, and so do we. Our AI models learn continuously, improving from every trade outcome and market condition.',
            },
          ].map((value, idx) => (
            <Grid item xs={12} sm={6} key={idx}>
              <Card
                sx={{
                  height: '100%',
                  border: `1px solid ${theme.palette.divider}`,
                  backgroundColor: theme.palette.background.paper,
                  borderRadius: '0px',
                  transition: 'all 0.3s ease',
                  '&:hover': {
                    boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
                  },
                }}
              >
                <CardContent>
                  <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
                    <CheckCircleIcon
                      sx={{
                        color: theme.palette.primary.main,
                        fontSize: '1.5rem',
                        flexShrink: 0,
                      }}
                    />
                    <Typography
                      variant="h6"
                      sx={{
                        fontWeight: 700,
                        color: theme.palette.text.primary,
                      }}
                    >
                      {value.title}
                    </Typography>
                  </Box>
                  <Typography
                    variant="body2"
                    sx={{
                      color: theme.palette.text.secondary,
                      lineHeight: 1.7,
                    }}
                  >
                    {value.description}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Container>

      <PromoBanner
        icon={<CheckCircleIcon sx={{ color: theme.palette.primary.main }} />}
        title="Live Our Values Every Day"
        subtitle="Experience the Bullseye difference through our commitment to innovation and integrity"
        primaryCTA={{ label: 'Try Platform', href: '/app/market' }}
        secondaryCTA={{ label: 'Learn More', href: '/services' }}
      />

      <Box sx={{ mx: { xs: 2, md: 4 }, mb: 6 }}>
        <CTASection
          variant="primary"
          title="Join Our Mission"
          subtitle="Be part of a team revolutionizing how investors access market intelligence."
          primaryCTA={{ label: 'Become a Client', link: '/contact' }}
          secondaryCTA={{ label: 'Contact Us', link: '/contact' }}
        />
      </Box>
    </MarketingLayout>
  );
};

export default MissionValues;
