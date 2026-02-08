import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Container, Box, Typography, Button, useTheme } from '@mui/material';
import { ArrowBack } from '@mui/icons-material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import CTASection from '../../components/marketing/CTASection';

const articlesData = [];

const ArticleDetail = () => {
  const { articleId } = useParams();
  const navigate = useNavigate();
  const theme = useTheme();

  const article = articlesData.find(a => a.id === articleId);

  if (!article) {
    return (
      <MarketingLayout>
        <Container maxWidth="lg" sx={{ py: 8 }}>
          <Box sx={{ textAlign: 'center' }}>
            <Typography variant="h4" sx={{ mb: 2 }}>Article not found</Typography>
            <Button onClick={() => navigate('/')} startIcon={<ArrowBack />}>
              Back to Home
            </Button>
          </Box>
        </Container>
      </MarketingLayout>
    );
  }

  return (
    <MarketingLayout>
      <Container maxWidth="md" sx={{ py: 6 }}>
        <Button
          onClick={() => navigate('/')}
          startIcon={<ArrowBack />}
          sx={{ mb: 4 }}
        >
          Back to Home
        </Button>

        {/* Article Header */}
        <Box sx={{ mb: 4 }}>
          <Typography
            variant="h2"
            sx={{
              fontSize: { xs: '2rem', md: '2.8rem' },
              fontWeight: 700,
              mb: 2,
              color: theme.palette.text.primary,
              lineHeight: 1.3,
            }}
          >
            {article.title}
          </Typography>

          <Box sx={{ display: 'flex', gap: 3, mb: 3, flexWrap: 'wrap' }}>
            <Typography variant="body2" sx={{ color: theme.palette.text.secondary }}>
              <strong>Published:</strong> {article.date}
            </Typography>
            <Typography variant="body2" sx={{ color: theme.palette.text.secondary }}>
              <strong>By:</strong> {article.author}
            </Typography>
            <Typography variant="body2" sx={{ color: theme.palette.text.secondary }}>
              {article.readTime}
            </Typography>
          </Box>

          {/* Tags */}
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            {article.tags.map((tag, i) => (
              <Typography
                key={i}
                sx={{
                  fontSize: '0.85rem',
                  backgroundColor: theme.palette.mode === 'dark'
                    ? 'rgba(33, 150, 243, 0.2)'
                    : 'rgba(33, 150, 243, 0.1)',
                  px: 1.5,
                  py: 0.5,
                  borderRadius: '4px',
                  color: theme.palette.primary.main,
                  fontWeight: 600,
                }}
              >
                {tag}
              </Typography>
            ))}
          </Box>
        </Box>

        {/* Article Content */}
        <Box
          sx={{
            '& p': {
              fontSize: '1.05rem',
              lineHeight: 1.9,
              color: theme.palette.text.secondary,
              mb: 2.5,
              '&:first-of-type': {
                fontSize: '1.15rem',
                fontWeight: 500,
                color: theme.palette.text.primary,
                mb: 3,
              },
            },
          }}
        >
          {article.content.split('\n\n').map((paragraph, idx) => {
            // Handle section headers
            if (paragraph.startsWith('##')) {
              const headerText = paragraph.replace(/^##\s/, '');
              return (
                <Typography
                  key={idx}
                  variant="h4"
                  sx={{
                    fontSize: '1.6rem',
                    fontWeight: 700,
                    mt: 4,
                    mb: 2,
                    color: theme.palette.text.primary,
                  }}
                >
                  {headerText}
                </Typography>
              );
            }

            // Skip empty paragraphs
            if (!paragraph.trim()) {
              return null;
            }

            // Regular paragraphs
            return (
              <Typography
                key={idx}
                sx={{
                  fontSize: '1.05rem',
                  lineHeight: 1.9,
                  color: theme.palette.text.secondary,
                  mb: 2.5,
                }}
              >
                {paragraph}
              </Typography>
            );
          })}
        </Box>

        <Box sx={{ mt: 6, pt: 4, borderTop: `1px solid ${theme.palette.divider}` }}>
          <Typography variant="caption" sx={{ color: theme.palette.text.secondary }}>
            This analysis represents comprehensive macro economic and market analysis. Suitable for institutional investors and advisors with multi-quarter to multi-year planning horizons.
          </Typography>
        </Box>
      </Container>

      <CTASection
        variant="dark"
        title="Ready to Access Professional Research?"
        subtitle="Get institutional-grade market research and advisory insights."
        primaryCTA={{ label: 'Launch Platform', link: '/app/market' }}
      />
    </MarketingLayout>
  );
};

export default ArticleDetail;
