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

  // Mock notifications - in real app, these would come from API/WebSocket
  const generateMockNotifications = useCallback(() => {
    const mockNotifications = [
      {
        id: 1,
        type: 'signal',
        title: 'New Buy Signal',
        message: 'AAPL showing strong bullish momentum',
        time: new Date(Date.now() - 5 * 60 * 1000), // 5 minutes ago
        read: false,
        priority: 'high',
        icon: <TrendingUp color="success" />
      },
      {
        id: 2,
        type: 'portfolio',
        title: 'Portfolio Update',
        message: 'Your portfolio gained 2.3% today',
        time: new Date(Date.now() - 15 * 60 * 1000), // 15 minutes ago
        read: false,
        priority: 'medium',
        icon: <CheckCircle color="success" />
      },
      {
        id: 3,
        type: 'warning',
        title: 'Risk Alert',
        message: 'High volatility detected in TSLA',
        time: new Date(Date.now() - 30 * 60 * 1000), // 30 minutes ago
        read: true,
        priority: 'high',
        icon: <Warning color="warning" />
      },
      {
        id: 4,
        type: 'info',
        title: 'Market Update',
        message: 'S&P 500 approaching resistance level',
        time: new Date(Date.now() - 60 * 60 * 1000), // 1 hour ago
        read: true,
        priority: 'low',
        icon: <Info color="info" />
      },
      {
        id: 5,
        type: 'signal',
        title: 'Sell Signal',
        message: 'Consider taking profits on NVDA',
        time: new Date(Date.now() - 2 * 60 * 60 * 1000), // 2 hours ago
        read: false,
        priority: 'high',
        icon: <TrendingDown color="error" />
      }
    ];

    setNotifications(mockNotifications);
    setUnreadCount(mockNotifications.filter(n => !n.read).length);
  }, []);

  useEffect(() => {
    generateMockNotifications();
    
    // Simulate real-time notifications
    const interval = setInterval(() => {
      const newNotification = {
        id: Date.now(),
        type: 'signal',
        title: 'Live Update',
        message: 'Market conditions changing',
        time: new Date(),
        read: false,
        priority: 'medium',
        icon: <Info color="info" />
      };
      
      setNotifications(prev => [newNotification, ...prev].slice(0, 10)); // Keep only latest 10
      setUnreadCount(prev => prev + 1);
    }, 30000); // Every 30 seconds

    return () => clearInterval(interval);
  }, [generateMockNotifications]);

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
      <button className="p-2 rounded-full hover:bg-gray-100" onClick={handleClick} sx={{ position: 'relative' }}>
        <span className="inline-flex items-center justify-center px-2 py-1 text-xs font-bold leading-none text-red-100 bg-red-600 rounded-full" badgeContent={unreadCount} color="error" max={99}>
          {unreadCount > 0 ? (
            <NotificationsActive color="primary" />
          ) : (
            <Notifications />
          )}
        </span>
      </button>

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
        <div  sx={{ p: 2 }}>
          <div  sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <div  variant="h6">Notifications</div>
            <div  sx={{ display: 'flex', gap: 1 }}>
              {unreadCount > 0 && (
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" size="small" onClick={markAllAsRead}>
                  Mark all read
                </button>
              )}
              <button className="p-2 rounded-full hover:bg-gray-100" size="small" onClick={handleClose}>
                <Close />
              </button>
            </div>
          </div>

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
                  <div className="bg-white shadow-md rounded-lg"
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
                    <div className="bg-white shadow-md rounded-lg"Content sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                      <div  sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
                        <div  sx={{ mt: 0.5 }}>
                          {notification.icon}
                        </div>
                        <div  sx={{ flex: 1, minWidth: 0 }}>
                          <div  sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                            <div  variant="subtitle2" sx={{ fontWeight: 600 }}>
                              {notification.title}
                            </div>
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                              label={notification.priority}
                              size="small"
                              color={getPriorityColor(notification.priority)}
                              sx={{ height: 18, fontSize: '0.65rem' }}
                            />
                            {!notification.read && (
                              <CircleIcon sx={{ fontSize: 8, color: 'primary.main' }} />
                            )}
                          </div>
                          <div  variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                            {notification.message}
                          </div>
                          <div  variant="caption" color="text.secondary">
                            {formatTime(notification.time)}
                          </div>
                        </div>
                        <button className="p-2 rounded-full hover:bg-gray-100"
                          size="small"
                          onClick={(e) => {
                            e.stopPropagation();
                            deleteNotification(notification.id);
                          }}
                          sx={{ opacity: 0.7, '&:hover': { opacity: 1 } }}
                        >
                          <Delete fontSize="small" />
                        </button>
                      </div>
                    </div>
                  </div>
                </Fade>
              ))
            )}
          </List>

          {notifications.length > 5 && (
            <div  sx={{ pt: 1, textAlign: 'center' }}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" size="small" variant="outlined" fullWidth>
                View All Notifications
              </button>
            </div>
          )}
        </div>
      </Popover>
    </>
  );
};

export default NotificationSystem;