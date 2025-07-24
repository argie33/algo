import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  Typography,
  Box,
  List,
  ListItem,
  ListItemText,
  Chip,
  IconButton,
  Menu,
  MenuItem,
  Divider,
  Avatar,
  LinearProgress,
  Link,
  Tooltip,
  Button
} from '@mui/material';
import {
  MoreVert,
  TrendingUp,
  TrendingDown,
  TrendingFlat,
  OpenInNew,
  Refresh,
  Schedule,
  Language
} from '@mui/icons-material';
import { useSimpleFetch } from '../hooks/useSimpleFetch.js';
import newsService from '../services/newsService';
import { formatDistanceToNow } from 'date-fns';

const NewsWidget = ({ 
  symbols = [], 
  category = null, 
  limit = 10, 
  height = 400,
  showSentiment = true,
  autoRefresh = true 
}) => {
  const [anchorEl, setAnchorEl] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState(category || 'market');

  // Fetch news data
  const { data: newsData, isLoading, error, refetch } = useSimpleFetch({
    queryKey: ['news', symbols, selectedCategory, limit],
    queryFn: async () => {
      if (selectedCategory === 'market') {
        return newsService.getMarketNews({ limit });
      } else if (symbols.length > 0) {
        return newsService.getNewsForSymbols(symbols, { limit });
      } else {
        return newsService.getNewsByCategory(selectedCategory, { limit });
      }
    },
    staleTime: 60 * 1000, // 1 minute
    refetchInterval: autoRefresh ? 60 * 1000 : false,
    retry: 1
  });

  const handleMenuOpen = (event) => {
    setAnchorEl(event.currentTarget);
  };

  const handleMenuClose = () => {
    setAnchorEl(null);
  };

  const handleCategoryChange = (category) => {
    setSelectedCategory(category);
    handleMenuClose();
  };

  const handleRefresh = () => {
    refetch();
  };

  const getSentimentIcon = (sentiment) => {
    if (!sentiment || !showSentiment) return null;
    
    switch (sentiment.label) {
      case 'positive':
        return <TrendingUp color="success" fontSize="small" />;
      case 'negative':
        return <TrendingDown color="error" fontSize="small" />;
      default:
        return <TrendingFlat color="action" fontSize="small" />;
    }
  };

  const getSentimentColor = (sentiment) => {
    if (!sentiment) return 'default';
    
    switch (sentiment.label) {
      case 'positive':
        return 'success';
      case 'negative':
        return 'error';
      default:
        return 'default';
    }
  };

  const formatTimeAgo = (dateString) => {
    try {
      return formatDistanceToNow(new Date(dateString), { addSuffix: true });
    } catch {
      return 'Recently';
    }
  };

  const categories = [
    { value: 'market', label: 'Market' },
    { value: 'technology', label: 'Tech' },
    { value: 'healthcare', label: 'Healthcare' },
    { value: 'energy', label: 'Energy' },
    { value: 'finance', label: 'Finance' },
    { value: 'crypto', label: 'Crypto' }
  ];

  return (
    <Card sx={{ height }}>
      <CardHeader
        title={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Language color="primary" />
            <Typography variant="h6" fontWeight="bold">
              Market News
            </Typography>
            <Chip 
              label={categories.find(c => c.value === selectedCategory)?.label || 'Market'} 
              size="small" 
              color="primary"
            />
          </Box>
        }
        action={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <IconButton onClick={handleRefresh} disabled={isLoading}>
              <Refresh />
            </IconButton>
            <IconButton onClick={handleMenuOpen}>
              <MoreVert />
            </IconButton>
          </Box>
        }
        sx={{ pb: 1 }}
      />
      
      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={handleMenuClose}
      >
        <MenuItem disabled>
          <Typography variant="caption">Categories</Typography>
        </MenuItem>
        <Divider />
        {categories.map(cat => (
          <MenuItem 
            key={cat.value} 
            onClick={() => handleCategoryChange(cat.value)}
            selected={selectedCategory === cat.value}
          >
            {cat.label}
          </MenuItem>
        ))}
      </Menu>

      <CardContent sx={{ pt: 0, height: 'calc(100% - 64px)', overflow: 'hidden' }}>
        {isLoading && <LinearProgress sx={{ mb: 2 }} />}
        
        {error && (
          <Box sx={{ textAlign: 'center', py: 2 }}>
            <Typography color="error" variant="body2">
              {error.message || 'Failed to load news. Please check your connection.'}
            </Typography>
            <Button onClick={handleRefresh} size="small" sx={{ mt: 1 }}>
              Retry
            </Button>
          </Box>
        )}

        <Box sx={{ height: '100%', overflow: 'auto' }}>
          <List dense>
            {(Array.isArray(newsData) ? newsData : newsData?.articles || []).map((article, index) => (
              <React.Fragment key={article.id || index}>
                <ListItem 
                  alignItems="flex-start"
                  sx={{ 
                    px: 0, 
                    py: 1.5,
                    '&:hover': { bgcolor: 'action.hover' },
                    borderRadius: 1
                  }}
                >
                  <ListItemText
                    primary={
                      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
                        <Box sx={{ flex: 1 }}>
                          <Link
                            href={article.url}
                            target="_blank"
                            rel="noopener"
                            underline="hover"
                            color="inherit"
                            sx={{ 
                              fontWeight: 600,
                              fontSize: '0.9rem',
                              lineHeight: 1.3,
                              display: '-webkit-box',
                              WebkitLineClamp: 2,
                              WebkitBoxOrient: 'vertical',
                              overflow: 'hidden'
                            }}
                          >
                            {article.headline}
                          </Link>
                        </Box>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          {getSentimentIcon(article.sentiment)}
                          <IconButton size="small" href={article.url} target="_blank">
                            <OpenInNew fontSize="small" />
                          </IconButton>
                        </Box>
                      </Box>
                    }
                    secondary={
                      <Box sx={{ mt: 1 }}>
                        <Typography
                          variant="body2"
                          color="text.secondary"
                          sx={{
                            fontSize: '0.8rem',
                            lineHeight: 1.3,
                            display: '-webkit-box',
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: 'vertical',
                            overflow: 'hidden',
                            mb: 1
                          }}
                        >
                          {article.summary}
                        </Typography>
                        
                        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1 }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <Chip
                              label={article.source || 'News'}
                              size="small"
                              variant="outlined"
                              sx={{ fontSize: '0.7rem', height: 20 }}
                            />
                            {showSentiment && article.sentiment && (
                              <Chip
                                label={article.sentiment.label}
                                size="small"
                                color={getSentimentColor(article.sentiment)}
                                sx={{ fontSize: '0.7rem', height: 20 }}
                              />
                            )}
                          </Box>
                          
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                            <Schedule fontSize="small" color="action" />
                            <Typography variant="caption" color="text.secondary">
                              {formatTimeAgo(article.createdAt || article.publishedAt)}
                            </Typography>
                          </Box>
                        </Box>

                        {article.symbols && article.symbols.length > 0 && (
                          <Box sx={{ display: 'flex', gap: 0.5, mt: 1, flexWrap: 'wrap' }}>
                            {article.symbols.slice(0, 3).map(symbol => (
                              <Chip
                                key={symbol}
                                label={symbol}
                                size="small"
                                variant="outlined"
                                color="primary"
                                sx={{ fontSize: '0.65rem', height: 18 }}
                              />
                            ))}
                            {article.symbols.length > 3 && (
                              <Chip
                                label={`+${article.symbols.length - 3}`}
                                size="small"
                                variant="outlined"
                                sx={{ fontSize: '0.65rem', height: 18 }}
                              />
                            )}
                          </Box>
                        )}
                      </Box>
                    }
                  />
                </ListItem>
                {index < ((Array.isArray(newsData) ? newsData : newsData?.articles || []).length) - 1 && <Divider variant="inset" />}
              </React.Fragment>
            ))}
            
            {(!newsData || newsData.length === 0) && !isLoading && (
              <Box sx={{ textAlign: 'center', py: 4 }}>
                <Typography color="text.secondary" variant="body2" sx={{ mb: 2 }}>
                  {newsData?.message || 'No news available at the moment'}
                </Typography>
                {newsData?.available_when_configured && (
                  <Box sx={{ mt: 2, textAlign: 'left', bgcolor: 'background.paper', p: 2, borderRadius: 1, border: '1px solid', borderColor: 'divider' }}>
                    <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600, mb: 1, display: 'block' }}>
                      Available when configured:
                    </Typography>
                    <Box component="ul" sx={{ m: 0, pl: 2, fontSize: '0.75rem', color: 'text.secondary' }}>
                      {newsData.available_when_configured.map((feature, idx) => (
                        <li key={idx} style={{ marginBottom: '4px' }}>{feature}</li>
                      ))}
                    </Box>
                  </Box>
                )}
              </Box>
            )}
          </List>
        </Box>
      </CardContent>
    </Card>
  );
};

export default NewsWidget;