import React from 'react';
import { Container, Box, Typography, Grid, Card, CardContent, useTheme, alpha } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import CTASection from '../../components/marketing/CTASection';
import ImagePlaceholder from '../../components/marketing/ImagePlaceholder';
import { CheckCircle as CheckCircleIcon } from '@mui/icons-material';

const MissionValues = () => {
  const theme = useTheme();

  const coreValues = [
    {
      title: 'Quantitative Rigor',
      description:
        'Every analytical model is backtested against 10+ years of historical market data and validated for statistical significance. We document our methodology, track out-of-sample performance, and refine models when evidence demands it.',
    },
    {
      title: 'Integrated Analysis',
      description:
        'Superior research requires multiple analytical perspectives working together. Our six-dimension framework integrates fundamental valuation, earnings dynamics, technical structure, sentiment indicators, sector rotation, and quantitative modeling into a unified signal.',
    },
    {
      title: 'Research Independence',
      description:
        'Bullseye maintains complete research independence. No investment banking relationships. No underwriting business. No pressure to maintain ratings. Our analysis reflects only the data and our analytical views&#8212;nothing else.',
    },
    {
      title: 'Radical Transparency',
      description:
        'We document data sources, explain model assumptions, and show exactly what factors drive our scores and signals. You understand why a stock passes or fails every stage of the process. No black boxes.',
    },
    {
      title: 'Comprehensive Coverage',
      description:
        'Full-coverage research across 5,300+ US equities spanning all market capitalizations and sectors. Large-cap and micro-cap opportunities receive the same rigorous analytical attention&#8212;systematic coverage, not selective coverage.',
    },
    {
      title: 'Continuous Improvement',
      description:
        'Market regimes evolve, and our models adapt accordingly. We continuously monitor performance, update factors, and refine our research frameworks to maintain analytical edge as conditions change.',
    },
  ];

  const mission = [
    'Superior investment outcomes require superior research',
    'Independent research removes the conflicts that distort Wall Street analysis',
    'Institutional-grade tools should be accessible to every serious investor',
    'Systematic, evidence-based process beats discretionary guesswork over time',
    'Transparency in methodology builds justified confidence in research',
  ];

  return (
    <MarketingLayout>
      <PageHeader
        title="Mission & Values"
        subtitle="What drives our research, how we think about markets, and the principles behind every decision we make"
      />

      {/* Mission Section */}
      <Box sx={{ py: { xs: 8, md: 10 }, backgroundColor: theme.palette.background.default }}>
        <Container maxWidth="lg">
          <Grid container spacing={7} alignItems="center">
            <Grid item xs={12} md={6}>
              <Typography
                variant="overline"
                sx={{ color: theme.palette.primary.main, fontWeight: 700, letterSpacing: '3px', display: 'block', mb: 1.5 }}
              >
                Our Mission
              </Typography>
              <Typography
                variant="h3"
                sx={{
                  fontSize: { xs: '2rem', sm: '2.5rem', md: '3rem' },
                  fontWeight: 800,
                  mb: 3,
                  color: theme.palette.text.primary,
                  letterSpacing: '-0.5px',
                  lineHeight: 1.2,
                }}
              >
                Evidence Over Opinion. Discipline Over Emotion.
              </Typography>
              <Typography
                sx={{ fontSize: '1.1rem', color: theme.palette.text.secondary, lineHeight: 1.8, mb: 3 }}
              >
                Superior investment outcomes require superior research. Bullseye Financial
                delivers institutional-grade equity analysis combining rigorous fundamental
                analysis, quantitative modeling, and technical research into a comprehensive
                platform accessible to every serious investor.
              </Typography>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                {mission.map((item, i) => (
                  <Box key={i} sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5 }}>
                    <CheckCircleIcon sx={{ color: theme.palette.primary.main, fontSize: '1.15rem', mt: 0.3, flexShrink: 0 }} />
                    <Typography sx={{ color: theme.palette.text.secondary, fontSize: '0.97rem', lineHeight: 1.6 }}>
                      {item}
                    </Typography>
                  </Box>
                ))}
              </Box>
            </Grid>
            <Grid item xs={12} md={6}>
              <ImagePlaceholder
                src="https://images.unsplash.com/photo-1504868584819-f8e8b4b6d7e3?w=900&h=650&fit=crop&auto=format&q=80"
                alt="Financial research and data analysis"
                height={{ xs: '280px', md: '420px' }}
              />
            </Grid>
          </Grid>
        </Container>
      </Box>

      {/* Mission Statement Block */}
      <Box
        sx={{
          py: { xs: 8, md: 10 },
          background: `linear-gradient(135deg, ${theme.palette.primary.main} 0%, ${alpha(theme.palette.primary.main, 0.75)} 100%)`,
        }}
      >
        <Container maxWidth="md">
          <Typography
            variant="h3"
            sx={{
              fontSize: { xs: '1.8rem', md: '2.5rem' },
              fontWeight: 800,
              color: '#fff',
              textAlign: 'center',
              mb: 3,
              lineHeight: 1.3,
            }}
          >
            &#8220;Independent research, transparent methodology, and the conviction to follow
            the data wherever it leads.&#8221;
          </Typography>
          <Typography sx={{ textAlign: 'center', color: alpha('#fff', 0.75), fontSize: '1rem' }}>
            &mdash; Bullseye Financial Research Principles
          </Typography>
        </Container>
      </Box>

      {/* Core Values */}
      <Box sx={{ py: { xs: 8, md: 10 }, backgroundColor: theme.palette.background.default }}>
        <Container maxWidth="lg">
          <Box sx={{ textAlign: 'center', mb: 7 }}>
            <Typography
              variant="overline"
              sx={{ color: theme.palette.primary.main, fontWeight: 700, letterSpacing: '3px', display: 'block', mb: 1.5 }}
            >
              Core Values
            </Typography>
            <Typography
              variant="h3"
              sx={{
                fontSize: { xs: '1.9rem', sm: '2.3rem', md: '2.8rem' },
                fontWeight: 800,
                mb: 2,
                color: theme.palette.text.primary,
                letterSpacing: '-0.5px',
              }}
            >
              What We Believe In
            </Typography>
            <Typography sx={{ fontSize: '1.05rem', color: theme.palette.text.secondary, maxWidth: '600px', mx: 'auto', lineHeight: 1.8 }}>
              Six principles that guide every research decision, every model we build, and every signal we publish
            </Typography>
          </Box>

          <Grid container spacing={3}>
            {coreValues.map((value, idx) => (
              <Grid item xs={12} sm={6} key={idx}>
                <Card
                  sx={{
                    height: '100%',
                    border: `1px solid ${theme.palette.divider}`,
                    backgroundColor: theme.palette.background.paper,
                    borderRadius: '0px',
                    boxShadow: 'none',
                    transition: 'all 0.25s ease',
                    '&:hover': {
                      boxShadow: '0 4px 16px rgba(0,0,0,0.07)',
                      borderColor: theme.palette.primary.main,
                    },
                  }}
                >
                  <CardContent sx={{ p: 3.5 }}>
                    <Box sx={{ display: 'flex', gap: 1.5, mb: 2, alignItems: 'flex-start' }}>
                      <CheckCircleIcon sx={{ color: theme.palette.primary.main, fontSize: '1.3rem', mt: 0.2, flexShrink: 0 }} />
                      <Typography variant="h6" sx={{ fontWeight: 700, color: theme.palette.text.primary, fontSize: '1.05rem', lineHeight: 1.3 }}>
                        {value.title}
                      </Typography>
                    </Box>
                    <Typography
                      variant="body2"
                      sx={{ color: theme.palette.text.secondary, lineHeight: 1.7, pl: 3.5 }}
                      dangerouslySetInnerHTML={{ __html: value.description }}
                    />
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      <CTASection
        variant="primary"
        title="Partner with Bullseye Financial"
        subtitle="Access professional-grade equity research built on these principles&#8212;systematic, transparent, and free."
        primaryCTA={{ label: 'Launch Platform', link: '/app/markets' }}
        secondaryCTA={{ label: 'Contact Us', link: '/contact' }}
      />
    </MarketingLayout>
  );
};

export default MissionValues;
