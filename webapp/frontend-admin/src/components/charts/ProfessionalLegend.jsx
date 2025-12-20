/**
 * Professional Financial Chart Legend
 * Clean, organized, with filtering capabilities
 *
 * Features:
 * - Multi-column layout
 * - Toggle visibility on click
 * - Color indicators
 * - Icons for different data types
 * - Responsive design
 * - Accessibility support
 */

import React, { useState } from 'react';
import {
  Box,
  Typography,
  useTheme,
  useMediaQuery,
  Chip,
  _Grid,
  Tooltip,
} from '@mui/material';
import {
  _ShowChart,
  _TrendingUp,
  _Visibility,
  _VisibilityOff,
} from '@mui/icons-material';

const ProfessionalLegend = ({
  items = [],
  onItemToggle = null,
  orientation = 'vertical',
  columns = 2,
  sx = {},
}) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const [visibleItems, setVisibleItems] = useState(
    new Set(items.map((item) => item.dataKey || item.name))
  );

  const handleItemClick = (dataKey) => {
    const newVisible = new Set(visibleItems);
    if (newVisible.has(dataKey)) {
      newVisible.delete(dataKey);
    } else {
      newVisible.add(dataKey);
    }
    setVisibleItems(newVisible);

    // Notify parent component
    if (onItemToggle) {
      onItemToggle(dataKey, !visibleItems.has(dataKey));
    }
  };

  const containerSx =
    orientation === 'horizontal'
      ? {
        display: 'flex',
        flexWrap: 'wrap',
        gap: 2,
        justifyContent: 'flex-start',
        ...sx,
      }
      : {
        display: 'grid',
        gridTemplateColumns: isMobile ? '1fr' : `repeat(${columns}, 1fr)`,
        gap: 2,
        ...sx,
      };

  return (
    <Box sx={containerSx}>
      {items.map((item) => {
        const isVisible = visibleItems.has(item.dataKey || item.name);
        const color = item.color || item.fill || '#3B82F6';
        const name = item.name || item.dataKey || '';

        return (
          <Tooltip
            key={item.dataKey || item.name}
            title="Click to toggle visibility"
            placement="top"
          >
            <Chip
              icon={
                <Box
                  sx={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    backgroundColor: color,
                    mr: 1,
                  }}
                />
              }
              label={
                <Typography
                  variant="caption"
                  sx={{
                    fontWeight: 500,
                    fontSize: '12px',
                  }}
                >
                  {name}
                </Typography>
              }
              onClick={() => handleItemClick(item.dataKey || item.name)}
              onDelete={null}
              sx={{
                backgroundColor: isVisible
                  ? theme.palette.mode === 'dark'
                    ? 'rgba(255, 255, 255, 0.1)'
                    : 'rgba(59, 130, 246, 0.05)'
                  : theme.palette.mode === 'dark'
                    ? 'rgba(255, 255, 255, 0.05)'
                    : 'rgba(0, 0, 0, 0.02)',
                border: isVisible
                  ? `1px solid ${color}33`
                  : `1px solid ${theme.palette.divider}`,
                opacity: isVisible ? 1 : 0.5,
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                '&:hover': {
                  backgroundColor: isVisible
                    ? theme.palette.mode === 'dark'
                      ? 'rgba(255, 255, 255, 0.15)'
                      : 'rgba(59, 130, 246, 0.1)'
                    : theme.palette.mode === 'dark'
                      ? 'rgba(255, 255, 255, 0.08)'
                      : 'rgba(0, 0, 0, 0.04)',
                  borderColor: color,
                },
              }}
            />
          </Tooltip>
        );
      })}
    </Box>
  );
};

export default ProfessionalLegend;
