import React from 'react';
import { Container, Box, Typography, Grid, Card, CardContent, useTheme } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import CTASection from '../../components/marketing/CTASection';
import PromoBanner from '../../components/marketing/PromoBanner';
import { People as PeopleIcon } from '@mui/icons-material';

const OurTeam = () => {
  const theme = useTheme();

  const teamMembers = [
    {
      name: 'Sarah Chen',
      role: 'Founder & CEO',
      bio: 'AI strategist with 15+ years in quantitative finance. Previously led machine learning initiatives at Goldman Sachs. PhD in Computer Science from MIT.',
      image: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=400&h=400&fit=crop',
    },
    {
      name: 'Michael Rodriguez',
      role: 'Chief Research Officer',
      bio: 'Portfolio manager and research veteran with expertise in technical analysis and market microstructure. 12 years of hedge fund management experience.',
      image: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&h=400&fit=crop',
    },
    {
      name: 'Dr. James Park',
      role: 'VP of AI & Engineering',
      bio: 'PhD in Computer Science. Specializes in developing proprietary AI models for financial market analysis. Published researcher in machine learning applications.',
      image: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400&h=400&fit=crop',
    },
    {
      name: 'Emily Thompson',
      role: 'Chief Operations Officer',
      bio: 'Operations leader with extensive experience scaling fintech platforms and managing institutional relationships. 10+ years in financial services.',
      image: 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400&h=400&fit=crop',
    },
    {
      name: 'David Kumar',
      role: 'Head of Data Science',
      bio: 'Data scientist and statistician with expertise in sentiment analysis and alternative data. Previously worked at Two Sigma and Renaissance Technologies.',
      image: 'https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=400&h=400&fit=crop',
    },
    {
      name: 'Jessica Martinez',
      role: 'VP of Product',
      bio: 'Product strategist focused on user experience and platform development. Formerly at major fintech platforms including Charles Schwab and E*TRADE.',
      image: 'https://images.unsplash.com/photo-1517841905240-74386c8b7136?w=400&h=400&fit=crop',
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
          Our team combines deep expertise in artificial intelligence, quantitative finance, and software engineering to create innovative market analysis solutions.
        </Typography>

        <Grid container spacing={4}>
          {teamMembers.map((member, idx) => (
            <Grid item xs={12} sm={6} md={4} key={idx}>
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
                  component="img"
                  src={member.image}
                  alt={member.name}
                  sx={{
                    width: '100%',
                    height: 280,
                    objectFit: 'cover',
                    display: 'block',
                  }}
                  onError={(e) => {
                    e.target.style.display = 'none';
                    e.target.parentElement.style.background = `linear-gradient(135deg, ${theme.palette.primary.main}20 0%, ${theme.palette.primary.main}05 100%)`;
                  }}
                />
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

      <PromoBanner
        icon={<PeopleIcon sx={{ color: theme.palette.primary.main }} />}
        title="Interested in Joining Our Team?"
        subtitle="We're always looking for talented people passionate about AI and finance"
        primaryCTA={{ label: 'View Careers', href: '#' }}
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
