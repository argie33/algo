import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  Container,
  Grid,
  LinearProgress,
  Typography,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  ExpandMore,
  ShowChart,
  BarChart,
} from "@mui/icons-material";
import {
  BarChart as RechartsBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
  Tooltip,
  LineChart,
  ComposedChart,
  Line,
} from "recharts";
import api from "../services/api";
import {
  formatPercentage,
  getChangeColor,
} from "../utils/formatters";

// Helper component for sector momentum chart
const SectorMomentumChart = ({ sector, aggregateToWeekly }) => {
  const { data: trendData } = useQuery({
    queryKey: [`momentum-trend-sector`, sector.sector_name || sector.sector],
    queryFn: async () => {
      try {
        const response = await api.get(
          `/api/sectors/trend/sector/${encodeURIComponent(sector.sector_name || sector.sector)}`
        );
        return response.data?.trendData || [];
      } catch { return []; }
    },
    staleTime: 300000,
    enabled: !!(sector.sector_name || sector.sector),
    retry: false,
  });

  let momentumData = (trendData || []).map(row => ({
    date: row.label || row.date,
    momentum: parseFloat(row.momentumScore || row.momentum || 0)
  }));

  if (momentumData.length > 0 && momentumData[0].date) {
    const threeMonthsAgo = new Date();
    threeMonthsAgo.setMonth(threeMonthsAgo.getMonth() - 3);
    momentumData = momentumData.filter(row => {
      try {
        const rowDate = new Date(row.date);
        return rowDate >= threeMonthsAgo;
      } catch { return true; }
    });
    momentumData = aggregateToWeekly(momentumData);
  }

  return (
    <Box sx={{ borderTop: "1px solid", borderColor: "divider", pt: 2, minHeight: 300 }}>
      <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 2 }}>
        ⚡ Momentum Score
      </Typography>
      {momentumData.length > 0 ? (
        <Box sx={{ width: "100%", height: 250 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={momentumData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" fontSize={12} />
              <YAxis />
              <Tooltip
                formatter={(value) => formatPercentage(value)}
                labelFormatter={(label) => `${label}`}
              />
              <Line
                type="monotone"
                dataKey="momentum"
                stroke="#ff9800"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </Box>
      ) : (
        <Typography variant="caption" color="text.secondary">Loading momentum data...</Typography>
      )}
    </Box>
  );
};

// Helper component for industry momentum chart
const IndustryMomentumChart = ({ industry, aggregateToWeekly }) => {
  const { data: trendData } = useQuery({
    queryKey: [`momentum-trend-industry`, industry.industry],
    queryFn: async () => {
      try {
        const response = await api.get(
          `/api/sectors/trend/industry/${encodeURIComponent(industry.industry)}`
        );
        return response.data?.trendData || [];
      } catch { return []; }
    },
    staleTime: 300000,
    enabled: !!industry.industry,
    retry: false,
  });

  let momentumData = (trendData || []).map(row => ({
    date: row.label || row.date,
    momentum: parseFloat(row.momentumScore || row.momentum || 0)
  }));

  if (momentumData.length > 0 && momentumData[0].date) {
    const threeMonthsAgo = new Date();
    threeMonthsAgo.setMonth(threeMonthsAgo.getMonth() - 3);
    momentumData = momentumData.filter(row => {
      try {
        const rowDate = new Date(row.date);
        return rowDate >= threeMonthsAgo;
      } catch { return true; }
    });
    momentumData = aggregateToWeekly(momentumData);
  }

  return (
    <Box sx={{ borderTop: "1px solid", borderColor: "divider", pt: 2, mt: 2, minHeight: 300 }}>
      <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 2 }}>
        ⚡ Momentum Score
      </Typography>
      {momentumData.length > 0 ? (
        <Box sx={{ width: "100%", height: 250 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={momentumData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" fontSize={12} />
              <YAxis />
              <Tooltip
                formatter={(value) => formatPercentage(value)}
                labelFormatter={(label) => `${label}`}
              />
              <Line
                type="monotone"
                dataKey="momentum"
                stroke="#ff9800"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </Box>
      ) : (
        <Typography variant="caption" color="text.secondary">Loading momentum data...</Typography>
      )}
    </Box>
  );
};

const SectorAnalysis = () => {
  const [lastUpdate, setLastUpdate] = useState(null);

  // Vibrant color palette for sectors & industries (no gray defaults - only 1 gray for unknowns)
  const vibrantColors = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8",
    "#F7DC6F", "#BB8FCE", "#85C1E2", "#F8B88B", "#ABEBC6",
    "#F1948A", "#A3E4D7", "#F5B041", "#A9DFBF", "#F8BBAD",
    "#B7DEE8", "#F9E79F", "#D7BDE2", "#AED6F1", "#F5CBA7",
  ];

  const sectorColors = {
    "Technology": "#2196F3",
    "Healthcare": "#4CAF50",
    "Financials": "#FF9800",
    "Consumer Discretionary": "#9C27B0",
    "Consumer Staples": "#795548",
    "Energy": "#FF5722",
    "Industrials": "#607D8B",
    "Materials": "#8BC34A",
    "Utilities": "#FFC107",
    "Real Estate": "#E91E63",
    "Communication Services": "#00BCD4",
  };

  // Function to get vibrant color for unknown sectors/industries
  const getVibrantColor = (index) => {
    return vibrantColors[index % vibrantColors.length];
  };

  // Only use gray as last resort fallback
  const getColorForSector = (sectorName) => {
    return sectorColors[sectorName] || "#999"; // Only gray for truly unknown
  };

  // Comprehensive industry-to-sector mapping
  // This mapping ensures ALL industries are correctly assigned to their sectors
  // regardless of how the API returns sector assignments
  const industryToSectorMapping = {
    // Technology (40+ industries)
    "Software": "Technology",
    "Software Infrastructure": "Technology",
    "Software Consulting": "Technology",
    "Information Services": "Technology",
    "IT Services & Consulting": "Technology",
    "Data Processing & Outsourced Services": "Technology",
    "Application Software": "Technology",
    "Systems Software": "Technology",
    "Internet Services & Infrastructure": "Technology",
    "Web Services": "Technology",
    "IT Consulting & Services": "Technology",
    "Semiconductors": "Technology",
    "Semiconductor Equipment": "Technology",
    "Electronic Components": "Technology",
    "Electronics Manufacturing Services": "Technology",
    "Computers & Peripherals": "Technology",
    "Computer Hardware": "Technology",
    "Computer & Office Equipment": "Technology",
    "Networking & Communication Devices": "Technology",
    "Communications Equipment": "Technology",
    "Technology Hardware": "Technology",
    "Tech & Telecom Equipment": "Technology",
    "Home & Office Furnishings": "Technology",

    // Healthcare (30+ industries)
    "Pharmaceuticals": "Healthcare",
    "Pharmaceutical Manufacturers": "Healthcare",
    "Generic Pharmaceuticals": "Healthcare",
    "Biotechnology": "Healthcare",
    "Biotech & Pharmaceuticals": "Healthcare",
    "Diagnostic Substances": "Healthcare",
    "Medical Devices": "Healthcare",
    "Medical Appliances": "Healthcare",
    "Medical Instruments & Supplies": "Healthcare",
    "Medical Devices & Supplies": "Healthcare",
    "Healthcare Services": "Healthcare",
    "Healthcare Providers": "Healthcare",
    "Hospitals": "Healthcare",
    "Nursing Homes": "Healthcare",
    "Senior Housing": "Healthcare",
    "Behavioral Health": "Healthcare",
    "Medical Facilities": "Healthcare",
    "Drug Retailers": "Healthcare",
    "Pharmacy": "Healthcare",
    "Health & Fitness Services": "Healthcare",

    // Financials (25+ industries)
    "Banks": "Financials",
    "Commercial Banks": "Financials",
    "Community Banks": "Financials",
    "Regional Banks": "Financials",
    "Diversified Banks": "Financials",
    "Investment Banking": "Financials",
    "Financial Services": "Financials",
    "Financial Exchanges": "Financials",
    "Financial Data & Stock Exchanges": "Financials",
    "Capital Markets": "Financials",
    "Asset Management": "Financials",
    "Investment Management": "Financials",
    "Investment Services": "Financials",
    "Credit Agencies": "Financials",
    "Insurance": "Financials",
    "Accident & Health Insurance": "Financials",
    "Life Insurance": "Financials",
    "Property & Casualty Insurance": "Financials",
    "Insurance Brokerage": "Financials",
    "Insurance Companies": "Financials",

    // Consumer Discretionary (30+ industries)
    "Retail - Specialty": "Consumer Discretionary",
    "Apparel Retail": "Consumer Discretionary",
    "Apparel Manufacturing": "Consumer Discretionary",
    "Apparel Stores": "Consumer Discretionary",
    "Footwear": "Consumer Discretionary",
    "Shoes": "Consumer Discretionary",
    "Luxury Goods": "Consumer Discretionary",
    "Jewelry & Watches": "Consumer Discretionary",
    "Department Stores": "Consumer Discretionary",
    "Home Improvement Retail": "Consumer Discretionary",
    "Home Furnishings": "Consumer Discretionary",
    "Furniture": "Consumer Discretionary",
    "Office Furniture": "Consumer Discretionary",
    "Sporting Goods": "Consumer Discretionary",
    "Toy & Game Retailers": "Consumer Discretionary",
    "Toys": "Consumer Discretionary",
    "Restaurants": "Consumer Discretionary",
    "Hotels & Resorts": "Consumer Discretionary",
    "Lodging": "Consumer Discretionary",
    "Casinos & Gambling": "Consumer Discretionary",
    "Entertainment Venues": "Consumer Discretionary",
    "Recreational Services": "Consumer Discretionary",
    "Automotive": "Consumer Discretionary",
    "Auto Parts & Equipment": "Consumer Discretionary",
    "Auto Parts Suppliers": "Consumer Discretionary",
    "Automotive OEM": "Consumer Discretionary",
    "Autos": "Consumer Discretionary",
    "Tires & Rubber": "Consumer Discretionary",

    // Consumer Staples (20+ industries)
    "Beverages": "Consumer Staples",
    "Beer & Liquor": "Consumer Staples",
    "Beverage - Non-Alcoholic": "Consumer Staples",
    "Soft Drinks": "Consumer Staples",
    "Packaged Foods": "Consumer Staples",
    "Food Manufacturing": "Consumer Staples",
    "Grocery Stores": "Consumer Staples",
    "Food Distribution": "Consumer Staples",
    "Food Retailers": "Consumer Staples",
    "Household Products": "Consumer Staples",
    "Cleaning Products": "Consumer Staples",
    "Personal Care": "Consumer Staples",
    "Cosmetics": "Consumer Staples",
    "Health & Personal Care": "Consumer Staples",
    "Hypermarkets & Super Centers": "Consumer Staples",
    "Discount Variety Retailers": "Consumer Staples",
    "Wholesale Clubs": "Consumer Staples",
    "Tobacco": "Consumer Staples",
    "Cigarettes": "Consumer Staples",

    // Energy (15+ industries)
    "Oil & Gas": "Energy",
    "Oil & Gas - Integrated": "Energy",
    "Oil & Gas - E&P": "Energy",
    "Oil & Gas Exploration & Production": "Energy",
    "Oil & Gas Refining & Marketing": "Energy",
    "Oil & Gas Services": "Energy",
    "Oil & Gas Equipment & Services": "Energy",
    "Pipeline": "Energy",
    "Renewable Energy": "Energy",
    "Solar": "Energy",
    "Wind Energy": "Energy",
    "Coal": "Energy",
    "Uranium": "Energy",

    // Industrials (35+ industries)
    "Aerospace": "Industrials",
    "Aerospace & Defense": "Industrials",
    "Defense": "Industrials",
    "Machinery": "Industrials",
    "Industrial Machinery": "Industrials",
    "Specialized Machinery": "Industrials",
    "Manufacturing": "Industrials",
    "Diversified Manufacturers": "Industrials",
    "Electrical Equipment": "Industrials",
    "Electrical Components": "Industrials",
    "Electrical Machinery": "Industrials",
    "Appliances": "Industrials",
    "Small Appliances": "Industrials",
    "Containers & Packaging": "Industrials",
    "Metal & Glass Containers": "Industrials",
    "Paper Packaging": "Industrials",
    "Trucks": "Industrials",
    "Commercial Vehicles": "Industrials",
    "Building Products": "Industrials",
    "Heavy Equipment": "Industrials",
    "Construction Equipment": "Industrials",
    "Waste Management": "Industrials",
    "Environmental Services": "Industrials",
    "Shipping Services": "Industrials",
    "Marine": "Industrials",
    "Rail Transportation": "Industrials",
    "Airlines": "Industrials",
    "Transportation": "Industrials",
    "Logistics": "Industrials",
    "Delivery Services": "Industrials",
    "Trucking": "Industrials",
    "Construction": "Industrials",
    "Construction & Building": "Industrials",
    "Mining": "Industrials",

    // Materials (20+ industries)
    "Chemicals": "Materials",
    "Chemical Manufacturing": "Materials",
    "Specialty Chemicals": "Materials",
    "Agricultural Chemicals": "Materials",
    "Metals & Mining": "Materials",
    "Steel": "Materials",
    "Aluminum": "Materials",
    "Copper": "Materials",
    "Gold": "Materials",
    "Silver": "Materials",
    "Precious Metals": "Materials",
    "Paper & Forest Products": "Materials",
    "Paper Products": "Materials",
    "Lumber & Wood Products": "Materials",
    "Forestry": "Materials",
    "Cement": "Materials",
    "Building Materials": "Materials",
    "Glass": "Materials",

    // Utilities (10+ industries)
    "Utilities": "Utilities",
    "Electric Utilities": "Utilities",
    "Gas Utilities": "Utilities",
    "Water Utilities": "Utilities",
    "Multiline Utilities": "Utilities",
    "Utility Services": "Utilities",

    // Real Estate (15+ industries)
    "Real Estate": "Real Estate",
    "Real Estate Services": "Real Estate",
    "REITs": "Real Estate",
    "REIT": "Real Estate",
    "REIT - Retail": "Real Estate",
    "REIT - Residential": "Real Estate",
    "REIT - Office": "Real Estate",
    "REIT - Industrial": "Real Estate",
    "REIT - Hotel": "Real Estate",
    "REIT - Healthcare": "Real Estate",
    "Real Estate Development": "Real Estate",
    "Land Development": "Real Estate",
    "Property Management": "Real Estate",
    "Residential Real Estate": "Real Estate",
    "Commercial Real Estate": "Real Estate",

    // Communication Services (20+ industries)
    "Advertising": "Communication Services",
    "Advertising Agencies": "Communication Services",
    "Media": "Communication Services",
    "Media & Entertainment": "Communication Services",
    "Broadcast Media": "Communication Services",
    "Television": "Communication Services",
    "Radio": "Communication Services",
    "Cable & Satellite": "Communication Services",
    "Publishing": "Communication Services",
    "News Publishers": "Communication Services",
    "Telecom": "Communication Services",
    "Telecommunications": "Communication Services",
    "Telecom Services": "Communication Services",
    "Wireless": "Communication Services",
    "Internet Service Providers": "Communication Services",
    "Internet & Cable Services": "Communication Services",
    "Diversified Telecom Services": "Communication Services",
    "Movies & Entertainment": "Communication Services",
    "Interactive Media": "Communication Services",
    "Internet Information Providers": "Communication Services",
    "Internet Services": "Communication Services",
    "Online Entertainment": "Communication Services",
  };

  // Normalize sector names to handle mismatches between APIs
  // Both sectors and industries APIs may use different naming conventions
  const normalizeSectorName = (sectorName) => {
    if (!sectorName) return '';

    const sectorMapping = {
      // Industries API naming variants
      "Basic Materials": "Materials",
      "Consumer Cyclical": "Consumer Discretionary",
      "Consumer Defensive": "Consumer Staples",
      "Financial Services": "Financials",
      // Additional variants that might appear
      "Financials": "Financials",
      "Financials Services": "Financials",
      "Communication Services": "Communication Services",
      "Communications": "Communication Services",
      "Consumer Staples": "Consumer Staples",
      "Consumer Discretionary": "Consumer Discretionary",
      "Energy": "Energy",
      "Healthcare": "Healthcare",
      "Health Care": "Healthcare",
      "Industrials": "Industrials",
      "Technology": "Technology",
      "Tech": "Technology",
      "Utilities": "Utilities",
      "Real Estate": "Real Estate",
      "Realty": "Real Estate",
      "REITs": "Real Estate",
      "Materials": "Materials",
    };

    // Try direct mapping first
    if (sectorMapping[sectorName]) {
      return sectorMapping[sectorName];
    }

    // If not found, return as-is (in case it's already normalized)
    return sectorName;
  };

  // Helper component to render compact trend chart
  const TrendChart = ({ data, width = 100, height = 40 }) => {
    if (!data || data.length < 2) return null;

    return (
      <div style={{ width: `${width}px`, height: `${height}px`, display: "inline-block" }}>
        <LineChart
          width={width}
          height={height}
          data={data}
          margin={{ top: 2, right: 2, bottom: 2, left: 0 }}
        >
          <YAxis
            hide={true}
            reversed={true}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#fff",
              border: "1px solid #ccc",
              borderRadius: "4px",
              padding: "4px",
              fontSize: "11px"
            }}
          />
          <Line
            type="monotone"
            dataKey="rank"
            stroke="#2196F3"
            dot={false}
            strokeWidth={1.5}
            isAnimationActive={false}
          />
        </LineChart>
      </div>
    );
  };

  // Helper function to aggregate daily data into weekly data
  const aggregateToWeekly = (dailyData) => {
    if (!dailyData || dailyData.length === 0) return [];

    // If data doesn't have date field (fallback data), return as-is
    if (!dailyData[0].date) {
      return dailyData;
    }

    const weeklyData = [];
    let currentWeek = null;
    let weekEnd = null;

    for (const row of dailyData) {
      try {
        if (!row.date) continue;

        const rowDate = new Date(row.date);
        if (isNaN(rowDate.getTime())) continue; // Skip invalid dates

        const dayOfWeek = rowDate.getDay();

        // Initialize first week
        if (!currentWeek) {
          currentWeek = new Date(rowDate);
          // Set to start of week (Monday = 1, adjust Sunday = 0)
          const offset = dayOfWeek === 0 ? 6 : dayOfWeek - 1;
          currentWeek.setDate(rowDate.getDate() - offset);
          weekEnd = new Date(currentWeek);
          weekEnd.setDate(weekEnd.getDate() + 6); // End of week (Sunday)
        }

        // Check if we've moved to a new week
        if (rowDate > weekEnd) {
          const offset = dayOfWeek === 0 ? 6 : dayOfWeek - 1;
          currentWeek = new Date(rowDate);
          currentWeek.setDate(rowDate.getDate() - offset);
          weekEnd = new Date(currentWeek);
          weekEnd.setDate(weekEnd.getDate() + 6);
        }

        // Always keep the last data point of the current period
        if (weeklyData.length === 0 || weeklyData[weeklyData.length - 1].weekStart !== currentWeek.toISOString().split('T')[0]) {
          weeklyData.push({
            date: row.date,
            label: row.label,
            rank: row.rank,
            weekStart: currentWeek.toISOString().split('T')[0]
          });
        } else {
          // Update the last entry with the newest data for this week
          weeklyData[weeklyData.length - 1] = {
            date: row.date,
            label: row.label,
            rank: row.rank,
            weekStart: currentWeek.toISOString().split('T')[0]
          };
        }
      } catch (error) {
        console.warn("Error processing row in aggregateToWeekly:", row, error);
        continue;
      }
    }

    return weeklyData.length > 0 ? weeklyData : dailyData;
  };

  // Detailed ranking trend chart showing rank changes over time
  const DetailedTrendChart = ({ sectorOrIndustry, type = "sector" }) => {
    const { data: trendData, isLoading } = useQuery({
      queryKey: [
        `detailed-trend-${type}`,
        type === "sector" ? (sectorOrIndustry.sector_name || sectorOrIndustry.sector) : sectorOrIndustry.industry
      ],
      queryFn: async () => {
        try {
          const name = type === "sector" ? (sectorOrIndustry.sector_name || sectorOrIndustry.sector) : sectorOrIndustry.industry;
          const response = await api.get(
            `/api/sectors/trend/${type}/${encodeURIComponent(name)}`
          );
          return response.data;
        } catch (error) {
          console.error(`Failed to fetch ${type} trend:`, error);
          return null;
        }
      },
      staleTime: 300000, // 5 minutes
      enabled: !!(type === "sector" ? (sectorOrIndustry.sector_name || sectorOrIndustry.sector) : sectorOrIndustry.industry),
      retry: false,
    });

    if (isLoading) {
      return (
        <Box display="flex" justifyContent="center" alignItems="center" minHeight={300}>
          <LinearProgress sx={{ width: "50%" }} />
        </Box>
      );
    }

    if (!trendData?.trendData || trendData.trendData.length === 0) {
      return (
        <Typography variant="body2" color="text.secondary" align="center">
          No ranking trend data available
        </Typography>
      );
    }

    // Use only real API data (no fallback) - include both rank and momentum score
    let history = trendData?.trendData.map(row => ({
      date: row.date,
      label: row.label,
      rank: row.rank,
      momentumScore: parseFloat(row.momentumScore || row.momentum || 0)
    }));

    // DEBUG: Log momentum data
    if (history && history.length > 0) {
      console.log(`[MOMENTUM DEBUG] ${type}=${name || 'unknown'} - Sample momentum scores:`,
        history.slice(0, 3).map(h => ({ date: h.date, momentum: h.momentumScore, rank: h.rank }))
      );
    }

    // Filter to last 3 months only (same as mini trend charts)
    if (history.length > 0 && history[0].date) {
      const threeMonthsAgo = new Date();
      threeMonthsAgo.setMonth(threeMonthsAgo.getMonth() - 3);
      history = history.filter(row => {
        try {
          const rowDate = new Date(row.date);
          return rowDate >= threeMonthsAgo;
        } catch {
          return true;
        }
      });
    }

    // Smooth out data by aggregating to weekly (like the small trend charts)
    history = aggregateToWeekly(history);

    // Format date for x-axis display
    const formatXAxisDate = (dateString) => {
      if (!dateString) return "";
      try {
        const date = new Date(dateString);
        return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
      } catch {
        return dateString;
      }
    };

    // Find min and max ranks for better visualization
    const ranks = history.map(h => h.rank).filter(r => r !== null && r !== undefined);
    const minRank = ranks.length > 0 ? Math.min(...ranks) : 1;
    const maxRank = ranks.length > 0 ? Math.max(...ranks) : 12;

    return (
      <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {/* Ranking Summary */}
        <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 1 }}>
          <Box sx={{ p: 1.5, backgroundColor: "grey.50", borderRadius: 1 }}>
            <Typography variant="caption" color="text.secondary" fontWeight="bold">
              Current Rank
            </Typography>
            <Typography variant="body2">
              #{history[history.length - 1]?.rank || "N/A"}
            </Typography>
          </Box>
          <Box sx={{ p: 1.5, backgroundColor: "grey.50", borderRadius: 1 }}>
            <Typography variant="caption" color="text.secondary" fontWeight="bold">
              Best Rank
            </Typography>
            <Typography variant="body2">
              #{minRank || "N/A"}
            </Typography>
          </Box>
          <Box sx={{ p: 1.5, backgroundColor: "grey.50", borderRadius: 1 }}>
            <Typography variant="caption" color="text.secondary" fontWeight="bold">
              Worst Rank
            </Typography>
            <Typography variant="body2">
              #{maxRank || "N/A"}
            </Typography>
          </Box>
          <Box sx={{ p: 1.5, backgroundColor: "grey.50", borderRadius: 1 }}>
            <Typography variant="caption" color="text.secondary" fontWeight="bold">
              Data Points
            </Typography>
            <Typography variant="body2">
              {history.length} days
            </Typography>
          </Box>
        </Box>

        {/* Ranking Trend Chart - Dual axes for rank vs momentum score */}
        <Box sx={{ width: "100%", height: 320, minHeight: 320, overflow: "hidden" }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={history} margin={{ top: 5, right: 80, left: 60, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 12 }}
                interval={Math.floor(history.length / 8)}
                tickFormatter={formatXAxisDate}
              />
              {/* Left Y-axis for Rank */}
              <YAxis
                yAxisId="left"
                width={50}
                tick={{ fontSize: 12 }}
                reversed={true}
                label={{ value: 'Rank (Lower is Better)', angle: -90, position: 'insideLeft' }}
              />
              {/* Right Y-axis for Momentum Score */}
              <YAxis
                yAxisId="right"
                orientation="right"
                width={70}
                tick={{ fontSize: 12 }}
                label={{ value: 'Momentum Score (Higher is Better)', angle: 90, position: 'insideRight' }}
                domain={['dataMin - 0.5', 'dataMax + 0.5']} // Ensure momentum line is visible
              />
              <Tooltip
                contentStyle={{ backgroundColor: 'rgba(255, 255, 255, 0.95)', border: '1px solid #ccc' }}
                formatter={(value, name) => {
                  if (name === 'Ranking') {
                    return [`#${value}`, name];
                  }
                  return [value?.toFixed(2), name];
                }}
                labelFormatter={(label) => `Date: ${formatXAxisDate(label)}`}
              />
              <Legend />
              {/* Rank line (left axis, blue) */}
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="rank"
                stroke="#2196F3"
                name="Ranking"
                dot={false}
                strokeWidth={2}
                isAnimationActive={false}
              />
              {/* Momentum Score line (right axis, orange) */}
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="momentumScore"
                stroke="#FF9800"
                name="Momentum Score"
                dot={false}
                strokeWidth={2}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </Box>
      </Box>
    );
  };

  // Detailed technical analysis chart with moving averages
  const DetailedTechnicalChart = ({ sectorOrIndustry, type = "sector" }) => {
    const { data: technicalData, isLoading } = useQuery({
      queryKey: [
        `technical-details-${type}`,
        type === "sector" ? (sectorOrIndustry.sector_name || sectorOrIndustry.sector) : sectorOrIndustry.industry
      ],
      queryFn: async () => {
        try {
          const name = type === "sector" ? (sectorOrIndustry.sector_name || sectorOrIndustry.sector) : sectorOrIndustry.industry;
          const response = await api.get(
            `/api/sectors/technical-details/${type}/${encodeURIComponent(name)}`
          );
          return response.data;
        } catch (error) {
          console.error(`Failed to fetch ${type} technical details:`, error);
          return null;
        }
      },
      staleTime: 300000, // 5 minutes
      enabled: !!(type === "sector" ? (sectorOrIndustry.sector_name || sectorOrIndustry.sector) : sectorOrIndustry.industry),
      retry: false,
    });

    if (isLoading) {
      return (
        <Box display="flex" justifyContent="center" alignItems="center" minHeight={300}>
          <LinearProgress sx={{ width: "50%" }} />
        </Box>
      );
    }

    if (!technicalData?.history || technicalData.history.length === 0) {
      return (
        <Typography variant="body2" color="text.secondary" align="center">
          No technical data available
        </Typography>
      );
    }

    const summaryData = technicalData.summary || {};
    const history = technicalData.history || [];

    // Format date for x-axis display
    const formatXAxisDate = (dateString) => {
      if (!dateString) return "";
      try {
        const date = new Date(dateString);
        return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
      } catch {
        return dateString;
      }
    };

    return (
      <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {/* Technical Summary Metrics */}
        <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 1 }}>
          <Box sx={{ p: 1.5, backgroundColor: "grey.50", borderRadius: 1 }}>
            <Typography variant="caption" color="text.secondary" fontWeight="bold">
              Current Price
            </Typography>
            <Typography variant="body2">
              ${summaryData.current_price?.toFixed(2) || "N/A"}
            </Typography>
          </Box>
          <Box sx={{ p: 1.5, backgroundColor: "grey.50", borderRadius: 1 }}>
            <Typography variant="caption" color="text.secondary" fontWeight="bold">
              20-Day MA
            </Typography>
            <Typography variant="body2">
              ${summaryData.ma_20?.toFixed(2) || "N/A"} ({summaryData.price_vs_ma20})
            </Typography>
          </Box>
          <Box sx={{ p: 1.5, backgroundColor: "grey.50", borderRadius: 1 }}>
            <Typography variant="caption" color="text.secondary" fontWeight="bold">
              50-Day MA
            </Typography>
            <Typography variant="body2">
              ${summaryData.ma_50?.toFixed(2) || "N/A"}
            </Typography>
          </Box>
          <Box sx={{ p: 1.5, backgroundColor: "grey.50", borderRadius: 1 }}>
            <Typography variant="caption" color="text.secondary" fontWeight="bold">
              200-Day MA
            </Typography>
            <Typography variant="body2">
              ${summaryData.ma_200?.toFixed(2) || "N/A"} ({summaryData.price_vs_ma200})
            </Typography>
          </Box>
          <Box sx={{ p: 1.5, backgroundColor: "grey.50", borderRadius: 1 }}>
            <Typography variant="caption" color="text.secondary" fontWeight="bold">
              RSI (14)
            </Typography>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Typography variant="body2">
                {summaryData.rsi ? `${summaryData.rsi.toFixed(2)}` : "N/A"}
              </Typography>
              <Chip
                label={
                  summaryData.rsi && summaryData.rsi > 70
                    ? "Overbought"
                    : summaryData.rsi && summaryData.rsi < 30
                    ? "Oversold"
                    : "Neutral"
                }
                size="small"
                sx={{ height: "20px" }}
                color={
                  summaryData.rsi && summaryData.rsi > 70
                    ? "error"
                    : summaryData.rsi && summaryData.rsi < 30
                    ? "warning"
                    : "default"
                }
              />
            </Box>
          </Box>
        </Box>

        {/* Price and Moving Averages Chart */}
        <Box sx={{ width: "100%", height: 300, minHeight: 300 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={history} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 12 }}
                interval={Math.floor(history.length / 8)}
                tickFormatter={formatXAxisDate}
              />
              <YAxis width={50} tick={{ fontSize: 12 }} />
              <Tooltip
                formatter={(value) => value ? `$${parseFloat(value).toFixed(2)}` : "N/A"}
                labelFormatter={(label) => `Date: ${formatXAxisDate(label)}`}
              />
              <Line
                type="monotone"
                dataKey="close"
                stroke="#2196F3"
                name="Price"
                dot={false}
                strokeWidth={2}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="ma_20"
                stroke="#FFA726"
                name="MA 20"
                dot={false}
                strokeWidth={1.5}
                strokeDasharray="5 5"
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="ma_50"
                stroke="#66BB6A"
                name="MA 50"
                dot={false}
                strokeWidth={1.5}
                strokeDasharray="5 5"
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="ma_200"
                stroke="#EF5350"
                name="MA 200"
                dot={false}
                strokeWidth={1.5}
                strokeDasharray="5 5"
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </Box>
      </Box>
    );
  };

  const SectorTrendChart = ({ sector }) => {
    // Fetch full trend data from API
    const { data: trendResponse } = useQuery({
      queryKey: ["sector-trend", sector.sector || sector.sector_name],
      queryFn: async () => {
        try {
          const sectorName = sector.sector || sector.sector_name;
          const response = await api.get(`/api/sectors/trend/sector/${encodeURIComponent(sectorName)}`);
          return response.data;
        } catch (error) {
          console.error("Failed to fetch sector trend:", error);
          return null;
        }
      },
      staleTime: 300000, // 5 minutes
      enabled: !!(sector.sector || sector.sector_name),
      retry: false,
    });

    // Use API data if available, otherwise fall back to summary data
    let trendData = trendResponse?.trendData && trendResponse.trendData.length > 0
      ? trendResponse.trendData.map(row => ({
          date: row.date,
          label: row.label,
          rank: row.rank
        }))
      : [
          { period: "12W", rank: sector.rank_12w_ago || sector.rank_12w_ago === 0 ? sector.rank_12w_ago : null },
          { period: "4W", rank: sector.rank_4w_ago || sector.rank_4w_ago === 0 ? sector.rank_4w_ago : null },
          { period: "1W", rank: sector.rank_1w_ago || sector.rank_1w_ago === 0 ? sector.rank_1w_ago : null },
          { period: "Now", rank: sector.current_rank || sector.overall_rank },
        ].filter(d => d.rank !== null);

    // Filter to last 3 months only
    if (trendData.length > 0 && trendData[0].date) {
      const threeMonthsAgo = new Date();
      threeMonthsAgo.setMonth(threeMonthsAgo.getMonth() - 3);
      trendData = trendData.filter(row => {
        try {
          const rowDate = new Date(row.date);
          return rowDate >= threeMonthsAgo;
        } catch {
          return true;
        }
      });
    }

    // Aggregate to weekly data for smoother visualization
    trendData = aggregateToWeekly(trendData);

    return <TrendChart data={trendData} />;
  };

  const IndustryTrendChart = ({ industry }) => {
    // Fetch full trend data from API
    const { data: trendResponse } = useQuery({
      queryKey: ["industry-trend", industry.industry],
      queryFn: async () => {
        try {
          const response = await api.get(`/api/sectors/trend/industry/${encodeURIComponent(industry.industry)}`);
          return response.data;
        } catch (error) {
          console.error("Failed to fetch industry trend:", error);
          return null;
        }
      },
      staleTime: 300000, // 5 minutes
      enabled: !!industry.industry,
      retry: false,
    });

    // Use API data if available, otherwise fall back to summary data
    let trendData = trendResponse?.trendData && trendResponse.trendData.length > 0
      ? trendResponse.trendData.map(row => ({
          date: row.date,
          label: row.label,
          rank: row.rank
        }))
      : [
          { period: "8W", rank: industry.rank_8w_ago || industry.rank_8w_ago === 0 ? industry.rank_8w_ago : null },
          { period: "4W", rank: industry.rank_4w_ago || industry.rank_4w_ago === 0 ? industry.rank_4w_ago : null },
          { period: "1W", rank: industry.rank_1w_ago || industry.rank_1w_ago === 0 ? industry.rank_1w_ago : null },
          { period: "Now", rank: industry.current_rank },
        ].filter(d => d.rank !== null);

    // Filter to last 3 months only
    if (trendData.length > 0 && trendData[0].date) {
      const threeMonthsAgo = new Date();
      threeMonthsAgo.setMonth(threeMonthsAgo.getMonth() - 3);
      trendData = trendData.filter(row => {
        try {
          const rowDate = new Date(row.date);
          return rowDate >= threeMonthsAgo;
        } catch {
          return true;
        }
      });
    }

    // Aggregate to weekly data for smoother visualization
    trendData = aggregateToWeekly(trendData);

    return <TrendChart data={trendData} width={90} height={35} />;
  };

  // Component to render top performing companies for an industry
  const TopPerformingCompaniesGrid = ({ industry }) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const [companies, setCompanies] = useState([]);
    const [isLoading, setIsLoading] = useState(false);

    const handleToggle = async () => {
      if (isExpanded) {
        setIsExpanded(false);
      } else {
        setIsExpanded(true);

        if (companies.length === 0 && !isLoading) {
          setIsLoading(true);
          try {
            // Fetch top 10 performing stocks in this industry, sorted by composite score
            const response = await api.get(
              `/api/stocks?industry=${encodeURIComponent(industry.industry)}&limit=10&sortBy=composite_score&sortOrder=desc`
            );
            const stocksData = response.data;

            // Handle both response formats: direct array or nested in data.stocks
            let stocksList = [];
            if (Array.isArray(stocksData?.data)) {
              stocksList = stocksData.data;
            } else if (stocksData?.data && Array.isArray(stocksData.data.stocks)) {
              stocksList = stocksData.data.stocks;
            }

            setCompanies(stocksList || []);
          } catch (err) {
            console.error(`Failed to fetch companies for ${industry.industry}:`, err);
            setCompanies([]);
          } finally {
            setIsLoading(false);
          }
        }
      }
    };

    return (
      <Box>
        <Box
          onClick={handleToggle}
          sx={{
            p: 1.5,
            backgroundColor: "action.hover",
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1,
            cursor: "pointer",
            transition: "all 0.2s",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            "&:hover": {
              backgroundColor: "action.selected",
              borderColor: "primary.main",
            },
          }}
        >
          <Typography variant="body2" fontWeight="600">
            {isExpanded ? "Hide" : "Show"} Top Performing Companies
          </Typography>
          <Typography variant="body2" sx={{ color: "primary.main", fontWeight: "bold" }}>
            {isExpanded ? "−" : "+"}
          </Typography>
        </Box>

        {isExpanded && (
          <Box sx={{ mt: 2, display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 1.5 }}>
            {isLoading ? (
              <Box sx={{ gridColumn: "1 / -1", textAlign: "center", py: 2 }}>
                <Typography variant="body2" color="text.secondary">Loading companies...</Typography>
              </Box>
            ) : companies.length > 0 ? (
              companies.map((company) => (
                <Box
                  key={company.symbol}
                  sx={{
                    p: 1.5,
                    backgroundColor: "background.paper",
                    border: "1px solid",
                    borderColor: "divider",
                    borderRadius: 1,
                    transition: "all 0.2s",
                    "&:hover": {
                      boxShadow: 2,
                      borderColor: "primary.main",
                    },
                  }}
                >
                  <Typography variant="caption" fontWeight="bold" display="block" sx={{ mb: 0.5 }}>
                    {company.symbol}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.75, fontSize: "0.75rem" }}>
                    {(company.company_name || company.fullName)?.substring(0, 40)}
                  </Typography>

                  {/* Show company metrics */}
                  <Box sx={{ display: "flex", flexDirection: "column", gap: 0.25 }}>
                    {company.price?.current && (
                      <Typography variant="caption" display="block" sx={{ fontSize: "0.7rem" }}>
                        Price: <strong>${parseFloat(company.price.current).toFixed(2)}</strong>
                      </Typography>
                    )}
                    {company.marketCap && (
                      <Typography variant="caption" display="block" sx={{ fontSize: "0.7rem" }}>
                        Market Cap: <strong>${(company.marketCap / 1e9).toFixed(1)}B</strong>
                      </Typography>
                    )}
                    {company.exchange && (
                      <Typography variant="caption" display="block" sx={{ fontSize: "0.7rem", color: "text.secondary" }}>
                        {company.exchange}
                      </Typography>
                    )}
                  </Box>
                </Box>
              ))
            ) : (
              <Box sx={{ gridColumn: "1 / -1", textAlign: "center", py: 2 }}>
                <Typography variant="body2" color="text.secondary">No companies found</Typography>
              </Box>
            )}
          </Box>
        )}
      </Box>
    );
  };

  // Component to render industry cards grid with proper state management
  const IndustryCardsGrid = ({ industries }) => {
    const [expandedIndustries, setExpandedIndustries] = useState({});
    const [companiesCache, setCompaniesCache] = useState({});
    const [loadingIndustries, setLoadingIndustries] = useState({});

    const handleToggleIndustry = async (industryName) => {
      const isCurrentlyExpanded = expandedIndustries[industryName];

      if (isCurrentlyExpanded) {
        // Collapse industry
        setExpandedIndustries(prev => ({
          ...prev,
          [industryName]: false
        }));
      } else {
        // Expand industry and fetch companies if not cached
        setExpandedIndustries(prev => ({
          ...prev,
          [industryName]: true
        }));

        if (!companiesCache[industryName]) {
          setLoadingIndustries(prev => ({
            ...prev,
            [industryName]: true
          }));

          try {
            const response = await api.get(`/api/stocks?industry=${encodeURIComponent(industryName)}&limit=10`);
            setCompaniesCache(prev => ({
              ...prev,
              [industryName]: response.data?.data?.stocks || []
            }));
          } catch (err) {
            console.error(`Failed to fetch companies for ${industryName}:`, err);
            setCompaniesCache(prev => ({
              ...prev,
              [industryName]: []
            }));
          } finally {
            setLoadingIndustries(prev => ({
              ...prev,
              [industryName]: false
            }));
          }
        }
      }
    };

    return (
      <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 1 }}>
        {industries
          .sort((a, b) => {
            const rankA = a.current_rank || 9999;
            const rankB = b.current_rank || 9999;
            return rankA - rankB;
          })
          .map((industry) => {
            const isExpanded = expandedIndustries[industry.industry];
            const topCompanies = companiesCache[industry.industry] || [];
            const isLoading = loadingIndustries[industry.industry];

            return (
              <Box
                key={industry.industry}
                sx={{
                  p: 1.5,
                  backgroundColor: "background.paper",
                  border: "1px solid",
                  borderColor: "divider",
                  borderRadius: 1,
                  cursor: "pointer",
                  transition: "all 0.2s",
                  "&:hover": {
                    boxShadow: 1,
                    borderColor: "primary.main",
                  },
                }}
                onClick={() => handleToggleIndustry(industry.industry)}
              >
                <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <Box sx={{ flex: 1 }}>
                    <Typography variant="caption" fontWeight="600" display="block">
                      #{industry.current_rank || "N/A"}: {industry.industry}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.25 }}>
                      {formatPercentage(industry.performance_1d)} (1D) | {industry.stock_count} stocks
                    </Typography>
                  </Box>
                  <Typography variant="caption" sx={{ ml: 1, color: "primary.main", fontWeight: "bold" }}>
                    {isExpanded ? "−" : "+"}
                  </Typography>
                </Box>

                {isExpanded && (
                  <Box sx={{ mt: 1.5, pt: 1.5, borderTop: "1px solid", borderColor: "divider" }}>
                    <Typography variant="caption" fontWeight="bold" display="block" sx={{ mb: 1 }}>
                      Top Companies:
                    </Typography>
                    {isLoading ? (
                      <Typography variant="caption" color="text.secondary">Loading...</Typography>
                    ) : topCompanies.length > 0 ? (
                      <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
                        {topCompanies.map((company) => (
                          <Typography key={company.ticker} variant="caption" color="text.secondary" display="block">
                            {company.symbol} - {company.fullName?.substring(0, 30)}
                          </Typography>
                        ))}
                      </Box>
                    ) : (
                      <Typography variant="caption" color="text.secondary">No companies found</Typography>
                    )}
                  </Box>
                )}
              </Box>
            );
          })}
      </Box>
    );
  };

  // Fetch sector performance data (consolidated /api/sectors endpoint)
  const { data: rotationData, isLoading: rotationLoading, error: rotationError } = useQuery({
    queryKey: ["sector-performance"],
    queryFn: async () => {
      const response = await api.get("/api/sectors/sectors-with-history?limit=20");
      return response.data;
    },
    staleTime: 60000,
    enabled: true,
    retry: false,
  });

  // Fetch industry performance data (consolidated /api/sectors endpoint)
  // NOTE: Removed limit=50 to fetch ALL industries available
  const { data: industryData, isLoading: industryLoading, error: industryError } = useQuery({
    queryKey: ["industry-performance"],
    queryFn: async () => {
      const response = await api.get("/api/sectors/industries-with-history");
      return response.data;
    },
    staleTime: 60000,
    enabled: true,
    retry: false,
  });

  // Fetch seasonality data
  const { data: seasonalityData, isLoading: seasonalityLoading, error: seasonalityError } = useQuery({
    queryKey: ["sector-seasonality"],
    queryFn: async () => {
      const response = await api.get("/api/market/seasonality");
      return response.data;
    },
    staleTime: 3600000, // 1 hour - seasonality data doesn't change daily
    enabled: true,
    retry: false,
  });

  // Update lastUpdate timestamp when sectors data loads (industries optional)
  useEffect(() => {
    // Update when sectors are loaded (industries are optional for display)
    if (rotationData?.data?.sectors?.length > 0) {
      setLastUpdate(new Date());
    }
  }, [rotationData]);

  // DEBUG: Log industries data received
  useEffect(() => {
    if (industryData?.data?.industries && industryData.data.industries.length > 0) {
      console.log(`[INDUSTRIES API] Total industries returned: ${industryData.data.industries.length}`);
      const industrialsIndustries = industryData.data.industries.filter(ind =>
        (ind.sector === 'Industrials' || ind.sector_name === 'Industrials' ||
         ind.sector === 'Industrial' || ind.sector_name === 'Industrial')
      );
      console.log(`[INDUSTRIALS DATA] Found ${industrialsIndustries.length} for Industrials:`);
      industrialsIndustries.slice(0, 3).forEach(ind => {
        console.log(`  - ${ind.industry}: sector="${ind.sector}", sector_name="${ind.sector_name}"`);
        console.log(`    Historical Ranks: current=${ind.current_rank}, 1w=${ind.rank_1w_ago}, 4w=${ind.rank_4w_ago}, 8w=${ind.rank_8w_ago}`);
      });

      // Check ALL industries for historical rank data
      console.log(`[HISTORICAL RANK CHECK] Sample of industries with historical data:`);
      industryData.data.industries.slice(0, 10).forEach((ind, idx) => {
        console.log(`  [${idx}] ${ind.industry}: current=${ind.current_rank} | 1w_ago=${ind.rank_1w_ago} | 4w_ago=${ind.rank_4w_ago} | 8w_ago=${ind.rank_8w_ago}`);
      });
    }
  }, [industryData]);

  // DEBUG: Log sector historical data
  useEffect(() => {
    if (rotationData?.data?.sectors && rotationData.data.sectors.length > 0) {
      console.log(`[SECTORS API] Total sectors returned: ${rotationData.data.sectors.length}`);
      console.log(`[SECTOR HISTORICAL RANK CHECK] Sample of sectors with historical data:`);
      rotationData.data.sectors.slice(0, 5).forEach((sector, idx) => {
        console.log(`  [${idx}] ${sector.sector_name || sector.sector}: current=${sector.current_rank || sector.overall_rank} | 1w_ago=${sector.rank_1w_ago} | 4w_ago=${sector.rank_4w_ago} | 12w_ago=${sector.rank_12w_ago}`);
      });
    }
  }, [rotationData]);

  // Render sectors if sectors data is available (industries are optional for filtering)
  const shouldRenderSectors = rotationData?.data?.sectors && rotationData?.data?.sectors.length > 0;

  const formatTimeAgo = (date) => {
    const seconds = Math.floor((new Date() - date) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ago`;
  };

  // Prepare chart data from rotation data with vibrant colors
  const chartData = (rotationData?.data?.sectors || [])
    .filter((s) => (s.sector_name || s.sector) && (s.current_perf_1d ?? s.performance_1d) != null && !isNaN(s.current_perf_1d ?? s.performance_1d))
    .map((s, index) => {
      const sectorName = s.sector_name || s.sector;
      return {
        name: sectorName.length > 15 ? sectorName.substring(0, 15) + "..." : sectorName,
        fullName: sectorName,
        performance: parseFloat((s.current_perf_1d ?? s.performance_1d ?? 0).toFixed(2)),
        color: sectorColors[sectorName] || getVibrantColor(index),
      };
    })
    .sort((a, b) => b.performance - a.performance);

  // Pie chart data with vibrant colors for visual appeal
  const pieData = (rotationData?.data?.sectors || [])
    .filter((s) => (s.sector_name || s.sector) && (s.current_rank || s.overall_rank) != null && !isNaN(s.current_rank || s.overall_rank))
    .map((s, index) => {
      const sectorName = s.sector_name || s.sector;
      return {
        name: sectorName,
        value: Math.abs(s.current_rank || s.overall_rank), // Use rank as proxy for significance
        color: sectorColors[sectorName] || getVibrantColor(index),
      };
    });

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box display="flex" alignItems="center" justifyContent="between" mb={4}>
        <Box>
          <Typography variant="h3" component="h1" gutterBottom>
            Sector Analysis
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Comprehensive sector performance analysis and comparisons
          </Typography>
          <Box display="flex" gap={1} mt={1}>
            <Chip
              label={`${rotationData?.data?.sectors?.length || 0} sectors`}
              color="primary"
              size="small"
            />
            <Chip
              label={`Updated ${lastUpdate ? formatTimeAgo(lastUpdate) : "..."}`}
              color="info"
              size="small"
              variant="outlined"
            />
          </Box>
        </Box>
      </Box>


      {/* Performance Overview */}
      <Grid container spacing={3} mb={4}>
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography
                variant="h6"
                gutterBottom
                display="flex"
                alignItems="center"
                gap={1}
              >
                <BarChart color="primary" />
                Sector Performance Today
              </Typography>
              <Box height={400}>
                <ResponsiveContainer width="100%" height="100%">
                  <RechartsBarChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="name"
                      angle={-45}
                      textAnchor="end"
                      height={80}
                      interval={0}
                    />
                    <YAxis />
                    <Tooltip
                      formatter={(value) => [`${value}%`, "Performance"]}
                    />
                    <Bar
                      dataKey="performance"
                      fill={(entry) => entry.color}
                      radius={[4, 4, 0, 0]}
                    >
                      {(chartData || []).map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Bar>
                  </RechartsBarChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography
                variant="h6"
                gutterBottom
                display="flex"
                alignItems="center"
                gap={1}
              >
                <ShowChart color="primary" />
                Market Cap Distribution
              </Typography>
              <Box height={400}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={pieData}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={120}
                      paddingAngle={2}
                      dataKey="value"
                    >
                      {(pieData || []).map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(value) => [
                        `$${(value || 0).toFixed(1)}T`,
                        "Market Cap",
                      ]}
                    />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>



      {/* Sector Rankings */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
            Sector Rankings
          </Typography>
          {rotationLoading ? (
            <Box display="flex" justifyContent="center" py={4}>
              <LinearProgress sx={{ width: "50%" }} />
            </Box>
          ) : rotationError ? (
            <Alert severity="warning">
              Sector data not available.
            </Alert>
          ) : !rotationData?.data?.sectors?.length ? (
            <Alert severity="info">
              No sector data available.
            </Alert>
          ) : !shouldRenderSectors ? (
            <Box display="flex" justifyContent="center" py={4}>
              <LinearProgress sx={{ width: "50%" }} />
            </Box>
          ) : (
            <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {/* Header Row */}
              <Box sx={{ display: "flex", mb: 1, px: 2 }}>
                <Grid container spacing={2} alignItems="center" sx={{ width: "100%", fontWeight: "bold" }}>
                  <Grid item xs={12} sm={1.5}>
                    <Typography variant="caption" fontWeight="bold">Sector</Typography>
                  </Grid>
                  <Grid item xs={3} sm={1.2}>
                    <Typography variant="caption" fontWeight="bold" align="center">Rank</Typography>
                  </Grid>
                  <Grid item xs={3} sm={1}>
                    <Typography variant="caption" fontWeight="bold" align="center">1W Ago</Typography>
                  </Grid>
                  <Grid item xs={3} sm={1}>
                    <Typography variant="caption" fontWeight="bold" align="center">4W Ago</Typography>
                  </Grid>
                  <Grid item xs={3} sm={1}>
                    <Typography variant="caption" fontWeight="bold" align="center">8W Ago</Typography>
                  </Grid>
                  <Grid item xs={3} sm={1.2}>
                    <Typography variant="caption" fontWeight="bold" align="center">Momentum</Typography>
                  </Grid>
                  <Grid item xs={3} sm={1.2}>
                    <Typography variant="caption" fontWeight="bold" align="center">Trend</Typography>
                  </Grid>
                  <Grid item xs={3} sm={1}>
                    <Typography variant="caption" fontWeight="bold" align="right">1D%</Typography>
                  </Grid>
                  <Grid item xs={3} sm={1}>
                    <Typography variant="caption" fontWeight="bold" align="right">5D%</Typography>
                  </Grid>
                  <Grid item xs={3} sm={1}>
                    <Typography variant="caption" fontWeight="bold" align="right">20D%</Typography>
                  </Grid>
                </Grid>
              </Box>
              {(rotationData?.data?.sectors || [])
                .filter((s) => s.sector_name || s.sector)
                .sort((a, b) => (a.current_rank || a.overall_rank || 999) - (b.current_rank || b.overall_rank || 999))
                .map((sector, index) => {
                // Find matching industries for this sector
                // Industries API returns `sector` field, Sectors API returns `sector_name`
                const sectorName = sector.sector_name || sector.sector;

                const sectorIndustries = (industryData?.data?.industries || []).filter(
                  (ind) => {
                    // Filter industries that belong to this sector using sector field from API
                    // Normalize BOTH sides to ensure proper matching across API naming conventions
                    const indSector = ind.sector || ind.sector_name || '';
                    return normalizeSectorName(indSector) === normalizeSectorName(sectorName);
                  }
                );

                return (
                  <Accordion key={`${sector.sector_name || sector.sector}-${index}`} defaultExpanded={index === 0} sx={{ border: "1px solid", borderColor: "divider" }}>
                    <AccordionSummary
                      expandIcon={<ExpandMore />}
                      sx={{
                        backgroundColor: "grey.50",
                        "&:hover": { backgroundColor: "grey.100" },
                        overflow: "visible",
                        minHeight: "60px",
                      }}
                    >
                      <Grid container spacing={1} alignItems="center" sx={{ width: "100%", overflow: "visible" }}>
                        <Grid item xs={12} sm={1.5}>
                          <Typography variant="body2" fontWeight="bold">
                            {sector.sector_name || sector.sector}
                          </Typography>
                        </Grid>
                        <Grid item xs={3} sm={1.2}>
                          <Chip
                            label={`#${sector.current_rank || sector.overall_rank || "N/A"}`}
                            size="small"
                            color="primary"
                            variant="outlined"
                          />
                        </Grid>
                        <Grid item xs={3} sm={1}>
                          <Typography variant="caption" fontWeight="bold" align="center">
                            {sector.rank_1w_ago !== null && sector.rank_1w_ago !== undefined ? sector.rank_1w_ago : "—"}
                          </Typography>
                        </Grid>
                        <Grid item xs={3} sm={1}>
                          <Typography variant="caption" fontWeight="bold" align="center">
                            {sector.rank_4w_ago !== null && sector.rank_4w_ago !== undefined ? sector.rank_4w_ago : "—"}
                          </Typography>
                        </Grid>
                        <Grid item xs={3} sm={1}>
                          <Typography variant="caption" fontWeight="bold" align="center">
                            {sector.rank_12w_ago !== null && sector.rank_12w_ago !== undefined ? sector.rank_12w_ago : "—"}
                          </Typography>
                        </Grid>
                        <Grid item xs={3} sm={1.2}>
                          <Chip
                            label={sector.current_momentum || sector.momentum || "N/A"}
                            size="small"
                            color={
                              (sector.current_momentum || sector.momentum) === "Strong"
                                ? "success"
                                : (sector.current_momentum || sector.momentum) === "Moderate"
                                  ? "info"
                                  : "default"
                            }
                          />
                        </Grid>
                        <Grid item xs={3} sm={1.2}>
                          <Typography variant="h6" align="center">
                            {sector.trend || "—"}
                          </Typography>
                        </Grid>
                        <Grid item xs={3} sm={1}>
                          <Typography
                            variant="caption"
                            sx={{
                              color: getChangeColor(sector.current_perf_1d ?? sector.performance_1d),
                              fontWeight: 600,
                            }}
                            align="right"
                          >
                            {formatPercentage(sector.current_perf_1d ?? sector.performance_1d)}
                          </Typography>
                        </Grid>
                        <Grid item xs={3} sm={1}>
                          <Typography
                            variant="caption"
                            sx={{
                              color: getChangeColor(sector.current_perf_5d ?? sector.performance_5d),
                              fontWeight: 600,
                            }}
                            align="right"
                          >
                            {formatPercentage(sector.current_perf_5d ?? sector.performance_5d)}
                          </Typography>
                        </Grid>
                        <Grid item xs={3} sm={1}>
                          <Typography
                            variant="caption"
                            sx={{
                              color: getChangeColor(sector.current_perf_20d ?? sector.performance_20d),
                              fontWeight: 600,
                            }}
                            align="right"
                          >
                            {formatPercentage(sector.current_perf_20d ?? sector.performance_20d)}
                          </Typography>
                        </Grid>
                        <Grid item xs={12} sm={1.5} sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "60px" }}>
                          <SectorTrendChart sector={sector} />
                        </Grid>
                      </Grid>
                    </AccordionSummary>
                    <AccordionDetails sx={{ backgroundColor: "grey.25", p: 2 }}>
                      <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                        {/* Metrics Section */}
                        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 2 }}>
                          <Box>
                            <Typography variant="caption" color="text.secondary" fontWeight="bold">📊 Current Ranking</Typography>
                            <Typography variant="body2">
                              • Overall Rank: #{sector.current_rank || sector.overall_rank || "N/A"}
                            </Typography>
                            <Typography variant="body2">
                              • Momentum: {sector.current_momentum || sector.momentum || "N/A"}
                            </Typography>
                            <Typography variant="body2">
                              • Trend: {sector.current_trend || sector.trend || "N/A"}
                            </Typography>
                          </Box>
                          <Box>
                            <Typography variant="caption" color="text.secondary" fontWeight="bold">📈 Performance Metrics</Typography>
                            <Typography variant="body2">
                              • 1-Day: {formatPercentage(sector.current_perf_1d ?? sector.performance_1d)}
                            </Typography>
                            <Typography variant="body2">
                              • 5-Day: {formatPercentage(sector.current_perf_5d ?? sector.performance_5d)}
                            </Typography>
                            <Typography variant="body2">
                              • 20-Day: {formatPercentage(sector.current_perf_20d ?? sector.performance_20d)}
                            </Typography>
                          </Box>
                          <Box>
                            <Typography variant="caption" color="text.secondary" fontWeight="bold">📅 Historical Ranks</Typography>
                            <Typography variant="body2">
                              • 1W Ago: {sector.rank_1w_ago !== null && sector.rank_1w_ago !== undefined ? `#${sector.rank_1w_ago}` : "—"}
                            </Typography>
                            <Typography variant="body2">
                              • 4W Ago: {sector.rank_4w_ago !== null && sector.rank_4w_ago !== undefined ? `#${sector.rank_4w_ago}` : "—"}
                            </Typography>
                            <Typography variant="body2">
                              • 12W Ago: {sector.rank_12w_ago !== null && sector.rank_12w_ago !== undefined ? `#${sector.rank_12w_ago}` : "—"}
                            </Typography>
                          </Box>
                        </Box>

                        {/* Ranking Trend Section */}
                        <Box sx={{ borderTop: "1px solid", borderColor: "divider", pt: 2 }}>
                          <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 2 }}>
                            📊 Ranking Trend (Historical)
                          </Typography>
                          <DetailedTrendChart sectorOrIndustry={sector} type="sector" />
                        </Box>

                        {/* Momentum Score Chart - Same Historical Data as Trend Chart */}
                        <SectorMomentumChart sector={sector} aggregateToWeekly={aggregateToWeekly} />

                        {/* Industries Section */}
                        <Box sx={{ borderTop: "1px solid", borderColor: "divider", pt: 2 }}>
                          <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 1 }}>
                            📁 Industries ({sectorIndustries.length})
                          </Typography>
                          {sectorIndustries.length > 0 ? (
                            <IndustryCardsGrid industries={sectorIndustries} />
                          ) : (
                            <Typography variant="caption" color="text.secondary">
                              No industries available
                            </Typography>
                          )}
                        </Box>
                      </Box>
                    </AccordionDetails>
                  </Accordion>
                );
              })}
            </Box>
          )}
        </CardContent>
      </Card>

      {/* Top Industry Rankings */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
            Industry Rankings
          </Typography>
          {industryLoading ? (
            <Box display="flex" justifyContent="center" py={4}>
              <LinearProgress sx={{ width: "50%" }} />
            </Box>
          ) : industryError || !industryData?.data?.industries?.length ? (
            <Alert severity="info" sx={{ mb: 2 }}>
              Industry performance data is currently loading or unavailable.
              {industryError && " The data will appear once the industry loader completes."}
            </Alert>
          ) : (
            <>
              <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
                {/* Header Row */}
                <Box sx={{ display: "flex", mb: 1, px: 2 }}>
                  <Grid container spacing={2} alignItems="center" sx={{ width: "100%", fontWeight: "bold" }}>
                    <Grid item xs={2} sm={0.8}>
                      <Typography variant="caption" fontWeight="bold" align="center">Rank</Typography>
                    </Grid>
                    <Grid item xs={12} sm={2}>
                      <Typography variant="caption" fontWeight="bold">Industry</Typography>
                    </Grid>
                    <Grid item xs={2} sm={1}>
                      <Typography variant="caption" fontWeight="bold" align="center">1W Ago</Typography>
                    </Grid>
                    <Grid item xs={2} sm={1}>
                      <Typography variant="caption" fontWeight="bold" align="center">4W Ago</Typography>
                    </Grid>
                    <Grid item xs={2} sm={1}>
                      <Typography variant="caption" fontWeight="bold" align="center">8W Ago</Typography>
                    </Grid>
                    <Grid item xs={2} sm={1.2}>
                      <Typography variant="caption" fontWeight="bold" align="center">Momentum</Typography>
                    </Grid>
                    <Grid item xs={2} sm={1.2}>
                      <Typography variant="caption" fontWeight="bold" align="center">Status</Typography>
                    </Grid>
                    <Grid item xs={2} sm={0.8}>
                      <Typography variant="caption" fontWeight="bold" align="right">1D%</Typography>
                    </Grid>
                    <Grid item xs={2} sm={0.8}>
                      <Typography variant="caption" fontWeight="bold" align="right">5D%</Typography>
                    </Grid>
                    <Grid item xs={2} sm={0.8}>
                      <Typography variant="caption" fontWeight="bold" align="right">20D%</Typography>
                    </Grid>
                    <Grid item xs={2} sm={1}>
                      <Typography variant="caption" fontWeight="bold" align="right">Count</Typography>
                    </Grid>
                    <Grid item xs={12} sm={1.5}>
                      <Typography variant="caption" fontWeight="bold" align="center">Trend</Typography>
                    </Grid>
                  </Grid>
                </Box>
                {(industryData?.data?.industries || [])
                  .filter((i) => i.industry)
                  .sort((a, b) => (a.current_rank || 999) - (b.current_rank || 999))
                  .map((industry, index) => (
                  <Accordion key={`${industry.industry}-${index}`} defaultExpanded={index === 0} sx={{ border: "1px solid", borderColor: "divider" }}>
                    <AccordionSummary
                      expandIcon={<ExpandMore />}
                      sx={{
                        backgroundColor: "grey.50",
                        "&:hover": { backgroundColor: "grey.100" },
                        overflow: "hidden",
                        minHeight: "auto",
                        py: 1,
                      }}
                    >
                      <Grid container spacing={1} alignItems="center" sx={{ width: "100%", overflow: "hidden" }}>
                        <Grid item xs={2} sm={0.8}>
                          <Chip
                            label={`#${industry.current_rank || "N/A"}`}
                            size="small"
                            color="primary"
                            variant="outlined"
                            sx={{ width: "100%", fontSize: "0.7rem" }}
                          />
                        </Grid>
                        <Grid item xs={12} sm={2} sx={{ minWidth: 0 }}>
                          <Typography variant="caption" fontWeight="bold" sx={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {industry.industry}
                          </Typography>
                          <Typography variant="caption" color="text.secondary" sx={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: "0.7rem" }}>
                            {industry.sector}
                          </Typography>
                        </Grid>
                        <Grid item xs={2} sm={1}>
                          <Typography variant="caption" fontWeight="bold" align="center" sx={{ fontSize: "0.75rem" }}>
                            {industry.rank_1w_ago !== null && industry.rank_1w_ago !== undefined ? industry.rank_1w_ago : "—"}
                          </Typography>
                        </Grid>
                        <Grid item xs={2} sm={1}>
                          <Typography variant="caption" fontWeight="bold" align="center" sx={{ fontSize: "0.75rem" }}>
                            {industry.rank_4w_ago !== null && industry.rank_4w_ago !== undefined ? industry.rank_4w_ago : "—"}
                          </Typography>
                        </Grid>
                        <Grid item xs={2} sm={1}>
                          <Typography variant="caption" fontWeight="bold" align="center" sx={{ fontSize: "0.75rem" }}>
                            {industry.rank_8w_ago !== null && industry.rank_8w_ago !== undefined ? industry.rank_8w_ago : "—"}
                          </Typography>
                        </Grid>
                        <Grid item xs={2} sm={1.2}>
                          <Chip
                            label={industry.momentum || "N/A"}
                            size="small"
                            color={
                              industry.momentum === "Strong"
                                ? "success"
                                : industry.momentum === "Moderate"
                                  ? "info"
                                  : "default"
                            }
                            sx={{ width: "100%", fontSize: "0.7rem" }}
                          />
                        </Grid>
                        <Grid item xs={2} sm={1.2} sx={{ display: "flex", justifyContent: "center" }}>
                          <Typography variant="h6" align="center">
                            {industry.trend || "—"}
                          </Typography>
                        </Grid>
                        <Grid item xs={2} sm={0.8}>
                          <Typography
                            variant="caption"
                            sx={{
                              color: getChangeColor(industry.performance_1d),
                              fontWeight: 600,
                              fontSize: "0.75rem",
                            }}
                            align="right"
                          >
                            {formatPercentage(industry.performance_1d)}
                          </Typography>
                        </Grid>
                        <Grid item xs={2} sm={0.8}>
                          <Typography
                            variant="caption"
                            sx={{
                              color: getChangeColor(industry.performance_5d),
                              fontWeight: 600,
                              fontSize: "0.75rem",
                            }}
                            align="right"
                          >
                            {formatPercentage(industry.performance_5d)}
                          </Typography>
                        </Grid>
                        <Grid item xs={2} sm={0.8}>
                          <Typography
                            variant="caption"
                            sx={{
                              color: getChangeColor(industry.performance_20d),
                              fontWeight: 600,
                              fontSize: "0.75rem",
                            }}
                            align="right"
                          >
                            {formatPercentage(industry.performance_20d)}
                          </Typography>
                        </Grid>
                        <Grid item xs={2} sm={1}>
                          <Typography variant="caption" fontWeight="bold" align="right" sx={{ fontSize: "0.75rem" }}>
                            {industry.stock_count || 0}
                          </Typography>
                        </Grid>
                        <Grid item xs={12} sm={1.5} sx={{ display: "flex", justifyContent: "center", alignItems: "center" }}>
                          <IndustryTrendChart industry={industry} />
                        </Grid>
                      </Grid>
                    </AccordionSummary>
                    <AccordionDetails sx={{ backgroundColor: "grey.25", p: 2 }}>
                      <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
                        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 2 }}>
                          <Box>
                            <Typography variant="caption" color="text.secondary" fontWeight="bold">📊 Ranking History</Typography>
                            <Typography variant="body2">
                              • 1W Ago: {industry.rank_1w_ago !== null ? `#${industry.rank_1w_ago}` : "—"}
                            </Typography>
                            <Typography variant="body2">
                              • 4W Ago: {industry.rank_4w_ago !== null ? `#${industry.rank_4w_ago}` : "—"}
                            </Typography>
                            <Typography variant="body2">
                              • 8W Ago: {industry.rank_8w_ago !== null ? `#${industry.rank_8w_ago}` : "—"}
                            </Typography>
                            <Typography variant="body2" sx={{ mt: 0.5, fontWeight: "600", color: "text.primary" }}>
                              Change: {industry.rank_change_1w !== null ? `${industry.rank_change_1w > 0 ? '+' : ''}${industry.rank_change_1w}` : "—"}
                            </Typography>
                          </Box>
                          <Box>
                            <Typography variant="caption" color="text.secondary" fontWeight="bold">📈 Performance</Typography>
                            <Typography variant="body2">
                              • 1-Day: {formatPercentage(industry.performance_1d)}
                            </Typography>
                            <Typography variant="body2">
                              • 5-Day: {formatPercentage(industry.performance_5d)}
                            </Typography>
                            <Typography variant="body2">
                              • 20-Day: {formatPercentage(industry.performance_20d)}
                            </Typography>
                          </Box>
                          <Box>
                            <Typography variant="caption" color="text.secondary" fontWeight="bold">💼 Industry Info</Typography>
                            <Typography variant="body2">
                              • Sector: <strong>{industry.sector}</strong>
                            </Typography>
                            <Typography variant="body2">
                              • Stocks: <strong>{industry.stock_count || 0}</strong>
                            </Typography>
                            <Typography variant="body2">
                              • Rank: <strong>{industry.current_rank || "N/A"}</strong>
                            </Typography>
                          </Box>
                        </Box>

                        {/* Momentum Score Chart - Same Historical Data as Trend Chart */}
                        <IndustryMomentumChart industry={industry} aggregateToWeekly={aggregateToWeekly} />

                        {/* Top Performing Companies Section */}
                        <Box sx={{ borderTop: "1px solid", borderColor: "divider", pt: 2, mt: 2 }}>
                          <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 2 }}>
                            ⭐ Top Performing Companies in {industry.industry}
                          </Typography>
                          <TopPerformingCompaniesGrid industry={industry} />
                        </Box>

                        {/* Technical Analysis Section */}
                        <Box sx={{ borderTop: "1px solid", borderColor: "divider", pt: 2, mt: 2 }}>
                          <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 2 }}>
                            📈 Technical Analysis (200-Day History with Moving Averages)
                          </Typography>
                          <DetailedTechnicalChart sectorOrIndustry={industry} type="industry" />
                        </Box>
                      </Box>
                    </AccordionDetails>
                  </Accordion>
                ))}
              </Box>
              {industryData?.data?.summary && (
                <Box
                  sx={{
                    mt: 2,
                    pt: 2,
                    borderTop: "1px solid",
                    borderColor: "divider",
                  }}
                >
                  <Typography variant="body2" color="text.secondary">
                    Showing top {industryData.data.industries?.length || 0} of{" "}
                    {industryData.data.summary.total_industries} industries |{" "}
                    Avg 20-Day Performance:{" "}
                    <strong>
                      {formatPercentage(
                        industryData.data.summary.avg_performance_20d
                      )}
                    </strong>
                  </Typography>
                </Box>
              )}
            </>
          )}
        </CardContent>
      </Card>

    </Container>
  );
};

export default SectorAnalysis;
