import React from 'react';
import { Container, Box, Typography, Grid, Card, CardContent, useTheme, alpha, Accordion, AccordionSummary, AccordionDetails } from '@mui/material';
import { ExpandMore as ExpandMoreIcon, Help as HelpIcon } from '@mui/icons-material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';
import CTASection from '../../components/marketing/CTASection';
import ImagePlaceholder from '../../components/marketing/ImagePlaceholder';

const FAQs = () => {
  const theme = useTheme();

  const faqCategories = [
    {
      title: 'Research & Data',
      faqs: [
        {
          question: 'What research dimensions does your platform cover?',
          answer: 'We provide 6+ research dimensions: AI-powered stock scoring, earnings intelligence, sentiment & positioning analysis, technical analysis, sector research, economic & macro intelligence, market overview, and hedge helper tools.',
        },
        {
          question: 'Do you offer institutional data access?',
          answer: 'Yes. Institutional clients can access our research data via API for integration with internal systems. Contact our sales team to discuss enterprise access options.',
        },
        {
          question: 'What data sources do you use?',
          answer: 'We integrate 10+ years of historical market data, real-time pricing, earnings data, sentiment indicators, economic calendars, and proprietary positioning metrics. All data is continuously updated and validated.',
        },
      ],
    },
  ];

  return (
    <MarketingLayout>
      <PageHeader
        title="Frequently Asked Questions"
        subtitle="Find answers to common questions about our research platform and services"
      />

      {/* Hero Image */}
      <Box sx={{ py: { xs: 4, md: 6 }, backgroundColor: theme.palette.background.paper }}>
        <Container maxWidth="lg">
          <ImagePlaceholder
            src="https://picsum.photos/1200/400?random"
            alt="Professional support and customer service"
            height={{ xs: '250px', md: '350px' }}
          />
        </Container>
      </Box>

      <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: theme.palette.background.default }}>
        <Container maxWidth="lg">
          {faqCategories.map((category, catIdx) => (
            <Box key={catIdx} sx={{ mb: 8 }}>
              <Typography
                variant="h4"
                sx={{
                  fontSize: { xs: '1.5rem', sm: '2rem', md: '2.2rem' },
                  fontWeight: 800,
                  mb: 4,
                  color: theme.palette.text.primary,
                }}
              >
                {category.title}
              </Typography>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {category.faqs.map((faq, faqIdx) => (
                  <Accordion
                    key={faqIdx}
                    sx={{
                      border: `1px solid ${theme.palette.divider}`,
                      backgroundColor: theme.palette.background.paper,
                      borderRadius: '0px',
                      '&:hover': {
                        backgroundColor: alpha(theme.palette.primary.main, 0.02),
                      },
                      '&.Mui-expanded': {
                        margin: '0',
                      },
                    }}
                  >
                    <AccordionSummary
                      expandIcon={<ExpandMoreIcon />}
                      sx={{
                        '& .MuiAccordionSummary-content': {
                          margin: '12px 0',
                        },
                      }}
                    >
                      <Typography
                        sx={{
                          fontWeight: 600,
                          fontSize: '1.05rem',
                          color: theme.palette.text.primary,
                        }}
                      >
                        {faq.question}
                      </Typography>
                    </AccordionSummary>
                    <AccordionDetails sx={{ pt: 0, pb: 2 }}>
                      <Typography
                        sx={{
                          color: theme.palette.text.secondary,
                          lineHeight: 1.8,
                          fontSize: '1rem',
                        }}
                      >
                        {faq.answer}
                      </Typography>
                    </AccordionDetails>
                  </Accordion>
                ))}
              </Box>
            </Box>
          ))}
        </Container>
      </Box>

      <Box sx={{ mx: { xs: 2, md: 4 }, mb: 6 }}>
        <CTASection
          variant="primary"
          title="Still have questions?"
          subtitle="Contact our team directly for more detailed information about our research platform and services."
          primaryCTA={{ label: 'Contact Us', link: '/contact' }}
          
        />
      </Box>
    </MarketingLayout>
  );
};

export default FAQs;
