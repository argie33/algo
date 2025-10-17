import React from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  Box,
  Chip,
  Tooltip,
  Paper,
  Button,
} from '@mui/material';
import { formatCellValue, getCellAlign, getDynamicColumns } from '../utils/signalTableHelpers';

/**
 * Reusable dynamic signal table component
 * Automatically renders all available columns from signal data
 */
export const DynamicSignalTable = ({
  signals = [],
  maxRows = 10,
  onSymbolClick = null,
  customPriorityColumns = null,
  stickyHeader = true,
  maxHeight = 600,
}) => {
  if (!signals || signals.length === 0) {
    return (
      <Box sx={{ p: 4, textAlign: "center" }}>
        <Typography variant="body2" color="text.secondary">
          No signals available
        </Typography>
      </Box>
    );
  }

  const columns = getDynamicColumns(signals, customPriorityColumns);

  const renderCellContent = (signal, colKey) => {
    const value = signal[colKey];

    // Handle symbol column - make it clickable if handler provided
    if (colKey === 'symbol' && onSymbolClick) {
      return (
        <Button
          variant="text"
          size="small"
          sx={{ fontWeight: 'bold', minWidth: 'auto', p: 0.5 }}
          onClick={() => onSymbolClick(signal.symbol)}
        >
          {value}
        </Button>
      );
    }

    // Handle signal column - show as chip
    if (colKey === 'signal') {
      const isBuy = (value || '').toUpperCase() === 'BUY';
      const isSell = (value || '').toUpperCase() === 'SELL';
      return (
        <Chip
          label={value || 'N/A'}
          size="small"
          color={isBuy ? 'success' : isSell ? 'error' : 'default'}
        />
      );
    }

    // Format value intelligently
    return formatCellValue(value, colKey);
  };

  return (
    <TableContainer
      component={Paper}
      elevation={0}
      sx={{ maxHeight, overflowY: 'auto', overflowX: 'auto' }}
    >
      <Table size="small" stickyHeader={stickyHeader}>
        <TableHead>
          <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
            {columns.map((col) => (
              <TableCell
                key={col}
                align={getCellAlign(col)}
                sx={{
                  fontWeight: 'bold',
                  whiteSpace: 'nowrap',
                  minWidth: '100px',
                }}
              >
                <Tooltip title={col} placement="top">
                  <span>{col.replace(/_/g, ' ').toUpperCase()}</span>
                </Tooltip>
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {signals.slice(0, maxRows).map((signal, index) => (
            <TableRow key={`${signal.symbol}-${index}`} hover>
              {columns.map((col) => (
                <TableCell
                  key={`${signal.symbol}-${col}`}
                  align={getCellAlign(col)}
                  sx={{ whiteSpace: 'nowrap' }}
                >
                  <Typography variant="caption">
                    {renderCellContent(signal, col)}
                  </Typography>
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
};

export default DynamicSignalTable;
