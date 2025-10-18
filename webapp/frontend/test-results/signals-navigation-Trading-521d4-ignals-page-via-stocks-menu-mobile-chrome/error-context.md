# Page snapshot

```yaml
- generic [ref=e3]:
  - banner [ref=e4]:
    - generic [ref=e5]:
      - button "open drawer" [ref=e6] [cursor=pointer]:
        - img [ref=e7] [cursor=pointer]
      - generic: Dashboard
      - button "Sign In" [ref=e9] [cursor=pointer]:
        - img [ref=e11] [cursor=pointer]
        - text: Sign In
  - navigation
  - main [ref=e13]:
    - generic [ref=e16]:
      - heading "Market Overview" [level=4] [ref=e17]
      - alert [ref=e18]:
        - img [ref=e20]
        - generic [ref=e22]:
          - text: Failed to load market data. Please check your data sources and try again.
          - generic [ref=e23]: "Technical details: Failed to fetch market overview: Network Error"
          - generic [ref=e24]:
            - text: "Debug endpoint:"
            - code [ref=e25]: http://localhost:5001/market/debug
```