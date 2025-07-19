import React from 'react';

export const SearchableSelect = ({ children, ...props }) => {
  return (
    <div className="searchableselect" {...props}>
      SearchableSelect Component - {children}
    </div>
  );
};
