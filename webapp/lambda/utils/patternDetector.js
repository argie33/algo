const { query } = require('./database');

class PatternDetector {
  constructor() {
    this.isMonitoring = false;
    this.monitoringInterval = null;
    this.patternAlgorithms = this.initializePatternAlgorithms();
  }

  initializePatternAlgorithms() {
    return {
      head_and_shoulders: this.detectHeadAndShoulders.bind(this),
      inverse_head_and_shoulders: this.detectInverseHeadAndShoulders.bind(this),
      double_top: this.detectDoubleTop.bind(this),
      double_bottom: this.detectDoubleBottom.bind(this),
      triangle_ascending: this.detectAscendingTriangle.bind(this),
      triangle_descending: this.detectDescendingTriangle.bind(this),
      triangle_symmetrical: this.detectSymmetricalTriangle.bind(this),
      flag_bull: this.detectBullFlag.bind(this),
      flag_bear: this.detectBearFlag.bind(this),
      cup_and_handle: this.detectCupAndHandle.bind(this),
      wedge_rising: this.detectRisingWedge.bind(this),
      wedge_falling: this.detectFallingWedge.bind(this)
    };
  }

  async startRealTimeMonitoring(intervalMinutes = 15) {
    // Skip pattern detection in test environments
    if (process.env.NODE_ENV === 'test' || process.env.DISABLE_PATTERN_DETECTION === 'true') {
      console.log('Pattern detection disabled in test environment');
      return;
    }

    if (this.isMonitoring) {
      console.log('Pattern monitoring already running');
      return;
    }

    this.isMonitoring = true;
    console.log(`Starting real-time pattern monitoring with ${intervalMinutes} minute intervals`);

    // Initial scan
    await this.scanAllSymbols();

    // Set up interval
    this.monitoringInterval = setInterval(async () => {
      try {
        await this.scanAllSymbols();
      } catch (error) {
        console.error('Error in pattern monitoring:', error);
      }
    }, intervalMinutes * 60 * 1000);
  }

  stopRealTimeMonitoring() {
    if (this.monitoringInterval) {
      clearInterval(this.monitoringInterval);
      this.monitoringInterval = null;
    }
    this.isMonitoring = false;
    console.log('Pattern monitoring stopped');
  }

  async scanAllSymbols() {
    try {
      // Get list of active symbols
      const symbolsResult = await query(`
        SELECT DISTINCT symbol 
        FROM stock_data 
        WHERE date >= CURRENT_DATE - INTERVAL '30 days'
        LIMIT 500
      `);

      const symbols = symbolsResult.rows.map(row => row.symbol);
      console.log(`Scanning ${symbols.length} symbols for patterns`);

      // Scan each symbol
      for (const symbol of symbols) {
        try {
          await this.detectPatterns(symbol, '1d');
        } catch (error) {
          console.warn(`Error scanning ${symbol}:`, error.message);
        }
      }
    } catch (error) {
      console.error('Error in scanAllSymbols:', error);
    }
  }

  async detectPatterns(symbol, timeframe = '1d', specificPatterns = null) {
    try {
      // Get price data
      const priceData = await this.getPriceData(symbol, timeframe);
      if (!priceData || priceData.length < 50) {
        return [];
      }

      // Get technical indicators
      const technicalData = await this.getTechnicalData(symbol, timeframe);

      const detections = [];
      const patternsToCheck = specificPatterns || Object.keys(this.patternAlgorithms);

      for (const patternType of patternsToCheck) {
        if (this.patternAlgorithms[patternType]) {
          try {
            const detection = await this.patternAlgorithms[patternType](priceData, technicalData);
            if (detection) {
              detections.push({
                symbol,
                pattern_type: patternType,
                timeframe,
                confidence: detection.confidence,
                data: detection.data,
                start_date: detection.start_date,
                end_date: detection.end_date,
                detected_at: new Date().toISOString()
              });
            }
          } catch (error) {
            console.warn(`Error detecting ${patternType} for ${symbol}:`, error.message);
          }
        }
      }

      return detections;
    } catch (error) {
      console.error(`Error detecting patterns for ${symbol}:`, error);
      return [];
    }
  }

