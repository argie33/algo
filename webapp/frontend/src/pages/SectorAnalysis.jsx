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
  BarChart,
} from "@mui/icons-material";
import {
  BarChart as RechartsBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Cell,
  Tooltip,
  Legend,
  LineChart,
  ComposedChart,
  Line,
  ReferenceLine,
  Area,
} from "recharts";
import api from "../services/api";
import {
  formatPercentage,
  formatPercentageChange,
  getChangeColor,
} from "../utils/formatters";
import { formatXAxisDate } from "../utils/dateFormatters";
import PETrendChart from "../components/PETrendChart";

// Helper component for sector momentum chart
// Displays Daily Strength chart with Moving Averages
const MomentumChart = ({ type = 'sector', data, aggregateToWeekly }) => {
  const identifierName = type === 'sector' ? data?.sector_name : data?.industry;
  const trendArray = data?.trendData || [];

  // Transform trend data - API provides daily strength and technical indicators
  let chartData = trendArray.map(row => ({
    date: row.date,
    // Price data (using daily strength as proxy for price movement) - null if missing
    price: row.dailyStrengthScore !== null && row.dailyStrengthScore !== undefined ? parseFloat(row.dailyStrengthScore) : null,
    // Keep original field for aggregation functions - null if missing
    dailyStrengthScore: row.dailyStrengthScore !== null && row.dailyStrengthScore !== undefined ? parseFloat(row.dailyStrengthScore) : null,
    // Moving averages (calculated on daily strength)
    ma_5: row.ma_5 !== undefined && row.ma_5 !== null ? parseFloat(row.ma_5) : null,
    ma_10: row.ma_10 !== undefined && row.ma_10 !== null ? parseFloat(row.ma_10) : null,
    ma_20: row.ma_20 !== undefined && row.ma_20 !== null ? parseFloat(row.ma_20) : null,
    // RSI data (calculated from daily strength)
    rsi: row.rsi !== undefined && row.rsi !== null ? parseFloat(row.rsi) : null,
    // Metadata
    rank: row.rank,
    trend: row.trend,
  }));

  // Limit to last 12 months of available data, or all data if less than 12 months available
  const now = new Date();
  const oneYearAgo = new Date(now.getFullYear() - 1, now.getMonth(), now.getDate());

  // First, filter to try last year
  let filteredData = chartData.filter(d => {
    const rowDate = new Date(d.date);
    return rowDate >= oneYearAgo;
  });

  // If we don't have a year of data, use all available data instead
  if (filteredData.length === 0 && chartData.length > 0) {
    filteredData = chartData;
  }

  chartData = filteredData;

  // Check what data is available
  // NOTE: Using only MA 10 and MA 20 for clarity - best practice is 2 MAs, not 3
  // MA 10 = short-term momentum, MA 20 = medium-term trend
  const hasPrice = chartData.some(d => d.price !== null && d.price !== undefined);
  const hasMA10 = chartData.some(m => m.ma_10 !== null && m.ma_10 !== undefined);
  const hasMA20 = chartData.some(m => m.ma_20 !== null && m.ma_20 !== undefined);

  if (chartData.length > 0) {
    console.log(`[${type.toUpperCase()} CHARTS] ${identifierName}: ${chartData.length} rows (last 12 months or all available)`);
  }

  // Calculate consistent x-axis interval for all charts
  const xAxisInterval = Math.max(1, Math.floor(chartData.length / 8));

  // Aggregate to weekly if requested
  if (aggregateToWeekly && chartData.length > 0) {
    chartData = aggregateToWeekly(chartData);
  }

  // Only render if there's actual data to display
  if (!chartData || chartData.length === 0 || !hasPrice) {
    return null;
  }

  return (
    <Box sx={{ borderTop: "1px solid", borderColor: "divider", pt: 2, mb: 3 }}>
      <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 2 }}>
        📊 Daily Strength Chart
      </Typography>
      <>
        {/* CHART 1: DAILY STRENGTH + MAs */}
        {hasPrice && (
          <Box sx={{ width: "100%", mb: 3 }}>
            <Box sx={{ width: "100%", height: 320, minHeight: 320, overflow: "hidden" }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 5, right: 30, left: 60, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tick={{ fontSize: 12 }} interval={xAxisInterval} tickFormatter={(date) => formatXAxisDate(date)} />
                  <YAxis width={50} tick={{ fontSize: 12 }} />
                  <Tooltip contentStyle={{ backgroundColor: 'rgba(255, 255, 255, 0.95)', border: '1px solid #ccc' }} formatter={(val) => typeof val === 'number' ? val.toFixed(2) : val} />
                  <Line type="monotone" dataKey="price" stroke="#FF6B35" strokeWidth={3} dot={false} connectNulls name="Daily Strength" isAnimationActive={false} />
                  {hasMA10 && <Line type="monotone" dataKey="ma_10" stroke="#1ABC9C" strokeWidth={2} strokeDasharray="5 5" dot={false} connectNulls name="MA 10" isAnimationActive={false} />}
                  {hasMA20 && <Line type="monotone" dataKey="ma_20" stroke="#E74C3C" strokeWidth={2} strokeDasharray="5 5" dot={false} connectNulls name="MA 20" isAnimationActive={false} />}
                </LineChart>
              </ResponsiveContainer>
            </Box>
            {/* UNIFIED LEGEND BELOW CHART - WITH PROPER LINE STYLES */}
            <Box sx={{ display: "flex", justifyContent: "center", flexWrap: "wrap", gap: 3, mt: 2.5, px: 2 }}>
              {hasPrice && (
                <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                  {/* Solid line for Daily Strength */}
                  <svg width="20" height="12" style={{ display: "flex", alignItems: "center" }}>
                    <line x1="0" y1="6" x2="20" y2="6" stroke="#FF6B35" strokeWidth="3" />
                  </svg>
                  <Typography variant="caption" fontSize="11px">Daily Strength</Typography>
                </Box>
              )}
              {hasMA10 && (
                <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                  {/* Dashed line for MA 10 */}
                  <svg width="20" height="12" style={{ display: "flex", alignItems: "center" }}>
                    <line x1="0" y1="6" x2="20" y2="6" stroke="#1ABC9C" strokeWidth="2" strokeDasharray="5 5" />
                  </svg>
                  <Typography variant="caption" fontSize="11px">MA 10</Typography>
                </Box>
              )}
              {hasMA20 && (
                <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                  {/* Dashed line for MA 20 */}
                  <svg width="20" height="12" style={{ display: "flex", alignItems: "center" }}>
                    <line x1="0" y1="6" x2="20" y2="6" stroke="#E74C3C" strokeWidth="2" strokeDasharray="5 5" />
                  </svg>
                  <Typography variant="caption" fontSize="11px">MA 20</Typography>
                </Box>
              )}
            </Box>
          </Box>
        )}
      </>
    </Box>
  );
};

