import React from 'react';

export const CheckboxField = ({ children, ...props }) => {
  return (
    <div className="checkboxfield" {...props}>
      CheckboxField Component - {children}
    </div>
  );
};
