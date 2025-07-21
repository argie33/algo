import React from 'react';
import { Tabs as MuiTabs } from '@mui/material';

export const Tabs = React.forwardRef(({ className, value, onValueChange, children, ...props }, ref) => {
  return (
    <div ref={ref} className={className} {...props}>
      {children}
    </div>
  );
});
Tabs.displayName = "Tabs";

export const TabsList = React.forwardRef(({ className, children, ...props }, ref) => (
  <MuiTabs ref={ref} className={className} {...props}>
    {children}
  </MuiTabs>
));
TabsList.displayName = "TabsList";

export const TabsTrigger = React.forwardRef(({ className, value, children, ...props }, ref) => (
  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" ref={ref} className={className} value={value} label={children} {...props} />
));
TabsTrigger.displayName = "TabsTrigger";

export const TabsContent = React.forwardRef(({ className, value, children, ...props }, ref) => (
  <div  ref={ref} className={className} {...props}>
    {children}
  </div>
));
TabsContent.displayName = "TabsContent";