// Sector momentum chart with data fetching - loads trend data via API
const SectorMomentumChart = ({ sector, aggregateToWeekly }) => {
  // Fetch trend data for this specific sector
  const { data: trendResponse, isLoading } = useQuery({
    queryKey: ["sector-momentum", sector.sector_name || sector.sector],
    queryFn: async () => {
      try {
        const response = await api.get(
          `/api/sectors/trend/sector/${encodeURIComponent(sector.sector_name || sector.sector)}`
        );
        // responseFormatter wraps response in { success, data: {...}, timestamp }
        return response?.data?.data || response?.data;
      } catch (error) {
        console.error("Failed to fetch sector momentum data:", error);
        return null;
      }
    },
    staleTime: 0, // Always fresh - no stale cache
    gcTime: 0, // Disable garbage collection cache // 5 minutes
    enabled: !!(sector.sector_name || sector.sector),
    retry: false,
  });

  if (isLoading) {
    return (
      <Box display="flex" justifyContent="center" py={2}>
        <LinearProgress sx={{ width: "100%", maxWidth: 400 }} />
      </Box>
    );
  }

  // Pass trend data to MomentumChart
  const sectorWithTrend = {
    ...sector,
    trendData: trendResponse?.trendData || []
  };

  return <MomentumChart type="sector" data={sectorWithTrend} aggregateToWeekly={aggregateToWeekly} />;
};

