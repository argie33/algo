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
      title: 'Independent Research',
      description:
        'We operate without investment banking relationships or sell-side conflicts. Our research is driven purely by analysis and data, allowing us to publish unbiased views on companies and markets.',
    },
    {
      icon: <LightbulbIcon />,
      title: 'Quantitative & Fundamental Analysis',
      description:
        'Our research combines quantitative factor models with fundamental analysis. We evaluate stocks using multi-factor scoring across value, quality, momentum, and technical metrics validated through historical backtesting.',
    },
    {
      icon: <GroupsIcon />,
      title: 'Comprehensive Market Coverage',
      description:
        'Research coverage across 5,300+ US equities with 10+ years of historical data. We publish analysis on earnings, sector trends, economic indicators, and market technicals to provide complete investment intelligence.',
    },
    {
      icon: <TrendingUpIcon />,
      title: 'Evidence-Based Methodology',
      description:
        'All research models are backtested against historical data and validated for statistical significance. We explain our methodology transparently and show the factors driving our analysis.',
    },
  ];

  const teamMembers = [];

  return (
    <MarketingLayout>
      {/* Header */}
      <PageHeader
        title="About Bullseye Financial"
        subtitle="Independent equity research firm delivering quantitative analysis, fundamental insights, and technical research to institutional and individual investors"
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
            Bullseye Financial is an independent research firm providing comprehensive equity analysis to institutional investors, registered investment advisors, and active traders. We publish research combining quantitative models, fundamental analysis, and technical insights across 5,300+ US equities.
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
            Our research covers earnings analysis, sector rotation, economic trends, and multi-factor stock scoring. We maintain research independence without investment banking conflicts, allowing us to publish unbiased analysis focused solely on investment merit.
          </Typography>
        </Container>
      </Box>

      {/* Mission Statement Section */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: theme.palette.background.paper }}>
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
            Our Mission
          </Typography>
          <Typography
            sx={{
              fontSize: '1.1rem',
              color: theme.palette.text.secondary,
              mb: 3,
              lineHeight: 1.8,
              maxWidth: '900px',
              mx: 'auto',
              textAlign: 'center',
            }}
          >
            To democratize institutional-grade equity research by combining rigorous quantitative analysis, fundamental insights, and technical expertise into a comprehensive research platform accessible to professional and individual investors.
          </Typography>
          <Typography
            sx={{
              fontSize: '1rem',
              color: theme.palette.text.secondary,
              lineHeight: 1.8,
              maxWidth: '900px',
              mx: 'auto',
              textAlign: 'center',
              fontStyle: 'italic',
            }}
          >
            We believe independent research drives better investment decisions. By removing conflicts of interest and publishing transparent, evidence-based analysis across 5,300+ equities, we empower investors to make informed decisions based on data, not Wall Street relationships.
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
                principle: 'Quantitative Rigor',
                description: 'All factor models are backtested against 10+ years of historical data. We validate statistical significance and measure out-of-sample performance before deploying any research model in production.',
              },
              {
                principle: 'Fundamental Analysis',
                description: 'We evaluate companies using traditional fundamental metrics including valuation, profitability, financial strength, and earnings quality. Fundamental analysis remains the foundation of long-term investment decisions.',
              },
              {
                principle: 'Research Independence',
                description: 'Bullseye maintains complete research independence. We have no investment banking relationships, no underwriting business, and no conflicts that compromise our analytical objectivity.',
              },
              {
                principle: 'Transparent Methodology',
                description: 'We explain our research methodology and show the factors driving our analysis. Clients understand what metrics we evaluate and why certain stocks score positively or negatively.',
              },
              {
                principle: 'Comprehensive Coverage',
                description: 'Our research universe covers 5,300+ US equities across all market capitalizations and sectors. We provide the breadth needed for portfolio construction and relative value analysis.',
              },
              {
                principle: 'Continuous Validation',
                description: 'Research models are continuously monitored and validated. We track performance, refine models based on changing market conditions, and adapt our approach as evidence dictates.',
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
              backgroundImage: 'none',
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
                title: 'Research Integrity',
                description:
                  'Unbiased, fact-based analysis free from conflicts of interest. No investment banking relationships. No pressure to maintain ratings. Our research reflects only the data and our analytical views.',
              },
              {
                title: 'Institutional Quality',
                description:
                  'Professional-grade research comparable to Wall Street firms. Rigorous factor analysis, multi-dimensional modeling, and institutional-caliber coverage across 5,300+ equities.',
              },
              {
                title: 'Evidence-Based Validation',
                description:
                  'Every model backtested against 10+ years of data. Every signal validated for statistical significance. Real performance tracking ensures our research delivers measurable results.',
              },
              {
                title: 'Market Excellence',
                description:
                  'Deep expertise in equity research, portfolio strategy, and market dynamics. Continuous innovation in analytical methods and incorporation of AI-powered insights for competitive advantage.',
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
              'Independent research without investment banking conflicts',
              'Multi-factor quantitative models validated through rigorous backtesting',
              'Comprehensive coverage of 5,300+ US equities with 10+ years of data',
              'Evidence-based methodology prioritizing data over market narratives',
              'Research platform serving institutions, RIAs, and active traders',
              'Transparent methodology with clear factor explanations',
              'Analysis updated during market hours with historical context',
              'Professional research platform designed for serious investors',
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
                description: 'Comprehensive US equity research coverage',
              },
              {
                metric: '10+',
                label: 'Years of Data',
                description: 'Historical data for backtesting and validation',
              },
              {
                metric: 'Multi-Factor',
                label: 'Research Models',
                description: 'Quantitative, fundamental, and technical analysis',
              },
              {
                metric: 'Daily',
                label: 'Research Updates',
                description: 'Analysis refreshed during market hours',
              },
              {
                metric: 'Independent',
                label: 'Research Firm',
                description: 'No investment banking conflicts of interest',
              },
              {
                metric: 'Evidence-Based',
                label: 'Methodology',
                description: 'Backtested models with statistical validation',
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
                  <Typography
                    variant="h4"
                    sx={{
                      fontWeight: 800,
                      color: theme.palette.primary.main,
                      mb: 0.5,
                      fontSize: '2.2rem',
                      mt: 2,
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
        primaryCTA={{ label: 'Get Started', href: '/contact' }}
        
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
