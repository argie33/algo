import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  Card,
  CardContent,
  Switch,
  FormControlLabel,
  Button,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Autocomplete,
  Alert,
  LinearProgress,
  IconButton,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Tabs,
  Tab,
  Badge,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  CircularProgress,
  Avatar,
  Snackbar,
  AlertTitle,
  Stack,
  ButtonGroup,
  Skeleton,
  CardHeader,
  CardActions,
  Fade,
  Grow,
  Zoom,
  Collapse,
  useTheme,
  alpha,
  styled,
  keyframes
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  PlayArrow,
  Stop,
  Settings,
  Analytics,
  Speed,
  SignalWifi4Bar,
  SignalWifiOff,
  Refresh,
  Add,
  Delete,
  Timeline,
  ShowChart,
  MonetizationOn,
  Assessment,
  Warning,
  CheckCircle,
  Error,
  Info,
  AdminPanelSettings,
  Dashboard,
  Storage,
  NetworkCheck,
  CloudSync,
  DataUsage,
  Security,
  Notifications,
  Schedule,
  ExpandMore,
  MoreVert,
  Power,
  PowerOff,
  Restore,
  ClearAll,
  Build,
  HealthAndSafety,
  TrendingFlat,
  SyncAlt,
  AutoFixHigh,
  ReportProblem,
  OnlinePrediction,
  FlashOn,
  FlashOff,
  Bolt,
  Whatshot,
  Wifi,
  WifiOff,
  SignalWifi3Bar,
  SignalWifi2Bar,
  SignalWifi1Bar,
  Tune,
  AutoMode,
  ManualMode,
  SmartToy,
  Psychology,
  Insights,
  Visibility,
  VisibilityOff,
  PauseCircle,
  PlayCircle,
  StopCircle,
  RestartAlt,
  Update,
  Cached,
  LightMode,
  DarkMode,
  Fullscreen,
  FullscreenExit,
  PictureInPicture,
  Close,
  Maximize,
  Minimize,
  Launch,
  OpenInNew,
  ZoomIn,
  ZoomOut,
  FilterAlt,
  Sort,
  ViewColumn,
  ViewList,
  ViewModule,
  GridView,
  TableView,
  BarChart,
  DonutSmall,
  PieChart,
  MultilineChart,
  Equalizer,
  CandlestickChart,
  TrendingUpTwoTone,
  TrendingDownTwoTone,
  FlashOnTwoTone,
  WifiTwoTone,
  MonitorHeart,
  ElectricBolt,
  RocketLaunch,
  Subscriptions,
  Stream,
  LiveTv,
  Sensors,
  Hub,
  Router,
  Cable,
  Podcasts,
  Radio,
  Cast,
  CastConnected,
  ConnectedTv,
  Bluetooth,
  BluetoothConnected,
  SignalCellular4Bar,
  SignalCellularConnectedNoInternet4Bar,
  SignalCellularNoSim,
  SignalCellularOff,
  FiberManualRecord,
  FiberSmartRecord,
  RadioButtonChecked,
  RadioButtonUnchecked,
  FlashAuto,
  AutoAwesome,
  AutoAwesomeMotion,
  AutoFixNormal,
  AutoFixOff,
  AutoGraph,
  AutoStories,
  QueryStats,
  Analytics as AnalyticsIcon,
  Insights as InsightsIcon,
  MonitorWeight,
  Memory,
  Dns,
  CloudQueue,
  CloudDone,
  CloudOff,
  CloudDownload,
  CloudUpload,
  Sync,
  SyncProblem,
  SyncDisabled,
  CheckCircleOutline,
  ErrorOutline,
  WarningAmber,
  InfoOutlined,
  HelpOutline,
  NotificationsActive,
  NotificationsOff,
  VolumeUp,
  VolumeOff,
  VolumeMute,
  VolumeDown,
  Alarm,
  AlarmOn,
  AlarmOff,
  Timer,
  TimerOff,
  Timelapse,
  Schedule as ScheduleIcon,
  AccessTime,
  History,
  Today,
  DateRange,
  CalendarToday,
  Event,
  EventNote,
  EventAvailable,
  EventBusy,
  Pending,
  PendingActions,
  HourglassBottom,
  HourglassTop,
  HourglassEmpty,
  HourglassFull,
  WatchLater,
  MoreTime,
  UpdateDisabled,
  Autorenew,
  Loop,
  Repeat,
  RepeatOne,
  RepeatOn,
  Shuffle,
  ShuffleOn,
  SkipNext,
  SkipPrevious,
  FastForward,
  FastRewind,
  Forward,
  Replay,
  Replay10,
  Replay30,
  Forward10,
  Forward30,
  Speed as SpeedIcon,
  SlowMotionVideo,
  NavigateNext,
  NavigateBefore,
  FirstPage,
  LastPage,
  ChevronLeft,
  ChevronRight,
  ExpandLess,
  ExpandCircleDown,
  UnfoldMore,
  UnfoldLess,
  DoubleArrow,
  ArrowUpward,
  ArrowDownward,
  ArrowForward,
  ArrowBack,
  NorthEast,
  SouthEast,
  NorthWest,
  SouthWest,
  CallMade,
  CallReceived,
  TrendingNeutral,
  Moving,
  OpenWith,
  PanTool,
  TouchApp,
  Gesture,
  SwipeUp,
  SwipeDown,
  SwipeLeft,
  SwipeRight,
  SwipeVertical,
  SwipeDownAlt,
  SwipeUpAlt,
  SwipeLeftAlt,
  SwipeRightAlt,
  PinchZoomIn,
  PinchZoomOut,
  Compress,
  Expand,
  Height,
  Width,
  AspectRatio,
  CropFree,
  Crop,
  CropSquare,
  CropPortrait,
  CropLandscape,
  Crop32,
  Crop54,
  Crop75,
  CropDin,
  CropOriginal,
  CropRotate,
  Rotate90DegreesCcw,
  Rotate90DegreesCw,
  RotateLeft,
  RotateRight,
  Flip,
  FlipToBack,
  FlipToFront,
  Transform,
  Animation,
  Motion,
  MotionPhotos,
  MotionPhotosOn,
  MotionPhotosOff,
  MotionPhotosPause,
  MotionPhotosAuto,
  LiveHelp,
  LiveHelpOutlined,
  LiveHelpRounded,
  LiveHelpSharp,
  LiveHelpTwoTone,
  LiveTvRounded,
  LiveTvSharp,
  LiveTvTwoTone,
  LiveTvOutlined,
  BroadcastOnHome,
  BroadcastOnPersonal,
  VideoCameraFront,
  VideoCameraBack,
  Videocam,
  VideocamOff,
  VideoCall,
  VideoCallOutlined,
  VideoCallRounded,
  VideoCallSharp,
  VideoCallTwoTone,
  VideoSettings,
  VideoLibrary,
  VideoFile,
  VideoLabel,
  Theaters,
  Movie,
  MovieCreation,
  MovieFilter,
  LocalMovies,
  RecentActors,
  PermMedia,
  Collections,
  CollectionsBookmark,
  Folder,
  FolderOpen,
  FolderSpecial,
  FolderShared,
  CreateNewFolder,
  Topic,
  Label,
  LabelImportant,
  LabelOff,
  Bookmark,
  BookmarkBorder,
  BookmarkAdd,
  BookmarkAdded,
  BookmarkRemove,
  Bookmarks,
  BookmarksOutlined,
  BookmarksRounded,
  BookmarksSharp,
  BookmarksTwoTone,
  Star,
  StarBorder,
  StarHalf,
  StarOutline,
  StarRate,
  Grade,
  GradeOutlined,
  GradeRounded,
  GradeSharp,
  GradeTwoTone,
  AutoAwesome as AutoAwesomeIcon,
  AutoAwesomeMotion as AutoAwesomeMotionIcon,
  AutoAwesomeMosaic,
  AutoDelete,
  AutoDeleteOutlined,
  AutoDeleteRounded,
  AutoDeleteSharp,
  AutoDeleteTwoTone,
  AutoMode as AutoModeIcon,
  AutoStories as AutoStoriesIcon,
  SmartToy as SmartToyIcon,
  Psychology as PsychologyIcon,
  Insights as InsightsIconAlt,
  DataObject,
  DataArray,
  DataThresholding,
  DataExploration,
  DataSaverOff,
  DataSaverOn,
  DataUsageRounded,
  DataUsageSharp,
  DataUsageTwoTone,
  DataUsageOutlined,
  DatasetLinked,
  Dataset,
  TableChart,
  TableRows,
  TableView as TableViewIcon,
  ViewAgenda,
  ViewArray,
  ViewCarousel,
  ViewColumn as ViewColumnIcon,
  ViewComfy,
  ViewComfyAlt,
  ViewCompact,
  ViewCompactAlt,
  ViewDay,
  ViewHeadline,
  ViewInAr,
  ViewKanban,
  ViewList as ViewListIcon,
  ViewModule as ViewModuleIcon,
  ViewQuilt,
  ViewSidebar,
  ViewStream,
  ViewTimeline,
  ViewWeek,
  DynamicFeed,
  DynamicForm,
  Feed,
  Rss,
  RssFeed,
  FilterList,
  FilterListOff,
  FilterAlt as FilterAltIcon,
  FilterAltOff,
  FilterDrama,
  FilterCenterFocus,
  FilterBAndW,
  FilterHdr,
  FilterNone,
  FilterTiltShift,
  FilterVintage,
  Filter1,
  Filter2,
  Filter3,
  Filter4,
  Filter5,
  Filter6,
  Filter7,
  Filter8,
  Filter9,
  Filter9Plus,
  Sort as SortIcon,
  SortByAlpha,
  ImportExport,
  SwapVert,
  SwapHoriz,
  SwapVerticalCircle,
  SwapHorizontalCircle,
  SwapCalls,
  Compare,
  CompareArrows,
  Code,
  CodeOff,
  Terminal,
  WebAsset,
  Web,
  WebhookTwoTone,
  Webhook,
  Api,
  ApiTwoTone,
  DeveloperMode,
  DeveloperBoard,
  DeveloperBoardOff,
  IntegrationInstructions,
  Source,
  GitHub,
  BugReport,
  FindInPage,
  FindReplace,
  Search,
  SearchOff,
  ManageSearch,
  PersonSearch,
  PageviewTwoTone,
  Pageview,
  Preview,
  FindInPageTwoTone,
  FindInPageOutlined,
  FindInPageRounded,
  FindInPageSharp,
  YoutubeSearchedFor,
  Saved,
  SavedSearch,
  Explore,
  ExploreOff,
  TravelExplore,
  Map,
  MapOutlined,
  MapRounded,
  MapSharp,
  MapTwoTone,
  Layers,
  LayersRounded,
  LayersSharp,
  LayersTwoTone,
  LayersOutlined,
  LayersClear,
  Stack as StackIcon,
  QueueMusic,
  Queue,
  QueuePlayNext,
  LibraryMusic,
  LibraryBooks,
  LibraryAdd,
  LibraryAddCheck,
  Album,
  Audiotrack,
  GraphicEq,
  Equalizer as EqualizerIcon,
  VolumeUp as VolumeUpIcon,
  VolumeDown as VolumeDownIcon,
  VolumeOff as VolumeOffIcon,
  VolumeMute as VolumeMuteIcon,
  MusicNote,
  MusicOff,
  Note,
  Notes,
  SpeakerNotes,
  SpeakerNotesOff,
  Mic,
  MicOff,
  MicNone,
  MicExternalOn,
  MicExternalOff,
  Headset,
  HeadsetOff,
  HeadsetMic,
  Hearing,
  HearingDisabled,
  RecordVoiceOver,
  VoiceOverOff,
  VoiceChat,
  NoAccounts,
  AccountCircle,
  AccountBox,
  Person,
  PersonAdd,
  PersonRemove,
  PersonOff,
  PersonOutline,
  PersonPin,
  PersonPinCircle,
  PersonalVideo,
  People,
  PeopleOutline,
  PeopleAlt,
  Group,
  GroupAdd,
  GroupRemove,
  GroupOff,
  GroupWork,
  Groups,
  SupervisorAccount,
  AdminPanelSettings as AdminPanelSettingsIcon,
  ManageAccounts,
  SwitchAccount,
  AccountTree,
  AccountBalance,
  AccountBalanceWallet,
  AccountCircleOutlined,
  AccountCircleRounded,
  AccountCircleSharp,
  AccountCircleTwoTone,
  ContactMail,
  ContactPhone,
  ContactPage,
  Contacts,
  ContactsOutlined,
  ContactsRounded,
  ContactsSharp,
  ContactsTwoTone,
  ContactSupport,
  ContactEmergency,
  Mail,
  MailOutline,
  MailOutlined,
  MailRounded,
  MailSharp,
  MailTwoTone,
  MailLock,
  AlternateEmail,
  Email,
  EmailOutlined,
  EmailRounded,
  EmailSharp,
  EmailTwoTone,
  Inbox,
  InboxOutlined,
  InboxRounded,
  InboxSharp,
  InboxTwoTone,
  Outbox,
  OutboxOutlined,
  OutboxRounded,
  OutboxSharp,
  OutboxTwoTone,
  Drafts,
  DraftsOutlined,
  DraftsRounded,
  DraftsSharp,
  DraftsTwoTone,
  Send,
  SendOutlined,
  SendRounded,
  SendSharp,
  SendTwoTone,
  SendAndArchive,
  SendTimeExtension,
  Forward as ForwardIcon,
  ForwardToInbox,
  Reply,
  ReplyAll,
  Unsubscribe,
  MarkEmailRead,
  MarkEmailUnread,
  MoveToInbox,
  Archive,
  ArchiveOutlined,
  ArchiveRounded,
  ArchiveSharp,
  ArchiveTwoTone,
  Unarchive,
  UnarchiveOutlined,
  UnarchiveRounded,
  UnarchiveSharp,
  UnarchiveTwoTone,
  Flag,
  FlagOutlined,
  FlagRounded,
  FlagSharp,
  FlagTwoTone,
  FlagCircle,
  OutlinedFlag,
  Report,
  ReportOff,
  ReportOutlined,
  ReportRounded,
  ReportSharp,
  ReportTwoTone,
  ReportGmailerrorred,
  ReportProblem as ReportProblemIcon,
  GppGood,
  GppBad,
  GppMaybe,
  Shield,
  ShieldMoon,
  Security as SecurityIcon,
  SecurityUpdate,
  SecurityUpdateGood,
  SecurityUpdateWarning,
  VerifiedUser,
  VerifiedUserOutlined,
  VerifiedUserRounded,
  VerifiedUserSharp,
  VerifiedUserTwoTone,
  Lock,
  LockOpen,
  LockOutlined,
  LockRounded,
  LockSharp,
  LockTwoTone,
  LockClock,
  LockPerson,
  LockReset,
  NoEncryption,
  NoEncryptionGmailerrorred,
  EnhancedEncryption,
  Key,
  KeyOff,
  KeyOutlined,
  KeyRounded,
  KeySharp,
  KeyTwoTone,
  Password,
  PasswordOutlined,
  PasswordRounded,
  PasswordSharp,
  PasswordTwoTone,
  Fingerprint,
  FingerprintOutlined,
  FingerprintRounded,
  FingerprintSharp,
  FingerprintTwoTone,
  Apps,
  AppsOutlined,
  AppsRounded,
  AppsSharp,
  AppsTwoTone,
  Menu,
  MenuOpen,
  MenuOutlined,
  MenuRounded,
  MenuSharp,
  MenuTwoTone,
  MenuBook,
  MoreHoriz,
  MoreVert as MoreVertIcon,
  MoreHorizOutlined,
  MoreHorizRounded,
  MoreHorizSharp,
  MoreHorizTwoTone,
  MoreVertOutlined,
  MoreVertRounded,
  MoreVertSharp,
  MoreVertTwoTone,
  DragHandle,
  DragIndicator,
  Reorder,
  OpenWith as OpenWithIcon,
  Pan,
  PanTool as PanToolIcon,
  PanToolAlt,
  TouchApp as TouchAppIcon,
  Gesture as GestureIcon,
  Swipe,
  SwipeUp as SwipeUpIcon,
  SwipeDown as SwipeDownIcon,
  SwipeLeft as SwipeLeftIcon,
  SwipeRight as SwipeRightIcon,
  SwipeVertical as SwipeVerticalIcon,
  SwipeDownAlt as SwipeDownAltIcon,
  SwipeUpAlt as SwipeUpAltIcon,
  SwipeLeftAlt as SwipeLeftAltIcon,
  SwipeRightAlt as SwipeRightAltIcon,
  PinchZoomIn as PinchZoomInIcon,
  PinchZoomOut as PinchZoomOutIcon,
  Compress as CompressIcon,
  Expand as ExpandIcon,
  Height as HeightIcon,
  Width as WidthIcon,
  AspectRatio as AspectRatioIcon,
  CropFree as CropFreeIcon,
  Crop as CropIcon,
  CropSquare as CropSquareIcon,
  CropPortrait as CropPortraitIcon,
  CropLandscape as CropLandscapeIcon,
  Crop32 as Crop32Icon,
  Crop54 as Crop54Icon,
  Crop75 as Crop75Icon,
  CropDin as CropDinIcon,
  CropOriginal as CropOriginalIcon,
  CropRotate as CropRotateIcon,
  Rotate90DegreesCcw as Rotate90DegreesCcwIcon,
  Rotate90DegreesCw as Rotate90DegreesCwIcon,
  RotateLeft as RotateLeftIcon,
  RotateRight as RotateRightIcon,
  Flip as FlipIcon,
  FlipToBack as FlipToBackIcon,
  FlipToFront as FlipToFrontIcon,
  Transform as TransformIcon
} from '@mui/icons-material';
import {
  ResponsiveContainer,
  LineChart,
  AreaChart,
  Line,
  Area,
  Bar,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend as RechartsLegend
} from 'recharts';

