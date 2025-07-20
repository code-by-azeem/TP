# backend/candlestickData.py

# --- !!! Run monkey_patch FIRST !!! ---
import eventlet
eventlet.monkey_patch()
# --- End of Critical Change ---

# --- Now other imports ---
import MetaTrader5 as mt5
import time
import logging
import sys
import os
from datetime import datetime, timedelta
from threading import Lock
from flask import Flask, jsonify, request, session
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
# dateutil is not needed for this bar count approach
import random
from collections import Counter # Added for logging client counts by timeframe

# Import trading bot
from trading_bot.bot_manager import bot_manager

# --- Configuration ---
load_dotenv()
SYMBOL = os.getenv("MT5_SYMBOL", "ETHUSD")
UPDATE_INTERVAL_SECONDS = 1 # Defines the background loop's target interval
HISTORY_COUNT = 5000
DATA_REQUEST_RATE_LIMIT = {}
DATA_REQUEST_COUNTERS = {}
LOG_RATE_LIMIT = 10

# Global dictionary to store client timeframes - key: client_sid, value: timeframe
client_timeframes = {}
# Global to store the last M1 candle time we processed to avoid resending same data
last_processed_m1_candle_time = 0
# Lock for last_processed_m1_candle_time if needed, but background_price_updater is single-threaded access for it.

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(threadName)s %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

# Create a custom filter to reduce repetitive logs
class DuplicateFilter(logging.Filter):
    def __init__(self, name=''):
        super(DuplicateFilter, self).__init__(name)
        self.last_log = {}
        
    def filter(self, record):
        # Get the message and path to use as a unique key
        current_time = time.time()
        log_key = f"{record.pathname}:{record.lineno}:{record.getMessage()}"
        
        # Check if we've seen this log recently
        if log_key in self.last_log:
            last_time = self.last_log[log_key]
            # Only allow the same log message once every LOG_RATE_LIMIT seconds
            if current_time - last_time < LOG_RATE_LIMIT:
                return False  # Skip this log
                
        # Update the last time we saw this log
        self.last_log[log_key] = current_time
        return True

# Apply the custom filter
log.addFilter(DuplicateFilter())

# Reduce socket.io logs to make terminal more readable
logging.getLogger('socketio').setLevel(logging.WARNING)
logging.getLogger('engineio').setLevel(logging.WARNING)
logging.getLogger('werkzeug').setLevel(logging.WARNING)

# --- Flask & SocketIO App Initialization ---
log.info("Initializing Flask application...")
app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Set a strong secret key in production

# Configure CORS with more options
cors_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
CORS(app, 
     resources={r"/*": {"origins": cors_origins}},
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
     methods=["GET", "POST", "OPTIONS"],
     vary_header=True)

# Configure SocketIO with improved connection options for better stability
socketio = SocketIO(
    app, 
    cors_allowed_origins=cors_origins, 
    async_mode='eventlet',
    logger=False,
    engineio_logger=False,
    ping_timeout=120,         # Increased from 60 to 120
    ping_interval=25,
    max_http_buffer_size=10 * 1024 * 1024,  # Increased buffer size for large data transfers
    always_connect=True,
    manage_session=True,
    transports=['websocket', 'polling'],  # Explicitly specify available transports
    reconnection=True,        # Allow reconnection by default
    reconnection_attempts=10, # Max reconnection attempts
    reconnection_delay=1,     # Initial delay in seconds
    reconnection_delay_max=5  # Maximum delay between reconnections
)
log.info(f"Flask-SocketIO initialized with transports: {socketio.server.eio.transports}")

# --- Simple user management for web app access (separate from MT5 authentication) ---
# MT5 handles its own authentication via mt5.initialize(), but we need web app login
users = {
    'mohib': 'mohib'  # Pre-create your user account
}

# Renamed to avoid conflict if 'timeframes' is used as a local variable elsewhere
timeframes_mt5_constants = {
    "1m": mt5.TIMEFRAME_M1,
    "5m": mt5.TIMEFRAME_M5,
    "1h": mt5.TIMEFRAME_H1,
    "4h": mt5.TIMEFRAME_H4,
    "1d": mt5.TIMEFRAME_D1,
    "1w": mt5.TIMEFRAME_W1
}

# --- MT5 Connection ---
def initialize_mt5():
    try:
        log.info("Initializing MetaTrader 5 connection...")
        # Try initializing MT5
        if not mt5.initialize():
            log.error(f"MT5 init failed: {mt5.last_error()}")
            return False
            
        log.info(f"MT5 connection successful. Checking symbol: {SYMBOL}")
        symbol_info = mt5.symbol_info(SYMBOL)
        
        if not symbol_info:
            log.error(f"{SYMBOL} not found")
            mt5.shutdown()
            return False
            
        if not symbol_info.visible:
            log.warning(f"{SYMBOL} not visible, enabling...")
            if not mt5.symbol_select(SYMBOL, True):
                log.error(f"Failed to enable {SYMBOL}")
                mt5.shutdown()
                return False
                
            time.sleep(0.5)
            symbol_info = mt5.symbol_info(SYMBOL)
            
            if not symbol_info or not symbol_info.visible:
                log.error(f"Failed confirm {SYMBOL} visibility")
                mt5.shutdown()
                return False
                
            log.info(f"{SYMBOL} enabled.")
        else: 
            log.info(f"{SYMBOL} is visible.")
            
        if not mt5.terminal_info():
            log.error("Lost MT5 connection")
            mt5.shutdown()
            return False
            
        log.info("MT5 setup complete.")
        return True
    except Exception as e:
        log.error(f"MT5 initialization error: {e}", exc_info=True)
        return False

# Try initializing MT5, but continue even if it fails
mt5_initialized = initialize_mt5()
if not mt5_initialized:
    log.warning("MT5 initialization failed, but continuing to run the server. Some features will be unavailable.")

# --- Background Task ---
thread = None
thread_lock = Lock()

def format_candle(rate):
    """Format candle data from MT5 into a format compatible with lightweight-charts"""
    if rate is None or len(rate) < 5: return None
    
    # Convert datetime timestamp to Unix timestamp in seconds
    unix_timestamp = None
    
    # Handle different timestamp types
    if isinstance(rate[0], datetime):
        # If it's a datetime object, convert to Unix timestamp
        unix_timestamp = int(rate[0].timestamp())
    elif isinstance(rate[0], (int, float)):
        # If it's already a numeric timestamp
        unix_timestamp = int(rate[0])
        # If in milliseconds, convert to seconds
        if unix_timestamp > 9999999999:
            unix_timestamp = unix_timestamp // 1000
    else:
        # Try to convert string or other format to int
        try:
            unix_timestamp = int(rate[0])
            if unix_timestamp > 9999999999:
                unix_timestamp = unix_timestamp // 1000
        except (ValueError, TypeError):
            log.error(f"Invalid timestamp format: {rate[0]}")
            return None
    
    return {
        'time': unix_timestamp, 
        'open': float(rate[1]), 
        'high': float(rate[2]), 
        'low': float(rate[3]), 
        'close': float(rate[4])
    }

def create_dummy_candle():
    """Create a dummy candle for testing when MT5 is not available"""
    # Get current timestamp in seconds (not milliseconds)
    current_time = int(datetime.now().timestamp())
    
    # Generate price data with some randomness but keep it realistic
    base_prices = {
        "ETHUSD": 3246.50,
        "BTCUSD": 65000.0,
        "XAUUSD": 2300.0
    }
    
    # Get base price with small variance - keep it realistic
    price_base = base_prices.get(SYMBOL, 1000.0) + (random.random() * 10 - 5)
    # Create reasonable volatility
    price_range = price_base * 0.005  # 0.5% volatility
    price_high = price_base + abs(random.random() * price_range)
    price_low = price_base - abs(random.random() * price_range)
    price_close = price_low + random.random() * (price_high - price_low)
    
    # Ensure all values are proper floats with limited decimal places
    return {
        'time': current_time,
        'open': round(float(price_base), 2),
        'high': round(float(price_high), 2),
        'low': round(float(price_low), 2),
        'close': round(float(price_close), 2)
    }

def getCandleStartTime(timestamp, timeframe):
    """
    Calculate the start time of a candle based on the timestamp and timeframe.
    
    Args:
        timestamp (int): Unix timestamp in seconds
        timeframe (str): Timeframe string ('1m', '5m', '1h', '4h', '1d', '1w')
        
    Returns:
        int: Unix timestamp in seconds for the start of the candle
    """
    # Convert timestamp to datetime object
    dt = datetime.fromtimestamp(timestamp)
    
    # Calculate the start time based on timeframe
    if timeframe == '1m':
        # Start of the minute
        return int(datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute).timestamp())
    elif timeframe == '5m':
        # Start of the 5-minute interval
        minute = dt.minute - (dt.minute % 5)
        return int(datetime(dt.year, dt.month, dt.day, dt.hour, minute).timestamp())
    elif timeframe == '1h':
        # Start of the hour
        return int(datetime(dt.year, dt.month, dt.day, dt.hour).timestamp())
    elif timeframe == '4h':
        # Start of the 4-hour interval
        hour = dt.hour - (dt.hour % 4)
        return int(datetime(dt.year, dt.month, dt.day, hour).timestamp())
    elif timeframe == '1d':
        # Start of the day
        return int(datetime(dt.year, dt.month, dt.day).timestamp())
    elif timeframe == '1w':
        # Start of the week (Monday)
        days_since_monday = dt.weekday()
        monday = dt - timedelta(days=days_since_monday)
        return int(datetime(monday.year, monday.month, monday.day).timestamp())
    else:
        # Default to 1m if timeframe is not recognized
        return int(datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute).timestamp())

