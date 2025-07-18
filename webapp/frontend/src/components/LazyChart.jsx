import React, { Suspense, lazy } from 'react';

const ChartLoader = ({ height = 200 }) => (
  <div  
    sx={{ 
      display: 'flex', 
      justifyContent: 'center', 
      alignItems: 'center', 
      height: height,
      backgroundColor: 'grey.50',
      borderRadius: 1
    }}
  >
    <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={24} />
  </div>
);

// This is a completely wrong approach - just export normal recharts for now
export {
  LineChart,
  AreaChart, 
  BarChart,
  PieChart,
  Line,
  Area,
  Bar,
  Pie,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell
} from 'recharts';

export default ChartLoader;