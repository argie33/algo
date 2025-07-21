import React from 'react';

export const Progress = React.forwardRef(({ className, value, ...props }, ref) => {
  return (
    <div 
      ref={ref} 
      className={className || "w-full bg-gray-200 rounded-full h-2"}
      data-variant={value !== undefined ? "determinate" : "indeterminate"}
      data-value={value}
      {...props} 
    >
      <div 
        className="bg-blue-600 h-2 rounded-full transition-all duration-300"
        style={{ width: `${value || 0}%` }}
      />
    </div>
  );
});
Progress.displayName = "Progress";