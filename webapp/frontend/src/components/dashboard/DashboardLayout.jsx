import React from 'react';

export const DashboardLayout = ({ children, sidebar, header, ...props }) => {
  return (
    <div className="dashboard-layout" style={{ display: 'grid', gridTemplateColumns: '250px 1fr', minHeight: '100vh' }} {...props}>
      {sidebar && <aside className="dashboard-sidebar">{sidebar}</aside>}
      <main className="dashboard-main">
        {header && <header className="dashboard-header">{header}</header>}
        <div className="dashboard-content">{children}</div>
      </main>
    </div>
  );
};