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
import { useQuery } from '@tanstack/react-query';
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
  const { data: newsData, isLoading, error, refetch } = useQuery({
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
    <div className="bg-white shadow-md rounded-lg" sx={{ height }}>
      <div className="bg-white shadow-md rounded-lg"Header
        title={
          <div  sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Language color="primary" />
            <div  variant="h6" fontWeight="bold">
              Market News
            </div>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
              label={categories.find(c => c.value === selectedCategory)?.label || 'Market'} 
              size="small" 
              color="primary"
            />
          </div>
        }
        action={
          <div  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <button className="p-2 rounded-full hover:bg-gray-100" onClick={handleRefresh} disabled={isLoading}>
              <Refresh />
            </button>
            <button className="p-2 rounded-full hover:bg-gray-100" onClick={handleMenuOpen}>
              <MoreVert />
            </button>
          </div>
        }
        sx={{ pb: 1 }}
      />
      
      <div className="absolute right-0 mt-2 w-48 bg-white rounded-md shadow-lg z-10"
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={handleMenuClose}
      >
        <option  disabled>
          <div  variant="caption">Categories</div>
        </option>
        <hr className="border-gray-200" />
        {categories.map(cat => (
          <option  
            key={cat.value} 
            onClick={() => handleCategoryChange(cat.value)}
            selected={selectedCategory === cat.value}
          >
            {cat.label}
          </option>
        ))}
      </div>

      <div className="bg-white shadow-md rounded-lg"Content sx={{ pt: 0, height: 'calc(100% - 64px)', overflow: 'hidden' }}>
        {isLoading && <div className="w-full bg-gray-200 rounded-full h-2" sx={{ mb: 2 }} />}
        
        {error && (
          <div  sx={{ textAlign: 'center', py: 2 }}>
            <div  color="error" variant="body2">
              Failed to load news. Using sample data.
            </div>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={handleRefresh} size="small" sx={{ mt: 1 }}>
              Retry
            </button>
          </div>
        )}

        <div  sx={{ height: '100%', overflow: 'auto' }}>
          <List dense>
            {(newsData || []).map((article, index) => (
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
                      <div  sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
                        <div  sx={{ flex: 1 }}>
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
                        </div>
                        <div  sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          {getSentimentIcon(article.sentiment)}
                          <button className="p-2 rounded-full hover:bg-gray-100" size="small" href={article.url} target="_blank">
                            <OpenInNew fontSize="small" />
                          </button>
                        </div>
                      </div>
                    }
                    secondary={
                      <div  sx={{ mt: 1 }}>
                        <div 
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
                        </div>
                        
                        <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1 }}>
                          <div  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                              label={article.source || 'News'}
                              size="small"
                              variant="outlined"
                              sx={{ fontSize: '0.7rem', height: 20 }}
                            />
                            {showSentiment && article.sentiment && (
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                                label={article.sentiment.label}
                                size="small"
                                color={getSentimentColor(article.sentiment)}
                                sx={{ fontSize: '0.7rem', height: 20 }}
                              />
                            )}
                          </div>
                          
                          <div  sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                            <Schedule fontSize="small" color="action" />
                            <div  variant="caption" color="text.secondary">
                              {formatTimeAgo(article.createdAt || article.publishedAt)}
                            </div>
                          </div>
                        </div>

                        {article.symbols && article.symbols.length > 0 && (
                          <div  sx={{ display: 'flex', gap: 0.5, mt: 1, flexWrap: 'wrap' }}>
                            {article.symbols.slice(0, 3).map(symbol => (
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                                key={symbol}
                                label={symbol}
                                size="small"
                                variant="outlined"
                                color="primary"
                                sx={{ fontSize: '0.65rem', height: 18 }}
                              />
                            ))}
                            {article.symbols.length > 3 && (
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                                label={`+${article.symbols.length - 3}`}
                                size="small"
                                variant="outlined"
                                sx={{ fontSize: '0.65rem', height: 18 }}
                              />
                            )}
                          </div>
                        )}
                      </div>
                    }
                  />
                </ListItem>
                {index < (newsData?.length || 0) - 1 && <hr className="border-gray-200" variant="inset" />}
              </React.Fragment>
            ))}
            
            {(!newsData || newsData.length === 0) && !isLoading && (
              <div  sx={{ textAlign: 'center', py: 4 }}>
                <div  color="text.secondary">
                  No news available at the moment
                </div>
              </div>
            )}
          </List>
        </div>
      </div>
    </div>
  );
};

export default NewsWidget;