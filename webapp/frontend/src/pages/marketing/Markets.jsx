import React from 'react';
import { Container, Box, Typography, useTheme, Grid, alpha, Card, CardContent } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import CTASection from '../../components/marketing/CTASection';
import PromoBanner from '../../components/marketing/PromoBanner';
import ImagePlaceholder from '../../components/marketing/ImagePlaceholder';
import { Rocket as RocketIcon, TrendingUp as TrendingUpIcon } from '@mui/icons-material';
import { Business as BusinessIcon, LocalFireDepartment as CommoditiesIcon, Public as PublicIcon } from '@mui/icons-material';

const Markets = () => {
  const theme = useTheme();

  const marketTools = [
    {
      icon: <BusinessIcon fontSize="large" />,
      title: 'Sector Analysis',
      subtitle: 'Track Sector Rotations',
      description: 'Monitor sector performance, relative strength, and rotation signals. Understand which sectors have momentum and which are lagging.',
      link: '/sectors',
    },
    {
      icon: <CommoditiesIcon fontSize="large" />,
      title: 'Commodities',
      subtitle: 'Global Commodity Markets',
      description: 'Real-time analysis of crude oil, natural gas, precious metals, and agricultural commodities with macro context and hedging insights.',
      link: '/commodities',
    },
    {
      icon: <PublicIcon fontSize="large" />,
      title: 'Economic Indicators',
      subtitle: 'Macro Economic Dashboard',
      description: 'Track key economic data, Fed policy, inflation trends, and macro drivers affecting markets and sectors.',
      link: '/economic',
    },
  ];

  return (
    <MarketingLayout>
      {/* Header */}
      <PageHeader
        title="Market Analysis Tools"
        subtitle="Comprehensive market surveillance across sectors, commodities, and macroeconomic indicators"
      />

      {/* Hero Image Section */}
      <Box sx={{ py: { xs: 4, md: 6 }, backgroundColor: alpha(theme.palette.primary.main, 0.02) }}>
        <Container maxWidth="lg">
          <ImagePlaceholder
            src="https://images.unsplash.com/photo-1611432579699-484f7990f311?w=1200&h=500&fit=crop&auto=format&q=80"
            alt="Market analysis and surveillance"
            height={{ xs: '250px', md: '400px' }}
          />
        </Container>
      </Box>

      {/* Market Tools Overview */}
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
            Monitor All Markets
          </Typography>
          <Typography
            sx={{
              fontSize: '1.05rem',
              color: theme.palette.text.secondary,
              textAlign: 'center',
              mb: 6,
              maxWidth: '800px',
              mx: 'auto',
              lineHeight: 1.8,
            }}
          >
            Professional-grade market analysis tools for understanding sector rotations, commodity dynamics, and macroeconomic trends that drive markets.
          </Typography>

          <Grid container spacing={4}>
            {marketTools.map((tool, idx) => (
              <Grid item xs={12} md={4} key={idx}>
                <Card
                  sx={{
                    height: '100%',
                    border: `1px solid ${theme.palette.divider}`,
                    backgroundColor: theme.palette.background.paper,
                    borderRadius: '0px',
                    transition: 'all 0.3s ease',
                    cursor: 'pointer',
                    '&:hover': {
                      boxShadow: '0 12px 30px rgba(0,0,0,0.12)',
                      transform: 'translateY(-6px)',
                      borderColor: theme.palette.primary.main,
                    },
                  }}
                  onClick={() => window.location.href = tool.link}
                >
                  <CardContent sx={{ p: 4 }}>
                    <Box sx={{ color: theme.palette.primary.main, fontSize: '3rem', mb: 2 }}>
                      {tool.icon}
                    </Box>
                    <Typography
                      variant="h6"
                      sx={{
                        fontWeight: 700,
                        mb: 0.5,
                        color: theme.palette.text.primary,
                      }}
                    >
                      {tool.title}
                    </Typography>
                    <Typography
                      sx={{
                        color: theme.palette.primary.main,
                        fontWeight: 600,
                        fontSize: '0.95rem',
                        mb: 2,
                      }}
                    >
                      {tool.subtitle}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        color: theme.palette.text.secondary,
                        lineHeight: 1.6,
                      }}
                    >
                      {tool.description}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Why Monitor Markets */}
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
            Why Professional Market Analysis Matters
          </Typography>

          <Grid container spacing={4}>
            {[
              {
                title: 'Sector Rotation',
                description: 'Capital flows between sectors in predictable patterns. Our analysis helps you position ahead of major rotations.',
              },
              {
                title: 'Commodity Impact',
                description: 'Commodities affect inflation, corporate earnings, and portfolio hedging. Monitor crude, metals, and agriculture in real-time.',
              },
              {
                title: 'Macro Context',
                description: 'Fed policy, economic data, and geopolitical events drive market movements. Stay informed of macro drivers.',
              },
              {
                title: 'Portfolio Hedging',
                description: 'Use commodities and sector analysis to identify hedging opportunities that protect against downside risk.',
              },
              {
                title: 'Relative Strength',
                description: 'Understand which sectors and markets have momentum, which are weakening, and which are ready to break out.',
              },
              {
                title: 'Risk Management',
                description: 'Comprehensive market surveillance helps identify regime changes and market structure risks early.',
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
                      transform: 'translateY(-2px)',
                    },
                  }}
                >
                  <CardContent>
                    <Typography
                      variant="h6"
                      sx={{
                        fontWeight: 700,
                        mb: 1.5,
                        color: theme.palette.primary.main,
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

      {/* Promotional Banner */}
      <PromoBanner
        icon={<RocketIcon sx={{ color: theme.palette.primary.main }} />}
        title="Ready to Access Market Intelligence?"
        subtitle="Explore our comprehensive market analysis tools for sectors, commodities, and macro indicators."
        primaryCTA={{ label: 'Launch Market Tools', href: '/app/market' }}
        secondaryCTA={{ label: 'Learn About Research', href: '/services' }}
      />

      {/* CTA Section */}
      <Box sx={{ mx: { xs: 2, md: 4 }, mb: 6 }}>
        <CTASection
          variant="primary"
          title="Monitor Global Markets Like a Pro"
          subtitle="Get professional-grade market analysis, real-time data, and actionable insights across all asset classes."
          primaryCTA={{ label: 'Explore Tools', link: '/app/market' }}
          secondaryCTA={{ label: 'View Pricing', link: '/contact' }}
        />
      </Box>
    </MarketingLayout>
  );
};

export default Markets;
