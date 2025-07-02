import React from 'react';
import { Card as MuiCard, CardContent as MuiCardContent, CardHeader as MuiCardHeader, Typography } from '@mui/material';

export const Card = React.forwardRef(({ className, ...props }, ref) => (
  <MuiCard ref={ref} className={className} {...props} />
));
Card.displayName = "Card";

export const CardHeader = React.forwardRef(({ className, ...props }, ref) => (
  <MuiCardHeader ref={ref} className={className} {...props} />
));
CardHeader.displayName = "CardHeader";

export const CardTitle = React.forwardRef(({ className, children, ...props }, ref) => (
  <Typography ref={ref} variant="h6" component="div" className={className} {...props}>
    {children}
  </Typography>
));
CardTitle.displayName = "CardTitle";

export const CardDescription = React.forwardRef(({ className, children, ...props }, ref) => (
  <Typography ref={ref} variant="body2" color="text.secondary" className={className} {...props}>
    {children}
  </Typography>
));
CardDescription.displayName = "CardDescription";

export const CardContent = React.forwardRef(({ className, ...props }, ref) => (
  <MuiCardContent ref={ref} className={className} {...props} />
));
CardContent.displayName = "CardContent";

export const CardFooter = React.forwardRef(({ className, ...props }, ref) => (
  <div ref={ref} className={className} style={{ padding: '16px' }} {...props} />
));
CardFooter.displayName = "CardFooter";