  async getPriceData(symbol, timeframe) {
    try {
      const tableName = `stock_data${timeframe === '1w' ? '_weekly' : timeframe === '1M' ? '_monthly' : ''}`;
      const result = await query(`
        SELECT date, open, high, low, close, volume
        FROM ${tableName}
        WHERE symbol = $1
        ORDER BY date DESC
        LIMIT 100
      `, [symbol]);

      return result.rows.reverse(); // Chronological order
    } catch (error) {
      console.error(`Error fetching price data for ${symbol}:`, error);
      return [];
    }
  }

  async getTechnicalData(symbol, timeframe) {
    try {
      const tableName = `technical_data${timeframe === '1w' ? '_weekly' : timeframe === '1M' ? '_monthly' : '_daily'}`;
      const result = await query(`
        SELECT *
        FROM ${tableName}
        WHERE symbol = $1
        ORDER BY date DESC
        LIMIT 100
      `, [symbol]);

      return result.rows.reverse(); // Chronological order
    } catch (error) {
      console.error(`Error fetching technical data for ${symbol}:`, error);
      return [];
    }
  }

  // Pattern detection algorithms
  detectHeadAndShoulders(priceData, technicalData) {
    if (priceData.length < 30) return null;

    const prices = priceData.map(p => p.high);
    const lows = priceData.map(p => p.low);
    const n = prices.length;

    // Look for three peaks pattern
    const peaks = this.findPeaks(prices);
    if (peaks.length < 3) return null;

    // Get the last 3 significant peaks
    const lastPeaks = peaks.slice(-3);
    const [leftShoulder, head, rightShoulder] = lastPeaks;

    // Validate head and shoulders pattern
    const leftShoulderPrice = prices[leftShoulder];
    const headPrice = prices[head];
    const rightShoulderPrice = prices[rightShoulder];

    // Head should be higher than shoulders
    if (headPrice <= leftShoulderPrice || headPrice <= rightShoulderPrice) return null;

    // Shoulders should be roughly equal (within 5%)
    const shoulderDiff = Math.abs(leftShoulderPrice - rightShoulderPrice) / leftShoulderPrice;
    if (shoulderDiff > 0.05) return null;

    // Calculate neckline
    const leftTrough = this.findTroughBetween(lows, leftShoulder, head);
    const rightTrough = this.findTroughBetween(lows, head, rightShoulder);
    const necklinePrice = (lows[leftTrough] + lows[rightTrough]) / 2;

    // Current price should be near or below neckline for confirmation
    const currentPrice = prices[n - 1];
    const necklineBreak = currentPrice < necklinePrice;

    const confidence = this.calculateHeadAndShouldersConfidence(
      leftShoulderPrice, headPrice, rightShoulderPrice, necklinePrice, currentPrice, necklineBreak
    );

    if (confidence < 0.5) return null;

    return {
      confidence,
      data: {
        left_shoulder: { index: leftShoulder, price: leftShoulderPrice },
        head: { index: head, price: headPrice },
        right_shoulder: { index: rightShoulder, price: rightShoulderPrice },
        neckline: necklinePrice,
        current_price: currentPrice,
        neckline_break: necklineBreak,
        target_price: necklinePrice - (headPrice - necklinePrice) // Price target
      },
      start_date: priceData[leftShoulder].date,
      end_date: priceData[n - 1].date
    };
  }

  detectInverseHeadAndShoulders(priceData, technicalData) {
    if (priceData.length < 30) return null;

    const prices = priceData.map(p => p.low);
    const highs = priceData.map(p => p.high);
    const n = prices.length;

    // Look for three troughs pattern
    const troughs = this.findTroughs(prices);
    if (troughs.length < 3) return null;

    // Get the last 3 significant troughs
    const lastTroughs = troughs.slice(-3);
    const [leftShoulder, head, rightShoulder] = lastTroughs;

    // Validate inverse head and shoulders pattern
    const leftShoulderPrice = prices[leftShoulder];
    const headPrice = prices[head];
    const rightShoulderPrice = prices[rightShoulder];

    // Head should be lower than shoulders
    if (headPrice >= leftShoulderPrice || headPrice >= rightShoulderPrice) return null;

    // Shoulders should be roughly equal (within 5%)
    const shoulderDiff = Math.abs(leftShoulderPrice - rightShoulderPrice) / leftShoulderPrice;
    if (shoulderDiff > 0.05) return null;

    // Calculate neckline
    const leftPeak = this.findPeakBetween(highs, leftShoulder, head);
    const rightPeak = this.findPeakBetween(highs, head, rightShoulder);
    const necklinePrice = (highs[leftPeak] + highs[rightPeak]) / 2;

    // Current price should be near or above neckline for confirmation
    const currentPrice = prices[n - 1];
    const necklineBreak = currentPrice > necklinePrice;

    const confidence = this.calculateInverseHeadAndShouldersConfidence(
      leftShoulderPrice, headPrice, rightShoulderPrice, necklinePrice, currentPrice, necklineBreak
    );

    if (confidence < 0.5) return null;

    return {
      confidence,
      data: {
        left_shoulder: { index: leftShoulder, price: leftShoulderPrice },
        head: { index: head, price: headPrice },
        right_shoulder: { index: rightShoulder, price: rightShoulderPrice },
        neckline: necklinePrice,
        current_price: currentPrice,
        neckline_break: necklineBreak,
        target_price: necklinePrice + (necklinePrice - headPrice) // Price target
      },
      start_date: priceData[leftShoulder].date,
      end_date: priceData[n - 1].date
    };
  }

