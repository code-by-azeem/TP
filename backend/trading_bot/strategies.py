"""
Trading Strategies for the Bot
This file contains different trading strategies that can be used by the bot.
"""
import MetaTrader5 as mt5
import numpy as np
import logging
from typing import Dict, Optional, List
from datetime import datetime

log = logging.getLogger(__name__)

class BaseStrategy:
    """Base class for all trading strategies"""
    
    def __init__(self, symbol: str = "ETHUSD"):
        self.symbol = symbol
        self.name = "base_strategy"
        
    def analyze(self, rates: np.ndarray) -> Optional[Dict]:
        """
        Analyze market data and return trading signal
        Returns: Dict with signal info or None
        """
        raise NotImplementedError("Subclasses must implement analyze method")
        
    def get_name(self) -> str:
        return self.name

class MovingAverageCrossover(BaseStrategy):
    """Simple Moving Average Crossover Strategy"""
    
    def __init__(self, symbol: str = "ETHUSD", short_period: int = 10, long_period: int = 50):
        super().__init__(symbol)
        self.name = "ma_crossover"
        self.short_period = short_period
        self.long_period = long_period
        
    def analyze(self, rates: np.ndarray) -> Optional[Dict]:
        """
        Generate signal based on moving average crossover
        """
        try:
            if len(rates) < self.long_period:
                return None
                
            # Extract close prices
            close_prices = np.array([rate[4] for rate in rates])
            
            # Calculate moving averages
            short_ma = np.mean(close_prices[-self.short_period:])
            long_ma = np.mean(close_prices[-self.long_period:])
            
            # Previous MAs for trend confirmation
            if len(close_prices) >= self.long_period + 1:
                prev_short_ma = np.mean(close_prices[-self.short_period-1:-1])
                prev_long_ma = np.mean(close_prices[-self.long_period-1:-1])
            else:
                return None
            
            current_price = close_prices[-1]
            
            # Generate signals
            signal = None
            
            # Bullish crossover: short MA crosses above long MA
            if (prev_short_ma <= prev_long_ma and short_ma > long_ma):
                signal = {
                    'type': 'BUY',
                    'price': current_price,
                    'confidence': 0.8,
                    'strategy': self.name,
                    'short_ma': short_ma,
                    'long_ma': long_ma,
                    'reason': 'MA Bullish Crossover'
                }
            
            # Bearish crossover: short MA crosses below long MA
            elif (prev_short_ma >= prev_long_ma and short_ma < long_ma):
                signal = {
                    'type': 'SELL',
                    'price': current_price,
                    'confidence': 0.8,
                    'strategy': self.name,
                    'short_ma': short_ma,
                    'long_ma': long_ma,
                    'reason': 'MA Bearish Crossover'
                }
            
            return signal
            
        except Exception as e:
            log.error(f"Error in MA crossover analysis: {e}")
            return None

class RSIStrategy(BaseStrategy):
    """RSI-based trading strategy"""
    
    def __init__(self, symbol: str = "ETHUSD", period: int = 14, oversold: float = 30, overbought: float = 70):
        super().__init__(symbol)
        self.name = "rsi_strategy"
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        
    def calculate_rsi(self, prices: np.ndarray) -> float:
        """Calculate RSI value"""
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-self.period:])
        avg_loss = np.mean(losses[-self.period:])
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
        
    def analyze(self, rates: np.ndarray) -> Optional[Dict]:
        """Generate signal based on RSI levels"""
        try:
            if len(rates) < self.period + 1:
                return None
                
            close_prices = np.array([rate[4] for rate in rates])
            current_price = close_prices[-1]
            
            rsi = self.calculate_rsi(close_prices)
            
            signal = None
            
            # Oversold condition - potential buy signal
            if rsi < self.oversold:
                signal = {
                    'type': 'BUY',
                    'price': current_price,
                    'confidence': 0.7,
                    'strategy': self.name,
                    'rsi': rsi,
                    'reason': f'RSI Oversold ({rsi:.2f})'
                }
            
            # Overbought condition - potential sell signal
            elif rsi > self.overbought:
                signal = {
                    'type': 'SELL',
                    'price': current_price,
                    'confidence': 0.7,
                    'strategy': self.name,
                    'rsi': rsi,
                    'reason': f'RSI Overbought ({rsi:.2f})'
                }
            
            return signal
            
        except Exception as e:
            log.error(f"Error in RSI analysis: {e}")
            return None