def background_price_updater():
    global last_processed_m1_candle_time # Allow modification of global
    log.info(f"Background M1 price updater task starting ({UPDATE_INTERVAL_SECONDS}s interval emission).")
    
    update_log_counter = 0 # For periodic logging
    last_log_time = time.time()
    target_interval = float(UPDATE_INTERVAL_SECONDS)
    
    # This variable will track the start of each iteration for precise interval logging
    last_iteration_start_time = time.time()
    
    # Track last emission timestamp per client to prevent flooding
    last_client_emission = {}
    # Minimum time between emissions to the same client (in seconds)
    min_client_emission_interval = 0.25  # 250ms between updates (4 updates/second)
    
    # Track the last sent candle data per timeframe to avoid sending duplicate data
    last_sent_candle_by_timeframe = {}

    while True:
        current_iteration_start_time = time.time()
        try:
            # Periodic detailed logging
            update_log_counter += 1
            should_log_details_this_iteration = False
            if update_log_counter >= 10 or (current_iteration_start_time - last_log_time) >= 10:
                should_log_details_this_iteration = True
                update_log_counter = 0
                last_log_time = current_iteration_start_time
                
                # Log the actual interval between these detailed logging blocks
                log.info(f"Price updater activity check. Clients: {len(client_timeframes)}")
                if client_timeframes:
                    # Using Counter for a cleaner log
                    tf_counts = Counter(client_timeframes.values())
                    log.info(f"Clients by timeframe: {dict(tf_counts)}")

            # Check MT5 connection status
            mt5_connected_for_this_iteration = False
            try:
                term_info = mt5.terminal_info()
                # Ensure term_info itself is not None before checking attributes
                mt5_connected_for_this_iteration = term_info is not None and hasattr(term_info, 'connected') and term_info.connected
            except Exception as mt5_conn_err:
                if should_log_details_this_iteration: 
                    log.error(f"MT5 connection check error in background task: {mt5_conn_err}")
                mt5_connected_for_this_iteration = False

            if mt5_connected_for_this_iteration:
                try:
                    # Fetch the latest 1-minute candle
                    rates = mt5.copy_rates_from_pos(SYMBOL, timeframes_mt5_constants["1m"], 0, 1)
                    if rates is not None and len(rates) > 0:
                        current_m1_candle = format_candle(rates[0])
                        if current_m1_candle:
                            # Check if this candle is new or different from the last one processed
                            is_new_candle = current_m1_candle['time'] > last_processed_m1_candle_time
                            
                            # Get the last sent 1m candle if it exists
                            last_m1_candle = last_sent_candle_by_timeframe.get('1m', None)
                            
                            # Check if this is a price update within the same candle
                            is_price_update = (not is_new_candle and last_m1_candle and 
                                              (current_m1_candle['close'] != last_m1_candle.get('close', 0) or
                                               current_m1_candle['high'] != last_m1_candle.get('high', 0) or
                                               current_m1_candle['low'] != last_m1_candle.get('low', 0)))
                            
                            # Only update if we have a new candle, price change, or we're replying to a new client
                            if is_new_candle or is_price_update:
                                # For new candles, update the timestamp reference
                                if is_new_candle:
                                    last_processed_m1_candle_time = current_m1_candle['time']
                                
                                current_m1_candle['timeframe'] = '1m'  # Explicitly tag data as M1
                                
                                # Update our last sent candle for 1m timeframe
                                last_sent_candle_by_timeframe['1m'] = current_m1_candle.copy()
                                
                                # Get all clients who are interested in 1m timeframe
                                m1_clients = [sid for sid, tf in client_timeframes.items() if tf == '1m']
                                    
                                # Only emit to clients who haven't received an update recently
                                current_time = time.time()
                                for sid in m1_clients:
                                    # Check if we should emit to this client based on rate limiting
                                    last_emission_time = last_client_emission.get(sid, 0)
                                    time_since_last_emission = current_time - last_emission_time
                                    
                                    if time_since_last_emission >= min_client_emission_interval:
                                        socketio.emit('price_update', current_m1_candle, room=sid)
                                        last_client_emission[sid] = current_time
                                        
                                if should_log_details_this_iteration and m1_clients:
                                    log.info(f"Sent M1 update to {len(m1_clients)} clients: T:{current_m1_candle['time']} C:{current_m1_candle['close']}")
                                
                                # Now also process other timeframes (aggregating from the new M1 data)
                                # This is where you would update 5m, 1h, etc. candles based on the new M1 data
                                # For each other timeframe, check if the current M1 belongs to a new candle for that timeframe
                                for tf in ['5m', '1h', '4h', '1d', '1w']:
                                    # Calculate the start time for this M1 candle in the target timeframe
                                    candle_start_time = getCandleStartTime(current_m1_candle['time'], tf)
                                    
                                    # If we have clients for this timeframe, process it
                                    tf_clients = [sid for sid, client_tf in client_timeframes.items() if client_tf == tf]
                                    if tf_clients:
                                        # Check if we already have a candle for this timeframe with this start time
                                        last_tf_candle = last_sent_candle_by_timeframe.get(tf, None)
                                        
                                        # If we have a new candle or it's updated (for this timeframe)
                                        if not last_tf_candle or last_tf_candle.get('time', 0) != candle_start_time:
                                            # We need to fetch the complete candle data for this timeframe
                                            try:
                                                tf_rates = mt5.copy_rates_from_pos(SYMBOL, timeframes_mt5_constants[tf], 0, 1)
                                                if tf_rates is not None and len(tf_rates) > 0:
                                                    tf_candle = format_candle(tf_rates[0])
                                                    if tf_candle:
                                                        tf_candle['timeframe'] = tf
                                                        
                                                        # Store as the last sent candle for this timeframe
                                                        last_sent_candle_by_timeframe[tf] = tf_candle.copy()
                                                        
                                                        # Send to interested clients with rate limiting
                                                        for sid in tf_clients:
                                                            last_emission_time = last_client_emission.get(sid, 0)
                                                            time_since_last_emission = current_time - last_emission_time
                                                            
                                                            if time_since_last_emission >= min_client_emission_interval:
                                                                socketio.emit('price_update', tf_candle, room=sid)
                                                                last_client_emission[sid] = current_time
                                                        
                                                        if should_log_details_this_iteration:
                                                            log.info(f"Sent {tf} update to {len(tf_clients)} clients: T:{tf_candle['time']} C:{tf_candle['close']}")
                                            except Exception as tf_err:
                                                if should_log_details_this_iteration:
                                                    log.error(f"Error fetching {tf} data: {tf_err}")
                                        # If candle hasn't updated for this timeframe, but it's the same one (update within the current candle)
                                        elif last_tf_candle and last_tf_candle.get('time', 0) == candle_start_time:
                                            # We have a candle with the same start time, but the close price may have changed
                                            # Update from MT5 to get the latest prices for this timeframe's candle
                                            try:
                                                tf_rates = mt5.copy_rates_from_pos(SYMBOL, timeframes_mt5_constants[tf], 0, 1)
                                                if tf_rates is not None and len(tf_rates) > 0:
                                                    new_tf_candle = format_candle(tf_rates[0])
                                                    if new_tf_candle:
                                                        # Check if anything has changed in the candle
                                                        has_changes = (
                                                            new_tf_candle['close'] != last_tf_candle.get('close', 0) or
                                                            new_tf_candle['high'] != last_tf_candle.get('high', 0) or
                                                            new_tf_candle['low'] != last_tf_candle.get('low', 0)
                                                        )
                                                        
                                                        if has_changes:
                                                            new_tf_candle['timeframe'] = tf
                                                            
                                                            # Update stored candle
                                                            last_sent_candle_by_timeframe[tf] = new_tf_candle.copy()
                                                            
                                                            # Send to interested clients with rate limiting
                                                            for sid in tf_clients:
                                                                last_emission_time = last_client_emission.get(sid, 0)
                                                                time_since_last_emission = current_time - last_emission_time
                                                                
                                                                if time_since_last_emission >= min_client_emission_interval:
                                                                    socketio.emit('price_update', new_tf_candle, room=sid)
                                                                    last_client_emission[sid] = current_time
                                                            
                                                            if should_log_details_this_iteration:
                                                                log.info(f"Sent updated {tf} candle to {len(tf_clients)} clients: T:{new_tf_candle['time']} C:{new_tf_candle['close']}")
                                            except Exception as tf_update_err:
                                                if should_log_details_this_iteration:
                                                    log.error(f"Error updating {tf} data: {tf_update_err}")
                        else:
                            if should_log_details_this_iteration:
                                log.warning("Failed to format candle data")
                    else:
                        if should_log_details_this_iteration:
                            log.warning(f"No rates returned from MT5 for symbol {SYMBOL}")
                except Exception as e_mt5_fetch:
                    if should_log_details_this_iteration: 
                        log.error(f"Error fetching/processing M1 rates from MT5: {e_mt5_fetch}")
            else: # MT5 not connected
                if should_log_details_this_iteration: 
                    log.warning("MT5 not connected, sending connection status to clients.")
                
                # Send a connection status update to all clients
                for sid in client_timeframes.keys():
                    last_emission_time = last_client_emission.get(sid, 0)
                    time_since_last_emission = time.time() - last_emission_time
                    
                    # Send status updates less frequently
                    if time_since_last_emission >= 5.0:  # Every 5 seconds when disconnected
                        socketio.emit('connection_status', {
                            'status': 'disconnected',
                            'message': 'MT5 connection lost',
                            'timestamp': datetime.now().isoformat()
                        }, room=sid)
                        last_client_emission[sid] = time.time()

            # Calculate processing time for this iteration
            loop_processing_duration = time.time() - current_iteration_start_time
            
            # Calculate sleep time to maintain the target_interval
            # The effective interval includes processing time + sleep time
            sleep_duration = target_interval - loop_processing_duration
            
            if sleep_duration < 0:
                sleep_duration = 0 # Avoid negative sleep; loop is taking longer than target_interval
                if should_log_details_this_iteration:
                    log.warning(f"Price updater loop duration ({loop_processing_duration:.3f}s) exceeded target interval ({target_interval:.3f}s).")

            # Clean up disconnected clients from our tracking dictionaries
            for sid in list(last_client_emission.keys()):
                if sid not in client_timeframes:
                    del last_client_emission[sid]

            socketio.sleep(sleep_duration)
        except Exception as e:
            log.error(f"Unexpected error in background_price_updater: {e}", exc_info=True)
            socketio.sleep(1)  # Sleep briefly before retrying after an error

# --- Real-time Trade Monitoring ---
trade_monitor_thread = None
last_known_positions = {}  # Track position states
last_known_deals = set()   # Track processed deal IDs
last_full_history_check = datetime.now() - timedelta(minutes=5)  # Track last full history check

def background_trade_monitor():
    """Monitor MT5 trades in real-time and emit updates via SocketIO with enhanced deal detection"""
    global last_known_positions, last_known_deals, last_full_history_check
    
    log.info("Starting enhanced real-time trade monitor...")
    
    # Track the last time we checked for deals to reduce API calls
    last_deal_check = datetime.now() - timedelta(minutes=1)
    deal_check_cache = {}
    
    while True:
        try:
            # Check MT5 connection
            if not is_mt5_connected():
                socketio.sleep(5)  # Wait before retrying
                continue
            
            current_time = datetime.now()
            
            # Get current positions
            current_positions = mt5.positions_get()
            if current_positions is None:
                current_positions = []
            
            # Convert positions to dict for easier comparison
            current_positions_dict = {}
            for pos in current_positions:
                ticket = getattr(pos, 'ticket', 0)
                current_positions_dict[ticket] = pos
            
            # First run initialization
            if not last_known_positions:
                last_known_positions = current_positions_dict
                log.info(f"Initialized trade monitor with {len(current_positions_dict)} open positions")
                socketio.sleep(1)
                continue
            
            # Enhanced deal monitoring - check for new deals every 500ms for immediate detection
            if (current_time - last_deal_check).total_seconds() >= 0.5:
                check_for_new_deals(current_time)
                # Also check for very recent deals (last 2 minutes) for immediate detection
                check_immediate_deals(current_time)
                last_deal_check = current_time
            
            # Perform full history check every 30 seconds to catch any missed trades
            if (current_time - last_full_history_check).total_seconds() >= 30:
                check_full_recent_history(current_time)
                last_full_history_check = current_time
            
            # Check for new or updated positions
            for ticket, pos in current_positions_dict.items():
                if ticket not in last_known_positions:
                    # New position opened
                    log.info(f"New position opened: {ticket}")
                    trade_data = format_position_data(pos, is_new=True)
                    if trade_data:
                        socketio.emit('trade_update', {
                            'type': 'position_opened',
                            'data': trade_data,
                            'timestamp': datetime.now().isoformat()
                        })
                        
                        # Also emit account summary update
                        emit_account_summary_update()
                else:
                    # Check if position was updated (profit changed)
                    old_pos = last_known_positions[ticket]
                    old_profit = float(getattr(old_pos, 'profit', 0))
                    new_profit = float(getattr(pos, 'profit', 0))
                    old_current_price = float(getattr(old_pos, 'price_current', 0))
                    new_current_price = float(getattr(pos, 'price_current', 0))
                    
                    # Check for profit change or price change (more sensitive for real-time updates)
                    profit_changed = abs(old_profit - new_profit) > 0.005  # Reduced threshold for more updates
                    price_changed = abs(old_current_price - new_current_price) > 0.00001  # More sensitive
                    
                    if profit_changed or price_changed:
                        trade_data = format_position_data(pos, is_new=False)
                        if trade_data:
                            socketio.emit('trade_update', {
                                'type': 'position_updated',
                                'data': trade_data,
                                'timestamp': datetime.now().isoformat()
                            })
                            
                            # Emit account summary update for any profit changes
                            emit_account_summary_update()
            
            # Check for closed positions with improved detection
            closed_positions = []
            for ticket in list(last_known_positions.keys()):
                if ticket not in current_positions_dict:
                    closed_positions.append(ticket)
            
            # Process closed positions with enhanced deal lookup
            if closed_positions:
                log.info(f"Detected {len(closed_positions)} closed positions: {closed_positions}")
                process_closed_positions(closed_positions, current_time)
            
            # Update last known positions
            last_known_positions = current_positions_dict
            
            socketio.sleep(0.5)  # Check every 500ms for faster response
            
        except Exception as e:
            log.error(f"Error in trade monitor: {e}", exc_info=True)
            socketio.sleep(2)  # Shorter sleep on error for faster recovery

