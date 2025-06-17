#!/usr/bin/env python3
"""
TradePulse Backend Startup Script
This script starts the Flask backend with trading bot integration
"""
import sys
import os
import logging
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

def check_dependencies():
    """Check if all required dependencies are installed"""
    required_packages = [
        'flask',
        'flask_socketio',
        'MetaTrader5',
        'numpy',
        'pandas',
        'eventlet'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ Missing required packages: {', '.join(missing_packages)}")
        print("Please install them using: pip install -r backend/requirements.txt")
        return False
    
    print("✅ All required packages are installed")
    return True

def check_mt5_connection():
    """Check MetaTrader 5 connection"""
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            print("✅ MetaTrader 5 connection successful")
            mt5.shutdown()
            return True
        else:
            print("⚠️  MetaTrader 5 connection failed - will use demo data")
            return False
    except Exception as e:
        print(f"⚠️  MetaTrader 5 error: {e} - will use demo data")
        return False

def start_application():
    """Start the TradePulse backend application"""
    try:
        # Change to backend directory
        os.chdir(backend_dir)
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        )
        
        print("\n🚀 Starting TradePulse Backend...")
        print("="*50)
        
        # Check dependencies
        if not check_dependencies():
            sys.exit(1)
        
        # Check MT5 connection
        check_mt5_connection()
        
        # Test bot integration
        print("🤖 Testing bot integration...")
        try:
            from trading_bot.bot_manager import bot_manager
            from trading_bot.strategies import list_strategies
            
            strategies = list_strategies()
            print(f"✅ Available strategies: {', '.join(strategies)}")
            
            status = bot_manager.get_bot_status()
            print(f"✅ Bot manager initialized successfully")
            
        except Exception as e:
            print(f"❌ Bot integration error: {e}")
            print("The application will start but bot features may not work")
        
        print("\n🌐 Starting Flask server...")
        print("📊 Dashboard: http://localhost:3000")
        print("🔌 API: http://localhost:5000")
        print("🛑 Press Ctrl+C to stop")
        print("="*50)
        
        # Start the main application
        import candlestickData
        
    except KeyboardInterrupt:
        print("\n👋 Shutting down TradePulse Backend...")
    except Exception as e:
        print(f"\n❌ Error starting application: {e}")
        sys.exit(1)

if __name__ == "__main__":
    start_application() 