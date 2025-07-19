import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Badge, IconButton, Popover, List, ListItem, ListItemText,
  ListItemIcon, Typography, Button, Chip, Divider, Card,
  CardContent, Stack, Fade, Slide
} from '@mui/material';
import {
  Notifications, NotificationsActive, TrendingUp, TrendingDown,
  Warning, Info, CheckCircle, Close, Delete, MarkAsUnread,
  Circle as CircleIcon
} from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';

const NotificationSystem = () => {
  const { user } = useAuth();
  const [anchorEl, setAnchorEl] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);

  // Load real notifications from API
  const loadNotifications = useCallback(async () => {
    try {
      const response = await fetch('/api/notifications', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('accessToken')}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          const formattedNotifications = data.data.map(notification => ({
            ...notification,
            time: new Date(notification.timestamp),
            icon: getNotificationIcon(notification.type, notification.priority)
          }));
          
          setNotifications(formattedNotifications);
          setUnreadCount(formattedNotifications.filter(n => !n.read).length);
          return;
        }
      }
    } catch (error) {
      console.error('Failed to load notifications:', error);
    }
    
    // If API fails, show empty state instead of mock data
    setNotifications([]);
    setUnreadCount(0);
  }, []);
  
  // Get appropriate icon for notification type
  const getNotificationIcon = (type, priority) => {
    switch (type) {
      case 'signal':
        return priority === 'high' ? 
          <TrendingUp color="success" /> : 
          <TrendingDown color="error" />;
      case 'portfolio':
        return <CheckCircle color="success" />;
      case 'warning':
        return <Warning color="warning" />;
      case 'info':
      default:
        return <Info color="info" />;
    }
  };

  useEffect(() => {
    loadNotifications();
    
    // Set up real-time notification polling
    const interval = setInterval(() => {
      loadNotifications();
    }, 30000); // Check for new notifications every 30 seconds

    return () => clearInterval(interval);
  }, [loadNotifications]);

  const handleClick = (event) => {
    setAnchorEl(event.currentTarget);
  };

  const handleClose = () => {
    setAnchorEl(null);
  };

  const markAsRead = (id) => {
    setNotifications(prev => 
      prev.map(notification => 
        notification.id === id 
          ? { ...notification, read: true }
          : notification
      )
    );
    setUnreadCount(prev => Math.max(0, prev - 1));
  };

  const markAllAsRead = () => {
    setNotifications(prev => 
      prev.map(notification => ({ ...notification, read: true }))
    );
    setUnreadCount(0);
  };

  const deleteNotification = (id) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
    const notification = notifications.find(n => n.id === id);
    if (notification && !notification.read) {
      setUnreadCount(prev => Math.max(0, prev - 1));
    }
  };

  const formatTime = (time) => {
    const now = new Date();
    const diff = now - time;
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (days > 0) return `${days}d ago`;
    if (hours > 0) return `${hours}h ago`;
    if (minutes > 0) return `${minutes}m ago`;
    return 'Just now';
  };

  const getPriorityColor = (priority) => {
    switch (priority) {
      case 'high': return 'error';
      case 'medium': return 'warning';
      case 'low': return 'info';
      default: return 'default';
    }
  };

  const open = Boolean(anchorEl);

  return (
    <>
      <IconButton onClick={handleClick} sx={{ position: 'relative' }}>
        <Badge badgeContent={unreadCount} color="error" max={99}>
          {unreadCount > 0 ? (
            <NotificationsActive color="primary" />
          ) : (
            <Notifications />
          )}
        </Badge>
      </IconButton>

      <Popover
        open={open}
        anchorEl={anchorEl}
        onClose={handleClose}
        anchorOrigin={{
          vertical: 'bottom',
          horizontal: 'right',
        }}
        transformOrigin={{
          vertical: 'top',
          horizontal: 'right',
        }}
        PaperProps={{
          sx: { 
            width: 400, 
            maxHeight: 500,
            mt: 1,
            borderRadius: 2,
            boxShadow: '0 8px 32px rgba(0,0,0,0.1)'
          }
        }}
      >
        <Box sx={{ p: 2 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <Typography variant="h6">Notifications</Typography>
            <Box sx={{ display: 'flex', gap: 1 }}>
              {unreadCount > 0 && (
                <Button size="small" onClick={markAllAsRead}>
                  Mark all read
                </Button>
              )}
              <IconButton size="small" onClick={handleClose}>
                <Close />
              </IconButton>
            </Box>
          </Box>

          <List sx={{ maxHeight: 350, overflow: 'auto' }}>
            {notifications.length === 0 ? (
              <ListItem>
                <ListItemText 
                  primary="No notifications"
                  secondary="You're all caught up!"
                />
              </ListItem>
            ) : (
              notifications.map((notification, index) => (
                <Fade in={true} timeout={300 + index * 100} key={notification.id}>
                  <Card
                    variant={notification.read ? 'outlined' : 'elevation'}
                    elevation={notification.read ? 0 : 1}
                    sx={{
                      mb: 1,
                      backgroundColor: notification.read ? 'grey.50' : 'background.paper',
                      border: notification.read ? '1px solid' : 'none',
                      borderColor: notification.read ? 'grey.300' : 'transparent',
                      cursor: 'pointer',
                      '&:hover': {
                        backgroundColor: notification.read ? 'grey.100' : 'primary.50'
                      }
                    }}
                    onClick={() => !notification.read && markAsRead(notification.id)}
                  >
                    <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
                        <Box sx={{ mt: 0.5 }}>
                          {notification.icon}
                        </Box>
                        <Box sx={{ flex: 1, minWidth: 0 }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                              {notification.title}
                            </Typography>
                            <Chip
                              label={notification.priority}
                              size="small"
                              color={getPriorityColor(notification.priority)}
                              sx={{ height: 18, fontSize: '0.65rem' }}
                            />
                            {!notification.read && (
                              <CircleIcon sx={{ fontSize: 8, color: 'primary.main' }} />
                            )}
                          </Box>
                          <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                            {notification.message}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {formatTime(notification.time)}
                          </Typography>
                        </Box>
                        <IconButton
                          size="small"
                          onClick={(e) => {
                            e.stopPropagation();
                            deleteNotification(notification.id);
                          }}
                          sx={{ opacity: 0.7, '&:hover': { opacity: 1 } }}
                        >
                          <Delete fontSize="small" />
                        </IconButton>
                      </Box>
                    </CardContent>
                  </Card>
                </Fade>
              ))
            )}
          </List>

          {notifications.length > 5 && (
            <Box sx={{ pt: 1, textAlign: 'center' }}>
              <Button size="small" variant="outlined" fullWidth>
                View All Notifications
              </Button>
            </Box>
          )}
        </Box>
      </Popover>
    </>
  );
};

export default NotificationSystem;