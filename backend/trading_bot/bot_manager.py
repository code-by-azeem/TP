"""
Trading Bot Manager - Controls bot operations and integrates with the main application
"""
import logging
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Callable
import MetaTrader5 as mt5
from .strategies import get_strategy, list_strategies

log = logging.getLogger(__name__)

class TradingBotManager:
    def __init__(self, mt5_symbol="ETHUSD"):
        self.symbol = mt5_symbol
        self.is_running = False
        self.strategies = {}
        self.active_trades = {}
        self.bot_thread = None
        self.update_callbacks = []
        
        # Bot configuration
        self.config = {
            'max_risk_per_trade': 0.02,  # 2% risk per trade
            'max_daily_trades': 10,
            'auto_trading_enabled': False,
            'strategy_name': 'default',
            'stop_loss_pips': 50,
            'take_profit_pips': 100
        }
        
        # Performance tracking
        self.performance = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_profit': 0.0,
            'win_rate': 0.0,
            'daily_pnl': 0.0
        }
        
    def register_update_callback(self, callback: Callable):
        """Register callback for bot status updates"""
        self.update_callbacks.append(callback)
        
    def notify_updates(self, data: Dict):
        """Notify all registered callbacks about bot updates"""
        for callback in self.update_callbacks:
            try:
                callback(data)
            except Exception as e:
                log.error(f"Error in update callback: {e}")
    
    def start_bot(self, strategy_name: str = "default"):
        """Start the trading bot"""
        if self.is_running:
            log.warning("Bot is already running")
            return False
            
        if not mt5.initialize():
            log.error("Failed to initialize MT5 for bot")
            return False
            
        log.info(f"Starting trading bot with strategy: {strategy_name}")
        self.is_running = True
        self.config['strategy_name'] = strategy_name
        
        # Start bot in separate thread
        self.bot_thread = threading.Thread(target=self._bot_loop, daemon=True)
        self.bot_thread.start()
        
        # Notify frontend about bot start
        self.notify_updates({
            'type': 'bot_status',
            'status': 'started',
            'strategy': strategy_name,
            'timestamp': datetime.now().isoformat()
        })
        
        return True
        
    def stop_bot(self):
        """Stop the trading bot"""
        if not self.is_running:
            log.warning("Bot is not running")
            return False
            
        log.info("Stopping trading bot...")
        self.is_running = False
        
        if self.bot_thread and self.bot_thread.is_alive():
            self.bot_thread.join(timeout=5)
            
        # Notify frontend about bot stop
        self.notify_updates({
            'type': 'bot_status',
            'status': 'stopped',
            'timestamp': datetime.now().isoformat()
        })
        
        return True
        
    def _bot_loop(self):
        """Main bot execution loop"""
        log.info("Bot loop started")
        
        while self.is_running:
            try:
                # Get current market data
                current_tick = mt5.symbol_info_tick(self.symbol)
                if not current_tick:
                    log.warning(f"No tick data for {self.symbol}")
                    time.sleep(1)
                    continue
                    
                # Check for trading signals
                signal = self._analyze_market()
                
                if signal and self.config['auto_trading_enabled']:
                    self._execute_trade(signal)
                    
                # Update performance metrics
                self._update_performance()
                
                # Notify frontend with updates
                self.notify_updates({
                    'type': 'bot_update',
                    'current_price': current_tick.bid,
                    'signal': signal,
                    'performance': self.performance,
                    'active_trades': len(self.active_trades),
                    'timestamp': datetime.now().isoformat()
                })
                
                time.sleep(1)  # Main loop interval
                
            except Exception as e:
                log.error(f"Error in bot loop: {e}")
                time.sleep(5)
                
        log.info("Bot loop ended")
        
    def _analyze_market(self) -> Optional[Dict]:
        """Analyze market conditions and generate trading signals"""
        try:
            # Get recent candle data
            rates = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_M1, 0, 100)
            if rates is None or len(rates) < 50:
                return None
            
            # Get the current strategy
            strategy = get_strategy(self.config['strategy_name'], self.symbol)
            
            # Analyze using the selected strategy
            signal = strategy.analyze(rates)
            
            return signal
            
        except Exception as e:
            log.error(f"Error in market analysis: {e}")
            return None
            
    def _execute_trade(self, signal: Dict):
        """Execute a trade based on the signal"""
        if not self.config['auto_trading_enabled']:
            log.info(f"Auto trading disabled, signal: {signal}")
            return
            
        try:
            # Implement your trade execution logic here
            # This is a placeholder
            log.info(f"Executing trade: {signal}")
            
            # Update active trades
            trade_id = f"trade_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.active_trades[trade_id] = {
                'signal': signal,
                'entry_time': datetime.now(),
                'status': 'active'
            }
            
            # Notify frontend
            self.notify_updates({
                'type': 'new_trade',
                'trade_id': trade_id,
                'signal': signal,
                'timestamp': datetime.now().isoformat()
            })
            
        except Exception as e:
            log.error(f"Error executing trade: {e}")
            
    def _update_performance(self):
        """Update bot performance metrics"""
        # Calculate performance metrics based on active/closed trades
        # This is a placeholder implementation
        total_trades = len(self.active_trades)
        self.performance.update({
            'total_trades': total_trades,
            'active_trades': len([t for t in self.active_trades.values() if t['status'] == 'active']),
            'last_update': datetime.now().isoformat()
        })
        
    def get_bot_status(self) -> Dict:
        """Get current bot status"""
        return {
            'is_running': self.is_running,
            'strategy': self.config['strategy_name'],
            'auto_trading': self.config['auto_trading_enabled'],
            'performance': self.performance,
            'active_trades': len(self.active_trades),
            'config': self.config
        }
        
    def update_config(self, new_config: Dict):
        """Update bot configuration"""
        self.config.update(new_config)
        log.info(f"Bot configuration updated: {new_config}")
        
        # Notify frontend
        self.notify_updates({
            'type': 'config_update',
            'config': self.config,
            'timestamp': datetime.now().isoformat()
        })
        
    def add_strategy(self, name: str, strategy_func: Callable):
        """Add a new trading strategy"""
        self.strategies[name] = strategy_func
        log.info(f"Strategy '{name}' added to bot")
        
    def get_available_strategies(self) -> List[str]:
        """Get list of available strategies"""
        return list_strategies()

# Global bot manager instance
bot_manager = TradingBotManager()