def check_for_new_deals(current_time):
    """Enhanced deal monitoring to catch closing trades faster"""
    global last_known_deals
    
    try:
        # Look back 5 minutes for new deals for better detection
        date_from = current_time - timedelta(minutes=5)
        date_to = current_time
        
        deals = mt5.history_deals_get(date_from, date_to)
        if not deals:
            return
        
        for deal in deals:
            deal_ticket = getattr(deal, 'ticket', 0)
            deal_position_id = getattr(deal, 'position_id', 0)
            deal_type = getattr(deal, 'type', -1)
            
            # Skip if we've already processed this deal
            if deal_ticket in last_known_deals:
                continue
            
            # Only process actual trade deals
            if deal_type in [0, 1]:  # BUY or SELL deals
                last_known_deals.add(deal_ticket)
                
                # Check if this is a closing deal for a position we were tracking
                if deal_position_id in last_known_positions:
                    # This is a closing deal for a tracked position
                    try:
                        closed_trade_data = format_closed_trade_data(
                            last_known_positions[deal_position_id], deal
                        )
                        if closed_trade_data:
                            socketio.emit('trade_update', {
                                'type': 'position_closed',
                                'data': closed_trade_data,
                                'timestamp': datetime.now().isoformat()
                            })
                            log.info(f"Fast-detected position close via deals: {deal_position_id}")
                            
                            # Remove from tracked positions
                            if deal_position_id in last_known_positions:
                                del last_known_positions[deal_position_id]
                            
                            # Emit account summary update
                            emit_account_summary_update()
                            
                            # Also emit a signal to refresh trade history for all clients
                            socketio.emit('refresh_trade_history', {
                                'reason': 'new_closed_trade',
                                'timestamp': datetime.now().isoformat()
                            })
                    except Exception as e:
                        log.error(f"Error processing fast-detected closed trade: {e}")
                else:
                    # This might be a trade that was closed when the system wasn't running
                    # Emit a refresh signal to ensure it's picked up
                    log.info(f"Detected deal {deal_ticket} for unknown position {deal_position_id}, triggering refresh")
                    socketio.emit('refresh_trade_history', {
                        'reason': 'unknown_position_deal',
                        'deal_ticket': deal_ticket,
                        'timestamp': datetime.now().isoformat()
                    })
        
        # Cleanup old deals from our tracking set to prevent memory growth
        if len(last_known_deals) > 1000:
            # Keep only the most recent 500 deals
            last_known_deals = set(list(last_known_deals)[-500:])
            
    except Exception as e:
        log.error(f"Error in enhanced deal monitoring: {e}")

def check_immediate_deals(current_time):
    """Check for very recent deals (last 2 minutes) for immediate detection"""
    global last_known_deals
    
    try:
        # Look back 2 minutes for immediate detection (increased from 30 seconds)
        date_from = current_time - timedelta(minutes=2)
        date_to = current_time
        
        deals = mt5.history_deals_get(date_from, date_to)
        if not deals:
            return
        
        new_deals_found = False
        for deal in deals:
            deal_ticket = getattr(deal, 'ticket', 0)
            deal_position_id = getattr(deal, 'position_id', 0)
            deal_type = getattr(deal, 'type', -1)
            
            # Skip if we've already processed this deal
            if deal_ticket in last_known_deals:
                continue
            
            # Only process actual trade deals
            if deal_type in [0, 1]:  # BUY or SELL deals
                last_known_deals.add(deal_ticket)
                new_deals_found = True
                
                log.info(f"IMMEDIATE: New deal detected - Ticket: {deal_ticket}, Position: {deal_position_id}")
                
                # Always emit refresh signal for immediate deals
                socketio.emit('refresh_trade_history', {
                    'reason': 'immediate_new_deal',
                    'deal_ticket': deal_ticket,
                    'timestamp': datetime.now().isoformat()
                })
                
                # Check if this is a closing deal for a position we were tracking
                if deal_position_id in last_known_positions:
                    # This is a closing deal for a tracked position
                    try:
                        closed_trade_data = format_closed_trade_data(
                            last_known_positions[deal_position_id], deal
                        )
                        if closed_trade_data:
                            socketio.emit('trade_update', {
                                'type': 'position_closed',
                                'data': closed_trade_data,
                                'timestamp': datetime.now().isoformat()
                            })
                            log.info(f"IMMEDIATE: Emitted position_closed for {deal_position_id}")
                            
                            # Remove from tracked positions
                            if deal_position_id in last_known_positions:
                                del last_known_positions[deal_position_id]
                            
                            # Emit account summary update
                            emit_account_summary_update()
                            
                            # Emit refresh signal for immediate UI update
                            socketio.emit('refresh_trade_history', {
                                'reason': 'immediate_closed_trade',
                                'timestamp': datetime.now().isoformat()
                            })
                    except Exception as e:
                        log.error(f"Error processing immediate closed trade: {e}")
                else:
                    # This might be a trade that was closed when system wasn't running
                    log.info(f"IMMEDIATE: Unknown position deal {deal_ticket} for position {deal_position_id}")
                    socketio.emit('refresh_trade_history', {
                        'reason': 'immediate_unknown_deal',
                        'deal_ticket': deal_ticket,
                        'timestamp': datetime.now().isoformat()
                    })
        
        if new_deals_found:
            log.info(f"IMMEDIATE: Found new deals, triggering account summary update")
            emit_account_summary_update()
            
    except Exception as e:
        log.error(f"Error in immediate deal monitoring: {e}")

def check_full_recent_history(current_time):
    """Periodically check full recent history to catch any missed trades"""
    global last_known_deals
    
    try:
        # Look back 10 minutes for comprehensive check
        date_from = current_time - timedelta(minutes=10)
        date_to = current_time
        
        deals = mt5.history_deals_get(date_from, date_to)
        if not deals:
            return
        
        new_deals_count = 0
        for deal in deals:
            deal_ticket = getattr(deal, 'ticket', 0)
            deal_type = getattr(deal, 'type', -1)
            
            # Skip if we've already processed this deal
            if deal_ticket in last_known_deals:
                continue
            
            # Only process actual trade deals
            if deal_type in [0, 1]:  # BUY or SELL deals
                last_known_deals.add(deal_ticket)
                new_deals_count += 1
        
        if new_deals_count > 0:
            log.info(f"Full history check found {new_deals_count} new deals, triggering refresh")
            socketio.emit('refresh_trade_history', {
                'reason': 'periodic_full_check',
                'new_deals': new_deals_count,
                'timestamp': datetime.now().isoformat()
            })
            emit_account_summary_update()
            
    except Exception as e:
        log.error(f"Error in full history check: {e}")

def process_closed_positions(closed_positions, current_time):
    """Process closed positions with enhanced deal lookup"""
    # Get recent deals to find closing information - look back further
    date_from = current_time - timedelta(minutes=15)  # Increased to 15 minutes to catch more trades
    
    try:
        deals = mt5.history_deals_get(date_from, current_time)
        if deals:
            processed_deals = set()
            
            for ticket in closed_positions:
                if ticket in last_known_positions:
                    position_found = False
                    
                    # Look for closing deals for this position
                    for deal in deals:
                        deal_ticket = getattr(deal, 'ticket', 0)
                        deal_position_id = getattr(deal, 'position_id', 0)
                        
                        # Skip if already processed
                        if deal_ticket in processed_deals:
                            continue
                        
                        if deal_position_id == ticket:
                            # Found the closing deal
                            try:
                                closed_trade_data = format_closed_trade_data(
                                    last_known_positions[ticket], deal
                                )
                                if closed_trade_data:
                                    socketio.emit('trade_update', {
                                        'type': 'position_closed',
                                        'data': closed_trade_data,
                                        'timestamp': datetime.now().isoformat()
                                    })
                                    processed_deals.add(deal_ticket)
                                    last_known_deals.add(deal_ticket)  # Add to global tracking
                                    position_found = True
                                    log.info(f"Emitted position_closed for ticket {ticket}")
                                    
                                    # Emit account summary update
                                    emit_account_summary_update()
                                    break
                            except Exception as format_error:
                                log.error(f"Error formatting closed trade data for {ticket}: {format_error}")
                    
                    # If no closing deal found, create basic closed trade info
                    if not position_found:
                        log.warning(f"No closing deal found for position {ticket}, creating estimated closed trade")
                        try:
                            basic_closed_data = format_basic_closed_trade(last_known_positions[ticket])
                            if basic_closed_data:
                                socketio.emit('trade_update', {
                                    'type': 'position_closed',
                                    'data': basic_closed_data,
                                    'timestamp': datetime.now().isoformat()
                                })
                                log.info(f"Emitted estimated position_closed for ticket {ticket}")
                                
                                # Emit account summary update
                                emit_account_summary_update()
                        except Exception as basic_error:
                            log.error(f"Error creating basic closed trade for {ticket}: {basic_error}")
    except Exception as deals_error:
        log.error(f"Error fetching deals for closed positions: {deals_error}")

def emit_account_summary_update():
    """Emit account summary update to all connected clients"""
    try:
        # Get updated account summary
        if is_mt5_connected():
            account_info = mt5.account_info()
            if account_info:
                # Get current positions for unrealized profit
                current_positions = mt5.positions_get()
                if current_positions is None:
                    current_positions = []
                
                # Calculate unrealized profit
                unrealized_profit = 0.0
                for position in current_positions:
                    try:
                        real_profit = float(getattr(position, 'profit', 0))
                        swap = float(getattr(position, 'swap', 0))
                        commission = float(getattr(position, 'commission', 0))
                        unrealized_profit += real_profit + swap + commission
                    except Exception as e:
                        continue
                
                # Build quick account update
                account_update = {
                    'balance': float(getattr(account_info, 'balance', 0)),
                    'equity': float(getattr(account_info, 'equity', 0)),
                    'margin': float(getattr(account_info, 'margin', 0)),
                    'margin_free': float(getattr(account_info, 'margin_free', 0)),
                    'total_profit': float(getattr(account_info, 'profit', 0)),
                    'unrealized_profit': unrealized_profit,
                    'open_positions': len(current_positions),
                    'timestamp': datetime.now().isoformat()
                }
                
                # Emit to all connected clients
                socketio.emit('account_update', account_update)
                
    except Exception as e:
        log.error(f"Error emitting account summary update: {e}")

