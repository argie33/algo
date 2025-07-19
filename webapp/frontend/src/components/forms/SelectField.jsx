import React from 'react';

export const SelectField = ({ children, ...props }) => {
  return (
    <div className="selectfield" {...props}>
      SelectField Component - {children}
    </div>
  );
};
