import React from 'react';
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export const BubbleChart = ({ data = [], width = '100%', height = 300, ...props }) => {
  return (
    <ResponsiveContainer width={width} height={height}>
      <ScatterChart data={data} {...props}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="x" />
        <YAxis dataKey="y" />
        <Tooltip />
        <Scatter dataKey="z" fill="#8884d8" />
      </ScatterChart>
    </ResponsiveContainer>
  );
};