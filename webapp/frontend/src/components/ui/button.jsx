import React from 'react';
import { Button as MuiButton } from '@mui/material';

const Button = React.forwardRef(({ className, variant = "contained", size = "medium", ...props }, ref) => {
  const muiVariant = variant === "default" ? "contained" : variant;
  
  return (
    <MuiButton 
      ref={ref} 
      className={className} 
      variant={muiVariant}
      size={size}
      {...props} 
    />
  );
});
Button.displayName = "Button";

export default Button;