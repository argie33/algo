import React from 'react';
import { Container, Box, Typography, Grid, Card, CardContent, useTheme } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import CTASection from '../../components/marketing/CTASection';
import PromoBanner from '../../components/marketing/PromoBanner';
import {
  Flag as FlagIcon,
  Lightbulb as LightbulbIcon,
  Groups as GroupsIcon,
  TrendingUp as TrendingUpIcon,
  Handshake as HandshakeIcon,
  School as SchoolIcon,
} from '@mui/icons-material';

const Firm = () => {
  const theme = useTheme();

  const expertise = [
    {
      icon: <FlagIcon />,
      title: 'Deep Market Knowledge',
      description:
        '20+ years of combined expertise in financial markets and technology. Our team understands what works in real-world trading, what data matters, and how to apply AI and data science to reveal market insights.',
    },
    {
      icon: <LightbulbIcon />,
      title: 'AI & Quantitative Innovation',
      description:
        'We don\'t just apply AI—we develop proprietary algorithms that solve real problems. Our models analyze 100+ factors across 6+ dimensions to reveal market inefficiencies traditional analysis misses.',
    },
    {
      icon: <GroupsIcon />,
      title: 'Finance & Technology Experts',
      description:
        'A team combining deep expertise in financial markets and software engineering. Over 20 years of collective experience analyzing markets, building trading systems, and developing financial technology solutions.',
    },
    {
      icon: <TrendingUpIcon />,
      title: 'Evidence-Based & Transparent',
      description:
        'We show our work. Every analysis includes the underlying factors, confidence levels, and historical backtests. No black boxes. You understand exactly why our system recommends what it recommends.',
    },
  ];

  const teamMembers = [
    {
      name: 'Team Member 1',
      role: 'Finance & Market Expert',
      bio: 'Financial market specialist with deep experience in equity analysis, market trends, and investment strategy. Combines traditional financial knowledge with innovative analytical approaches.',
      image: 'https://picsum.photos/800/500?random=10',
      expertise: 'Market Analysis, Investment Strategy, Financial Research',
    },
    {
      name: 'Team Member 2',
      role: 'Data & Analytics Lead',
      bio: 'Technology expert specializing in data analysis and system architecture. Focuses on translating market insights into actionable intelligence through advanced analytics and AI.',
      image: 'https://picsum.photos/800/500?random=10',
      expertise: 'Data Science, AI Development, Technical Architecture',
    },
    {
      name: 'Team Member 3',
      role: 'Platform Development',
      bio: 'Software engineer and systems architect dedicated to building intuitive, robust platforms that deliver market intelligence to investors. Expert in financial technology development.',
      image: 'https://picsum.photos/800/500?random=10',
      expertise: 'Software Engineering, Platform Development, Technology',
    },
    {
      name: 'Team Member 4',
      role: 'Operations & Growth',
      bio: 'Business operations specialist focused on scaling the platform and ensuring clients get maximum value from our research and analytics tools.',
      image: 'https://picsum.photos/800/500?random=10',
      expertise: 'Operations, Client Success, Business Strategy',
    },
  ];

  return (
    <MarketingLayout>
      {/* Header */}
      <PageHeader
        title="About Bullseye Financial"
        subtitle="A research firm and advisory platform combining deep market knowledge with cutting-edge AI and big data techniques"
      />

      {/* Who We Are Section */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: theme.palette.background.default }}>
        <Container maxWidth="lg">
          <Typography
            variant="h3"
            sx={{
              fontSize: { xs: '1.8rem', sm: '2.2rem', md: '2.5rem' },
              fontWeight: 800,
              mb: 4,
              textAlign: 'center',
              color: theme.palette.text.primary,
            }}
          >
            Who We Are
          </Typography>
          <Typography
            sx={{
              fontSize: '1.05rem',
              color: theme.palette.text.secondary,
              mb: 3,
              lineHeight: 1.8,
              maxWidth: '900px',
              mx: 'auto',
            }}
          >
            Bullseye Financial is a research firm and advisory platform dedicated to democratizing access to institutional-grade market intelligence. We combine decades of collective Wall Street experience with cutting-edge artificial intelligence and machine learning to deliver research-driven insights that traditional analysis misses.
          </Typography>
          <Typography
            sx={{
              fontSize: '1.05rem',
              color: theme.palette.text.secondary,
              lineHeight: 1.8,
              maxWidth: '900px',
              mx: 'auto',
            }}
          >
            Our mission is simple: empower investors—whether institutions, advisors, or individuals—with the same research-grade analysis and insights traditionally available only to Wall Street professionals. We believe sophisticated financial research shouldn't be limited to those with access to expensive institutional platforms.
          </Typography>
        </Container>
      </Box>

      {/* Our Expertise Section */}
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
            Our Research Expertise
          </Typography>
          <Grid container spacing={4}>
            {expertise.map((item, idx) => (
              <Grid item xs={12} sm={6} key={idx}>
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
                  <CardContent>
                    <Box sx={{ mb: 2, color: theme.palette.primary.main }}>
                      {item.icon}
                    </Box>
                    <Typography
                      variant="h6"
                      sx={{
                        fontWeight: 700,
                        mb: 1.5,
                        color: theme.palette.text.primary,
                      }}
                    >
                      {item.title}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        color: theme.palette.text.secondary,
                        lineHeight: 1.7,
                      }}
                    >
                      {item.description}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Research Approach Section */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: theme.palette.background.default }}>
        <Container maxWidth="lg">
          <Typography
            variant="h3"
            sx={{
              fontSize: { xs: '1.8rem', sm: '2.2rem', md: '2.5rem' },
              fontWeight: 800,
              mb: 2,
              textAlign: 'center',
              color: theme.palette.text.primary,
            }}
          >
            Our Research Philosophy
          </Typography>
          <Typography
            sx={{
              fontSize: '1.05rem',
              color: theme.palette.text.secondary,
              textAlign: 'center',
              mb: 6,
              maxWidth: '800px',
              mx: 'auto',
            }}
          >
            Everything we do is grounded in five core principles that guide our research and advisory approach
          </Typography>

          <Grid container spacing={4}>
            {[
              {
                principle: 'Multi-Dimensional Analysis',
                description: 'We analyze markets across 6+ independent dimensions—fundamentals, technicals, sentiment, macro trends, sector dynamics, and positioning. This comprehensive approach reveals opportunities and risks that single-dimension analysis misses.',
              },
              {
                principle: 'Data-Driven Insights',
                description: 'Every recommendation is grounded in rigorous data analysis. We process 10+ years of historical data and real-time market information through proprietary AI models to identify patterns and trends.',
              },
              {
                principle: 'Continuous Innovation',
                description: 'Financial markets evolve constantly. Our research team and AI models continuously learn from market outcomes, adapting methodologies and improving accuracy as conditions change.',
              },
              {
                principle: 'Transparency & Explanation',
                description: 'We believe clients deserve to understand how our analysis works. We explain our methodology, show our reasoning, and provide confidence levels for every recommendation.',
              },
              {
                principle: 'Customized Solutions',
                description: 'Different investors have different needs. We customize our research offerings based on client type, investment strategy, time horizon, and specific mandates.',
              },
              {
                principle: 'Evidence Over Opinion',
                description: 'We focus on what the data shows, not what the consensus believes. Our research prioritizes empirical evidence, testing methodologies against real-world outcomes.',
              },
            ].map((item, idx) => (
              <Grid item xs={12} md={6} key={idx}>
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
                      {item.principle}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        color: theme.palette.text.secondary,
                        lineHeight: 1.7,
                      }}
                    >
                      {item.description}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Featured: Leadership Spotlight */}
      <Box sx={{ position: 'relative', py: { xs: 4, md: 6 }, overflow: 'hidden', backgroundColor: alpha(theme.palette.primary.main, 0.03) }}>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 0, alignItems: 'stretch' }}>
          {/* Left: Image */}
          <Box
            sx={{
              backgroundImage: 'url(https://picsum.photos/800/500?random=10)',
              backgroundSize: 'cover',
              backgroundPosition: 'center',
              minHeight: { xs: '300px', md: '500px' },
              position: 'relative',
              display: { xs: 'none', md: 'block' },
              '&::after': {
                content: '""',
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                backgroundColor: 'rgba(98, 125, 152, 0.2)',
              },
            }}
          />
          {/* Right: Content */}
          <Box
            sx={{
              backgroundColor: 'white',
              p: { xs: 4, md: 6 },
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
              minHeight: { xs: 'auto', md: '500px' },
            }}
          >
            <Box sx={{ mb: 2 }}>
              <Typography
                sx={{
                  fontSize: '0.85rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '1px',
                  color: theme.palette.primary.main,
                  mb: 1,
                }}
              >
                👥 Expert Leadership
              </Typography>
            </Box>
            <Typography
              variant="h3"
              sx={{
                fontSize: { xs: '2rem', md: '3rem' },
                fontWeight: 900,
                mb: 3,
                color: theme.palette.text.primary,
                lineHeight: 1.2,
              }}
            >
              Built by Market Veterans
            </Typography>
            <Typography
              sx={{
                fontSize: '1.15rem',
                color: theme.palette.text.secondary,
                mb: 4,
                lineHeight: 1.8,
                maxWidth: '500px',
              }}
            >
              Our team combines 20+ years of combined experience in finance and technology. We bring market expertise and technical innovation together to solve real problems investors face every day.
            </Typography>
            <Box sx={{ mb: 4 }}>
              {[
                'Deep expertise in financial markets and analysis',
                'Advanced technology and data science capabilities',
                'Real-world understanding of investor needs',
                'Commitment to bringing institutional-grade insights to all investors',
              ].map((credential, i) => (
                <Box key={i} sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                  <Box
                    sx={{
                      width: '20px',
                      height: '20px',
                      borderRadius: '50%',
                      backgroundColor: theme.palette.primary.main,
                      color: '#fff',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '0.8rem',
                      fontWeight: 'bold',
                      mr: 2,
                      flexShrink: 0,
                    }}
                  >
                    ✓
                  </Box>
                  <Typography sx={{ color: theme.palette.text.secondary, fontSize: '1rem' }}>
                    {credential}
                  </Typography>
                </Box>
              ))}
            </Box>
            <Box
              sx={{
                px: 3,
                py: 1.5,
                backgroundColor: theme.palette.primary.main,
                color: '#fff',
                cursor: 'pointer',
                fontWeight: 600,
                transition: 'all 0.3s',
                display: 'inline-block',
                '&:hover': {
                  boxShadow: '0 8px 20px rgba(98, 125, 152, 0.3)',
                  transform: 'translateY(-2px)',
                },
              }}
            >
              Meet the Full Team
            </Box>
          </Box>
        </Box>
      </Box>

      {/* Leadership Team Section */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: theme.palette.background.paper }}>
        <Container maxWidth="lg">
          <Typography
            variant="h3"
            sx={{
              fontSize: { xs: '1.8rem', sm: '2.2rem', md: '2.5rem' },
              fontWeight: 800,
              mb: 2,
              textAlign: 'center',
              color: theme.palette.text.primary,
            }}
          >
            Our Research Leadership
          </Typography>
          <Typography
            sx={{
              fontSize: '1.05rem',
              color: theme.palette.text.secondary,
              textAlign: 'center',
              mb: 6,
              maxWidth: '800px',
              mx: 'auto',
            }}
          >
            Our team combines deep Wall Street experience with cutting-edge AI and data science expertise
          </Typography>

          <Grid container spacing={4}>
            {teamMembers.map((member, idx) => (
              <Grid item xs={12} md={6} key={idx}>
                <Card
                  sx={{
                    height: '100%',
                    border: `1px solid ${theme.palette.divider}`,
                    backgroundColor: theme.palette.background.default,
                    borderRadius: '0px',
                    overflow: 'hidden',
                    transition: 'all 0.3s ease',
                    '&:hover': {
                      boxShadow: '0 6px 16px rgba(0,0,0,0.1)',
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
                      height: 300,
                      objectFit: 'cover',
                      display: 'block',
                    }}
                    onError={(e) => {
                      e.target.style.display = 'none';
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
                      sx={{
                        fontWeight: 600,
                        color: theme.palette.primary.main,
                        mb: 2,
                        fontSize: '0.95rem',
                      }}
                    >
                      {member.role}
                    </Typography>
                    <Typography
                      sx={{
                        color: theme.palette.text.secondary,
                        lineHeight: 1.6,
                        mb: 2,
                        fontSize: '0.95rem',
                      }}
                    >
                      {member.bio}
                    </Typography>
                    <Typography
                      sx={{
                        fontWeight: 600,
                        color: theme.palette.primary.main,
                        fontSize: '0.85rem',
                        textTransform: 'uppercase',
                        letterSpacing: 0.5,
                      }}
                    >
                      Expertise: {member.expertise}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Core Values Section */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: theme.palette.background.default }}>
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
            What Drives Us
          </Typography>
          <Grid container spacing={4}>
            {[
              {
                title: 'Innovation First',
                description:
                  'We constantly push boundaries with cutting-edge AI and machine learning to uncover insights others miss. Our research team works relentlessly to improve our models and discover new analytical approaches.',
              },
              {
                title: 'Data-Driven Truth',
                description:
                  'We follow the data, not narratives. Every indicator, every signal is rigorously tested and validated. We prioritize accuracy over consensus and evidence over emotion.',
              },
              {
                title: 'Transparency Always',
                description:
                  'You understand how our analysis works. We explain our methodology, our sources, and our confidence levels. No black boxes, no hidden secrets.',
              },
              {
                title: 'Excellence Daily',
                description:
                  'We measure our success by your success. Our platform is built by experienced traders and investors who understand what you need to succeed.',
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
      </Box>

      {/* Why Bullseye Section */}
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
            Why Choose Bullseye Financial
          </Typography>

          <Grid container spacing={3}>
            {[
              'Institutional-grade research previously available only to Wall Street professionals',
              'Multi-dimensional analysis across 6+ independent market perspectives',
              'AI-powered insights trained on 10+ years of market data',
              'Evidence-based approach prioritizing empirical data over consensus',
              'Customized solutions tailored to your investment strategy and needs',
              'Transparent methodology—we explain our reasoning and confidence levels',
              'Real-time analysis and actionable intelligence 24/7',
              'Dedicated support for institutions, advisors, and active investors',
            ].map((item, idx) => (
              <Grid item xs={12} sm={6} md={4} key={idx}>
                <Box
                  sx={{
                    p: 3,
                    backgroundColor: theme.palette.background.default,
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: '0px',
                    transition: 'all 0.3s ease',
                    '&:hover': {
                      borderColor: theme.palette.primary.main,
                      backgroundColor: theme.palette.primary.main + '05',
                    },
                  }}
                >
                  <Box
                    sx={{
                      width: 24,
                      height: 24,
                      borderRadius: '50%',
                      backgroundColor: theme.palette.primary.main,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: '#fff',
                      fontSize: '0.8rem',
                      fontWeight: 'bold',
                      mb: 2,
                    }}
                  >
                    ✓
                  </Box>
                  <Typography
                    sx={{
                      color: theme.palette.text.secondary,
                      fontSize: '0.95rem',
                      lineHeight: 1.6,
                    }}
                  >
                    {item}
                  </Typography>
                </Box>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* By the Numbers Section */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: theme.palette.background.paper }}>
        <Container maxWidth="lg">
          <Typography
            variant="h3"
            sx={{
              fontSize: { xs: '1.8rem', sm: '2.2rem', md: '2.5rem' },
              fontWeight: 800,
              mb: 2,
              textAlign: 'center',
              color: theme.palette.text.primary,
            }}
          >
            Research Firm By the Numbers
          </Typography>
          <Typography
            sx={{
              fontSize: '1.05rem',
              color: theme.palette.text.secondary,
              textAlign: 'center',
              mb: 8,
              maxWidth: '700px',
              mx: 'auto',
            }}
          >
            The depth of our research capabilities and institutional coverage at a glance
          </Typography>
          <Grid container spacing={4}>
            {[
              {
                metric: '5,300+',
                label: 'Stocks Covered',
                description: 'Comprehensive analysis across the US equity market',
                icon: '📈',
              },
              {
                metric: '10+',
                label: 'Years of Data',
                description: 'Deep historical perspective for pattern analysis',
                icon: '📊',
              },
              {
                metric: '6',
                label: 'Research Dimensions',
                description: 'Market, economic, fundamental, technical, sector, sentiment',
                icon: '🔍',
              },
              {
                metric: '24/7',
                label: 'Real-Time Updates',
                description: 'Continuous analysis as markets move and data emerges',
                icon: '⚡',
              },
              {
                metric: '100%',
                label: 'Data-Driven',
                description: 'Evidence-based analysis with rigorous validation',
                icon: '✓',
              },
              {
                metric: 'AI-Powered',
                label: 'Advanced Analytics',
                description: 'Machine learning models identify patterns at scale',
                icon: '🤖',
              },
            ].map((item, idx) => (
              <Grid item xs={12} sm={6} md={4} key={idx}>
                <Box
                  sx={{
                    textAlign: 'center',
                    py: 4,
                    px: 3,
                    backgroundColor: theme.palette.background.default,
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: '0px',
                    transition: 'all 0.3s ease',
                    '&:hover': {
                      transform: 'translateY(-4px)',
                      boxShadow: '0 8px 20px rgba(0,0,0,0.08)',
                    },
                  }}
                >
                  <Box sx={{ fontSize: '3rem', mb: 2 }}>
                    {item.icon}
                  </Box>
                  <Typography
                    variant="h4"
                    sx={{
                      fontWeight: 800,
                      color: theme.palette.primary.main,
                      mb: 0.5,
                      fontSize: '2.2rem',
                    }}
                  >
                    {item.metric}
                  </Typography>
                  <Typography
                    variant="h6"
                    sx={{
                      fontWeight: 700,
                      color: theme.palette.text.primary,
                      mb: 1,
                      fontSize: '1.1rem',
                    }}
                  >
                    {item.label}
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{
                      color: theme.palette.text.secondary,
                      lineHeight: 1.6,
                    }}
                  >
                    {item.description}
                  </Typography>
                </Box>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Promotional Banner */}
      <PromoBanner
        icon={<HandshakeIcon sx={{ color: theme.palette.primary.main }} />}
        title="Partner With a Research-Driven Firm"
        subtitle="Access institutional-grade market intelligence and research-backed advisory solutions."
        primaryCTA={{ label: 'Get Started', href: '/become-client' }}
        secondaryCTA={{ label: 'View Services', href: '/services' }}
      />

      {/* CTA */}
      <Box sx={{ mx: { xs: 2, md: 4 }, mb: 6 }}>
        <CTASection
          variant="primary"
          title="Ready to Partner With Bullseye?"
          subtitle="Access research-driven insights and institutional-grade advisory solutions designed for serious investors."
          primaryCTA={{ label: 'Explore Platform', link: '/app/market' }}
          secondaryCTA={{ label: 'View Team', link: '/our-team' }}
        />
      </Box>
    </MarketingLayout>
  );
};

export default Firm;
