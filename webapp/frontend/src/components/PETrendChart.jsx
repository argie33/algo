import { useQuery } from "@tanstack/react-query";
import { Box, Card, CardContent, Typography, CircularProgress, Alert } from "@mui/material";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import api from "../services/api";
import { formatCurrency } from "../utils/formatters";
import { getChartContainerStyle } from "../utils/chartContainer";

export default function PETrendChart({ sectorName, industryName }) {
  const name = sectorName || industryName;
  const endpoint = sectorName ? `sectors/${sectorName}/trend` : `industries/${industryName}/trend`;

  const { data, isLoading, error } = useQuery({
    queryKey: ["trend", name],
    queryFn: async () => {
      const response = await api.get(`/api/${endpoint}?days=365`);
      return response.data.data;
    },
    enabled: !!name,
  });

  if (!name) return null;
  if (isLoading) return <CircularProgress size={30} />;

  const trendData = data?.trendData || [];
  if (error || trendData.length === 0) {
    return <Alert severity="info">No trend data available</Alert>;
  }

  const chartData = trendData.map(item => ({
    date: new Date(item.date).toLocaleDateString(),
    avgPrice: item.avgPrice !== null ? parseFloat(item.avgPrice) : null,
    stockCount: item.stockCount || 0,
  })).filter(item => item.avgPrice !== null);

  return (
    <Card sx={{ mt: 2 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Avg Price Trend (1 Year)
        </Typography>

        <div style={getChartContainerStyle('default')}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" angle={-45} textAnchor="end" height={60} />
              <YAxis label={{ value: "Avg Price ($)", angle: -90, position: "insideLeft" }} />
              <Tooltip
                contentStyle={{ backgroundColor: "rgba(0,0,0,0.8)", border: "1px solid #666", borderRadius: 4 }}
                labelStyle={{ color: "#fff" }}
                formatter={(value) => value != null ? formatCurrency(value) : "N/A"}
              />
              <Line type="monotone" dataKey="avgPrice" stroke="#E91E63" strokeWidth={3} dot={false} name="Avg Price" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 2 }}>
          Average price across {name} stocks over the past year
        </Typography>
      </CardContent>
    </Card>
  );
}