  detectDoubleTop(priceData, technicalData) {
    if (priceData.length < 20) return null;

    const prices = priceData.map(p => p.high);
    const lows = priceData.map(p => p.low);
    const n = prices.length;

    const peaks = this.findPeaks(prices);
    if (peaks.length < 2) return null;

    // Get the last 2 significant peaks
    const lastPeaks = peaks.slice(-2);
    const [firstPeak, secondPeak] = lastPeaks;

    const firstPeakPrice = prices[firstPeak];
    const secondPeakPrice = prices[secondPeak];

    // Peaks should be roughly equal (within 3%)
    const peakDiff = Math.abs(firstPeakPrice - secondPeakPrice) / firstPeakPrice;
    if (peakDiff > 0.03) return null;

    // Find the trough between peaks
    const troughIndex = this.findTroughBetween(lows, firstPeak, secondPeak);
    const troughPrice = lows[troughIndex];

    // Validate significant decline between peaks
    const declinePercent = (firstPeakPrice - troughPrice) / firstPeakPrice;
    if (declinePercent < 0.1) return null; // At least 10% decline

    const currentPrice = prices[n - 1];
    const supportBreak = currentPrice < troughPrice;

    const confidence = this.calculateDoubleTopConfidence(
      firstPeakPrice, secondPeakPrice, troughPrice, currentPrice, supportBreak
    );

    if (confidence < 0.5) return null;

    return {
      confidence,
      data: {
        first_peak: { index: firstPeak, price: firstPeakPrice },
        second_peak: { index: secondPeak, price: secondPeakPrice },
        trough: { index: troughIndex, price: troughPrice },
        current_price: currentPrice,
        support_break: supportBreak,
        target_price: troughPrice - (firstPeakPrice - troughPrice)
      },
      start_date: priceData[firstPeak].date,
      end_date: priceData[n - 1].date
    };
  }

  detectDoubleBottom(priceData, technicalData) {
    if (priceData.length < 20) return null;

    const prices = priceData.map(p => p.low);
    const highs = priceData.map(p => p.high);
    const n = prices.length;

    const troughs = this.findTroughs(prices);
    if (troughs.length < 2) return null;

    // Get the last 2 significant troughs
    const lastTroughs = troughs.slice(-2);
    const [firstTrough, secondTrough] = lastTroughs;

    const firstTroughPrice = prices[firstTrough];
    const secondTroughPrice = prices[secondTrough];

    // Troughs should be roughly equal (within 3%)
    const troughDiff = Math.abs(firstTroughPrice - secondTroughPrice) / firstTroughPrice;
    if (troughDiff > 0.03) return null;

    // Find the peak between troughs
    const peakIndex = this.findPeakBetween(highs, firstTrough, secondTrough);
    const peakPrice = highs[peakIndex];

    // Validate significant rally between troughs
    const rallyPercent = (peakPrice - firstTroughPrice) / firstTroughPrice;
    if (rallyPercent < 0.1) return null; // At least 10% rally

    const currentPrice = prices[n - 1];
    const resistanceBreak = currentPrice > peakPrice;

    const confidence = this.calculateDoubleBottomConfidence(
      firstTroughPrice, secondTroughPrice, peakPrice, currentPrice, resistanceBreak
    );

    if (confidence < 0.5) return null;

    return {
      confidence,
      data: {
        first_trough: { index: firstTrough, price: firstTroughPrice },
        second_trough: { index: secondTrough, price: secondTroughPrice },
        peak: { index: peakIndex, price: peakPrice },
        current_price: currentPrice,
        resistance_break: resistanceBreak,
        target_price: peakPrice + (peakPrice - firstTroughPrice)
      },
      start_date: priceData[firstTrough].date,
      end_date: priceData[n - 1].date
    };
  }

