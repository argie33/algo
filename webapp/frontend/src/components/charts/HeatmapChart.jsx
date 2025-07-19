import React from 'react';

export const HeatmapChart = ({ data = [], width = '100%', height = 300, ...props }) => {
  return (
    <div style={{ width, height, display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid #ccc' }}>
      <div>Heatmap Chart - {data.length} items</div>
    </div>
  );
};