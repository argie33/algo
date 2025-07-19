import React from 'react';

export const DatePicker = ({ children, ...props }) => {
  return (
    <div className="datepicker" {...props}>
      DatePicker Component - {children}
    </div>
  );
};