  detectAscendingTriangle(priceData, technicalData) {
    if (priceData.length < 20) return null;

    const prices = priceData.map(p => p.close);
    const highs = priceData.map(p => p.high);
    const lows = priceData.map(p => p.low);
    const n = prices.length;

    // Look for horizontal resistance and ascending support
    const recentData = priceData.slice(-20);
    const recentHighs = recentData.map(p => p.high);
    const recentLows = recentData.map(p => p.low);

    // Find resistance level (should be relatively flat)
    const resistanceLevel = Math.max(...recentHighs);
    const resistanceTouches = recentHighs.filter(h => Math.abs(h - resistanceLevel) / resistanceLevel < 0.02).length;

    if (resistanceTouches < 2) return null;

    // Check for ascending support line
    const supportTrend = this.calculateTrendline(recentLows, 'ascending');
    if (!supportTrend || supportTrend.slope <= 0) return null;

    // Calculate convergence
    const convergence = this.calculateTriangleConvergence(supportTrend, resistanceLevel);
    if (!convergence) return null;

    const currentPrice = prices[n - 1];
    const breakoutDirection = currentPrice > resistanceLevel ? 'bullish' : 'bearish';

    const confidence = this.calculateAscendingTriangleConfidence(
      resistanceLevel, supportTrend, currentPrice, breakoutDirection
    );

    if (confidence < 0.5) return null;

    return {
      confidence,
      data: {
        resistance_level: resistanceLevel,
        support_trend: supportTrend,
        current_price: currentPrice,
        breakout_direction: breakoutDirection,
        target_price: breakoutDirection === 'bullish' ? 
          resistanceLevel + (resistanceLevel - supportTrend.start_price) :
          supportTrend.current_price - (resistanceLevel - supportTrend.start_price)
      },
      start_date: priceData[n - 20].date,
      end_date: priceData[n - 1].date
    };
  }

  // Additional pattern detection methods would go here...
  detectDescendingTriangle(priceData, technicalData) {
    // Implementation for descending triangle
    return null;
  }

  detectSymmetricalTriangle(priceData, technicalData) {
    // Implementation for symmetrical triangle
    return null;
  }

  detectBullFlag(priceData, technicalData) {
    // Implementation for bull flag
    return null;
  }

  detectBearFlag(priceData, technicalData) {
    // Implementation for bear flag
    return null;
  }

  detectCupAndHandle(priceData, technicalData) {
    // Implementation for cup and handle
    return null;
  }

  detectRisingWedge(priceData, technicalData) {
    // Implementation for rising wedge
    return null;
  }

  detectFallingWedge(priceData, technicalData) {
    // Implementation for falling wedge
    return null;
  }

  // Helper methods
  findPeaks(prices) {
    const peaks = [];
    const windowSize = 3;
    
    for (let i = windowSize; i < prices.length - windowSize; i++) {
      let isPeak = true;
      
      for (let j = i - windowSize; j <= i + windowSize; j++) {
        if (j !== i && prices[j] >= prices[i]) {
          isPeak = false;
          break;
        }
      }
      
      if (isPeak) {
        peaks.push(i);
      }
    }
    
    return peaks;
  }

  findTroughs(prices) {
    const troughs = [];
    const windowSize = 3;
    
    for (let i = windowSize; i < prices.length - windowSize; i++) {
      let isTrough = true;
      
      for (let j = i - windowSize; j <= i + windowSize; j++) {
        if (j !== i && prices[j] <= prices[i]) {
          isTrough = false;
          break;
        }
      }
      
      if (isTrough) {
        troughs.push(i);
      }
    }
    
    return troughs;
  }

  findTroughBetween(prices, start, end) {
    let minIndex = start;
    let minPrice = prices[start];
    
    for (let i = start + 1; i < end; i++) {
      if (prices[i] < minPrice) {
        minPrice = prices[i];
        minIndex = i;
      }
    }
    
    return minIndex;
  }

  findPeakBetween(prices, start, end) {
    let maxIndex = start;
    let maxPrice = prices[start];
    
    for (let i = start + 1; i < end; i++) {
      if (prices[i] > maxPrice) {
        maxPrice = prices[i];
        maxIndex = i;
      }
    }
    
    return maxIndex;
  }

