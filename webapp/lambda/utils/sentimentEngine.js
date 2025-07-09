const axios = require('axios');

class SentimentEngine {
  constructor() {
    this.positiveWords = [
      'good', 'great', 'excellent', 'amazing', 'outstanding', 'fantastic', 'wonderful',
      'positive', 'bullish', 'optimistic', 'strong', 'robust', 'solid', 'healthy',
      'growth', 'increase', 'rise', 'surge', 'boost', 'gain', 'profit', 'success',
      'beat', 'exceed', 'outperform', 'upgrade', 'buy', 'recommend', 'target',
      'recovery', 'momentum', 'breakthrough', 'innovation', 'expansion', 'improvement'
    ];
    
    this.negativeWords = [
      'bad', 'terrible', 'awful', 'horrible', 'worst', 'disappointing', 'concerning',
      'negative', 'bearish', 'pessimistic', 'weak', 'poor', 'decline', 'fall',
      'drop', 'plunge', 'crash', 'collapse', 'loss', 'deficit', 'miss', 'fail',
      'underperform', 'downgrade', 'sell', 'avoid', 'warning', 'risk', 'concern',
      'trouble', 'problem', 'issue', 'challenge', 'difficulty', 'struggle'
    ];
    
    this.neutralWords = [
      'stable', 'steady', 'unchanged', 'flat', 'neutral', 'mixed', 'sideways',
      'hold', 'maintain', 'continue', 'expect', 'forecast', 'estimate', 'project'
    ];
    
    this.intensifiers = {
      'very': 1.5,
      'extremely': 2.0,
      'highly': 1.8,
      'significantly': 1.7,
      'substantially': 1.6,
      'considerably': 1.5,
      'moderately': 1.2,
      'slightly': 0.8,
      'somewhat': 0.9,
      'quite': 1.3,
      'rather': 1.1,
      'fairly': 1.1
    };
    
    this.negators = ['not', 'no', 'never', 'none', 'nothing', 'neither', 'nor', 'without'];
  }

  async analyzeSentiment(text, symbol = null) {
    try {
      // Try multiple sentiment analysis approaches
      const results = await Promise.allSettled([
        this.analyzeWithLexicon(text),
        this.analyzeWithVaderSentiment(text),
        this.analyzeWithTextBlob(text)
      ]);
      
      // Combine results
      const validResults = results
        .filter(result => result.status === 'fulfilled' && result.value)
        .map(result => result.value);
      
      if (validResults.length === 0) {
        // Fallback to lexicon-based analysis
        return this.analyzeWithLexicon(text);
      }
      
      // Average the scores
      const avgScore = validResults.reduce((sum, result) => sum + result.score, 0) / validResults.length;
      const avgConfidence = validResults.reduce((sum, result) => sum + result.confidence, 0) / validResults.length;
      
      return {
        score: avgScore,
        label: this.scoreToLabel(avgScore),
        confidence: avgConfidence,
        method: 'combined',
        symbol: symbol,
        text_length: text.length,
        analyzed_at: new Date().toISOString()
      };
    } catch (error) {
      console.error('Error in sentiment analysis:', error);
      return this.analyzeWithLexicon(text);
    }
  }

  analyzeWithLexicon(text) {
    const words = text.toLowerCase().replace(/[^\w\s]/g, '').split(/\s+/);
    let score = 0;
    let totalWords = 0;
    let sentimentWords = 0;
    
    for (let i = 0; i < words.length; i++) {
      const word = words[i];
      let wordScore = 0;
      let isNegated = false;
      
      // Check for negation in the previous 3 words
      for (let j = Math.max(0, i - 3); j < i; j++) {
        if (this.negators.includes(words[j])) {
          isNegated = true;
          break;
        }
      }
      
      // Get base sentiment score
      if (this.positiveWords.includes(word)) {
        wordScore = 1;
      } else if (this.negativeWords.includes(word)) {
        wordScore = -1;
      } else if (this.neutralWords.includes(word)) {
        wordScore = 0;
      }
      
      if (wordScore !== 0) {
        sentimentWords++;
        
        // Apply intensifiers
        if (i > 0 && this.intensifiers[words[i - 1]]) {
          wordScore *= this.intensifiers[words[i - 1]];
        }
        
        // Apply negation
        if (isNegated) {
          wordScore *= -1;
        }
        
        score += wordScore;
      }
      
      totalWords++;
    }
    
    // Normalize score
    const normalizedScore = sentimentWords > 0 ? score / sentimentWords : 0;
    
    // Scale to -1 to 1 range
    const finalScore = Math.max(-1, Math.min(1, normalizedScore));
    
    // Calculate confidence based on sentiment word density
    const density = sentimentWords / totalWords;
    const confidence = Math.min(0.5 + density * 0.5, 1.0);
    
    return {
      score: finalScore,
      label: this.scoreToLabel(finalScore),
      confidence: confidence,
      method: 'lexicon',
      sentiment_words: sentimentWords,
      total_words: totalWords,
      analyzed_at: new Date().toISOString()
    };
  }

