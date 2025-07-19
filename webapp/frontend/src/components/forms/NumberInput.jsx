import React from 'react';

export const NumberInput = ({ children, ...props }) => {
  return (
    <div className="numberinput" {...props}>
      NumberInput Component - {children}
    </div>
  );
};
