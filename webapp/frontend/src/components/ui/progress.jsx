import React from 'react';
import { LinearProgress } from '@mui/material';

export const Progress = React.forwardRef(({ className, value, ...props }, ref) => {
  return (
    <LinearProgress 
      ref={ref} 
      className={className} 
      variant={value !== undefined ? "determinate" : "indeterminate"}
      value={value}
      {...props} 
    />
  );
});
Progress.displayName = "Progress";