import React from 'react';
import { Alert as MuiAlert, AlertTitle as MuiAlertTitle } from '@mui/material';

export const Alert = React.forwardRef(({ className, variant = "info", ...props }, ref) => {
  const severity = variant === "destructive" ? "error" : variant;
  
  return (
    <MuiAlert 
      ref={ref} 
      className={className} 
      severity={severity}
      {...props} 
    />
  );
});
Alert.displayName = "Alert";

export const AlertDescription = React.forwardRef(({ className, ...props }, ref) => (
  <div ref={ref} className={className} {...props} />
));
AlertDescription.displayName = "AlertDescription";

export const AlertTitle = React.forwardRef(({ className, ...props }, ref) => (
  <MuiAlertTitle ref={ref} className={className} {...props} />
));
AlertTitle.displayName = "AlertTitle";