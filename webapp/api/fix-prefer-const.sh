#!/bin/bash

# Fix prefer-const violations in batch

echo "Fixing prefer-const violations..."

# routes/metrics.js line 618
sed -i '618s/let interpretation/const interpretation/' routes/metrics.js

# routes/orders.js lines 20 and 658
sed -i '20s/let params/const params/' routes/orders.js
sed -i '658s/let params/const params/' routes/orders.js

# routes/scores.js line 597
sed -i '597s/let interpretation/const interpretation/' routes/scores.js

# routes/scoring.js line 1052
sed -i '1052s/let maxScore/const maxScore/' routes/scoring.js

# routes/stocks-enhanced.js lines 371 and 372
sed -i '371s/let whereConditions/const whereConditions/' routes/stocks-enhanced.js
sed -i '372s/let queryParams/const queryParams/' routes/stocks-enhanced.js

# routes/stocks.js lines 879 and 880
sed -i '879s/let whereConditions/const whereConditions/' routes/stocks.js
sed -i '880s/let queryParams/const queryParams/' routes/stocks.js

# routes/trades.js lines 234 and 989
sed -i '234s/let params/const params/' routes/trades.js
sed -i '989s/let params/const params/' routes/trades.js

echo "Fixed prefer-const violations"