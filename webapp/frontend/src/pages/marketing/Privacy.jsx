import React from 'react';
import { Container, Box, Typography, useTheme, List, ListItem } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';

const Privacy = () => {
  const theme = useTheme();

  return (
    <MarketingLayout>
      <PageHeader
        title="Privacy Policy"
        subtitle="We take your privacy seriously"
      />

      <Container maxWidth="md" sx={{ py: { xs: 6, md: 8 } }}>
        <Box sx={{ lineHeight: 1.8 }}>
          <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, mt: 4 }}>
            1. Information We Collect
          </Typography>
          <Typography sx={{ color: theme.palette.text.secondary, mb: 2 }}>
            We may collect the following types of information:
          </Typography>
          <List sx={{ color: theme.palette.text.secondary, ml: 2 }}>
            <ListItem>• Email address when you sign up for our newsletter or services</ListItem>
            <ListItem>• Name and contact information when you submit a contact form</ListItem>
            <ListItem>• Usage data and analytics about how you interact with our website</ListItem>
            <ListItem>• IP address and browser information for security and analytics purposes</ListItem>
            <ListItem>• Account information if you create an account on our platform</ListItem>
          </List>

          <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, mt: 4 }}>
            2. How We Use Your Information
          </Typography>
          <Typography sx={{ color: theme.palette.text.secondary, mb: 2 }}>
            We use the information we collect for the following purposes:
          </Typography>
          <List sx={{ color: theme.palette.text.secondary, ml: 2 }}>
            <ListItem>• To send you newsletters and updates you've signed up for</ListItem>
            <ListItem>• To respond to your inquiries and provide customer support</ListItem>
            <ListItem>• To improve our website and services</ListItem>
            <ListItem>• To analyze usage patterns and trends</ListItem>
            <ListItem>• To comply with legal obligations</ListItem>
            <ListItem>• To protect against fraud and ensure security</ListItem>
          </List>

          <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, mt: 4 }}>
            3. Data Security
          </Typography>
          <Typography sx={{ color: theme.palette.text.secondary, mb: 3 }}>
            We implement appropriate security measures to protect your personal information from unauthorized access, alteration, disclosure, or destruction. However, no method of transmission over the internet is completely secure, and we cannot guarantee absolute security.
          </Typography>

          <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, mt: 4 }}>
            4. Third-Party Services
          </Typography>
          <Typography sx={{ color: theme.palette.text.secondary, mb: 3 }}>
            We may use third-party services (such as email providers, analytics services, and hosting providers) to process your information. These third parties are contractually obligated to use your information only as necessary to provide services to us and maintain confidentiality.
          </Typography>

          <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, mt: 4 }}>
            5. Cookies and Tracking
          </Typography>
          <Typography sx={{ color: theme.palette.text.secondary, mb: 3 }}>
            Our website uses cookies to enhance your experience. You can control cookie settings through your browser preferences. Some cookies are essential for website functionality, while others help us understand how you use our site.
          </Typography>

          <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, mt: 4 }}>
            6. Your Rights
          </Typography>
          <Typography sx={{ color: theme.palette.text.secondary, mb: 2 }}>
            Depending on your location, you may have the following rights:
          </Typography>
          <List sx={{ color: theme.palette.text.secondary, ml: 2 }}>
            <ListItem>• Right to access your personal information</ListItem>
            <ListItem>• Right to correct inaccurate information</ListItem>
            <ListItem>• Right to request deletion of your information</ListItem>
            <ListItem>• Right to unsubscribe from marketing communications</ListItem>
            <ListItem>• Right to data portability</ListItem>
            <ListItem>• Right to withdraw consent</ListItem>
          </List>

          <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, mt: 4 }}>
            7. Newsletter Communications
          </Typography>
          <Typography sx={{ color: theme.palette.text.secondary, mb: 3 }}>
            When you subscribe to our newsletter, we will send you regular updates and information about our services. You can unsubscribe at any time by clicking the unsubscribe link in any email or by contacting us directly.
          </Typography>

          <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, mt: 4 }}>
            8. Children's Privacy
          </Typography>
          <Typography sx={{ color: theme.palette.text.secondary, mb: 3 }}>
            Our website is not intended for children under 18 years of age. We do not knowingly collect personal information from children. If we become aware that we have collected information from a child without parental consent, we will delete such information immediately.
          </Typography>

          <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, mt: 4 }}>
            9. Changes to This Policy
          </Typography>
          <Typography sx={{ color: theme.palette.text.secondary, mb: 3 }}>
            We may update this Privacy Policy from time to time. We will notify you of any material changes by posting the updated policy on our website and updating the "Last updated" date below.
          </Typography>

          <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, mt: 4 }}>
            10. Contact Us
          </Typography>
          <Typography sx={{ color: theme.palette.text.secondary, mb: 3 }}>
            If you have questions about this Privacy Policy or our privacy practices, please contact us at{' '}
            <Box component="span" sx={{ color: theme.palette.primary.main, fontWeight: 600 }}>
              privacy@bullseyefinancial.com
            </Box>
          </Typography>

          <Typography sx={{ color: theme.palette.text.secondary, mt: 6, fontSize: '0.9rem' }}>
            Last updated: January 2, 2026
          </Typography>
        </Box>
      </Container>
    </MarketingLayout>
  );
};

export default Privacy;
