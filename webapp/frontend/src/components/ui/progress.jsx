import React from 'react';

export const Progress = React.forwardRef(({ className, value, ...props }, ref) => {
  return (
    <div className="w-full bg-gray-200 rounded-full h-2" 
      ref={ref} 
      className={className} 
      variant={value !== undefined ? "determinate" : "indeterminate"}
      value={value}
      {...props} 
    />
  );
});
Progress.displayName = "Progress";