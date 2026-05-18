# Lambda API Routes

15 routed endpoints. All routes must:

1. Use consistent error response format (error_response, success_response)
2. Include database error handling (UndefinedTable, UndefinedColumn, etc.)
3. Return JSON with status codes (200, 400, 404, 500, 503)

## Routes Structure

```
routes/
├── algo.py          — /api/algo/*
├── admin.py         — /api/admin/*
├── economic.py      — /api/economic/*
├── earnings.py      — /api/earnings/*
├── financials.py    — /api/financials/*
├── industries.py    — /api/industries/*
├── market.py        — /api/market/*
├── portfolio.py     — /api/portfolio/*
├── prices.py        — /api/prices/*
├── research.py      — /api/research/*
├── sectors.py       — /api/sectors/*
├── sentiment.py     — /api/sentiment/*
├── signals.py       — /api/signals/*
├── stocks.py        — /api/stocks/*
└── utils.py         — Shared response utilities
```

## Error Handling

Always catch: UndefinedTable, UndefinedColumn, OperationalError, DatabaseError, Exception.  
Return 503 for schema mismatches, 500 for unknown errors.
