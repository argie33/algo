import React from 'react';
import { Container, Box, Typography, Grid, Card, CardContent, useTheme } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import ContactForm from '../../components/marketing/ContactForm';
import { Email as EmailIcon, Phone as PhoneIcon, LocationOn as LocationOnIcon } from '@mui/icons-material';

const Contact = () => {
  const theme = useTheme();

  const contactInfo = [
    {
      icon: <EmailIcon />,
      title: 'Email',
      content: 'support@bullseyefinancial.com',
      subtitle: 'We respond within 24 hours',
    },
    {
      icon: <PhoneIcon />,
      title: 'Phone',
      content: '+1 (555) 123-4567',
      subtitle: 'Available Mon-Fri, 9AM-5PM EST',
    },
    {
      icon: <LocationOnIcon />,
      title: 'Location',
      content: 'New York, NY',
      subtitle: 'US-based company',
    },
  ];

  return (
    <MarketingLayout>
      {/* Header */}
      <PageHeader
        title="Get in Touch"
        subtitle="Questions about our AI-powered research and analysis platform? Interested in learning more about how we help investors manage their portfolios? We'd love to hear from you."
      />

      <Container maxWidth="lg" sx={{ py: { xs: 6, md: 8 } }}>
        <Grid container spacing={6}>
          {/* Contact Form */}
          <Grid item xs={12} md={6}>
            <Box>
              <Typography variant="h5" sx={{ fontWeight: 700, mb: 3 }}>
                Send us a Message
              </Typography>
              <ContactForm
                onSubmit={async (data) => {
                  try {
                    const response = await fetch('/api/contact', {
                      method: 'POST',
                      headers: {
                        'Content-Type': 'application/json',
                      },
                      body: JSON.stringify(data)
                    });

                    const result = await response.json();

                    if (!response.ok) {
                      throw new Error(result.error || 'Failed to submit form');
                    }

                    console.log('✅ Form submitted successfully:', result.data);
                    return result;
                  } catch (error) {
                    console.error('❌ Form submission error:', error);
                    throw error;
                  }
                }}
              />
            </Box>
          </Grid>

          {/* Contact Information */}
          <Grid item xs={12} md={6}>
            <Box>
              <Typography variant="h5" sx={{ fontWeight: 700, mb: 3 }}>
                Contact Information
              </Typography>
              <Grid container spacing={3}>
                {contactInfo.map((info, idx) => (
                  <Grid item xs={12} key={idx}>
                    <Card
                      sx={{
                        border: `1px solid ${theme.palette.divider}`,
                      }}
                    >
                      <CardContent>
                        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 2 }}>
                          <Box
                            sx={{
                              fontSize: '1.5rem',
                              color: theme.palette.primary.main,
                              mt: 0.5,
                            }}
                          >
                            {info.icon}
                          </Box>
                          <Box>
                            <Typography
                              variant="h6"
                              sx={{
                                fontWeight: 700,
                                mb: 0.5,
                                color: theme.palette.text.primary,
                              }}
                            >
                              {info.title}
                            </Typography>
                            <Typography
                              variant="body1"
                              sx={{
                                fontWeight: 600,
                                color: theme.palette.text.primary,
                                mb: 0.5,
                              }}
                            >
                              {info.content}
                            </Typography>
                            <Typography
                              variant="body2"
                              sx={{
                                color: theme.palette.text.secondary,
                              }}
                            >
                              {info.subtitle}
                            </Typography>
                          </Box>
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>
                ))}
              </Grid>

              {/* FAQ Section */}
              <Box sx={{ mt: 4 }}>
                <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>
                  Frequently Asked Questions
                </Typography>
                <Typography
                  variant="body2"
                  sx={{
                    color: theme.palette.text.secondary,
                    lineHeight: 1.8,
                    mb: 2,
                  }}
                >
                  <strong>What analysis tools does the platform include?</strong>
                  <br />
                  We offer 8 analysis dimensions: Stock Scoring, Earnings Calendar, Sentiment Analytics, Trading Signals, Sector Analysis, Economic Indicators, Market Overview, and Hedge Helper—all powered by AI.
                </Typography>
                <Typography
                  variant="body2"
                  sx={{
                    color: theme.palette.text.secondary,
                    lineHeight: 1.8,
                  }}
                >
                  <strong>How can I get started?</strong>
                  <br />
                  You can access the full platform immediately. Launch the app from our home page and begin exploring market analysis right away.
                </Typography>
              </Box>
            </Box>
          </Grid>
        </Grid>
      </Container>
    </MarketingLayout>
  );
};

export default Contact;