class BreakoutStrategy(BaseStrategy):
    """Price breakout strategy based on support/resistance levels"""
    
    def __init__(self, symbol: str = "ETHUSD", lookback_period: int = 20, breakout_threshold: float = 0.001):
        super().__init__(symbol)
        self.name = "breakout_strategy"
        self.lookback_period = lookback_period
        self.breakout_threshold = breakout_threshold
        
    def analyze(self, rates: np.ndarray) -> Optional[Dict]:
        """Generate signal based on price breakouts"""
        try:
            if len(rates) < self.lookback_period + 1:
                return None
                
            # Get recent data
            recent_rates = rates[-self.lookback_period:]
            high_prices = np.array([rate[2] for rate in recent_rates])
            low_prices = np.array([rate[3] for rate in recent_rates])
            close_prices = np.array([rate[4] for rate in recent_rates])
            
            current_price = close_prices[-1]
            
            # Calculate support and resistance levels
            resistance = np.max(high_prices[:-1])  # Exclude current candle
            support = np.min(low_prices[:-1])      # Exclude current candle
            
            signal = None
            
            # Breakout above resistance
            if current_price > resistance * (1 + self.breakout_threshold):
                signal = {
                    'type': 'BUY',
                    'price': current_price,
                    'confidence': 0.75,
                    'strategy': self.name,
                    'resistance': resistance,
                    'support': support,
                    'reason': f'Breakout above resistance ({resistance:.4f})'
                }
            
            # Breakdown below support
            elif current_price < support * (1 - self.breakout_threshold):
                signal = {
                    'type': 'SELL',
                    'price': current_price,
                    'confidence': 0.75,
                    'strategy': self.name,
                    'resistance': resistance,
                    'support': support,
                    'reason': f'Breakdown below support ({support:.4f})'
                }
            
            return signal
            
        except Exception as e:
            log.error(f"Error in breakout analysis: {e}")
            return None

class CombinedStrategy(BaseStrategy):
    """Combined strategy using multiple indicators"""
    
    def __init__(self, symbol: str = "ETHUSD"):
        super().__init__(symbol)
        self.name = "combined_strategy"
        self.ma_strategy = MovingAverageCrossover(symbol)
        self.rsi_strategy = RSIStrategy(symbol)
        self.breakout_strategy = BreakoutStrategy(symbol)
        
    def analyze(self, rates: np.ndarray) -> Optional[Dict]:
        """Combine signals from multiple strategies"""
        try:
            # Get signals from individual strategies
            ma_signal = self.ma_strategy.analyze(rates)
            rsi_signal = self.rsi_strategy.analyze(rates)
            breakout_signal = self.breakout_strategy.analyze(rates)
            
            signals = [s for s in [ma_signal, rsi_signal, breakout_signal] if s is not None]
            
            if not signals:
                return None
            
            # Count buy and sell signals
            buy_signals = [s for s in signals if s['type'] == 'BUY']
            sell_signals = [s for s in signals if s['type'] == 'SELL']
            
            current_price = rates[-1][4]
            
            # Require at least 2 agreeing signals
            if len(buy_signals) >= 2:
                avg_confidence = np.mean([s['confidence'] for s in buy_signals])
                reasons = [s['reason'] for s in buy_signals]
                
                return {
                    'type': 'BUY',
                    'price': current_price,
                    'confidence': min(avg_confidence * 1.2, 0.95),  # Boost confidence for agreement
                    'strategy': self.name,
                    'reasons': reasons,
                    'supporting_signals': len(buy_signals)
                }
            
            elif len(sell_signals) >= 2:
                avg_confidence = np.mean([s['confidence'] for s in sell_signals])
                reasons = [s['reason'] for s in sell_signals]
                
                return {
                    'type': 'SELL',
                    'price': current_price,
                    'confidence': min(avg_confidence * 1.2, 0.95),
                    'strategy': self.name,
                    'reasons': reasons,
                    'supporting_signals': len(sell_signals)
                }
            
            return None
            
        except Exception as e:
            log.error(f"Error in combined strategy analysis: {e}")
            return None

# Strategy factory
AVAILABLE_STRATEGIES = {
    'ma_crossover': MovingAverageCrossover,
    'rsi_strategy': RSIStrategy,
    'breakout_strategy': BreakoutStrategy,
    'combined_strategy': CombinedStrategy,
    'default': MovingAverageCrossover  # Default strategy
}

def get_strategy(strategy_name: str, symbol: str = "ETHUSD") -> BaseStrategy:
    """Get strategy instance by name"""
    strategy_class = AVAILABLE_STRATEGIES.get(strategy_name, MovingAverageCrossover)
    return strategy_class(symbol)

def list_strategies() -> List[str]:
    """Get list of available strategy names"""
    return list(AVAILABLE_STRATEGIES.keys())