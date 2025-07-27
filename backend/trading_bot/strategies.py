"""
Trading Strategies for the Bot
This file contains different trading strategies that can be used by the bot.
"""
import MetaTrader5 as mt5
import numpy as np
import logging
import time
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
    
    def __init__(self, symbol: str = "ETHUSD", short_period: int = 5, long_period: int = 15):
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
            
            # Log MA values for debugging
            log.debug(f"MA Analysis: Short={short_ma:.4f}, Long={long_ma:.4f}, PrevShort={prev_short_ma:.4f}, PrevLong={prev_long_ma:.4f}")
            
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
                log.info(f"🚀 MA BULLISH CROSSOVER: Short MA {short_ma:.4f} crossed above Long MA {long_ma:.4f}")
            
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
                log.info(f"🔻 MA BEARISH CROSSOVER: Short MA {short_ma:.4f} crossed below Long MA {long_ma:.4f}")
            
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
            
            # Always log current RSI status for debugging
            if rsi < self.oversold:
                status = f"OVERSOLD ({rsi:.1f} < {self.oversold})"
            elif rsi > self.overbought:
                status = f"OVERBOUGHT ({rsi:.1f} > {self.overbought})"
            else:
                status = f"NEUTRAL ({rsi:.1f})"
            log.info(f"📊 RSI Status: {status}")
            
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
                log.info(f"🚀 RSI BUY: RSI {rsi:.1f} is oversold (< {self.oversold})")
            
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
                log.info(f"🔻 RSI SELL: RSI {rsi:.1f} is overbought (> {self.overbought})")
            else:
                # Show how far from signal levels
                distance_to_oversold = rsi - self.oversold
                distance_to_overbought = self.overbought - rsi
                if distance_to_oversold < distance_to_overbought:
                    log.info(f"📊 RSI: {rsi:.1f} is {distance_to_oversold:.1f} points away from oversold ({self.oversold})")
                else:
                    log.info(f"📊 RSI: {rsi:.1f} is {distance_to_overbought:.1f} points away from overbought ({self.overbought})")
            
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

class AlwaysSignalStrategy(BaseStrategy):
    """Strategy that ALWAYS generates signals for immediate testing"""
    
    def __init__(self, symbol: str = "ETHUSD"):
        super().__init__(symbol)
        self.name = "always_signal"
        self.signal_count = 0
        
    def analyze(self, rates: np.ndarray) -> Optional[Dict]:
        """Always generate a signal for testing"""
        try:
            if len(rates) < 1:
                return None
                
            current_price = float(rates[-1][4])
            self.signal_count += 1
            
            # Alternate between BUY and SELL
            signal_type = 'BUY' if self.signal_count % 2 == 1 else 'SELL'
            
            signal = {
                'type': signal_type,
                'price': current_price,
                'confidence': 0.9,
                'strategy': self.name,
                'reason': f'Always {signal_type} Signal #{self.signal_count}'
            }
            
            log.info(f"⚡ AlwaysSignal GENERATED: {signal}")
            return signal
            
        except Exception as e:
            log.error(f"❌ Error in always signal strategy: {e}")
            return None

class TestStrategy(BaseStrategy):
    """Test strategy that generates frequent signals for testing"""
    
    def __init__(self, symbol: str = "ETHUSD"):
        super().__init__(symbol)
        self.name = "test_strategy"
        self.last_signal_time = 0
        self.signal_interval = 30  # Generate signal every 30 seconds for testing (reduced from 60)
        
    def analyze(self, rates: np.ndarray) -> Optional[Dict]:
        """Generate alternating buy/sell signals for testing"""
        try:
            if len(rates) < 5:
                log.warning(f"🧪 TestStrategy: Insufficient rates: {len(rates)}")
                return None
                
            current_time = time.time()
            time_since_last = current_time - self.last_signal_time
            
            log.info(f"🧪 TestStrategy: Time since last signal: {time_since_last:.1f}s (interval: {self.signal_interval}s)")
            
            if time_since_last < self.signal_interval:
                log.debug(f"🧪 TestStrategy: Waiting... {self.signal_interval - time_since_last:.1f}s remaining")
                return None
                
            current_price = float(rates[-1][4])
            
            # Alternate between BUY and SELL signals
            signal_type = 'BUY' if int(current_time) % 120 < 60 else 'SELL'
            
            self.last_signal_time = current_time
            
            signal = {
                'type': signal_type,
                'price': current_price,
                'confidence': 0.9,
                'strategy': self.name,
                'reason': f'Test {signal_type} Signal - Every 30s'
            }
            
            log.info(f"🚀 TestStrategy GENERATED: {signal}")
            return signal
            
        except Exception as e:
            log.error(f"❌ Error in test strategy analysis: {e}")
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

