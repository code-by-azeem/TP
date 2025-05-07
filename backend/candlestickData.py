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
from datetime import datetime
from threading import Lock
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
# dateutil is not needed for this bar count approach

# --- Configuration ---
load_dotenv()
SYMBOL = os.getenv("MT5_SYMBOL", "XAUUSD")
UPDATE_INTERVAL_SECONDS = 1 # Keeps the 1-second update interval
# Use HISTORY_COUNT for initial load - adjust as needed for performance/depth
HISTORY_COUNT = 5000

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(threadName)s %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

# --- Flask & SocketIO App Initialization ---
log.info("Initializing Flask application...")
app = Flask(__name__)
cors_origins = "http://localhost:3000"
CORS(app, resources={r"/*": {"origins": cors_origins}})
socketio = SocketIO(app, cors_allowed_origins=cors_origins, async_mode='eventlet')
log.info(f"Flask-SocketIO initialized. Allowed origins: {cors_origins}")

# --- MT5 Connection ---
def initialize_mt5():
    # Function remains unchanged - ensures proper MT5 setup
    log.info("Initializing MetaTrader 5 connection...")
    if not mt5.initialize(): log.error("MT5 init failed"); return False
    log.info(f"MT5 connection successful. Checking symbol: {SYMBOL}")
    symbol_info = mt5.symbol_info(SYMBOL)
    if not symbol_info: log.error(f"{SYMBOL} not found"); mt5.shutdown(); return False
    if not symbol_info.visible:
        log.warning(f"{SYMBOL} not visible, enabling...");
        if not mt5.symbol_select(SYMBOL, True): log.error(f"Failed to enable {SYMBOL}"); mt5.shutdown(); return False
        time.sleep(0.5); symbol_info = mt5.symbol_info(SYMBOL)
        if not symbol_info or not symbol_info.visible: log.error(f"Failed confirm {SYMBOL} visibility"); mt5.shutdown(); return False
        log.info(f"{SYMBOL} enabled.")
    else: log.info(f"{SYMBOL} is visible.")
    if not mt5.terminal_info(): log.error("Lost MT5 connection"); mt5.shutdown(); return False
    log.info("MT5 setup complete.")
    return True

if not initialize_mt5(): exit("Exiting: MT5 initialization failure.")

# --- Background Task ---
thread = None
thread_lock = Lock()

def format_candle(rate):
    # Function remains unchanged
    if rate is None or len(rate) < 5: return None
    return {'time': int(rate[0]), 'open': float(rate[1]), 'high': float(rate[2]), 'low': float(rate[3]), 'close': float(rate[4])}

def background_price_updater():
    # Function remains unchanged - emits latest M1 candle every second
    log.info("Background price updater task starting (1s interval emission).")
    while True:
        try:
            term_info = mt5.terminal_info()
            if term_info is None or term_info.connected is False: log.warning("MT5 Disconnected"); socketio.sleep(15); continue
            rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M1, 0, 1)
            if rates is not None and len(rates) > 0:
                latest_candle_data = format_candle(rates[0])
                if latest_candle_data: socketio.emit('price_update', latest_candle_data)
            else: log.warning(f"Could not fetch M1 rate. Err: {mt5.last_error()}")
        except Exception as e: log.error(f"BG Task Error: {e}", exc_info=True); socketio.sleep(10)
        socketio.sleep(UPDATE_INTERVAL_SECONDS)

# --- Flask Routes ---
@app.route('/status')
def status():
    # Endpoint remains unchanged
    log.info("Received request for /status")
    mt5_connected = False; term_info = mt5.terminal_info()
    if term_info is not None: mt5_connected = term_info.connected
    return jsonify({"status": "ok", "mt5_connected": mt5_connected, "symbol": SYMBOL, "timestamp": datetime.now().isoformat() })

# --- MODIFIED /data Route (Reverted to copy_rates_from_pos) ---
@app.route('/data')
def get_historical_data():
    """Provides historical data for the chart's initial load based on bar count."""
    timeframe_str = request.args.get('timeframe', default='1m')
    log.info(f"Received request for /data with timeframe: {timeframe_str}")
    timeframes = {"1m": mt5.TIMEFRAME_M1, "5m": mt5.TIMEFRAME_M5, "1h": mt5.TIMEFRAME_H1, "4h": mt5.TIMEFRAME_H4, "1d": mt5.TIMEFRAME_D1, "1w": mt5.TIMEFRAME_W1}
    mt5_timeframe = timeframes.get(timeframe_str)
    if mt5_timeframe is None: return jsonify({"error": "Invalid timeframe"}), 400

    # Use copy_rates_from_pos based on HISTORY_COUNT
    log.info(f"Requesting last {HISTORY_COUNT} rates for {SYMBOL} on {timeframe_str}")
    try:
        term_info = mt5.terminal_info()
        if term_info is None or term_info.connected is False: return jsonify({"error": "MT5 connection lost"}), 503
        rates = mt5.copy_rates_from_pos(SYMBOL, mt5_timeframe, 0, HISTORY_COUNT)
    except Exception as e: log.error(f"MT5 Error /data: {e}", exc_info=True); return jsonify({"error": "MT5 Error fetching history"}), 500

    if rates is None: return jsonify({"error": f"MT5 Error: {mt5.last_error()}"}), 500
    if len(rates) == 0: log.warning(f"No historical rates received."); return jsonify([])

    data = [format_candle(rate) for rate in rates if rate is not None]
    # IMPORTANT: Sort ascending by time because copy_rates_from_pos returns newest first
    data.sort(key=lambda x: x['time'])
    log.info(f"Formatted and returning {len(data)} historical points.")
    return jsonify(data)
# --- End of Modified /data Route ---

# --- SocketIO Event Handlers (Corrected Signatures) ---
@socketio.on('connect')
def handle_connect(auth=None):
    log.info(f"Client connected: {request.sid} (Auth: {auth})")
    # --- FIX: Separate global and with statements ---
    global thread
    with thread_lock:
    # --- End of Fix ---
        if thread is None: # Simplified check
            log.info("Starting background price updater task...")
            thread = socketio.start_background_task(target=background_price_updater)
            if thread: log.info("BG task started.")
            else: log.error("Failed to start BG task.")
        else: log.info("BG task already running.")

@socketio.on('disconnect')
def handle_disconnect(*args):
    # Handler remains unchanged
    log.info(f"Client disconnected: {request.sid}")

@socketio.on_error_default
def default_error_handler(e):
    # Handler remains unchanged
    log.error(f"SocketIO Error: {e}", exc_info=True)

# --- Main Execution Block ---
if __name__ == "__main__":
    # Block remains unchanged - checks MT5, uses socketio.run
    log.info(f"Preparing server for {SYMBOL}...")
    if not mt5.terminal_info() or not mt5.terminal_info().connected: log.critical("..."); exit()
    log.info(f"Starting Flask-SocketIO server using eventlet on http://0.0.0.0:5000")
    try:
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False, log_output=True)
    except Exception as e: log.critical(f"Server failed: {e}", exc_info=True)
    finally:
        log.info("Server stopping. Shutting down MT5..."); mt5.shutdown(); log.info("MT5 shut down.")