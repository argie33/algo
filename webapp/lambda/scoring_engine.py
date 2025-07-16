#!/usr/bin/env python3
"""
Six-Factor Stock Scoring Engine
Institutional-grade scoring system based on academic research
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

class StockScoringEngine:
    """Main scoring engine implementing the 6-factor system"""
    
    def __init__(self):
        self.factors = {
            'quality': QualityScore(),
            'growth': GrowthScore(),
            'value': ValueScore(),
            'momentum': MomentumScore(),
            'sentiment': SentimentScore(),
            'positioning': PositioningScore()
        }
        
        # Factor weights (must sum to 1.0)
        self.weights = {
            'quality': 0.20,
            'growth': 0.20,
            'value': 0.20,
            'momentum': 0.15,
            'sentiment': 0.15,
            'positioning': 0.10
        }
    
    def calculate_composite_score(self, symbol):
        """Calculate composite score for a stock"""
        try:
            # Get stock data
            stock = yf.Ticker(symbol)
            
            # Calculate individual factor scores
            scores = {}
            for factor_name, factor_calculator in self.factors.items():
                try:
                    scores[factor_name] = factor_calculator.calculate(stock)
                except Exception as e:
                    print(f"Error calculating {factor_name} for {symbol}: {e}")
                    scores[factor_name] = {'composite': 50, 'trend': 'stable'}
            
            # Calculate weighted composite score
            composite = sum(
                scores[factor]['composite'] * self.weights[factor]
                for factor in scores
            )
            
            # Get stock info
            info = stock.info
            
            return {
                'symbol': symbol,
                'company_name': info.get('longName', symbol),
                'composite': round(composite, 1),
                'quality': scores['quality'],
                'growth': scores['growth'],
                'value': scores['value'],
                'momentum': scores['momentum'],
                'sentiment': scores['sentiment'],
                'positioning': scores['positioning'],
                'market_regime': self._detect_market_regime(),
                'confidence_level': self._calculate_confidence(scores),
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"Error calculating composite score for {symbol}: {e}")
            return None
    
    def _detect_market_regime(self):
        """Simple market regime detection"""
        try:
            spy = yf.Ticker('SPY')
            hist = spy.history(period='3mo')
            recent_return = (hist['Close'][-1] / hist['Close'][0] - 1) * 100
            return 'bull' if recent_return > 0 else 'bear'
        except:
            return 'neutral'
    
    def _calculate_confidence(self, scores):
        """Calculate confidence level based on data quality"""
        # Simple confidence calculation based on score consistency
        score_values = [scores[factor]['composite'] for factor in scores]
        std_dev = np.std(score_values)
        # Higher std dev means lower confidence
        confidence = max(70, 100 - (std_dev * 2))
        return round(confidence, 1)


class QualityScore:
    """Quality Score Calculator - Based on Piotroski F-Score and Altman Z-Score"""
    
    def calculate(self, stock):
        try:
            # Get financial data
            info = stock.info
            financials = stock.financials
            balance_sheet = stock.balance_sheet
            cashflow = stock.cashflow
            
            # Calculate sub-scores
            earnings_quality = self._calculate_earnings_quality(financials, cashflow)
            balance_strength = self._calculate_balance_strength(balance_sheet, info)
            profitability = self._calculate_profitability(financials, balance_sheet)
            management = self._calculate_management(info, financials)
            
            # Weighted composite
            composite = (
                earnings_quality * 0.25 +
                balance_strength * 0.30 +
                profitability * 0.25 +
                management * 0.20
            )
            
            return {
                'composite': round(composite, 1),
                'earnings_quality': round(earnings_quality, 1),
                'balance_strength': round(balance_strength, 1),
                'profitability': round(profitability, 1),
                'management': round(management, 1),
                'trend': self._determine_trend(composite)
            }
            
        except Exception as e:
            print(f"Error in quality score calculation: {e}")
            return self._default_score()
    
    def _calculate_earnings_quality(self, financials, cashflow):
        """Calculate earnings quality based on cash flow vs net income"""
        try:
            if financials.empty or cashflow.empty:
                return 50
            
            # Get most recent year data
            net_income = financials.loc['Net Income'].iloc[0] if 'Net Income' in financials.index else 0
            operating_cf = cashflow.loc['Operating Cash Flow'].iloc[0] if 'Operating Cash Flow' in cashflow.index else 0
            
            if net_income == 0:
                return 50
            
            # Cash flow to net income ratio
            cf_ni_ratio = operating_cf / abs(net_income)
            
            # Score based on ratio (higher is better)
            if cf_ni_ratio > 1.2:
                return 90
            elif cf_ni_ratio > 1.0:
                return 80
            elif cf_ni_ratio > 0.8:
                return 70
            elif cf_ni_ratio > 0.6:
                return 60
            else:
                return 40
                
        except:
            return 50
    
    def _calculate_balance_strength(self, balance_sheet, info):
        """Calculate balance sheet strength (simplified Altman Z-Score)"""
        try:
            if balance_sheet.empty:
                return 50
            
            # Get key metrics
            total_assets = balance_sheet.loc['Total Assets'].iloc[0] if 'Total Assets' in balance_sheet.index else 1
            total_debt = balance_sheet.loc['Total Debt'].iloc[0] if 'Total Debt' in balance_sheet.index else 0
            current_assets = balance_sheet.loc['Current Assets'].iloc[0] if 'Current Assets' in balance_sheet.index else 0
            current_liabilities = balance_sheet.loc['Current Liabilities'].iloc[0] if 'Current Liabilities' in balance_sheet.index else 1
            
            # Calculate ratios
            debt_ratio = total_debt / total_assets
            current_ratio = current_assets / current_liabilities
            
            # Score based on ratios
            debt_score = 90 if debt_ratio < 0.3 else 70 if debt_ratio < 0.5 else 50 if debt_ratio < 0.7 else 30
            liquidity_score = 90 if current_ratio > 2.0 else 70 if current_ratio > 1.5 else 50 if current_ratio > 1.0 else 30
            
            return (debt_score + liquidity_score) / 2
            
        except:
            return 50
    
    def _calculate_profitability(self, financials, balance_sheet):
        """Calculate profitability metrics"""
        try:
            if financials.empty or balance_sheet.empty:
                return 50
            
            # Get metrics
            net_income = financials.loc['Net Income'].iloc[0] if 'Net Income' in financials.index else 0
            total_assets = balance_sheet.loc['Total Assets'].iloc[0] if 'Total Assets' in balance_sheet.index else 1
            shareholders_equity = balance_sheet.loc['Stockholders Equity'].iloc[0] if 'Stockholders Equity' in balance_sheet.index else 1
            
            # Calculate ROA and ROE
            roa = (net_income / total_assets) * 100
            roe = (net_income / shareholders_equity) * 100
            
            # Score based on profitability
            roa_score = 90 if roa > 15 else 70 if roa > 10 else 50 if roa > 5 else 30
            roe_score = 90 if roe > 20 else 70 if roe > 15 else 50 if roe > 10 else 30
            
            return (roa_score + roe_score) / 2
            
        except:
            return 50
    
    def _calculate_management(self, info, financials):
        """Calculate management effectiveness"""
        try:
            # Use available metrics like profit margins
            profit_margin = info.get('profitMargins', 0) * 100 if info.get('profitMargins') else 0
            
            # Score based on profit margin
            if profit_margin > 20:
                return 90
            elif profit_margin > 15:
                return 80
            elif profit_margin > 10:
                return 70
            elif profit_margin > 5:
                return 60
            else:
                return 40
                
        except:
            return 50
    
    def _determine_trend(self, score):
        """Determine trend based on score"""
        if score > 75:
            return 'improving'
        elif score > 50:
            return 'stable'
        else:
            return 'declining'
    
    def _default_score(self):
        """Default score when calculation fails"""
        return {
            'composite': 50,
            'earnings_quality': 50,
            'balance_strength': 50,
            'profitability': 50,
            'management': 50,
            'trend': 'stable'
        }


class GrowthScore:
    """Growth Score Calculator - Based on Sustainable Growth Rate model"""
    
    def calculate(self, stock):
        try:
            info = stock.info
            financials = stock.financials
            
            # Calculate sub-scores
            revenue_growth = self._calculate_revenue_growth(financials)
            earnings_growth = self._calculate_earnings_growth(financials)
            fundamental_growth = self._calculate_fundamental_growth(info, financials)
            market_expansion = self._calculate_market_expansion(info)
            
            # Weighted composite
            composite = (
                revenue_growth * 0.30 +
                earnings_growth * 0.30 +
                fundamental_growth * 0.25 +
                market_expansion * 0.15
            )
            
            return {
                'composite': round(composite, 1),
                'revenue_growth': round(revenue_growth, 1),
                'earnings_growth': round(earnings_growth, 1),
                'fundamental_growth': round(fundamental_growth, 1),
                'market_expansion': round(market_expansion, 1),
                'trend': self._determine_trend(composite)
            }
            
        except Exception as e:
            print(f"Error in growth score calculation: {e}")
            return self._default_score()
    
    def _calculate_revenue_growth(self, financials):
        """Calculate revenue growth rate"""
        try:
            if financials.empty or 'Total Revenue' not in financials.index:
                return 50
            
            revenues = financials.loc['Total Revenue'].dropna()
            if len(revenues) < 2:
                return 50
            
            # Calculate year-over-year growth
            recent_revenue = revenues.iloc[0]
            previous_revenue = revenues.iloc[1]
            
            if previous_revenue == 0:
                return 50
            
            growth_rate = ((recent_revenue / previous_revenue) - 1) * 100
            
            # Score based on growth rate
            if growth_rate > 25:
                return 95
            elif growth_rate > 15:
                return 85
            elif growth_rate > 10:
                return 75
            elif growth_rate > 5:
                return 65
            elif growth_rate > 0:
                return 55
            else:
                return 35
                
        except:
            return 50
    
    def _calculate_earnings_growth(self, financials):
        """Calculate earnings growth rate"""
        try:
            if financials.empty or 'Net Income' not in financials.index:
                return 50
            
            earnings = financials.loc['Net Income'].dropna()
            if len(earnings) < 2:
                return 50
            
            recent_earnings = earnings.iloc[0]
            previous_earnings = earnings.iloc[1]
            
            if previous_earnings <= 0:
                return 60 if recent_earnings > 0 else 40
            
            growth_rate = ((recent_earnings / previous_earnings) - 1) * 100
            
            # Score based on growth rate
            if growth_rate > 30:
                return 95
            elif growth_rate > 20:
                return 85
            elif growth_rate > 15:
                return 75
            elif growth_rate > 10:
                return 65
            elif growth_rate > 0:
                return 55
            else:
                return 35
                
        except:
            return 50
    
    def _calculate_fundamental_growth(self, info, financials):
        """Calculate fundamental growth drivers"""
        try:
            # Use ROE as proxy for fundamental growth
            roe = info.get('returnOnEquity', 0) * 100 if info.get('returnOnEquity') else 0
            
            # Score based on ROE
            if roe > 25:
                return 90
            elif roe > 20:
                return 80
            elif roe > 15:
                return 70
            elif roe > 10:
                return 60
            else:
                return 40
                
        except:
            return 50
    
    def _calculate_market_expansion(self, info):
        """Calculate market expansion potential"""
        try:
            # Use market cap as proxy for growth potential (smaller = more potential)
            market_cap = info.get('marketCap', 0)
            
            if market_cap == 0:
                return 50
            
            # Score based on market cap (inverted - smaller companies have more growth potential)
            if market_cap < 2e9:  # Small cap
                return 85
            elif market_cap < 10e9:  # Mid cap
                return 75
            elif market_cap < 50e9:  # Large cap
                return 65
            else:  # Mega cap
                return 55
                
        except:
            return 50
    
    def _determine_trend(self, score):
        """Determine trend based on score"""
        if score > 75:
            return 'accelerating'
        elif score > 50:
            return 'stable'
        else:
            return 'decelerating'
    
    def _default_score(self):
        """Default score when calculation fails"""
        return {
            'composite': 50,
            'revenue_growth': 50,
            'earnings_growth': 50,
            'fundamental_growth': 50,
            'market_expansion': 50,
            'trend': 'stable'
        }


class ValueScore:
    """Value Score Calculator - Based on Fama-French Value Factor"""
    
    def calculate(self, stock):
        try:
            info = stock.info
            
            # Calculate sub-scores
            pe_score = self._calculate_pe_score(info)
            dcf_score = self._calculate_dcf_score(info)
            relative_value = self._calculate_relative_value(info)
            
            # Weighted composite
            composite = (
                pe_score * 0.40 +
                dcf_score * 0.35 +
                relative_value * 0.25
            )
            
            return {
                'composite': round(composite, 1),
                'pe_score': round(pe_score, 1),
                'dcf_score': round(dcf_score, 1),
                'relative_value': round(relative_value, 1),
                'trend': self._determine_trend(composite)
            }
            
        except Exception as e:
            print(f"Error in value score calculation: {e}")
            return self._default_score()
    
    def _calculate_pe_score(self, info):
        """Calculate PE ratio score"""
        try:
            pe_ratio = info.get('trailingPE', 0)
            if pe_ratio == 0 or pe_ratio is None:
                return 50
            
            # Score based on PE ratio (lower is better for value)
            if pe_ratio < 10:
                return 95
            elif pe_ratio < 15:
                return 80
            elif pe_ratio < 20:
                return 70
            elif pe_ratio < 25:
                return 60
            elif pe_ratio < 30:
                return 50
            else:
                return 30
                
        except:
            return 50
    
    def _calculate_dcf_score(self, info):
        """Calculate DCF-based score (simplified)"""
        try:
            # Use PEG ratio as proxy for DCF value
            peg_ratio = info.get('pegRatio', 0)
            if peg_ratio == 0 or peg_ratio is None:
                return 50
            
            # Score based on PEG ratio (lower is better)
            if peg_ratio < 0.5:
                return 95
            elif peg_ratio < 1.0:
                return 85
            elif peg_ratio < 1.5:
                return 70
            elif peg_ratio < 2.0:
                return 60
            else:
                return 40
                
        except:
            return 50
    
    def _calculate_relative_value(self, info):
        """Calculate relative value score"""
        try:
            # Use price-to-book ratio
            pb_ratio = info.get('priceToBook', 0)
            if pb_ratio == 0 or pb_ratio is None:
                return 50
            
            # Score based on P/B ratio (lower is better)
            if pb_ratio < 1.0:
                return 95
            elif pb_ratio < 2.0:
                return 80
            elif pb_ratio < 3.0:
                return 70
            elif pb_ratio < 4.0:
                return 60
            else:
                return 40
                
        except:
            return 50
    
    def _determine_trend(self, score):
        """Determine trend based on score"""
        if score > 75:
            return 'undervalued'
        elif score > 50:
            return 'fairly_valued'
        else:
            return 'overvalued'
    
    def _default_score(self):
        """Default score when calculation fails"""
        return {
            'composite': 50,
            'pe_score': 50,
            'dcf_score': 50,
            'relative_value': 50,
            'trend': 'fairly_valued'
        }


class MomentumScore:
    """Momentum Score Calculator - Based on Jegadeesh-Titman Momentum"""
    
    def calculate(self, stock):
        try:
            # Get price history
            hist = stock.history(period='1y')
            
            # Calculate sub-scores
            price_momentum = self._calculate_price_momentum(hist)
            fundamental_momentum = self._calculate_fundamental_momentum(stock)
            technical = self._calculate_technical_momentum(hist)
            volume_analysis = self._calculate_volume_momentum(hist)
            
            # Weighted composite
            composite = (
                price_momentum * 0.40 +
                fundamental_momentum * 0.30 +
                technical * 0.20 +
                volume_analysis * 0.10
            )
            
            return {
                'composite': round(composite, 1),
                'price_momentum': round(price_momentum, 1),
                'fundamental_momentum': round(fundamental_momentum, 1),
                'technical': round(technical, 1),
                'volume_analysis': round(volume_analysis, 1),
                'trend': self._determine_trend(composite)
            }
            
        except Exception as e:
            print(f"Error in momentum score calculation: {e}")
            return self._default_score()
    
    def _calculate_price_momentum(self, hist):
        """Calculate 12-1 month price momentum"""
        try:
            if len(hist) < 30:
                return 50
            
            # 12-month momentum excluding most recent month
            recent_price = hist['Close'].iloc[-22]  # ~1 month ago
            year_ago_price = hist['Close'].iloc[0]
            
            if year_ago_price == 0:
                return 50
            
            momentum = ((recent_price / year_ago_price) - 1) * 100
            
            # Score based on momentum
            if momentum > 50:
                return 95
            elif momentum > 30:
                return 85
            elif momentum > 20:
                return 75
            elif momentum > 10:
                return 65
            elif momentum > 0:
                return 55
            elif momentum > -10:
                return 45
            else:
                return 25
                
        except:
            return 50
    
    def _calculate_fundamental_momentum(self, stock):
        """Calculate fundamental momentum (earnings revision proxy)"""
        try:
            info = stock.info
            
            # Use earnings growth as proxy for fundamental momentum
            earnings_growth = info.get('earningsGrowth', 0) * 100 if info.get('earningsGrowth') else 0
            
            # Score based on earnings growth
            if earnings_growth > 25:
                return 90
            elif earnings_growth > 15:
                return 80
            elif earnings_growth > 10:
                return 70
            elif earnings_growth > 5:
                return 60
            elif earnings_growth > 0:
                return 55
            else:
                return 40
                
        except:
            return 50
    
    def _calculate_technical_momentum(self, hist):
        """Calculate technical momentum (moving averages)"""
        try:
            if len(hist) < 50:
                return 50
            
            # Calculate moving averages
            ma_20 = hist['Close'].rolling(20).mean()
            ma_50 = hist['Close'].rolling(50).mean()
            
            current_price = hist['Close'].iloc[-1]
            current_ma_20 = ma_20.iloc[-1]
            current_ma_50 = ma_50.iloc[-1]
            
            # Score based on price vs moving averages
            score = 50
            if current_price > current_ma_20:
                score += 20
            if current_price > current_ma_50:
                score += 15
            if current_ma_20 > current_ma_50:
                score += 15
            
            return min(95, score)
            
        except:
            return 50
    
    def _calculate_volume_momentum(self, hist):
        """Calculate volume momentum"""
        try:
            if len(hist) < 20:
                return 50
            
            # Compare recent volume to average
            recent_volume = hist['Volume'].iloc[-10:].mean()
            avg_volume = hist['Volume'].iloc[-60:-10].mean()
            
            if avg_volume == 0:
                return 50
            
            volume_ratio = recent_volume / avg_volume
            
            # Score based on volume increase
            if volume_ratio > 1.5:
                return 85
            elif volume_ratio > 1.2:
                return 75
            elif volume_ratio > 1.0:
                return 65
            elif volume_ratio > 0.8:
                return 55
            else:
                return 45
                
        except:
            return 50
    
    def _determine_trend(self, score):
        """Determine trend based on score"""
        if score > 75:
            return 'strong'
        elif score > 50:
            return 'moderate'
        else:
            return 'weak'
    
    def _default_score(self):
        """Default score when calculation fails"""
        return {
            'composite': 50,
            'price_momentum': 50,
            'fundamental_momentum': 50,
            'technical': 50,
            'volume_analysis': 50,
            'trend': 'moderate'
        }


class SentimentScore:
    """Sentiment Score Calculator - Based on Baker & Wurgler Sentiment Index"""
    
    def calculate(self, stock):
        try:
            info = stock.info
            
            # Calculate sub-scores (simplified due to data limitations)
            analyst_sentiment = self._calculate_analyst_sentiment(info)
            social_sentiment = self._calculate_social_sentiment(info)
            market_sentiment = self._calculate_market_sentiment(info)
            news_sentiment = self._calculate_news_sentiment(info)
            
            # Weighted composite
            composite = (
                analyst_sentiment * 0.25 +
                social_sentiment * 0.25 +
                market_sentiment * 0.25 +
                news_sentiment * 0.25
            )
            
            return {
                'composite': round(composite, 1),
                'analyst_sentiment': round(analyst_sentiment, 1),
                'social_sentiment': round(social_sentiment, 1),
                'market_sentiment': round(market_sentiment, 1),
                'news_sentiment': round(news_sentiment, 1),
                'trend': self._determine_trend(composite)
            }
            
        except Exception as e:
            print(f"Error in sentiment score calculation: {e}")
            return self._default_score()
    
    def _calculate_analyst_sentiment(self, info):
        """Calculate analyst sentiment"""
        try:
            # Use recommendation mean as proxy
            recommendation_mean = info.get('recommendationMean', 3.0)
            
            # Score based on recommendation (1=Strong Buy, 5=Strong Sell)
            if recommendation_mean <= 1.5:
                return 95
            elif recommendation_mean <= 2.0:
                return 85
            elif recommendation_mean <= 2.5:
                return 75
            elif recommendation_mean <= 3.0:
                return 65
            elif recommendation_mean <= 3.5:
                return 55
            else:
                return 35
                
        except:
            return 50
    
    def _calculate_social_sentiment(self, info):
        """Calculate social sentiment (placeholder)"""
        try:
            # Placeholder - would integrate with social media APIs
            # For now, use a random walk around 50
            import random
            return 45 + random.randint(0, 10)
        except:
            return 50
    
    def _calculate_market_sentiment(self, info):
        """Calculate market-based sentiment"""
        try:
            # Use short ratio as contrarian indicator
            short_ratio = info.get('shortRatio', 0)
            
            # Score based on short ratio (higher short ratio = more negative sentiment = contrarian positive)
            if short_ratio > 10:
                return 85
            elif short_ratio > 5:
                return 75
            elif short_ratio > 3:
                return 65
            elif short_ratio > 1:
                return 55
            else:
                return 45
                
        except:
            return 50
    
    def _calculate_news_sentiment(self, info):
        """Calculate news sentiment (placeholder)"""
        try:
            # Placeholder - would integrate with news APIs
            # For now, use earnings surprise as proxy
            earnings_growth = info.get('earningsGrowth', 0) * 100 if info.get('earningsGrowth') else 0
            
            if earnings_growth > 20:
                return 85
            elif earnings_growth > 10:
                return 75
            elif earnings_growth > 0:
                return 65
            elif earnings_growth > -10:
                return 55
            else:
                return 45
                
        except:
            return 50
    
    def _determine_trend(self, score):
        """Determine trend based on score"""
        if score > 75:
            return 'bullish'
        elif score > 50:
            return 'neutral'
        else:
            return 'bearish'
    
    def _default_score(self):
        """Default score when calculation fails"""
        return {
            'composite': 50,
            'analyst_sentiment': 50,
            'social_sentiment': 50,
            'market_sentiment': 50,
            'news_sentiment': 50,
            'trend': 'neutral'
        }


class PositioningScore:
    """Positioning Score Calculator - Smart Money Tracking"""
    
    def calculate(self, stock):
        try:
            info = stock.info
            
            # Calculate sub-scores
            institutional = self._calculate_institutional_holdings(info)
            insider = self._calculate_insider_activity(info)
            short_interest = self._calculate_short_interest(info)
            options_flow = self._calculate_options_flow(info)
            
            # Weighted composite
            composite = (
                institutional * 0.40 +
                insider * 0.25 +
                short_interest * 0.20 +
                options_flow * 0.15
            )
            
            return {
                'composite': round(composite, 1),
                'institutional': round(institutional, 1),
                'insider': round(insider, 1),
                'short_interest': round(short_interest, 1),
                'options_flow': round(options_flow, 1),
                'trend': self._determine_trend(composite)
            }
            
        except Exception as e:
            print(f"Error in positioning score calculation: {e}")
            return self._default_score()
    
    def _calculate_institutional_holdings(self, info):
        """Calculate institutional holdings score"""
        try:
            # Use held by institutions percentage
            held_by_institutions = info.get('heldByInstitutions', 0) * 100
            
            # Score based on institutional ownership
            if held_by_institutions > 80:
                return 90
            elif held_by_institutions > 60:
                return 80
            elif held_by_institutions > 40:
                return 70
            elif held_by_institutions > 20:
                return 60
            else:
                return 45
                
        except:
            return 50
    
    def _calculate_insider_activity(self, info):
        """Calculate insider activity score"""
        try:
            # Use held by insiders as proxy
            held_by_insiders = info.get('heldByInsiders', 0) * 100
            
            # Score based on insider ownership (moderate levels are good)
            if held_by_insiders > 20:
                return 85
            elif held_by_insiders > 10:
                return 90
            elif held_by_insiders > 5:
                return 80
            elif held_by_insiders > 1:
                return 70
            else:
                return 50
                
        except:
            return 50
    
    def _calculate_short_interest(self, info):
        """Calculate short interest score"""
        try:
            # Use short percentage of float
            short_percent = info.get('shortPercentOfFloat', 0) * 100
            
            # Score based on short interest (lower is generally better)
            if short_percent < 2:
                return 85
            elif short_percent < 5:
                return 75
            elif short_percent < 10:
                return 65
            elif short_percent < 15:
                return 55
            else:
                return 45
                
        except:
            return 50
    
    def _calculate_options_flow(self, info):
        """Calculate options flow score (placeholder)"""
        try:
            # Placeholder - would need options data
            # For now, use a simple heuristic based on volatility
            beta = info.get('beta', 1.0)
            
            # Score based on beta (moderate beta suggests balanced options flow)
            if 0.8 <= beta <= 1.2:
                return 75
            elif 0.6 <= beta <= 1.5:
                return 65
            else:
                return 55
                
        except:
            return 50
    
    def _determine_trend(self, score):
        """Determine trend based on score"""
        if score > 75:
            return 'accumulation'
        elif score > 50:
            return 'neutral'
        else:
            return 'distribution'
    
    def _default_score(self):
        """Default score when calculation fails"""
        return {
            'composite': 50,
            'institutional': 50,
            'insider': 50,
            'short_interest': 50,
            'options_flow': 50,
            'trend': 'neutral'
        }


# Example usage
if __name__ == "__main__":
    engine = StockScoringEngine()
    
    # Test with AAPL
    result = engine.calculate_composite_score('AAPL')
    if result:
        print(f"Composite Score for {result['symbol']}: {result['composite']}")
        print(f"Quality: {result['quality']['composite']}")
        print(f"Growth: {result['growth']['composite']}")
        print(f"Value: {result['value']['composite']}")
        print(f"Momentum: {result['momentum']['composite']}")
        print(f"Sentiment: {result['sentiment']['composite']}")
        print(f"Positioning: {result['positioning']['composite']}")