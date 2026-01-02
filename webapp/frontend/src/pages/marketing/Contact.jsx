import React from 'react';
import { Container, Box, Typography, Grid, Card, CardContent, useTheme, alpha } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import ContactForm from '../../components/marketing/ContactForm';
import { Email as EmailIcon, Phone as PhoneIcon, LocationOn as LocationOnIcon, Business as BusinessIcon, School as SchoolIcon } from '@mui/icons-material';

const Contact = () => {
  const theme = useTheme();

  const contactDepartments = [
    {
      department: 'Sales & Partnerships',
      icon: <BusinessIcon />,
      image: 'https://images.unsplash.com/photo-1552664730-d307ca884978?w=600&h=350&fit=crop',
      description: 'Get a demo. Discuss pricing. Explore custom solutions tailored to your investment strategy.',
      email: 'sales@bullseyefinancial.com',
      phone: '+1 (555) 123-4567',
      hours: 'Mon-Fri, 9AM-5PM EST',
    },
    {
      department: 'Support & Technical',
      icon: <PhoneIcon />,
      image: 'https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=600&h=350&fit=crop',
      description: 'Need help with the platform? Questions about data, features, or API integration?',
      email: 'support@bullseyefinancial.com',
      phone: '+1 (555) 123-4568',
      hours: 'Mon-Fri, 8AM-6PM EST',
    },
    {
      department: 'Research & Methodology',
      icon: <SchoolIcon />,
      image: 'https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?w=600&h=350&fit=crop',
      description: 'Dive deep into our research. Understand our methodology. Discuss custom analysis for your portfolio.',
      email: 'research@bullseyefinancial.com',
      phone: '+1 (555) 123-4569',
      hours: 'Mon-Fri, 9AM-5PM EST',
    },
  ];

  const contactInfo = [
    {
      icon: <LocationOnIcon />,
      title: 'Headquarters',
      content: 'Chicago, Illinois',
      subtitle: 'US-based research firm',
    },
    {
      icon: <PhoneIcon />,
      title: 'Main Line',
      content: '+1 (555) 123-4567',
      subtitle: 'Main switchboard - Route to appropriate department',
    },
    {
      icon: <EmailIcon />,
      title: 'General Inquiry',
      content: 'info@bullseyefinancial.com',
      subtitle: 'We respond within 24 hours',
    },
  ];

  return (
    <MarketingLayout>
      {/* Header */}
      <PageHeader
        title="Contact Our Research Team"
        subtitle="Interested in our institutional-grade research solutions? Have questions about our methodology or data? Want to discuss a custom research partnership? Get in touch with our team."
      />

      {/* Contact Departments Section */}
      <Container maxWidth="lg" sx={{ py: { xs: 6, md: 8 } }}>
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
          Reach the Right Department
        </Typography>
        <Typography
          sx={{
            fontSize: '1.05rem',
            color: theme.palette.text.secondary,
            textAlign: 'center',
            mb: 6,
            maxWidth: '700px',
            mx: 'auto',
          }}
        >
          We have specialized teams ready to help with sales inquiries, technical support, and research methodology questions.
        </Typography>
        <Grid container spacing={4}>
          {contactDepartments.map((dept, idx) => (
            <Grid item xs={12} md={4} key={idx}>
              <Card
                sx={{
                  height: '100%',
                  border: `1px solid ${theme.palette.divider}`,
                  backgroundColor: theme.palette.background.paper,
                  borderRadius: '0px',
                  transition: 'all 0.3s ease',
                  overflow: 'hidden',
                  '&:hover': {
                    boxShadow: '0 8px 24px rgba(0,0,0,0.1)',
                    transform: 'translateY(-4px)',
                  },
                }}
              >
                <Box
                  component="img"
                  src={dept.image}
                  alt={dept.department}
                  sx={{
                    width: '100%',
                    height: 220,
                    objectFit: 'cover',
                    display: 'block',
                  }}
                  onError={(e) => {
                    e.target.style.display = 'none';
                    e.target.parentElement.style.background = `linear-gradient(135deg, ${theme.palette.primary.main}20 0%, ${theme.palette.primary.main}05 100%)`;
                  }}
                />
                <CardContent sx={{ p: 4 }}>
                  <Box
                    sx={{
                      fontSize: '2.5rem',
                      color: theme.palette.primary.main,
                      mb: 2,
                    }}
                  >
                    {dept.icon}
                  </Box>
                  <Typography
                    variant="h6"
                    sx={{
                      fontWeight: 700,
                      mb: 1,
                      color: theme.palette.text.primary,
                    }}
                  >
                    {dept.department}
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{
                      color: theme.palette.text.secondary,
                      mb: 3,
                      lineHeight: 1.6,
                    }}
                  >
                    {dept.description}
                  </Typography>
                  <Box sx={{ borderTop: `1px solid ${theme.palette.divider}`, pt: 3 }}>
                    <Typography
                      variant="body2"
                      sx={{
                        color: theme.palette.text.primary,
                        fontWeight: 600,
                        mb: 0.5,
                      }}
                    >
                      {dept.email}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        color: theme.palette.text.primary,
                        fontWeight: 600,
                        mb: 1,
                      }}
                    >
                      {dept.phone}
                    </Typography>
                    <Typography
                      variant="caption"
                      sx={{
                        color: theme.palette.text.secondary,
                      }}
                    >
                      {dept.hours}
                    </Typography>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Container>

      {/* Main Contact Section */}
      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: theme.palette.background.paper }}>
        <Container maxWidth="lg">
          <Grid container spacing={6}>
            {/* Contact Form */}
            <Grid item xs={12} md={6}>
              <Box>
                <Typography
                  variant="h4"
                  sx={{
                    fontWeight: 700,
                    mb: 3,
                    fontSize: { xs: '1.5rem', md: '1.8rem' },
                    color: theme.palette.text.primary,
                  }}
                >
                  Send us a Message
                </Typography>
                <Typography
                  variant="body2"
                  sx={{
                    color: theme.palette.text.secondary,
                    mb: 4,
                    lineHeight: 1.6,
                  }}
                >
                  Have specific questions about our research platform, custom solutions, or partnership opportunities? Fill out the form below and we'll get back to you promptly.
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
                <Typography
                  variant="h4"
                  sx={{
                    fontWeight: 700,
                    mb: 3,
                    fontSize: { xs: '1.5rem', md: '1.8rem' },
                    color: theme.palette.text.primary,
                  }}
                >
                  Get in Touch
                </Typography>
                <Grid container spacing={3} sx={{ mb: 6 }}>
                  {contactInfo.map((info, idx) => (
                    <Grid item xs={12} key={idx}>
                      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 2 }}>
                        <Box
                          sx={{
                            fontSize: '1.8rem',
                            color: theme.palette.primary.main,
                            mt: 0.5,
                            flexShrink: 0,
                          }}
                        >
                          {info.icon}
                        </Box>
                        <Box sx={{ flex: 1 }}>
                          <Typography
                            variant="h6"
                            sx={{
                              fontWeight: 700,
                              mb: 0.5,
                              color: theme.palette.text.primary,
                              fontSize: '1.05rem',
                            }}
                          >
                            {info.title}
                          </Typography>
                          <Typography
                            variant="body2"
                            sx={{
                              fontWeight: 600,
                              color: theme.palette.text.primary,
                              mb: 0.5,
                            }}
                          >
                            {info.content}
                          </Typography>
                          <Typography
                            variant="caption"
                            sx={{
                              color: theme.palette.text.secondary,
                            }}
                          >
                            {info.subtitle}
                          </Typography>
                        </Box>
                      </Box>
                    </Grid>
                  ))}
                </Grid>

                {/* FAQ Section */}
                <Box sx={{ backgroundColor: alpha(theme.palette.primary.main, 0.05), p: 3, borderRadius: '0px' }}>
                  <Typography
                    variant="h6"
                    sx={{
                      fontWeight: 700,
                      mb: 3,
                      color: theme.palette.text.primary,
                    }}
                  >
                    Research & Platform FAQs
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{
                      color: theme.palette.text.secondary,
                      lineHeight: 1.8,
                      mb: 3,
                    }}
                  >
                    <strong>What research dimensions does your platform cover?</strong>
                    <br />
                    We provide 6+ research dimensions: AI-powered stock scoring, earnings intelligence, sentiment & positioning analysis, technical analysis, sector research, economic & macro intelligence, market overview, and hedge helper tools.
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{
                      color: theme.palette.text.secondary,
                      lineHeight: 1.8,
                      mb: 3,
                    }}
                  >
                    <strong>Can I get a custom research solution?</strong>
                    <br />
                    Yes! We specialize in customized solutions. Our research team can tailor data dimensions, delivery methods, and analysis focus to match your specific investment strategy and requirements.
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{
                      color: theme.palette.text.secondary,
                      lineHeight: 1.8,
                    }}
                  >
                    <strong>What data sources do you use?</strong>
                    <br />
                    We integrate 10+ years of historical market data, real-time pricing, earnings data, sentiment indicators, economic calendars, and proprietary positioning metrics. All data is continuously updated and validated.
                  </Typography>
                </Box>
              </Box>
            </Grid>
          </Grid>
        </Container>
      </Box>
    </MarketingLayout>
  );
};

export default Contact;