# ============================================================================
# 🚀 ADVANCED STRATEGY EXAMPLES - ADD YOUR NEW STRATEGIES HERE
# ============================================================================

class BollingerBandsStrategy(BaseStrategy):
    """Bollinger Bands Strategy - Price reversal at bands"""
    
    def __init__(self, symbol: str = "ETHUSD", period: int = 20, std_dev: float = 2.0):
        super().__init__(symbol)
        self.name = "bollinger_bands"
        self.period = period
        self.std_dev = std_dev
        
    def analyze(self, rates: np.ndarray) -> Optional[Dict]:
        """Generate signals based on Bollinger Bands"""
        try:
            if len(rates) < self.period:
                return None
                
            close_prices = np.array([rate[4] for rate in rates])
            current_price = close_prices[-1]
            
            # Calculate Bollinger Bands
            sma = np.mean(close_prices[-self.period:])
            std = np.std(close_prices[-self.period:])
            
            upper_band = sma + (self.std_dev * std)
            lower_band = sma - (self.std_dev * std)
            
            # Always log current Bollinger status for debugging
            position_pct = ((current_price - lower_band) / (upper_band - lower_band)) * 100
            log.info(f"📊 BB Status: Price={current_price:.2f}, Upper={upper_band:.2f}, Lower={lower_band:.2f}, Position={position_pct:.1f}%")
            
            signal = None
            
            # Price touching lower band = BUY signal (oversold)
            if current_price <= lower_band:
                signal = {
                    'type': 'BUY',
                    'price': current_price,
                    'confidence': 0.8,
                    'strategy': self.name,
                    'upper_band': upper_band,
                    'lower_band': lower_band,
                    'sma': sma,
                    'reason': f'Price at lower band ({lower_band:.2f})'
                }
                log.info(f"📉 BOLLINGER BUY: Price {current_price:.2f} at lower band {lower_band:.2f}")
            
            # Price touching upper band = SELL signal (overbought)
            elif current_price >= upper_band:
                signal = {
                    'type': 'SELL',
                    'price': current_price,
                    'confidence': 0.8,
                    'strategy': self.name,
                    'upper_band': upper_band,
                    'lower_band': lower_band,
                    'sma': sma,
                    'reason': f'Price at upper band ({upper_band:.2f})'
                }
                log.info(f"📈 BOLLINGER SELL: Price {current_price:.2f} at upper band {upper_band:.2f}")
            else:
                # Show why no signal was generated
                if position_pct < 25:
                    log.info(f"📊 BB: Price near lower band ({position_pct:.1f}%) but not touching - waiting...")
                elif position_pct > 75:
                    log.info(f"📊 BB: Price near upper band ({position_pct:.1f}%) but not touching - waiting...")
                else:
                    log.info(f"📊 BB: Price in middle range ({position_pct:.1f}%) - no signal")
            
            return signal
            
        except Exception as e:
            log.error(f"Error in Bollinger Bands analysis: {e}")
            return None

