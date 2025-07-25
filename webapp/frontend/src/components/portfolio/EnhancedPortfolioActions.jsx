import React, { useState } from 'react';
import {
  Box,
  Button,
  ButtonGroup,
  IconButton,
  Tooltip,
  Menu,
  MenuItem,
  ListItemIcon,
  ListItemText,
  Divider,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Typography,
  FormControlLabel,
  Switch,
  Chip
} from '@mui/material';
import {
  Refresh,
  MoreVert,
  CloudSync,
  Speed,
  Storage,
  Settings,
  Download,
  Upload,
  History,
  Analytics
} from '@mui/icons-material';

const EnhancedPortfolioActions = ({ 
  onRefresh, 
  onForceSync, 
  onExport, 
  onImport,
  onViewHistory,
  onAnalyze,
  loading = false,
  syncStatus,
  showDataSource = true,
  dataSource
}) => {
  const [anchorEl, setAnchorEl] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [refreshInterval, setRefreshInterval] = useState(30);

  const handleMenuOpen = (event) => {
    setAnchorEl(event.currentTarget);
  };

  const handleMenuClose = () => {
    setAnchorEl(null);
  };

  const handleSettingsOpen = () => {
    setSettingsOpen(true);
    handleMenuClose();
  };

  const handleForceSync = () => {
    onForceSync?.(true);
    handleMenuClose();
  };

  const handleExport = () => {
    onExport?.();
    handleMenuClose();
  };

  const handleImport = () => {
    onImport?.();
    handleMenuClose();
  };

  const handleViewHistory = () => {
    onViewHistory?.();
    handleMenuClose();
  };

  const handleAnalyze = () => {
    onAnalyze?.();
    handleMenuClose();
  };

  return (
    <Box>
      <Box display="flex" alignItems="center" gap={1}>
        {/* Primary Actions */}
        <ButtonGroup variant="outlined" size="small">
          <Tooltip title="Refresh portfolio data">
            <Button
              startIcon={<Refresh />}
              onClick={onRefresh}
              disabled={loading}
            >
              Refresh
            </Button>
          </Tooltip>
          
          <Tooltip title="Force sync from broker">
            <Button
              startIcon={<CloudSync />}
              onClick={() => onForceSync?.(true)}
              disabled={loading}
              color="primary"
            >
              Sync
            </Button>
          </Tooltip>
        </ButtonGroup>

        {/* Data Source Indicator */}
        {showDataSource && dataSource && (
          <Chip
            icon={
              dataSource.source === 'database' ? <Storage /> :
              dataSource.source === 'alpaca' ? <CloudSync /> :
              <Speed />
            }
            label={`${dataSource.source === 'database' ? 'Cached' : 
                   dataSource.source === 'alpaca' ? 'Live' : 'Direct'} 
                   ${dataSource.responseTime ? `(${dataSource.responseTime}ms)` : ''}`}
            size="small"
            variant="outlined"
            color={
              dataSource.source === 'database' ? 'success' :
              dataSource.source === 'alpaca' ? 'info' : 'warning'
            }
          />
        )}

        {/* More Actions Menu */}
        <Tooltip title="More actions">
          <IconButton onClick={handleMenuOpen}>
            <MoreVert />
          </IconButton>
        </Tooltip>
      </Box>

      {/* Actions Menu */}
      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={handleMenuClose}
        transformOrigin={{ horizontal: 'right', vertical: 'top' }}
        anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
      >
        <MenuItem onClick={handleAnalyze}>
          <ListItemIcon>
            <Analytics />
          </ListItemIcon>
          <ListItemText>Analyze Portfolio</ListItemText>
        </MenuItem>
        
        <MenuItem onClick={handleViewHistory}>
          <ListItemIcon>
            <History />
          </ListItemIcon>
          <ListItemText>Performance History</ListItemText>
        </MenuItem>
        
        <Divider />
        
        <MenuItem onClick={handleExport}>
          <ListItemIcon>
            <Download />
          </ListItemIcon>
          <ListItemText>Export Data</ListItemText>
        </MenuItem>
        
        <MenuItem onClick={handleImport}>
          <ListItemIcon>
            <Upload />
          </ListItemIcon>
          <ListItemText>Import Holdings</ListItemText>
        </MenuItem>
        
        <Divider />
        
        <MenuItem onClick={handleSettingsOpen}>
          <ListItemIcon>
            <Settings />
          </ListItemIcon>
          <ListItemText>Settings</ListItemText>
        </MenuItem>
      </Menu>

      {/* Settings Dialog */}
      <Dialog open={settingsOpen} onClose={() => setSettingsOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Portfolio Settings</DialogTitle>
        <DialogContent>
          <Box py={2}>
            <Typography variant="h6" gutterBottom>
              Data Refresh
            </Typography>
            
            <FormControlLabel
              control={
                <Switch
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                />
              }
              label="Auto-refresh portfolio data"
            />
            
            {autoRefresh && (
              <Box mt={2}>
                <Typography variant="body2" color="text.secondary">
                  Refresh interval: {refreshInterval} seconds
                </Typography>
                {/* Could add a slider here for interval selection */}
              </Box>
            )}
            
            <Box mt={3}>
              <Typography variant="h6" gutterBottom>
                Data Sources
              </Typography>
              
              <Typography variant="body2" color="text.secondary" paragraph>
                • Database Cache: Fastest response, may be up to 5 minutes old
              </Typography>
              <Typography variant="body2" color="text.secondary" paragraph>
                • Live Sync: Fresh data from broker, automatically cached
              </Typography>
              <Typography variant="body2" color="text.secondary" paragraph>
                • Direct API: Bypasses cache and sync service
              </Typography>
            </Box>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSettingsOpen(false)}>
            Close
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default EnhancedPortfolioActions;