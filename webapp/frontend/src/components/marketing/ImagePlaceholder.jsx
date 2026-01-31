import React, { useState } from 'react';
import { Box, useTheme, alpha } from '@mui/material';

/**
 * ImagePlaceholder Component
 * Reusable image container with gradient background and error handling
 * Shows gradient background if image fails to load
 * Used by: HeroSection, Home, Services, Research pages
 */
const ImagePlaceholder = ({
  src,
  alt = 'Image',
  height = { xs: '300px', md: '450px' },
  onError = null,
}) => {
  const theme = useTheme();
  const [imageLoaded, setImageLoaded] = useState(true);

  const handleImageError = (e) => {
    console.warn(`⚠️ Image failed to load: ${src}`);
    setImageLoaded(false);
    if (onError) {
      onError(e);
    }
  };

  const handleImageLoad = () => {
    setImageLoaded(true);
  };

  return (
    <Box
      sx={{
        height,
        background: imageLoaded
          ? 'transparent'
          : `linear-gradient(135deg, ${theme.palette.primary.main}25 0%, ${theme.palette.secondary.main}15 100%)`,
        border: `1px solid ${alpha(theme.palette.divider, 0.5)}`,
        borderRadius: '0px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      <Box
        component="img"
        src={src}
        alt={alt}
        onError={handleImageError}
        onLoad={handleImageLoad}
        sx={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          objectPosition: 'center',
          display: imageLoaded ? 'block' : 'none',
        }}
      />
    </Box>
  );
};

export default ImagePlaceholder;
