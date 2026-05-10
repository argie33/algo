#!/bin/bash

# Fix MarketInternals.jsx - remove unused imports
sed -i "s/import { useEffect, useMemo,/import {/g" src/components/MarketInternals.jsx
sed -i "s/, useEffect//" src/components/MarketInternals.jsx
sed -i "s/, useMemo//" src/components/MarketInternals.jsx

# Fix MarketIndices.jsx - remove unused Paper, Chip
sed -i "s/Paper, Chip,//" src/components/MarketIndices.jsx

# Fix MarketVolatility.jsx - remove unused useState
sed -i "s/import { useState/import {/" src/components/MarketVolatility.jsx
sed -i "s/, useState//" src/components/MarketVolatility.jsx

echo "✓ Imports cleaned"
