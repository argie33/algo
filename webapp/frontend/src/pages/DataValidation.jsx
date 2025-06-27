import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { createComponentLogger } from '../utils/errorLogger';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  Alert,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  Tabs,
  Tab,
  TextField,
  Button,
  TablePagination,
  FormControl,
  InputLabel,
  Select,
  MenuItem
} from '@mui/material';
import {
  Storage,
  Analytics,
  TrendingUp,
  TrendingDown,
  HorizontalRule,
  CheckCircle,
  Error,
  Warning,
  Info,
  DataUsage
} from '@mui/icons-material';
import { formatNumber, formatDate } from '../utils/formatters';
import { 
  getDataValidationSummary, 
  getEpsRevisions, 
  getEpsTrend, 
  getGrowthEstimates,
  getEconomicData,
  getNaaimData,
  getFearGreedData,
  getTechnicalData
} from '../services/api';

// Create component-specific logger
const logger = createComponentLogger('DataValidation');

function DataValidation() {
  const [activeTab, setActiveTab] = useState(0);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [searchSymbol, setSearchSymbol] = useState('');
  const [selectedTimeframe, setSelectedTimeframe] = useState('daily');

  // Fetch data validation summary
  const { data: summaryData, isLoading: summaryLoading, refetch: refetchSummary } = useQuery({
    queryKey: ['dataValidationSummary'],
    queryFn: getDataValidationSummary,
    refetchInterval: 300000 // Refresh every 5 minutes
  });

  // Fetch EPS revisions
  const { data: epsRevisionsData, isLoading: epsRevisionsLoading } = useQuery({
    queryKey: ['epsRevisions', page, rowsPerPage, searchSymbol],
    queryFn: () => getEpsRevisions({ 
      page: page + 1, 
      limit: rowsPerPage, 
      symbol: searchSymbol || undefined 
    }),
    enabled: activeTab === 1
  });

  // Fetch EPS trend
  const { data: epsTrendData, isLoading: epsTrendLoading } = useQuery({
    queryKey: ['epsTrend', page, rowsPerPage, searchSymbol],
    queryFn: () => getEpsTrend({ 
      page: page + 1, 
      limit: rowsPerPage, 
      symbol: searchSymbol || undefined 
    }),
    enabled: activeTab === 2
  });

  // Fetch growth estimates
  const { data: growthEstimatesData, isLoading: growthEstimatesLoading } = useQuery({
    queryKey: ['growthEstimates', page, rowsPerPage, searchSymbol],
    queryFn: () => getGrowthEstimates({ 
      page: page + 1, 
      limit: rowsPerPage, 
      symbol: searchSymbol || undefined 
    }),
    enabled: activeTab === 3
  });

  // Fetch technical data
  const { data: technicalData, isLoading: technicalLoading } = useQuery({
    queryKey: ['technicalData', selectedTimeframe, page, rowsPerPage, searchSymbol],
    queryFn: () => getTechnicalData(selectedTimeframe, { 
      limit: rowsPerPage, 
      symbol: searchSymbol || undefined 
    }),
    enabled: activeTab === 4
  });

  // Fetch market data
  const { data: naaimData, isLoading: naaimLoading } = useQuery({
    queryKey: ['naaimData'],
    queryFn: () => getNaaimData({ limit: 50 }),
    enabled: activeTab === 5
  });

  const { data: fearGreedData, isLoading: fearGreedLoading } = useQuery({
    queryKey: ['fearGreedData'],
    queryFn: () => getFearGreedData({ limit: 50 }),
    enabled: activeTab === 5
  });

  const { data: economicData, isLoading: economicLoading } = useQuery({
    queryKey: ['economicData', page, rowsPerPage],
    queryFn: () => getEconomicData({ page: page + 1, limit: rowsPerPage }),
    enabled: activeTab === 6
  });

  const getStatusColor = (lastUpdated) => {
    if (!lastUpdated) return 'error';
    const now = new Date();
    const updated = new Date(lastUpdated);
    const diffHours = (now - updated) / (1000 * 60 * 60);
    
    if (diffHours < 24) return 'success';
    if (diffHours < 48) return 'warning';
    return 'error';
  };

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

  const DataSummaryTable = () => (
    <TableContainer component={Paper} elevation={0}>
      <Table>
        <TableHead>
          <TableRow sx={{ backgroundColor: 'grey.50' }}>
            <TableCell>Table Name</TableCell>
            <TableCell align="right">Record Count</TableCell>
            <TableCell>Last Updated</TableCell>
            <TableCell>Status</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {summaryData?.summary?.map((table) => (
            <TableRow key={table.table_name} hover>
              <TableCell>
                <Typography variant="body2" fontWeight="bold">
                  {table.table_name}
                </Typography>
              </TableCell>
              <TableCell align="right">
                <Typography variant="body2">
                  {formatNumber(table.record_count)}
                </Typography>
              </TableCell>
              <TableCell>
                <Typography variant="body2">
                  {table.last_updated ? formatDate(table.last_updated) : 'Never'}
                </Typography>
              </TableCell>
              <TableCell>
                <Chip 
                  label={getStatusColor(table.last_updated) === 'success' ? 'Fresh' : 
                        getStatusColor(table.last_updated) === 'warning' ? 'Stale' : 'Old'}
                  color={getStatusColor(table.last_updated)}
                  size="small"
                />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );

  const GenericDataTable = ({ data, columns, isLoading }) => {
    if (isLoading) {
      return (
        <Box display="flex" justifyContent="center" p={4}>
          <CircularProgress />
        </Box>
      );
    }

    if (!data?.data || data.data.length === 0) {
      return (
        <Alert severity="info" sx={{ m: 2 }}>
          No data available for the selected criteria.
        </Alert>
      );
    }

    return (
      <TableContainer component={Paper} elevation={0}>
        <Table>
          <TableHead>
            <TableRow sx={{ backgroundColor: 'grey.50' }}>
              {columns.map((col) => (
                <TableCell key={col.key} align={col.align || 'left'}>
                  {col.label}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {data.data.map((row, index) => (
              <TableRow key={index} hover>
                {columns.map((col) => (
                  <TableCell key={col.key} align={col.align || 'left'}>
                    {col.render ? col.render(row[col.key], row) : row[col.key]}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {data.pagination && (
          <TablePagination
            component="div"
            count={data.pagination.total}
            page={page}
            onPageChange={(e, newPage) => setPage(newPage)}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={(e) => setRowsPerPage(parseInt(e.target.value))}
          />
        )}
      </TableContainer>
    );
  };

  const epsRevisionsColumns = [
    { key: 'symbol', label: 'Symbol' },
    { key: 'period', label: 'Period' },
    { key: 'current_estimate', label: 'Current', align: 'right', render: (val) => val?.toFixed(2) },
    { key: 'seven_days_ago', label: '7 Days Ago', align: 'right', render: (val) => val?.toFixed(2) },
    { key: 'thirty_days_ago', label: '30 Days Ago', align: 'right', render: (val) => val?.toFixed(2) },
    { key: 'revision_direction', label: 'Direction', render: (val) => (
      <Chip 
        label={val} 
        color={val === 'UP' ? 'success' : val === 'DOWN' ? 'error' : 'default'}
        size="small"
      />
    )}
  ];

  const epsTrendColumns = [
    { key: 'symbol', label: 'Symbol' },
    { key: 'period', label: 'Period' },
    { key: 'current_estimate', label: 'Current', align: 'right', render: (val) => val?.toFixed(2) },
    { key: 'number_of_revisions_up', label: 'Revisions Up', align: 'right' },
    { key: 'number_of_revisions_down', label: 'Revisions Down', align: 'right' }
  ];

  const growthEstimatesColumns = [
    { key: 'symbol', label: 'Symbol' },
    { key: 'period', label: 'Period' },
    { key: 'growth_estimate', label: 'Growth %', align: 'right', render: (val) => `${val?.toFixed(1)}%` },
    { key: 'number_of_analysts', label: 'Analysts', align: 'right' },
    { key: 'mean_estimate', label: 'Mean', align: 'right', render: (val) => val?.toFixed(2) }
  ];

  const technicalColumns = [
    { key: 'symbol', label: 'Symbol' },
    { key: 'date', label: 'Date', render: (val) => formatDate(val) },
    { key: 'rsi', label: 'RSI', align: 'right', render: (val) => val?.toFixed(2) },
    { key: 'macd', label: 'MACD', align: 'right', render: (val) => val?.toFixed(4) },
    { key: 'adx', label: 'ADX', align: 'right', render: (val) => val?.toFixed(2) },
    { key: 'sma_20', label: 'SMA 20', align: 'right', render: (val) => val?.toFixed(2) }
  ];

  const isLoading = summaryLoading || epsRevisionsLoading || epsTrendLoading || 
                   growthEstimatesLoading || technicalLoading || naaimLoading || 
                   fearGreedLoading || economicLoading;

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4" gutterBottom>
          Data Validation Dashboard
        </Typography>
        <Button
          variant="outlined"
          startIcon={<Refresh />}
          onClick={() => refetchSummary()}
          disabled={summaryLoading}
        >
          Refresh Summary
        </Button>
      </Box>

      {/* Summary Cards */}
      <Grid container spacing={3} mb={4}>
        <Grid item xs={12} md={3}>
          <SummaryCard
            title="Total Tables"
            value={summaryData?.summary?.length || 0}
            subtitle="Data tables monitored"
            icon={<Storage />}
            color="primary.main"
          />
        </Grid>
        <Grid item xs={12} md={3}>
          <SummaryCard
            title="Fresh Data"
            value={summaryData?.summary?.filter(t => getStatusColor(t.last_updated) === 'success').length || 0}
            subtitle="Updated in last 24h"
            icon={<TrendingUp />}
            color="success.main"
          />
        </Grid>
        <Grid item xs={12} md={3}>
          <SummaryCard
            title="Total Records"
            value={formatNumber(summaryData?.summary?.reduce((sum, t) => sum + parseInt(t.record_count), 0) || 0)}
            subtitle="Across all tables"
            icon={<DataUsage />}
            color="info.main"
          />
        </Grid>
        <Grid item xs={12} md={3}>
          <SummaryCard
            title="Last Updated"
            value={summaryData?.generated_at ? formatDate(summaryData.generated_at) : 'Never'}
            subtitle="Summary generated"
            icon={<Analytics />}
            color="warning.main"
          />
        </Grid>
      </Grid>

      {/* Search and Filters */}
      <Box display="flex" gap={2} mb={3}>
        <TextField
          label="Search Symbol"
          value={searchSymbol}
          onChange={(e) => setSearchSymbol(e.target.value.toUpperCase())}
          size="small"
          InputProps={{
            startAdornment: <Search />
          }}
        />
        {activeTab === 4 && (
          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel>Timeframe</InputLabel>
            <Select
              value={selectedTimeframe}
              onChange={(e) => setSelectedTimeframe(e.target.value)}
            >
              <MenuItem value="daily">Daily</MenuItem>
              <MenuItem value="weekly">Weekly</MenuItem>
              <MenuItem value="monthly">Monthly</MenuItem>
            </Select>
          </FormControl>
        )}
      </Box>

      {/* Tabs */}
      <Tabs value={activeTab} onChange={(e, newValue) => setActiveTab(newValue)} sx={{ mb: 3 }}>
        <Tab label="Summary" icon={<Analytics />} />
        <Tab label="EPS Revisions" icon={<TrendingUp />} />
        <Tab label="EPS Trend" icon={<Timeline />} />
        <Tab label="Growth Estimates" icon={<ShowChart />} />
        <Tab label="Technical Data" icon={<Timeline />} />
        <Tab label="Market Data" icon={<DataUsage />} />
        <Tab label="Economic Data" icon={<Analytics />} />
      </Tabs>

      {/* Tab Content */}
      <Box>
        {activeTab === 0 && <DataSummaryTable />}
        {activeTab === 1 && (
          <GenericDataTable 
            data={epsRevisionsData} 
            columns={epsRevisionsColumns}
            isLoading={epsRevisionsLoading}
          />
        )}
        {activeTab === 2 && (
          <GenericDataTable 
            data={epsTrendData} 
            columns={epsTrendColumns}
            isLoading={epsTrendLoading}
          />
        )}
        {activeTab === 3 && (
          <GenericDataTable 
            data={growthEstimatesData} 
            columns={growthEstimatesColumns}
            isLoading={growthEstimatesLoading}
          />
        )}
        {activeTab === 4 && (
          <GenericDataTable 
            data={technicalData} 
            columns={technicalColumns}
            isLoading={technicalLoading}
          />
        )}
        {activeTab === 5 && (
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Typography variant="h6" gutterBottom>NAAIM Exposure</Typography>
              {naaimLoading ? (
                <CircularProgress />
              ) : (
                <TableContainer component={Paper}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Date</TableCell>
                        <TableCell align="right">Exposure %</TableCell>
                        <TableCell align="right">Change</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {naaimData?.data?.slice(0, 10).map((row, index) => (
                        <TableRow key={index}>
                          <TableCell>{formatDate(row.date)}</TableCell>
                          <TableCell align="right">{row.exposure_percent}%</TableCell>
                          <TableCell align="right">{row.change_from_previous}%</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </Grid>
            <Grid item xs={12} md={6}>
              <Typography variant="h6" gutterBottom>Fear & Greed Index</Typography>
              {fearGreedLoading ? (
                <CircularProgress />
              ) : (
                <TableContainer component={Paper}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Date</TableCell>
                        <TableCell align="right">Value</TableCell>
                        <TableCell>Classification</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {fearGreedData?.data?.slice(0, 10).map((row, index) => (
                        <TableRow key={index}>
                          <TableCell>{formatDate(row.date)}</TableCell>
                          <TableCell align="right">{row.value}</TableCell>
                          <TableCell>{row.classification}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </Grid>
          </Grid>
        )}
        {activeTab === 6 && (
          <GenericDataTable 
            data={economicData} 
            columns={[
              { key: 'series_id', label: 'Series ID' },
              { key: 'title', label: 'Title' },
              { key: 'date', label: 'Date', render: (val) => formatDate(val) },
              { key: 'value', label: 'Value', align: 'right' },
              { key: 'units', label: 'Units' }
            ]}
            isLoading={economicLoading}
          />
        )}
      </Box>
    </Container>
  );
}

export default DataValidation;
