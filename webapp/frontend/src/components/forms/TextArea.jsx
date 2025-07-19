import React from 'react';

export const TextArea = ({ children, ...props }) => {
  return (
    <div className="textarea" {...props}>
      TextArea Component - {children}
    </div>
  );
};
