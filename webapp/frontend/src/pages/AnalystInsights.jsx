import React, { useState, useEffect } from 'react';
import { useSimpleFetch } from '../hooks/useSimpleFetch.js';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { createComponentLogger } from '../utils/errorLogger';
import { formatCurrency, formatNumber, formatPercentage, getChangeColor } from '../utils/formatters';
import { getAnalystRecommendations, getRecentAnalystActions } from '../services/api';
import { API_BASE } from '../config/production';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  TextField,
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
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Alert,
  CircularProgress,
  Divider,
  Slider,
  FormControlLabel,
  Switch,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  IconButton,
  Tooltip
} from '@mui/material';
import {
  ExpandMore,
  TrendingUp,
  TrendingDown,
  ShowChart,
  Timeline,
  Assessment,
  Speed,
  Psychology,
  Analytics,
  Person,
  Business,
  Star,
  StarBorder,
  FilterList,
  Clear,
  Search,
  Refresh,
  HorizontalRule
} from '@mui/icons-material';

// Create component-specific logger
const logger = createComponentLogger('AnalystInsights');

function AnalystInsights() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedSymbol, setSelectedSymbol] = useState('');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);

  // Fetch analyst upgrades/downgrades
  const { data: upgradesData, isLoading: upgradesLoading, error: upgradesError } = useSimpleFetch({
    queryKey: ['analystUpgrades', page, rowsPerPage],
    queryFn: async () => {
      try {
        const params = new URLSearchParams({
          page: page + 1,
          limit: rowsPerPage
        });
        const url = `${API_BASE}/analysts/upgrades?${params}`;
        logger.success('fetchAnalystUpgrades', null, { url, params: params.toString() });
        
        const response = await fetch(url);
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          const error = new Error(errorData.error || `Failed to fetch analyst data (${response.status})`);
          logger.error('fetchAnalystUpgrades', error, {
            url,
            status: response.status,
            statusText: response.statusText,
            errorData
          });
          throw error;
        }
        
        const result = await response.json();
        logger.success('fetchAnalystUpgrades', result, {
          resultCount: result?.data?.length || 0,
          total: result?.total || 0,
          page: page + 1
        });
        return result;
      } catch (err) {
        logger.error('fetchAnalystUpgrades', err, {
          page: page + 1,
          rowsPerPage,
          apiBase: API_BASE
        });
        throw err;
      }
    },
    refetchInterval: 300000, // Refresh every 5 minutes
    retry: 2,
    staleTime: 60000,
    onError: (err) => logger.queryError('analystUpgrades', err, { page, rowsPerPage })
  });
  const getActionChip = (action) => {
    const actionConfig = {
      'up': { color: '#10B981', icon: <TrendingUp />, label: 'Upgrade' },
      'down': { color: '#DC2626', icon: <TrendingDown />, label: 'Downgrade' },
      'main': { color: '#3B82F6', icon: <HorizontalRule />, label: 'Maintains' },
      'init': { color: '#8B5CF6', icon: <Analytics />, label: 'Initiates' },
      'resume': { color: '#10B981', icon: <TrendingUp />, label: 'Resume' },
      'reit': { color: '#F59E0B', icon: <HorizontalRule />, label: 'Reiterate' }
    };

    const config = actionConfig[action?.toLowerCase()] || actionConfig['main'];
    
    return (
      <Chip
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

  const getGradeColor = (grade) => {
    const gradeColors = {
      'Strong Buy': '#059669',
      'Buy': '#10B981',
      'Outperform': '#10B981',
      'Hold': '#6B7280',
      'Neutral': '#6B7280',
      'Underperform': '#F59E0B',
      'Sell': '#DC2626',
      'Strong Sell': '#991B1B'
    };
    
    return gradeColors[grade] || '#6B7280';
  };

  const UpgradesDowngradesTable = () => (
    <TableContainer component={Paper}>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>Symbol</TableCell>
            <TableCell>Company</TableCell>
            <TableCell>Action</TableCell>
            <TableCell>From Grade</TableCell>
            <TableCell>To Grade</TableCell>
            <TableCell>Firm</TableCell>
            <TableCell>Date</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {upgradesData?.data?.map((item, index) => (
            <TableRow key={`${item.symbol}-${index}`} hover>
              <TableCell>
                <Typography variant="body2" fontWeight="bold">
                  {item.symbol}
                </Typography>
              </TableCell>
              <TableCell>
                <Typography variant="body2" noWrap>
                  {item.company}
                </Typography>
              </TableCell>
              <TableCell>
                {getActionChip(item.action)}
              </TableCell>
              <TableCell>
                {item.from_grade && (
                  <Chip
                    label={item.from_grade}
                    size="small"
                    variant="outlined"
                    sx={{
                      borderColor: getGradeColor(item.from_grade),
                      color: getGradeColor(item.from_grade)
                    }}
                  />
                )}
              </TableCell>
              <TableCell>
                {item.to_grade && (
                  <Chip
                    label={item.to_grade}
                    size="small"
                    sx={{
                      backgroundColor: getGradeColor(item.to_grade),
                      color: 'white',
                      fontWeight: 'medium'
                    }}
                  />
                )}
              </TableCell>
              <TableCell>
                <Typography variant="body2">
                  {item.firm}
                </Typography>
              </TableCell>
              <TableCell>
                <Typography variant="body2">
                  {new Date(item.date).toLocaleDateString()}
                </Typography>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );

  // Summary stats
  const upgrades = upgradesData?.data?.filter(item => item.action?.toLowerCase() === 'up') || [];
  const downgrades = upgradesData?.data?.filter(item => item.action?.toLowerCase() === 'down') || [];
  const initiates = upgradesData?.data?.filter(item => item.action?.toLowerCase() === 'init') || [];

  const SummaryCard = ({ title, value, subtitle, icon, color }) => (
    <Card>
      <CardContent>
        <Box display="flex" alignItems="center" mb={1}>
          {icon}
          <Typography variant="h6" ml={1}>{title}</Typography>
        </Box>
        <Typography variant="h4" sx={{ color, fontWeight: 'bold' }}>
          {value}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {subtitle}
        </Typography>
      </CardContent>
    </Card>
  );

  if (upgradesLoading && !upgradesData) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Typography variant="h4" gutterBottom>
        Analyst Insights
      </Typography>
      {/* Only Analyst Actions tab remains */}
      {/* Summary Cards */}
      <Grid container spacing={3} mb={4}>
        <Grid item xs={12} md={3}>
          <SummaryCard
            title="Upgrades"
            value={upgrades.length}
            subtitle="Recent upgrades"
            icon={<TrendingUp />}
            color="#10B981"
          />
        </Grid>
        <Grid item xs={12} md={3}>
          <SummaryCard
            title="Downgrades"
            value={downgrades.length}
            subtitle="Recent downgrades"
            icon={<TrendingDown />}
            color="#DC2626"
          />
        </Grid>
        <Grid item xs={12} md={3}>
          <SummaryCard
            title="Initiates"
            value={initiates.length}
            subtitle="New coverage"
            icon={<Analytics />}
            color="#8B5CF6"
          />
        </Grid>
        <Grid item xs={12} md={3}>
          <SummaryCard
            title="Total Actions"
            value={upgradesData?.data?.length || 0}
            subtitle="All analyst actions"
            icon={<HorizontalRule />}
            color="#3B82F6"
          />
        </Grid>
      </Grid>
      {upgradesError && (
        <Alert severity="error" sx={{ mb: 3 }}>
          Failed to load analyst data: {upgradesError.message}
          <br />
          <small>This may indicate that analyst data tables are not yet populated or there's a database connectivity issue.</small>
        </Alert>
      )}
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Recent Analyst Actions
          </Typography>
          <UpgradesDowngradesTable />
          <TablePagination
            component="div"
            count={upgradesData?.pagination?.total || 0}
            page={page}
            onPageChange={(e, newPage) => setPage(newPage)}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={(e) => {
              setRowsPerPage(parseInt(e.target.value, 10));
              setPage(0);
            }}
            rowsPerPageOptions={[10, 25, 50, 100]}
          />
        </CardContent>
      </Card>
    </Container>
  );
}

export default AnalystInsights;
