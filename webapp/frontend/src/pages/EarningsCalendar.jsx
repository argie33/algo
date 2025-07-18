import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { createComponentLogger } from '../utils/errorLogger'
import { formatCurrency, formatNumber, formatPercentage as formatPercent, getChangeColor } from '../utils/formatters'
import { getCalendarEvents, getEarningsEstimates, getEarningsHistory, getEpsRevisions, getEpsTrend, getEarningsMetrics } from '../services/api'
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  TextField,
  MenuItem,
  Button,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  Paper,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  FormControl,
  InputLabel,
  Select,
  Slider,
  Switch,
  FormControlLabel,
  IconButton,
  Tooltip,
  Alert,
  CircularProgress,
  Divider,
  InputAdornment,
  ToggleButton,
  ToggleButtonGroup,
  Tabs,
  Tab,
  Modal,
  Backdrop,
  Fade
} from '@mui/material'
import {
  ExpandMore,
  FilterList,
  Clear,
  Search,
  TrendingUp,
  TrendingDown,
  ShowChart,
  Tune,
  Event as EventIcon,
  AttachMoney,
  Schedule,
  Analytics,
  EventNote,
  HorizontalRule
} from '@mui/icons-material'

// Create component-specific logger
const logger = createComponentLogger('EarningsCalendar');

