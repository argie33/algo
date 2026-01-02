import React from 'react';
import { Container, Box, Typography, Grid, Card, CardContent, useTheme, alpha } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import IconCardGrid from '../../components/marketing/IconCardGrid';
import CTASection from '../../components/marketing/CTASection';
import PromoBanner from '../../components/marketing/PromoBanner';
import {
  Flag as FlagIcon,
  Lightbulb as LightbulbIcon,
  Groups as GroupsIcon,
  Timeline as TimelineIcon,
  Handshake as HandshakeIcon,
} from '@mui/icons-material';

const Firm = () => {
  const theme = useTheme();

  const about_sections = [
    {
      icon: <FlagIcon />,
      title: 'AI-Powered Analysis',
      description:
        'We use machine learning and artificial intelligence to analyze market data in innovative and creative ways. Our platform harnesses AI to interpret stocks, earnings, sentiment, and economic trends.',
    },
    {
      icon: <LightbulbIcon />,
      title: 'Real-Time Insights',
      description:
        'Our AI systems process market data continuously to provide you with current analysis and signals. Get instant insights on stocks, earnings calendars, market sentiment, and sector performance.',
    },
    {
      icon: <GroupsIcon />,
      title: 'Multiple Analysis Dimensions',
      description:
        'Analyze markets from 8 different angles: stock scoring, earnings tracking, sentiment analysis, technical signals, sector performance, economic indicators, market overview, and hedging strategies.',
    },
    {
      icon: <TimelineIcon />,
      title: 'Data Integration',
      description:
        'We combine real-time market data with AI interpretation to help you understand stocks and markets better. All data is processed and analyzed to uncover patterns and opportunities.',
    },
  ];

  return (
    <MarketingLayout>
      {/* Header */}
      <PageHeader
        title="About Bullseye Financial"
        subtitle="Comprehensive market intelligence for informed investors"
      />

      {/* About Sections */}
      <Container maxWidth="lg" sx={{ py: { xs: 6, md: 8 } }}>
        <IconCardGrid items={about_sections} columns={{ xs: 12, sm: 6, md: 6, lg: 6 }} />
      </Container>

      {/* Mission Statement Section */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: '#f8f9fa' }}>
        <Container maxWidth="lg">
          <Typography
            variant="h3"
            sx={{
              fontSize: { xs: '1.8rem', sm: '2.2rem', md: '2.5rem' },
              fontWeight: 800,
              mb: 3,
              color: theme.palette.text.primary,
            }}
          >
            Our Mission
          </Typography>
          <Typography
            variant="body1"
            sx={{
              fontSize: '1.05rem',
              color: theme.palette.text.secondary,
              mb: 2.5,
              lineHeight: 1.8,
              maxWidth: '800px',
            }}
          >
            To democratize access to institutional-grade market intelligence. We believe sophisticated AI-powered analysis shouldn&apos;t be limited to Wall Street professionals. By combining machine learning, real-time data, and innovative financial research, we empower individual investors and traders to compete with the best.
          </Typography>
        </Container>
      </Box>

      {/* Core Values Section */}
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
          What Drives Us
        </Typography>
        <Grid container spacing={4}>
          {[
            {
              title: 'Innovation First',
              description:
                'We constantly push boundaries with cutting-edge AI and machine learning to uncover insights others miss. Our research team works relentlessly to improve our models and analysis.',
            },
            {
              title: 'Data-Driven Truth',
              description:
                'We follow the data, not narratives. Every indicator, every signal is rigorously tested and validated. We prioritize accuracy over consensus.',
            },
            {
              title: 'Transparency Always',
              description:
                'You understand how our analysis works. We explain our methodology, our sources, and our confidence levels. No black boxes, no hidden secrets.',
            },
            {
              title: 'Excellence Daily',
              description:
                'We measure our success by your success. Our platform is built by experienced traders and investors who understand what you need.',
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
                  <Typography
                    variant="h6"
                    sx={{
                      fontWeight: 700,
                      mb: 2,
                      color: theme.palette.primary.main,
                      fontSize: '1.1rem',
                    }}
                  >
                    {value.title}
                  </Typography>
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

      {/* Leadership Team Section */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: theme.palette.background.paper }}>
        <Container maxWidth="lg">
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
            Our Leadership Team
          </Typography>
          <Grid container spacing={4}>
            {[
              {
                name: 'Sarah Chen',
                role: 'Founder & CEO',
                bio: 'AI strategist with 15+ years in quantitative finance. Previously led machine learning initiatives at Goldman Sachs.',
              },
              {
                name: 'Michael Rodriguez',
                role: 'Chief Research Officer',
                bio: 'Portfolio manager and research veteran with expertise in technical analysis and market microstructure.',
              },
              {
                name: 'Dr. James Park',
                role: 'VP of AI & Engineering',
                bio: 'PhD in Computer Science. Specializes in developing proprietary AI models for financial market analysis.',
              },
              {
                name: 'Emily Thompson',
                role: 'Chief Operations Officer',
                bio: 'Operations leader with extensive experience scaling fintech platforms and managing institutional relationships.',
              },
            ].map((member, idx) => (
              <Grid item xs={12} sm={6} md={6} lg={3} key={idx}>
                <Card
                  sx={{
                    height: '100%',
                    border: `1px solid ${theme.palette.divider}`,
                    backgroundColor: theme.palette.background.default,
                    borderRadius: '0px',
                    transition: 'all 0.3s ease',
                    '&:hover': {
                      boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
                      transform: 'translateY(-2px)',
                    },
                  }}
                >
                  <Box
                    sx={{
                      height: 200,
                      background: `linear-gradient(135deg, ${theme.palette.primary.main}20 0%, ${theme.palette.primary.main}05 100%)`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '3rem',
                      fontWeight: 700,
                      color: theme.palette.primary.main,
                    }}
                  >
                    {member.name.charAt(0)}
                  </Box>
                  <CardContent>
                    <Typography
                      variant="h6"
                      sx={{
                        fontWeight: 700,
                        mb: 0.5,
                        color: theme.palette.text.primary,
                      }}
                    >
                      {member.name}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        fontWeight: 600,
                        color: theme.palette.primary.main,
                        mb: 1.5,
                      }}
                    >
                      {member.role}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        color: theme.palette.text.secondary,
                        lineHeight: 1.6,
                      }}
                    >
                      {member.bio}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Promotional Banner */}
      <PromoBanner
        icon={<HandshakeIcon sx={{ color: theme.palette.primary.main }} />}
        title="Become a Partner"
        subtitle="Join our growing community of professional investors and traders."
        primaryCTA={{ label: 'Get Started', href: '/become-client' }}
        secondaryCTA={{ label: 'Learn More', href: '/services' }}
      />

      {/* CTA */}
      <Box sx={{ mx: { xs: 2, md: 4 }, mb: 6 }}>
        <CTASection
          variant="primary"
          title="Ready to Get Started?"
          subtitle="Join investors who use Bullseye Financial for evidence-based market analysis."
          primaryCTA={{ label: 'Explore Platform', link: '/app/market' }}
          secondaryCTA={{ label: 'View Services', link: '/services' }}
        />
      </Box>
    </MarketingLayout>
  );
};

export default Firm;
