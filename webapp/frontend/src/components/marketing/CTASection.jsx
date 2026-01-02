import React from 'react';
import {
  Box,
  Container,
  Typography,
  Button,
  useTheme,
  alpha,
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { ArrowForward as ArrowForwardIcon } from '@mui/icons-material';

const CTASection = ({
  title,
  subtitle,
  primaryCTA = { label: 'Get Started', link: '/app/market' },
  secondaryCTA = { label: 'Learn More', link: '/services' },
  variant = 'primary',
  centered = true,
}) => {
  const navigate = useNavigate();
  const theme = useTheme();

  const bgVariants = {
    primary: {
      background: `linear-gradient(135deg, ${theme.palette.primary.main}15 0%, ${theme.palette.primary.main}05 100%)`,
      borderColor: theme.palette.primary.main + '30',
    },
    secondary: {
      background: theme.palette.background.paper,
      borderColor: theme.palette.divider,
    },
    dark: {
      background: `linear-gradient(135deg, ${theme.palette.primary.main}30 0%, ${theme.palette.primary.main}15 100%)`,
      borderColor: theme.palette.primary.main + '50',
    },
  };

  const selectedVariant = bgVariants[variant] || bgVariants.primary;

  return (
    <Box
      sx={{
        py: { xs: 6, md: 8 },
        background: selectedVariant.background,
        border: `1px solid ${selectedVariant.borderColor}`,
        borderRadius: '0px',
        my: { xs: 4, md: 6 },
      }}
    >
      <Container maxWidth="md">
        <Box sx={{ textAlign: centered ? 'center' : 'left' }}>
          {title && (
            <Typography
              variant="h3"
              component="h2"
              sx={{
                fontSize: { xs: '1.8rem', sm: '2.2rem', md: '2.5rem' },
                fontWeight: 800,
                mb: 2,
                color: theme.palette.text.primary,
              }}
            >
              {title}
            </Typography>
          )}

          {subtitle && (
            <Typography
              variant="h6"
              sx={{
                fontSize: { xs: '1rem', md: '1.1rem' },
                color: theme.palette.text.secondary,
                fontWeight: 400,
                mb: 4,
                lineHeight: 1.6,
              }}
            >
              {subtitle}
            </Typography>
          )}

          {/* Buttons */}
          <Box
            sx={{
              display: 'flex',
              gap: 2,
              flexWrap: 'wrap',
              justifyContent: centered ? 'center' : 'flex-start',
            }}
          >
            {primaryCTA && (
              <Button
                variant="contained"
                size="large"
                onClick={() => navigate(primaryCTA.link)}
                sx={{
                  fontSize: '1rem',
                  fontWeight: 600,
                  py: 1.5,
                  px: 4,
                  borderRadius: '0px',
                  textTransform: 'none',
                  boxShadow: `0 4px 12px ${alpha(theme.palette.primary.main, 0.25)}`,
                  '&:hover': {
                    boxShadow: `0 6px 20px ${alpha(theme.palette.primary.main, 0.35)}`,
                  },
                }}
              >
                {primaryCTA.label}
              </Button>
            )}

            {secondaryCTA && (
              <Button
                variant="outlined"
                size="large"
                onClick={() => navigate(secondaryCTA.link)}
                sx={{
                  fontSize: '1rem',
                  fontWeight: 600,
                  py: 1.5,
                  px: 4,
                  borderRadius: '0px',
                  textTransform: 'none',
                  borderColor: alpha(theme.palette.primary.main, 0.4),
                  '&:hover': {
                    backgroundColor: alpha(theme.palette.primary.main, 0.05),
                    borderColor: theme.palette.primary.main,
                  },
                }}
              >
                {secondaryCTA.label}
              </Button>
            )}
          </Box>
        </Box>
      </Container>
    </Box>
  );
};

export default CTASection;
