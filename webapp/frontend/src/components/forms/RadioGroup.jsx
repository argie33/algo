import React from 'react';

export const RadioGroup = ({ children, ...props }) => {
  return (
    <div className="radiogroup" {...props}>
      RadioGroup Component - {children}
    </div>
  );
};
