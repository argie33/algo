#!/bin/bash

echo "Fixing hardcoded N/A values in portfolio.js..."

# portfolio.js fixes
sed -i "s/momentum12m: quality\.momentum_12m ?? 'N\/A',/momentum12m: quality.momentum_12m,/g" portfolio.js
sed -i "s/suggestedReplacement: replacement ? replacement\.symbol : 'N\/A'/suggestedReplacement: replacement ? replacement.symbol : null/g" portfolio.js
sed -i "s/quality: worstQuality\?\.quality_score ?? 'N\/A',/quality: worstQuality?.quality_score,/g" portfolio.js
sed -i "s/momentum12m: worstQuality\?\.momentum_12m ?? 'N\/A'/momentum12m: worstQuality?.momentum_12m/g" portfolio.js
sed -i "s/suggestedTarget: consolidationTarget ? consolidationTarget\.symbol : 'N\/A'/suggestedTarget: consolidationTarget ? consolidationTarget.symbol : null/g" portfolio.js
sed -i "s/replacementQuality: betterReplacement ? betterReplacement\.quality : 'N\/A'/replacementQuality: betterReplacement ? betterReplacement.quality : null/g" portfolio.js
sed -i "s/technicalScore: score\?\.technicals_score || 'N\/A',/technicalScore: score?.technicals_score,/g" portfolio.js
sed -i "s/momentum12m: quality\?\.momentum_12m ? quality\.momentum_12m\.toFixed(2) : 'N\/A',/momentum12m: quality?.momentum_12m ? quality.momentum_12m.toFixed(2) : null,/g" portfolio.js
sed -i "s/fundamentalScore: score\?\.fundamentals_score || 'N\/A',/fundamentalScore: score?.fundamentals_score,/g" portfolio.js
sed -i "s/technicalScore: score\?\.technicals_score || 'N\/A'/technicalScore: score?.technicals_score/g" portfolio.js
sed -i "s/portfolioData\.broker || \"unknown\",/portfolioData.broker,/g" portfolio.js
sed -i "s/portfolioData\.summary\?\.accountStatus || \"unknown\",/portfolioData.summary?.accountStatus,/g" portfolio.js
sed -i "s/portfolioData\.summary\?\.environment || \"unknown\",/portfolioData.summary?.environment,/g" portfolio.js
sed -i "s/portfolioData\.broker || \"unknown\"/portfolioData.broker/g" portfolio.js

echo "Fixing hardcoded N/A values in risk.js..."
# risk.js fixes
sed -i "s/: \"N\/A\";$/: null;/g" risk.js
sed -i "s/risk_score: \"N\/A\",/risk_score: null,/g" risk.js
sed -i "s/volatility: \"N\/A\",/volatility: null,/g" risk.js

echo "Fixing hardcoded N/A values in analysts.js..."
# analysts.js fixes - be specific for this one
sed -i "s/averageRating: latest\.recommendation_mean !== null && !isNaN(latest\.recommendation_mean) ? parseFloat(latest\.recommendation_mean)\.toFixed(2) : \"N\/A\",/averageRating: latest.recommendation_mean !== null \&\& !isNaN(latest.recommendation_mean) ? parseFloat(latest.recommendation_mean).toFixed(2) : null,/g" analysts.js
sed -i "s/ratingChangeVelocity: ratingChangeVelocity !== null ? ratingChangeVelocity\.toFixed(3) : \"N\/A\",/ratingChangeVelocity: ratingChangeVelocity !== null ? ratingChangeVelocity.toFixed(3) : null,/g" analysts.js

echo "Fixing hardcoded N/A values in market.js..."
# market.js fixes - multiple instances
sed -i "s/advance_decline_ratio: breadth\.declining > 0 ? (breadth\.advancing \/ breadth\.declining)\.toFixed(2) : \"N\/A\",/advance_decline_ratio: breadth.declining > 0 ? (breadth.advancing \/ breadth.declining).toFixed(2) : null,/g" market.js
sed -i "s/percent: maAnalysis\.total_with_sma20 ? parseFloat(advancingPercAboveMA20)\.toFixed(2) : \"N\/A\",/percent: maAnalysis.total_with_sma20 ? parseFloat(advancingPercAboveMA20).toFixed(2) : null,/g" market.js
sed -i "s/percent: maAnalysis\.total_with_sma50 ? parseFloat((maAnalysis\.above_sma50 \/ maAnalysis\.total_with_sma50 \* 100))\.toFixed(2) : \"N\/A\",/percent: maAnalysis.total_with_sma50 ? parseFloat((maAnalysis.above_sma50 \/ maAnalysis.total_with_sma50 * 100)).toFixed(2) : null,/g" market.js
sed -i "s/percent: maAnalysis\.total_with_sma200 ? parseFloat(advancingPercAboveMA200)\.toFixed(2) : \"N\/A\",/percent: maAnalysis.total_with_sma200 ? parseFloat(advancingPercAboveMA200).toFixed(2) : null,/g" market.js

echo "Fixing hardcoded N/A values in signals.js..."
# signals.js fixes
sed -i "s/avg_volume: signalData\.length > 0 && queryConfig\.availableColumns\.includes('volume') ? (signalData\.reduce((sum, d) => sum + safeFloat(d\.volume), 0) \/ signalData\.length)\.toFixed(0) : \"N\/A\",/avg_volume: signalData.length > 0 \&\& queryConfig.availableColumns.includes('volume') ? (signalData.reduce((sum, d) => sum + safeFloat(d.volume), 0) \/ signalData.length).toFixed(0) : null,/g" signals.js

echo "Fixing hardcoded 'unknown' values in alerts.js..."
# alerts.js fixes
sed -i "s/volume_trend: analysisResult\.rows\[0\]\?\.volume_trend || \"unknown\"/volume_trend: analysisResult.rows[0]?.volume_trend/g" alerts.js

echo "✅ All hardcoded N/A values have been fixed!"