// Styled components for enhanced visuals
const pulse = keyframes`
  0% { opacity: 0.6; }
  50% { opacity: 1; }
  100% { opacity: 0.6; }
`;

const glow = keyframes`
  0% { box-shadow: 0 0 5px rgba(25, 118, 210, 0.5); }
  50% { box-shadow: 0 0 20px rgba(25, 118, 210, 0.8); }
  100% { box-shadow: 0 0 5px rgba(25, 118, 210, 0.5); }
`;

const slideIn = keyframes`
  from { transform: translateX(-100%); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
`;

const float = keyframes`
  0%, 100% { transform: translateY(0px); }
  50% { transform: translateY(-10px); }
`;

const LiveStatusCard = styled(Card)(({ theme, status }) => ({
  position: 'relative',
  overflow: 'hidden',
  background: status === 'active' 
    ? `linear-gradient(135deg, ${alpha(theme.palette.success.main, 0.1)} 0%, ${alpha(theme.palette.success.main, 0.05)} 100%)`
    : status === 'warning'
    ? `linear-gradient(135deg, ${alpha(theme.palette.warning.main, 0.1)} 0%, ${alpha(theme.palette.warning.main, 0.05)} 100%)`
    : `linear-gradient(135deg, ${alpha(theme.palette.error.main, 0.1)} 0%, ${alpha(theme.palette.error.main, 0.05)} 100%)`,
  border: `1px solid ${alpha(
    status === 'active' ? theme.palette.success.main : 
    status === 'warning' ? theme.palette.warning.main : 
    theme.palette.error.main, 0.3
  )}`,
  transition: 'all 0.3s ease-in-out',
  '&:hover': {
    transform: 'translateY(-4px)',
    boxShadow: theme.shadows[8],
  },
  '&::before': {
    content: '""',
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    height: '4px',
    background: status === 'active' ? theme.palette.success.main : 
                status === 'warning' ? theme.palette.warning.main : 
                theme.palette.error.main,
    animation: status === 'active' ? `${glow} 2s ease-in-out infinite` : 'none',
  }
}));

