import React from 'react';
import { Select as MuiSelect } from '@mui/material';

export const Select = React.forwardRef(({ className, children, value, onValueChange, ...props }, ref) => {
  return (
    <div className={`mb-4 ${className || ''}`}>
      <MuiSelect size="small" 
        ref={ref} 
        value={value || ''}
        onChange={(e) => onValueChange && onValueChange(e.target.value)}
        {...props}
      >
        {children}
      </MuiSelect>
    </div>
  );
});
Select.displayName = "Select";

export const SelectContent = React.forwardRef(({ className, children, ...props }, ref) => (
  <div ref={ref} className={className} {...props}>
    {children}
  </div>
));
SelectContent.displayName = "SelectContent";

export const SelectItem = React.forwardRef(({ className, value, children, ...props }, ref) => (
  <option  ref={ref} className={className} value={value} {...props}>
    {children}
  </option>
));
SelectItem.displayName = "SelectItem";

export const SelectTrigger = React.forwardRef(({ className, children, ...props }, ref) => (
  <div ref={ref} className={className} {...props}>
    {children}
  </div>
));
SelectTrigger.displayName = "SelectTrigger";

export const SelectValue = React.forwardRef(({ className, placeholder, ...props }, ref) => (
  <span ref={ref} className={className} {...props}>
    {placeholder}
  </span>
));
SelectValue.displayName = "SelectValue";