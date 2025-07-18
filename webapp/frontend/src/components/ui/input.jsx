import React from 'react';

export const Input = React.forwardRef(({ className, type = "text", ...props }, ref) => {
  return (
    <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" 
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