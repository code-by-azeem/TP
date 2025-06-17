# Trading Bot Integration Guide

## Overview
Your TradePulse application now has a complete trading bot integration framework. This guide explains how to integrate your existing GitHub trading bot code with the current system.

## Integration Architecture

```
TradePulse/
├── backend/
│   ├── trading_bot/
│   │   ├── __init__.py
│   │   ├── bot_manager.py      # Main bot controller
│   │   ├── strategies.py       # Trading strategies
│   │   └── your_bot_code.py    # Your GitHub bot goes here
│   └── candlestickData.py      # Updated with bot APIs
└── frontend/
    └── src/components/
        ├── TradingBot.js       # Bot control UI
        └── TradingBot.css      # Bot styling
```

## Step-by-Step Integration

### 1. Add Your GitHub Bot Code

1. **Clone/Download your bot code** into `backend/trading_bot/`
2. **Rename your main bot file** to `your_bot_code.py` or keep original name
3. **Import your bot** in `bot_manager.py`

Example integration:
```python
# In bot_manager.py, add at the top:
from .your_bot_code import YourBotClass

# In TradingBotManager.__init__():
self.your_bot = YourBotClass()
```

### 2. Integrate Your Trading Logic

#### Option A: Use Existing Strategy Framework
Add your strategies to `strategies.py`:

```python
class YourCustomStrategy(BaseStrategy):
    def __init__(self, symbol: str = "ETHUSD"):
        super().__init__(symbol)
        self.name = "your_strategy_name"
        # Your initialization code
        
    def analyze(self, rates: np.ndarray) -> Optional[Dict]:
        # Your analysis logic here
        # Return signal dict or None
        pass
```

#### Option B: Replace Analysis Method
Replace `_analyze_market()` in `bot_manager.py`:

```python
def _analyze_market(self) -> Optional[Dict]:
    """Your custom market analysis"""
    try:
        # Use your existing bot logic
        signal = self.your_bot.get_signal()
        
        # Convert to our signal format:
        if signal:
            return {
                'type': signal['action'],  # 'BUY' or 'SELL'
                'price': signal['price'],
                'confidence': signal['confidence'],
                'strategy': 'your_strategy',
                'reason': signal.get('reason', '')
            }
        return None
    except Exception as e:
        log.error(f"Error in custom analysis: {e}")
        return None
```

### 3. Integrate Your Trade Execution

Update `_execute_trade()` method in `bot_manager.py`:

```python
def _execute_trade(self, signal: Dict):
    """Execute trade using your bot"""
    try:
        if not self.config['auto_trading_enabled']:
            log.info(f"Auto trading disabled, signal: {signal}")
            return
            
        # Use your existing trade execution logic
        result = self.your_bot.execute_trade(
            action=signal['type'],
            symbol=self.symbol,
            price=signal['price'],
            stop_loss=self.config['stop_loss_pips'],
            take_profit=self.config['take_profit_pips']
        )
        
        if result['success']:
            # Track the trade
            trade_id = result['trade_id']
            self.active_trades[trade_id] = {
                'signal': signal,
                'entry_time': datetime.now(),
                'status': 'active',
                'mt5_ticket': result.get('ticket')
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
```

### 4. Configure Your Bot Settings

Add your bot-specific settings to the config in `bot_manager.py`:

```python
self.config = {
    'max_risk_per_trade': 0.02,
    'max_daily_trades': 10,
    'auto_trading_enabled': False,
    'strategy_name': 'your_strategy',
    'stop_loss_pips': 50,
    'take_profit_pips': 100,
    
    # Your custom settings:
    'your_api_key': 'your_key',
    'your_secret': 'your_secret',
    'risk_management': True,
    # Add any other config your bot needs
}
```

## Running the Integrated System

### 1. Install Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Start Backend
```bash
cd backend
python candlestickData.py
```

### 3. Start Frontend
```bash
cd frontend
npm install
npm start
```

### 4. Access Bot Controls
1. Navigate to `http://localhost:3000`
2. Login to your account
3. Click "Trading Bot" tab
4. Configure and start your bot

## API Endpoints

The integration provides these endpoints:

- `GET /bot/status` - Get bot status
- `POST /bot/start` - Start bot with strategy
- `POST /bot/stop` - Stop bot
- `GET /bot/config` - Get configuration
- `POST /bot/config` - Update configuration
- `GET /bot/strategies` - List available strategies

## WebSocket Events

Real-time bot updates via WebSocket:

- `bot_update` - General bot updates
- `bot_start_response` - Start confirmation
- `bot_stop_response` - Stop confirmation
- `bot_config_response` - Config updates
- `bot_error` - Error notifications

## Customization Examples

### Example 1: Adding Your Indicator
```python
# In strategies.py
class YourIndicatorStrategy(BaseStrategy):
    def analyze(self, rates):
        # Your indicator calculation
        indicator_value = self.calculate_your_indicator(rates)
        
        if indicator_value > threshold:
            return {
                'type': 'BUY',
                'price': rates[-1][4],
                'confidence': 0.8,
                'strategy': 'your_indicator',
                'indicator_value': indicator_value
            }
        return None
```

### Example 2: Custom Risk Management
```python
# In bot_manager.py
def calculate_position_size(self, signal):
    """Your position sizing logic"""
    account_balance = self.get_account_balance()
    risk_amount = account_balance * self.config['max_risk_per_trade']
    
    # Your position size calculation
    position_size = your_position_size_logic(risk_amount, signal)
    
    return position_size
```

## Testing Your Integration

1. **Test with Demo Account First**
2. **Start with `auto_trading_enabled: false`**
3. **Monitor signals without executing trades**
4. **Gradually enable features**
5. **Check logs for any errors**

## Troubleshooting

### Common Issues:

1. **Import Errors**: Ensure your bot code is in the correct directory
2. **Strategy Not Found**: Check strategy name in `AVAILABLE_STRATEGIES`
3. **MT5 Connection**: Verify MetaTrader 5 is running and connected
4. **WebSocket Issues**: Check CORS settings and network connectivity

### Debug Mode:
Enable detailed logging in `candlestickData.py`:
```python
logging.basicConfig(level=logging.DEBUG)
```

## Security Considerations

1. **Never commit API keys** to version control
2. **Use environment variables** for sensitive data
3. **Test thoroughly** before live trading
4. **Implement proper error handling**
5. **Monitor bot performance** continuously

## Next Steps

1. **Integrate your GitHub bot code**
2. **Test with paper trading**
3. **Customize strategies as needed**
4. **Add performance analytics**
5. **Implement risk management rules**

---

**Note**: This integration framework is designed to be flexible. You can adapt it to work with any trading bot architecture while maintaining the UI and real-time communication features. 