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
        self.bot_id = None  # Track which bot this manager belongs to
        self.unique_magic_number = None  # Unique magic number for this bot instance
        self.bot_start_time = None  # When this bot instance started
        
        # PERSISTENT performance tracking - survives trade closures
        self.lifetime_stats = {
            'total_completed_trades': 0,
            'total_winning_trades': 0,
            'total_losing_trades': 0,
            'lifetime_realized_profit': 0.0,
            'lifetime_max_drawdown': 0.0,
            'peak_balance': 0.0,
            'completed_trade_history': [],  # Store completed trades
            'daily_stats': {}  # Track daily performance
        }
        
        # Bot configuration
        self.config = {
            'max_risk_per_trade': 0.02,  # 2% risk per trade
            'max_daily_trades': 10,
            'auto_trading_enabled': False,
            'strategy_name': 'default',
            'stop_loss_pips': 50,
            'take_profit_pips': 100
        }
        
        # Performance tracking - start fresh for each bot instance
        self.performance = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_profit': 0.0,
            'win_rate': 0.0,
            'daily_pnl': 0.0,
            'unrealized_pnl': 0.0,
            'total_pnl': 0.0,
            'max_drawdown': 0.0,
            'active_trades': 0,
            'recent_trades': []
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
    
    def start_bot(self, strategy_name: str = "default", bot_id: str = None):
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
        self.bot_id = bot_id  # Store bot ID
        
        # Generate unique magic number for this bot instance
        self.unique_magic_number = self._generate_unique_magic_number()
        
        # Set bot start time for tracking purposes
        self.bot_start_time = datetime.now()
        
        # Reset performance metrics for this new bot instance
        self.performance = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_profit': 0.0,
            'win_rate': 0.0,
            'daily_pnl': 0.0,
            'unrealized_pnl': 0.0,
            'total_pnl': 0.0,
            'max_drawdown': 0.0,
            'active_trades': 0,
            'recent_trades': [],
            'last_update': datetime.now().isoformat()
        }
        
        # Log current configuration for debugging
        log.info(f"Bot Config: auto_trading={self.config['auto_trading_enabled']}, risk={self.config['max_risk_per_trade']}")
        log.info(f"Bot {self.bot_id} assigned magic number: {self.unique_magic_number}")
        
        # Start bot in separate thread
        self.bot_thread = threading.Thread(target=self._bot_loop, daemon=True)
        self.bot_thread.start()
        
        # Notify frontend about bot start
        self.notify_updates({
            'type': 'bot_status',
            'status': 'started',
            'strategy': strategy_name,
            'bot_id': self.bot_id,
            'magic_number': self.unique_magic_number,
            'start_time': self.bot_start_time.isoformat(),
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
            'bot_id': self.bot_id,
            'timestamp': datetime.now().isoformat()
        })
        
        return True
        
    def _bot_loop(self):
        """Main bot execution loop"""
        log.info("🤖 Bot loop started")
        log.info(f"🔧 Initial Bot Config: auto_trading={self.config['auto_trading_enabled']}, strategy={self.config['strategy_name']}")
        
        last_trade_minute = 0  # Track the last minute when trade was attempted
        last_performance_update = 0  # Track last performance update
        
        while self.is_running:
            try:
                # Get current market data
                current_tick = mt5.symbol_info_tick(self.symbol)
                if not current_tick:
                    log.warning(f"No tick data for {self.symbol}")
                    time.sleep(1)
                    continue
                
                # Get current minute to control trade frequency
                current_time = time.time()
                current_minute = int(current_time // 60)  # Convert to minute intervals
                
                # Only analyze and potentially trade once per minute
                should_analyze = current_minute > last_trade_minute
                
                if should_analyze:
                    # Check for trading signals
                    signal = self._analyze_market()
                    
                    # Log signal analysis for debugging
                    if signal:
                        log.info(f"🎯 SIGNAL GENERATED: {signal['type']} at {signal['price']} - {signal.get('reason', 'No reason')}")
                        if self.config['auto_trading_enabled']:
                            log.info("✅ Auto trading enabled - executing trade")
                            self._execute_trade(signal)
                            last_trade_minute = current_minute  # Update last trade minute
                            
                            # IMMEDIATE performance update after trade execution
                            self._update_performance()
                            
                        else:
                            log.warning("⚠️ Auto trading DISABLED - skipping trade execution")
                            last_trade_minute = current_minute  # Still update to avoid spam
                    else:
                        # Log once per minute when no signal
                        log.info(f"📊 No signal generated at minute {current_minute} - auto_trading: {self.config['auto_trading_enabled']}")
                        last_trade_minute = current_minute
                
                # Update performance metrics more frequently (every 10 seconds instead of every minute)
                performance_update_interval = 10  # seconds
                if current_time - last_performance_update >= performance_update_interval:
                    self._update_performance()
                    last_performance_update = current_time
                
                # Always notify frontend with updates (for responsive UI)
                self.notify_updates({
                    'type': 'bot_update',
                    'bot_id': self.bot_id,
                    'current_price': current_tick.bid,
                    'signal': signal if should_analyze else None,
                    'performance': self.performance,  # Always include complete performance data
                    'active_trades': self.performance.get('active_trades', 0),  # Use performance data
                    'timestamp': datetime.now().isoformat(),
                    'next_analysis_in': 60 - int(current_time % 60)  # Seconds until next analysis
                })
                
                time.sleep(1)  # Keep 1-second loop for responsive UI updates
                
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

            # Prepare the trade request with safe comment and unique magic number
            safe_comment = f"TradePulse_{self.bot_id}_{signal['type']}"[:31]  # MT5 comment limit is 31 chars

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
                        "magic": self.unique_magic_number,  # Use bot-specific magic number
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
            
            # IMMEDIATELY update performance after successful trade
            log.info(f"✅ Trade completed! Ticket: {result.order}, Volume: {result.volume}, Price: {result.price}")
            
            # Force immediate performance update
            self._update_performance()
            
            # Notify frontend with updated performance
            self.notify_updates({
                'type': 'trade_executed',
                'bot_id': self.bot_id,
                'trade_id': trade_id,
                'ticket': result.order,
                'signal': signal,
                'volume': result.volume,
                'price': result.price,
                'sl': sl_price,
                'tp': tp_price,
                # 'performance': self.performance,  # Include updated performance
                'strategy': self.config.get('strategy_name'),
                'magic_number': self.unique_magic_number,
                'user_id': getattr(self, 'owner_user_id', None),   # set when starting bot (see below)
                'config_snapshot': {
                    'max_risk_per_trade': self.config.get('max_risk_per_trade'),
                    'trade_size_usd':     self.config.get('trade_size_usd'),
                    'leverage':           self.config.get('leverage'),
                    'asset_type':         self.config.get('asset_type'),

                    'risk_reward_ratio':  self.config.get('risk_reward_ratio'),
                    'stop_loss_pips':     self.config.get('stop_loss_pips'),
                    'take_profit_pips':   self.config.get('take_profit_pips'),
                    'max_loss_threshold': self.config.get('max_loss_threshold'),

                    'entry_trigger':      self.config.get('entry_trigger'),
                    'exit_trigger':       self.config.get('exit_trigger'),
                    'max_daily_trades':   self.config.get('max_daily_trades'),
                    'time_window':        self.config.get('time_window'),

                    'rsi_period':             self.config.get('rsi_period'),
                    'moving_average_period':  self.config.get('moving_average_period'),
                    'bollinger_bands_period': self.config.get('bollinger_bands_period'),
                    'bb_deviation':           self.config.get('bb_deviation'),

                    'auto_stop_enabled':      self.config.get('auto_stop_enabled'),
                    'max_consecutive_losses': self.config.get('max_consecutive_losses'),
                    'auto_trading_enabled':   self.config.get('auto_trading_enabled'),},
                'timestamp': datetime.now().isoformat()
            })
            
        except Exception as e:
            log.error(f"Error executing trade: {e}")
            self._notify_trade_error("Trade execution error", str(e))
            
    def _notify_trade_error(self, error_type: str, details: str):
        """Notify frontend about trade execution errors"""
        self.notify_updates({
            'type': 'trade_error',
            'bot_id': self.bot_id,
            'error': error_type,
            'details': details,
            'timestamp': datetime.now().isoformat()
        })
            
    def _update_performance(self):
        """Update bot performance metrics based on ONLY this bot's trades"""
        try:
            # Skip if bot hasn't been properly initialized
            if not self.unique_magic_number or not self.bot_start_time:
                log.debug(f"Bot {self.bot_id} not fully initialized for performance tracking")
                return
                
            # Get actual account info
            if not mt5.initialize():
                log.warning("MT5 not initialized for performance update")
                return
                
            # Get account info for general data
            account_info = mt5.account_info()
            if account_info:
                current_balance = account_info.balance
                current_equity = account_info.equity
                
                # Update performance with real account data
                self.performance.update({
                    'account_balance': current_balance,
                    'account_equity': current_equity,
                    'floating_pnl': current_equity - current_balance
                })
            
            # Get trade history ONLY from when this bot started (not all history)
            from datetime import timedelta
            
            # Get deals from bot start time to now - this ensures we only get THIS bot's trades
            deals = mt5.history_deals_get(self.bot_start_time, datetime.now())
            bot_specific_trades = []
            
            log.debug(f"Checking deals from {self.bot_start_time} for bot {self.bot_id} with magic {self.unique_magic_number}")
            
            if deals:
                for deal in deals:
                    magic_number = getattr(deal, 'magic', 0)
                    comment = getattr(deal, 'comment', '')
                    deal_type = getattr(deal, 'type', -1)
                    
                    # STRICT filtering: ONLY this bot's trades
                    is_this_bot_trade = (
                        magic_number == self.unique_magic_number or  # Bot's unique magic number
                        (f"TradePulse_{self.bot_id}" in comment and magic_number >= 234000)  # Bot-specific comment only
                    )
                    
                    # Only include actual trade deals (not balance operations)
                    if is_this_bot_trade and deal_type in [0, 1]:  # BUY or SELL deals
                        profit = getattr(deal, 'profit', 0)
                        commission = getattr(deal, 'commission', 0)
                        swap = getattr(deal, 'swap', 0)
                        net_profit = profit + commission + swap
                        
                        bot_specific_trades.append({
                            'ticket': getattr(deal, 'ticket', 0),
                            'position_id': getattr(deal, 'position_id', 0),
                            'time': datetime.fromtimestamp(getattr(deal, 'time', 0)),
                            'type': 'BUY' if deal_type == 0 else 'SELL',
                            'volume': getattr(deal, 'volume', 0),
                            'price': getattr(deal, 'price', 0),
                            'profit': net_profit,
                            'raw_profit': profit,
                            'commission': commission,
                            'swap': swap,
                            'magic': magic_number,
                            'comment': comment
                        })
                        
                        log.debug(f"Found bot trade: ticket={getattr(deal, 'ticket', 0)}, "
                                f"magic={magic_number}, profit={net_profit:.2f}, comment={comment}")
            
            # If no bot-specific trades found, try fallback method for recent TradePulse trades
            if len(bot_specific_trades) == 0:
                log.info(f"No specific trades found for bot {self.bot_id}, trying fallback method...")
                fallback_trades = self._find_recent_bot_trades_fallback()
                if fallback_trades:
                    # Use fallback trades but limit to reasonable number
                    bot_specific_trades = fallback_trades[:10]  # Max 10 recent trades
                    log.info(f"Using {len(bot_specific_trades)} fallback trades for bot {self.bot_id}")
            
            # Detect newly completed trades first
            self._detect_completed_trades(bot_specific_trades)
            
            # Group deals by position_id to count actual completed trades (not individual deals)
            position_groups = {}
            for trade in bot_specific_trades:
                pos_id = trade['position_id']
                if pos_id not in position_groups:
                    position_groups[pos_id] = []
                position_groups[pos_id].append(trade)
            
            # Calculate metrics from completed positions
            completed_trades = []
            for pos_id, trades in position_groups.items():
                if len(trades) >= 2:  # Position opened and closed
                    # Calculate total profit for this position
                    total_profit = sum(t['profit'] for t in trades)
                    # Use the last trade for timing (close)
                    last_trade = max(trades, key=lambda x: x['time'])
                    completed_trades.append({
                        'position_id': pos_id,
                        'profit': total_profit,
                        'time': last_trade['time'],
                        'type': last_trade['type'],
                        'volume': last_trade['volume'],
                        'price': last_trade['price']
                    })
                elif len(trades) == 1:
                    # Single deal - might be a closing deal or instant execution
                    trade = trades[0]
                    if trade['profit'] != 0:  # Has profit/loss, so it's a completed trade
                        completed_trades.append({
                            'position_id': pos_id,
                            'profit': trade['profit'],
                            'time': trade['time'],
                            'type': trade['type'],
                            'volume': trade['volume'],
                            'price': trade['price']
                        })
            
            # COMBINE lifetime stats with current session stats for complete picture
            total_trades = self.lifetime_stats['total_completed_trades'] + len(completed_trades)
            winning_trades = self.lifetime_stats['total_winning_trades'] + len([t for t in completed_trades if t['profit'] > 0])
            losing_trades = self.lifetime_stats['total_losing_trades'] + len([t for t in completed_trades if t['profit'] < 0])
            session_profit = sum(t['profit'] for t in completed_trades)
            total_realized_profit = self.lifetime_stats['lifetime_realized_profit'] + session_profit
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # Calculate daily P&L (from lifetime stats for today)
            today = datetime.now().strftime('%Y-%m-%d')
            daily_pnl = 0.0
            if today in self.lifetime_stats['daily_stats']:
                daily_pnl = self.lifetime_stats['daily_stats'][today]['profit']
            
            # Add session profit to daily P&L
            daily_pnl += session_profit
            
            # Calculate max drawdown (combine lifetime and session)
            session_running_pnl = 0
            session_peak = 0
            session_max_drawdown = 0
            
            for trade in sorted(completed_trades, key=lambda x: x['time']):
                session_running_pnl += trade['profit']
                if session_running_pnl > session_peak:
                    session_peak = session_running_pnl
                drawdown = session_peak - session_running_pnl
                if drawdown > session_max_drawdown:
                    session_max_drawdown = drawdown
            
            max_drawdown = max(self.lifetime_stats['lifetime_max_drawdown'], session_max_drawdown)
            
            # Get open positions for THIS bot only
            open_positions = mt5.positions_get()
            if open_positions is None:
                open_positions = []
            
            log.debug(f"Total open positions in MT5: {len(open_positions)}")
            
            # Filter positions by THIS bot's magic number OR bot-specific comment
            bot_positions = []
            for pos in open_positions:
                pos_magic = getattr(pos, 'magic', 0)
                pos_comment = getattr(pos, 'comment', '')
                pos_ticket = getattr(pos, 'ticket', 0)
                pos_profit = getattr(pos, 'profit', 0)
                
                # STRICT position filtering - ONLY this bot's trades
                belongs_to_bot = (
                    pos_magic == self.unique_magic_number or 
                    (f"TradePulse_{self.bot_id}" in pos_comment and pos_magic >= 234000)
                )
                
                if belongs_to_bot:
                    bot_positions.append(pos)
                    log.info(f"Found bot position: ticket={pos_ticket}, magic={pos_magic}, "
                           f"profit={pos_profit:.2f}, comment='{pos_comment}'")
                else:
                    log.debug(f"Skipped position: ticket={pos_ticket}, magic={pos_magic}, comment='{pos_comment}'")
            
            log.info(f"Bot {self.bot_id} has {len(bot_positions)} open positions out of {len(open_positions)} total")
            
            # Calculate unrealized P&L from THIS bot's open positions
            unrealized_pnl = 0
            for pos in bot_positions:
                profit = getattr(pos, 'profit', 0)
                commission = getattr(pos, 'commission', 0)
                swap = getattr(pos, 'swap', 0)
                unrealized_pnl += profit + commission + swap
            
            # Update performance with COMBINED lifetime + session data
            self.performance.update({
                'total_trades': total_trades,  # Lifetime + session
                'winning_trades': winning_trades,  # Lifetime + session
                'losing_trades': losing_trades,  # Lifetime + session
                'total_profit': round(total_realized_profit, 2),  # Lifetime + session realized
                'daily_pnl': round(daily_pnl, 2),  # Today's total
                'win_rate': round(win_rate, 1),  # Combined win rate
                'max_drawdown': round(max_drawdown, 2),  # Combined max drawdown
                'active_trades': len(bot_positions),  # Current open positions
                'unrealized_pnl': round(unrealized_pnl, 2),  # Current unrealized
                'total_pnl': round(total_realized_profit + unrealized_pnl, 2),  # Total realized + unrealized
                'last_update': datetime.now().isoformat(),
                'magic_number': self.unique_magic_number,  # For debugging
                'bot_start_time': self.bot_start_time.isoformat(),  # For reference
                'lifetime_stats': {  # Include lifetime stats for frontend
                    'completed_trades': self.lifetime_stats['total_completed_trades'],
                    'lifetime_profit': self.lifetime_stats['lifetime_realized_profit'],
                    'lifetime_winning': self.lifetime_stats['total_winning_trades'],
                    'lifetime_losing': self.lifetime_stats['total_losing_trades']
                }
            })
            
            # Store recent trades for frontend display (combine lifetime + session)
            all_recent_trades = []
            
            # Add completed trades from lifetime stats
            for trade in self.lifetime_stats['completed_trade_history'][-5:]:  # Last 5 lifetime trades
                all_recent_trades.append({
                    'ticket': trade['ticket'],
                    'time': trade['time'].isoformat() if isinstance(trade['time'], datetime) else trade['time'],
                    'type': trade['type'],
                    'volume': trade['volume'],
                    'price': trade['price'],
                    'profit': trade['profit'],
                    'bot_id': trade['bot_id']
                })
            
            # Add current session trades
            session_trades = sorted(bot_specific_trades, key=lambda x: x['time'], reverse=True)[:5]
            for t in session_trades:
                all_recent_trades.append({
                    'ticket': t['ticket'],
                    'time': t['time'].isoformat(),
                    'type': t['type'],
                    'volume': t['volume'],
                    'price': t['price'],
                    'profit': t['profit'],
                    'bot_id': self.bot_id
                })
            
            # Sort by time and keep last 10
            all_recent_trades.sort(key=lambda x: x['time'], reverse=True)
            self.performance['recent_trades'] = all_recent_trades[:10]
            
            log.info(f"📊 Bot {self.bot_id} COMPLETE performance: {total_trades} total trades "
                    f"(lifetime: {self.lifetime_stats['total_completed_trades']}, session: {len(completed_trades)}), "
                    f"{win_rate:.1f}% win rate, ${total_realized_profit:.2f} realized, "
                    f"${unrealized_pnl:.2f} unrealized, ${total_realized_profit + unrealized_pnl:.2f} total P&L, "
                    f"W:{winning_trades}/L:{losing_trades}")
            
        except Exception as e:
            log.error(f"Error updating performance for bot {self.bot_id}: {e}")
            # Fallback to basic tracking
            self.performance.update({
                'total_trades': 0,
                'active_trades': 0,
                'last_update': datetime.now().isoformat()
            })
    
    def get_trade_history(self):
        """Get recent trade history for THIS bot only"""
        try:
            if not mt5.initialize():
                return []
            
            # Skip if bot hasn't been properly initialized
            if not self.unique_magic_number or not self.bot_start_time:
                log.debug(f"Bot {self.bot_id} not fully initialized for trade history")
                return []
                
            # Get trade history from when this bot started
            deals = mt5.history_deals_get(self.bot_start_time, datetime.now())
            bot_trades = []
            
            if deals:
                for deal in deals:
                    magic_number = getattr(deal, 'magic', 0)
                    comment = getattr(deal, 'comment', '')
                    deal_type = getattr(deal, 'type', -1)
                    
                    # STRICT filtering: Only trades with THIS bot's magic number
                    is_this_bot_trade = (
                        magic_number == self.unique_magic_number or 
                        (f"TradePulse_{self.bot_id}" in comment and magic_number >= 234000)
                    )
                    
                    # Only include actual trade deals
                    if is_this_bot_trade and deal_type in [0, 1]:  # BUY or SELL deals
                        bot_trades.append({
                            'ticket': getattr(deal, 'ticket', 0),
                            'position_id': getattr(deal, 'position_id', 0),
                            'time': datetime.fromtimestamp(getattr(deal, 'time', 0)).isoformat(),
                            'type': 'BUY' if deal_type == 0 else 'SELL',
                            'volume': getattr(deal, 'volume', 0),
                            'price': getattr(deal, 'price', 0),
                            'profit': getattr(deal, 'profit', 0) + getattr(deal, 'commission', 0) + getattr(deal, 'swap', 0),
                            'magic': magic_number
                        })
            
            log.debug(f"Bot {self.bot_id} trade history: {len(bot_trades)} trades found")
            return sorted(bot_trades, key=lambda x: x['time'], reverse=True)
            
        except Exception as e:
            log.error(f"Error getting trade history for bot {self.bot_id}: {e}")
            return []
        
    def get_bot_status(self) -> Dict:
        """Get current bot status"""
        return {
            'is_running': self.is_running,
            'strategy': self.config['strategy_name'],
            'auto_trading': self.config['auto_trading_enabled'],
            'performance': self.performance,
            'active_trades': len(self.active_trades),
            'config': self.config,
            'magic_number': self.unique_magic_number,
            'bot_start_time': self.bot_start_time.isoformat() if self.bot_start_time else None,
            'bot_id': self.bot_id
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

    def force_performance_update(self):
        """Force an immediate performance update - useful for debugging"""
        log.info(f"🔄 Force updating performance for bot {self.bot_id}")
        self._update_performance()
        
        # Log detailed performance data
        log.info(f"📊 DETAILED Performance for {self.bot_id}:")
        log.info(f"   - Total Trades: {self.performance.get('total_trades', 0)}")
        log.info(f"   - Active Trades: {self.performance.get('active_trades', 0)}")
        log.info(f"   - Win Rate: {self.performance.get('win_rate', 0)}%")
        log.info(f"   - Winning Trades: {self.performance.get('winning_trades', 0)}")
        log.info(f"   - Losing Trades: {self.performance.get('losing_trades', 0)}")
        log.info(f"   - Realized P&L: ${self.performance.get('total_profit', 0)}")
        log.info(f"   - Unrealized P&L: ${self.performance.get('unrealized_pnl', 0)}")
        log.info(f"   - Total P&L: ${self.performance.get('total_pnl', 0)}")
        log.info(f"   - Magic Number: {self.unique_magic_number}")
        
        return self.performance

    def _generate_unique_magic_number(self):
        """Generate a unique magic number for this bot instance"""
        import hashlib
        import time
        
        # Create unique identifier from bot_id and timestamp
        unique_string = f"{self.bot_id}_{int(time.time())}"
        hash_obj = hashlib.md5(unique_string.encode())
        
        # Convert to integer and ensure it's within MT5 limits (0-2147483647)
        magic_number = int(hash_obj.hexdigest()[:8], 16) % 2147483647
        
        # Ensure it's not 0 and is in a reasonable range for our bots (234000-300000)
        magic_number = 234000 + (magic_number % 66000)
        
        log.info(f"Generated unique magic number for bot {self.bot_id}: {magic_number}")
        return magic_number

    def _find_recent_bot_trades_fallback(self):
        """Fallback method to find recent trades that might belong to this bot"""
        try:
            # For bots that were started recently, also look for ANY recent TradePulse trades
            # This helps capture trades that were executed before the unique magic number system
            from datetime import timedelta
            
            # Look back 60 minutes for any TradePulse trades (increased from 30)
            recent_time = datetime.now() - timedelta(minutes=60)
            deals = mt5.history_deals_get(recent_time, datetime.now())
            
            fallback_trades = []
            if deals:
                log.info(f"Fallback: Checking {len(deals)} deals from last 60 minutes")
                
                for deal in deals:
                    magic_number = getattr(deal, 'magic', 0)
                    comment = getattr(deal, 'comment', '')
                    deal_type = getattr(deal, 'type', -1)
                    deal_time = datetime.fromtimestamp(getattr(deal, 'time', 0))
                    
                    # Enhanced TradePulse trade detection
                    is_tradepulse_trade = (
                        'TradePulse' in comment or 
                        'tradepulse' in comment.lower() or
                        (magic_number >= 234000 and magic_number <= 300000) or
                        (magic_number >= 10000000 and magic_number <= 99999999)  # Also check for larger magic numbers
                    )
                    
                    if is_tradepulse_trade and deal_type in [0, 1]:
                        profit = getattr(deal, 'profit', 0)
                        commission = getattr(deal, 'commission', 0)
                        swap = getattr(deal, 'swap', 0)
                        net_profit = profit + commission + swap
                        
                        fallback_trades.append({
                            'ticket': getattr(deal, 'ticket', 0),
                            'position_id': getattr(deal, 'position_id', 0),
                            'time': deal_time,
                            'type': 'BUY' if deal_type == 0 else 'SELL',
                            'volume': getattr(deal, 'volume', 0),
                            'price': getattr(deal, 'price', 0),
                            'profit': net_profit,
                            'raw_profit': profit,
                            'commission': commission,
                            'swap': swap,
                            'magic': magic_number,
                            'comment': comment,
                            'fallback': True  # Mark as fallback trade
                        })
                        
                        log.info(f"Fallback found: Ticket={getattr(deal, 'ticket', 0)}, Magic={magic_number}, "
                               f"Comment='{comment}', Profit={net_profit:.2f}, Time={deal_time}")
            
            log.info(f"Fallback search found {len(fallback_trades)} recent TradePulse trades")
            return fallback_trades
            
        except Exception as e:
            log.error(f"Error in fallback trade search: {e}")
            return []

    def _track_completed_trade(self, trade_data):
        """Track a completed trade in lifetime statistics"""
        try:
            profit = trade_data.get('profit', 0)
            
            # Update lifetime counters
            self.lifetime_stats['total_completed_trades'] += 1
            self.lifetime_stats['lifetime_realized_profit'] += profit
            
            if profit > 0:
                self.lifetime_stats['total_winning_trades'] += 1
            elif profit < 0:
                self.lifetime_stats['total_losing_trades'] += 1
            
            # Add to completed trade history (keep last 50 trades)
            trade_record = {
                'ticket': trade_data.get('ticket', 0),
                'position_id': trade_data.get('position_id', 0),
                'time': trade_data.get('time', datetime.now()),
                'type': trade_data.get('type', 'UNKNOWN'),
                'volume': trade_data.get('volume', 0),
                'price': trade_data.get('price', 0),
                'profit': profit,
                'bot_id': self.bot_id,
                'magic_number': self.unique_magic_number,
                'comment': trade_data.get('comment', ''),
                'completed_at': datetime.now()
            }
            
            self.lifetime_stats['completed_trade_history'].append(trade_record)
            
            # Keep only last 50 completed trades
            if len(self.lifetime_stats['completed_trade_history']) > 50:
                self.lifetime_stats['completed_trade_history'] = self.lifetime_stats['completed_trade_history'][-50:]
            
            # Update daily stats
            today = datetime.now().strftime('%Y-%m-%d')
            if today not in self.lifetime_stats['daily_stats']:
                self.lifetime_stats['daily_stats'][today] = {
                    'trades': 0,
                    'profit': 0.0,
                    'winning': 0,
                    'losing': 0
                }
            
            self.lifetime_stats['daily_stats'][today]['trades'] += 1
            self.lifetime_stats['daily_stats'][today]['profit'] += profit
            if profit > 0:
                self.lifetime_stats['daily_stats'][today]['winning'] += 1
            elif profit < 0:
                self.lifetime_stats['daily_stats'][today]['losing'] += 1
            
            # Update max drawdown
            current_balance = self.lifetime_stats['lifetime_realized_profit']
            if current_balance > self.lifetime_stats['peak_balance']:
                self.lifetime_stats['peak_balance'] = current_balance
            
            drawdown = self.lifetime_stats['peak_balance'] - current_balance
            if drawdown > self.lifetime_stats['lifetime_max_drawdown']:
                self.lifetime_stats['lifetime_max_drawdown'] = drawdown
            
            log.info(f"📝 Tracked completed trade for {self.bot_id}: Profit=${profit:.2f}, "
                    f"Lifetime: {self.lifetime_stats['total_completed_trades']} trades, "
                    f"${self.lifetime_stats['lifetime_realized_profit']:.2f} total profit")
            
        except Exception as e:
            log.error(f"Error tracking completed trade: {e}")
    
    def _detect_completed_trades(self, current_bot_trades):
        """Detect newly completed trades by comparing with previous state"""
        try:
            # Check if we have any deals that represent completed positions
            for trade in current_bot_trades:
                trade_key = f"{trade['position_id']}_{trade['ticket']}"
                
                # If this trade has profit and we haven't tracked it yet
                if (trade['profit'] != 0 and 
                    not any(ct['ticket'] == trade['ticket'] for ct in self.lifetime_stats['completed_trade_history'])):
                    
                    # This is a completed trade
                    self._track_completed_trade(trade)
                    
                    # Notify frontend about the completed trade
                    self.notify_updates({
                        'type': 'trade_completed',
                        'bot_id': self.bot_id,
                        'trade_data': trade,
                        'timestamp': datetime.now().isoformat()
                    })
                    
        except Exception as e:
            log.error(f"Error detecting completed trades: {e}")

# Global bot manager instance
bot_manager = TradingBotManager()