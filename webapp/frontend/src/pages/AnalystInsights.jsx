import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Grid,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  InputAdornment,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Alert,
  CircularProgress,
  Tooltip,
  Avatar
} from '@mui/material';
import {
  Search as SearchIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  ShowChart as ShowChartIcon,
  Person as PersonIcon,
  Business as BusinessIcon,
  Timeline as TimelineIcon
} from '@mui/icons-material';
import api from '../services/api';

const AnalystInsights = () => {
  const [upgrades, setUpgrades] = useState([]);
  const [symbolData, setSymbolData] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchSymbol, setSearchSymbol] = useState('');
  const [filterAction, setFilterAction] = useState('all');
  const [page] = useState(1);

  // Fetch all analyst data
  useEffect(() => {
    fetchAnalystData();
  }, [page, filterAction]);

  const fetchAnalystData = async () => {
    try {
      setLoading(true);

      // Fetch upgrades/downgrades
      const upgradesResponse = await api.get(`/api/analysts/upgrades?page=${page}&limit=50`);
      const upgradesData = upgradesResponse.data;

      if (upgradesData.success) {
        let filteredUpgrades = upgradesData.data;
        if (filterAction !== 'all') {
          filteredUpgrades = upgradesData.data.filter(item =>
            item.action && item.action.toLowerCase().includes(filterAction.toLowerCase())
          );
        }
        setUpgrades(filteredUpgrades);
      } else {
        throw new Error(upgradesData.error || 'Failed to fetch analyst data');
      }

    } catch (err) {
      console.error('Error fetching analyst data:', err);
      setError('Failed to load analyst data');
    } finally {
      setLoading(false);
    }
  };

  // Fetch specific symbol data
  const fetchSymbolData = async (symbol) => {
    if (!symbol) return;

    try {
      const response = await api.get(`/api/analysts/${symbol.toUpperCase()}`);
      const data = response.data;

      if (data.success) {
        setSymbolData(prev => ({
          ...prev,
          [symbol.toUpperCase()]: data
        }));
      }
    } catch (err) {
      console.error(`Error fetching data for ${symbol}:`, err);
    }
  };

  const getActionIcon = (action) => {
    if (!action) return <ShowChartIcon />;

    const actionLower = action.toLowerCase();
    if (actionLower.includes('upgrade') || actionLower.includes('buy')) {
      return <TrendingUpIcon sx={{ color: 'success.main' }} />;
    } else if (actionLower.includes('downgrade') || actionLower.includes('sell')) {
      return <TrendingDownIcon sx={{ color: 'error.main' }} />;
    }
    return <ShowChartIcon sx={{ color: 'info.main' }} />;
  };

  const getActionColor = (action) => {
    if (!action) return 'default';

    const actionLower = action.toLowerCase();
    if (actionLower.includes('upgrade') || actionLower.includes('buy')) {
      return 'success';
    } else if (actionLower.includes('downgrade') || actionLower.includes('sell')) {
      return 'error';
    }
    return 'info';
  };


  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    try {
      return new Date(dateString).toLocaleDateString();
    } catch {
      return dateString;
    }
  };

  const filteredUpgrades = upgrades.filter(upgrade =>
    !searchSymbol || upgrade.symbol?.toLowerCase().includes(searchSymbol.toLowerCase())
  );

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <PersonIcon fontSize="large" />
          Analyst Insights
        </Typography>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {/* Summary Cards */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <Avatar sx={{ bgcolor: 'success.main' }}>
                  <TrendingUpIcon />
                </Avatar>
                <Box>
                  <Typography variant="h6">
                    {upgrades.filter(u => u.action?.toLowerCase().includes('upgrade')).length}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Recent Upgrades
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <Avatar sx={{ bgcolor: 'error.main' }}>
                  <TrendingDownIcon />
                </Avatar>
                <Box>
                  <Typography variant="h6">
                    {upgrades.filter(u => u.action?.toLowerCase().includes('downgrade')).length}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Recent Downgrades
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <Avatar sx={{ bgcolor: 'info.main' }}>
                  <BusinessIcon />
                </Avatar>
                <Box>
                  <Typography variant="h6">
                    {new Set(upgrades.map(u => u.firm).filter(Boolean)).size}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Active Firms
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <Avatar sx={{ bgcolor: 'warning.main' }}>
                  <TimelineIcon />
                </Avatar>
                <Box>
                  <Typography variant="h6">
                    {upgrades.length}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Total Actions
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Filters */}
      <Box sx={{ mb: 3, display: 'flex', gap: 2, flexWrap: 'wrap' }}>
        <TextField
          placeholder="Search by symbol..."
          variant="outlined"
          size="small"
          value={searchSymbol}
          onChange={(e) => setSearchSymbol(e.target.value)}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
          }}
          sx={{ minWidth: 200 }}
        />

        <FormControl size="small" sx={{ minWidth: 150 }}>
          <InputLabel id="action-filter-label">Action Filter</InputLabel>
          <Select
            labelId="action-filter-label"
            id="action-filter"
            value={filterAction}
            label="Action Filter"
            onChange={(e) => setFilterAction(e.target.value)}
          >
            <MenuItem value="all">All Actions</MenuItem>
            <MenuItem value="upgrade">Upgrades</MenuItem>
            <MenuItem value="downgrade">Downgrades</MenuItem>
            <MenuItem value="initiate">Initiations</MenuItem>
            <MenuItem value="maintain">Maintains</MenuItem>
          </Select>
        </FormControl>
      </Box>

      {/* Upgrades/Downgrades Table */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <TimelineIcon />
            Recent Analyst Actions
          </Typography>

          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Symbol</TableCell>
                  <TableCell>Firm</TableCell>
                  <TableCell>Action</TableCell>
                  <TableCell>From Grade</TableCell>
                  <TableCell>To Grade</TableCell>
                  <TableCell>Date</TableCell>
                  <TableCell>Details</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredUpgrades.slice(0, 20).map((upgrade, index) => (
                  <TableRow key={upgrade.id || index} hover>
                    <TableCell>
                      <Typography
                        variant="body2"
                        fontWeight="bold"
                        sx={{ cursor: 'pointer', color: 'primary.main' }}
                        onClick={() => fetchSymbolData(upgrade.symbol)}
                      >
                        {upgrade.symbol}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {upgrade.firm || 'N/A'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        {getActionIcon(upgrade.action)}
                        <Chip
                          label={upgrade.action || 'N/A'}
                          color={getActionColor(upgrade.action)}
                          size="small"
                        />
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {upgrade.from_grade || 'N/A'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {upgrade.to_grade || 'N/A'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {formatDate(upgrade.date)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Tooltip title={upgrade.details || 'No details available'}>
                        <Typography
                          variant="body2"
                          sx={{
                            maxWidth: 200,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap'
                          }}
                        >
                          {upgrade.details || 'N/A'}
                        </Typography>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>


      {/* Symbol Detail Modal would go here - simplified for now */}
      {Object.keys(symbolData).length > 0 && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="caption" color="text.secondary">
            Click on symbols to load detailed data (feature can be expanded)
          </Typography>
        </Box>
      )}
    </Box>
  );
};

export default AnalystInsights;