const IndustryMomentumChart = ({ industry, aggregateToWeekly }) => {
  // Fetch trend data for this specific industry
  const { data: trendResponse, isLoading } = useQuery({
    queryKey: ["industry-momentum", industry.industry],
    queryFn: async () => {
      try {
        const response = await api.get(
          `/api/industries/trend/industry/${encodeURIComponent(industry.industry)}`
        );
        // responseFormatter wraps response in { success, data: {...}, timestamp }
        return response?.data?.data || response?.data;
      } catch (error) {
        console.error("Failed to fetch industry momentum data:", error);
        return null;
      }
    },
    staleTime: 0, // Always fresh - no stale cache
    gcTime: 0, // Disable garbage collection cache // 5 minutes
    enabled: !!industry.industry,
    retry: false,
  });

  if (isLoading) {
    return (
      <Box display="flex" justifyContent="center" py={2}>
        <LinearProgress sx={{ width: "100%", maxWidth: 400 }} />
      </Box>
    );
  }

  // Pass trend data to MomentumChart
  const industryWithTrend = {
    ...industry,
    trendData: trendResponse?.trendData || []
  };

  return <MomentumChart type="industry" data={industryWithTrend} aggregateToWeekly={aggregateToWeekly} />;
};

const SectorAnalysis = () => {
  const [lastUpdate, setLastUpdate] = useState(null);
  const [performanceTimeframe, setPerformanceTimeframe] = useState("1d"); // 1d, 5d, 20d, ytd

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

  // Get trend icon and color based on trend value
  const getTrendIcon = (trend) => {
    const trendLower = (trend || "").toLowerCase();
    if (trendLower.includes("uptrend")) {
      return { icon: TrendingUp, color: "#4caf50", label: "Uptrend" };
    } else if (trendLower.includes("downtrend")) {
      return { icon: TrendingDown, color: "#f44336", label: "Downtrend" };
    } else {
      return { icon: TrendingUp, color: "#9e9e9e", label: "Sideways" };
    }
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
  // Simple sector name comparison (both APIs use same naming conventions)
  const normalizeSectorName = (sectorName) => {
    if (!sectorName) return '';
    // Both sectors API and industries API use identical sector names,
    // so no mapping needed - just return the name as-is for direct comparison
    return sectorName.trim();
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
    if (dailyData.length > 0 && !dailyData[0].date) {
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
            momentum: row.momentum,
            price: row.price,
            ma_5: row.ma_5,
            ma_10: row.ma_10,
            ma_20: row.ma_20,
            rsi: row.rsi,
            close: row.close,
            trend: row.trend,
            dailyStrengthScore: row.dailyStrengthScore,
            weekStart: currentWeek.toISOString().split('T')[0]
          });
        } else {
          // Update the last entry with the newest data for this week
          weeklyData[weeklyData.length - 1] = {
            date: row.date,
            label: row.label,
            rank: row.rank,
            momentum: row.momentum,
            price: row.price,
            ma_5: row.ma_5,
            ma_10: row.ma_10,
            ma_20: row.ma_20,
            rsi: row.rsi,
            close: row.close,
            trend: row.trend,
            dailyStrengthScore: row.dailyStrengthScore,
            weekStart: currentWeek.toISOString().split('T')[0]
          };
        }
      } catch (error) {
        console.warn("Error processing row in aggregateToWeekly:", row, error);
        continue;
      }
    }

    // Sort by date to ensure proper chronological order in the chart
    return weeklyData.length > 0 ? weeklyData.sort((a, b) => new Date(a.date) - new Date(b.date)) : dailyData;
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
          const endpoint = type === "sector"
            ? `/api/sectors/trend/sector/${encodeURIComponent(name)}`
            : `/api/industries/trend/industry/${encodeURIComponent(name)}`;
          const response = await api.get(endpoint);
          // responseFormatter wraps response in { success, data: {...}, timestamp }
          return response?.data?.data || response?.data;
        } catch (error) {
          console.error(`Failed to fetch ${type} trend:`, error);
          return null;
        }
      },
      staleTime: 0, // Always fresh - no stale cache
    gcTime: 0, // Disable garbage collection cache // 5 minutes
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

    // Use only real API data (no synthetic defaults) - include both rank and momentum score
    let history = trendData?.trendData.map(row => {
      // Only include momentum if real data available - do not synthesize 0
      let momentum = null;
      if (row.dailyStrengthScore !== null && row.dailyStrengthScore !== undefined) {
        momentum = parseFloat(row.dailyStrengthScore);
      } else if (row.momentumScore !== null && row.momentumScore !== undefined) {
        momentum = parseFloat(row.momentumScore);
      } else if (row.momentum !== null && row.momentum !== undefined) {
        momentum = parseFloat(row.momentum);
      }
      // Return null for momentum if all sources are missing (no fake 0 value)
      return {
        date: row.date,
        label: row.label,
        rank: row.rank,
        momentum: momentum
      };
    });

    const name = type === "sector" ? (sectorOrIndustry.sector_name || sectorOrIndustry.sector) : sectorOrIndustry.industry;

    // DEBUG: Log rank and momentum data
    if (history && history.length > 0) {
      const uniqueRanks = [...new Set(history.map(h => h.rank))];
      console.log(`[RANK TREND DEBUG] ${type}=${name} - Total points: ${history.length}, Unique ranks: ${uniqueRanks.length}`, {
        ranks: uniqueRanks.slice(0, 10),
        sample: history.slice(0, 3).map(h => ({ date: h.date, rank: h.rank, momentum: h.momentum }))
      });
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
        </Box>

        {/* Ranking Trend Chart - Rank only (no momentum) */}
        <Box sx={{ width: "100%", height: 320, minHeight: 320, overflow: "hidden" }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={history} margin={{ top: 5, right: 30, left: 60, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 12 }}
                interval={Math.floor(history.length / 8)}
                tickFormatter={formatXAxisDate}
              />
              {/* Y-axis for Rank */}
              <YAxis
                width={50}
                tick={{ fontSize: 12 }}
                reversed={true}
                label={{ value: 'Rank (Lower is Better)', angle: -90, position: 'insideLeft' }}
              />
              <Tooltip
                contentStyle={{ backgroundColor: 'rgba(255, 255, 255, 0.95)', border: '1px solid #ccc' }}
                formatter={(value) => `#${value}`}
                labelFormatter={(label) => `Date: ${formatXAxisDate(label)}`}
              />
              <Legend />
              {/* Rank line (blue) */}
              <Line
                type="monotone"
                dataKey="rank"
                stroke="#2196F3"
                name="Ranking"
                dot={false}
                strokeWidth={2}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </Box>
      </Box>
    );
  };

  // Consolidated trend chart wrapper for both sectors and industries
  const TrendChartWrapper = ({ type = 'sector', data, width, height }) => {
    // Determine query key and identifier based on type
    const identifier = type === 'sector'
      ? (data.sector || data.sector_name)
      : data.industry;

    // API endpoint and query configuration
    const queryConfig = type === 'sector'
      ? { endpoint: `/api/sectors/trend/sector/${encodeURIComponent(identifier)}`, key: ["sector-trend", identifier] }
      : { endpoint: `/api/industries/trend/industry/${encodeURIComponent(identifier)}`, key: ["industry-trend", identifier] };

    // Fallback periods based on type
    const fallbackPeriods = type === 'sector'
      ? [
          { period: "12W", rank: data.rank_12w_ago || data.rank_12w_ago === 0 ? data.rank_12w_ago : null },
          { period: "4W", rank: data.rank_4w_ago || data.rank_4w_ago === 0 ? data.rank_4w_ago : null },
          { period: "1W", rank: data.rank_1w_ago || data.rank_1w_ago === 0 ? data.rank_1w_ago : null },
          { period: "Now", rank: data.current_rank || data.overall_rank },
        ]
      : [
          { period: "8W", rank: data.rank_8w_ago || data.rank_8w_ago === 0 ? data.rank_8w_ago : null },
          { period: "4W", rank: data.rank_4w_ago || data.rank_4w_ago === 0 ? data.rank_4w_ago : null },
          { period: "1W", rank: data.rank_1w_ago || data.rank_1w_ago === 0 ? data.rank_1w_ago : null },
          { period: "Now", rank: data.current_rank },
        ];

    // Fetch full trend data from API
    const { data: trendResponse } = useQuery({
      queryKey: queryConfig.key,
      queryFn: async () => {
        try {
          const response = await api.get(queryConfig.endpoint);
          // responseFormatter wraps response in { success, data: {...}, timestamp }
          return response?.data?.data || response?.data;
        } catch (error) {
          console.error(`Failed to fetch ${type} trend:`, error);
          return null;
        }
      },
      staleTime: 0, // Always fresh - no stale cache
    gcTime: 0, // Disable garbage collection cache // 5 minutes
      enabled: !!identifier,
      retry: false,
    });

    // Use API data if available, otherwise fall back to summary data
    let trendData = trendResponse?.trendData && trendResponse.trendData.length > 0
      ? trendResponse.trendData.map(row => ({
          date: row.date,
          label: row.label,
          rank: row.rank
        }))
      : fallbackPeriods.filter(d => d.rank !== null);

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

    const props = { data: trendData };
    if (width) props.width = width;
    if (height) props.height = height;
    return <TrendChart {...props} />;
  };

  // Legacy component wrappers for backwards compatibility
  const SectorTrendChart = ({ sector }) => <TrendChartWrapper type="sector" data={sector} />;
  const IndustryTrendChart = ({ industry }) => <TrendChartWrapper type="industry" data={industry} width={90} height={35} />;

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
              `/api/scores/stockscores?limit=10&sortBy=composite_score&sortOrder=desc`
            );
            // Get response data with proper structure
            const stocksList = response?.data?.items || [];

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

  // Component to render industry cards grid (simplified - no expandable dropdowns)
  const IndustryCardsGrid = ({ industries }) => {
    return (
      <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 1 }}>
        {industries
          .sort((a, b) => {
            const rankA = a.current_rank ?? 9999;
            const rankB = b.current_rank ?? 9999;
            return rankA - rankB;
          })
          .map((industry) => (
            <Box
              key={industry.industry}
              sx={{
                p: 1.5,
                backgroundColor: "background.paper",
                border: "1px solid",
                borderColor: "divider",
                borderRadius: 1,
                transition: "all 0.2s",
                "&:hover": {
                  boxShadow: 1,
                  borderColor: "primary.main",
                },
              }}
            >
              <Typography variant="caption" fontWeight="600" display="block">
                #{industry.current_rank || "N/A"}: {industry.industry}
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.25 }}>
                {formatPercentageChange(industry.performance_1d)} (1D) | {industry.stock_count} stocks
              </Typography>
            </Box>
          ))}
      </Box>
    );
  };

  // Fetch sector performance data (consolidated /api/sectors endpoint)
  const { data: rotationData, isLoading: rotationLoading, error: rotationError } = useQuery({
    queryKey: ["sector-performance"],
    queryFn: async () => {
      const response = await api.get("/api/sectors/sectors?limit=20");
      // Axios wraps response in { data: {...}, status, ... }
      // Backend returns: { items: [...sectors], pagination: {...}, success: true }
      // So response.data = { items: [...sectors], pagination: {...}, success: true }
      // Extract the array with response.data.items (new format)
      return response?.data?.items || [];
    },
    staleTime: 0, // Always fresh - no stale cache
    gcTime: 0, // Disable garbage collection cache
    enabled: true,
    retry: false,
  });

  // Fetch industry performance data from /api/industries/industries endpoint
  const { data: industryData, isLoading: industryLoading, error: industryError } = useQuery({
    queryKey: ["industry-performance"],
    queryFn: async () => {
      const response = await api.get("/api/industries/industries");
      // Axios wraps response in { data: {...}, status, ... }
      // Backend returns: { items: [...industries], pagination: {...}, success: true }
      // So response.data = { items: [...industries], pagination: {...}, success: true }
      // Extract the array with response.data.items (new format)
      const industriesArray = response?.data?.items || [];

      return industriesArray.map(ind => ({
        industry: ind.industry,
        sector: ind.sector,
        current_rank: ind.current_rank,
        rank_1w_ago: ind.rank_1w_ago,
        rank_4w_ago: ind.rank_4w_ago,
        rank_12w_ago: ind.rank_12w_ago,
        current_momentum: ind.current_momentum,
        performance_1d: ind.performance_1d,
        performance_5d: ind.performance_5d,
        performance_20d: ind.performance_20d,
        current_trend: ind.current_trend
      }));
    },
    staleTime: 0, // Always fresh - no stale cache
    gcTime: 0, // Disable garbage collection cache
    enabled: true,
    retry: false,
  });

  // Update lastUpdate timestamp when sectors data loads (industries optional)
  useEffect(() => {
    // Update when sectors are loaded (industries are optional for display)
    // rotationData is already { sectors: [...] }, not { data: { sectors: [...] } }
    if (rotationData?.length > 0) {
      setLastUpdate(new Date());
    }
  }, [rotationData]);


  // DEBUG: Log sector historical data
  useEffect(() => {
    if (rotationData && Array.isArray(rotationData) && rotationData.length > 0) {
      console.log(`[SECTORS API] Total sectors returned: ${rotationData.length}`);
      console.log(`[SECTOR CHART DATA] Sectors available for chart:`, rotationData.map(s => ({ name: s.sector_name, perf_1d: s.current_perf_1d })));
      console.log(`[SECTOR HISTORICAL RANK CHECK] Sample of sectors with historical data:`);
      rotationData.slice(0, 5).forEach((sector, idx) => {
        console.log(`  [${idx}] ${sector.sector_name || sector.sector}: current=${sector.current_rank || sector.overall_rank} | 1d_perf=${sector.current_perf_1d} | 1w_ago=${sector.rank_1w_ago} | 4w_ago=${sector.rank_4w_ago} | 12w_ago=${sector.rank_12w_ago}`);
      });
    } else {
      console.log(`[SECTORS API] No sectors data available:`, rotationData);
    }
  }, [rotationData]);

  // Render sectors if sectors data is available (industries are optional for filtering)
  const shouldRenderSectors = rotationData && rotationData.length > 0;

  const formatTimeAgo = (date) => {
    const seconds = Math.floor((new Date() - date) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ago`;
  };

  // Helper function to get performance value based on timeframe
  const getPerformanceValue = (sector, timeframe) => {
    switch(timeframe) {
      case "1d":
        return sector.current_perf_1d ?? sector.performance_1d;
      case "5d":
        return sector.current_perf_5d ?? sector.performance_5d;
      case "20d":
        return sector.current_perf_20d ?? sector.performance_20d;
      case "ytd":
        return sector.current_perf_ytd ?? sector.performance_ytd ?? sector.current_perf_1d ?? sector.performance_1d;
      default:
        return sector.current_perf_1d ?? sector.performance_1d;
    }
  };

  // Prepare chart data from rotation data with vibrant colors
  const chartData = (rotationData || [])
    .filter((s) => {
      const hasName = !!(s.sector_name || s.sector);
      const perfValue = getPerformanceValue(s, performanceTimeframe);
      const hasPerf = perfValue != null;
      const perfIsNum = !isNaN(perfValue);
      const passes = hasName && hasPerf && perfIsNum;
      if (!passes) {
        console.log(`[CHART FILTER] Filtered out:`, { name: s.sector_name, perf: perfValue, hasName, hasPerf, perfIsNum });
      }
      return passes;
    })
    .map((s, index) => {
      const sectorName = s.sector_name || s.sector;
      const perfValue = getPerformanceValue(s, performanceTimeframe);
      return {
        name: sectorName.length > 15 ? sectorName.substring(0, 15) + "..." : sectorName,
        fullName: sectorName,
        performance: parseFloat((perfValue ?? 0).toFixed(2)),
        color: sectorColors[sectorName] || getVibrantColor(index),
      };
    })
    .sort((a, b) => b.performance - a.performance);

  console.log(`[CHART DATA] Final chart data points: ${chartData.length}`, chartData);

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
              label={`${rotationData?.length || 0} sectors`}
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
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
            <Typography
              variant="h6"
              display="flex"
              alignItems="center"
              gap={1}
            >
              <BarChart color="primary" />
              Sector Performance
            </Typography>
            <Box display="flex" gap={1}>
              {[
                { value: "1d", label: "Daily" },
                { value: "5d", label: "5D" },
                { value: "20d", label: "Monthly" },
              ].map((option) => (
                <Box
                  key={option.value}
                  onClick={() => setPerformanceTimeframe(option.value)}
                  sx={{
                    px: 2,
                    py: 0.5,
                    cursor: "pointer",
                    borderRadius: 1,
                    backgroundColor: performanceTimeframe === option.value ? "primary.main" : "action.hover",
                    color: performanceTimeframe === option.value ? "white" : "text.primary",
                    fontWeight: performanceTimeframe === option.value ? 600 : 400,
                    transition: "all 0.2s",
                    "&:hover": {
                      backgroundColor: performanceTimeframe === option.value ? "primary.dark" : "action.selected",
                    },
                  }}
                >
                  <Typography variant="caption">{option.label}</Typography>
                </Box>
              ))}
            </Box>
          </Box>
          <Box width="100%" height={400} sx={{ overflow: "hidden", position: "relative", display: "block" }}>
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
          ) : !rotationData?.length ? (
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
              {(rotationData || [])
                .filter((s) => s.sector_name || s.sector)
                .sort((a, b) => (a.current_rank ?? a.overall_rank ?? 999) - (b.current_rank ?? b.overall_rank ?? 999))
                .map((sector, index) => {
                // Find matching industries for this sector
                // Industries API returns `sector` field, Sectors API returns `sector_name`
                const sectorName = sector.sector_name || sector.sector;

                const sectorIndustries = (industryData || []).filter(
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
                          {(() => {
                            const { icon: Icon, color } = getTrendIcon(sector.current_trend || sector.trend);
                            return <Icon sx={{ color, fontSize: 24, mx: "auto" }} title={sector.current_trend || sector.trend || "—"} />;
                          })()}
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
                            {formatPercentageChange(sector.current_perf_1d ?? sector.performance_1d)}
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
                            {formatPercentageChange(sector.current_perf_5d ?? sector.performance_5d)}
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
                            {formatPercentageChange(sector.current_perf_20d ?? sector.performance_20d)}
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
                        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 2 }}>
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
                              • 1-Day: {formatPercentageChange(sector.current_perf_1d ?? sector.performance_1d)}
                            </Typography>
                            <Typography variant="body2">
                              • 5-Day: {formatPercentageChange(sector.current_perf_5d ?? sector.performance_5d)}
                            </Typography>
                            <Typography variant="body2">
                              • 20-Day: {formatPercentageChange(sector.current_perf_20d ?? sector.performance_20d)}
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
                          <Box>
                            <Typography variant="caption" color="text.secondary" fontWeight="bold">💰 P/E Valuation</Typography>
                            <Typography variant="body2">
                              • Trailing P/E: {sector.pe?.trailing ? sector.pe.trailing.toFixed(2) : "—"}
                            </Typography>
                            <Typography variant="body2">
                              • Forward P/E: {sector.pe?.forward ? sector.pe.forward.toFixed(2) : "—"}
                            </Typography>
                            <Typography variant="body2">
                              • Percentile: {sector.pe?.percentile ? `${sector.pe.percentile}th` : "—"}
                            </Typography>
                          </Box>
                        </Box>

                        {/* P/E Trend Chart */}
                        <PETrendChart sectorName={sector.sector_name} />

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
          ) : industryError || !industryData?.length ? (
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
                      <Typography variant="caption" fontWeight="bold" align="center">12W Ago</Typography>
                    </Grid>
                    <Grid item xs={2} sm={1.2}>
                      <Typography variant="caption" fontWeight="bold" align="center">Momentum</Typography>
                    </Grid>
                    <Grid item xs={2} sm={1.2}>
                      <Typography variant="caption" fontWeight="bold" align="center">Trend</Typography>
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
                {(industryData || [])
                  .filter((i) => i.industry)
                  .sort((a, b) => (a.current_rank ?? 999) - (b.current_rank ?? 999))
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
                            {industry.rank_12w_ago !== null && industry.rank_12w_ago !== undefined ? industry.rank_12w_ago : "—"}
                          </Typography>
                        </Grid>
                        <Grid item xs={2} sm={1.2}>
                          <Chip
                            label={industry.current_momentum || "N/A"}
                            size="small"
                            color={
                              industry.current_momentum === "Strong"
                                ? "success"
                                : industry.current_momentum === "Moderate"
                                  ? "info"
                                  : "default"
                            }
                            sx={{ width: "100%", fontSize: "0.7rem" }}
                          />
                        </Grid>
                        <Grid item xs={2} sm={1.2} sx={{ display: "flex", justifyContent: "center" }}>
                          {(() => {
                            const { icon: Icon, color } = getTrendIcon(industry.current_trend || industry.trend);
                            return <Icon sx={{ color, fontSize: 24 }} title={industry.current_trend || industry.trend || "—"} />;
                          })()}
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
                            {formatPercentageChange(industry.performance_1d)}
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
                            {formatPercentageChange(industry.performance_5d)}
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
                            {formatPercentageChange(industry.performance_20d)}
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
                        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 2 }}>
                          <Box>
                            <Typography variant="caption" color="text.secondary" fontWeight="bold">📊 Ranking History</Typography>
                            <Typography variant="body2">
                              • 1W Ago: {industry.rank_1w_ago !== null ? `#${industry.rank_1w_ago}` : "—"}
                            </Typography>
                            <Typography variant="body2">
                              • 4W Ago: {industry.rank_4w_ago !== null ? `#${industry.rank_4w_ago}` : "—"}
                            </Typography>
                            <Typography variant="body2">
                              • 12W Ago: {industry.rank_12w_ago !== null ? `#${industry.rank_12w_ago}` : "—"}
                            </Typography>
                            <Typography variant="body2" sx={{ mt: 0.5, fontWeight: "600", color: "text.primary" }}>
                              Change: {industry.rank_change_1w !== null ? `${industry.rank_change_1w > 0 ? '+' : ''}${industry.rank_change_1w}` : "—"}
                            </Typography>
                          </Box>
                          <Box>
                            <Typography variant="caption" color="text.secondary" fontWeight="bold">📈 Performance</Typography>
                            <Typography variant="body2">
                              • 1-Day: {formatPercentageChange(industry.performance_1d)}
                            </Typography>
                            <Typography variant="body2">
                              • 5-Day: {formatPercentageChange(industry.performance_5d)}
                            </Typography>
                            <Typography variant="body2">
                              • 20-Day: {formatPercentageChange(industry.performance_20d)}
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
                          <Box>
                            <Typography variant="caption" color="text.secondary" fontWeight="bold">💰 P/E Valuation</Typography>
                            <Typography variant="body2">
                              • Trailing P/E: {industry.pe?.trailing ? industry.pe.trailing.toFixed(2) : "—"}
                            </Typography>
                            <Typography variant="body2">
                              • Forward P/E: {industry.pe?.forward ? industry.pe.forward.toFixed(2) : "—"}
                            </Typography>
                            <Typography variant="body2">
                              • Percentile: {industry.pe?.percentile ? `${industry.pe.percentile}th` : "—"}
                            </Typography>
                          </Box>
                        </Box>

                        {/* Ranking Trend Section */}
                        <Box sx={{ borderTop: "1px solid", borderColor: "divider", pt: 2 }}>
                          <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 2 }}>
                            📊 Ranking Trend (Historical)
                          </Typography>
                          <DetailedTrendChart sectorOrIndustry={industry} type="industry" />
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
                      </Box>
                    </AccordionDetails>
                  </Accordion>
                ))}
              </Box>
            </>
          )}
        </CardContent>
      </Card>

    </Container>
  );
};

export default SectorAnalysis;