  calculateTrendline(prices, direction) {
    if (prices.length < 5) return null;
    
    // Simple linear regression
    const n = prices.length;
    const x = Array.from({ length: n }, (_, i) => i);
    const y = prices;
    
    const sumX = x.reduce((a, b) => a + b, 0);
    const sumY = y.reduce((a, b) => a + b, 0);
    const sumXY = x.reduce((sum, xi, i) => sum + xi * y[i], 0);
    const sumXX = x.reduce((sum, xi) => sum + xi * xi, 0);
    
    const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
    const intercept = (sumY - slope * sumX) / n;
    
    if (direction === 'ascending' && slope <= 0) return null;
    if (direction === 'descending' && slope >= 0) return null;
    
    return {
      slope,
      intercept,
      start_price: intercept,
      current_price: intercept + slope * (n - 1)
    };
  }

  calculateTriangleConvergence(supportTrend, resistanceLevel) {
    // Calculate where support line would meet resistance
    const convergencePoint = (resistanceLevel - supportTrend.intercept) / supportTrend.slope;
    return convergencePoint > 0 ? convergencePoint : null;
  }

  // Confidence calculation methods
  calculateHeadAndShouldersConfidence(leftShoulder, head, rightShoulder, neckline, currentPrice, necklineBreak) {
    let confidence = 0.6; // Base confidence
    
    // Symmetry of shoulders
    const shoulderSymmetry = 1 - Math.abs(leftShoulder - rightShoulder) / leftShoulder;
    confidence += shoulderSymmetry * 0.2;
    
    // Head prominence
    const headProminence = Math.min((head - leftShoulder) / leftShoulder, (head - rightShoulder) / rightShoulder);
    confidence += Math.min(headProminence, 0.1);
    
    // Neckline break
    if (necklineBreak) {
      confidence += 0.1;
    }
    
    return Math.min(confidence, 1.0);
  }

  calculateInverseHeadAndShouldersConfidence(leftShoulder, head, rightShoulder, neckline, currentPrice, necklineBreak) {
    let confidence = 0.6; // Base confidence
    
    // Symmetry of shoulders
    const shoulderSymmetry = 1 - Math.abs(leftShoulder - rightShoulder) / leftShoulder;
    confidence += shoulderSymmetry * 0.2;
    
    // Head prominence
    const headProminence = Math.min((leftShoulder - head) / leftShoulder, (rightShoulder - head) / rightShoulder);
    confidence += Math.min(headProminence, 0.1);
    
    // Neckline break
    if (necklineBreak) {
      confidence += 0.1;
    }
    
    return Math.min(confidence, 1.0);
  }

  calculateDoubleTopConfidence(firstPeak, secondPeak, trough, currentPrice, supportBreak) {
    let confidence = 0.6; // Base confidence
    
    // Peak similarity
    const peakSimilarity = 1 - Math.abs(firstPeak - secondPeak) / firstPeak;
    confidence += peakSimilarity * 0.2;
    
    // Decline significance
    const declineSignificance = (firstPeak - trough) / firstPeak;
    confidence += Math.min(declineSignificance, 0.1);
    
    // Support break
    if (supportBreak) {
      confidence += 0.1;
    }
    
    return Math.min(confidence, 1.0);
  }

  calculateDoubleBottomConfidence(firstTrough, secondTrough, peak, currentPrice, resistanceBreak) {
    let confidence = 0.6; // Base confidence
    
    // Trough similarity
    const troughSimilarity = 1 - Math.abs(firstTrough - secondTrough) / firstTrough;
    confidence += troughSimilarity * 0.2;
    
    // Rally significance
    const rallySignificance = (peak - firstTrough) / firstTrough;
    confidence += Math.min(rallySignificance, 0.1);
    
    // Resistance break
    if (resistanceBreak) {
      confidence += 0.1;
    }
    
    return Math.min(confidence, 1.0);
  }

  calculateAscendingTriangleConfidence(resistanceLevel, supportTrend, currentPrice, breakoutDirection) {
    let confidence = 0.6; // Base confidence
    
    // Support trend strength
    const trendStrength = Math.min(supportTrend.slope / resistanceLevel, 0.1);
    confidence += trendStrength;
    
    // Breakout confirmation
    if (breakoutDirection === 'bullish') {
      confidence += 0.1;
    }
    
    return Math.min(confidence, 1.0);
  }
}

module.exports = PatternDetector;