import React from 'react';
import { Card as MuiCard, CardHeader as MuiCardHeader, CardContent as MuiCardContent } from '@mui/material';

const Card = React.forwardRef(({ className, ...props }, ref) => (
  <MuiCard ref={ref} className={className} {...props} />
));
Card.displayName = "Card";

const CardHeader = React.forwardRef(({ className, ...props }, ref) => (
  <MuiCardHeader ref={ref} className={className} {...props} />
));
CardHeader.displayName = "CardHeader";

const CardTitle = React.forwardRef(({ className, children, ...props }, ref) => (
  <div  ref={ref} variant="h6" component="div" className={className} {...props}>
    {children}
  </div>
));
CardTitle.displayName = "CardTitle";

const CardDescription = React.forwardRef(({ className, children, ...props }, ref) => (
  <div  ref={ref} variant="body2" color="text.secondary" className={className} {...props}>
    {children}
  </div>
));
CardDescription.displayName = "CardDescription";

const CardContent = React.forwardRef(({ className, ...props }, ref) => (
  <MuiCardContent ref={ref} className={className} {...props} />
));
CardContent.displayName = "CardContent";

const CardFooter = React.forwardRef(({ className, ...props }, ref) => (
  <div ref={ref} className={className} style={{ padding: '16px' }} {...props} />
));
CardFooter.displayName = "CardFooter";

export default Card;
export { CardHeader, CardTitle, CardDescription, CardContent, CardFooter };