  async analyzeWithVaderSentiment(text) {
    try {
      // Mock VADER sentiment analysis (would require Python integration)
      // For now, return a simplified version
      return this.analyzeWithLexicon(text);
    } catch (error) {
      console.error('VADER sentiment analysis failed:', error);
      return null;
    }
  }

  async analyzeWithTextBlob(text) {
    try {
      // Mock TextBlob sentiment analysis (would require Python integration)
      // For now, return a simplified version
      return this.analyzeWithLexicon(text);
    } catch (error) {
      console.error('TextBlob sentiment analysis failed:', error);
      return null;
    }
  }

  async analyzeWithHuggingFace(text) {
    try {
      if (!process.env.HUGGINGFACE_API_KEY) {
        return null;
      }
      
      const response = await axios.post(
        'https://api-inference.huggingface.co/models/cardiffnlp/twitter-roberta-base-sentiment-latest',
        { inputs: text },
        {
          headers: {
            'Authorization': `Bearer ${process.env.HUGGINGFACE_API_KEY}`,
            'Content-Type': 'application/json'
          },
          timeout: 10000
        }
      );
      
      if (response.data && response.data[0]) {
        const results = response.data[0];
        
        // Find the highest confidence label
        let maxScore = -1;
        let maxLabel = 'neutral';
        
        results.forEach(result => {
          if (result.score > maxScore) {
            maxScore = result.score;
            maxLabel = result.label;
          }
        });
        
        // Convert to our scoring system
        let score = 0;
        if (maxLabel === 'LABEL_2' || maxLabel === 'positive') {
          score = maxScore;
        } else if (maxLabel === 'LABEL_0' || maxLabel === 'negative') {
          score = -maxScore;
        } else {
          score = 0;
        }
        
        return {
          score: score,
          label: this.scoreToLabel(score),
          confidence: maxScore,
          method: 'huggingface',
          analyzed_at: new Date().toISOString()
        };
      }
      
      return null;
    } catch (error) {
      console.error('Hugging Face sentiment analysis failed:', error);
      return null;
    }
  }

  scoreToLabel(score) {
    if (score > 0.1) {
      return 'positive';
    } else if (score < -0.1) {
      return 'negative';
    } else {
      return 'neutral';
    }
  }

  labelToScore(label) {
    switch (label.toLowerCase()) {
      case 'positive':
        return 0.5;
      case 'negative':
        return -0.5;
      case 'neutral':
      default:
        return 0;
    }
  }

  async analyzeBatchSentiment(textArray, symbols = []) {
    const results = [];
    
    for (let i = 0; i < textArray.length; i++) {
      const text = textArray[i];
      const symbol = symbols[i] || null;
      
      try {
        const sentiment = await this.analyzeSentiment(text, symbol);
        results.push(sentiment);
      } catch (error) {
        console.error(`Error analyzing sentiment for text ${i}:`, error);
        results.push({
          score: 0,
          label: 'neutral',
          confidence: 0.5,
          method: 'error',
          symbol: symbol,
          analyzed_at: new Date().toISOString()
        });
      }
    }
    
    return results;
  }

