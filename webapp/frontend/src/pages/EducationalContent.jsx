import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  CardMedia,
  IconButton,
  Button,
  Chip,
  LinearProgress,
  Stack,
  Paper,
  Divider,
  alpha,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Avatar,
  Tooltip,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  InputAdornment,
  Tabs,
  Tab,
  Rating,
  Accordion,
  AccordionSummary,
  AccordionDetails
} from '@mui/material';
import {
  School,
  PlayArrow,
  Article,
  Assessment,
  Timeline,
  Business,
  Search,
  Psychology,
  ShowChart,
  AttachMoney,
  Speed,
  CheckCircle,
  Refresh,
  CalendarToday,
  AccessTime,
  Person,
  Star,
  Bookmark,
  Share,
  ThumbUp,
  Comment,
  Visibility,
  ExpandMore,
  Quiz,
  MenuBook,
  TrendingUp,
  BarChart,
  PieChart,
  AccountBalance,
  Gavel,
  Security,
  Language,
  Calculate,
  VideoLibrary,
  LibraryBooks,
  Assignment
} from '@mui/icons-material';
import { api } from '../services/api';
import { formatDistanceToNow } from 'date-fns';

function TabPanel({ children, value, index }) {
  return (
    <div hidden={value !== index}>
      {value === index && <div  sx={{ py: 2 }}>{children}</div>}
    </div>
  );
}

