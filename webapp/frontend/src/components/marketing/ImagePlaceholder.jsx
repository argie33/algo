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
  // Use gradient for placeholder src or if src is empty
  const isPlaceholder = !src || src === 'gradient';
  const [imageLoaded, setImageLoaded] = useState(!isPlaceholder);

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
          : `linear-gradient(135deg, ${theme.palette.primary.main}20 0%, ${theme.palette.secondary.main}10 100%)`,
        border: `2px solid ${alpha(theme.palette.primary.main, 0.3)}`,
        borderRadius: '2px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      {!isPlaceholder && (
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
      )}
      {!imageLoaded && !isPlaceholder && (
        <Box sx={{
          textAlign: 'center',
          color: theme.palette.text.secondary,
          fontSize: '1rem',
          fontWeight: 500,
          padding: '20px',
        }}>
          {alt}
        </Box>
      )}
    </Box>
  );
};

export default ImagePlaceholder;