  calculateSentimentTrend(sentiments) {
    if (sentiments.length < 2) {
      return {
        trend: 'insufficient_data',
        strength: 0,
        direction: 'neutral'
      };
    }
    
    // Calculate moving averages
    const shortPeriod = Math.min(5, sentiments.length);
    const longPeriod = Math.min(10, sentiments.length);
    
    const shortMA = sentiments.slice(-shortPeriod).reduce((sum, s) => sum + s.score, 0) / shortPeriod;
    const longMA = sentiments.slice(-longPeriod).reduce((sum, s) => sum + s.score, 0) / longPeriod;
    
    const diff = shortMA - longMA;
    
    let trend = 'neutral';
    let strength = Math.abs(diff);
    
    if (diff > 0.1) {
      trend = 'improving';
    } else if (diff < -0.1) {
      trend = 'deteriorating';
    }
    
    return {
      trend: trend,
      strength: strength,
      direction: diff > 0 ? 'positive' : diff < 0 ? 'negative' : 'neutral',
      short_ma: shortMA,
      long_ma: longMA,
      difference: diff
    };
  }

  aggregateSentimentScores(sentiments) {
    if (sentiments.length === 0) {
      return {
        overall_score: 0,
        overall_label: 'neutral',
        confidence: 0,
        positive_count: 0,
        negative_count: 0,
        neutral_count: 0,
        total_count: 0
      };
    }
    
    const scores = sentiments.map(s => s.score);
    const confidences = sentiments.map(s => s.confidence);
    
    // Weighted average by confidence
    const totalWeight = confidences.reduce((sum, c) => sum + c, 0);
    const weightedScore = scores.reduce((sum, score, i) => sum + score * confidences[i], 0) / totalWeight;
    
    // Count by label
    const labelCounts = sentiments.reduce((counts, s) => {
      counts[s.label] = (counts[s.label] || 0) + 1;
      return counts;
    }, {});
    
    return {
      overall_score: weightedScore,
      overall_label: this.scoreToLabel(weightedScore),
      confidence: totalWeight / sentiments.length,
      positive_count: labelCounts.positive || 0,
      negative_count: labelCounts.negative || 0,
      neutral_count: labelCounts.neutral || 0,
      total_count: sentiments.length,
      score_distribution: {
        min: Math.min(...scores),
        max: Math.max(...scores),
        avg: scores.reduce((sum, s) => sum + s, 0) / scores.length,
        std: this.calculateStandardDeviation(scores)
      }
    };
  }

  calculateStandardDeviation(values) {
    const mean = values.reduce((sum, val) => sum + val, 0) / values.length;
    const squaredDiffs = values.map(val => Math.pow(val - mean, 2));
    const avgSquaredDiff = squaredDiffs.reduce((sum, val) => sum + val, 0) / squaredDiffs.length;
    return Math.sqrt(avgSquaredDiff);
  }

  getEmotionFromSentiment(score, confidence) {
    if (confidence < 0.3) {
      return 'uncertain';
    }
    
    if (score > 0.7) {
      return 'very_positive';
    } else if (score > 0.3) {
      return 'positive';
    } else if (score > 0.1) {
      return 'slightly_positive';
    } else if (score < -0.7) {
      return 'very_negative';
    } else if (score < -0.3) {
      return 'negative';
    } else if (score < -0.1) {
      return 'slightly_negative';
    } else {
      return 'neutral';
    }
  }

  detectSentimentAnomalies(sentiments, threshold = 2.0) {
    if (sentiments.length < 10) {
      return [];
    }
    
    const scores = sentiments.map(s => s.score);
    const mean = scores.reduce((sum, s) => sum + s, 0) / scores.length;
    const std = this.calculateStandardDeviation(scores);
    
    const anomalies = [];
    
    sentiments.forEach((sentiment, index) => {
      const zScore = Math.abs((sentiment.score - mean) / std);
      
      if (zScore > threshold) {
        anomalies.push({
          index: index,
          sentiment: sentiment,
          z_score: zScore,
          deviation: sentiment.score - mean,
          type: sentiment.score > mean ? 'positive_spike' : 'negative_spike'
        });
      }
    });
    
    return anomalies;
  }
}

module.exports = SentimentEngine;