class MACDStrategy(BaseStrategy):
    """MACD Strategy - Moving Average Convergence Divergence"""
    
    def __init__(self, symbol: str = "ETHUSD", fast_period: int = 12, slow_period: int = 26, signal_period: int = 9):
        super().__init__(symbol)
        self.name = "macd_strategy"
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        
    def calculate_ema(self, prices: np.ndarray, period: int) -> float:
        """Calculate Exponential Moving Average"""
        multiplier = 2 / (period + 1)
        ema = prices[0]  # Start with first price
        for price in prices[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        return ema
        
    def analyze(self, rates: np.ndarray) -> Optional[Dict]:
        """Generate signals based on MACD crossover"""
        try:
            if len(rates) < self.slow_period + self.signal_period:
                return None
                
            close_prices = np.array([rate[4] for rate in rates])
            current_price = close_prices[-1]
            
            # Calculate MACD components
            ema_fast = self.calculate_ema(close_prices[-self.fast_period:], self.fast_period)
            ema_slow = self.calculate_ema(close_prices[-self.slow_period:], self.slow_period)
            
            macd_line = ema_fast - ema_slow
            
            # Calculate signal line (EMA of MACD)
            if len(close_prices) >= self.slow_period + self.signal_period:
                macd_values = []
                for i in range(self.signal_period):
                    idx = -(self.signal_period - i)
                    fast = self.calculate_ema(close_prices[:idx] if idx < 0 else close_prices, self.fast_period)
                    slow = self.calculate_ema(close_prices[:idx] if idx < 0 else close_prices, self.slow_period)
                    macd_values.append(fast - slow)
                
                signal_line = self.calculate_ema(np.array(macd_values), self.signal_period)
                
                # Previous values for crossover detection
                if len(macd_values) >= 2:
                    prev_macd = macd_values[-2]
                    prev_signal = self.calculate_ema(np.array(macd_values[:-1]), self.signal_period)
                    
                    signal = None
                    
                    # MACD crosses above signal line = BUY
                    if prev_macd <= prev_signal and macd_line > signal_line:
                        signal = {
                            'type': 'BUY',
                            'price': current_price,
                            'confidence': 0.85,
                            'strategy': self.name,
                            'macd': macd_line,
                            'signal_line': signal_line,
                            'reason': 'MACD Bullish Crossover'
                        }
                        log.info(f"🚀 MACD BUY: MACD {macd_line:.4f} crossed above signal {signal_line:.4f}")
                    
                    # MACD crosses below signal line = SELL
                    elif prev_macd >= prev_signal and macd_line < signal_line:
                        signal = {
                            'type': 'SELL',
                            'price': current_price,
                            'confidence': 0.85,
                            'strategy': self.name,
                            'macd': macd_line,
                            'signal_line': signal_line,
                            'reason': 'MACD Bearish Crossover'
                        }
                        log.info(f"🔻 MACD SELL: MACD {macd_line:.4f} crossed below signal {signal_line:.4f}")
                    
                    return signal
            
            return None
            
        except Exception as e:
            log.error(f"Error in MACD analysis: {e}")
            return None

class StochasticStrategy(BaseStrategy):
    """Stochastic Oscillator Strategy - Momentum indicator"""
    
    def __init__(self, symbol: str = "ETHUSD", k_period: int = 14, d_period: int = 3, oversold: float = 20, overbought: float = 80):
        super().__init__(symbol)
        self.name = "stochastic_strategy"
        self.k_period = k_period
        self.d_period = d_period
        self.oversold = oversold
        self.overbought = overbought
        
    def analyze(self, rates: np.ndarray) -> Optional[Dict]:
        """Generate signals based on Stochastic levels"""
        try:
            if len(rates) < self.k_period + self.d_period:
                return None
                
            # Get price data
            high_prices = np.array([rate[2] for rate in rates[-self.k_period:]])
            low_prices = np.array([rate[3] for rate in rates[-self.k_period:]])
            close_prices = np.array([rate[4] for rate in rates])
            current_price = close_prices[-1]
            
            # Calculate %K
            highest_high = np.max(high_prices)
            lowest_low = np.min(low_prices)
            
            if highest_high == lowest_low:
                return None
                
            k_percent = 100 * (current_price - lowest_low) / (highest_high - lowest_low)
            
            # Calculate %D (SMA of %K)
            if len(close_prices) >= self.k_period + self.d_period:
                k_values = []
                for i in range(self.d_period):
                    idx = -(self.d_period - i)
                    period_high = np.max([rate[2] for rate in rates[idx-self.k_period:idx if idx < 0 else len(rates)]])
                    period_low = np.min([rate[3] for rate in rates[idx-self.k_period:idx if idx < 0 else len(rates)]])
                    period_close = rates[idx][4] if idx < 0 else rates[-1][4]
                    
                    if period_high != period_low:
                        k_val = 100 * (period_close - period_low) / (period_high - period_low)
                        k_values.append(k_val)
                
                if len(k_values) >= self.d_period:
                    d_percent = np.mean(k_values[-self.d_period:])
                    
                    signal = None
                    
                    # Oversold condition + %K crosses above %D = BUY
                    if k_percent < self.oversold and k_percent > d_percent:
                        signal = {
                            'type': 'BUY',
                            'price': current_price,
                            'confidence': 0.75,
                            'strategy': self.name,
                            'k_percent': k_percent,
                            'd_percent': d_percent,
                            'reason': f'Stochastic oversold ({k_percent:.1f}%)'
                        }
                        log.info(f"📉 STOCHASTIC BUY: %K {k_percent:.1f}% oversold, above %D {d_percent:.1f}%")
                    
                    # Overbought condition + %K crosses below %D = SELL
                    elif k_percent > self.overbought and k_percent < d_percent:
                        signal = {
                            'type': 'SELL',
                            'price': current_price,
                            'confidence': 0.75,
                            'strategy': self.name,
                            'k_percent': k_percent,
                            'd_percent': d_percent,
                            'reason': f'Stochastic overbought ({k_percent:.1f}%)'
                        }
                        log.info(f"📈 STOCHASTIC SELL: %K {k_percent:.1f}% overbought, below %D {d_percent:.1f}%")
                    
                    return signal
            
            return None
            
        except Exception as e:
            log.error(f"Error in Stochastic analysis: {e}")
            return None

class VolumeWeightedStrategy(BaseStrategy):
    """Volume Weighted Average Price (VWAP) Strategy"""
    
    def __init__(self, symbol: str = "ETHUSD", period: int = 20, threshold: float = 0.002):
        super().__init__(symbol)
        self.name = "vwap_strategy"
        self.period = period
        self.threshold = threshold  # 0.2% threshold
        
    def analyze(self, rates: np.ndarray) -> Optional[Dict]:
        """Generate signals based on price vs VWAP"""
        try:
            if len(rates) < self.period:
                return None
                
            recent_rates = rates[-self.period:]
            
            # Calculate VWAP
            total_volume_price = 0
            total_volume = 0
            
            for rate in recent_rates:
                typical_price = (rate[2] + rate[3] + rate[4]) / 3  # (H+L+C)/3
                volume = rate[5] if len(rate) > 5 else 1000  # Use tick volume or default
                total_volume_price += typical_price * volume
                total_volume += volume
            
            if total_volume == 0:
                return None
                
            vwap = total_volume_price / total_volume
            current_price = rates[-1][4]
            
            # Calculate price deviation from VWAP
            deviation = (current_price - vwap) / vwap
            
            signal = None
            
            # Price significantly below VWAP = BUY signal
            if deviation < -self.threshold:
                signal = {
                    'type': 'BUY',
                    'price': current_price,
                    'confidence': 0.8,
                    'strategy': self.name,
                    'vwap': vwap,
                    'deviation': deviation * 100,
                    'reason': f'Price {deviation*100:.2f}% below VWAP'
                }
                log.info(f"📉 VWAP BUY: Price {current_price:.2f} is {deviation*100:.2f}% below VWAP {vwap:.2f}")
            
            # Price significantly above VWAP = SELL signal
            elif deviation > self.threshold:
                signal = {
                    'type': 'SELL',
                    'price': current_price,
                    'confidence': 0.8,
                    'strategy': self.name,
                    'vwap': vwap,
                    'deviation': deviation * 100,
                    'reason': f'Price {deviation*100:.2f}% above VWAP'
                }
                log.info(f"📈 VWAP SELL: Price {current_price:.2f} is {deviation*100:.2f}% above VWAP {vwap:.2f}")
            
            return signal
            
        except Exception as e:
            log.error(f"Error in VWAP analysis: {e}")
            return None

# ============================================================================

# Strategy factory
AVAILABLE_STRATEGIES = {
    'ma_crossover': MovingAverageCrossover,
    'moving_average': MovingAverageCrossover,  # Add frontend mapping
    'rsi_strategy': RSIStrategy,
    'breakout_strategy': BreakoutStrategy,
    'combined_strategy': CombinedStrategy,
    'bollinger_bands': BollingerBandsStrategy,  # Map to breakout for now
    'macd_strategy': MACDStrategy,  # New MACD strategy
    'stochastic_strategy': StochasticStrategy,  # New Stochastic strategy  
    'vwap_strategy': VolumeWeightedStrategy,  # New VWAP strategy
    'test_strategy': TestStrategy,  # Test strategy for debugging
    'always_signal': AlwaysSignalStrategy,  # Always generates signals
    'default': AlwaysSignalStrategy  # Default to always signal for testing
}

def get_strategy(strategy_name: str, symbol: str = "ETHUSD") -> BaseStrategy:
    """Get strategy instance by name"""
    strategy_class = AVAILABLE_STRATEGIES.get(strategy_name, MovingAverageCrossover)
    return strategy_class(symbol)

def list_strategies() -> List[str]:
    """Get list of available strategy names"""
    return list(AVAILABLE_STRATEGIES.keys())