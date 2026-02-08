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

  const teamMembers = [
    {
      id: 1,
      name: 'Erik A.',
      role: 'Founder & Chief Investment Officer',
      bio: 'Former quantitative analyst with 15+ years in institutional trading and AI-driven market analysis. Specializes in systematic approach to market rotation and institutional capital flows.',
      expertise: ['Market Analysis', 'AI/ML', 'Portfolio Strategy'],
    },
    {
      id: 2,
      name: 'Amanda',
      role: 'Chief Technology Officer',
      bio: 'Leads technology infrastructure and data platform development. Expert in building real-time data processing systems for institutional-grade market intelligence.',
      expertise: ['Data Engineering', 'ML Systems', 'Real-time Computing'],
    },
    {
      id: 3,
      name: 'Anthony Riga',
      role: 'Senior Market Research Analyst',
      bio: 'Seasoned equity researcher specializing in macro trends, sector rotation analysis, and institutional capital flows. Deep expertise in AI adoption impacts across industries.',
      expertise: ['Market Research', 'Macro Analysis', 'Sector Rotation', 'Institutional Flows'],
    },
  ];

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

      {/* Team Members Grid */}
      <Container maxWidth="lg" sx={{ py: { xs: 4, md: 6 } }}>
        <Grid container spacing={3}>
          {teamMembers.map((member) => (
            <Grid item xs={12} sm={6} md={6} key={member.id}>
              <Card
                sx={{
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  transition: 'transform 0.2s, box-shadow 0.2s',
                  '&:hover': {
                    transform: 'translateY(-4px)',
                    boxShadow: theme.shadows[8],
                  },
                }}
              >
                <CardContent sx={{ flexGrow: 1 }}>
                  <Box sx={{ mb: 2, pb: 2, borderBottom: `1px solid ${theme.palette.divider}` }}>
                    <Typography variant="h6" sx={{ fontWeight: 700, mb: 0.5 }}>
                      {member.name}
                    </Typography>
                    <Typography variant="body2" sx={{ color: theme.palette.primary.main, fontWeight: 600 }}>
                      {member.role}
                    </Typography>
                  </Box>
                  <Typography variant="body2" sx={{ mb: 2, color: theme.palette.text.secondary }}>
                    {member.bio}
                  </Typography>
                  <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                    {member.expertise.map((skill, idx) => (
                      <Typography
                        key={idx}
                        variant="caption"
                        sx={{
                          backgroundColor: theme.palette.primary.light,
                          color: theme.palette.primary.dark,
                          px: 1.5,
                          py: 0.5,
                          borderRadius: '12px',
                          fontSize: '0.75rem',
                          fontWeight: 600,
                        }}
                      >
                        {skill}
                      </Typography>
                    ))}
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Container>

      {/* Team Image Section */}
      <Box sx={{ py: { xs: 4, md: 6 }, backgroundColor: theme.palette.background.default }}>
        <Container maxWidth="lg">
          <ImagePlaceholder
            src="https://picsum.photos/1200/400?random"
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
