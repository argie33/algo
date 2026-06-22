import { useApiQuery } from "../hooks/useApiQuery";
import {
  Card,
  CardContent,
  Typography,
  CircularProgress,
  Alert,
} from "@mui/material";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import api from "../services/api";
import { formatCurrency } from "../utils/formatters";
import { getChartContainerStyle } from "../utils/chartContainer";

export default function PETrendChart({ sectorName, industryName }) {
  const name = sectorName || industryName;
  const endpoint = sectorName
    ? `sectors/${sectorName}/trend`
    : `industries/${industryName}/trend`;

  const {
    data,
    loading: isLoading,
    error,
  } = useApiQuery(["trend", name], () => api.get(`/api/${endpoint}?days=365`), {
    enabled: !!name,
  });

  if (!name) return null;
  if (isLoading) return <CircularProgress size={30} />;

  const trendData = Array.isArray(data?.trendData) ? data.trendData : [];
  if (error || trendData.length === 0) {
    return <Alert severity="info">No trend data available</Alert>;
  }

  const chartData = trendData
    .map((item) => ({
      date: item.date ? new Date(item.date).toLocaleDateString() : "—",
      avgPrice: item.avgPrice !== null ? parseFloat(item.avgPrice) : null,
      stockCount: item.stockCount || 0,
    }))
    .filter((item) => item.avgPrice !== null);

  return (
    <Card sx={{ mt: 2 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Avg Price Trend (1 Year)
        </Typography>

        <div style={getChartContainerStyle("default")}>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart
              data={chartData}
              margin={{ top: 20, right: 30, left: 80, bottom: 80 }}
            >
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                angle={-45}
                textAnchor="end"
                height={80}
                tick={{ fontSize: 12 }}
                interval={Math.max(0, Math.floor(chartData.length / 8))}
              />
              <YAxis
                label={{
                  value: "Avg Price ($)",
                  angle: -90,
                  position: "insideLeft",
                  offset: 10,
                }}
                width={70}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "rgba(0,0,0,0.9)",
                  border: "1px solid #666",
                  borderRadius: 4,
                  color: "#fff",
                }}
                labelStyle={{ color: "#fff" }}
                formatter={(value) =>
                  value != null ? formatCurrency(value) : "N/A"
                }
                cursor={{ stroke: "#888" }}
              />
              <Line
                type="monotone"
                dataKey="avgPrice"
                stroke="#E91E63"
                strokeWidth={3}
                dot={false}
                name="Avg Price"
                isAnimationActive={true}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: "block", mt: 2 }}
        >
          Average price across {name} stocks over the past year
        </Typography>
      </CardContent>
    </Card>
  );
}
