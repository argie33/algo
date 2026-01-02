import React from 'react';
import { Box, Card, CardContent, Grid, Typography, useTheme } from '@mui/material';

/**
 * IconCardGrid Component
 * Reusable card grid with icons and text
 * Used by: Firm (about sections), Services (use cases), Research (testing), Media (learning resources)
 */
const IconCardGrid = ({
  items,
  columns = { xs: 12, sm: 6, md: 6, lg: 6 },
  withHover = true,
  gap = 4,
}) => {
  const theme = useTheme();

  if (!items || items.length === 0) {
    return null;
  }

  return (
    <Grid container spacing={gap}>
      {items.map((item, idx) => (
        <Grid item xs={columns.xs} sm={columns.sm} md={columns.md} lg={columns.lg} key={idx}>
          <Card
            sx={{
              height: '100%',
              border: `1px solid ${theme.palette.divider}`,
              backgroundColor: theme.palette.background.paper,
              borderRadius: '0px',
              transition: 'all 0.3s ease',
              ...(withHover && {
                '&:hover': {
                  boxShadow: theme.shadows[4],
                  transform: 'translateY(-4px)',
                },
              }),
            }}
          >
            <CardContent>
              {/* Icon */}
              {item.icon && (
                <Box
                  sx={{
                    fontSize: item.iconSize || '2.5rem',
                    mb: 2,
                    color: theme.palette.primary.main,
                  }}
                >
                  {item.icon}
                </Box>
              )}

              {/* Title */}
              <Typography
                variant="h6"
                sx={{
                  fontWeight: 700,
                  mb: 1.5,
                  color: theme.palette.text.primary,
                }}
              >
                {item.title}
              </Typography>

              {/* Description */}
              <Typography
                variant="body2"
                sx={{
                  color: theme.palette.text.secondary,
                  lineHeight: 1.6,
                }}
              >
                {item.description}
              </Typography>

              {/* Optional content after description */}
              {item.additionalContent && <Box sx={{ mt: 2 }}>{item.additionalContent}</Box>}
            </CardContent>
          </Card>
        </Grid>
      ))}
    </Grid>
  );
};

export default IconCardGrid;
