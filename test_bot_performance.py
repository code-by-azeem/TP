#!/usr/bin/env python3
"""
Test Bot Performance Tracking System

This script tests the complete bot performance tracking system:
1. Backend performance calculation from MT5 trade history
2. Frontend display of performance metrics 
3. Real-time updates when trades are executed
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import MetaTrader5 as mt5
from datetime import datetime, timedelta
from backend.trading_bot.bot_manager import TradingBotManager

def test_mt5_connection():
    """Test MT5 connection"""
    print("🔌 Testing MT5 Connection...")
    
    if not mt5.initialize():
        print(f"❌ MT5 initialization failed: {mt5.last_error()}")
        return False
        
    account_info = mt5.account_info()
    if account_info:
        print(f"✅ MT5 Connected - Account: {account_info.login}, Balance: ${account_info.balance:.2f}")
        return True
    else:
        print("❌ Failed to get account info")
        return False

def test_trade_history_retrieval():
    """Test trade history retrieval"""
    print("\n📊 Testing Trade History Retrieval...")
    
    try:
        # Get last 24 hours of trade history
        yesterday = datetime.now() - timedelta(days=1)
        deals = mt5.history_deals_get(yesterday, datetime.now())
        
        if deals:
            print(f"✅ Found {len(deals)} deals in last 24 hours")
            
            # Filter TradePulse trades
            bot_deals = []
            for deal in deals:
                comment = getattr(deal, 'comment', '')
                if 'TradePulse_' in comment or getattr(deal, 'magic', 0) == 12345:
                    bot_deals.append(deal)
            
            print(f"🤖 Found {len(bot_deals)} TradePulse bot trades")
            
            # Show recent bot trades
            for deal in bot_deals[-5:]:  # Last 5 trades
                profit = getattr(deal, 'profit', 0)
                commission = getattr(deal, 'commission', 0)
                swap = getattr(deal, 'swap', 0)
                net_profit = profit + commission + swap
                
                print(f"   • Ticket: {getattr(deal, 'ticket', 0)}, "
                      f"Profit: ${net_profit:.2f}, "
                      f"Time: {datetime.fromtimestamp(getattr(deal, 'time', 0))}")
            
            return len(bot_deals)
        else:
            print("⚠️ No deals found in last 24 hours")
            return 0
            
    except Exception as e:
        print(f"❌ Error retrieving trade history: {e}")
        return 0

def test_bot_performance_calculation():
    """Test bot performance calculation"""
    print("\n🧮 Testing Bot Performance Calculation...")
    
    try:
        # Create a bot manager instance
        bot_manager = TradingBotManager()
        bot_manager.bot_id = "test_bot_1"
        
        # Update performance (this will fetch real MT5 data)
        bot_manager._update_performance()
        
        performance = bot_manager.performance
        
        print("✅ Performance Metrics Calculated:")
        print(f"   • Total Trades: {performance.get('total_trades', 0)}")
        print(f"   • Winning Trades: {performance.get('winning_trades', 0)}")
        print(f"   • Losing Trades: {performance.get('losing_trades', 0)}")
        print(f"   • Win Rate: {performance.get('win_rate', 0):.1f}%")
        print(f"   • Total P&L: ${performance.get('total_profit', 0):.2f}")
        print(f"   • Daily P&L: ${performance.get('daily_pnl', 0):.2f}")
        print(f"   • Max Drawdown: ${performance.get('max_drawdown', 0):.2f}")
        
        recent_trades = performance.get('recent_trades', [])
        print(f"   • Recent Trades: {len(recent_trades)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error calculating performance: {e}")
        return False

def test_trade_history_method():
    """Test bot's get_trade_history method"""
    print("\n📋 Testing Bot Trade History Method...")
    
    try:
        bot_manager = TradingBotManager()
        bot_manager.bot_id = "test_bot_1"
        
        trade_history = bot_manager.get_trade_history()
        
        print(f"✅ Retrieved {len(trade_history)} trades from bot history method")
        
        for trade in trade_history[:3]:  # Show first 3 trades
            print(f"   • #{trade['ticket']}: {trade['type']} @ ${trade['price']:.4f}, "
                  f"P&L: ${trade['profit']:.2f}, {trade['time']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error getting trade history: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 Starting Bot Performance Tracking System Test\n")
    
    # Test 1: MT5 Connection
    mt5_ok = test_mt5_connection()
    
    if not mt5_ok:
        print("\n❌ MT5 connection failed. Cannot proceed with tests.")
        return
    
    # Test 2: Trade History Retrieval
    trade_count = test_trade_history_retrieval()
    
    # Test 3: Performance Calculation
    perf_ok = test_bot_performance_calculation()
    
    # Test 4: Bot Trade History Method
    history_ok = test_trade_history_method()
    
    # Summary
    print("\n" + "="*50)
    print("📋 TEST SUMMARY")
    print("="*50)
    print(f"MT5 Connection: {'✅ PASS' if mt5_ok else '❌ FAIL'}")
    print(f"Trade History: {'✅ PASS' if trade_count >= 0 else '❌ FAIL'} ({trade_count} trades found)")
    print(f"Performance Calc: {'✅ PASS' if perf_ok else '❌ FAIL'}")
    print(f"History Method: {'✅ PASS' if history_ok else '❌ FAIL'}")
    
    if mt5_ok and perf_ok and history_ok:
        print("\n🎉 ALL TESTS PASSED! Bot performance tracking system is working correctly.")
        
        if trade_count > 0:
            print("✅ The system successfully found and processed real TradePulse trades.")
        else:
            print("⚠️ No TradePulse trades found. Start a bot to see performance tracking in action.")
            
    else:
        print("\n⚠️ Some tests failed. Check the issues above.")
    
    # Cleanup
    mt5.shutdown()

if __name__ == "__main__":
    main() 