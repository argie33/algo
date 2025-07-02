import React from 'react';
import { Select as MuiSelect, MenuItem, FormControl, InputLabel } from '@mui/material';

export const Select = React.forwardRef(({ className, children, value, onValueChange, ...props }, ref) => {
  return (
    <FormControl className={className} size="small">
      <MuiSelect 
        ref={ref} 
        value={value || ''}
        onChange={(e) => onValueChange && onValueChange(e.target.value)}
        {...props}
      >
        {children}
      </MuiSelect>
    </FormControl>
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
  <MenuItem ref={ref} className={className} value={value} {...props}>
    {children}
  </MenuItem>
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