const PulsingIcon = styled('div')(({ theme, color = 'primary' }) => ({
  display: 'inline-flex',
  animation: `${pulse} 2s ease-in-out infinite`,
  color: theme.palette[color].main,
}));

const FloatingCard = styled(Card)(({ theme }) => ({
  animation: `${float} 3s ease-in-out infinite`,
  background: `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.05)} 0%, ${alpha(theme.palette.secondary.main, 0.05)} 100%)`,
  backdropFilter: 'blur(10px)',
  border: `1px solid ${alpha(theme.palette.primary.main, 0.1)}`,
  '&:hover': {
    transform: 'translateY(-8px)',
    boxShadow: theme.shadows[12],
  }
}));

const MetricCard = styled(Card)(({ theme, metric }) => ({
  background: `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.1)} 0%, ${alpha(theme.palette.secondary.main, 0.1)} 100%)`,
  border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`,
  transition: 'all 0.3s ease-in-out',
  position: 'relative',
  overflow: 'hidden',
  '&:hover': {
    transform: 'scale(1.02)',
    boxShadow: theme.shadows[8],
  },
  '&::before': {
    content: '""',
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    height: '3px',
    background: `linear-gradient(90deg, ${theme.palette.primary.main}, ${theme.palette.secondary.main})`,
  }
}));

const StreamingDataRow = styled(TableRow)(({ theme, isLive }) => ({
  background: isLive ? alpha(theme.palette.success.main, 0.05) : 'transparent',
  borderLeft: isLive ? `4px solid ${theme.palette.success.main}` : 'none',
  animation: isLive ? `${slideIn} 0.5s ease-out` : 'none',
  '&:hover': {
    background: alpha(theme.palette.action.hover, 0.1),
    transform: 'translateX(4px)',
    transition: 'all 0.2s ease-in-out',
  }
}));

const LiveDataPage = () => {
  const theme = useTheme();
  const [activeTab, setActiveTab] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [viewMode, setViewMode] = useState('grid'); // 'grid', 'list', 'chart'
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState(5000);
  const [connectionStatus, setConnectionStatus] = useState('connected');
  const [dataStreams, setDataStreams] = useState([]);
  const [metrics, setMetrics] = useState({});
  const [alerts, setAlerts] = useState([]);
  const [selectedSymbols, setSelectedSymbols] = useState([]);
  const [filterText, setFilterText] = useState('');
  const [sortBy, setSortBy] = useState('volume');
  const [sortOrder, setSortOrder] = useState('desc');
  const [isLoading, setIsLoading] = useState(false);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'info' });
  const [liveData, setLiveData] = useState({});
  const [historicalData, setHistoricalData] = useState([]);
  const [systemHealth, setSystemHealth] = useState('excellent');
  const [providerStatus, setProviderStatus] = useState({});
  const [realTimeMetrics, setRealTimeMetrics] = useState({
    messagesPerSecond: 0,
    latency: 0,
    throughput: 0,
    errorRate: 0,
    uptime: 0,
    connectedClients: 0
  });

  const refreshIntervalRef = useRef(null);
  const wsRef = useRef(null);

  // Mock real-time data generation
  useEffect(() => {
    const generateMockData = () => {
      const symbols = ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX', 'UBER', 'ZOOM'];
      const newData = {};
      
      symbols.forEach(symbol => {
        const basePrice = Math.random() * 500 + 50;
        const change = (Math.random() - 0.5) * 10;
        const volume = Math.floor(Math.random() * 10000000) + 1000000;
        
        newData[symbol] = {
          symbol,
          price: basePrice,
          change,
          changePercent: (change / basePrice) * 100,
          volume,
          high: basePrice + Math.random() * 20,
          low: basePrice - Math.random() * 20,
          open: basePrice + (Math.random() - 0.5) * 5,
          timestamp: new Date(),
          marketCap: basePrice * (Math.random() * 1000000000 + 100000000),
          peRatio: Math.random() * 50 + 5,
          eps: Math.random() * 10 + 0.5,
          dividendYield: Math.random() * 5,
          beta: Math.random() * 2 + 0.5,
          avgVolume: volume * (0.8 + Math.random() * 0.4),
          weekHigh52: basePrice * (1.2 + Math.random() * 0.3),
          weekLow52: basePrice * (0.7 - Math.random() * 0.2),
          movingAvg50: basePrice * (0.95 + Math.random() * 0.1),
          movingAvg200: basePrice * (0.9 + Math.random() * 0.2),
          rsi: Math.random() * 100,
          macd: (Math.random() - 0.5) * 5,
          bollinger: {
            upper: basePrice * 1.05,
            lower: basePrice * 0.95,
            middle: basePrice
          },
          volumeProfile: Array.from({ length: 20 }, () => Math.random() * 100),
          orderBook: {
            bids: Array.from({ length: 10 }, (_, i) => ({
              price: basePrice - (i + 1) * 0.1,
              size: Math.floor(Math.random() * 1000) + 100
            })),
            asks: Array.from({ length: 10 }, (_, i) => ({
              price: basePrice + (i + 1) * 0.1,
              size: Math.floor(Math.random() * 1000) + 100
            }))
          },
          trades: Array.from({ length: 5 }, () => ({
            price: basePrice + (Math.random() - 0.5) * 2,
            size: Math.floor(Math.random() * 1000) + 100,
            timestamp: new Date(Date.now() - Math.random() * 60000),
            side: Math.random() > 0.5 ? 'buy' : 'sell'
          }))
        };
      });
      
      setLiveData(newData);
      
      // Update metrics
      setRealTimeMetrics(prev => ({
        messagesPerSecond: Math.floor(Math.random() * 1000) + 500,
        latency: Math.floor(Math.random() * 100) + 20,
        throughput: Math.floor(Math.random() * 5000) + 2000,
        errorRate: Math.random() * 2,
        uptime: 99.9 - Math.random() * 0.5,
        connectedClients: Math.floor(Math.random() * 50) + 100
      }));
    };

    generateMockData();
    
    if (autoRefresh) {
      refreshIntervalRef.current = setInterval(generateMockData, refreshInterval);
    }

    return () => {
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current);
      }
    };
  }, [autoRefresh, refreshInterval]);

  // Mock data streams
  const mockDataStreams = [
    {
      id: 1,
      name: 'Equity Prices',
      provider: 'Alpaca',
      status: 'active',
      symbols: 4567,
      latency: 23,
      throughput: '2.1K/s',
      errorRate: 0.02,
      uptime: 99.98,
      cost: '$127.50',
      quality: 99.2,
      type: 'websocket',
      region: 'US-East',
      lastUpdate: new Date(),
      dataPoints: 1250000,
      compression: 'gzip',
      protocol: 'WSS',
      authentication: 'OAuth2',
      rateLimit: '10000/min',
      features: ['Real-time', 'Level 2', 'Options', 'Crypto']
    },
    {
      id: 2,
      name: 'Options Chain',
      provider: 'Interactive Brokers',
      status: 'active',
      symbols: 1234,
      latency: 45,
      throughput: '856/s',
      errorRate: 0.15,
      uptime: 99.85,
      cost: '$89.20',
      quality: 97.8,
      type: 'rest',
      region: 'US-East',
      lastUpdate: new Date(),
      dataPoints: 560000,
      compression: 'br',
      protocol: 'HTTPS',
      authentication: 'API Key',
      rateLimit: '5000/min',
      features: ['Greeks', 'Implied Volatility', 'Open Interest']
    },
    {
      id: 3,
      name: 'Crypto Prices',
      provider: 'Binance',
      status: 'warning',
      symbols: 567,
      latency: 78,
      throughput: '1.8K/s',
      errorRate: 1.2,
      uptime: 98.5,
      cost: '$45.80',
      quality: 94.2,
      type: 'websocket',
      region: 'Global',
      lastUpdate: new Date(),
      dataPoints: 890000,
      compression: 'deflate',
      protocol: 'WSS',
      authentication: 'HMAC',
      rateLimit: '20000/min',
      features: ['Spot', 'Futures', 'Margin', 'Lending']
    },
    {
      id: 4,
      name: 'Economic Data',
      provider: 'FRED',
      status: 'active',
      symbols: 89,
      latency: 2000,
      throughput: '2/s',
      errorRate: 0.01,
      uptime: 99.99,
      cost: '$0.00',
      quality: 100,
      type: 'rest',
      region: 'US-Central',
      lastUpdate: new Date(),
      dataPoints: 45000,
      compression: 'none',
      protocol: 'HTTPS',
      authentication: 'API Key',
      rateLimit: '1000/day',
      features: ['GDP', 'Inflation', 'Employment', 'Interest Rates']
    }
  ];

  useEffect(() => {
    setDataStreams(mockDataStreams);
  }, []);

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };

  const toggleFullscreen = () => {
    setIsFullscreen(!isFullscreen);
  };

  const handleRefreshToggle = () => {
    setAutoRefresh(!autoRefresh);
  };

  const handleManualRefresh = () => {
    setIsLoading(true);
    setTimeout(() => {
      setIsLoading(false);
      setSnackbar({
        open: true,
        message: 'Data refreshed successfully',
        severity: 'success'
      });
    }, 1000);
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'active': return 'success';
      case 'warning': return 'warning';
      case 'error': return 'error';
      default: return 'default';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'active': return <CheckCircle />;
      case 'warning': return <Warning />;
      case 'error': return <Error />;
      default: return <Info />;
    }
  };

  const formatNumber = (num) => {
    if (num >= 1000000000) return (num / 1000000000).toFixed(1) + 'B';
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toString();
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2
    }).format(amount);
  };

  const formatPercent = (percent) => {
    return new Intl.NumberFormat('en-US', {
      style: 'percent',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(percent / 100);
  };

  // Real-time metrics dashboard
  const MetricsDashboard = () => (
    <Grid container spacing={3}>
      <Grid item xs={12} md={2}>
        <MetricCard>
          <CardContent>
            <Box display="flex" alignItems="center" justifyContent="space-between">
              <Box>
                <Typography variant="h4" color="primary">
                  {realTimeMetrics.messagesPerSecond}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Msg/Sec
                </Typography>
              </Box>
              <PulsingIcon color="success">
                <ElectricBolt fontSize="large" />
              </PulsingIcon>
            </Box>
          </CardContent>
        </MetricCard>
      </Grid>

      <Grid item xs={12} md={2}>
        <MetricCard>
          <CardContent>
            <Box display="flex" alignItems="center" justifyContent="space-between">
              <Box>
                <Typography variant="h4" color="info.main">
                  {realTimeMetrics.latency}ms
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Latency
                </Typography>
              </Box>
              <SpeedIcon color="info" fontSize="large" />
            </Box>
          </CardContent>
        </MetricCard>
      </Grid>

      <Grid item xs={12} md={2}>
        <MetricCard>
          <CardContent>
            <Box display="flex" alignItems="center" justifyContent="space-between">
              <Box>
                <Typography variant="h4" color="secondary">
                  {formatNumber(realTimeMetrics.throughput)}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Throughput
                </Typography>
              </Box>
              <TrendingUp color="secondary" fontSize="large" />
            </Box>
          </CardContent>
        </MetricCard>
      </Grid>

      <Grid item xs={12} md={2}>
        <MetricCard>
          <CardContent>
            <Box display="flex" alignItems="center" justifyContent="space-between">
              <Box>
                <Typography variant="h4" color="warning.main">
                  {realTimeMetrics.errorRate.toFixed(2)}%
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Error Rate
                </Typography>
              </Box>
              <ReportProblemIcon color="warning" fontSize="large" />
            </Box>
          </CardContent>
        </MetricCard>
      </Grid>

      <Grid item xs={12} md={2}>
        <MetricCard>
          <CardContent>
            <Box display="flex" alignItems="center" justifyContent="space-between">
              <Box>
                <Typography variant="h4" color="success.main">
                  {realTimeMetrics.uptime.toFixed(1)}%
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Uptime
                </Typography>
              </Box>
              <HealthAndSafety color="success" fontSize="large" />
            </Box>
          </CardContent>
        </MetricCard>
      </Grid>

      <Grid item xs={12} md={2}>
        <MetricCard>
          <CardContent>
            <Box display="flex" alignItems="center" justifyContent="space-between">
              <Box>
                <Typography variant="h4" color="primary">
                  {realTimeMetrics.connectedClients}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Clients
                </Typography>
              </Box>
              <Hub color="primary" fontSize="large" />
            </Box>
          </CardContent>
        </MetricCard>
      </Grid>
    </Grid>
  );

  // Live data streams table
  const DataStreamsTable = () => (
    <Card>
      <CardHeader
        title={
          <Box display="flex" alignItems="center" gap={2}>
            <Stream color="primary" />
            <Typography variant="h6">Live Data Streams</Typography>
            <Badge badgeContent={dataStreams.filter(s => s.status === 'active').length} color="success">
              <Chip label="Active" size="small" />
            </Badge>
          </Box>
        }
        action={
          <Stack direction="row" spacing={1}>
            <Tooltip title="View Mode">
              <ButtonGroup size="small">
                <Button
                  variant={viewMode === 'grid' ? 'contained' : 'outlined'}
                  onClick={() => setViewMode('grid')}
                >
                  <GridView />
                </Button>
                <Button
                  variant={viewMode === 'list' ? 'contained' : 'outlined'}
                  onClick={() => setViewMode('list')}
                >
                  <ViewListIcon />
                </Button>
                <Button
                  variant={viewMode === 'chart' ? 'contained' : 'outlined'}
                  onClick={() => setViewMode('chart')}
                >
                  <BarChart />
                </Button>
              </ButtonGroup>
            </Tooltip>
            <Button
              startIcon={<Add />}
              variant="contained"
              size="small"
            >
              Add Stream
            </Button>
          </Stack>
        }
      />
      <CardContent>
        <TableContainer>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>
                  <Box display="flex" alignItems="center" gap={1}>
                    <Typography variant="subtitle2">Stream</Typography>
                    <SortIcon fontSize="small" />
                  </Box>
                </TableCell>
                <TableCell>Provider</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Symbols</TableCell>
                <TableCell>Latency</TableCell>
                <TableCell>Throughput</TableCell>
                <TableCell>Quality</TableCell>
                <TableCell>Cost</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {dataStreams.map((stream) => (
                <StreamingDataRow key={stream.id} isLive={stream.status === 'active'}>
                  <TableCell>
                    <Box display="flex" alignItems="center" gap={2}>
                      <Avatar
                        sx={{
                          bgcolor: getStatusColor(stream.status) + '.main',
                          width: 32,
                          height: 32
                        }}
                      >
                        {stream.type === 'websocket' ? <WifiTwoTone /> : <ApiTwoTone />}
                      </Avatar>
                      <Box>
                        <Typography variant="subtitle2">{stream.name}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          {stream.type.toUpperCase()} • {stream.region}
                        </Typography>
                      </Box>
                    </Box>
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={stream.provider}
                      size="small"
                      variant="outlined"
                      icon={<CloudSync />}
                    />
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={stream.status}
                      color={getStatusColor(stream.status)}
                      size="small"
                      icon={getStatusIcon(stream.status)}
                    />
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" fontWeight="bold">
                      {stream.symbols.toLocaleString()}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Box display="flex" alignItems="center" gap={1}>
                      <Typography variant="body2">{stream.latency}ms</Typography>
                      <LinearProgress
                        variant="determinate"
                        value={100 - (stream.latency / 100)}
                        sx={{ width: 40, height: 4 }}
                        color={stream.latency < 50 ? 'success' : stream.latency < 100 ? 'warning' : 'error'}
                      />
                    </Box>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" fontWeight="bold">
                      {stream.throughput}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Box display="flex" alignItems="center" gap={1}>
                      <CircularProgress
                        variant="determinate"
                        value={stream.quality}
                        size={24}
                        thickness={4}
                        color={stream.quality > 95 ? 'success' : stream.quality > 90 ? 'warning' : 'error'}
                      />
                      <Typography variant="body2">{stream.quality}%</Typography>
                    </Box>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" fontWeight="bold" color="warning.main">
                      {stream.cost}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={1}>
                      <Tooltip title="Configure">
                        <IconButton size="small">
                          <Settings />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="Pause">
                        <IconButton size="small" color="warning">
                          <PauseCircle />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="Restart">
                        <IconButton size="small" color="success">
                          <RestartAlt />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="More">
                        <IconButton size="small">
                          <MoreVertIcon />
                        </IconButton>
                      </Tooltip>
                    </Stack>
                  </TableCell>
                </StreamingDataRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
    </Card>
  );

  // Live market data feed
  const LiveMarketFeed = () => (
    <Card>
      <CardHeader
        title={
          <Box display="flex" alignItems="center" gap={2}>
            <LiveTv color="primary" />
            <Typography variant="h6">Live Market Data</Typography>
            <PulsingIcon color="success">
              <FiberManualRecord fontSize="small" />
            </PulsingIcon>
          </Box>
        }
        action={
          <Stack direction="row" spacing={1}>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>Sort By</InputLabel>
              <Select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                label="Sort By"
              >
                <MenuItem value="volume">Volume</MenuItem>
                <MenuItem value="price">Price</MenuItem>
                <MenuItem value="change">Change</MenuItem>
                <MenuItem value="marketCap">Market Cap</MenuItem>
              </Select>
            </FormControl>
            <TextField
              size="small"
              placeholder="Filter symbols..."
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              InputProps={{
                startAdornment: <Search fontSize="small" />
              }}
              sx={{ width: 200 }}
            />
          </Stack>
        }
      />
      <CardContent>
        <TableContainer sx={{ maxHeight: 400 }}>
          <Table stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Symbol</TableCell>
                <TableCell align="right">Price</TableCell>
                <TableCell align="right">Change</TableCell>
                <TableCell align="right">Volume</TableCell>
                <TableCell align="right">Market Cap</TableCell>
                <TableCell align="right">RSI</TableCell>
                <TableCell align="center">Trend</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {Object.values(liveData)
                .filter(stock => stock.symbol.toLowerCase().includes(filterText.toLowerCase()))
                .sort((a, b) => {
                  const aVal = a[sortBy];
                  const bVal = b[sortBy];
                  return sortOrder === 'desc' ? bVal - aVal : aVal - bVal;
                })
                .map((stock) => (
                  <StreamingDataRow key={stock.symbol} isLive={true}>
                    <TableCell>
                      <Box display="flex" alignItems="center" gap={2}>
                        <Avatar sx={{ bgcolor: 'primary.main', width: 32, height: 32 }}>
                          {stock.symbol[0]}
                        </Avatar>
                        <Box>
                          <Typography variant="subtitle2" fontWeight="bold">
                            {stock.symbol}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {new Date(stock.timestamp).toLocaleTimeString()}
                          </Typography>
                        </Box>
                      </Box>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2" fontWeight="bold">
                        {formatCurrency(stock.price)}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Box display="flex" alignItems="center" justifyContent="flex-end" gap={1}>
                        {stock.change > 0 ? (
                          <TrendingUp color="success" fontSize="small" />
                        ) : (
                          <TrendingDown color="error" fontSize="small" />
                        )}
                        <Typography
                          variant="body2"
                          color={stock.change > 0 ? 'success.main' : 'error.main'}
                          fontWeight="bold"
                        >
                          {stock.change > 0 ? '+' : ''}{stock.change.toFixed(2)}
                        </Typography>
                        <Typography
                          variant="caption"
                          color={stock.change > 0 ? 'success.main' : 'error.main'}
                        >
                          ({formatPercent(stock.changePercent)})
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2">
                        {formatNumber(stock.volume)}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2">
                        {formatCurrency(stock.marketCap)}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Box display="flex" alignItems="center" justifyContent="flex-end" gap={1}>
                        <LinearProgress
                          variant="determinate"
                          value={stock.rsi}
                          sx={{ width: 40, height: 4 }}
                          color={stock.rsi > 70 ? 'error' : stock.rsi < 30 ? 'success' : 'warning'}
                        />
                        <Typography variant="body2">
                          {stock.rsi.toFixed(0)}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell align="center">
                      <Chip
                        label={stock.change > 0 ? 'Bullish' : 'Bearish'}
                        color={stock.change > 0 ? 'success' : 'error'}
                        size="small"
                        variant="outlined"
                      />
                    </TableCell>
                  </StreamingDataRow>
                ))}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
    </Card>
  );

  // Connection status panel
  const ConnectionStatus = () => (
    <FloatingCard>
      <CardContent>
        <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
          <Typography variant="h6">Connection Status</Typography>
          <Stack direction="row" spacing={1}>
            <FormControlLabel
              control={
                <Switch
                  checked={autoRefresh}
                  onChange={handleRefreshToggle}
                  color="success"
                />
              }
              label="Auto Refresh"
            />
            <Button
              variant="outlined"
              size="small"
              onClick={handleManualRefresh}
              disabled={isLoading}
              startIcon={isLoading ? <CircularProgress size={16} /> : <Refresh />}
            >
              Refresh
            </Button>
          </Stack>
        </Box>
        
        <Grid container spacing={2}>
          <Grid item xs={12} md={3}>
            <Box display="flex" alignItems="center" gap={2}>
              <PulsingIcon color="success">
                <SignalWifi4Bar />
              </PulsingIcon>
              <Box>
                <Typography variant="body2" color="success.main" fontWeight="bold">
                  WebSocket Connected
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Primary feed active
                </Typography>
              </Box>
            </Box>
          </Grid>
          
          <Grid item xs={12} md={3}>
            <Box display="flex" alignItems="center" gap={2}>
              <CloudDone color="info" />
              <Box>
                <Typography variant="body2" color="info.main" fontWeight="bold">
                  API Gateway
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  99.9% uptime
                </Typography>
              </Box>
            </Box>
          </Grid>
          
          <Grid item xs={12} md={3}>
            <Box display="flex" alignItems="center" gap={2}>
              <Dns color="success" />
              <Box>
                <Typography variant="body2" color="success.main" fontWeight="bold">
                  Database
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Synchronized
                </Typography>
              </Box>
            </Box>
          </Grid>
          
          <Grid item xs={12} md={3}>
            <Box display="flex" alignItems="center" gap={2}>
              <Security color="success" />
              <Box>
                <Typography variant="body2" color="success.main" fontWeight="bold">
                  Security
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  All systems secure
                </Typography>
              </Box>
            </Box>
          </Grid>
        </Grid>
      </CardContent>
    </FloatingCard>
  );

  // Advanced controls panel
  const AdvancedControls = () => (
    <Card>
      <CardHeader
        title={
          <Box display="flex" alignItems="center" gap={2}>
            <Tune color="primary" />
            <Typography variant="h6">Advanced Controls</Typography>
          </Box>
        }
      />
      <CardContent>
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <Stack spacing={2}>
              <Typography variant="subtitle2" color="text.secondary">
                Data Stream Controls
              </Typography>
              <ButtonGroup variant="outlined" fullWidth>
                <Button startIcon={<PlayCircle />} color="success">
                  Start All
                </Button>
                <Button startIcon={<PauseCircle />} color="warning">
                  Pause All
                </Button>
                <Button startIcon={<StopCircle />} color="error">
                  Stop All
                </Button>
              </ButtonGroup>
              
              <ButtonGroup variant="outlined" fullWidth>
                <Button startIcon={<RestartAlt />}>
                  Restart
                </Button>
                <Button startIcon={<AutoFixHigh />}>
                  Auto-Heal
                </Button>
                <Button startIcon={<Build />}>
                  Diagnostics
                </Button>
              </ButtonGroup>
            </Stack>
          </Grid>
          
          <Grid item xs={12} md={6}>
            <Stack spacing={2}>
              <Typography variant="subtitle2" color="text.secondary">
                Performance Tuning
              </Typography>
              <FormControl fullWidth size="small">
                <InputLabel>Refresh Rate</InputLabel>
                <Select
                  value={refreshInterval}
                  onChange={(e) => setRefreshInterval(e.target.value)}
                  label="Refresh Rate"
                >
                  <MenuItem value={1000}>1 Second</MenuItem>
                  <MenuItem value={5000}>5 Seconds</MenuItem>
                  <MenuItem value={10000}>10 Seconds</MenuItem>
                  <MenuItem value={30000}>30 Seconds</MenuItem>
                </Select>
              </FormControl>
              
              <Stack direction="row" spacing={2}>
                <FormControlLabel
                  control={<Switch defaultChecked />}
                  label="Enable Compression"
                />
                <FormControlLabel
                  control={<Switch defaultChecked />}
                  label="Auto-Scaling"
                />
              </Stack>
            </Stack>
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );

  const tabContent = [
    {
      label: 'Live Dashboard',
      icon: <Dashboard />,
      component: (
        <Stack spacing={3}>
          <ConnectionStatus />
          <MetricsDashboard />
          <LiveMarketFeed />
        </Stack>
      )
    },
    {
      label: 'Data Streams',
      icon: <Stream />,
      component: (
        <Stack spacing={3}>
          <DataStreamsTable />
          <AdvancedControls />
        </Stack>
      )
    },
    {
      label: 'Analytics',
      icon: <Analytics />,
      component: (
        <Stack spacing={3}>
          <Typography variant="h6">Performance Analytics</Typography>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Throughput Trends
                  </Typography>
                  <Box height={300} display="flex" alignItems="center" justifyContent="center">
                    <Typography color="text.secondary">
                      Chart visualization will be implemented here
                    </Typography>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Error Rate Analysis
                  </Typography>
                  <Box height={300} display="flex" alignItems="center" justifyContent="center">
                    <Typography color="text.secondary">
                      Error analysis charts will be implemented here
                    </Typography>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </Stack>
      )
    },
    {
      label: 'System Health',
      icon: <HealthAndSafety />,
      component: (
        <Stack spacing={3}>
          <Typography variant="h6">System Health Monitor</Typography>
          <Grid container spacing={3}>
            <Grid item xs={12} md={4}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Server Status
                  </Typography>
                  <Stack spacing={2}>
                    <Box display="flex" alignItems="center" justifyContent="space-between">
                      <Typography>CPU Usage</Typography>
                      <Typography color="success.main">23%</Typography>
                    </Box>
                    <LinearProgress variant="determinate" value={23} color="success" />
                    
                    <Box display="flex" alignItems="center" justifyContent="space-between">
                      <Typography>Memory Usage</Typography>
                      <Typography color="warning.main">67%</Typography>
                    </Box>
                    <LinearProgress variant="determinate" value={67} color="warning" />
                    
                    <Box display="flex" alignItems="center" justifyContent="space-between">
                      <Typography>Disk I/O</Typography>
                      <Typography color="info.main">12%</Typography>
                    </Box>
                    <LinearProgress variant="determinate" value={12} color="info" />
                  </Stack>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={8}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Recent System Events
                  </Typography>
                  <List>
                    <ListItem>
                      <ListItemIcon>
                        <CheckCircle color="success" />
                      </ListItemIcon>
                      <ListItemText
                        primary="Data stream reconnected successfully"
                        secondary="2 minutes ago"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemIcon>
                        <Warning color="warning" />
                      </ListItemIcon>
                      <ListItemText
                        primary="High latency detected on Binance feed"
                        secondary="15 minutes ago"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemIcon>
                        <Info color="info" />
                      </ListItemIcon>
                      <ListItemText
                        primary="Scheduled maintenance completed"
                        secondary="1 hour ago"
                      />
                    </ListItem>
                  </List>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </Stack>
      )
    }
  ];

  return (
    <Box sx={{ p: 3, minHeight: '100vh' }}>
      {/* Header */}
      <Paper
        elevation={3}
        sx={{
          p: 2,
          mb: 3,
          background: `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.1)} 0%, ${alpha(theme.palette.secondary.main, 0.1)} 100%)`,
          border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`
        }}
      >
        <Box display="flex" alignItems="center" justifyContent="space-between">
          <Box display="flex" alignItems="center" gap={2}>
            <PulsingIcon color="primary">
              <LiveTv fontSize="large" />
            </PulsingIcon>
            <Box>
              <Typography variant="h4" fontWeight="bold">
                Live Data Command Center
              </Typography>
              <Typography variant="subtitle1" color="text.secondary">
                Real-time market data streaming and management platform
              </Typography>
            </Box>
          </Box>
          
          <Stack direction="row" spacing={1}>
            <Chip
              label={`${Object.keys(liveData).length} Active Symbols`}
              color="success"
              icon={<TrendingUp />}
            />
            <Chip
              label={`${dataStreams.filter(s => s.status === 'active').length} Streams`}
              color="info"
              icon={<Stream />}
            />
            <Button
              variant="outlined"
              startIcon={isFullscreen ? <FullscreenExit /> : <Fullscreen />}
              onClick={toggleFullscreen}
            >
              {isFullscreen ? 'Exit' : 'Fullscreen'}
            </Button>
          </Stack>
        </Box>
      </Paper>

      {/* Main Content */}
      <Box sx={{ width: '100%' }}>
        <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
          <Tabs
            value={activeTab}
            onChange={handleTabChange}
            variant="scrollable"
            scrollButtons="auto"
            sx={{
              '& .MuiTab-root': {
                minHeight: 64,
                fontWeight: 'bold',
                textTransform: 'none',
                fontSize: '1rem'
              }
            }}
          >
            {tabContent.map((tab, index) => (
              <Tab
                key={index}
                label={tab.label}
                icon={tab.icon}
                iconPosition="start"
                sx={{ gap: 1 }}
              />
            ))}
          </Tabs>
        </Box>

        <Fade in={true} timeout={500}>
          <Box>
            {tabContent[activeTab].component}
          </Box>
        </Fade>
      </Box>

      {/* Snackbar for notifications */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar({ ...snackbar, open: false })}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert
          onClose={() => setSnackbar({ ...snackbar, open: false })}
          severity={snackbar.severity}
          variant="filled"
          sx={{ width: '100%' }}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default LiveDataPage;