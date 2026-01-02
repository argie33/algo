import React from 'react';
import { Box, Container, Typography, Button, alpha, useTheme } from '@mui/material';
import { ArrowForward as ArrowForwardIcon } from '@mui/icons-material';

/**
 * PromoBanner Component
 * Sleek promotional banner for inner pages
 * Used between sections to highlight features or calls-to-action
 */
const PromoBanner = ({
  title,
  subtitle,
  primaryCTA = null,
  secondaryCTA = null,
  variant = 'primary', // primary or dark
  icon = null,
}) => {
  const theme = useTheme();

  const bgColor = variant === 'dark'
    ? theme.palette.primary.main
    : alpha(theme.palette.primary.main, 0.08);

  const textColor = variant === 'dark'
    ? '#fff'
    : theme.palette.text.primary;

  const borderColor = variant === 'dark'
    ? alpha('#fff', 0.2)
    : alpha(theme.palette.primary.main, 0.3);

  return (
    <Box
      sx={{
        py: { xs: 4, md: 6 },
        px: { xs: 2, md: 4 },
        backgroundColor: bgColor,
        border: `1px solid ${borderColor}`,
        borderRadius: '0px',
        my: { xs: 4, md: 6 },
        mx: { xs: 2, md: 4 },
      }}
    >
      <Container maxWidth="lg">
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: { xs: 2, md: 3 },
            flexWrap: { xs: 'wrap', md: 'nowrap' },
          }}
        >
          {icon && (
            <Box
              sx={{
                fontSize: { xs: '2rem', md: '2.5rem' },
                flexShrink: 0,
              }}
            >
              {icon}
            </Box>
          )}

          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography
              variant="h5"
              sx={{
                fontWeight: 700,
                color: textColor,
                mb: 0.5,
                fontSize: { xs: '1.3rem', md: '1.5rem' },
              }}
            >
              {title}
            </Typography>
            {subtitle && (
              <Typography
                variant="body2"
                sx={{
                  color: variant === 'dark'
                    ? alpha('#fff', 0.85)
                    : theme.palette.text.secondary,
                  fontSize: '0.95rem',
                }}
              >
                {subtitle}
              </Typography>
            )}
          </Box>

          {(primaryCTA || secondaryCTA) && (
            <Box
              sx={{
                display: 'flex',
                gap: 2,
                flexWrap: 'wrap',
                justifyContent: { xs: 'flex-start', md: 'flex-end' },
                width: { xs: '100%', md: 'auto' },
                flexShrink: 0,
              }}
            >
              {primaryCTA && (
                <Button
                  variant={variant === 'dark' ? 'contained' : 'contained'}
                  endIcon={<ArrowForwardIcon />}
                  onClick={primaryCTA.onClick}
                  href={primaryCTA.href}
                  sx={{
                    fontSize: '0.9rem',
                    fontWeight: 600,
                    py: 1,
                    px: 2.5,
                    borderRadius: '0px',
                    textTransform: 'none',
                    backgroundColor: variant === 'dark'
                      ? '#fff'
                      : theme.palette.primary.main,
                    color: variant === 'dark'
                      ? theme.palette.primary.main
                      : '#fff',
                    '&:hover': {
                      backgroundColor: variant === 'dark'
                        ? alpha('#fff', 0.9)
                        : alpha(theme.palette.primary.main, 0.9),
                    },
                  }}
                >
                  {primaryCTA.label}
                </Button>
              )}
              {secondaryCTA && (
                <Button
                  variant="outlined"
                  onClick={secondaryCTA.onClick}
                  href={secondaryCTA.href}
                  sx={{
                    fontSize: '0.9rem',
                    fontWeight: 600,
                    py: 1,
                    px: 2.5,
                    borderRadius: '0px',
                    textTransform: 'none',
                    borderColor: variant === 'dark'
                      ? alpha('#fff', 0.3)
                      : alpha(theme.palette.primary.main, 0.5),
                    color: textColor,
                    '&:hover': {
                      backgroundColor: variant === 'dark'
                        ? alpha('#fff', 0.1)
                        : alpha(theme.palette.primary.main, 0.05),
                      borderColor: variant === 'dark'
                        ? alpha('#fff', 0.5)
                        : theme.palette.primary.main,
                    },
                  }}
                >
                  {secondaryCTA.label}
                </Button>
              )}
            </Box>
          )}
        </Box>
      </Container>
    </Box>
  );
};

export default PromoBanner;