const EducationalContent = () => {
  const [activeTab, setActiveTab] = useState(0);
  const [content, setContent] = useState([]);
  const [courses, setCourses] = useState([]);
  const [quizzes, setQuizzes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [difficulty, setDifficulty] = useState('all');
  const [category, setCategory] = useState('all');
  const [contentType, setContentType] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    loadEducationalContent();
    loadCourses();
    loadQuizzes();
  }, [difficulty, category, contentType]);

  const loadEducationalContent = async () => {
    setLoading(true);
    try {
      const response = await api.get('/research/education', {
        params: { difficulty, category, type: contentType }
      });
      setContent(response.data.content || []);
    } catch (error) {
      console.error('Error loading educational content:', error);
      setContent(getMockContent());
    } finally {
      setLoading(false);
    }
  };

  const loadCourses = async () => {
    try {
      const response = await api.get('/research/education/courses');
      setCourses(response.data.courses || []);
    } catch (error) {
      console.error('Error loading courses:', error);
      setCourses(getMockCourses());
    }
  };

  const loadQuizzes = async () => {
    try {
      const response = await api.get('/research/education/quizzes');
      setQuizzes(response.data.quizzes || []);
    } catch (error) {
      console.error('Error loading quizzes:', error);
      setQuizzes(getMockQuizzes());
    }
  };

  const getMockContent = () => {
    return [
      {
        id: 1,
        title: "Understanding P/E Ratios: A Complete Guide",
        type: "article",
        category: "fundamental-analysis",
        difficulty: "beginner",
        duration: 8,
        author: "Investment Education Team",
        publishedAt: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000),
        description: "Learn how to interpret price-to-earnings ratios and use them in your investment decisions.",
        content: "The price-to-earnings ratio is one of the most widely used valuation metrics...",
        tags: ["Valuation", "P/E Ratio", "Fundamental Analysis"],
        views: 15600,
        likes: 340,
        rating: 4.7,
        thumbnail: "/education/pe-ratio-guide.jpg",
        keyPoints: [
          "How to calculate P/E ratios",
          "Forward vs trailing P/E",
          "Industry comparisons",
          "Limitations of P/E analysis"
        ]
      },
      {
        id: 2,
        title: "Technical Analysis Basics: Reading Charts",
        type: "video",
        category: "technical-analysis",
        difficulty: "beginner",
        duration: 15,
        author: "Chart Analysis Expert",
        publishedAt: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000),
        description: "Master the fundamentals of reading stock charts and identifying key patterns.",
        content: "Technical analysis is the study of price movements through charts...",
        tags: ["Charts", "Patterns", "Technical Analysis", "Candlesticks"],
        views: 23400,
        likes: 580,
        rating: 4.8,
        thumbnail: "/education/chart-analysis.jpg",
        keyPoints: [
          "Candlestick patterns",
          "Support and resistance",
          "Trend identification",
          "Volume analysis"
        ]
      },
      {
        id: 3,
        title: "Portfolio Diversification Strategies",
        type: "course",
        category: "portfolio-management",
        difficulty: "intermediate",
        duration: 45,
        author: "Portfolio Management Team",
        publishedAt: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000),
        description: "Learn how to build a well-diversified portfolio to manage risk and optimize returns.",
        content: "Diversification is the only free lunch in investing...",
        tags: ["Diversification", "Risk Management", "Asset Allocation"],
        views: 18900,
        likes: 425,
        rating: 4.9,
        thumbnail: "/education/diversification.jpg",
        keyPoints: [
          "Asset class diversification",
          "Geographic diversification", 
          "Sector allocation",
          "Rebalancing strategies"
        ]
      },
      {
        id: 4,
        title: "Options Trading Fundamentals",
        type: "video",
        category: "derivatives",
        difficulty: "advanced",
        duration: 25,
        author: "Options Specialist",
        publishedAt: new Date(Date.now() - 10 * 24 * 60 * 60 * 1000),
        description: "Comprehensive introduction to options trading, strategies, and risk management.",
        content: "Options provide leverage and flexibility in trading strategies...",
        tags: ["Options", "Derivatives", "Advanced Trading", "Greeks"],
        views: 12300,
        likes: 290,
        rating: 4.6,
        thumbnail: "/education/options-trading.jpg",
        keyPoints: [
          "Call and put options",
          "Option pricing models",
          "Basic strategies",
          "Risk management"
        ]
      },
      {
        id: 5,
        title: "Economic Indicators and Market Impact",
        type: "article",
        category: "economics",
        difficulty: "intermediate",
        duration: 12,
        author: "Economic Research Team",
        publishedAt: new Date(Date.now() - 14 * 24 * 60 * 60 * 1000),
        description: "Understand key economic indicators and how they influence market movements.",
        content: "Economic indicators provide insights into the health of the economy...",
        tags: ["Economics", "Indicators", "Market Analysis", "GDP"],
        views: 16800,
        likes: 375,
        rating: 4.5,
        thumbnail: "/education/economic-indicators.jpg",
        keyPoints: [
          "Leading vs lagging indicators",
          "GDP and employment data",
          "Inflation metrics",
          "Market reaction patterns"
        ]
      }
    ];
  };

  const getMockCourses = () => {
    return [
      {
        id: 1,
        title: "Complete Stock Market Investing Course",
        description: "From beginner to advanced investor in 30 lessons",
        difficulty: "beginner",
        lessons: 30,
        duration: 480,
        students: 15600,
        rating: 4.8,
        instructor: "Sarah Johnson, CFA",
        price: "Free",
        thumbnail: "/courses/complete-investing.jpg",
        modules: [
          "Introduction to Stock Markets",
          "Fundamental Analysis",
          "Technical Analysis",
          "Portfolio Construction",
          "Risk Management"
        ],
        progress: 0
      },
      {
        id: 2,
        title: "Advanced Options Trading Strategies",
        description: "Master complex options strategies for experienced traders",
        difficulty: "advanced",
        lessons: 25,
        duration: 600,
        students: 4200,
        rating: 4.9,
        instructor: "Michael Chen, Options Specialist",
        price: "Premium",
        thumbnail: "/courses/options-strategies.jpg",
        modules: [
          "Options Greeks Deep Dive",
          "Volatility Trading",
          "Multi-Leg Strategies",
          "Risk Management",
          "Real Trading Examples"
        ],
        progress: 0
      },
      {
        id: 3,
        title: "Cryptocurrency Investment Fundamentals",
        description: "Understanding digital assets and blockchain technology",
        difficulty: "intermediate",
        lessons: 20,
        duration: 360,
        students: 8900,
        rating: 4.6,
        instructor: "Alex Rodriguez, Blockchain Expert",
        price: "Premium",
        thumbnail: "/courses/crypto-fundamentals.jpg",
        modules: [
          "Blockchain Technology",
          "Cryptocurrency Valuation",
          "DeFi and NFTs",
          "Portfolio Integration",
          "Regulatory Landscape"
        ],
        progress: 0
      }
    ];
  };

  const getMockQuizzes = () => {
    return [
      {
        id: 1,
        title: "Financial Ratios Quiz",
        category: "fundamental-analysis",
        difficulty: "beginner",
        questions: 15,
        duration: 10,
        attempts: 5420,
        averageScore: 78,
        description: "Test your knowledge of key financial ratios and their interpretations"
      },
      {
        id: 2,
        title: "Chart Pattern Recognition",
        category: "technical-analysis", 
        difficulty: "intermediate",
        questions: 20,
        duration: 15,
        attempts: 3280,
        averageScore: 65,
        description: "Identify common chart patterns and their trading implications"
      },
      {
        id: 3,
        title: "Options Strategy Assessment",
        category: "derivatives",
        difficulty: "advanced",
        questions: 25,
        duration: 20,
        attempts: 1560,
        averageScore: 72,
        description: "Advanced quiz on options strategies and risk management"
      }
    ];
  };

  const getDifficultyColor = (difficulty) => {
    switch (difficulty) {
      case 'beginner': return '#4caf50';
      case 'intermediate': return '#ff9800';
      case 'advanced': return '#f44336';
      default: return '#9e9e9e';
    }
  };

  const getTypeIcon = (type) => {
    switch (type) {
      case 'video': return <VideoLibrary />;
      case 'article': return <Article />;
      case 'course': return <School />;
      case 'quiz': return <Quiz />;
      default: return <LibraryBooks />;
    }
  };

  const filteredContent = content.filter(item => {
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return item.title.toLowerCase().includes(query) ||
             item.description.toLowerCase().includes(query) ||
             item.tags.some(tag => tag.toLowerCase().includes(query));
    }
    return true;
  });

  return (
    <div className="container mx-auto" maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      {/* Header */}
      <div  sx={{ mb: 4 }}>
        <div  variant="h4" fontWeight={700} gutterBottom>
          Educational Content
        </div>
        <div  variant="body1" color="text.secondary">
          Learn about investing and market analysis with our comprehensive educational resources
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid" container spacing={3} sx={{ mb: 4 }}>
        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center' }}>
              <LibraryBooks sx={{ fontSize: 40, color: 'primary.main', mb: 1 }} />
              <div  variant="h4" fontWeight={600}>250+</div>
              <div  variant="body2" color="text.secondary">Articles & Guides</div>
            </div>
          </div>
        </div>
        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center' }}>
              <VideoLibrary sx={{ fontSize: 40, color: 'primary.main', mb: 1 }} />
              <div  variant="h4" fontWeight={600}>150+</div>
              <div  variant="body2" color="text.secondary">Video Lessons</div>
            </div>
          </div>
        </div>
        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center' }}>
              <School sx={{ fontSize: 40, color: 'primary.main', mb: 1 }} />
              <div  variant="h4" fontWeight={600}>25+</div>
              <div  variant="body2" color="text.secondary">Complete Courses</div>
            </div>
          </div>
        </div>
        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center' }}>
              <Quiz sx={{ fontSize: 40, color: 'primary.main', mb: 1 }} />
              <div  variant="h4" fontWeight={600}>50+</div>
              <div  variant="body2" color="text.secondary">Practice Quizzes</div>
            </div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
        <div className="bg-white shadow-md rounded-lg"Content>
          <div className="grid" container spacing={2} alignItems="center">
            <div className="grid" item xs={12} md={3}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                fullWidth
                size="small"
                placeholder="Search content..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <Search />
                    </InputAdornment>
                  )
                }}
              />
            </div>
            <div className="grid" item xs={12} md={2}>
              <div className="mb-4" fullWidth size="small">
                <label className="block text-sm font-medium text-gray-700 mb-1">Difficulty</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={difficulty}
                  label="Difficulty"
                  onChange={(e) => setDifficulty(e.target.value)}
                >
                  <option  value="all">All Levels</option>
                  <option  value="beginner">Beginner</option>
                  <option  value="intermediate">Intermediate</option>
                  <option  value="advanced">Advanced</option>
                </select>
              </div>
            </div>
            <div className="grid" item xs={12} md={2}>
              <div className="mb-4" fullWidth size="small">
                <label className="block text-sm font-medium text-gray-700 mb-1">Category</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={category}
                  label="Category"
                  onChange={(e) => setCategory(e.target.value)}
                >
                  <option  value="all">All Categories</option>
                  <option  value="fundamental-analysis">Fundamental Analysis</option>
                  <option  value="technical-analysis">Technical Analysis</option>
                  <option  value="portfolio-management">Portfolio Management</option>
                  <option  value="derivatives">Derivatives</option>
                  <option  value="economics">Economics</option>
                  <option  value="risk-management">Risk Management</option>
                </select>
              </div>
            </div>
            <div className="grid" item xs={12} md={2}>
              <div className="mb-4" fullWidth size="small">
                <label className="block text-sm font-medium text-gray-700 mb-1">Content Type</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={contentType}
                  label="Content Type"
                  onChange={(e) => setContentType(e.target.value)}
                >
                  <option  value="all">All Types</option>
                  <option  value="article">Articles</option>
                  <option  value="video">Videos</option>
                  <option  value="course">Courses</option>
                  <option  value="quiz">Quizzes</option>
                </select>
              </div>
            </div>
            <div className="grid" item xs={12} md={3}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="outlined"
                startIcon={<Refresh />}
                onClick={() => { loadEducationalContent(); loadCourses(); loadQuizzes(); }}
                fullWidth
              >
                Refresh Content
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content Tabs */}
      <div className="bg-white shadow-md rounded-lg">
        <div className="bg-white shadow-md rounded-lg"Content sx={{ pb: 0 }}>
          <div className="border-b border-gray-200" value={activeTab} onChange={(e, val) => setActiveTab(val)}>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="All Content" icon={<LibraryBooks />} iconPosition="start" />
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Courses" icon={<School />} iconPosition="start" />
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Quizzes" icon={<Quiz />} iconPosition="start" />
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Learning Paths" icon={<Timeline />} iconPosition="start" />
          </div>
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={0}>
          <div  sx={{ p: 3 }}>
            <div className="grid" container spacing={3}>
              {filteredContent.map((item) => (
                <div className="grid" item xs={12} md={6} lg={4} key={item.id}>
                  <div className="bg-white shadow-md rounded-lg" sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                    <div className="bg-white shadow-md rounded-lg"Media
                      component="div"
                      sx={{
                        height: 140,
                        bgcolor: '#1976d21A',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center'
                      }}
                    >
                      {getTypeIcon(item.type)}
                    </CardMedia>
                    <div className="bg-white shadow-md rounded-lg"Content sx={{ flexGrow: 1 }}>
                      <div className="flex flex-col space-y-2" spacing={1}>
                        <div  sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                          <div  variant="h6" component="h3" gutterBottom>
                            {item.title}
                          </div>
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                            label={item.difficulty}
                            size="small"
                            sx={{
                              bgcolor: getDifficultyColor(item.difficulty) + '1A',
                              color: getDifficultyColor(item.difficulty),
                              textTransform: 'capitalize'
                            }}
                          />
                        </div>
                        <div  variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                          {item.description}
                        </div>
                        <div className="flex flex-col space-y-2" direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
                          <AccessTime sx={{ fontSize: 16 }} />
                          <div  variant="caption">{item.duration} min</div>
                          <Person sx={{ fontSize: 16 }} />
                          <div  variant="caption">{item.author}</div>
                        </div>
                        <div  sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                          <Rating value={item.rating} precision={0.1} size="small" readOnly />
                          <div  variant="caption">({item.rating})</div>
                          <div  variant="caption">• {item.views.toLocaleString()} views</div>
                        </div>
                        <div className="flex flex-col space-y-2" direction="row" spacing={1} flexWrap="wrap">
                          {item.tags.slice(0, 3).map(tag => (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" key={tag} label={tag} size="small" variant="outlined" />
                          ))}
                        </div>
                      </div>
                    </div>
                    <div  sx={{ p: 2, pt: 0 }}>
                      <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="contained" fullWidth startIcon={<PlayArrow />}>
                        Start Learning
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={1}>
          <div  sx={{ p: 3 }}>
            <div className="grid" container spacing={3}>
              {courses.map((course) => (
                <div className="grid" item xs={12} md={6} key={course.id}>
                  <div className="bg-white shadow-md rounded-lg">
                    <div className="bg-white shadow-md rounded-lg"Content>
                      <div  variant="h6" gutterBottom>{course.title}</div>
                      <div  variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                        {course.description}
                      </div>
                      <div className="grid" container spacing={2} sx={{ mb: 2 }}>
                        <div className="grid" item xs={6}>
                          <div  variant="caption" color="text.secondary">Lessons</div>
                          <div  variant="body2" fontWeight={600}>{course.lessons}</div>
                        </div>
                        <div className="grid" item xs={6}>
                          <div  variant="caption" color="text.secondary">Duration</div>
                          <div  variant="body2" fontWeight={600}>{Math.floor(course.duration / 60)}h {course.duration % 60}m</div>
                        </div>
                        <div className="grid" item xs={6}>
                          <div  variant="caption" color="text.secondary">Students</div>
                          <div  variant="body2" fontWeight={600}>{course.students.toLocaleString()}</div>
                        </div>
                        <div className="grid" item xs={6}>
                          <div  variant="caption" color="text.secondary">Rating</div>
                          <div  sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                            <Rating value={course.rating} precision={0.1} size="small" readOnly />
                            <div  variant="body2">({course.rating})</div>
                          </div>
                        </div>
                      </div>
                      <div  variant="caption" color="text.secondary">Instructor: {course.instructor}</div>
                      <Accordion sx={{ mt: 2 }}>
                        <AccordionSummary expandIcon={<ExpandMore />}>
                          <div  variant="body2">Course Modules</div>
                        </AccordionSummary>
                        <AccordionDetails>
                          <List dense>
                            {course.modules.map((module, index) => (
                              <ListItem key={index}>
                                <ListItemIcon>
                                  <CheckCircle sx={{ fontSize: 16, color: 'success.main' }} />
                                </ListItemIcon>
                                <ListItemText primary={module} />
                              </ListItem>
                            ))}
                          </List>
                        </AccordionDetails>
                      </Accordion>
                      <div  sx={{ mt: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                          label={course.price}
                          color={course.price === 'Free' ? 'success' : 'primary'}
                          variant={course.price === 'Free' ? 'filled' : 'outlined'}
                        />
                        <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="contained" size="small">
                          {course.price === 'Free' ? 'Start Free' : 'Enroll Now'}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={2}>
          <div  sx={{ p: 3 }}>
            <div className="grid" container spacing={3}>
              {quizzes.map((quiz) => (
                <div className="grid" item xs={12} md={4} key={quiz.id}>
                  <div className="bg-white shadow-md rounded-lg">
                    <div className="bg-white shadow-md rounded-lg"Content>
                      <div  variant="h6" gutterBottom>{quiz.title}</div>
                      <div  variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                        {quiz.description}
                      </div>
                      <div className="flex flex-col space-y-2" spacing={1} sx={{ mb: 2 }}>
                        <div  sx={{ display: 'flex', justifyContent: 'space-between' }}>
                          <div  variant="caption">Questions:</div>
                          <div  variant="caption" fontWeight={600}>{quiz.questions}</div>
                        </div>
                        <div  sx={{ display: 'flex', justifyContent: 'space-between' }}>
                          <div  variant="caption">Duration:</div>
                          <div  variant="caption" fontWeight={600}>{quiz.duration} min</div>
                        </div>
                        <div  sx={{ display: 'flex', justifyContent: 'space-between' }}>
                          <div  variant="caption">Attempts:</div>
                          <div  variant="caption" fontWeight={600}>{quiz.attempts.toLocaleString()}</div>
                        </div>
                        <div  sx={{ display: 'flex', justifyContent: 'space-between' }}>
                          <div  variant="caption">Avg Score:</div>
                          <div  variant="caption" fontWeight={600}>{quiz.averageScore}%</div>
                        </div>
                      </div>
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                        label={quiz.difficulty}
                        size="small"
                        sx={{
                          bgcolor: getDifficultyColor(quiz.difficulty) + '1A',
                          color: getDifficultyColor(quiz.difficulty),
                          textTransform: 'capitalize',
                          mb: 2
                        }}
                      />
                      <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="outlined" fullWidth startIcon={<Assignment />}>
                        Take Quiz
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={3}>
          <div  sx={{ p: 3 }}>
            <div  variant="h6" gutterBottom>Structured Learning Paths</div>
            <div className="grid" container spacing={3}>
              <div className="grid" item xs={12} md={6}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div  variant="h6" gutterBottom>Beginner Investor Path</div>
                    <div  variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      Complete beginner's guide to stock market investing
                    </div>
                    <List dense>
                      <ListItem>
                        <ListItemIcon><School sx={{ fontSize: 16 }} /></ListItemIcon>
                        <ListItemText primary="Introduction to Stock Markets" secondary="2 hours" />
                      </ListItem>
                      <ListItem>
                        <ListItemIcon><Assessment sx={{ fontSize: 16 }} /></ListItemIcon>
                        <ListItemText primary="Understanding Financial Statements" secondary="3 hours" />
                      </ListItem>
                      <ListItem>
                        <ListItemIcon><ShowChart sx={{ fontSize: 16 }} /></ListItemIcon>
                        <ListItemText primary="Basic Technical Analysis" secondary="2 hours" />
                      </ListItem>
                      <ListItem>
                        <ListItemIcon><AccountBalance sx={{ fontSize: 16 }} /></ListItemIcon>
                        <ListItemText primary="Portfolio Construction Basics" secondary="2 hours" />
                      </ListItem>
                    </List>
                    <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="contained" fullWidth sx={{ mt: 2 }}>
                      Start Path
                    </button>
                  </div>
                </div>
              </div>
              <div className="grid" item xs={12} md={6}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div  variant="h6" gutterBottom>Advanced Trading Path</div>
                    <div  variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      Advanced strategies for experienced traders
                    </div>
                    <List dense>
                      <ListItem>
                        <ListItemIcon><Psychology sx={{ fontSize: 16 }} /></ListItemIcon>
                        <ListItemText primary="Advanced Options Strategies" secondary="4 hours" />
                      </ListItem>
                      <ListItem>
                        <ListItemIcon><BarChart sx={{ fontSize: 16 }} /></ListItemIcon>
                        <ListItemText primary="Quantitative Analysis" secondary="3 hours" />
                      </ListItem>
                      <ListItem>
                        <ListItemIcon><Security sx={{ fontSize: 16 }} /></ListItemIcon>
                        <ListItemText primary="Risk Management" secondary="2 hours" />
                      </ListItem>
                      <ListItem>
                        <ListItemIcon><Calculate sx={{ fontSize: 16 }} /></ListItemIcon>
                        <ListItemText primary="Algorithmic Trading Basics" secondary="3 hours" />
                      </ListItem>
                    </List>
                    <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="contained" fullWidth sx={{ mt: 2 }}>
                      Start Path
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default EducationalContent;