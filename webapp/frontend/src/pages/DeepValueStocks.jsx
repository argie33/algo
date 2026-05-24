import React, { useState, useMemo } from "react";
import {
  TrendingUp,
  Download as DownloadIcon,
  Info as InfoIcon,
  CheckCircle as VerifiedIcon,
  X as CloseIcon,
} from "lucide-react";
import { useApiQuery } from "../hooks/useApiQuery";
import api from "../services/api";

const DeepValueStocks = () => {
  const [selectedStock, setSelectedStock] = useState(null);
  const [infoOpen, setInfoOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(100);
  const [sortBy, setSortBy] = useState("generational_score");
  const [sortOrder, setSortOrder] = useState("desc");
  const [limit, setLimit] = useState(600); // Allow user to change limit

  const { data: rawStocks = [], loading, error } = useApiQuery(
    ['deepValueStocks', limit],
    () => api.get(`/api/stocks/deep-value?limit=${limit}`)
  );

  const stocks = useMemo(() => {
    const stocksData = Array.isArray(rawStocks) ? rawStocks : (rawStocks?.items || []);
    const num = (v) => v != null ? parseFloat(v) : null;
    return stocksData.map(s => ({
      ...s,
      generational_score: parseFloat(s.generational_score) || 0,
      current_price: num(s.current_price),
      trailing_pe: num(s.trailing_pe),
      price_to_book: num(s.price_to_book),
      price_to_sales: num(s.price_to_sales),
      roe_pct: num(s.roe_pct),
      op_margin_pct: num(s.op_margin_pct),
      gross_margin_pct: num(s.gross_margin_pct),
      net_margin_pct: num(s.net_margin_pct),
      roa_pct: num(s.roa_pct),
      ev_to_ebitda: num(s.ev_to_ebitda),
      peg_ratio: num(s.peg_ratio),
      dividend_yield: num(s.dividend_yield),
      debt_to_equity: num(s.debt_to_equity),
      current_ratio: num(s.current_ratio),
      sector_median_pe: num(s.sector_median_pe),
      market_median_pe: num(s.market_median_pe),
      discount_vs_sector_pe_pct: num(s.discount_vs_sector_pe_pct),
      discount_vs_market_pe_pct: num(s.discount_vs_market_pe_pct),
      high_52w: num(s.high_52w),
      high_3y: num(s.high_3y),
      low_52w: num(s.low_52w),
      drop_from_52w_high_pct: num(s.drop_from_52w_high_pct),
      drop_from_3y_high_pct: num(s.drop_from_3y_high_pct),
      intrinsic_value_per_share: num(s.intrinsic_value_per_share),
      margin_of_safety_pct: num(s.margin_of_safety_pct),
      revenue_growth_3y_pct: num(s.revenue_growth_3y_pct),
      eps_growth_3y_pct: num(s.eps_growth_3y_pct),
      revenue_growth_yoy_pct: num(s.revenue_growth_yoy_pct),
      fcf_growth_yoy_pct: num(s.fcf_growth_yoy_pct),
      sustainable_growth_pct: num(s.sustainable_growth_pct),
      op_margin_trend_pp: num(s.op_margin_trend_pp),
      gross_margin_trend_pp: num(s.gross_margin_trend_pp),
      roe_trend_pp: num(s.roe_trend_pp),
    }));
  }, [rawStocks]);

  const sorted = [...stocks].sort((a, b) => {
    const aVal = a[sortBy];
    const bVal = b[sortBy];
    if (aVal == null) return 1;
    if (bVal == null) return -1;
    const cmp = aVal > bVal ? 1 : aVal < bVal ? -1 : 0;
    return sortOrder === "desc" ? -cmp : cmp;
  });

  const handleSort = (field) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === "desc" ? "asc" : "desc");
    } else {
      setSortBy(field);
      setSortOrder("desc");
    }
    setPage(0);
  };

  const fmt = (v, dec = 2) => v != null ? parseFloat(v).toFixed(dec) : "â€”";
  const fmtPct = (v, dec = 1) => v != null ? `${parseFloat(v).toFixed(dec)}%` : "â€”";
  const fmtDiscount = (v) => v != null ? `${parseFloat(v).toFixed(1)}%` : "â€”";

  const avg = (arr, key) => {
    const vals = arr.map(s => s[key]).filter(v => v != null && !isNaN(v));
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  };

  const qualityBadge = (tier) => {
    if (tier === "tier1") return { label: "Tier 1", color: "#22c55e", bg: "rgba(34, 197, 94, 0.16)" };
    if (tier === "tier2") return { label: "Tier 2", color: "#22c55e", bg: "rgba(34, 197, 94, 0.12)" };
    return { label: "Other", color: "#b8c0d9", bg: "rgba(184, 192, 217, 0.12)" };
  };

  const MetricGrid = ({ items }) => (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
      gap: 'var(--space-2)',
      marginBottom: 'var(--space-3)',
    }}>
      {items.map(([label, val, color]) => (
        <div key={label} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <p style={{ margin: 0, fontSize: 'var(--t-2xs)', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 'var(--w-bold)' }}>
            {label}
          </p>
          <p style={{ margin: 0, fontSize: 'var(--t-sm)', fontWeight: 'var(--w-semibold)', color: color || 'var(--text)' }}>
            {val}
          </p>
        </div>
      ))}
    </div>
  );

  const StockDetailDialog = ({ stock, open, onClose }) => {
    if (!stock || !open) return null;
    const tier = qualityBadge(stock.quality_rank);

    return (
      <div style={{
        position: 'fixed',
        inset: 0,
        background: 'var(--overlay)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 100,
        backdropFilter: 'blur(8px)',
        padding: 'var(--space-4)',
      }} onClick={onClose}>
        <div style={{
          background: 'var(--surface)',
          borderRadius: 'var(--r-lg)',
          border: '1px solid var(--border)',
          maxWidth: '700px',
          width: '100%',
          maxHeight: '90vh',
          overflow: 'auto',
          boxShadow: 'var(--shadow-xl)',
        }} onClick={(e) => e.stopPropagation()}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: 'var(--space-5)',
            borderBottom: '1px solid var(--border)',
            position: 'sticky',
            top: 0,
            background: 'var(--surface)',
            zIndex: 10,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', minWidth: 0 }}>
              <h2 style={{ margin: 0, fontSize: 'var(--t-lg)', fontWeight: 'var(--w-bold)', color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {stock.symbol}
              </h2>
              {stock.company_name && <p style={{ margin: 0, fontSize: 'var(--t-sm)', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>â€” {stock.company_name}</p>}
              {(stock.quality_rank === "tier1" || stock.quality_rank === "tier2") && (
                <VerifiedIcon size={18} color={tier.color} style={{ flexShrink: 0 }} />
              )}
            </div>
            <button onClick={onClose} style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              padding: 'var(--space-2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--text-2)',
              flexShrink: 0,
            }}>
              <CloseIcon size={20} />
            </button>
          </div>

          <div style={{ padding: 'var(--space-5)', fontSize: 'var(--t-sm)' }}>
            <div style={{ display: "flex", gap: 'var(--space-2)', flexWrap: "wrap", marginBottom: 'var(--space-4)' }}>
              <span className="badge badge-brand">{`Generational Score: ${fmt(stock.generational_score, 1)}`}</span>
              <span style={{
                display: 'inline-flex',
                alignItems: 'center',
                padding: '2px var(--space-2)',
                borderRadius: 'var(--r-sm)',
                backgroundColor: tier.bg,
                color: tier.color,
                fontWeight: 'var(--w-bold)',
                fontSize: 'var(--t-2xs)',
                textTransform: 'uppercase',
              }}>
                {tier.label}
              </span>
              {stock.current_price != null && (
                <span className="badge">{`Price: $${stock.current_price.toFixed(2)}`}</span>
              )}
            </div>
            {stock.sector && <p style={{ margin: '0 0 var(--space-3) 0', fontSize: 'var(--t-xs)', color: 'var(--text-muted)' }}>{stock.sector} â€¢ {stock.industry}</p>}

            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 'var(--space-4)', marginTop: 'var(--space-4)' }}>
              <h3 style={{ margin: '0 0 var(--space-3) 0', fontSize: 'var(--t-sm)', fontWeight: 'var(--w-semibold)', color: 'var(--text)' }}>Current Valuation</h3>
              <MetricGrid items={[
                ["P/E Ratio", fmt(stock.trailing_pe)],
                ["P/B Ratio", fmt(stock.price_to_book)],
                ["P/S Ratio", fmt(stock.price_to_sales)],
                ["EV/EBITDA", fmt(stock.ev_to_ebitda)],
                ["PEG Ratio", fmt(stock.peg_ratio)],
                ["Div Yield", fmtPct(stock.dividend_yield)],
              ]} />
            </div>

            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 'var(--space-4)', marginTop: 'var(--space-4)' }}>
              <h3 style={{ margin: '0 0 var(--space-3) 0', fontSize: 'var(--t-sm)', fontWeight: 'var(--w-semibold)', color: '#6366f1' }}>ðŸ“Š DCF / Intrinsic Value</h3>
              <MetricGrid items={[
                ["Current Price", stock.current_price != null ? `$${stock.current_price.toFixed(2)}` : "â€”"],
                ["Intrinsic Value", stock.intrinsic_value_per_share != null ? `$${stock.intrinsic_value_per_share.toFixed(2)}` : "â€”"],
                ["Margin of Safety", stock.margin_of_safety_pct != null ? `${stock.margin_of_safety_pct.toFixed(1)}%` : "â€”", stock.margin_of_safety_pct >= 30 ? "#22c55e" : stock.margin_of_safety_pct >= 0 ? "#a1d922" : "#ef4444"],
              ]} />
            </div>

            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 'var(--space-4)', marginTop: 'var(--space-4)' }}>
              <h3 style={{ margin: '0 0 var(--space-3) 0', fontSize: 'var(--t-sm)', fontWeight: 'var(--w-semibold)', color: '#ef4444' }}>ðŸ”¥ Price Action / Fire Sale</h3>
              <MetricGrid items={[
                ["52w High", stock.high_52w != null ? `$${stock.high_52w.toFixed(2)}` : "â€”"],
                ["3y High", stock.high_3y != null ? `$${stock.high_3y.toFixed(2)}` : "â€”"],
                ["52w Low", stock.low_52w != null ? `$${stock.low_52w.toFixed(2)}` : "â€”"],
                ["â†“52w", fmtPct(stock.drop_from_52w_high_pct), stock.drop_from_52w_high_pct >= 30 ? "#ef4444" : "inherit"],
                ["â†“3y", fmtPct(stock.drop_from_3y_high_pct), stock.drop_from_3y_high_pct >= 40 ? "#ef4444" : "inherit"],
                ["Disc/Sector", fmtDiscount(stock.discount_vs_sector_pe_pct)],
                ["Disc/Market", fmtDiscount(stock.discount_vs_market_pe_pct)],
              ]} />
            </div>

            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 'var(--space-4)', marginTop: 'var(--space-4)' }}>
              <h3 style={{ margin: '0 0 var(--space-3) 0', fontSize: 'var(--t-sm)', fontWeight: 'var(--w-semibold)', color: '#22c55e' }}>ðŸ’Ž Quality & Profitability</h3>
              <MetricGrid items={[
                ["ROE", fmtPct(stock.roe_pct), stock.roe_pct >= 35 ? "#22c55e" : "inherit"],
                ["ROA", fmtPct(stock.roa_pct)],
                ["Gross Margin", fmtPct(stock.gross_margin_pct), stock.gross_margin_pct >= 50 ? "#22c55e" : "inherit"],
                ["Op Margin", fmtPct(stock.op_margin_pct), stock.op_margin_pct >= 20 ? "#22c55e" : "inherit"],
                ["Net Margin", fmtPct(stock.net_margin_pct)],
                ["D/E", fmt(stock.debt_to_equity), stock.debt_to_equity < 0.5 ? "#22c55e" : "inherit"],
                ["Cur Ratio", fmt(stock.current_ratio), stock.current_ratio > 2 ? "#22c55e" : "inherit"],
              ]} />
            </div>

            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 'var(--space-4)', marginTop: 'var(--space-4)' }}>
              <h3 style={{ margin: '0 0 var(--space-3) 0', fontSize: 'var(--t-sm)', fontWeight: 'var(--w-semibold)', color: '#22c55e' }}>ðŸ“ˆ Growth Engine</h3>
              <MetricGrid items={[
                ["Rev 3Y CAGR", fmtPct(stock.revenue_growth_3y_pct), stock.revenue_growth_3y_pct >= 10 ? "#22c55e" : "inherit"],
                ["EPS 3Y CAGR", fmtPct(stock.eps_growth_3y_pct), stock.eps_growth_3y_pct >= 15 ? "#22c55e" : "inherit"],
                ["Rev YoY", fmtPct(stock.revenue_growth_yoy_pct), stock.revenue_growth_yoy_pct >= 5 ? "#a1d922" : stock.revenue_growth_yoy_pct < 0 ? "#ef4444" : "inherit"],
                ["FCF YoY", fmtPct(stock.fcf_growth_yoy_pct), stock.fcf_growth_yoy_pct >= 0 ? "#a1d922" : "#ef4444"],
                ["Sust Growth", fmtPct(stock.sustainable_growth_pct)],
                ["PEG", fmt(stock.peg_ratio), stock.peg_ratio < 1 && stock.peg_ratio > 0 ? "#22c55e" : "inherit"],
              ]} />
            </div>

            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 'var(--space-4)', marginTop: 'var(--space-4)' }}>
              <h3 style={{ margin: '0 0 var(--space-3) 0', fontSize: 'var(--t-sm)', fontWeight: 'var(--w-semibold)', color: '#f97316' }}>âš ï¸ Trap Detection (YoY Trends)</h3>
              <p style={{ margin: '0 0 var(--space-2) 0', fontSize: 'var(--t-2xs)', color: 'var(--text-muted)' }}>
                Are quality metrics improving âœ“ or declining âœ—? Negative = potential value trap.
              </p>
              <MetricGrid items={[
                ["Op M Trend", stock.op_margin_trend_pp != null ? `${stock.op_margin_trend_pp >= 0 ? "+" : ""}${stock.op_margin_trend_pp.toFixed(2)}pp` : "â€”", stock.op_margin_trend_pp >= 0 ? "#22c55e" : stock.op_margin_trend_pp > -3 ? "#f97316" : "#ef4444"],
                ["GM Trend", stock.gross_margin_trend_pp != null ? `${stock.gross_margin_trend_pp >= 0 ? "+" : ""}${stock.gross_margin_trend_pp.toFixed(2)}pp` : "â€”", stock.gross_margin_trend_pp >= 0 ? "#22c55e" : stock.gross_margin_trend_pp > -3 ? "#f97316" : "#ef4444"],
                ["ROE Trend", stock.roe_trend_pp != null ? `${stock.roe_trend_pp >= 0 ? "+" : ""}${stock.roe_trend_pp.toFixed(2)}pp` : "â€”", stock.roe_trend_pp >= 0 ? "#22c55e" : stock.roe_trend_pp > -10 ? "#f97316" : "#ef4444"],
              ]} />
            </div>
          </div>
        </div>
      </div>
    );
  };

  const InfoDialog = ({ open, onClose }) => {
    if (!open) return null;
    return (
      <div style={{
        position: 'fixed',
        inset: 0,
        background: 'var(--overlay)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 100,
        backdropFilter: 'blur(8px)',
        padding: 'var(--space-4)',
      }} onClick={onClose}>
        <div style={{
          background: 'var(--surface)',
          borderRadius: 'var(--r-lg)',
          border: '1px solid var(--border)',
          maxWidth: '700px',
          width: '100%',
          maxHeight: '90vh',
          overflow: 'auto',
          boxShadow: 'var(--shadow-xl)',
        }} onClick={(e) => e.stopPropagation()}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: 'var(--space-5)',
            borderBottom: '1px solid var(--border)',
            position: 'sticky',
            top: 0,
            background: 'var(--surface)',
            zIndex: 10,
          }}>
            <h2 style={{ margin: 0, fontSize: 'var(--t-lg)', fontWeight: 'var(--w-bold)', color: 'var(--text)' }}>
              How Generational Opportunities Are Identified
            </h2>
            <button onClick={onClose} style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              padding: 'var(--space-2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--text-2)',
              flexShrink: 0,
            }}>
              <CloseIcon size={20} />
            </button>
          </div>
          <div style={{ padding: 'var(--space-5)', fontSize: 'var(--t-sm)', lineHeight: 'var(--lh-normal)' }}>
            <h3 style={{ margin: '0 0 var(--space-2) 0', fontWeight: 'var(--w-semibold)', color: 'var(--text)' }}>Quality Criteria (Tier 1 & 2)</h3>
            <ul style={{ margin: '0 0 var(--space-3) var(--space-3)', color: 'var(--text-2)' }}>
              <li><strong>Tier 1:</strong> ROE â‰¥ 25% + Op Margin â‰¥ 15%</li>
              <li><strong>Tier 2:</strong> ROE â‰¥ 20% + Op Margin â‰¥ 12%</li>
              <li>Current Ratio &gt; 1.5 (financial fortress)</li>
              <li>Debt/Equity &lt; 2.0 (sustainable leverage)</li>
            </ul>

            <h3 style={{ margin: '0 0 var(--space-2) 0', fontWeight: 'var(--w-semibold)', color: 'var(--text)' }}>Anomaly Detection (Valuation Mismatch)</h3>
            <p style={{ margin: '0 0 var(--space-2) 0', color: 'var(--text-2)' }}>Compares valuation to three baselines:</p>
            <ul style={{ margin: '0 0 var(--space-3) var(--space-3)', color: 'var(--text-2)' }}>
              <li><strong>Historical:</strong> Current P/E vs 3y average. Shows temporary panic.</li>
              <li><strong>Sector Peers:</strong> Current P/E vs sector median. Market misprice signal.</li>
              <li><strong>Overall Market:</strong> Current P/E vs S&P 500 median. Stock-specific vs market-wide.</li>
            </ul>

            <h3 style={{ margin: '0 0 var(--space-2) 0', fontWeight: 'var(--w-semibold)', color: 'var(--text)' }}>Generational Score (0-100)</h3>
            <ul style={{ margin: '0 0 var(--space-3) var(--space-3)', color: 'var(--text-2)' }}>
              <li>PE Cheapness (30%)</li>
              <li>PB Cheapness (20%)</li>
              <li>ROE Quality (25%)</li>
              <li>Margin Quality (15%)</li>
              <li>Liquidity (10%)</li>
            </ul>

            <div style={{ padding: 'var(--space-3)', backgroundColor: "rgba(245, 158, 11, 0.16)", borderRadius: 'var(--r-md)', borderLeft: '3px solid #f59e0b' }}>
              <p style={{ margin: 0, fontWeight: 'var(--w-semibold)', color: '#f59e0b' }}>
                ðŸŽ¯ EXCEPTIONAL QUALITY meets ANOMALY PRICING. Rare â€” perhaps 5-30 stocks at any moment. Where generational wealth compounds.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div style={{
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        height: "400px",
        color: 'var(--text-muted)',
      }}>
        <p>Loading opportunities...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="alert alert-danger" style={{ margin: 'var(--space-4)' }}>
        {error}
      </div>
    );
  }

  const paginated = sorted.slice(page * rowsPerPage, (page + 1) * rowsPerPage);
  const avgROE = avg(stocks, "roe_pct");
  const avgMoS = avg(stocks, "margin_of_safety_pct");
  const avgDrop = avg(stocks, "drop_from_3y_high_pct");

  return (
    <div style={{ padding: 'var(--space-6)' }}>
      <div style={{ marginBottom: 'var(--space-6)' }}>
        <h1 style={{ margin: '0 0 var(--space-2) 0', fontSize: 'var(--t-2xl)', fontWeight: 'var(--w-bold)', color: 'var(--text)' }}>
          Generational Opportunities
        </h1>
        <p style={{ margin: '0 0 var(--space-3) 0', maxWidth: '800px', color: 'var(--text-2)' }}>
          Tier-1 quality companies trading at anomaly prices. These stocks combine exceptional fundamentals (ROE &gt; 25%, margins &gt; 15%) with extreme valuations discounts. This is where generational wealth is built.
        </p>
      </div>

      <div className="grid grid-4" style={{ marginBottom: 'var(--space-6)' }}>
        <div className="kpi">
          <div className="kpi-label">Opportunities Found</div>
          <div className="kpi-value" style={{ color: "#22c55e" }}>{stocks.length}</div>
          <div className="kpi-sub">Tier 1 & 2 quality stocks</div>
        </div>
        <div className="kpi" style={{ backgroundColor: "rgba(99, 102, 241, 0.12)" }}>
          <div className="kpi-label">Avg Margin of Safety</div>
          <div className="kpi-value" style={{ color: "#818cf8" }}>{avgMoS != null ? avgMoS.toFixed(0) + "%" : "â€”"}</div>
          <div className="kpi-sub">DCF intrinsic value vs price</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Avg Drop from High</div>
          <div className="kpi-value" style={{ color: "#ef4444" }}>{avgDrop != null ? avgDrop.toFixed(0) + "%" : "â€”"}</div>
          <div className="kpi-sub">Fire sale magnitude (3y)</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Avg ROE</div>
          <div className="kpi-value" style={{ color: "#22c55e" }}>{avgROE != null ? avgROE.toFixed(1) + "%" : "â€”"}</div>
          <div className="kpi-sub">Elite quality metric</div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 'var(--space-4)', padding: 'var(--space-4)' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 'var(--space-3)', alignItems: 'center' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
            <label style={{ fontSize: 'var(--t-2xs)', color: 'var(--text-muted)', fontWeight: 'var(--w-bold)', textTransform: 'uppercase' }}>Sort By</label>
            <select value={sortBy} onChange={(e) => { setSortBy(e.target.value); setPage(0); }} className="input">
              <option value="generational_score">Generational Score</option>
              <option value="discount_vs_historical_pe_pct">Historical Discount</option>
              <option value="roe_pct">ROE</option>
              <option value="trailing_pe">P/E Ratio</option>
              <option value="op_margin_pct">Op. Margin</option>
            </select>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
            <label style={{ fontSize: 'var(--t-2xs)', color: 'var(--text-muted)', fontWeight: 'var(--w-bold)', textTransform: 'uppercase' }}>Rows per page</label>
            <select value={rowsPerPage} onChange={(e) => { setRowsPerPage(Number(e.target.value)); setPage(0); }} className="input">
              <option value={20}>20</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
            <label style={{ fontSize: 'var(--t-2xs)', color: 'var(--text-muted)', fontWeight: 'var(--w-bold)', textTransform: 'uppercase' }}>Load records</label>
            <select value={limit} onChange={(e) => { setLimit(Number(e.target.value)); setPage(0); }} className="input">
              <option value={200}>200</option>
              <option value={600}>600</option>
              <option value={1000}>1,000</option>
              <option value={2000}>2,000</option>
              <option value={5000}>5,000</option>
            </select>
          </div>
          <button className="btn btn-outline" onClick={() => {
            const csv = [
              ["Symbol", "Company", "Quality", "Gen.Score", "P/E", "ROE%", "OpM%", "Sector Disc%", "Market Disc%", "D/E", "Cur.Ratio"],
              ...sorted.map(s => [
                s.symbol,
                s.company_name || "",
                s.quality_rank || "",
                fmt(s.generational_score, 1),
                fmt(s.trailing_pe),
                fmtPct(s.roe_pct),
                fmtPct(s.op_margin_pct),
                fmtDiscount(s.discount_vs_sector_pe_pct),
                fmtDiscount(s.discount_vs_market_pe_pct),
                fmt(s.debt_to_equity),
                fmt(s.current_ratio),
              ]),
            ].map(r => r.join(",")).join("\n");
            const blob = new Blob([csv], { type: "text/csv" });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "generational_opportunities.csv";
            a.click();
          }} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', justifyContent: 'center' }}>
            <DownloadIcon size={14} />
            Export CSV
          </button>
          <button className="btn btn-outline" onClick={() => setInfoOpen(true)} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', justifyContent: 'center' }}>
            <InfoIcon size={14} />
            How It Works
          </button>
        </div>
      </div>

      {stocks.length === 0 ? (
        <div className="alert alert-info">
          No generational opportunities found at this time. Market conditions may need deeper dislocations.
        </div>
      ) : (
        <>
          <div style={{ marginBottom: 'var(--space-3)', display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 'var(--t-sm)', color: 'var(--text-muted)' }}>
            <span>Showing {page * rowsPerPage + 1}â€“{Math.min((page + 1) * rowsPerPage, sorted.length)} of {sorted.length} opportunities</span>
            <div style={{ display: "flex", gap: 'var(--space-2)' }}>
              <button className="btn btn-sm btn-outline" disabled={page === 0} onClick={() => setPage(p => p - 1)}>Prev</button>
              <button className="btn btn-sm btn-outline" disabled={(page + 1) * rowsPerPage >= sorted.length} onClick={() => setPage(p => p + 1)}>Next</button>
            </div>
          </div>

          <div className="card" style={{ padding: 0, overflow: 'auto' }}>
            <table className="data-table" style={{ marginBottom: 0 }}>
              <thead>
                <tr>
                  <th style={{ position: "sticky", left: 0, zIndex: 2, backgroundColor: 'var(--bg-2)' }}>Symbol</th>
                  <th style={{ minWidth: '180px' }}>Company</th>
                  <th style={{ minWidth: '90px' }}>Sector</th>
                  <th style={{ minWidth: '70px' }}>Quality</th>
                  <th style={{ textAlign: 'right', cursor: "pointer" }} onClick={() => handleSort("current_price")}>Price</th>
                  <th style={{ textAlign: 'right', cursor: "pointer" }} onClick={() => handleSort("trailing_pe")}>P/E</th>
                  <th style={{ textAlign: 'right', cursor: "pointer" }} onClick={() => handleSort("roe_pct")}>ROE%</th>
                  <th style={{ textAlign: 'right', cursor: "pointer" }} onClick={() => handleSort("op_margin_pct")}>OpM%</th>
                  <th style={{ textAlign: 'right', cursor: "pointer" }} onClick={() => handleSort("drop_from_52w_high_pct")}>â†“52w</th>
                  <th style={{ textAlign: 'right', cursor: "pointer" }} onClick={() => handleSort("drop_from_3y_high_pct")}>â†“3y</th>
                  <th style={{ textAlign: 'right', cursor: "pointer", backgroundColor: "rgba(99, 102, 241, 0.12)" }} onClick={() => handleSort("intrinsic_value_per_share")}>Intrinsic $</th>
                  <th style={{ textAlign: 'right', cursor: "pointer", backgroundColor: "rgba(99, 102, 241, 0.12)" }} onClick={() => handleSort("margin_of_safety_pct")}>MoS %</th>
                  <th style={{ textAlign: 'right' }}>RevYoY%</th>
                  <th style={{ textAlign: 'right' }}>OpM Trend</th>
                  <th style={{ textAlign: 'right' }}>D/E</th>
                </tr>
              </thead>
              <tbody>
                {paginated.map((stock, idx) => {
                  const globalIdx = page * rowsPerPage + idx;
                  const tier = qualityBadge(stock.quality_rank);
                  return (
                    <tr key={stock.symbol} onClick={() => { setSelectedStock(stock); setDetailOpen(true); }} style={{ cursor: 'pointer' }}>
                      <td style={{
                        fontWeight: 700,
                        fontSize: "1.05em",
                        color: globalIdx === 0 ? "#6366f1" : "inherit",
                        position: "sticky",
                        left: 0,
                        backgroundColor: idx % 2 === 0 ? (globalIdx === 0 ? "rgba(99, 102, 241, 0.08)" : 'var(--bg-2)') : 'transparent',
                        zIndex: 1,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 'var(--space-1)',
                      }}>
                        {globalIdx === 0 && <TrendingUp size={14} color="#22c55e" />}
                        {stock.symbol}
                      </td>
                      <td style={{ fontSize: 'var(--t-sm)', fontWeight: 500 }}>{stock.company_name || "â€”"}</td>
                      <td style={{ fontSize: 'var(--t-2xs)', color: 'var(--text-2)' }}>{stock.sector || "â€”"}</td>
                      <td style={{ fontSize: 'var(--t-2xs)' }}>
                        <span style={{
                          display: 'inline-flex',
                          padding: '2px var(--space-2)',
                          borderRadius: 'var(--r-sm)',
                          backgroundColor: tier.bg,
                          color: tier.color,
                          fontWeight: 'var(--w-bold)',
                        }}>
                          {tier.label}
                        </span>
                      </td>
                      <td style={{ textAlign: 'right', fontSize: 'var(--t-2xs)', fontWeight: 600 }}>
                        {stock.current_price != null ? `$${stock.current_price.toFixed(2)}` : "â€”"}
                      </td>
                      <td style={{ textAlign: 'right', fontSize: 'var(--t-2xs)' }}>{fmt(stock.trailing_pe)}</td>
                      <td style={{ textAlign: 'right', fontSize: 'var(--t-2xs)', color: stock.roe_pct != null && stock.roe_pct > 25 ? "#22c55e" : "inherit", fontWeight: stock.roe_pct > 25 ? 700 : 400 }}>
                        {fmtPct(stock.roe_pct)}
                      </td>
                      <td style={{ textAlign: 'right', fontSize: 'var(--t-2xs)', color: stock.op_margin_pct != null && stock.op_margin_pct > 15 ? "#22c55e" : "inherit", fontWeight: stock.op_margin_pct > 15 ? 700 : 400 }}>
                        {fmtPct(stock.op_margin_pct)}
                      </td>
                      <td style={{ textAlign: 'right', fontSize: 'var(--t-2xs)', color: stock.drop_from_52w_high_pct >= 30 ? "#c62828" : "inherit", fontWeight: stock.drop_from_52w_high_pct >= 25 ? 700 : 400 }}>
                        {fmtDiscount(stock.drop_from_52w_high_pct)}
                      </td>
                      <td style={{ textAlign: 'right', fontSize: 'var(--t-2xs)', color: stock.drop_from_3y_high_pct >= 50 ? "#c62828" : "inherit", fontWeight: stock.drop_from_3y_high_pct >= 40 ? 700 : 400 }}>
                        {fmtDiscount(stock.drop_from_3y_high_pct)}
                      </td>
                      <td style={{ textAlign: 'right', fontSize: 'var(--t-2xs)', fontWeight: 700, backgroundColor: "rgba(99, 102, 241, 0.12)", color: "#818cf8" }}>
                        {stock.intrinsic_value_per_share != null ? `$${stock.intrinsic_value_per_share.toFixed(2)}` : "â€”"}
                      </td>
                      <td style={{ textAlign: 'right', fontSize: 'var(--t-2xs)', fontWeight: 700, backgroundColor: "rgba(99, 102, 241, 0.12)", color: stock.margin_of_safety_pct >= 30 ? "#22c55e" : stock.margin_of_safety_pct >= 0 ? "#a1d922" : "#ef4444" }}>
                        {stock.margin_of_safety_pct != null ? `${stock.margin_of_safety_pct.toFixed(1)}%` : "â€”"}
                      </td>
                      <td style={{ textAlign: 'right', fontSize: 'var(--t-2xs)', color: stock.revenue_growth_yoy_pct >= 0 ? "#1b5e20" : "#c62828", fontWeight: 600 }}>
                        {fmtPct(stock.revenue_growth_yoy_pct)}
                      </td>
                      <td style={{ textAlign: 'right', fontSize: 'var(--t-2xs)', color: stock.op_margin_trend_pp >= 0 ? "#1b5e20" : stock.op_margin_trend_pp > -3 ? "#f57c00" : "#c62828" }}>
                        {stock.op_margin_trend_pp != null ? `${stock.op_margin_trend_pp >= 0 ? "+" : ""}${stock.op_margin_trend_pp.toFixed(2)}pp` : "â€”"}
                      </td>
                      <td style={{ textAlign: 'right', fontSize: 'var(--t-2xs)', color: stock.debt_to_equity > 2 ? "#c62828" : stock.debt_to_equity < 0.5 ? "#1b5e20" : "inherit" }}>
                        {fmt(stock.debt_to_equity)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div style={{ marginTop: 'var(--space-3)', display: "flex", justifyContent: "flex-end", gap: 'var(--space-2)' }}>
            <button className="btn btn-sm btn-outline" disabled={page === 0} onClick={() => { setPage(p => p - 1); window.scrollTo({ top: 0, behavior: "smooth" }); }}>Prev</button>
            <button className="btn btn-sm btn-outline" disabled={(page + 1) * rowsPerPage >= sorted.length} onClick={() => { setPage(p => p + 1); window.scrollTo({ top: 0, behavior: "smooth" }); }}>Next</button>
          </div>
        </>
      )}

      <StockDetailDialog stock={selectedStock} open={detailOpen} onClose={() => setDetailOpen(false)} />
      <InfoDialog open={infoOpen} onClose={() => setInfoOpen(false)} />
    </div>
  );
};

export default DeepValueStocks;

