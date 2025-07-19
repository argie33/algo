import React from 'react';
import { Treemap, ResponsiveContainer, Tooltip } from 'recharts';

export const TreemapChart = ({ data = [], width = '100%', height = 300, ...props }) => {
  return (
    <ResponsiveContainer width={width} height={height}>
      <Treemap
        data={data}
        dataKey="value"
        ratio={4/3}
        stroke="#fff"
        fill="#8884d8"
        {...props}
      >
        <Tooltip />
      </Treemap>
    </ResponsiveContainer>
  );
};