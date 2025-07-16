#!/usr/bin/env python3
"""
Sentiment Analysis NLP Pipeline
Multi-source sentiment analysis with financial domain adaptation
Based on behavioral finance research
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import requests
import json
import re
from dataclasses import dataclass
from abc import ABC, abstractmethod
import yfinance as yf
from textblob import TextBlob
import time

@dataclass
class SentimentResult:
    score: float  # -1 to 1 scale
    confidence: float  # 0 to 1 scale
    magnitude: float  # 0 to 1 scale (strength of sentiment)
    source: str
    timestamp: datetime
    raw_data: Dict

class BaseSentimentAnalyzer(ABC):
    """Base class for sentiment analyzers"""
    
    @abstractmethod
    def get_sentiment(self, symbol: str) -> SentimentResult:
        pass

class NewsSentimentAnalyzer(BaseSentimentAnalyzer):
    """
    Financial News Sentiment Analyzer
    Using NewsAPI and financial NLP techniques
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or "your_newsapi_key_here"
        self.base_url = "https://newsapi.org/v2/everything"
        
        # Financial sentiment keywords
        self.positive_keywords = [
            'bullish', 'strong', 'growth', 'profit', 'revenue', 'beat', 'outperform',
            'upgrade', 'buy', 'positive', 'optimistic', 'surge', 'rally', 'gain'
        ]
        
        self.negative_keywords = [
            'bearish', 'weak', 'decline', 'loss', 'miss', 'underperform',
            'downgrade', 'sell', 'negative', 'pessimistic', 'crash', 'fall', 'drop'
        ]
    
    def get_sentiment(self, symbol: str) -> SentimentResult:
        """Get news sentiment for a stock symbol"""
        try:
            # Get company name for better search
            ticker = yf.Ticker(symbol)
            info = ticker.info
            company_name = info.get('longName', symbol)
            
            # Search for recent news
            news_articles = self._fetch_news(symbol, company_name)
            
            if not news_articles:
                return SentimentResult(
                    score=0.0,
                    confidence=0.0,
                    magnitude=0.0,
                    source='news',
                    timestamp=datetime.now(),
                    raw_data={'articles': [], 'error': 'No articles found'}
                )
            
            # Analyze sentiment of articles
            sentiment_scores = []
            for article in news_articles:
                article_sentiment = self._analyze_article_sentiment(article)
                sentiment_scores.append(article_sentiment)
            
            # Calculate weighted average sentiment
            if sentiment_scores:
                avg_score = np.mean([s['score'] for s in sentiment_scores])
                avg_confidence = np.mean([s['confidence'] for s in sentiment_scores])
                avg_magnitude = np.mean([s['magnitude'] for s in sentiment_scores])
            else:
                avg_score = avg_confidence = avg_magnitude = 0.0
            
            return SentimentResult(
                score=avg_score,
                confidence=avg_confidence,
                magnitude=avg_magnitude,
                source='news',
                timestamp=datetime.now(),
                raw_data={
                    'articles_analyzed': len(news_articles),
                    'sentiment_scores': sentiment_scores
                }
            )
            
        except Exception as e:
            print(f"Error analyzing news sentiment for {symbol}: {e}")
            return SentimentResult(
                score=0.0,
                confidence=0.0,
                magnitude=0.0,
                source='news',
                timestamp=datetime.now(),
                raw_data={'error': str(e)}
            )
    
    def _fetch_news(self, symbol: str, company_name: str, days_back: int = 7) -> List[Dict]:
        """Fetch recent news articles"""
        if self.api_key == "your_newsapi_key_here":
            # Mock data for demonstration
            return [
                {
                    'title': f'{company_name} Reports Strong Quarterly Earnings',
                    'description': f'{company_name} beat expectations with strong revenue growth',
                    'publishedAt': datetime.now().isoformat(),
                    'source': {'name': 'Financial Times'}
                },
                {
                    'title': f'Analysts Upgrade {symbol} Following Positive Results',
                    'description': f'Several analysts raised price targets for {symbol}',
                    'publishedAt': datetime.now().isoformat(),
                    'source': {'name': 'Reuters'}
                }
            ]
        
        try:
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            # API parameters
            params = {
                'q': f'"{symbol}" OR "{company_name}"',
                'from': start_date.strftime('%Y-%m-%d'),
                'to': end_date.strftime('%Y-%m-%d'),
                'language': 'en',
                'sortBy': 'publishedAt',
                'apiKey': self.api_key,
                'pageSize': 20
            }
            
            response = requests.get(self.base_url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('articles', [])
            else:
                print(f"News API error: {response.status_code}")
                return []
                
        except Exception as e:
            print(f"Error fetching news: {e}")
            return []
    
    def _analyze_article_sentiment(self, article: Dict) -> Dict:
        """Analyze sentiment of a single article"""
        # Combine title and description for analysis
        text = f"{article.get('title', '')} {article.get('description', '')}"
        
        # Basic TextBlob sentiment analysis
        blob = TextBlob(text)
        base_sentiment = blob.sentiment
        
        # Financial keyword analysis
        keyword_sentiment = self._analyze_financial_keywords(text.lower())
        
        # Combine sentiment scores with weighting
        combined_score = (base_sentiment.polarity * 0.6 + keyword_sentiment * 0.4)
        confidence = min(1.0, base_sentiment.subjectivity + abs(keyword_sentiment) * 0.5)
        magnitude = abs(combined_score)
        
        # Source credibility weighting
        source_name = article.get('source', {}).get('name', '').lower()
        credibility_weight = self._get_source_credibility(source_name)
        
        return {
            'score': combined_score * credibility_weight,
            'confidence': confidence,
            'magnitude': magnitude,
            'text': text[:200],  # First 200 chars for debugging
            'source_credibility': credibility_weight
        }
    
    def _analyze_financial_keywords(self, text: str) -> float:
        """Analyze financial-specific keywords"""
        positive_count = sum(1 for keyword in self.positive_keywords if keyword in text)
        negative_count = sum(1 for keyword in self.negative_keywords if keyword in text)
        
        total_keywords = positive_count + negative_count
        if total_keywords == 0:
            return 0.0
        
        return (positive_count - negative_count) / total_keywords
    
    def _get_source_credibility(self, source_name: str) -> float:
        """Get credibility weight for news source"""
        high_credibility = ['reuters', 'bloomberg', 'wall street journal', 'financial times']
        medium_credibility = ['cnbc', 'marketwatch', 'yahoo finance', 'forbes']
        
        if any(source in source_name for source in high_credibility):
            return 1.0
        elif any(source in source_name for source in medium_credibility):
            return 0.8
        else:
            return 0.6

class RedditSentimentAnalyzer(BaseSentimentAnalyzer):
    """
    Reddit Sentiment Analyzer
    Analyzes sentiment from investing subreddits
    """
    
    def __init__(self):
        self.subreddits = ['investing', 'stocks', 'SecurityAnalysis', 'ValueInvesting', 'StockMarket']
        self.base_url = "https://www.reddit.com/r"
    
    def get_sentiment(self, symbol: str) -> SentimentResult:
        """Get Reddit sentiment for a stock symbol"""
        try:
            # Mock Reddit data for demonstration
            # In production, would use Reddit API (PRAW)
            mock_posts = self._get_mock_reddit_data(symbol)
            
            if not mock_posts:
                return SentimentResult(
                    score=0.0,
                    confidence=0.0,
                    magnitude=0.0,
                    source='reddit',
                    timestamp=datetime.now(),
                    raw_data={'posts': [], 'error': 'No posts found'}
                )
            
            # Analyze sentiment of posts
            sentiment_scores = []
            for post in mock_posts:
                post_sentiment = self._analyze_post_sentiment(post)
                sentiment_scores.append(post_sentiment)
            
            # Calculate volume-weighted sentiment
            if sentiment_scores:
                # Weight by engagement (upvotes + comments)
                total_engagement = sum(s['engagement'] for s in sentiment_scores)
                if total_engagement > 0:
                    weighted_score = sum(
                        s['score'] * s['engagement'] for s in sentiment_scores
                    ) / total_engagement
                else:
                    weighted_score = np.mean([s['score'] for s in sentiment_scores])
                
                avg_confidence = np.mean([s['confidence'] for s in sentiment_scores])
                avg_magnitude = np.mean([s['magnitude'] for s in sentiment_scores])
            else:
                weighted_score = avg_confidence = avg_magnitude = 0.0
            
            return SentimentResult(
                score=weighted_score,
                confidence=avg_confidence,
                magnitude=avg_magnitude,
                source='reddit',
                timestamp=datetime.now(),
                raw_data={
                    'posts_analyzed': len(mock_posts),
                    'total_engagement': sum(s.get('engagement', 0) for s in sentiment_scores),
                    'sentiment_distribution': self._get_sentiment_distribution(sentiment_scores)
                }
            )
            
        except Exception as e:
            print(f"Error analyzing Reddit sentiment for {symbol}: {e}")
            return SentimentResult(
                score=0.0,
                confidence=0.0,
                magnitude=0.0,
                source='reddit',
                timestamp=datetime.now(),
                raw_data={'error': str(e)}
            )
    
    def _get_mock_reddit_data(self, symbol: str) -> List[Dict]:
        """Mock Reddit data for demonstration"""
        return [
            {
                'title': f'$${symbol} - Bullish on recent earnings',
                'text': f'Just bought more {symbol}. Think it has strong potential',
                'upvotes': 25,
                'comments': 8,
                'subreddit': 'stocks'
            },
            {
                'title': f'{symbol} analysis - bearish outlook',
                'text': f'Concerned about {symbol} valuation. Might be overpriced',
                'upvotes': 12,
                'comments': 15,
                'subreddit': 'investing'
            },
            {
                'title': f'DD on {symbol}',
                'text': f'Deep dive analysis on {symbol}. Mixed signals but leaning positive',
                'upvotes': 45,
                'comments': 32,
                'subreddit': 'SecurityAnalysis'
            }
        ]
    
    def _analyze_post_sentiment(self, post: Dict) -> Dict:
        """Analyze sentiment of a Reddit post"""
        text = f"{post.get('title', '')} {post.get('text', '')}"
        
        # Basic sentiment analysis
        blob = TextBlob(text)
        sentiment = blob.sentiment
        
        # Reddit-specific adjustments
        engagement = post.get('upvotes', 0) + post.get('comments', 0)
        
        # Subreddit credibility weighting
        subreddit = post.get('subreddit', '').lower()
        credibility = self._get_subreddit_credibility(subreddit)
        
        return {
            'score': sentiment.polarity * credibility,
            'confidence': sentiment.subjectivity,
            'magnitude': abs(sentiment.polarity),
            'engagement': engagement,
            'credibility': credibility
        }
    
    def _get_subreddit_credibility(self, subreddit: str) -> float:
        """Get credibility weight for subreddit"""
        high_credibility = ['securityanalysis', 'valueinvesting']
        medium_credibility = ['investing', 'stocks']
        
        if subreddit in high_credibility:
            return 1.0
        elif subreddit in medium_credibility:
            return 0.8
        else:
            return 0.6
    
    def _get_sentiment_distribution(self, sentiment_scores: List[Dict]) -> Dict:
        """Get distribution of sentiment scores"""
        if not sentiment_scores:
            return {'positive': 0, 'neutral': 0, 'negative': 0}
        
        positive = sum(1 for s in sentiment_scores if s['score'] > 0.1)
        negative = sum(1 for s in sentiment_scores if s['score'] < -0.1)
        neutral = len(sentiment_scores) - positive - negative
        
        return {'positive': positive, 'neutral': neutral, 'negative': negative}

class AnalystSentimentAnalyzer(BaseSentimentAnalyzer):
    """
    Analyst Sentiment Analyzer
    Analyzes recommendation changes and estimate revisions
    """
    
    def __init__(self):
        self.recommendation_mapping = {
            'Strong Buy': 2.0,
            'Buy': 1.0,
            'Hold': 0.0,
            'Sell': -1.0,
            'Strong Sell': -2.0
        }
    
    def get_sentiment(self, symbol: str) -> SentimentResult:
        """Get analyst sentiment for a stock symbol"""
        try:
            # Get analyst recommendations from yfinance
            ticker = yf.Ticker(symbol)
            
            # Get recommendations
            try:
                recommendations = ticker.recommendations
                if recommendations is not None and not recommendations.empty:
                    recent_recs = recommendations.tail(10)  # Last 10 recommendations
                    rec_sentiment = self._analyze_recommendations(recent_recs)
                else:
                    rec_sentiment = {'score': 0.0, 'confidence': 0.0}
            except:
                rec_sentiment = {'score': 0.0, 'confidence': 0.0}
            
            # Get analyst estimates (mock data)
            estimate_sentiment = self._get_estimate_revisions(symbol)
            
            # Combine recommendation and estimate sentiment
            combined_score = (rec_sentiment['score'] * 0.6 + 
                            estimate_sentiment['score'] * 0.4)
            combined_confidence = (rec_sentiment['confidence'] * 0.6 + 
                                 estimate_sentiment['confidence'] * 0.4)
            
            return SentimentResult(
                score=combined_score,
                confidence=combined_confidence,
                magnitude=abs(combined_score),
                source='analyst',
                timestamp=datetime.now(),
                raw_data={
                    'recommendation_sentiment': rec_sentiment,
                    'estimate_sentiment': estimate_sentiment
                }
            )
            
        except Exception as e:
            print(f"Error analyzing analyst sentiment for {symbol}: {e}")
            return SentimentResult(
                score=0.0,
                confidence=0.0,
                magnitude=0.0,
                source='analyst',
                timestamp=datetime.now(),
                raw_data={'error': str(e)}
            )
    
    def _analyze_recommendations(self, recommendations: pd.DataFrame) -> Dict:
        """Analyze analyst recommendations"""
        if recommendations.empty:
            return {'score': 0.0, 'confidence': 0.0}
        
        # Convert recommendations to numerical scores
        rec_scores = []
        for _, row in recommendations.iterrows():
            firm = row.get('Firm', '')
            grade = row.get('To Grade', row.get('Grade', ''))
            
            # Map recommendation to score
            score = 0.0
            for rec_type, value in self.recommendation_mapping.items():
                if rec_type.lower() in str(grade).lower():
                    score = value
                    break
            
            rec_scores.append(score)
        
        if rec_scores:
            avg_score = np.mean(rec_scores)
            # Higher confidence with more recommendations
            confidence = min(1.0, len(rec_scores) / 10.0)
            return {'score': avg_score / 2.0, 'confidence': confidence}  # Normalize to -1,1
        else:
            return {'score': 0.0, 'confidence': 0.0}
    
    def _get_estimate_revisions(self, symbol: str) -> Dict:
        """Analyze estimate revisions (mock implementation)"""
        # Mock estimate revision data
        # In production, would integrate with I/B/E/S or similar service
        
        # Simulate estimate revisions
        revision_trend = np.random.normal(0.02, 0.05)  # Small positive bias
        
        return {
            'score': np.clip(revision_trend, -1.0, 1.0),
            'confidence': 0.6
        }

class SentimentAnalyzer:
    """
    Comprehensive Multi-source Sentiment Analysis
    Integrates news, social media, and analyst sentiment
    """
    
    def __init__(self, news_api_key: str = None):
        self.news_analyzer = NewsSentimentAnalyzer(news_api_key)
        self.reddit_analyzer = RedditSentimentAnalyzer()
        self.analyst_analyzer = AnalystSentimentAnalyzer()
        
        # Source reliability weights
        self.source_weights = {
            'news': 0.4,      # High weight for financial news
            'analyst': 0.35,  # Professional analyst opinions
            'reddit': 0.25    # Social sentiment
        }
    
    def analyze_comprehensive_sentiment(self, symbol: str) -> Dict:
        """Analyze comprehensive sentiment from all sources"""
        try:
            # Collect sentiment from multiple sources
            news_sentiment = self.news_analyzer.get_sentiment(symbol)
            reddit_sentiment = self.reddit_analyzer.get_sentiment(symbol)
            analyst_sentiment = self.analyst_analyzer.get_sentiment(symbol)
            
            # Calculate weighted composite sentiment
            sentiments = {
                'news': news_sentiment,
                'reddit': reddit_sentiment,
                'analyst': analyst_sentiment
            }
            
            weighted_sentiment = self._calculate_weighted_sentiment(sentiments)
            confidence = self._calculate_composite_confidence(sentiments)
            
            # Determine sentiment category
            sentiment_category = self._categorize_sentiment(weighted_sentiment)
            
            return {
                'composite_score': weighted_sentiment,
                'confidence': confidence,
                'sentiment_category': sentiment_category,
                'magnitude': abs(weighted_sentiment),
                'components': {
                    'news': {
                        'score': news_sentiment.score,
                        'confidence': news_sentiment.confidence,
                        'weight': self.source_weights['news']
                    },
                    'reddit': {
                        'score': reddit_sentiment.score,
                        'confidence': reddit_sentiment.confidence,
                        'weight': self.source_weights['reddit']
                    },
                    'analyst': {
                        'score': analyst_sentiment.score,
                        'confidence': analyst_sentiment.confidence,
                        'weight': self.source_weights['analyst']
                    }
                },
                'analysis_timestamp': datetime.now(),
                'symbol': symbol
            }
            
        except Exception as e:
            print(f"Error in comprehensive sentiment analysis for {symbol}: {e}")
            return {
                'composite_score': 0.0,
                'confidence': 0.0,
                'sentiment_category': 'neutral',
                'magnitude': 0.0,
                'components': {},
                'error': str(e),
                'analysis_timestamp': datetime.now(),
                'symbol': symbol
            }
    
    def _calculate_weighted_sentiment(self, sentiments: Dict[str, SentimentResult]) -> float:
        """Calculate confidence-weighted sentiment score"""
        weighted_sum = 0.0
        total_weight = 0.0
        
        for source, sentiment in sentiments.items():
            # Weight by both source reliability and confidence
            effective_weight = self.source_weights[source] * sentiment.confidence
            weighted_sum += sentiment.score * effective_weight
            total_weight += effective_weight
        
        if total_weight > 0:
            return weighted_sum / total_weight
        else:
            return 0.0
    
    def _calculate_composite_confidence(self, sentiments: Dict[str, SentimentResult]) -> float:
        """Calculate composite confidence score"""
        confidences = [sentiment.confidence for sentiment in sentiments.values()]
        
        # Average confidence weighted by source reliability
        weighted_confidence = sum(
            confidences[i] * list(self.source_weights.values())[i]
            for i in range(len(confidences))
        )
        
        return weighted_confidence
    
    def _categorize_sentiment(self, score: float) -> str:
        """Categorize sentiment score into descriptive category"""
        if score >= 0.3:
            return 'very_positive'
        elif score >= 0.1:
            return 'positive'
        elif score >= -0.1:
            return 'neutral'
        elif score >= -0.3:
            return 'negative'
        else:
            return 'very_negative'

def main():
    """Example usage of sentiment analysis framework"""
    print("Sentiment Analysis NLP Pipeline")
    print("=" * 40)
    
    # Initialize sentiment analyzer
    analyzer = SentimentAnalyzer()
    
    # Test symbols
    test_symbols = ['AAPL', 'MSFT', 'GOOGL']
    
    for symbol in test_symbols:
        print(f"\nAnalyzing sentiment for {symbol}:")
        print("-" * 30)
        
        result = analyzer.analyze_comprehensive_sentiment(symbol)
        
        print(f"Composite Score: {result['composite_score']:.3f}")
        print(f"Confidence: {result['confidence']:.1%}")
        print(f"Category: {result['sentiment_category']}")
        print(f"Magnitude: {result['magnitude']:.3f}")
        
        print("\nComponent Breakdown:")
        for source, data in result['components'].items():
            print(f"  {source.capitalize()}: {data['score']:.3f} "
                  f"(confidence: {data['confidence']:.1%}, weight: {data['weight']:.1%})")

if __name__ == "__main__":
    main()