function EarningsCalendar() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [activeTab, setActiveTab] = useState(0)
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(25)
  const [timeFilter, setTimeFilter] = useState('upcoming')
  
  // EPS Revisions state
  const [epsSymbol, setEpsSymbol] = useState('AAPL');
  const [epsInput, setEpsInput] = useState('AAPL');

  // Fetch calendar events
  const { data: calendarData, isLoading: calendarLoading, error: calendarError } = useQuery({
    queryKey: ['calendarEvents', timeFilter, page, rowsPerPage],
    queryFn: async () => {
      try {
        return await getCalendarEvents(timeFilter, page, rowsPerPage);
      } catch (error) {
        console.warn('Calendar API failed, using mock data:', error);
        // Return mock data when API fails
        return {
          success: true,
          data: {
            events: [],
            summary: {
              upcoming_events: 0,
              this_week: 0,
              earnings_seasons: 0,
              total_companies: 0
            },
            pagination: {
              total: 0,
              page: 1,
              limit: rowsPerPage,
              hasMore: false
            }
          }
        };
      }
    },
    enabled: activeTab === 0,
    refetchInterval: 300000 // Refresh every 5 minutes
  });

  // Fetch earnings estimates
  const { data: estimatesData, isLoading: estimatesLoading } = useQuery({
    queryKey: ['earningsEstimates', page, rowsPerPage],
    queryFn: async () => {
      return await getEarningsEstimates({ page: page + 1, limit: rowsPerPage });
    },
    enabled: activeTab === 1,
    refetchInterval: 300000
  });

  // Fetch earnings history
  const { data: historyData, isLoading: historyLoading } = useQuery({
    queryKey: ['earningsHistory', page, rowsPerPage],
    queryFn: async () => {
      return await getEarningsHistory({ page: page + 1, limit: rowsPerPage });
    },
    enabled: activeTab === 2,
    refetchInterval: 600000 // Refresh every 10 minutes
  });

  // EPS Revisions fetch
  const { data: epsRevisionsData, isLoading: epsRevisionsLoading, error: epsRevisionsError, refetch: refetchEps } = useQuery({
    queryKey: ['epsRevisions', epsSymbol],
    queryFn: async () => {
      return await getEpsRevisions(epsSymbol);
    },
    enabled: activeTab === 3 && !!epsSymbol,
    staleTime: 60000
  });

  // EPS Trend fetch
  const { data: epsTrendData, isLoading: epsTrendLoading, error: epsTrendError, refetch: refetchEpsTrend } = useQuery({
    queryKey: ['epsTrend', epsSymbol],
    queryFn: async () => {
      return await getEpsTrend(epsSymbol);
    },
    enabled: activeTab === 4 && !!epsSymbol,
    staleTime: 60000
  });

  // Earnings Metrics fetch
  const { data: earningsMetricsData, isLoading: earningsMetricsLoading, error: earningsMetricsError, refetch: refetchEarningsMetrics } = useQuery({
    queryKey: ['earningsMetrics', epsSymbol, page, rowsPerPage],
    queryFn: async () => {
      return await getEarningsMetrics(epsSymbol, page, rowsPerPage);
    },
    enabled: activeTab === 5 && !!epsSymbol,
    staleTime: 60000
  });

  const getEventTypeChip = (eventType) => {
    const typeConfig = {
      'earnings': { color: '#3B82F6', icon: <ShowChart />, label: 'Earnings' },
      'dividend': { color: '#10B981', icon: <AttachMoney />, label: 'Dividend' },
      'split': { color: '#8B5CF6', icon: <Analytics />, label: 'Stock Split' },
      'meeting': { color: '#F59E0B', icon: <EventNote />, label: 'Meeting' }
    };

    const config = typeConfig[eventType?.toLowerCase()] || typeConfig['earnings'];
    
    return (
      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
        label={config.label}
        size="small"
        icon={config.icon}
        sx={{
          backgroundColor: config.color,
          color: 'white',
          fontWeight: 'medium',
          '& .MuiChip-icon': {
            color: 'white'
          }
        }}
      />
    );
  };

  const getSurpriseColor = (surprise) => {
    if (surprise > 5) return 'success.main';
    if (surprise > 0) return 'success.light';
    if (surprise < -5) return 'error.main';
    if (surprise < 0) return 'error.light';
    return 'grey.500';
  };

  const getSurpriseIcon = (surprise) => {
    if (surprise > 0) return <TrendingUp />;
    if (surprise < 0) return <TrendingDown />;
    return <TrendingUp />;
  };

  const CalendarEventsTable = () => (
    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} elevation={0}>
      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow sx={{ backgroundColor: 'grey.50' }}>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Event Type</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Date</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Title</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Time to Event</td>
          </tr>
        </thead>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
          {calendarData?.data?.map((event, index) => (
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={`${event.symbol}-${index}`} hover>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                <div  variant="body2" fontWeight="bold">
                  {event.symbol}
                </div>
              </td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                {getEventTypeChip(event.event_type)}
              </td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                <div  variant="body2">
                  {new Date(event.start_date).toLocaleDateString()}
                </div>
              </td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                <div  variant="body2" noWrap>
                  {event.title}
                </div>
              </td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                <div  variant="body2" color="text.secondary">
                  {Math.ceil((new Date(event.start_date) - new Date()) / (1000 * 60 * 60 * 24))} days
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const EarningsEstimatesTable = () => (
    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} elevation={0}>
      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow sx={{ backgroundColor: 'grey.50' }}>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Company</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Period</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Avg Estimate</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Low</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">High</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Analysts</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Growth</td>
          </tr>
        </thead>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
          {Object.entries(estimatesData?.data || {}).map(([symbol, group]) => (
            group.estimates.map((estimate, index) => (
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={`${symbol}-${estimate.period}-${index}`} hover>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                  <div  variant="body2" fontWeight="bold">{symbol}</div>
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                  <div  variant="body2">{group.company_name}</div>
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label={estimate.period} size="small" variant="outlined" />
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                  <div  variant="body2" fontWeight="bold">
                    {formatCurrency(estimate.avg_estimate)}
                  </div>
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{formatCurrency(estimate.low_estimate)}</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{formatCurrency(estimate.high_estimate)}</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                  <div  variant="body2">{estimate.number_of_analysts}</div>
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                  <div  display="flex" alignItems="center" justifyContent="flex-end" gap={1}>
                    <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ bgcolor: getSurpriseColor(estimate.growth), width: 24, height: 24 }}>
                      {getSurpriseIcon(estimate.growth)}
                    </div>
                    <div  variant="body2" sx={{ color: getSurpriseColor(estimate.growth) }}>
                      {formatPercentage(estimate.growth / 100)}
                    </div>
                  </div>
                </td>
              </tr>
            ))
          ))}
        </tbody>
      </table>
    </div>
  );

  const EarningsHistoryTable = () => (
    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} elevation={0}>
      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow sx={{ backgroundColor: 'grey.50' }}>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Company</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Quarter</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Actual EPS</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Estimated EPS</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Difference</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Surprise %</td>
          </tr>
        </thead>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
          {Object.entries(historyData?.data || {}).map(([symbol, group]) => (
            group.history.map((history, index) => (
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={`${symbol}-${history.quarter}-${index}`} hover>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                  <div  variant="body2" fontWeight="bold">
                    {symbol}
                  </div>
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                  <div  variant="body2">{group.company_name}</div>
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                  <div  variant="body2">
                    {new Date(history.quarter).toLocaleDateString()}
                  </div>
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                  <div  variant="body2" fontWeight="bold">
                    {formatCurrency(history.eps_actual)}
                  </div>
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                  {formatCurrency(history.eps_estimate)}
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                  <div  
                    variant="body2"
                    sx={{ color: history.eps_difference >= 0 ? 'success.main' : 'error.main' }}
                  >
                    {formatCurrency(history.eps_difference)}
                  </div>
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                  <div  display="flex" alignItems="center" justifyContent="flex-end" gap={1}>
                    <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ 
                      bgcolor: getSurpriseColor(history.surprise_percent), 
                      width: 24, 
                      height: 24 
                    }}>
                      {getSurpriseIcon(history.surprise_percent)}
                    </div>
                    <div  
                      variant="body2" 
                      sx={{ color: getSurpriseColor(history.surprise_percent) }}
                    >
                      {formatPercentage(history.surprise_percent / 100)}
                    </div>
                  </div>
                </td>
              </tr>
            ))
          ))}
        </tbody>
      </table>
    </div>
  );

  const SummaryCard = ({ title, value, subtitle, icon, color }) => (
    <div className="bg-white shadow-md rounded-lg">
      <div className="bg-white shadow-md rounded-lg"Content>
        <div  display="flex" alignItems="center" mb={1}>
          {icon}
          <div  variant="h6" ml={1}>{title}</div>
        </div>
        <div  variant="h4" sx={{ color, fontWeight: 'bold' }}>
          {value}
        </div>
        <div  variant="body2" color="text.secondary">
          {subtitle}
        </div>
      </div>
    </div>
  );

  const isLoading = calendarLoading || (activeTab === 1 && estimatesLoading) || (activeTab === 2 && historyLoading) || (activeTab === 3 && epsRevisionsLoading) || (activeTab === 4 && epsTrendLoading) || (activeTab === 5 && earningsMetricsLoading);

  if (isLoading && !calendarData && !estimatesData && !historyData) {
    return (
      <div className="container mx-auto" maxWidth="lg" sx={{ py: 4 }}>
        <div  display="flex" justifyContent="center" alignItems="center" minHeight="400px">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto" maxWidth="lg" sx={{ py: 4 }}>
      <div  variant="h4" gutterBottom>
        Earnings Calendar & Estimates
      </div>

      {/* Summary Cards */}
      <div className="grid" container spacing={3} mb={4}>
        <div className="grid" item xs={12} md={3}>
          <SummaryCard
            title="Upcoming Events"
            value={calendarData?.summary?.upcoming_events || 0}
            subtitle="Next 30 days"
            icon={<Schedule />}
            color="#3B82F6"
          />
        </div>
        <div className="grid" item xs={12} md={3}>
          <SummaryCard
            title="Earnings This Week"
            value={calendarData?.summary?.this_week || 0}
            subtitle="Companies reporting"
            icon={<ShowChart />}
            color="#10B981"
          />
        </div>
        <div className="grid" item xs={12} md={3}>
          <SummaryCard
            title="Positive Surprises"
            value={historyData?.summary?.positive_surprises || 0}
            subtitle="Last quarter"
            icon={<TrendingUp />}
            color="#059669"
          />
        </div>
        <div className="grid" item xs={12} md={3}>
          <SummaryCard
            title="Estimates Updated"
            value={estimatesData?.summary?.recent_updates || 0}
            subtitle="Last 7 days"
            icon={<Analytics />}
            color="#8B5CF6"
          />
        </div>
      </div>

      {/* Error Handling */}
      {calendarError && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 3 }}>
          Failed to load calendar data. Please try again later.
        </div>
      )}

      {/* Tabs */}
      <div  mb={3}>
        <div className="border-b border-gray-200" value={activeTab} onChange={(e, newValue) => setActiveTab(newValue)}>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Calendar Events" icon={<Schedule />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Earnings Estimates" icon={<ShowChart />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Earnings History" icon={<Analytics />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="EPS Revisions" icon={<TrendingUp />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="EPS Trend" icon={<TrendingDown />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Earnings Metrics" icon={<HorizontalRule />} />
        </div>
      </div>

      {/* Filters for Calendar Tab */}
      {activeTab === 0 && (
        <div className="grid" container spacing={2} mb={3}>
          <div className="grid" item xs={12} sm={4}>
            <div className="mb-4" fullWidth>
              <label className="block text-sm font-medium text-gray-700 mb-1">Time Filter</label>
              <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={timeFilter}
                label="Time Filter"
                onChange={(e) => setTimeFilter(e.target.value)}
              >
                <option  value="upcoming">Upcoming Events</option>
                <option  value="this_week">This Week</option>
                <option  value="next_week">Next Week</option>
                <option  value="this_month">This Month</option>
              </select>
            </div>
          </div>
        </div>
      )}

      {/* Loading indicator */}
      {isLoading && <div className="w-full bg-gray-200 rounded-full h-2" sx={{ mb: 2 }} />}

      {/* Content */}
      <div className="bg-white shadow-md rounded-lg">
        <div className="bg-white shadow-md rounded-lg"Content>
          {activeTab === 0 && (
            <>
              <div  variant="h6" gutterBottom>
                Earnings Calendar - {timeFilter.replace('_', ' ').toUpperCase()}
              </div>
              <CalendarEventsTable />
            </>
          )}
          
          {activeTab === 1 && (
            <>
              <div  variant="h6" gutterBottom>
                Earnings Estimates
              </div>
              <EarningsEstimatesTable />
            </>
          )}

          {activeTab === 2 && (
            <>
              <div  variant="h6" gutterBottom>
                Earnings History & Surprises
              </div>
              <EarningsHistoryTable />
            </>
          )}

          {activeTab === 3 && (
            <>
              <div  variant="h6" gutterBottom>
                EPS Revisions Lookup
              </div>
              <div  display="flex" alignItems="center" gap={2} mb={2}>
                <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  label="Symbol"
                  value={epsInput}
                  onChange={e => setEpsInput(e.target.value.toUpperCase())}
                  size="small"
                  sx={{ width: 120 }}
                  inputProps={{ maxLength: 8 }}
                />
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  variant="contained"
                  onClick={() => {
                    setEpsSymbol(epsInput);
                    refetchEps();
                  }}
                  disabled={epsRevisionsLoading || !epsInput}
                >
                  Lookup
                </button>
              </div>
              {epsRevisionsLoading ? (
                <div  display="flex" justifyContent="center" my={3}><div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={28} /></div>
              ) : epsRevisionsError ? (
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error">Failed to load EPS revisions: {epsRevisionsError.message}</div>
              ) : epsRevisionsData?.data?.length ? (
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} sx={{ mt: 2 }}>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Period</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Up Last 7d</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Up Last 30d</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Down Last 7d</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Down Last 30d</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Fetched At</td>
                      </tr>
                    </thead>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                      {epsRevisionsData.data.map((row, idx) => (
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={row.period + idx}>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{row.period}</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.up_last7days ?? '-'}</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.up_last30days ?? '-'}</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.down_last7days ?? '-'}</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.down_last30days ?? '-'}</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.fetched_at ? new Date(row.fetched_at).toLocaleString() : '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div  variant="body2" color="text.secondary" mt={2}>
                  No EPS revisions data found for <b>{epsSymbol}</b>.
                </div>
              )}
            </>
          )}
          {activeTab === 4 && (
            <>
              <div  variant="h6" gutterBottom>
                EPS Trend Lookup
              </div>
              <div  display="flex" alignItems="center" gap={2} mb={2}>
                <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  label="Symbol"
                  value={epsInput}
                  onChange={e => setEpsInput(e.target.value.toUpperCase())}
                  size="small"
                  sx={{ width: 120 }}
                  inputProps={{ maxLength: 8 }}
                />
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  variant="contained"
                  onClick={() => {
                    setEpsSymbol(epsInput);
                    refetchEpsTrend();
                  }}
                  disabled={epsTrendLoading || !epsInput}
                >
                  Lookup
                </button>
              </div>
              {epsTrendLoading ? (
                <div  display="flex" justifyContent="center" my={3}><div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={28} /></div>
              ) : epsTrendError ? (
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error">Failed to load EPS trend: {epsTrendError.message}</div>
              ) : epsTrendData?.data?.length ? (
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} sx={{ mt: 2 }}>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Period</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Current</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">7 Days Ago</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">30 Days Ago</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">60 Days Ago</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">90 Days Ago</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Fetched At</td>
                      </tr>
                    </thead>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                      {epsTrendData.data.map((row, idx) => (
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={row.period + idx}>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{row.period}</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.current ?? '-'}</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.days7ago ?? '-'}</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.days30ago ?? '-'}</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.days60ago ?? '-'}</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.days90ago ?? '-'}</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.fetched_at ? new Date(row.fetched_at).toLocaleString() : '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div  variant="body2" color="text.secondary" mt={2}>
                  No EPS trend data found for <b>{epsSymbol}</b>.
                </div>
              )}
            </>
          )}
          {activeTab === 5 && (
            <>
              <div  variant="h6" gutterBottom>
                Earnings Metrics Lookup
              </div>
              <div  display="flex" alignItems="center" gap={2} mb={2}>
                <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  label="Symbol"
                  value={epsInput}
                  onChange={e => setEpsInput(e.target.value.toUpperCase())}
                  size="small"
                  sx={{ width: 120 }}
                  inputProps={{ maxLength: 8 }}
                />
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  variant="contained"
                  onClick={() => {
                    setEpsSymbol(epsInput);
                    refetchEarningsMetrics();
                  }}
                  disabled={earningsMetricsLoading || !epsInput}
                >
                  Lookup
                </button>
              </div>
              {earningsMetricsLoading ? (
                <div  display="flex" justifyContent="center" my={3}><div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={28} /></div>
              ) : earningsMetricsError ? (
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error">Failed to load earnings metrics: {earningsMetricsError.message}</div>
              ) : (
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} sx={{ mt: 2 }}>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Report Date</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">EPS Growth 1Q</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">EPS Growth 2Q</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">EPS Growth 4Q</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">EPS Growth 8Q</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">EPS Accel Qtrs</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Surprise Last Q</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Est Rev 1M</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Est Rev 3M</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Est Rev 6M</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Annual EPS 1Y</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Annual EPS 3Y</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Annual EPS 5Y</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Consec EPS Yrs</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Est Change This Yr</td>
                      </tr>
                    </thead>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                      {Array.isArray(earningsMetricsData?.data?.[epsSymbol]?.metrics) && earningsMetricsData.data[epsSymbol].metrics.length > 0 ? (
                        earningsMetricsData.data[epsSymbol].metrics.map((row, idx) => (
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={row.report_date + idx}>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{row.report_date}</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.eps_growth_1q ?? '-'}</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.eps_growth_2q ?? '-'}</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.eps_growth_4q ?? '-'}</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.eps_growth_8q ?? '-'}</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.eps_acceleration_qtrs ?? '-'}</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.eps_surprise_last_q ?? '-'}</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.eps_estimate_revision_1m ?? '-'}</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.eps_estimate_revision_3m ?? '-'}</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.eps_estimate_revision_6m ?? '-'}</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.annual_eps_growth_1y ?? '-'}</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.annual_eps_growth_3y ?? '-'}</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.annual_eps_growth_5y ?? '-'}</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.consecutive_eps_growth_years ?? '-'}</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.eps_estimated_change_this_year ?? '-'}</td>
                          </tr>
                        ))
                      ) : (
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell colSpan={15} align="center">
                            <div  variant="body2" color="text.secondary" mt={2}>
                              No earnings metrics data found for <b>{epsSymbol}</b>.
                            </div>
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
          
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"lePagination
            component="div"
            count={
              activeTab === 0 ? (calendarData?.pagination?.total || 0) :
              activeTab === 1 ? (estimatesData?.pagination?.total || 0) :
              activeTab === 2 ? (historyData?.pagination?.total || 0) :
              activeTab === 3 ? (epsRevisionsData?.pagination?.total || 0) :
              activeTab === 4 ? (epsTrendData?.pagination?.total || 0) :
              (earningsMetricsData?.pagination?.total || 0)
            }
            page={page}
            onPageChange={(e, newPage) => setPage(newPage)}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={(e) => {
              setRowsPerPage(parseInt(e.target.value, 10));
              setPage(0);
            }}
            rowsPerPageOptions={[10, 25, 50, 100]}
          />
        </div>
      </div>
    </div>
  );
}

export default EarningsCalendar;
