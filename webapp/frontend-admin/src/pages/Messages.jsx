import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Typography,
  CircularProgress,
  Alert,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { formatDistanceToNow } from 'date-fns';

const Messages = () => {
  const theme = useTheme();
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedMessage, setSelectedMessage] = useState(null);
  const [openDialog, setOpenDialog] = useState(false);

  // Fetch messages
  useEffect(() => {
    const fetchMessages = async () => {
      try {
        setLoading(true);
        const response = await fetch('/api/contact/submissions');
        const result = await response.json();

        if (!response.ok) {
          throw new Error(result.error || 'Failed to fetch messages');
        }

        setMessages(result.data.submissions || []);
        setError(null);
      } catch (err) {
        console.error('Error fetching messages:', err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchMessages();
  }, []);

  const handleOpenDialog = (message) => {
    setSelectedMessage(message);
    setOpenDialog(true);
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
    setSelectedMessage(null);
  };

  const handleStatusChange = async (id, newStatus) => {
    try {
      const response = await fetch(`/api/contact/submissions/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus })
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error);
      }

      // Update local state
      setMessages(messages.map(msg => 
        msg.id === id ? { ...msg, status: newStatus, reviewed_at: new Date() } : msg
      ));

      if (selectedMessage?.id === id) {
        setSelectedMessage({ ...selectedMessage, status: newStatus });
      }
    } catch (err) {
      console.error('Error updating message:', err);
      alert(`Failed to update message: ${err.message}`);
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'new':
        return 'primary';
      case 'reviewed':
        return 'success';
      case 'archived':
        return 'default';
      default:
        return 'default';
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" sx={{ mb: 3, fontWeight: 700 }}>
        📧 Contact Form Submissions
      </Typography>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {messages.length === 0 ? (
        <Alert severity="info">No messages received yet</Alert>
      ) : (
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow sx={{ backgroundColor: theme.palette.primary.main + '10' }}>
                <TableCell sx={{ fontWeight: 700 }}>Date</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Name</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Email</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Subject</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Status</TableCell>
                <TableCell sx={{ fontWeight: 700, textAlign: 'center' }}>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {messages.map((message) => (
                <TableRow key={message.id} hover>
                  <TableCell>
                    {formatDistanceToNow(new Date(message.submitted_at), { addSuffix: true })}
                  </TableCell>
                  <TableCell>{message.name}</TableCell>
                  <TableCell>{message.email}</TableCell>
                  <TableCell>{message.subject || '—'}</TableCell>
                  <TableCell>
                    <Chip
                      label={message.status}
                      color={getStatusColor(message.status)}
                      size="small"
                    />
                  </TableCell>
                  <TableCell sx={{ textAlign: 'center' }}>
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={() => handleOpenDialog(message)}
                    >
                      View
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* Message Detail Dialog */}
      <Dialog open={openDialog} onClose={handleCloseDialog} maxWidth="sm" fullWidth>
        <DialogTitle>Message Details</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          {selectedMessage && (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <Box>
                <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>From:</Typography>
                <Typography>{selectedMessage.name} ({selectedMessage.email})</Typography>
              </Box>
              {selectedMessage.subject && (
                <Box>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>Subject:</Typography>
                  <Typography>{selectedMessage.subject}</Typography>
                </Box>
              )}
              <Box>
                <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>Message:</Typography>
                <Typography sx={{ whiteSpace: 'pre-wrap', mt: 1 }}>
                  {selectedMessage.message}
                </Typography>
              </Box>
              <Box>
                <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>Status:</Typography>
                <Box sx={{ mt: 1, display: 'flex', gap: 1 }}>
                  <Button
                    size="small"
                    variant={selectedMessage.status === 'new' ? 'contained' : 'outlined'}
                    onClick={() => handleStatusChange(selectedMessage.id, 'new')}
                  >
                    New
                  </Button>
                  <Button
                    size="small"
                    variant={selectedMessage.status === 'reviewed' ? 'contained' : 'outlined'}
                    onClick={() => handleStatusChange(selectedMessage.id, 'reviewed')}
                  >
                    Reviewed
                  </Button>
                  <Button
                    size="small"
                    variant={selectedMessage.status === 'archived' ? 'contained' : 'outlined'}
                    onClick={() => handleStatusChange(selectedMessage.id, 'archived')}
                  >
                    Archived
                  </Button>
                </Box>
              </Box>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default Messages;
