import React from 'react';
import { Box, Button, useTheme, alpha } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { ArrowForward as ArrowForwardIcon } from '@mui/icons-material';

/**
 * CTAButtonGroup Component
 * Reusable button group for consistent CTA styling across all pages
 * Eliminates duplicate button code in HeroSection, Home, CTASection, etc.
 */
const CTAButtonGroup = ({
  primaryCTA,
  secondaryCTA = null,
  centered = true,
  gap = 2,
  flexWrap = 'wrap',
}) => {
  const navigate = useNavigate();
  const theme = useTheme();

  if (!primaryCTA) {
    return null;
  }

  const handleNavigate = (link) => {
    navigate(link);
  };

  return (
    <Box
      sx={{
        display: 'flex',
        gap,
        flexWrap,
        justifyContent: centered ? 'center' : 'flex-start',
        alignItems: 'center',
      }}
    >
      {/* Primary Button */}
      <Button
        variant="contained"
        size="large"
        onClick={() => handleNavigate(primaryCTA.link)}
        endIcon={primaryCTA.icon || <ArrowForwardIcon />}
        sx={{
          fontSize: '1rem',
          fontWeight: 600,
          py: 1.5,
          px: 4,
          borderRadius: '0px',
          textTransform: 'none',
          boxShadow: `0 4px 12px ${alpha(theme.palette.primary.main, 0.3)}`,
          '&:hover': {
            boxShadow: `0 6px 20px ${alpha(theme.palette.primary.main, 0.4)}`,
          },
        }}
      >
        {primaryCTA.label}
      </Button>

      {/* Secondary Button */}
      {secondaryCTA && (
        <Button
          variant="outlined"
          size="large"
          onClick={() => handleNavigate(secondaryCTA.link)}
          endIcon={secondaryCTA.icon}
          sx={{
            fontSize: '1rem',
            fontWeight: 600,
            py: 1.5,
            px: 4,
            borderRadius: '0px',
            textTransform: 'none',
            borderColor: alpha(theme.palette.primary.main, 0.5),
            color: theme.palette.primary.main,
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
  );
};

export default CTAButtonGroup;
