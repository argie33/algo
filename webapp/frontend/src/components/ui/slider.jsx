import React from 'react';

export const Slider = React.forwardRef(({ className, value, onValueChange, ...props }, ref) => {
  return (
    <MuiSlider 
      ref={ref} 
      className={className} 
      value={value}
      onChange={(e, newValue) => onValueChange && onValueChange(newValue)}
      {...props} 
    />
  );
});
Slider.displayName = "Slider";