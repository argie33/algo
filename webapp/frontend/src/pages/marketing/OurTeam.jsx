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
      name: 'Erik A.',
      role: 'CEO & Co-Founder',
      bio: 'Visionary leader combining deep expertise in finance and information technology. With 15+ years in finance and software development, Erik leverages AI and cutting-edge machine learning to transform how investors analyze market data. Passionate about democratizing institutional-grade intelligence through innovative technology.',
      image: 'https://images.unsplash.com/photo-1552664730-d307ca884978?w=800&h=500&fit=crop',
    },
    {
      name: 'Sarah Chen',
      role: 'VP Engineering & Technology',
      bio: 'CTO and technical leader driving Bullseye\'s AI-powered analytics engine. With expertise in distributed systems, machine learning, and financial technology, Sarah builds scalable infrastructure that processes and analyzes millions of data points in real-time to deliver actionable market insights.',
      image: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=800&h=500&fit=crop',
    },
    {
      name: 'Michael Torres',
      role: 'VP Research & Analytics',
      bio: 'Quantitative researcher and data science leader specializing in market pattern recognition and predictive modeling. Michael develops proprietary algorithms that identify trading opportunities and market trends, combining academic rigor with practical market experience.',
      image: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=800&h=500&fit=crop',
    },
    {
      name: 'Jessica Liu',
      role: 'VP Product & Customer Success',
      bio: 'Product strategist focused on creating intuitive, powerful tools for serious investors. Jessica bridges the gap between sophisticated financial analysis and user-friendly design, ensuring Bullseye delivers institutional capabilities with consumer-grade simplicity.',
      image: 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=800&h=500&fit=crop',
    },
    {
      name: 'David Rodriguez',
      role: 'Head of Market Research',
      bio: 'Senior market analyst with 12+ years of equity research experience. David leads the fundamental research team, conducting deep dives into market dynamics, sector rotations, and macroeconomic trends to inform Bullseye\'s intelligence platform.',
      image: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=800&h=500&fit=crop',
    },
    {
      name: 'Amanda Foster',
      role: 'Head of Operations & Business Development',
      bio: 'Strategic operations leader focused on scaling Bullseye and expanding market reach. Amanda oversees business development, partnerships, and operational excellence, ensuring the platform meets the needs of individual investors and institutional clients alike.',
      image: 'https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=800&h=500&fit=crop',
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