def format_position_data(position, is_new=False):
    """Format MT5 position data for frontend"""
    try:
        position_type = "BUY" if getattr(position, 'type', 0) == 0 else "SELL"
        open_time = datetime.fromtimestamp(position.time) if hasattr(position, 'time') else datetime.now()
        
        # Calculate real profit
        real_profit = float(getattr(position, 'profit', 0))
        swap = float(getattr(position, 'swap', 0))
        commission = float(getattr(position, 'commission', 0))
        total_profit = real_profit + swap + commission
        
        # Get prices
        open_price = float(getattr(position, 'price_open', 0))
        current_price = float(getattr(position, 'price_current', open_price))
        
        # Calculate percentage change
        change_percent = 0.0
        if open_price > 0 and current_price > 0:
            if position_type == "BUY":
                change_percent = ((current_price - open_price) / open_price) * 100
            else:  # SELL
                change_percent = ((open_price - current_price) / open_price) * 100
        
        return {
            "id": int(getattr(position, 'ticket', 0)),
            "ticket": int(getattr(position, 'ticket', 0)),
            "timestamp": open_time.isoformat(),
            "time": open_time.isoformat(),
            "symbol": getattr(position, 'symbol', ''),
            "type": position_type,
            "volume": float(getattr(position, 'volume', 0)),
            "price": open_price,
            "entry_price": open_price,
            "current_price": current_price,
            "sl": float(getattr(position, 'sl', 0)),
            "tp": float(getattr(position, 'tp', 0)),
            "profit": total_profit,
            "raw_profit": real_profit,
            "commission": commission,
            "swap": swap,
            "change_percent": change_percent,
            "comment": getattr(position, 'comment', ''),
            "is_open": True,
            "is_new": is_new
        }
    except Exception as e:
        log.error(f"Error formatting position data: {e}")
        return None

def format_closed_trade_data(last_position, closing_deal):
    """Format closed trade data combining position and deal info"""
    try:
        position_type = "BUY" if getattr(last_position, 'type', 0) == 0 else "SELL"
        open_time = datetime.fromtimestamp(last_position.time) if hasattr(last_position, 'time') else datetime.now()
        close_time = datetime.fromtimestamp(closing_deal.time) if hasattr(closing_deal, 'time') else datetime.now()
        
        # Get final profit from the deal
        total_profit = float(getattr(closing_deal, 'profit', 0))
        commission = float(getattr(closing_deal, 'commission', 0))
        swap = float(getattr(closing_deal, 'swap', 0))
        final_profit = total_profit + commission + swap
        
        # Get prices
        open_price = float(getattr(last_position, 'price_open', 0))
        close_price = float(getattr(closing_deal, 'price', open_price))
        
        # Calculate percentage change
        change_percent = 0.0
        if open_price > 0 and close_price > 0:
            if position_type == "BUY":
                change_percent = ((close_price - open_price) / open_price) * 100
            else:  # SELL
                change_percent = ((open_price - close_price) / open_price) * 100
        
        return {
            "id": int(getattr(last_position, 'ticket', 0)),
            "ticket": int(getattr(last_position, 'ticket', 0)),
            "timestamp": open_time.isoformat(),
            "time": open_time.isoformat(),
            "close_time": close_time.isoformat(),
            "symbol": getattr(last_position, 'symbol', ''),
            "type": position_type,
            "volume": float(getattr(last_position, 'volume', 0)),
            "price": open_price,
            "entry_price": open_price,
            "exit_price": close_price,
            "current_price": close_price,
            "sl": float(getattr(last_position, 'sl', 0)),
            "tp": float(getattr(last_position, 'tp', 0)),
            "profit": final_profit,
            "raw_profit": total_profit,
            "commission": commission,
            "swap": swap,
            "change_percent": change_percent,
            "comment": getattr(last_position, 'comment', ''),
            "is_open": False,
            "just_closed": True
        }
    except Exception as e:
        log.error(f"Error formatting closed trade data: {e}")
        return None

def format_basic_closed_trade(last_position):
    """Format basic closed trade data when no closing deal is available"""
    try:
        position_type = "BUY" if getattr(last_position, 'type', 0) == 0 else "SELL"
        open_time = datetime.fromtimestamp(last_position.time) if hasattr(last_position, 'time') else datetime.now()
        close_time = datetime.now()  # Use current time as close time
        
        # Get current market price as estimated close price
        symbol = getattr(last_position, 'symbol', '')
        current_price = float(getattr(last_position, 'price_current', 0))
        open_price = float(getattr(last_position, 'price_open', 0))
        
        # If no current price available, use open price
        if current_price == 0:
            current_price = open_price
        
        # Estimate profit based on current price (may not be exact)
        volume = float(getattr(last_position, 'volume', 0))
        estimated_profit = 0.0
        
        if open_price > 0 and current_price > 0:
            if position_type == "BUY":
                estimated_profit = (current_price - open_price) * volume * 100  # Rough estimation
            else:  # SELL
                estimated_profit = (open_price - current_price) * volume * 100  # Rough estimation
        
        # Calculate percentage change
        change_percent = 0.0
        if open_price > 0 and current_price > 0:
            if position_type == "BUY":
                change_percent = ((current_price - open_price) / open_price) * 100
            else:  # SELL
                change_percent = ((open_price - current_price) / open_price) * 100
        
        return {
            "id": int(getattr(last_position, 'ticket', 0)),
            "ticket": int(getattr(last_position, 'ticket', 0)),
            "timestamp": open_time.isoformat(),
            "time": open_time.isoformat(),
            "close_time": close_time.isoformat(),
            "symbol": symbol,
            "type": position_type,
            "volume": volume,
            "price": open_price,
            "entry_price": open_price,
            "exit_price": current_price,
            "current_price": current_price,
            "sl": float(getattr(last_position, 'sl', 0)),
            "tp": float(getattr(last_position, 'tp', 0)),
            "profit": estimated_profit,
            "raw_profit": estimated_profit,
            "commission": 0.0,  # Unknown without deal
            "swap": 0.0,  # Unknown without deal
            "change_percent": change_percent,
            "comment": getattr(last_position, 'comment', ''),
            "is_open": False,
            "just_closed": True,
            "estimated": True  # Flag to indicate this is estimated data
        }
    except Exception as e:
        log.error(f"Error formatting basic closed trade data: {e}")
        return None

def check_new_historical_trades():
    """Check for new completed trades in recent history"""
    global last_known_deals
    
    try:
        # Check last 5 minutes of deals
        date_to = datetime.now()
        date_from = date_to - timedelta(minutes=5)
        
        deals = mt5.history_deals_get(date_from, date_to)
        if deals:
            for deal in deals:
                deal_ticket = getattr(deal, 'ticket', 0)
                
                # Skip if we've already processed this deal
                if deal_ticket in last_known_deals:
                    continue
                
                # Add to known deals
                last_known_deals.add(deal_ticket)
                
                # Only emit for actual trades (not balance operations)
                deal_type = getattr(deal, 'type', -1)
                if deal_type in [0, 1]:  # BUY or SELL deals
                    log.info(f"New historical deal detected: {deal_ticket}")
                    # You could emit this as a historical trade update if needed
    
    except Exception as e:
        log.error(f"Error checking historical trades: {e}")
        return None

# --- Flask Routes ---
@app.route('/status')
def status():
    # Endpoint remains unchanged
    log.info("Received request for /status")
    
    # Safe MT5 connection check
    mt5_connected = False
    try:
        term_info = mt5.terminal_info()
        mt5_connected = term_info is not None and hasattr(term_info, 'connected') and term_info.connected
    except Exception as e:
        log.error(f"MT5 connection check error in status endpoint: {e}")
    
    return jsonify({
        "status": "ok", 
        "mt5_connected": mt5_connected, 
        "symbol": SYMBOL, 
        "timestamp": datetime.now().isoformat()
    })

