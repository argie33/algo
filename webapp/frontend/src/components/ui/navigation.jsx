import React, { useState, Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { Link, useLocation } from 'react-router-dom';
import { 
  Bars3Icon, 
  XMarkIcon,
  ChartBarIcon,
  CurrencyDollarIcon,
  NewspaperIcon,
  CogIcon,
  HomeIcon,
  BellIcon,
  MagnifyingGlassIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  DocumentTextIcon,
  PresentationChartLineIcon,
  BookOpenIcon,
  WrenchScrewdriverIcon,
  AcademicCapIcon,
  LightBulbIcon,
  TrophyIcon,
  ShieldCheckIcon,
  SparklesIcon
} from '@heroicons/react/24/outline';
import { useResponsive } from '../../utils/responsive';

const navigation = [
  { 
    name: 'Dashboard', 
    href: '/', 
    icon: HomeIcon,
    current: false
  },
  { 
    name: 'Portfolio', 
    href: '/portfolio', 
    icon: CurrencyDollarIcon,
    current: false,
    children: [
      { name: 'Overview', href: '/portfolio' },
      { name: 'Holdings', href: '/portfolio/holdings' },
      { name: 'Performance', href: '/portfolio/performance' },
      { name: 'Trade History', href: '/portfolio/trade-history' },
      { name: 'Optimization', href: '/portfolio/optimize' },
      { name: 'Enhanced View', href: '/portfolio/enhanced' },
    ]
  },
  { 
    name: 'Market Data', 
    href: '/market', 
    icon: ChartBarIcon,
    current: false,
    children: [
      { name: 'Market Overview', href: '/market' },
      { name: 'Live Data', href: '/live-data' },
      { name: 'Real-Time Dashboard', href: '/real-time-dashboard' },
      { name: 'Data Management', href: '/data-management' },
      { name: 'Metrics Dashboard', href: '/metrics' },
    ]
  },
  { 
    name: 'Trading', 
    href: '/trading', 
    icon: BellIcon,
    current: false,
    children: [
      { name: 'Trading Signals', href: '/trading' },
      { name: 'Enhanced Signals', href: '/trading-signals-enhanced' },
      { name: 'Risk Management', href: '/risk-management' },
      { name: 'Backtest', href: '/backtest' },
    ]
  },
  { 
    name: 'Analysis', 
    href: '/technical', 
    icon: PresentationChartLineIcon,
    current: false,
    children: [
      { name: 'Technical Analysis', href: '/technical' },
      { name: 'Pattern Recognition', href: '/stocks/patterns' },
      { name: 'Analyst Insights', href: '/analysts' },
      { name: 'Sector Analysis', href: '/sectors' },
      { name: 'Economic Modeling', href: '/economic' },
    ]
  },
  { 
    name: 'Stocks', 
    href: '/stocks', 
    icon: MagnifyingGlassIcon,
    current: false,
    children: [
      { name: 'Stock Explorer', href: '/stocks' },
      { name: 'Advanced Screener', href: '/screener-advanced' },
      { name: 'Watchlist', href: '/watchlist' },
      { name: 'Earnings Calendar', href: '/earnings' },
    ]
  },
  { 
    name: 'Options', 
    href: '/options', 
    icon: TrophyIcon,
    current: false,
    children: [
      { name: 'Options Analytics', href: '/options' },
      { name: 'Strategies', href: '/options/strategies' },
      { name: 'Options Flow', href: '/options/flow' },
      { name: 'Volatility Surface', href: '/options/volatility' },
      { name: 'Greeks Monitor', href: '/options/greeks' },
    ]
  },
  { 
    name: 'Sentiment', 
    href: '/sentiment', 
    icon: NewspaperIcon,
    current: false,
    children: [
      { name: 'Sentiment Analysis', href: '/sentiment' },
      { name: 'News Sentiment', href: '/sentiment/news' },
      { name: 'Social Media', href: '/sentiment/social' },
      { name: 'News Analysis', href: '/news-analysis' },
    ]
  },
  { 
    name: 'Commodities & Crypto', 
    href: '/commodities', 
    icon: CurrencyDollarIcon,
    current: false,
    children: [
      { name: 'Commodities', href: '/commodities' },
      { name: 'Enhanced Commodities', href: '/commodities-enhanced' },
      { name: 'Crypto Overview', href: '/crypto' },
      { name: 'Crypto Advanced', href: '/crypto/advanced' },
    ]
  },
  { 
    name: 'Research', 
    href: '/research/commentary', 
    icon: BookOpenIcon,
    current: false,
    children: [
      { name: 'Market Commentary', href: '/research/commentary' },
      { name: 'Educational Content', href: '/research/education' },
      { name: 'Research Reports', href: '/research/reports' },
    ]
  },
  { 
    name: 'Tools', 
    href: '/scores', 
    icon: WrenchScrewdriverIcon,
    current: false,
    children: [
      { name: 'AI Assistant', href: '/tools/ai' },
      { name: 'Scores Dashboard', href: '/scores' },
      { name: 'Performance Monitor', href: '/performance-monitoring' },
      { name: 'Service Health', href: '/service-health' },
    ]
  },
  { 
    name: 'Settings', 
    href: '/settings', 
    icon: CogIcon,
    current: false,
    children: [
      { name: 'General Settings', href: '/settings' },
      { name: 'API Keys', href: '/settings/api-keys' },
    ]
  },
];

export function TailwindNavigation({ children }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [openDropdowns, setOpenDropdowns] = useState({});
  const location = useLocation();
  const { isMobile } = useResponsive();

  const toggleDropdown = (itemName) => {
    setOpenDropdowns(prev => ({
      ...prev,
      [itemName]: !prev[itemName]
    }));
  };
  
  const isActivePath = (href) => {
    if (href === '/') return location.pathname === '/';
    return location.pathname.startsWith(href);
  };

  return (
    <div className="h-full">
      {/* Mobile sidebar */}
      <Transition.Root show={sidebarOpen} as={Fragment}>
        <Dialog as="div" className="relative z-50 lg:hidden" onClose={setSidebarOpen}>
          <Transition.Child
            as={Fragment}
            enter="transition-opacity ease-linear duration-300"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="transition-opacity ease-linear duration-300"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-gray-900/80" />
          </Transition.Child>

          <div className="fixed inset-0 flex">
            <Transition.Child
              as={Fragment}
              enter="transition ease-in-out duration-300 transform"
              enterFrom="-translate-x-full"
              enterTo="translate-x-0"
              leave="transition ease-in-out duration-300 transform"
              leaveFrom="translate-x-0"
              leaveTo="-translate-x-full"
            >
              <Dialog.Panel className="relative mr-16 flex w-full max-w-xs flex-1">
                <Transition.Child
                  as={Fragment}
                  enter="ease-in-out duration-300"
                  enterFrom="opacity-0"
                  enterTo="opacity-100"
                  leave="ease-in-out duration-300"
                  leaveFrom="opacity-100"
                  leaveTo="opacity-0"
                >
                  <div className="absolute left-full top-0 flex w-16 justify-center pt-5">
                    <button
                      type="button"
                      className="-m-2.5 p-2.5"
                      onClick={() => setSidebarOpen(false)}
                    >
                      <span className="sr-only">Close sidebar</span>
                      <XMarkIcon className="h-6 w-6 text-white" aria-hidden="true" />
                    </button>
                  </div>
                </Transition.Child>
                <div className="flex grow flex-col gap-y-5 overflow-y-auto bg-white px-6 pb-2">
                  <div className="flex h-16 shrink-0 items-center">
                    <h1 className="text-xl font-bold text-blue-600">Financial Platform</h1>
                  </div>
                  <nav className="flex flex-1 flex-col">
                    <ul role="list" className="flex flex-1 flex-col gap-y-7">
                      <li>
                        <ul role="list" className="-mx-2 space-y-1">
                          {navigation.map((item) => (
                            <li key={item.name}>
                              {!item.children ? (
                                <Link
                                  to={item.href}
                                  className={`group flex gap-x-3 rounded-md p-2 text-sm leading-6 font-semibold ${
                                    isActivePath(item.href) 
                                      ? 'bg-blue-50 text-blue-600' 
                                      : 'text-gray-700 hover:text-blue-600 hover:bg-gray-50'
                                  }`}
                                  onClick={() => setSidebarOpen(false)}
                                >
                                  <item.icon
                                    className={`h-6 w-6 shrink-0 ${
                                      isActivePath(item.href)
                                        ? 'text-blue-600'
                                        : 'text-gray-400 group-hover:text-blue-600'
                                    }`}
                                    aria-hidden="true"
                                  />
                                  {item.name}
                                </Link>
                              ) : (
                                <div>
                                  <button
                                    onClick={() => toggleDropdown(item.name)}
                                    className={`group flex w-full items-center gap-x-3 rounded-md p-2 text-left text-sm leading-6 font-semibold ${
                                      isActivePath(item.href) 
                                        ? 'bg-blue-50 text-blue-600' 
                                        : 'text-gray-700 hover:text-blue-600 hover:bg-gray-50'
                                    }`}
                                  >
                                    <item.icon
                                      className={`h-6 w-6 shrink-0 ${
                                        isActivePath(item.href)
                                          ? 'text-blue-600'
                                          : 'text-gray-400 group-hover:text-blue-600'
                                      }`}
                                      aria-hidden="true"
                                    />
                                    <span className="flex-1">{item.name}</span>
                                    {openDropdowns[item.name] ? (
                                      <ChevronDownIcon className="h-4 w-4" />
                                    ) : (
                                      <ChevronRightIcon className="h-4 w-4" />
                                    )}
                                  </button>
                                  {openDropdowns[item.name] && (
                                    <ul className="mt-1 space-y-1 pl-8">
                                      {item.children.map((child) => (
                                        <li key={child.name}>
                                          <Link
                                            to={child.href}
                                            className={`group flex gap-x-3 rounded-md p-2 text-sm leading-6 ${
                                              isActivePath(child.href)
                                                ? 'bg-blue-50 text-blue-600 font-medium'
                                                : 'text-gray-600 hover:text-blue-600 hover:bg-gray-50'
                                            }`}
                                            onClick={() => setSidebarOpen(false)}
                                          >
                                            {child.name}
                                          </Link>
                                        </li>
                                      ))}
                                    </ul>
                                  )}
                                </div>
                              )}
                            </li>
                          ))}
                        </ul>
                      </li>
                    </ul>
                  </nav>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </Dialog>
      </Transition.Root>

      {/* Static sidebar for desktop */}
      <div className="hidden lg:fixed lg:inset-y-0 lg:z-50 lg:flex lg:w-72 lg:flex-col">
        <div className="flex grow flex-col gap-y-5 overflow-y-auto border-r border-gray-200 bg-white px-6">
          <div className="flex h-16 shrink-0 items-center">
            <h1 className="text-xl font-bold text-blue-600">Financial Platform</h1>
          </div>
          <nav className="flex flex-1 flex-col">
            <ul role="list" className="flex flex-1 flex-col gap-y-7">
              <li>
                <ul role="list" className="-mx-2 space-y-1">
                  {navigation.map((item) => (
                    <li key={item.name}>
                      {!item.children ? (
                        <Link
                          to={item.href}
                          className={`group flex gap-x-3 rounded-md p-2 text-sm leading-6 font-semibold ${
                            isActivePath(item.href) 
                              ? 'bg-blue-50 text-blue-600' 
                              : 'text-gray-700 hover:text-blue-600 hover:bg-gray-50'
                          }`}
                        >
                          <item.icon
                            className={`h-6 w-6 shrink-0 ${
                              isActivePath(item.href)
                                ? 'text-blue-600'
                                : 'text-gray-400 group-hover:text-blue-600'
                            }`}
                            aria-hidden="true"
                          />
                          {item.name}
                        </Link>
                      ) : (
                        <div>
                          <button
                            onClick={() => toggleDropdown(item.name)}
                            className={`group flex w-full items-center gap-x-3 rounded-md p-2 text-left text-sm leading-6 font-semibold ${
                              isActivePath(item.href) 
                                ? 'bg-blue-50 text-blue-600' 
                                : 'text-gray-700 hover:text-blue-600 hover:bg-gray-50'
                            }`}
                          >
                            <item.icon
                              className={`h-6 w-6 shrink-0 ${
                                isActivePath(item.href)
                                  ? 'text-blue-600'
                                  : 'text-gray-400 group-hover:text-blue-600'
                              }`}
                              aria-hidden="true"
                            />
                            <span className="flex-1">{item.name}</span>
                            {openDropdowns[item.name] ? (
                              <ChevronDownIcon className="h-4 w-4" />
                            ) : (
                              <ChevronRightIcon className="h-4 w-4" />
                            )}
                          </button>
                          {openDropdowns[item.name] && (
                            <ul className="mt-1 space-y-1 pl-8">
                              {item.children.map((child) => (
                                <li key={child.name}>
                                  <Link
                                    to={child.href}
                                    className={`group flex gap-x-3 rounded-md p-2 text-sm leading-6 ${
                                      isActivePath(child.href)
                                        ? 'bg-blue-50 text-blue-600 font-medium'
                                        : 'text-gray-600 hover:text-blue-600 hover:bg-gray-50'
                                    }`}
                                  >
                                    {child.name}
                                  </Link>
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              </li>
            </ul>
          </nav>
        </div>
      </div>

      {/* Mobile header */}
      <div className="sticky top-0 z-40 flex items-center gap-x-6 bg-white px-4 py-4 shadow-sm sm:px-6 lg:hidden">
        <button
          type="button"
          className="-m-2.5 p-2.5 text-gray-700 lg:hidden"
          onClick={() => setSidebarOpen(true)}
        >
          <span className="sr-only">Open sidebar</span>
          <Bars3Icon className="h-6 w-6" aria-hidden="true" />
        </button>
        <div className="flex-1 text-sm font-semibold leading-6 text-gray-900">
          Financial Platform
        </div>
      </div>

      {/* Main content */}
      <main className="py-10 lg:pl-72">
        <div className="px-4 sm:px-6 lg:px-8">
          {children}
        </div>
      </main>
    </div>
  );
}

export function NavigationWrapper({ children }) {
  return (
    <TailwindNavigation>
      {children}
    </TailwindNavigation>
  );
}

export default TailwindNavigation;