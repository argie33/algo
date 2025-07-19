import React from 'react';

export const FormWizard = ({ children, ...props }) => {
  return (
    <div className="formwizard" {...props}>
      FormWizard Component - {children}
    </div>
  );
};
