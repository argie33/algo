import React from 'react';

export const FileUpload = ({ children, ...props }) => {
  return (
    <div className="fileupload" {...props}>
      FileUpload Component - {children}
    </div>
  );
};
