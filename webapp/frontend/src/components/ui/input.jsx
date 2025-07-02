import React from 'react';
import { TextField } from '@mui/material';

export const Input = React.forwardRef(({ className, type = "text", ...props }, ref) => {
  return (
    <TextField 
      ref={ref} 
      className={className} 
      type={type}
      variant="outlined"
      size="small"
      {...props} 
    />
  );
});
Input.displayName = "Input";