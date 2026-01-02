import React, { useState } from 'react';
import { Container, Box, Typography, Grid, Card, CardContent, TextField, Button, Select, MenuItem, FormControl, InputLabel, useTheme, alpha } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import CTAButtonGroup from '../../components/marketing/CTAButtonGroup';
import { Check as CheckIcon } from '@mui/icons-material';

const BecomeClient = () => {
  const theme = useTheme();
  const [formData, setFormData] = useState({
    name: '',
    company: '',
    clientType: '',
    phone: '',
    email: '',
    aum: '',
    subscriptionType: '',
    message: '',
  });

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    // In a real app, this would send to backend
    console.log('Form submitted:', formData);
    alert('Thank you for your interest! Our team will contact you shortly.');
    setFormData({
      name: '',
      company: '',
      clientType: '',
      phone: '',
      email: '',
      aum: '',
      subscriptionType: '',
      message: '',
    });
  };

  const whyChoosePoints = [
    {
      title: 'AI-Powered Analysis',
      description: 'Leverage cutting-edge artificial intelligence and machine learning for market insights that traditional analysis misses.',
    },
    {
      title: 'Multi-Dimensional Research',
      description: 'Access analysis across 8 different dimensions: stocks, earnings, sentiment, technicals, sectors, economics, market overview, and hedging strategies.',
    },
    {
      title: 'Real-Time Intelligence',
      description: 'Get instant updates and signals powered by live market data feeds. Never miss an important market opportunity.',
    },
  ];

  const serviceOfferings = [
    {
      title: 'Stock Analysis & Scoring',
      description: 'AI-powered composite scores analyzing stocks across multiple dimensions with institutional-grade accuracy.',
    },
    {
      title: 'Earnings Intelligence',
      description: 'Real-time earnings calendar tracking, estimate revisions, and surprise analysis for informed decision-making.',
    },
    {
      title: 'Market Research & Reports',
      description: 'In-depth market analysis, sector research, and economic trend reports tailored to your investment strategy.',
    },
    {
      title: 'Custom Solutions',
      description: 'Tailored analysis, dedicated reports, and bespoke research solutions designed for your specific needs.',
    },
  ];

  const processSteps = [
    {
      step: '1',
      title: 'Schedule Consultation',
      description: 'Meet with our team to understand your investment goals and research needs.',
    },
    {
      step: '2',
      title: 'Custom Proposal',
      description: 'Receive a tailored proposal with recommended analysis tools and subscription tier.',
    },
    {
      step: '3',
      title: 'Onboarding & Support',
      description: 'Get set up with full platform access and dedicated support to maximize value.',
    },
  ];

  return (
    <MarketingLayout>
      {/* Hero Section */}
      <PageHeader
        title="Become a Bullseye Client"
        subtitle="Join professional investors and traders using AI-powered market intelligence for smarter investment decisions."
      />

      {/* Why Choose Bullseye */}
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
          <Grid container spacing={4}>
            {whyChoosePoints.map((point, idx) => (
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
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'flex-start', mb: 2 }}>
                      <CheckIcon
                        sx={{
                          color: theme.palette.primary.main,
                          mr: 1.5,
                          mt: 0.5,
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
                        {point.title}
                      </Typography>
                    </Box>
                    <Typography
                      variant="body2"
                      sx={{
                        color: theme.palette.text.secondary,
                        lineHeight: 1.7,
                      }}
                    >
                      {point.description}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Service Offerings */}
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
          Our Service Offerings
        </Typography>
        <Grid container spacing={4}>
          {serviceOfferings.map((service, idx) => (
            <Grid item xs={12} sm={6} key={idx}>
              <Card
                sx={{
                  height: '100%',
                  border: `1px solid ${theme.palette.divider}`,
                  backgroundColor: theme.palette.background.paper,
                  borderRadius: '0px',
                  transition: 'all 0.3s ease',
                  '&:hover': {
                    borderColor: alpha(theme.palette.primary.main, 0.5),
                    boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
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
                    {service.title}
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{
                      color: theme.palette.text.secondary,
                      lineHeight: 1.7,
                    }}
                  >
                    {service.description}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Container>

      {/* Getting Started Process */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: '#f8f9fa' }}>
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
            Getting Started
          </Typography>
          <Grid container spacing={4} sx={{ mb: 4 }}>
            {processSteps.map((step, idx) => (
              <Grid item xs={12} sm={6} md={4} key={idx}>
                <Box sx={{ textAlign: 'center' }}>
                  <Box
                    sx={{
                      width: 70,
                      height: 70,
                      borderRadius: '0px',
                      backgroundColor: theme.palette.primary.main,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: '#fff',
                      fontSize: '2rem',
                      fontWeight: 'bold',
                      mb: 2,
                      mx: 'auto',
                    }}
                  >
                    {step.step}
                  </Box>
                  <Typography
                    variant="h6"
                    sx={{
                      fontWeight: 700,
                      mb: 1.5,
                      color: theme.palette.text.primary,
                    }}
                  >
                    {step.title}
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{
                      color: theme.palette.text.secondary,
                      lineHeight: 1.6,
                    }}
                  >
                    {step.description}
                  </Typography>
                </Box>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Contact Form Section */}
      <Container maxWidth="md" sx={{ py: { xs: 6, md: 8 } }}>
        <Typography
          variant="h3"
          sx={{
            fontSize: { xs: '1.8rem', sm: '2.2rem', md: '2.5rem' },
            fontWeight: 800,
            mb: 1,
            textAlign: 'center',
            color: theme.palette.text.primary,
          }}
        >
          Start Your Journey Today
        </Typography>
        <Typography
          sx={{
            fontSize: '1.05rem',
            color: theme.palette.text.secondary,
            textAlign: 'center',
            mb: 4,
            maxWidth: '600px',
            mx: 'auto',
          }}
        >
          Fill out the form below and our team will contact you to discuss your investment research needs.
        </Typography>

        <Card
          sx={{
            border: `1px solid ${theme.palette.divider}`,
            backgroundColor: theme.palette.background.paper,
            borderRadius: '0px',
            p: 4,
          }}
        >
          <form onSubmit={handleSubmit}>
            <Grid container spacing={3}>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="Full Name"
                  name="name"
                  value={formData.name}
                  onChange={handleInputChange}
                  required
                  variant="outlined"
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="Company"
                  name="company"
                  value={formData.company}
                  onChange={handleInputChange}
                  variant="outlined"
                />
              </Grid>

              <Grid item xs={12} sm={6}>
                <FormControl fullWidth>
                  <InputLabel>Client Type</InputLabel>
                  <Select
                    name="clientType"
                    value={formData.clientType}
                    onChange={handleInputChange}
                    label="Client Type"
                  >
                    <MenuItem value="">Select...</MenuItem>
                    <MenuItem value="institution">Institutional</MenuItem>
                    <MenuItem value="wealth">Wealth Management</MenuItem>
                    <MenuItem value="individual">Individual Investor</MenuItem>
                    <MenuItem value="trader">Active Trader</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              <Grid item xs={12} sm={6}>
                <FormControl fullWidth>
                  <InputLabel>Assets Under Management</InputLabel>
                  <Select
                    name="aum"
                    value={formData.aum}
                    onChange={handleInputChange}
                    label="Assets Under Management"
                  >
                    <MenuItem value="">Select...</MenuItem>
                    <MenuItem value="0-20m">$0 - $20M</MenuItem>
                    <MenuItem value="20-100m">$20M - $100M</MenuItem>
                    <MenuItem value="100m-500m">$100M - $500M</MenuItem>
                    <MenuItem value="500m-1b">$500M - $1B</MenuItem>
                    <MenuItem value="1b+">$1B+</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="Phone Number"
                  name="phone"
                  type="tel"
                  value={formData.phone}
                  onChange={handleInputChange}
                  required
                  variant="outlined"
                />
              </Grid>

              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="Email Address"
                  name="email"
                  type="email"
                  value={formData.email}
                  onChange={handleInputChange}
                  required
                  variant="outlined"
                />
              </Grid>

              <Grid item xs={12}>
                <FormControl fullWidth>
                  <InputLabel>Subscription Preference</InputLabel>
                  <Select
                    name="subscriptionType"
                    value={formData.subscriptionType}
                    onChange={handleInputChange}
                    label="Subscription Preference"
                  >
                    <MenuItem value="">Select...</MenuItem>
                    <MenuItem value="individual">Individual Access</MenuItem>
                    <MenuItem value="team">Team/Firm-wide</MenuItem>
                    <MenuItem value="enterprise">Enterprise Custom</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Message"
                  name="message"
                  value={formData.message}
                  onChange={handleInputChange}
                  multiline
                  rows={4}
                  placeholder="Tell us about your investment research needs..."
                  variant="outlined"
                />
              </Grid>

              <Grid item xs={12}>
                <Button
                  type="submit"
                  variant="contained"
                  size="large"
                  fullWidth
                  sx={{
                    py: 1.5,
                    fontSize: '1rem',
                    fontWeight: 600,
                    borderRadius: '0px',
                    textTransform: 'none',
                  }}
                >
                  Request Information
                </Button>
              </Grid>
            </Grid>
          </form>
        </Card>
      </Container>

      {/* Final CTA */}
      <Box sx={{ mx: { xs: 2, md: 4 }, mb: 6 }}>
        <Box
          sx={{
            py: { xs: 4, md: 6 },
            px: { xs: 3, md: 6 },
            backgroundColor: alpha(theme.palette.primary.main, 0.08),
            border: `1px solid ${alpha(theme.palette.primary.main, 0.3)}`,
            borderRadius: '0px',
            textAlign: 'center',
          }}
        >
          <Typography
            variant="h4"
            sx={{
              fontWeight: 700,
              mb: 2,
              color: theme.palette.text.primary,
              fontSize: { xs: '1.5rem', md: '2rem' },
            }}
          >
            Ready to Transform Your Investment Strategy?
          </Typography>
          <Typography
            sx={{
              fontSize: '1.05rem',
              color: theme.palette.text.secondary,
              mb: 3,
              maxWidth: '600px',
              mx: 'auto',
            }}
          >
            Join hundreds of professional investors using Bullseye Financial for AI-powered market intelligence.
          </Typography>
          <CTAButtonGroup
            primaryCTA={{ label: 'Schedule Demo', link: '#' }}
            secondaryCTA={{ label: 'Browse Platform', link: '/app/market' }}
          />
        </Box>
      </Box>
    </MarketingLayout>
  );
};

export default BecomeClient;
