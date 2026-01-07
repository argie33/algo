import React from 'react';
import {
  Box,
  Container,
  Grid,
  Card,
  CardContent,
  CardActionArea,
  Typography,
  useTheme,
  useMediaQuery,
  Chip,
  alpha,
} from '@mui/material';
import { useNavigate } from 'react-router-dom';

const FeatureGrid = ({ title, subtitle, features, columns = { xs: 1, sm: 2, md: 3, lg: 3 } }) => {
  const navigate = useNavigate();
  const theme = useTheme();

  const getColorFromIndex = (idx) => {
    // Professional single-color accent scheme (light grays with blue accent)
    return {
      main: theme.palette.primary.main,  // Consistent professional blue
      light: alpha(theme.palette.primary.main, 0.08),  // Very subtle background
    };
  };

  return (
    <Box sx={{ py: { xs: 6, md: 8 }, backgroundColor: theme.palette.background.default }}>
      <Container maxWidth="lg">
        {/* Header */}
        {(title || subtitle) && (
          <Box sx={{ mb: 6, textAlign: 'center' }}>
            {title && (
              <Typography
                variant="h3"
                component="h2"
                sx={{
                  fontSize: { xs: '2rem', sm: '2.5rem', md: '3rem' },
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
                  maxWidth: '600px',
                  mx: 'auto',
                }}
              >
                {subtitle}
              </Typography>
            )}
          </Box>
        )}

        {/* Feature Grid */}
        <Grid container spacing={3}>
          {features.map((feature, idx) => {
            const colors = getColorFromIndex(idx);
            return (
              <Grid item xs={columns.xs} sm={columns.sm} md={columns.md} lg={columns.lg} key={idx}>
                <CardActionArea
                  onClick={() => feature.link && navigate(feature.link)}
                  sx={{ height: '100%' }}
                >
                  <Card
                    sx={{
                      height: '100%',
                      display: 'flex',
                      flexDirection: 'column',
                      cursor: feature.link ? 'pointer' : 'default',
                      transition: 'all 0.3s ease',
                      border: `1px solid ${alpha(theme.palette.divider, 0.4)}`,
                      backgroundColor: theme.palette.background.paper,
                      boxShadow: 'none',
                      borderRadius: '0px',
                      '&:hover': feature.link ? {
                        borderColor: alpha(theme.palette.primary.main, 0.4),
                        boxShadow: '0 4px 12px rgba(0,0,0,0.06)',
                        '& .feature-icon': {
                          backgroundColor: colors.light,
                          color: colors.main,
                        },
                      } : {},
                    }}
                  >
                    <CardContent sx={{ flexGrow: 1, pb: 2, textAlign: 'center' }}>
                      {/* Icon */}
                      {feature.icon && (
                        <Box
                          className="feature-icon"
                          sx={{
                            width: 52,
                            height: 52,
                            borderRadius: '0px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: '1.5rem',
                            mb: 2,
                            mx: 'auto',
                            backgroundColor: colors.light,
                            color: colors.main,
                            transition: 'all 0.3s ease',
                            border: `1px solid ${alpha(colors.main, 0.2)}`,
                          }}
                        >
                          {React.isValidElement(feature.icon) ? feature.icon : null}
                        </Box>
                      )}

                      {/* Title */}
                      <Typography
                        variant="h6"
                        sx={{
                          fontWeight: 700,
                          mb: 1.5,
                          color: theme.palette.text.primary,
                          fontSize: '1.1rem',
                          textAlign: 'center',
                        }}
                      >
                        {feature.title}
                      </Typography>

                      {/* Description */}
                      <Typography
                        variant="body2"
                        sx={{
                          color: theme.palette.text.secondary,
                          mb: 2,
                          lineHeight: 1.6,
                          textAlign: 'center',
                        }}
                      >
                        {feature.description}
                      </Typography>

                      {/* Bullet Points (Optional) */}
                      {feature.bullets && (
                        <Box sx={{ mb: 2, display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 1, width: '100%', px: 2 }}>
                          {feature.bullets.map((bullet, bidx) => (
                            <Box
                              key={bidx}
                              sx={{
                                display: 'flex',
                                alignItems: 'flex-start',
                                fontSize: '0.9rem',
                                color: theme.palette.text.secondary,
                                gap: 1,
                              }}
                            >
                              <Box
                                sx={{
                                  width: 4,
                                  height: 4,
                                  borderRadius: '50%',
                                  backgroundColor: colors.main,
                                  flexShrink: 0,
                                  mt: 0.75,
                                }}
                              />
                              <Box sx={{ flex: 1 }}>{bullet}</Box>
                            </Box>
                          ))}
                        </Box>
                      )}

                      {/* Tags (Optional) */}
                      {feature.tags && (
                        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mt: 2, justifyContent: 'center' }}>
                          {feature.tags.map((tag, tidx) => (
                            <Chip
                              key={tidx}
                              label={tag}
                              size="small"
                              variant="outlined"
                              sx={{
                                borderColor: alpha(theme.palette.primary.main, 0.3),
                                color: theme.palette.text.secondary,
                                fontWeight: 500,
                                fontSize: '0.75rem',
                                backgroundColor: 'transparent',
                              }}
                            />
                          ))}
                        </Box>
                      )}
                    </CardContent>
                  </Card>
                </CardActionArea>
              </Grid>
            );
          })}
        </Grid>
      </Container>
    </Box>
  );
};

export default FeatureGrid;