@app.route('/force-refresh-trades')
def force_refresh_trades():
    """Force refresh trade data - useful for immediate updates without server restart"""
    if 'username' not in session:
        return jsonify({"error": "Please login to access trade data"}), 401
    
    try:
        # Emit refresh signal to all clients
        socketio.emit('refresh_trade_history', {
            'reason': 'manual_force_refresh',
            'timestamp': datetime.now().isoformat()
        })
        
        # Also emit account summary update
        emit_account_summary_update()
        
        return jsonify({
            "status": "success",
            "message": "Trade refresh triggered",
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        log.error(f"Error forcing trade refresh: {e}", exc_info=True)
        return jsonify({"error": "Failed to refresh trades"}), 500

@app.route('/account-summary')
def get_account_summary():
    """Get comprehensive account summary with unified profit calculations"""
    if 'username' not in session:
        return jsonify({"error": "Please login to access account summary"}), 401
    
    try:
        if not is_mt5_connected():
            return jsonify({"error": "MT5 connection not available"}), 503
        
        # Get real account data from MT5
        account_info = mt5.account_info()
        if account_info is None:
            log.error(f"Failed to get account info from MT5: {mt5.last_error()}")
            return jsonify({"error": "Failed to retrieve account information from MT5"}), 500
        
        # Get current open positions for unrealized profit
        current_positions = []
        try:
            current_positions = mt5.positions_get()
            if current_positions is None:
                current_positions = []
        except Exception as e:
            log.error(f"Error fetching open positions for summary: {e}")
            current_positions = []
        
        # Calculate unrealized profit from open positions
        unrealized_profit = 0.0
        position_count = len(current_positions)
        for position in current_positions:
            try:
                real_profit = float(getattr(position, 'profit', 0))
                swap = float(getattr(position, 'swap', 0))
                commission = float(getattr(position, 'commission', 0))
                unrealized_profit += real_profit + swap + commission
            except Exception as e:
                log.error(f"Error calculating unrealized profit for position: {e}")
                continue
        
        # Get historical deals for realized profit (last 6 months)
        date_to = datetime.now()
        date_from = date_to - timedelta(days=180)
        
        deals = []
        try:
            deals = mt5.history_deals_get(date_from, date_to)
            if deals is None:
                deals = []
        except Exception as e:
            log.error(f"Error fetching deals for realized profit: {e}")
            deals = []
        
        # Calculate realized profit and trade statistics
        realized_profit = 0.0
        winning_trades = 0
        losing_trades = 0
        closed_trades_count = 0
        processed_positions = {}  # Track positions with their profit
        
        # Group deals by position to calculate per-trade profit
        deal_groups = {}
        for deal in deals:
            try:
                deal_type = getattr(deal, 'type', -1)
                position_id = getattr(deal, 'position_id', 0)
                
                # Only process actual trade deals
                if deal_type in [0, 1] and position_id > 0:
                    if position_id not in deal_groups:
                        deal_groups[position_id] = []
                    deal_groups[position_id].append(deal)
                    
            except Exception as e:
                log.error(f"Error grouping deal for statistics: {e}")
                continue
        
        # Process each position's deals
        for position_id, position_deals in deal_groups.items():
            try:
                # Calculate total P/L for this position
                position_profit = 0.0
                position_commission = 0.0
                position_swap = 0.0
                
                for deal in position_deals:
                    position_profit += float(getattr(deal, 'profit', 0))
                    position_commission += float(getattr(deal, 'commission', 0))
                    position_swap += float(getattr(deal, 'swap', 0))
                
                total_position_pl = position_profit + position_commission + position_swap
                
                # Add to realized profit
                realized_profit += total_position_pl
                
                # Determine if this is a closed position (has at least 2 deals or profit != 0)
                is_closed = len(position_deals) >= 2 or (len(position_deals) == 1 and position_profit != 0)
                
                if is_closed:
                    closed_trades_count += 1
                    
                    # Count wins/losses
                    if total_position_pl > 0:
                        winning_trades += 1
                    elif total_position_pl < 0:
                        losing_trades += 1
                    # If exactly 0, don't count as win or loss
                    
                    processed_positions[position_id] = total_position_pl
                    
            except Exception as e:
                log.error(f"Error processing position {position_id} for statistics: {e}")
                continue
        
        # Log detailed statistics
        log.info(f"Account Summary Statistics:")
        log.info(f"  - Total deals processed: {len(deals)}")
        log.info(f"  - Unique positions: {len(deal_groups)}")
        log.info(f"  - Closed trades: {closed_trades_count}")
        log.info(f"  - Winning trades: {winning_trades}")
        log.info(f"  - Losing trades: {losing_trades}")
        log.info(f"  - Realized P/L: ${realized_profit:.2f}")
        log.info(f"  - Unrealized P/L: ${unrealized_profit:.2f}")
        
        # Build comprehensive account summary
        account_summary = {
            # Basic account info
            "id": int(getattr(account_info, 'login', 0)),
            "username": session.get('username', getattr(account_info, 'name', 'MT5 User')),
            "currency": getattr(account_info, 'currency', 'USD'),
            "server": getattr(account_info, 'server', ''),
            "company": getattr(account_info, 'company', ''),
            
            # Core account metrics
            "balance": float(getattr(account_info, 'balance', 0)),
            "equity": float(getattr(account_info, 'equity', 0)),
            "margin": float(getattr(account_info, 'margin', 0)),
            "margin_free": float(getattr(account_info, 'margin_free', 0)),
            "margin_level": float(getattr(account_info, 'margin_level', 0)),
            
            # Profit breakdown
            "total_profit": float(getattr(account_info, 'profit', 0)),  # This should match unrealized_profit
            "realized_profit": realized_profit,
            "unrealized_profit": unrealized_profit,
            
            # Trading statistics
            "open_positions": position_count,
            "closed_trades_6m": closed_trades_count,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": (winning_trades / closed_trades_count * 100) if closed_trades_count > 0 else 0,
            
            # Account settings
            "leverage": f"1:{int(getattr(account_info, 'leverage', 100))}",
            "trade_allowed": bool(getattr(account_info, 'trade_allowed', False)),
            "trade_expert": bool(getattr(account_info, 'trade_expert', False)),
            
            # Timestamps
            "lastUpdate": datetime.now().isoformat(),
            "summary_generated": datetime.now().isoformat()
        }
        
        # Add aliases for frontend compatibility
        account_summary['freeMargin'] = account_summary['margin_free']
        account_summary['marginLevel'] = account_summary['margin_level']
        account_summary['profit'] = account_summary['total_profit']  # For backward compatibility
        
        log.info(f"Generated account summary: Balance={account_summary['balance']:.2f}, "
                f"Realized={realized_profit:.2f}, Unrealized={unrealized_profit:.2f}, "
                f"Total={account_summary['total_profit']:.2f}, Win Rate={account_summary['win_rate']:.1f}%")
        
        return jsonify(account_summary)
        
    except Exception as e:
        log.error(f"Error generating account summary: {e}", exc_info=True)
        return jsonify({"error": "Failed to generate account summary"}), 500

@app.route('/realized-profit')
def get_realized_profit():
    """Get realized profit from closed trades only (deprecated - use /account-summary instead)"""
    if 'username' not in session:
        return jsonify({"error": "Please login to access realized profit"}), 401
    
    try:
        if not is_mt5_connected():
            return jsonify({"error": "MT5 connection not available"}), 503
        
        # Set date range for the last 6 months (180 days)
        date_to = datetime.now()
        date_from = date_to - timedelta(days=180)
        
        # Get historical deals (completed trades)
        deals = []
        try:
            deals = mt5.history_deals_get(date_from, date_to)
            if deals is None:
                deals = []
        except Exception as e:
            log.error(f"Error fetching deals for realized profit: {e}")
            deals = []
        
        # Calculate total realized profit from deals
        total_realized_profit = 0
        for deal in deals:
            try:
                # Only include actual trade deals (not balance operations)
                deal_type = getattr(deal, 'type', -1)
                if deal_type in [0, 1]:  # BUY or SELL deals
                    profit = float(getattr(deal, 'profit', 0))
                    commission = float(getattr(deal, 'commission', 0))
                    swap = float(getattr(deal, 'swap', 0))
                    total_realized_profit += profit + commission + swap
            except Exception as e:
                log.error(f"Error processing deal for realized profit: {e}")
                continue
        
        return jsonify({
            "realized_profit": total_realized_profit,
            "currency": "USD",
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        log.error(f"Error calculating realized profit: {e}", exc_info=True)
        return jsonify({"error": "Failed to calculate realized profit"}), 500

# --- Removed duplicate endpoint - using /account instead ---

# --- Removed duplicate endpoint - using /trade-history instead ---

# --- MODIFIED /data Route with enhanced rate limiting ---
@app.route('/data')
def get_historical_data():
    """Provides historical data for the chart's initial load based on bar count."""
    client_ip = request.remote_addr
    current_time = time.time()
    timeframe_str = request.args.get('timeframe', default='1m')
    
    # Track how many requests we get for this IP and timeframe in a short period
    counter_key = f"{client_ip}:{timeframe_str}"
    
    # Initialize or increment the counter
    if counter_key in DATA_REQUEST_COUNTERS:
        if current_time - DATA_REQUEST_COUNTERS[counter_key]['first_time'] < 5:
            # Still in the counting window, increment counter
            DATA_REQUEST_COUNTERS[counter_key]['count'] += 1
            
            # If we're getting too many requests in a short time, add a delay
            if DATA_REQUEST_COUNTERS[counter_key]['count'] > 10:
                # Log a warning but only once per 10 seconds
                if current_time - DATA_REQUEST_COUNTERS[counter_key].get('warning_time', 0) > 10:
                    log.warning(f"Rate limiting client {client_ip} - received {DATA_REQUEST_COUNTERS[counter_key]['count']} requests in 5s")
                    DATA_REQUEST_COUNTERS[counter_key]['warning_time'] = current_time
                
                # Add a small delay to slow down client requests
                time.sleep(0.5)
        else:
            # Reset counter if it's been more than 5 seconds
            DATA_REQUEST_COUNTERS[counter_key] = {
                'count': 1,
                'first_time': current_time
            }
    else:
        # First request from this IP for this timeframe
        DATA_REQUEST_COUNTERS[counter_key] = {
            'count': 1,
            'first_time': current_time
        }
    
    # Check if we've logged a request from this IP recently to reduce log spam
    if client_ip in DATA_REQUEST_RATE_LIMIT:
        last_log_time = DATA_REQUEST_RATE_LIMIT[client_ip]
        if current_time - last_log_time < LOG_RATE_LIMIT:
            # Still in rate limit window, process without logging
            timeframes = {"1m": mt5.TIMEFRAME_M1, "5m": mt5.TIMEFRAME_M5, "1h": mt5.TIMEFRAME_H1, "4h": mt5.TIMEFRAME_H4, "1d": mt5.TIMEFRAME_D1, "1w": mt5.TIMEFRAME_W1}
            mt5_timeframe = timeframes.get(timeframe_str)
            if mt5_timeframe is None: return jsonify({"error": "Invalid timeframe"}), 400

            # Check MT5 connection first
            if not is_mt5_connected():
                # Instead of just 503, return dummy candles to help client rendering
                log.warning(f"MT5 not connected for data request - generating dummy data for timeframe {timeframe_str}")
                # Generate 20 dummy candles
                dummy_data = []
                now = int(datetime.now().timestamp())
                
                # Create appropriate time interval based on timeframe
                if timeframe_str == "1m": interval = 60
                elif timeframe_str == "5m": interval = 300
                elif timeframe_str == "1h": interval = 3600
                elif timeframe_str == "4h": interval = 14400
                elif timeframe_str == "1d": interval = 86400
                elif timeframe_str == "1w": interval = 604800
                else: interval = 60
                
                # Generate 50 candles for requested timeframe
                for i in range(50):
                    time_point = now - (interval * (50-i))
                    dummy_candle = create_dummy_candle()
                    dummy_candle['time'] = time_point
                    dummy_data.append(dummy_candle)
                
                # Include an error flag that frontend can detect
                return jsonify({
                    "data": dummy_data,
                    "error": "MT5 connection lost",
                    "dummy_data": True
                }), 200
            
            try:
                rates = mt5.copy_rates_from_pos(SYMBOL, mt5_timeframe, 0, HISTORY_COUNT)
            except Exception as e: 
                log.error(f"MT5 Error /data: {e}", exc_info=True)
                # Return dummy data with error flag
                log.warning(f"MT5 error for data request - generating dummy data for timeframe {timeframe_str}")
                # Generate 20 dummy candles
                dummy_data = []
                now = int(datetime.now().timestamp())
                
                # Create appropriate time interval based on timeframe
                if timeframe_str == "1m": interval = 60
                elif timeframe_str == "5m": interval = 300
                elif timeframe_str == "1h": interval = 3600
                elif timeframe_str == "4h": interval = 14400
                elif timeframe_str == "1d": interval = 86400
                elif timeframe_str == "1w": interval = 604800
                else: interval = 60
                
                # Generate 50 candles for requested timeframe
                for i in range(50):
                    time_point = now - (interval * (50-i))
                    dummy_candle = create_dummy_candle()
                    dummy_candle['time'] = time_point
                    dummy_data.append(dummy_candle)
                
                return jsonify({
                    "data": dummy_data,
                    "error": f"MT5 Error: {str(e)}",
                    "dummy_data": True
                }), 200

            if rates is None: 
                log.error(f"MT5 returned null for rates: {mt5.last_error()}")
                # Return dummy data with error flag instead of error
                # Same approach as above
                dummy_data = []
                now = int(datetime.now().timestamp())
                interval = 60  # Default to 1 minute
                if timeframe_str == "5m": interval = 300
                elif timeframe_str == "1h": interval = 3600
                elif timeframe_str == "4h": interval = 14400
                elif timeframe_str == "1d": interval = 86400
                elif timeframe_str == "1w": interval = 604800
                
                for i in range(50):
                    time_point = now - (interval * (50-i))
                    dummy_candle = create_dummy_candle()
                    dummy_candle['time'] = time_point
                    dummy_data.append(dummy_candle)
                
                return jsonify({
                    "data": dummy_data, 
                    "error": f"MT5 Error: {mt5.last_error()}",
                    "dummy_data": True
                }), 200
            
            if len(rates) == 0: return jsonify([])

            data = [format_candle(rate) for rate in rates if rate is not None]
            data.sort(key=lambda x: x['time'])
            return jsonify(data)
    
    # Update the last log time
    DATA_REQUEST_RATE_LIMIT[client_ip] = current_time
    
    # Log full request details (this will only happen once every LOG_RATE_LIMIT seconds per IP)
    log.info(f"Received request for /data with timeframe: {timeframe_str}")
    timeframes = {"1m": mt5.TIMEFRAME_M1, "5m": mt5.TIMEFRAME_M5, "1h": mt5.TIMEFRAME_H1, "4h": mt5.TIMEFRAME_H4, "1d": mt5.TIMEFRAME_D1, "1w": mt5.TIMEFRAME_W1}
    mt5_timeframe = timeframes.get(timeframe_str)
    if mt5_timeframe is None: return jsonify({"error": "Invalid timeframe"}), 400

    # Use copy_rates_from_pos based on HISTORY_COUNT
    log.info(f"Requesting last {HISTORY_COUNT} rates for {SYMBOL} on {timeframe_str}")
    
    # Check MT5 connection first (same code as above, for the logged version)
    if not is_mt5_connected():
        log.warning(f"MT5 not connected for data request - generating dummy data for timeframe {timeframe_str}")
        dummy_data = []
        now = int(datetime.now().timestamp())
        
        # Create appropriate time interval based on timeframe
        if timeframe_str == "1m": interval = 60
        elif timeframe_str == "5m": interval = 300
        elif timeframe_str == "1h": interval = 3600
        elif timeframe_str == "4h": interval = 14400
        elif timeframe_str == "1d": interval = 86400
        elif timeframe_str == "1w": interval = 604800
        else: interval = 60
        
        # Generate 50 candles for requested timeframe
        for i in range(50):
            time_point = now - (interval * (50-i))
            dummy_candle = create_dummy_candle()
            dummy_candle['time'] = time_point
            dummy_data.append(dummy_candle)
        
        return jsonify({
            "data": dummy_data,
            "error": "MT5 connection lost",
            "dummy_data": True
        }), 200
    
    try:
        rates = mt5.copy_rates_from_pos(SYMBOL, mt5_timeframe, 0, HISTORY_COUNT)
    except Exception as e: 
        log.error(f"MT5 Error /data: {e}", exc_info=True)
        # Return dummy data as above
        dummy_data = []
        now = int(datetime.now().timestamp())
        interval = 60  # Default to 1 minute
        if timeframe_str == "5m": interval = 300
        elif timeframe_str == "1h": interval = 3600
        elif timeframe_str == "4h": interval = 14400
        elif timeframe_str == "1d": interval = 86400
        elif timeframe_str == "1w": interval = 604800
        
        for i in range(50):
            time_point = now - (interval * (50-i))
            dummy_candle = create_dummy_candle()
            dummy_candle['time'] = time_point
            dummy_data.append(dummy_candle)
        
        return jsonify({
            "data": dummy_data, 
            "error": f"MT5 Error: {str(e)}",
            "dummy_data": True
        }), 200

    if rates is None: 
        # Same approach, return dummy data
        dummy_data = []
        now = int(datetime.now().timestamp())
        interval = 60  # Default to 1 minute
        if timeframe_str == "5m": interval = 300
        elif timeframe_str == "1h": interval = 3600
        elif timeframe_str == "4h": interval = 14400
        elif timeframe_str == "1d": interval = 86400
        elif timeframe_str == "1w": interval = 604800
        
        for i in range(50):
            time_point = now - (interval * (50-i))
            dummy_candle = create_dummy_candle()
            dummy_candle['time'] = time_point
            dummy_data.append(dummy_candle)
        
        return jsonify({
            "data": dummy_data, 
            "error": f"MT5 Error: {mt5.last_error()}",
            "dummy_data": True
        }), 200
    
    if len(rates) == 0: log.warning(f"No historical rates received."); return jsonify([])

    data = [format_candle(rate) for rate in rates if rate is not None]
    # IMPORTANT: Sort ascending by time because copy_rates_from_pos returns newest first
    data.sort(key=lambda x: x['time'])
    
    # Only log the number of points, not the entire content
    log.info(f"Formatted and returning {len(data)} historical points for {timeframe_str}")
    return jsonify(data)

@app.route('/account-info')
def account_info():
    log.info("Received request for /account-info")
    
    try:
        # Safe MT5 account info check
        account = None
        try:
            account = mt5.account_info()
        except Exception as e:
            log.error(f"MT5 account info error: {e}")
            return jsonify({"error": "MT5 account info not available"}), 503
            
        if account is None:
            return jsonify({"error": "MT5 account info not available"}), 503
            
        # Return account info
        return jsonify({
            "balance": account.balance,
            "equity": account.equity,
            "margin": account.margin,
            "freeMargin": account.margin_free,
            "marginLevel": account.margin_level,
            "profit": account.profit
        })
    except Exception as e:
        log.error(f"Error in account-info endpoint: {e}", exc_info=True)
        return jsonify({"error": "Failed to get account information"}), 500

@app.route('/signup', methods=['POST'])
def signup():
    log.info("Received signup request")
    try:
        data = request.json
        if not data:
            log.error("No JSON data in request")
            return jsonify({'error': 'Missing request data'}), 400
            
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            log.error("Missing username or password")
            return jsonify({'error': 'Username and password required'}), 400
            
        if username in users:
            log.warning(f"Signup failed: User {username} already exists")
            return jsonify({'error': 'User already exists'}), 409
            
        # Store user
        users[username] = password
        session['username'] = username
        
        # Try connecting to MT5 but don't fail if it doesn't work
        try:
            if not mt5_initialized:
                initialize_mt5()  # Try again for this user
        except Exception as e:
            log.error(f"MT5 connection error during signup: {e}")
            # We continue without MT5 - the user can still login
        
        log.info(f"User {username} signed up successfully")
        return jsonify({'message': 'Signup successful'}), 201
        
    except Exception as e:
        log.error(f"Error during signup: {e}", exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/login', methods=['POST'])
def login():
    log.info("Received login request")
    try:
        data = request.json
        if not data:
            log.error("No JSON data in login request")
            return jsonify({'error': 'Missing request data'}), 400
            
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            log.error("Missing username or password in login request")
            return jsonify({'error': 'Username and password required'}), 400
            
        if users.get(username) != password:
            log.warning(f"Login failed: Invalid credentials for user {username}")
            return jsonify({'error': 'Invalid credentials'}), 401
            
        session['username'] = username
        
        # Try connecting to MT5 but don't fail if it doesn't work
        try:
            if not mt5_initialized:
                initialize_mt5()
        except Exception as e:
            log.error(f"MT5 connection error during login: {e}")
            # We continue without MT5
        
        log.info(f"User {username} logged in successfully")
        return jsonify({'message': 'Login successful'}), 200
        
    except Exception as e:
        log.error(f"Error during login: {e}", exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('username', None)
    return jsonify({'message': 'Logged out'})

@app.route('/auth-check')
def auth_check():
    if 'username' in session:
        return jsonify({'authenticated': True, 'username': session['username']})
    return jsonify({'authenticated': False})

# --- MT5 Account endpoint - Returns data from connected MT5 account ---
@app.route('/account', methods=['GET'])
def get_account():
    log.info("Received request for MT5 account info")
    
    # Simple session check for web app access
    if 'username' not in session:
        log.warning("Unauthorized account info request - please login first")
        return jsonify({"error": "Please login to access account information"}), 401
    
    try:
        # Check MT5 connection
        if not is_mt5_connected():
            log.warning("MT5 not connected for account info request")
            return jsonify({"error": "MT5 connection not available"}), 503
        
        # Get real account data from MT5 - this returns data for the connected account
        account_info = mt5.account_info()
        if account_info is None:
            log.error(f"Failed to get account info from MT5: {mt5.last_error()}")
            return jsonify({"error": "Failed to retrieve account information from MT5"}), 500
        
        # Debug: Log all available account_info attributes
        log.info(f"MT5 account_info available attributes: {dir(account_info)}")
        
        # Build account data using REAL MT5 account ID and information
        account_data = {
            "id": int(getattr(account_info, 'login', 0)),  # Use REAL MT5 account login as ID
            "username": session.get('username', getattr(account_info, 'name', 'MT5 User')),  # Use session username, fallback to MT5 name
            "lastUpdate": datetime.now().isoformat()
        }
        
        # List of all known MT5 account_info fields
        all_mt5_fields = [
            'login', 'trade_mode', 'leverage', 'limit_orders', 'margin_so_mode',
            'trade_allowed', 'trade_expert', 'margin_so_call', 'margin_so_so',
            'currency', 'balance', 'credit', 'profit', 'equity', 'margin',
            'margin_free', 'margin_level', 'margin_call', 'margin_stop_out',
            'margin_initial', 'margin_maintenance', 'assets', 'liabilities',
            'commission_blocked', 'name', 'server', 'company'
        ]
        
        # Extract all available fields from MT5 account_info
        for field in all_mt5_fields:
            if hasattr(account_info, field):
                value = getattr(account_info, field)
                # Convert to appropriate type and add to account_data
                if field in ['balance', 'credit', 'profit', 'equity', 'margin', 'margin_free', 
                           'margin_level', 'margin_call', 'margin_stop_out', 'margin_initial', 
                           'margin_maintenance', 'assets', 'liabilities', 'commission_blocked']:
                    account_data[field] = float(value) if value is not None else 0.0
                elif field == 'leverage':
                    account_data[field] = f"1:{int(value)}" if value is not None else "1:100"
                elif field in ['trade_allowed', 'trade_expert']:
                    account_data[field] = bool(value) if value is not None else False
                elif field in ['login', 'limit_orders', 'margin_so_mode', 'trade_mode']:
                    account_data[field] = int(value) if value is not None else 0
                else:
                    # String fields like name, server, company, currency
                    account_data[field] = str(value) if value is not None else ""
                
                log.info(f"MT5 field '{field}': {account_data[field]} (type: {type(value).__name__})")
            else:
                log.debug(f"MT5 field '{field}' not available on this account")
        
        # Add aliases for frontend compatibility
        if 'margin_free' in account_data:
            account_data['freeMargin'] = account_data['margin_free']
        if 'margin_level' in account_data:
            account_data['marginLevel'] = account_data['margin_level']
        
        log.info(f"Successfully retrieved MT5 account info for login: {account_data.get('login', 'N/A')}")
        log.info(f"Total account data fields: {len(account_data)} - {list(account_data.keys())}")
        return jsonify(account_data)
        
    except Exception as e:
        log.error(f"Error fetching account info: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch account information"}), 500

# --- MT5 Trade History endpoint - Returns data from connected MT5 account ---
@app.route('/trade-history', methods=['GET'])
def get_trade_history():
    log.info("Received request for MT5 trade history")
    
    # Simple session check for web app access
    if 'username' not in session:
        log.warning("Unauthorized trade history request - please login first")
        return jsonify({"error": "Please login to access trade history"}), 401
    
    try:
        # Check MT5 connection
        if not is_mt5_connected():
            log.warning("MT5 not connected for trade history request")
            return jsonify({"error": "MT5 connection not available"}), 503
        
        # Set date range for the last 6 months (180 days) with extended current day coverage
        date_to = datetime.now() + timedelta(hours=1)  # Add 1 hour buffer for current day
        date_from = date_to - timedelta(days=180)
        
        log.info(f"Fetching MT5 trade history from {date_from} to {date_to}")
        
        # Get historical deals (completed trades) using history_deals_get
        deals = []
        try:
            deals = mt5.history_deals_get(date_from, date_to)
            if deals is None:
                log.warning(f"No deals returned from MT5: {mt5.last_error()}")
                # Try alternative approach - get today's deals separately
                today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                today_deals = mt5.history_deals_get(today_start, datetime.now())
                if today_deals:
                    deals = list(today_deals)
                    log.info(f"Retrieved {len(deals)} today's deals as fallback")
                else:
                    deals = []
            else:
                log.info(f"Retrieved {len(deals)} historical deals from {date_from.date()} to {date_to.date()}")
                
                # Also fetch today's deals separately to ensure we have the latest
                today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                today_deals = mt5.history_deals_get(today_start, datetime.now())
                if today_deals:
                    # Combine with existing deals, avoiding duplicates
                    existing_tickets = {getattr(d, 'ticket', 0) for d in deals}
                    new_deals = [d for d in today_deals if getattr(d, 'ticket', 0) not in existing_tickets]
                    if new_deals:
                        deals.extend(new_deals)
                        log.info(f"Added {len(new_deals)} additional today's deals")
                        
        except Exception as e:
            log.error(f"Error fetching deals: {e}", exc_info=True)
            deals = []
        
        # Get current open positions to add to the list
        current_positions = []
        try:
            current_positions = mt5.positions_get()
            if current_positions is None:
                current_positions = []
            log.info(f"Found {len(current_positions)} current open positions")
        except Exception as e:
            log.error(f"Error fetching open positions: {e}")
            current_positions = []
        
        # Group deals by position to get complete trades
        # Process deals to create closed trades
        closed_trades = []
        open_trades = []  # Initialize open_trades list
        deal_groups = {}
        
        # Group deals by position_id to form complete trades
        for deal in deals:
            try:
                position_id = getattr(deal, 'position_id', 0)
                deal_type = getattr(deal, 'type', -1)
                
                # Skip non-trade deals (balance operations, etc.)
                if deal_type not in [0, 1]:  # Only BUY or SELL deals
                    continue
                    
                if position_id > 0:  # Valid position ID
                    if position_id not in deal_groups:
                        deal_groups[position_id] = []
                    deal_groups[position_id].append(deal)
            except Exception as e:
                log.error(f"Error processing deal {getattr(deal, 'ticket', 'unknown')}: {e}")
                continue
        
        # Convert deal groups to trades - improved logic
        for position_id, position_deals in deal_groups.items():
            try:
                # Sort deals by time
                position_deals.sort(key=lambda d: getattr(d, 'time', 0))
                
                # We need at least one deal to create a trade record
                if len(position_deals) == 0:
                    continue
                
                # Find entry and exit deals
                entry_deal = None
                exit_deal = None
                
                # The first deal is typically the entry
                entry_deal = position_deals[0]
                
                # If we have multiple deals, the last one might be the exit
                if len(position_deals) > 1:
                    exit_deal = position_deals[-1]
                    
                    # Verify this is actually a closing deal by checking if it's the opposite type
                    entry_type = getattr(entry_deal, 'type', -1)
                    exit_type = getattr(exit_deal, 'type', -1)
                    
                    # If they're the same type, it's not a closing deal
                    if entry_type == exit_type:
                        exit_deal = None
                
                # Calculate total profit, commission, and swap from ALL deals in this position
                total_profit = 0.0
                total_commission = 0.0
                total_swap = 0.0
                total_volume = 0.0
                
                for deal in position_deals:
                    total_profit += float(getattr(deal, 'profit', 0))
                    total_commission += float(getattr(deal, 'commission', 0))
                    total_swap += float(getattr(deal, 'swap', 0))
                    total_volume += float(getattr(deal, 'volume', 0))
                
                # Determine trade type from entry deal
                entry_type = getattr(entry_deal, 'type', 0)
                if entry_type == 0:  # DEAL_TYPE_BUY
                    trade_type = "BUY"
                elif entry_type == 1:  # DEAL_TYPE_SELL
                    trade_type = "SELL"
                else:
                    # Skip non-trade deals
                    continue
                
                # Get trade details
                symbol = getattr(entry_deal, 'symbol', '')
                entry_price = float(getattr(entry_deal, 'price', 0))
                
                # Determine if trade is closed
                is_closed = exit_deal is not None
                
                if is_closed:
                    # Closed trade
                    exit_price = float(getattr(exit_deal, 'price', entry_price))
                    close_time = datetime.fromtimestamp(getattr(exit_deal, 'time', 0))
                    
                    # Calculate percentage change
                    change_percent = 0.0
                    if entry_price > 0 and exit_price > 0:
                        if trade_type == "BUY":
                            change_percent = ((exit_price - entry_price) / entry_price) * 100
                        else:  # SELL
                            change_percent = ((entry_price - exit_price) / entry_price) * 100
                    
                    # Create closed trade data
                    trade_data = {
                        "id": int(position_id),
                        "ticket": int(position_id),
                        "timestamp": datetime.fromtimestamp(getattr(entry_deal, 'time', 0)).isoformat(),
                        "time": datetime.fromtimestamp(getattr(entry_deal, 'time', 0)).isoformat(),
                        "close_time": close_time.isoformat(),
                        "symbol": symbol,
                        "type": trade_type,
                        "volume": float(getattr(entry_deal, 'volume', total_volume)),
                        "price": entry_price,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "current_price": exit_price,
                        "sl": 0.0,  # SL/TP not available in deals
                        "tp": 0.0,
                        "profit": total_profit + total_commission + total_swap,
                        "raw_profit": total_profit,
                        "commission": total_commission,
                        "swap": total_swap,
                        "change_percent": change_percent,
                        "comment": getattr(entry_deal, 'comment', ''),
                        "identifier": position_id,
                        "reason": getattr(exit_deal, 'reason', None) if exit_deal else None,
                        "is_open": False
                    }
                    
                    closed_trades.append(trade_data)
                    log.info(f"Processed closed trade {position_id}: {trade_type} {trade_data['volume']} {symbol} "
                            f"entry: {entry_price}, exit: {exit_price}, profit: {total_profit:.2f}")
                else:
                    # This might be a partially filled position or a position that's still open
                    # Check if it's in current positions
                    is_in_current_positions = any(
                        getattr(pos, 'ticket', 0) == position_id 
                        for pos in current_positions
                    )
                    
                    if not is_in_current_positions and len(position_deals) == 1:
                        # Single deal that's not in current positions - might be a closed trade
                        # where we only have the closing deal
                        current_price = entry_price
                        
                        # Create a record for this trade
                        trade_data = {
                            "id": int(position_id),
                            "ticket": int(position_id),
                            "timestamp": datetime.fromtimestamp(getattr(entry_deal, 'time', 0)).isoformat(),
                            "time": datetime.fromtimestamp(getattr(entry_deal, 'time', 0)).isoformat(),
                            "close_time": datetime.fromtimestamp(getattr(entry_deal, 'time', 0)).isoformat(),
                            "symbol": symbol,
                            "type": trade_type,
                            "volume": float(getattr(entry_deal, 'volume', 0)),
                            "price": entry_price,
                            "entry_price": entry_price,
                            "exit_price": entry_price,
                            "current_price": entry_price,
                            "sl": 0.0,
                            "tp": 0.0,
                            "profit": total_profit + total_commission + total_swap,
                            "raw_profit": total_profit,
                            "commission": total_commission,
                            "swap": total_swap,
                            "change_percent": 0.0,
                            "comment": getattr(entry_deal, 'comment', ''),
                            "identifier": position_id,
                            "reason": getattr(entry_deal, 'reason', None),
                            "is_open": False,
                            "single_deal": True  # Flag to indicate this is from a single deal
                        }
                        
                        if total_profit != 0:  # Only add if there's actual profit/loss
                            closed_trades.append(trade_data)
                            log.info(f"Added single-deal trade {position_id}: profit: {total_profit:.2f}")
                    
            except Exception as e:
                log.error(f"Error processing position {position_id}: {e}", exc_info=True)
                continue
        
        # Convert current open positions to trade format
        for position in current_positions:
            try:
                # Convert position type to readable format
                # Check if constants are available
                if hasattr(mt5, 'POSITION_TYPE_BUY'):
                    position_type = "BUY" if position.type == mt5.POSITION_TYPE_BUY else "SELL"
                else:
                    # Fallback for older MT5 versions or missing constants
                    position_type = "BUY" if getattr(position, 'type', 0) == 0 else "SELL"
                
                # Get position timestamps
                open_time = datetime.fromtimestamp(position.time) if hasattr(position, 'time') else datetime.now()
                
                # Calculate real profit
                real_profit = float(getattr(position, 'profit', 0))
                swap = float(getattr(position, 'swap', 0))
                commission = float(getattr(position, 'commission', 0))
                total_profit = real_profit + swap + commission
                
                # Get SL and TP
                sl = float(getattr(position, 'sl', 0))
                tp = float(getattr(position, 'tp', 0))
                
                # Get prices
                open_price = float(getattr(position, 'price_open', 0))
                current_price = float(getattr(position, 'price_current', open_price))
                
                # Calculate percentage change
                change_percent = 0.0
                if open_price > 0 and current_price > 0:
                    if position_type == "BUY":
                        change_percent = ((current_price - open_price) / open_price) * 100
                    else:  # SELL
                        change_percent = ((open_price - current_price) / open_price) * 100
                
                trade_data = {
                    "id": int(getattr(position, 'ticket', 0)),
                    "ticket": int(getattr(position, 'ticket', 0)),
                    "timestamp": open_time.isoformat(),
                    "time": open_time.isoformat(),
                    "close_time": None,
                    "symbol": getattr(position, 'symbol', ''),
                    "type": position_type,
                    "volume": float(getattr(position, 'volume', 0)),
                    "price": open_price,
                    "entry_price": open_price,
                    "exit_price": current_price,
                    "current_price": current_price,
                    "sl": sl,
                    "tp": tp,
                    "profit": total_profit,
                    "raw_profit": real_profit,
                    "commission": commission,
                    "swap": swap,
                    "change_percent": change_percent,
                    "comment": getattr(position, 'comment', ''),
                    "identifier": getattr(position, 'identifier', None),
                    "reason": None,
                    "is_open": True
                }
                
                open_trades.append(trade_data)
                log.info(f"Open Position {trade_data['ticket']}: {position_type} {trade_data['volume']} {trade_data['symbol']} "
                        f"at {open_price}, current: {current_price}, profit: {total_profit:.2f}, change: {change_percent:.2f}%")
                
            except Exception as position_error:
                log.error(f"Error processing open position {getattr(position, 'ticket', 'unknown')}: {position_error}")
                continue
        
        # Combine all trades (closed + open)
        all_trades = closed_trades + open_trades
        
        # Calculate summary statistics for logging
        total_closed_trades = len(closed_trades)
        total_open_trades = len(open_trades)
        total_realized_pl = sum(t['profit'] for t in closed_trades)
        total_unrealized_pl = sum(t['profit'] for t in open_trades)
        
        log.info(f"Trade processing summary: {total_closed_trades} closed trades, {total_open_trades} open positions")
        log.info(f"Realized P/L: ${total_realized_pl:.2f}, Unrealized P/L: ${total_unrealized_pl:.2f}")
        
        if len(all_trades) == 0:
            log.info("No trades found in MT5 account - returning empty list")
            return jsonify([])
        
        # Sort trades by time (newest first)
        try:
            all_trades.sort(key=lambda x: x['timestamp'], reverse=True)
        except Exception as sort_error:
            log.error(f"Error sorting trades: {sort_error}")
            # If sorting fails, return unsorted data
        
        log.info(f"Successfully retrieved {len(all_trades)} total trades from MT5 account")
        log.info(f"Final breakdown - Closed trades: {len(closed_trades)}, Open positions: {len(open_trades)}")
        
        return jsonify(all_trades)
        
    except Exception as e:
        log.error(f"Error fetching trade history: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch trade history"}), 500

# --- SocketIO Event Handlers (Corrected Signatures) ---
@socketio.on('check_connection')
def handle_check_connection():
    log.info(f"Connection check from client: {request.sid}")
    socketio.emit('connection_status', {
        'status': 'connected',
        'sid': request.sid,
        'timestamp': datetime.now().isoformat()
    }, room=request.sid)

@socketio.on('request_update')
def handle_request_update(data):
    """Handle client requests for immediate data updates"""
    sid = request.sid
    timeframe = data.get('timeframe', '1m')
    
    log.info(f"Client {sid} requested immediate update for timeframe {timeframe}")
    
    # Update the client's timeframe preference if it has changed
    client_timeframes[sid] = timeframe
    
    # Send an immediate update for the requested timeframe
    send_timeframe_update(sid, timeframe)
    
    # Send an acknowledgment
    socketio.emit('update_requested', {
        'status': 'success',
        'timeframe': timeframe,
        'timestamp': datetime.now().isoformat()
    }, room=sid)

@socketio.on('set_timeframe')
def handle_set_timeframe(data):
    """Handle client timeframe change requests"""
    sid = request.sid
    timeframe = data.get('timeframe', '1m')
    
    # Store the client's timeframe preference in the global dictionary
    client_timeframes[sid] = timeframe
    log.info(f"Client {sid} set timeframe to {timeframe}")
    
    # Send an acknowledgment
    socketio.emit('timeframe_set', {
        'status': 'success',
        'timeframe': timeframe,
        'timestamp': datetime.now().isoformat()
    }, room=sid)
    
    # Send an immediate update for the new timeframe
    send_timeframe_update(sid, timeframe)

@socketio.on('set_update_mode')
def handle_set_update_mode(data):
    sid = request.sid
    mode = data.get('mode', 'standard')
    
    # Store the client's update mode preference
    if not hasattr(handle_set_update_mode, 'client_update_modes'):
        handle_set_update_mode.client_update_modes = {}
    
    handle_set_update_mode.client_update_modes[sid] = mode
    log.info(f"Client {sid} set update mode to {mode}")
    
    # Send acknowledgment
    socketio.emit('update_mode_set', {
        'status': 'success',
        'mode': mode,
        'timestamp': datetime.now().isoformat()
    }, room=sid)

def send_timeframe_update(sid, timeframe_str):
    """Send an update for a specific timeframe to a specific client"""
    if timeframe_str not in timeframes_mt5_constants:
        log.warning(f"Invalid timeframe requested: {timeframe_str}, defaulting to 1m")
        timeframe_str = "1m"
    
    mt5_timeframe = timeframes_mt5_constants.get(timeframe_str, mt5.TIMEFRAME_M1)
    
    log.info(f"Sending {timeframe_str} timeframe update to client {sid}")
    
    # Prevent flooding by checking last emission time
    current_time = time.time()
    last_emission_key = f"{sid}:{timeframe_str}"
    last_emission_time = getattr(send_timeframe_update, 'last_emissions', {}).get(last_emission_key, 0)
    
    # Initialize the dictionary if it doesn't exist
    if not hasattr(send_timeframe_update, 'last_emissions'):
        send_timeframe_update.last_emissions = {}
        
    # Only send if it's been at least 1 second since the last emission for this client/timeframe
    if current_time - last_emission_time < 1.0:
        log.info(f"Skipping {timeframe_str} update for {sid} (rate limited)")
        return
        
    try:
        # Check if MT5 is connected
        if is_mt5_connected():
            try:
                # Get historical data for the requested timeframe
                # Fetch 2 candles to show trend
                rates = mt5.copy_rates_from_pos(SYMBOL, mt5_timeframe, 0, 2)
                
                if rates is not None and len(rates) > 0:
                    # Format the most recent candle
                    candle_data = format_candle(rates[0])
                    if candle_data:
                        # Add the timeframe to the data so client knows what timeframe this is for
                        candle_data['timeframe'] = timeframe_str
                        
                        # Send the data to the specific client
                        socketio.emit('price_update', candle_data, room=sid)
                        send_timeframe_update.last_emissions[last_emission_key] = current_time
                        log.info(f"Sent {timeframe_str} candle data to client {sid}")
                        
                        # If we have previous candle data, send that too for context
                        if len(rates) > 1:
                            prev_candle = format_candle(rates[1])
                            if prev_candle:
                                prev_candle['timeframe'] = timeframe_str
                                prev_candle['is_history'] = True  # Mark as historical data
                                socketio.emit('price_update', prev_candle, room=sid)
                        return
                    else:
                        raise ValueError("Failed to format candle data")
                else:
                    raise ValueError(f"No data returned from MT5: {mt5.last_error()}")
            except Exception as rates_err:
                log.error(f"Error fetching {timeframe_str} data: {rates_err}")
                # Fall through to dummy data
        else:
            log.warning(f"MT5 not connected, sending dummy data for {timeframe_str}")
        
        # If we get here, we need to send dummy data
        try:
            # Create and send dummy data as a fallback
            dummy_data = create_dummy_candle()
            dummy_data['time'] = int(time.time())  # Current time in seconds
            dummy_data['timeframe'] = timeframe_str
            dummy_data['is_dummy'] = True  # Mark as dummy data
            socketio.emit('price_update', dummy_data, room=sid)
            send_timeframe_update.last_emissions[last_emission_key] = current_time
            log.info(f"Sent emergency dummy data for timeframe {timeframe_str} to client {sid}")
            
            # Also send a connection status update
            socketio.emit('connection_status', {
                'status': 'disconnected',
                'message': 'Using simulated data - MT5 unavailable',
                'timestamp': datetime.now().isoformat()
            }, room=sid)
        except Exception as dummy_err:
            log.error(f"Failed to send emergency dummy data: {dummy_err}")
            # Emit a clear error to the client
            socketio.emit('error', {
                'message': 'Failed to retrieve market data',
                'timestamp': datetime.now().isoformat()
            }, room=sid)
    except Exception as e:
        log.error(f"Unexpected error in send_timeframe_update: {e}", exc_info=True)

@socketio.on('connect')
def handle_connect(auth=None):
    log.info(f"Client connected: {request.sid} (Auth: {auth})")
    # Send an immediate welcome message to confirm connection
    socketio.emit('connection_ack', {
        'status': 'connected', 
        'sid': request.sid,
        'timestamp': datetime.now().isoformat(),
        'server_info': {
            'version': 'TradePulse Backend 1.0',
            'python_version': sys.version,
            'symbol': SYMBOL,
            'mt5_connected': is_mt5_connected()
        }
    }, room=request.sid)
    
    # Get the requested timeframe from query parameters
    timeframe = request.args.get('timeframe', '1m')
    
    # Store the client's timeframe preference in the global dictionary
    client_timeframes[request.sid] = timeframe
    log.info(f"Client {request.sid} initial timeframe: {timeframe}")
    
    # Log socket engine and transport
    transport = request.environ.get('wsgi.websocket_version', 'Unknown transport')
    log.info(f"Client {request.sid} connected with transport: {transport}")
    
    # Send an immediate dummy update to confirm data flow works
    send_timeframe_update(request.sid, timeframe)
    
    # --- Start the background tasks if not running ---
    global thread, trade_monitor_thread
    with thread_lock:
        if thread is None:
            log.info("Starting background price updater task...")
            thread = socketio.start_background_task(target=background_price_updater)
            if thread: log.info("Background task started successfully.")
            else: log.error("Failed to start background task.")
        else: 
            log.info("Background task already running.")
        
        # Start trade monitor thread
        if trade_monitor_thread is None:
            log.info("Starting background trade monitor task...")
            trade_monitor_thread = socketio.start_background_task(target=background_trade_monitor)
            if trade_monitor_thread: log.info("Trade monitor task started successfully.")
            else: log.error("Failed to start trade monitor task.")
        else:
            log.info("Trade monitor task already running.")

@socketio.on('disconnect')
def handle_disconnect(*args):
    sid = request.sid
    log.info(f"Client disconnected: {sid}")
    
    # Clean up client's timeframe preference
    if sid in client_timeframes:
        del client_timeframes[sid]
        log.info(f"Removed client {sid} from timeframe tracking")
    
    socketio.emit('disconnect_ack', {'status': 'disconnected'}, room=sid)

@socketio.on_error_default
def default_error_handler(e):
    log.error(f"SocketIO Error: {e}", exc_info=True)
    socketio.emit('error_event', {'error': str(e)}, room=request.sid)

# Add a simple ping-pong handler to test the socket connection
@socketio.on('ping_server')
def handle_ping(data=None):
    log.info(f"Received ping from client: {request.sid}")
    socketio.emit('pong_client', {
        'timestamp': datetime.now().isoformat(),
        'server_time': datetime.now().strftime('%H:%M:%S'),
        'received_ping': data
    }, room=request.sid)

# Helper function to check MT5 connection
def is_mt5_connected():
    """Check if MT5 is connected safely"""
    try:
        term_info = mt5.terminal_info()
        return term_info is not None and hasattr(term_info, 'connected') and term_info.connected
    except Exception as e:
        log.error(f"Error checking MT5 connection: {e}")
        return False

# --- Trading Bot Integration ---

def bot_update_callback(data):
    """Callback function to handle bot updates and send to frontend"""
    try:
        # Send bot updates to all connected clients
        socketio.emit('bot_update', data)
        log.info(f"Sent bot update: {data.get('type', 'unknown')}")
    except Exception as e:
        log.error(f"Error sending bot update: {e}")

# Register bot update callback
bot_manager.register_update_callback(bot_update_callback)

# Trading Bot API Routes
@app.route('/bot/status', methods=['GET'])
def get_bot_status():
    """Get current bot status"""
    try:
        status = bot_manager.get_bot_status()
        return jsonify({
            'success': True,
            'data': status
        })
    except Exception as e:
        log.error(f"Error getting bot status: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/bot/start', methods=['POST'])
def start_bot():
    """Start the trading bot"""
    try:
        data = request.get_json() or {}
        strategy = data.get('strategy', 'default')
        
        success = bot_manager.start_bot(strategy)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Bot started with strategy: {strategy}'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to start bot'
            }), 400
            
    except Exception as e:
        log.error(f"Error starting bot: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/bot/stop', methods=['POST'])
def stop_bot():
    """Stop the trading bot"""
    try:
        success = bot_manager.stop_bot()
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Bot stopped successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Bot was not running'
            }), 400
            
    except Exception as e:
        log.error(f"Error stopping bot: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/bot/config', methods=['GET', 'POST'])
def bot_config():
    """Get or update bot configuration"""
    if request.method == 'GET':
        try:
            config = bot_manager.config
            return jsonify({
                'success': True,
                'data': config
            })
        except Exception as e:
            log.error(f"Error getting bot config: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    elif request.method == 'POST':
        try:
            new_config = request.get_json() or {}
            bot_manager.update_config(new_config)
            
            return jsonify({
                'success': True,
                'message': 'Configuration updated',
                'data': bot_manager.config
            })
            
        except Exception as e:
            log.error(f"Error updating bot config: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

@app.route('/bot/strategies', methods=['GET'])
def get_strategies():
    """Get available trading strategies"""
    try:
        strategies = bot_manager.get_available_strategies()
        return jsonify({
            'success': True,
            'data': strategies
        })
    except Exception as e:
        log.error(f"Error getting strategies: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Trading Bot WebSocket Events
@socketio.on('bot_start')
def handle_bot_start(data):
    """Handle bot start request via WebSocket"""
    try:
        strategy = data.get('strategy', 'default') if data else 'default'
        success = bot_manager.start_bot(strategy)
        
        socketio.emit('bot_start_response', {
            'success': success,
            'strategy': strategy,
            'timestamp': datetime.now().isoformat()
        }, room=request.sid)
        
    except Exception as e:
        log.error(f"Error in bot_start handler: {e}")
        socketio.emit('bot_error', {
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, room=request.sid)

@socketio.on('bot_stop')
def handle_bot_stop(data):
    """Handle bot stop request via WebSocket"""
    try:
        success = bot_manager.stop_bot()
        
        socketio.emit('bot_stop_response', {
            'success': success,
            'timestamp': datetime.now().isoformat()
        }, room=request.sid)
        
    except Exception as e:
        log.error(f"Error in bot_stop handler: {e}")
        socketio.emit('bot_error', {
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, room=request.sid)

@socketio.on('bot_config_update')
def handle_bot_config_update(data):
    """Handle bot configuration update via WebSocket"""
    try:
        if data:
            bot_manager.update_config(data)
            
        socketio.emit('bot_config_response', {
            'success': True,
            'config': bot_manager.config,
            'timestamp': datetime.now().isoformat()
        }, room=request.sid)
        
    except Exception as e:
        log.error(f"Error in bot_config_update handler: {e}")
        socketio.emit('bot_error', {
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, room=request.sid)

# --- Main Execution Block ---
if __name__ == "__main__":
    # Setup better error handling for the server start
    log.info(f"Preparing server for {SYMBOL}...")
    
    # Try to initialize MT5 but continue even if it fails
    if not mt5.initialize():
        log.warning(f"MT5 initialization failed: {mt5.last_error()}, but continuing with dummy data")
    
    log.info(f"Starting Flask-SocketIO server using eventlet on http://0.0.0.0:5000")
    log.info(f"Socket.IO path: /socket.io")
    
    try:
        # Ensure these parameters for better socket performance
        socketio.run(app, 
                    host='0.0.0.0', 
                    port=5000, 
                    debug=False, 
                    use_reloader=False, 
                    log_output=True,
                    allow_unsafe_werkzeug=True)
    except Exception as e: 
        log.critical(f"Server failed: {e}", exc_info=True)
    finally:
        log.info("Server stopping. Shutting down MT5...")
        mt5.shutdown()
        log.info("MT5 shut down.")