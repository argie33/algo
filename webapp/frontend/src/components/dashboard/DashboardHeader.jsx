import React from 'react';

export const DashboardHeader = ({ user, title = 'Dashboard', actions, ...props }) => {
  return (
    <header className="dashboard-header" style={{ padding: '1rem', borderBottom: '1px solid #e0e0e0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }} {...props}>
      <div>
        <h1 style={{ margin: 0, fontSize: '1.5rem' }}>{title}</h1>
        {user && <p style={{ margin: 0, color: '#666' }}>Welcome back, {user.firstName}</p>}
      </div>
      {actions && <div className="dashboard-actions">{actions}</div>}
    </header>
  );
};