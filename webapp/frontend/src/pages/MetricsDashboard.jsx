import { useState, useMemo } from "react";
import { TrendingUp, Info, BarChart3, DollarSign, Wallet } from "lucide-react";
import { useApiQuery } from "../hooks/useApiQuery";
import { api } from "../services/api";

const MetricsDashboard = () => {
  const [activeTab, setActiveTab] = useState(0);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedSector, setSelectedSector] = useState("");
  const [sortBy, setSortBy] = useState("composite_metric");
  const [sortOrder, setSortOrder] = useState("desc");

  const { data: scoresData, loading, error } = useApiQuery(
    ['stockscores'],
    () => api.get("/api/scores/stockscores?limit=10000")
  );

  const allStocks = Array.isArray(scoresData) ? scoresData : (scoresData?.items || []);

  const stocks = useMemo(() => {
    let filtered = Array.isArray(allStocks) ? allStocks : [];

    if (searchTerm) {
      filtered = filtered.filter(s =>
        s.symbol.toLowerCase().includes(searchTerm.toLowerCase())
      );
    }

    if (selectedSector) {
      filtered = filtered.filter(s => s.sector === selectedSector);
    }

    filtered.sort((a, b) => {
      const sortKey = sortBy === "composite_metric" ? "composite_score" : sortBy.replace("_metric", "_score");
      const aVal = a[sortKey] || 0;
      const bVal = b[sortKey] || 0;
      return sortOrder === "desc" ? bVal - aVal : aVal - bVal;
    });

    return filtered;
  }, [allStocks, searchTerm, selectedSector, sortBy, sortOrder]);

  const sectors = useMemo(() => {
    const sectorData = {};
    allStocks.forEach(stock => {
      if (stock.sector) {
        if (!sectorData[stock.sector]) {
          sectorData[stock.sector] = [];
        }
        sectorData[stock.sector].push(stock);
      }
    });

    return Object.entries(sectorData).map(([name, stocks]) => ({
      name,
      count: stocks.length,
      avgComposite: (stocks.reduce((sum, s) => sum + (s.composite_score || 0), 0) / stocks.length).toFixed(2),
    }));
  }, [allStocks]);

  const topStocksData = useMemo(() => {
    const allList = Array.isArray(allStocks) ? allStocks : [];
    const compositeList = [...allList].filter(s => s.composite_score !== null).sort((a, b) => b.composite_score - a.composite_score);
    const qualityList = [...allList].filter(s => s.quality_score !== null).sort((a, b) => b.quality_score - a.quality_score);
    const valueList = [...allList].filter(s => s.value_score !== null).sort((a, b) => b.value_score - a.value_score);
    return {
      composite: { items: compositeList.slice(0, 10), total: compositeList.length },
      quality: { items: qualityList.slice(0, 10), total: qualityList.length },
      value: { items: valueList.slice(0, 10), total: valueList.length },
    };
  }, [allStocks]);

  const getMetricColor = (metric) => {
    if (metric >= 0.8) return "#22c55e";
    if (metric >= 0.7) return "#a1d922";
    if (metric >= 0.6) return "#f59e0b";
    if (metric >= 0.5) return "#f97316";
    return "#ef4444";
  };

  const getMetricClass = (metric) => {
    if (metric >= 0.8) return 'up';
    if (metric >= 0.7) return 'up';
    if (metric >= 0.6) return 'flat';
    if (metric >= 0.5) return 'down';
    return 'down';
  };

  if (error) {
    return (
      <div className="page-container">
        <div className="alert alert-danger">Error loading metrics: {error}</div>
      </div>
    );
  }

  return (
    <div className="page-container">
      {/* Header */}
      <div style={{ marginBottom: '2rem' }}>
        <h1 style={{ marginBottom: '0.5rem', fontWeight: 700 }}>Institutional-Grade Stock Metrics</h1>
        <p className="text-secondary">Advanced multi-factor analysis based on academic research and institutional methodology</p>
      </div>

      {/* Tabs */}
      <div style={{ borderBottom: '1px solid var(--border)', marginBottom: '1.5rem', display: 'flex', gap: '2rem' }}>
        <button
          onClick={() => setActiveTab(0)}
          style={{
            padding: '0.75rem 1rem',
            borderBottom: activeTab === 0 ? '2px solid var(--brand)' : '2px solid transparent',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontWeight: activeTab === 0 ? 600 : 400,
            color: activeTab === 0 ? 'var(--text-1)' : 'var(--text-2)',
          }}
        >
          Stock Metrics
        </button>
        <button
          onClick={() => setActiveTab(1)}
          style={{
            padding: '0.75rem 1rem',
            borderBottom: activeTab === 1 ? '2px solid var(--brand)' : '2px solid transparent',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontWeight: activeTab === 1 ? 600 : 400,
            color: activeTab === 1 ? 'var(--text-1)' : 'var(--text-2)',
          }}
        >
          Sector Analysis
        </button>
        <button
          onClick={() => setActiveTab(2)}
          style={{
            padding: '0.75rem 1rem',
            borderBottom: activeTab === 2 ? '2px solid var(--brand)' : '2px solid transparent',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontWeight: activeTab === 2 ? 600 : 400,
            color: activeTab === 2 ? 'var(--text-1)' : 'var(--text-2)',
          }}
        >
          Top Performers
        </button>
      </div>

      {/* Filters */}
      {activeTab === 0 && (
        <div className="card" style={{ padding: '1.5rem', marginBottom: '1.5rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem', alignItems: 'end' }}>
            <div>
              <label className="text-secondary" style={{ fontSize: '0.85rem', display: 'block', marginBottom: '0.5rem' }}>Search Symbol/Company</label>
              <input
                type="text"
                className="form-control"
                placeholder="Search..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
            <div>
              <label className="text-secondary" style={{ fontSize: '0.85rem', display: 'block', marginBottom: '0.5rem' }}>Sector</label>
              <select
                className="form-control"
                value={selectedSector}
                onChange={(e) => setSelectedSector(e.target.value)}
              >
                <option value="">All Sectors</option>
                <option value="Technology">Technology</option>
                <option value="Healthcare">Healthcare</option>
                <option value="Financial Services">Financial Services</option>
                <option value="Consumer Cyclical">Consumer Cyclical</option>
                <option value="Industrials">Industrials</option>
                <option value="Communication Services">Communication Services</option>
                <option value="Consumer Defensive">Consumer Defensive</option>
                <option value="Energy">Energy</option>
                <option value="Utilities">Utilities</option>
                <option value="Real Estate">Real Estate</option>
                <option value="Basic Materials">Basic Materials</option>
              </select>
            </div>
            <div>
              <label className="text-secondary" style={{ fontSize: '0.85rem', display: 'block', marginBottom: '0.5rem' }}>Sort By</label>
              <select
                className="form-control"
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
              >
                <option value="composite_metric">Composite Metric</option>
                <option value="quality_metric">Quality Metric</option>
                <option value="value_metric">Value Metric</option>
                <option value="market_cap">Market Cap</option>
                <option value="symbol">Symbol</option>
              </select>
            </div>
            <div>
              <select
                className="form-control"
                value={sortOrder}
                onChange={(e) => setSortOrder(e.target.value)}
              >
                <option value="desc">High → Low</option>
                <option value="asc">Low → High</option>
              </select>
            </div>
          </div>
        </div>
      )}

      {/* Content */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '3rem' }}>Loading metrics...</div>
      ) : (
        <>
          {/* Stock Metrics Table */}
          {activeTab === 0 && (
            <div className="card" style={{ marginTop: '1.5rem', overflow: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
                <thead>
                  <tr style={{ backgroundColor: 'var(--surface-2)', borderBottom: '1px solid var(--border)' }}>
                    <th style={{ padding: '0.75rem', textAlign: 'left', fontWeight: 600, color: 'var(--text-muted)' }}>Symbol</th>
                    <th style={{ padding: '0.75rem', textAlign: 'left', fontWeight: 600, color: 'var(--text-muted)' }}>Company</th>
                    <th style={{ padding: '0.75rem', textAlign: 'left', fontWeight: 600, color: 'var(--text-muted)' }}>Sector</th>
                    <th style={{ padding: '0.75rem', textAlign: 'center', fontWeight: 600, color: 'var(--text-muted)' }}>Composite</th>
                    <th style={{ padding: '0.75rem', textAlign: 'center', fontWeight: 600, color: 'var(--text-muted)' }}>Quality</th>
                    <th style={{ padding: '0.75rem', textAlign: 'center', fontWeight: 600, color: 'var(--text-muted)' }}>Value</th>
                    <th style={{ padding: '0.75rem', textAlign: 'center', fontWeight: 600, color: 'var(--text-muted)' }}>Growth</th>
                    <th style={{ padding: '0.75rem', textAlign: 'right', fontWeight: 600, color: 'var(--text-muted)' }}>Price</th>
                    <th style={{ padding: '0.75rem', textAlign: 'right', fontWeight: 600, color: 'var(--text-muted)' }}>Market Cap</th>
                  </tr>
                </thead>
                <tbody>
                  {(stocks || []).map((stock, idx) => (
                    <tr key={stock.symbol} style={{ borderTop: '1px solid var(--border)', backgroundColor: idx % 2 === 0 ? 'var(--surface)' : 'var(--surface-2)' }}>
                      <td style={{ padding: '0.75rem', fontWeight: 600, color: 'var(--brand)' }}>{stock.symbol}</td>
                      <td style={{ padding: '0.75rem', fontSize: '0.85rem' }}>{stock.company_name?.substring(0, 30)}</td>
                      <td style={{ padding: '0.75rem', fontSize: '0.85rem' }}>
                        <span style={{ padding: '0.25rem 0.5rem', borderRadius: '4px', backgroundColor: 'var(--surface-2)', fontSize: '0.8rem' }}>
                          {stock.sector}
                        </span>
                      </td>
                      <td style={{ padding: '0.75rem', textAlign: 'center', fontWeight: 600, color: getMetricColor(stock.composite_score || 0) }}>
                        {(stock.composite_score || 0).toFixed(3)}
                      </td>
                      <td style={{ padding: '0.75rem', textAlign: 'center', color: getMetricColor(stock.quality_score || 0) }}>
                        {(stock.quality_score || 0).toFixed(3)}
                      </td>
                      <td style={{ padding: '0.75rem', textAlign: 'center', color: getMetricColor(stock.value_score || 0) }}>
                        {(stock.value_score || 0).toFixed(3)}
                      </td>
                      <td style={{ padding: '0.75rem', textAlign: 'center', color: getMetricColor(stock.growth_score || 0) }}>
                        {(stock.growth_score || 0).toFixed(3)}
                      </td>
                      <td style={{ padding: '0.75rem', textAlign: 'right' }}>${stock.current_price?.toFixed(2) || 'N/A'}</td>
                      <td style={{ padding: '0.75rem', textAlign: 'right' }}>
                        {stock.market_cap ? `$${(stock.market_cap / 1e9).toFixed(1)}B` : 'N/A'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Sector Analysis */}
          {activeTab === 1 && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.5rem', marginTop: '1.5rem' }}>
              {(sectors || []).map((sector) => (
                <div key={sector.name} className="card" style={{ padding: '1.5rem' }}>
                  <h3 style={{ margin: '0 0 0.5rem 0', fontWeight: 600 }}>{sector.name}</h3>
                  <p className="text-secondary" style={{ margin: '0 0 1rem 0', fontSize: '0.9rem' }}>{sector.count} stocks</p>

                  <div style={{ marginBottom: '1rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', fontSize: '0.85rem' }}>
                      <span>Composite</span>
                      <span style={{ fontWeight: 600 }}>{parseFloat(sector.avgComposite || 0).toFixed(3)}</span>
                    </div>
                    <div style={{
                      width: '100%',
                      height: '8px',
                      backgroundColor: 'var(--border)',
                      borderRadius: '4px',
                      overflow: 'hidden'
                    }}>
                      <div style={{
                        width: `${Math.min(100, parseFloat(sector.avgComposite || 0) * 100)}%`,
                        height: '100%',
                        backgroundColor: getMetricColor(parseFloat(sector.avgComposite || 0)),
                        borderRadius: '4px'
                      }} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Top Stocks */}
          {activeTab === 2 && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1.5rem', marginTop: '1.5rem' }}>
              {Object.entries(topStocksData).map(([category, data]) => {
                const stocks = data?.items || [];
                const total = data?.total || 0;
                const scoreKey = category === "composite" ? "composite_score" : category === "quality" ? "quality_score" : "value_score";
                return (
                  <div key={category} className="card" style={{ padding: '1.5rem' }}>
                    <h3 style={{ margin: '0 0 0.5rem 0', fontWeight: 600, textTransform: 'capitalize' }}>
                      Top {category === "composite" ? "Overall" : category} Stocks
                      {total > 10 && <span style={{ fontSize: '0.8rem', marginLeft: '0.5rem', color: 'var(--text-3)' }}>({stocks.length} of {total})</span>}
                    </h3>
                    <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
                      {(stocks || []).map((stock, index) => (
                        <div
                          key={stock.symbol}
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            padding: '0.75rem 0',
                            borderBottom: index < 9 ? '1px solid var(--border)' : 'none'
                          }}
                        >
                          <div>
                            <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>
                              {index + 1}. {stock.symbol}
                            </div>
                            <div className="text-secondary" style={{ fontSize: '0.8rem' }}>
                              {stock.company_name?.substring(0, 25)}
                            </div>
                          </div>
                          <div style={{ textAlign: 'right' }}>
                            <div style={{ fontWeight: 600, color: getMetricColor(stock[scoreKey] || 0), fontSize: '0.95rem' }}>
                              {(stock[scoreKey] || 0).toFixed(3)}
                            </div>
                            <div className="text-secondary" style={{ fontSize: '0.8rem' }}>
                              {stock.sector}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* Legend */}
      <div className="card" style={{ padding: '1.5rem', marginTop: '2rem', backgroundColor: 'var(--surface-2)' }}>
        <h3 style={{ margin: '0 0 1rem 0', fontWeight: 600 }}>Metrics Methodology</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1.5rem', marginBottom: '1.5rem' }}>
          <div>
            <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>Quality Metric</div>
            <p className="text-secondary" style={{ fontSize: '0.9rem', margin: 0 }}>
              Financial statement quality, balance sheet strength, profitability, management effectiveness using Piotroski F-Score, Altman Z-Score analysis
            </p>
          </div>
          <div>
            <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>Value Metric</div>
            <p className="text-secondary" style={{ fontSize: '0.9rem', margin: 0 }}>
              Traditional multiples (P/E, P/B, EV/EBITDA), DCF intrinsic value, dividend discount model, and peer comparison analysis
            </p>
          </div>
          <div>
            <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>Growth Metric</div>
            <p className="text-secondary" style={{ fontSize: '0.9rem', margin: 0 }}>
              Revenue growth analysis, earnings growth quality, fundamental growth drivers, and market expansion potential
            </p>
          </div>
        </div>

        <div style={{ borderTop: '1px solid var(--border)', paddingTop: '1rem' }}>
          <div style={{ fontWeight: 600, marginBottom: '0.75rem' }}>Metric Ranges (0-1 Scale):</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem' }}>
            {[
              { v: 0.9, label: 'Excellent (0.8-1.0)' },
              { v: 0.75, label: 'Good (0.7-0.79)' },
              { v: 0.65, label: 'Fair (0.6-0.69)' },
              { v: 0.55, label: 'Below Average (0.5-0.59)' },
              { v: 0.4, label: 'Poor (0.0-0.49)' }
            ].map((item) => (
              <span
                key={item.label}
                style={{
                  padding: '0.5rem 0.75rem',
                  borderRadius: '4px',
                  backgroundColor: getMetricColor(item.v),
                  color: '#fff',
                  fontWeight: 600,
                  fontSize: '0.85rem'
                }}
              >
                {item.label}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default MetricsDashboard;
