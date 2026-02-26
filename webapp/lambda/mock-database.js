// Mock database for testing without PostgreSQL
// This allows the frontend to show data while PostgreSQL is being installed

const mockData = {
  stocks: [
    { symbol: "AAPL", name: "Apple Inc.", sector: "Technology", price: 225.50, change: 2.5, composite_score: 8.5 },
    { symbol: "MSFT", name: "Microsoft Corp.", sector: "Technology", price: 425.30, change: 1.8, composite_score: 8.2 },
    { symbol: "GOOGL", name: "Alphabet Inc.", sector: "Technology", price: 165.80, change: 3.2, composite_score: 8.0 },
    { symbol: "TSLA", name: "Tesla Inc.", sector: "Automotive", price: 265.75, change: -1.2, composite_score: 7.5 },
    { symbol: "AMZN", name: "Amazon.com Inc.", sector: "Consumer", price: 188.45, change: 2.1, composite_score: 8.3 },
    { symbol: "META", name: "Meta Platforms", sector: "Technology", price: 625.40, change: 4.5, composite_score: 7.8 },
    { symbol: "NVDA", name: "NVIDIA Corp.", sector: "Technology", price: 875.30, change: 5.2, composite_score: 9.0 },
    { symbol: "JPM", name: "JPMorgan Chase", sector: "Finance", price: 198.75, change: 1.5, composite_score: 7.2 },
    { symbol: "JNJ", name: "Johnson & Johnson", sector: "Healthcare", price: 155.20, change: 0.8, composite_score: 7.0 },
    { symbol: "V", name: "Visa Inc.", sector: "Finance", price: 285.90, change: 2.3, composite_score: 7.9 },
  ],
  signals: {
    buy: [
      { symbol: "NVDA", signal: "BUY", strength: 9.0, buy_level: 870, stop_level: 820 },
      { symbol: "AMZN", signal: "BUY", strength: 8.5, buy_level: 190, stop_level: 175 },
      { symbol: "META", signal: "BUY", strength: 8.2, buy_level: 630, stop_level: 600 },
    ],
    sell: [
      { symbol: "TSLA", signal: "SELL", strength: 7.5, sell_level: 260, stop_level: 280 },
      { symbol: "JPM", signal: "SELL", strength: 6.8, sell_level: 195, stop_level: 210 },
    ]
  }
};

module.exports = {
  query: async (sql, params) => {
    // Simple mock responses for common queries
    if (sql.includes("SELECT 1")) {
      return { rows: [{ "?column?": 1 }] };
    }
    if (sql.includes("stock_scores")) {
      return { rows: mockData.stocks };
    }
    if (sql.includes("sectors")) {
      return { rows: [
        { sector: "Technology", count: 6 },
        { sector: "Finance", count: 3 },
        { sector: "Healthcare", count: 1 },
        { sector: "Automotive", count: 1 },
        { sector: "Consumer", count: 1 },
      ]};
    }
    return { rows: [] };
  },
  getConnection: async () => {
    return {
      query: async (sql, params) => module.exports.query(sql, params),
      release: () => {}
    };
  },
  end: () => {}
};
