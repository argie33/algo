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
                Superior investment outcomes require superior research. Bullseye Financial delivers institutional-grade equity research combining rigorous fundamental analysis, quantitative modeling, and real-time market intelligence. We serve institutional investors, asset managers, and professional advisors with the same analytical rigor and comprehensive coverage that define the research standards of leading investment firms.
              </Typography>
              <Typography
                variant="body1"
                sx={{
                  fontSize: '1.1rem',
                  color: theme.palette.text.secondary,
                  lineHeight: 1.8,
                }}
              >
                Our platform analyzes 5,300+ equities across six integrated research dimensions—valuation, earnings fundamentals, technical analysis, market sentiment, sector dynamics, and quantitative factors. By integrating over a decade of historical market data with real-time feeds from market data providers, we deliver the systematic, evidence-based research framework that professional investors require for informed capital allocation decisions.
              </Typography>
            </Grid>

            {/* Right Image */}
            <Grid item xs={12} md={6}>
              <ImagePlaceholder
                src="https://images.unsplash.com/photo-1552664730-d307ca884978?w=1200&h=400&fit=crop&auto=format&q=80"
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
              title: 'Rigorous Methodology',
              description:
                'Every analytical model undergoes systematic validation against historical market data and real-world outcomes. We maintain institutional-grade standards for research quality, with documented methodologies and peer review processes that ensure accuracy and reproducibility.',
            },
            {
              title: 'Integrated Analysis',
              description:
                'Superior research requires multiple analytical perspectives. Our six-dimensional framework integrates fundamental research, valuation metrics, technical analysis, sentiment indicators, and quantitative modeling into a unified analytical framework for comprehensive investment insights.',
            },
            {
              title: 'Institutional Transparency',
              description:
                'Professional investors require transparency in research methodology and analytical confidence. We document data sources, explain model assumptions, disclose analytical limitations, and provide detailed confidence intervals for all published research.',
            },
            {
              title: 'Research Excellence',
              description:
                'Our research standards reflect the institutional investment practices of leading global asset managers. We measure success by our clients\' investment outcomes and maintain the analytical discipline required for professional capital allocation.',
            },
            {
              title: 'Comprehensive Coverage',
              description:
                'Full-coverage equities research across all market segments and sectors. Our systematic approach ensures that both large-cap and micro-cap opportunities receive the same rigorous analytical attention, enabling truly unbiased security selection.',
            },
            {
              title: 'Continuous Model Development',
              description:
                'Market regimes evolve, and our analytical models adapt accordingly. We continuously refine our factors, update our algorithms, and enhance our research frameworks to maintain analytical edge in dynamic market environments.',
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
        title="Institutional-Grade Research Standards"
        subtitle="Experience rigorous, comprehensive research methodology designed for professional investors"
        primaryCTA={{ label: 'Explore Platform', href: '/app/market' }}
        secondaryCTA={{ label: 'View Services', href: '/services' }}
      />

      <Box sx={{ mx: { xs: 2, md: 4 }, mb: 6 }}>
        <CTASection
          variant="primary"
          title="Partner with Bullseye Financial"
          subtitle="Access professional-grade equity research and comprehensive market analysis."
          primaryCTA={{ label: 'Schedule Consultation', link: '/contact' }}
          secondaryCTA={{ label: 'Learn About Access', link: '/services' }}
        />
      </Box>
    </MarketingLayout>
  );
};

export default MissionValues;
