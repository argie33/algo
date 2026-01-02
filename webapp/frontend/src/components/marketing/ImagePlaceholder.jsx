import React from 'react';
import { Box, useTheme, alpha } from '@mui/material';

/**
 * ImagePlaceholder Component
 * Reusable image container with gradient background and error handling
 * Used by: HeroSection, Home, Services, Research pages
 */
const ImagePlaceholder = ({
  src,
  alt = 'Image',
  height = { xs: '300px', md: '450px' },
  onError = null,
}) => {
  const theme = useTheme();

  const handleImageError = (e) => {
    if (onError) {
      onError(e);
    } else {
      // Default behavior: hide broken image
      e.target.style.display = 'none';
    }
  };

  return (
    <Box
      sx={{
        height,
        background: `linear-gradient(135deg, ${theme.palette.primary.main}15 0%, ${theme.palette.primary.main}05 100%)`,
        border: `1px solid ${alpha(theme.palette.divider, 0.5)}`,
        borderRadius: '0px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
      }}
    >
      <Box
        component="img"
        src={src}
        alt={alt}
        onError={handleImageError}
        sx={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          objectPosition: 'center',
        }}
      />
    </Box>
  );
};

export default ImagePlaceholder;
