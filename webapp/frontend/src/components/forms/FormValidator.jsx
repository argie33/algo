import React from 'react';

export const FormValidator = ({ children, ...props }) => {
  return (
    <div className="formvalidator" {...props}>
      FormValidator Component - {children}
    </div>
  );
};
