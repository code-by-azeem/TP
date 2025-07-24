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
        
        # Log current configuration for debugging
        log.info(f"Bot Config: auto_trading={self.config['auto_trading_enabled']}, risk={self.config['max_risk_per_trade']}")
        
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
        log.info("🤖 Bot loop started")
        log.info(f"🔧 Initial Bot Config: auto_trading={self.config['auto_trading_enabled']}, strategy={self.config['strategy_name']}")
        
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
                
                # Log signal analysis for debugging
                if signal:
                    log.info(f"🎯 SIGNAL GENERATED: {signal['type']} at {signal['price']} - {signal.get('reason', 'No reason')}")
                    if self.config['auto_trading_enabled']:
                        log.info("✅ Auto trading enabled - executing trade")
                        self._execute_trade(signal)
                    else:
                        log.warning("⚠️ Auto trading DISABLED - skipping trade execution")
                else:
                    # Log every 10 iterations to avoid spam
                    if hasattr(self, '_no_signal_counter'):
                        self._no_signal_counter += 1
                    else:
                        self._no_signal_counter = 1
                    
                    if self._no_signal_counter % 10 == 0:
                        log.info(f"📊 No signal generated (checked {self._no_signal_counter} times) - auto_trading: {self.config['auto_trading_enabled']}")
                    
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
                log.error(f"❌ Error in bot loop: {e}")
                time.sleep(5)
                
        log.info("🤖 Bot loop ended")
        
    def _analyze_market(self) -> Optional[Dict]:
        """Analyze market conditions and generate trading signals"""
        try:
            # Get recent candle data
            rates = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_M1, 0, 100)
            if rates is None or len(rates) < 50:
                log.warning(f"⚠️ Insufficient candle data: {len(rates) if rates is not None else 0} candles (need 50+)")
                return None
            
            # Get the current strategy
            strategy = get_strategy(self.config['strategy_name'], self.symbol)
            log.info(f"📈 Using strategy: {strategy.name} for {self.config['strategy_name']} with {len(rates)} candles")
            
            # Analyze using the selected strategy
            signal = strategy.analyze(rates)
            
            if signal:
                log.info(f"🎯 Strategy {strategy.name} generated signal: {signal}")
            else:
                log.debug(f"📊 Strategy {strategy.name} - no signal")
            
            return signal
            
        except Exception as e:
            log.error(f"❌ Error in market analysis: {e}")
            return None
            
    def _execute_trade(self, signal: Dict):
        """Execute a trade based on the signal"""
        if not self.config['auto_trading_enabled']:
            log.info(f"Auto trading disabled, signal: {signal}")
            return
            
        try:
            log.info(f"Executing trade: {signal}")
            
            # Calculate position size based on risk management
            account_info = mt5.account_info()
            if account_info is None:
                log.error("❌ Failed to get account info")
                return
                
            account_balance = account_info.balance
            log.info(f"💰 Account balance: ${account_balance}")
            
            # Calculate risk amount
            risk_amount = account_balance * (self.config['max_risk_per_trade'] / 100.0)
            log.info(f"💸 Risk amount: ${risk_amount}")
            
            # Get symbol info for pip value calculation
            symbol_info = mt5.symbol_info(self.symbol)
            if symbol_info is None:
                log.error(f"❌ Failed to get symbol info for {self.symbol}")
                return
                
            # Calculate lot size - MUCH MORE CONSERVATIVE
            # For ETHUSD: 1 lot = 1 ETH, price ~$3740, so 1 lot = $3740
            # Use a small fixed lot size for testing, then implement proper risk calc
            if account_balance < 1000:
                lot_size = 0.01  # Micro lot for small accounts
            elif account_balance < 5000:
                lot_size = 0.1   # Mini lot
            else:
                # Risk-based calculation but capped
                price_per_lot = signal['price']  # For ETHUSD, 1 lot = price in USD
                max_lots_by_balance = account_balance * 0.02 / price_per_lot  # Max 2% of balance
                risk_lots = risk_amount / (self.config['stop_loss_pips'] * 0.1)  # Assuming $0.1 per pip
                lot_size = min(max_lots_by_balance, risk_lots, 1.0)  # Cap at 1 lot max
                
            # Ensure minimum lot size and round properly
            lot_size = max(0.01, round(lot_size, 2))
            log.info(f"📊 Calculated lot size: {lot_size} (Balance: ${account_balance}, Risk: {self.config['max_risk_per_trade']}%)")

            # Determine order type and get current price
            order_type = mt5.ORDER_TYPE_BUY if signal['type'] == 'BUY' else mt5.ORDER_TYPE_SELL
            
            # Get current price
            current_tick = mt5.symbol_info_tick(self.symbol)
            if not current_tick:
                log.error(f"Cannot get current price for {self.symbol}")
                return
                
            current_price = current_tick.ask if signal['type'] == 'BUY' else current_tick.bid
            log.info(f"💱 Current market price: {current_price} (signal price was: {signal['price']})")

            # Calculate stop loss and take profit prices
            # For ETHUSD, 1 pip = 0.01, so we need to multiply by 10 * point
            pip_size = 10 * symbol_info.point  # Correct pip calculation for ETHUSD
            min_distance = max(20 * pip_size, symbol_info.trade_stops_level * symbol_info.point)  # Minimum 20 pips or broker requirement
            
            if signal['type'] == 'BUY':
                sl_price = current_price - max(self.config['stop_loss_pips'] * pip_size, min_distance) if self.config['stop_loss_pips'] > 0 else 0
                tp_price = current_price + max(self.config['take_profit_pips'] * pip_size, min_distance) if self.config['take_profit_pips'] > 0 else 0
            else:  # SELL
                sl_price = current_price + max(self.config['stop_loss_pips'] * pip_size, min_distance) if self.config['stop_loss_pips'] > 0 else 0
                tp_price = current_price - max(self.config['take_profit_pips'] * pip_size, min_distance) if self.config['take_profit_pips'] > 0 else 0
            
            log.info(f"📊 Pip calculation: pip_size={pip_size}, min_distance={min_distance}, stops_level={symbol_info.trade_stops_level}")

            # Prepare the trade request with safe comment
            safe_comment = f"TradePulse_{signal['type']}"[:31]  # MT5 comment limit is 31 chars

            # Try different filling modes and SL/TP combinations
            filling_modes = [
                mt5.ORDER_FILLING_RETURN,  # OANDA standard
                mt5.ORDER_FILLING_IOC,     # Immediate or Cancel
                mt5.ORDER_FILLING_FOK      # Fill or Kill
            ]

            # Try with SL/TP first, then without if it fails
            sl_tp_configs = [
                {'sl': sl_price, 'tp': tp_price, 'description': 'with SL/TP'},
                {'description': 'without SL/TP (market order only)'}  # No sl/tp keys at all
            ]

            result = None
            for sl_tp_config in sl_tp_configs:
                for filling_mode in filling_modes:
                    # Base request
                    request = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": self.symbol,
                        "volume": lot_size,
                        "type": order_type,
                        "price": current_price,
                        "deviation": 20,
                        "magic": 234000,  # EA magic number
                        "comment": safe_comment,
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": filling_mode,
                    }
                    
                    # Add SL/TP only if they exist in config and are > 0
                    if 'sl' in sl_tp_config and sl_tp_config['sl'] > 0:
                        request['sl'] = sl_tp_config['sl']
                    if 'tp' in sl_tp_config and sl_tp_config['tp'] > 0:
                        request['tp'] = sl_tp_config['tp']
                    
                    log.info(f"📤 Trying order {sl_tp_config['description']} with filling mode {filling_mode}: {signal['type']} {lot_size} {self.symbol} at {current_price}")
                    log.info(f"📋 Order request: {request}")
                    
                    # Send the trade request
                    result = mt5.order_send(request)
                    
                    if result is None:
                        error_info = mt5.last_error()
                        log.error(f"❌ Order send failed with filling {filling_mode}: {error_info}")
                        continue  # Try next filling mode
                        
                    # Check if order was successful
                    if result.retcode == mt5.TRADE_RETCODE_DONE:
                        # SUCCESS!
                        log.info(f"✅ SUCCESS! Order executed {sl_tp_config['description']} with filling mode {filling_mode}")
                        log.info(f"✅ Order executed successfully! Ticket: {result.order}, Volume: {result.volume}, Price: {result.price}")
                        break
                    elif result.retcode == 10030:  # Unsupported filling mode
                        log.warning(f"⚠️ Filling mode {filling_mode} not supported, trying next...")
                        continue
                    elif result.retcode == 10016:  # Invalid stops
                        log.warning(f"⚠️ Invalid stops {sl_tp_config['description']}, trying next configuration...")
                        break  # Try next SL/TP config
                    elif result.retcode == 10019:  # No money
                        log.error(f"💰 INSUFFICIENT FUNDS! Need ~${lot_size * current_price:.2f}, have ${account_balance:.2f}")
                        log.error("🔧 Trying smaller lot size...")
                        # Try with much smaller lot size
                        smaller_lot = max(0.01, lot_size / 10)
                        request['volume'] = smaller_lot
                        log.info(f"📤 Retrying with smaller volume: {smaller_lot}")
                        result = mt5.order_send(request)
                        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                            log.info(f"✅ SUCCESS with smaller lot! Ticket: {result.order}, Volume: {result.volume}")
                            break
                    else:
                        log.error(f"❌ Order failed with retcode: {result.retcode} - {result}")
                        continue
                
                # If we succeeded, break out of both loops
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    break

            # Check final result
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                log.error(f"❌ All order configurations failed. Last result: {result}")
                self._notify_trade_error("All order configurations failed", f"Last retcode: {result.retcode if result else 'None'}")
                return
            
            # Order successful - track it
            trade_id = f"trade_{result.order}"
            self.active_trades[trade_id] = {
                'signal': signal,
                'entry_time': datetime.now(),
                'status': 'active',
                'mt5_ticket': result.order,
                'lot_size': lot_size,
                'entry_price': signal['price'],
                'sl': sl_price,
                'tp': tp_price
            }
            
            # Update performance metrics and log successful trade
            self.performance['total_trades'] += 1
            
            log.info(f"✅ Trade completed! Ticket: {result.order}, Volume: {result.volume}, Price: {result.price}")
            
            # Notify frontend
            self.notify_updates({
                'type': 'trade_executed',
                'trade_id': trade_id,
                'ticket': result.order,
                'signal': signal,
                'volume': result.volume,
                'price': result.price,
                'sl': sl_price,
                'tp': tp_price,
                'timestamp': datetime.now().isoformat()
            })
            
        except Exception as e:
            log.error(f"Error executing trade: {e}")
            self._notify_trade_error("Trade execution error", str(e))
            
    def _notify_trade_error(self, error_type: str, details: str):
        """Notify frontend about trade execution errors"""
        self.notify_updates({
            'type': 'trade_error',
            'error': error_type,
            'details': details,
            'timestamp': datetime.now().isoformat()
        })
            
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
        old_auto_trading = self.config.get('auto_trading_enabled', False)
        self.config.update(new_config)
        new_auto_trading = self.config.get('auto_trading_enabled', False)
        
        log.info(f"🔧 Bot configuration updated: {new_config}")
        log.info(f"📊 Auto trading changed: {old_auto_trading} → {new_auto_trading}")
        log.info(f"🔧 Full config now: {self.config}")
        
        # Notify frontend
        self.notify_updates({
            'type': 'config_update',
            'config': self.config,
            'auto_trading_changed': old_auto_trading != new_auto_trading,
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