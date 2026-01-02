import React from 'react';
import { Container, Box, Typography, useTheme, List, ListItem } from '@mui/material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import PageHeader from '../../components/marketing/PageHeader';

const Terms = () => {
  const theme = useTheme();

  return (
    <MarketingLayout>
      <PageHeader
        title="Terms of Service"
        subtitle="Please read these terms carefully before using our platform"
      />

      <Container maxWidth="md" sx={{ py: { xs: 6, md: 8 } }}>
        <Box sx={{ lineHeight: 1.8 }}>
          <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, mt: 4 }}>
            1. Acceptance of Terms
          </Typography>
          <Typography sx={{ color: theme.palette.text.secondary, mb: 3 }}>
            By accessing and using Bullseye Financial's website and services, you accept and agree to be bound by the terms and provision of this agreement. If you do not agree to abide by the above, please do not use this service.
          </Typography>

          <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, mt: 4 }}>
            2. Use License
          </Typography>
          <Typography sx={{ color: theme.palette.text.secondary, mb: 2 }}>
            Permission is granted to temporarily download one copy of the materials (information or software) on Bullseye Financial's website for personal, non-commercial transitory viewing only. This is the grant of a license, not a transfer of title, and under this license you may not:
          </Typography>
          <List sx={{ color: theme.palette.text.secondary, ml: 2 }}>
            <ListItem>• Modify or copy the materials</ListItem>
            <ListItem>• Use the materials for any commercial purpose or for any public display</ListItem>
            <ListItem>• Attempt to decompile or reverse engineer any software contained on the website</ListItem>
            <ListItem>• Remove any copyright or other proprietary notations from the materials</ListItem>
            <ListItem>• Transfer the materials to another person or "mirror" the materials on any other server</ListItem>
            <ListItem>• Violate any applicable laws or regulations related to access to or use of the website</ListItem>
          </List>

          <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, mt: 4 }}>
            3. Disclaimer
          </Typography>
          <Typography sx={{ color: theme.palette.text.secondary, mb: 3 }}>
            The materials on Bullseye Financial's website are provided on an 'as is' basis. Bullseye Financial makes no warranties, expressed or implied, and hereby disclaims and negates all other warranties including, without limitation, implied warranties or conditions of merchantability, fitness for a particular purpose, or non-infringement of intellectual property or other violation of rights.
          </Typography>

          <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, mt: 4 }}>
            4. Investment Disclaimer
          </Typography>
          <Typography sx={{ color: theme.palette.text.secondary, mb: 3 }}>
            The information provided on Bullseye Financial is for informational purposes only and should not be construed as investment advice. Past performance is not indicative of future results. All investments carry risk, including the potential loss of principal. Before making any investment decisions, please consult with a qualified financial advisor.
          </Typography>

          <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, mt: 4 }}>
            5. Limitations
          </Typography>
          <Typography sx={{ color: theme.palette.text.secondary, mb: 3 }}>
            In no event shall Bullseye Financial or its suppliers be liable for any damages (including, without limitation, damages for loss of data or profit, or due to business interruption) arising out of the use or inability to use the materials on Bullseye Financial's website, even if Bullseye Financial or an authorized representative has been notified orally or in writing of the possibility of such damage.
          </Typography>

          <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, mt: 4 }}>
            6. Accuracy of Materials
          </Typography>
          <Typography sx={{ color: theme.palette.text.secondary, mb: 3 }}>
            The materials appearing on Bullseye Financial's website could include technical, typographical, or photographic errors. Bullseye Financial does not warrant that any of the materials on its website are accurate, complete, or current. Bullseye Financial may make changes to the materials contained on its website at any time without notice.
          </Typography>

          <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, mt: 4 }}>
            7. Links
          </Typography>
          <Typography sx={{ color: theme.palette.text.secondary, mb: 3 }}>
            Bullseye Financial has not reviewed all of the sites linked to its website and is not responsible for the contents of any such linked site. The inclusion of any link does not imply endorsement by Bullseye Financial of the site. Use of any such linked website is at the user's own risk.
          </Typography>

          <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, mt: 4 }}>
            8. Modifications
          </Typography>
          <Typography sx={{ color: theme.palette.text.secondary, mb: 3 }}>
            Bullseye Financial may revise these terms of service for its website at any time without notice. By using this website, you are agreeing to be bound by the then current version of these terms of service.
          </Typography>

          <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, mt: 4 }}>
            9. Governing Law
          </Typography>
          <Typography sx={{ color: theme.palette.text.secondary, mb: 3 }}>
            These terms and conditions are governed by and construed in accordance with the laws of the United States, and you irrevocably submit to the exclusive jurisdiction of the courts located there.
          </Typography>

          <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, mt: 4 }}>
            10. Contact Information
          </Typography>
          <Typography sx={{ color: theme.palette.text.secondary, mb: 3 }}>
            If you have any questions about these Terms of Service, please contact us at{' '}
            <Box component="span" sx={{ color: theme.palette.primary.main, fontWeight: 600 }}>
              legal@bullseyefinancial.com
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

export default Terms;
