import React from 'react';

export const Badge = React.forwardRef(({ className, variant = "default", children, ...props }, ref) => {
  const muiVariant = variant === "destructive" ? "filled" : "outlined";
  const color = variant === "destructive" ? "error" : "default";
  
  return (
    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
      ref={ref} 
      className={className} 
      variant={muiVariant}
      color={color}
      label={children}
      size="small"
      {...props} 
    />
  );
});
Badge.displayName = "Badge";