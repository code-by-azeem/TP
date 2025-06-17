# 🚀 TradePulse - Advanced Trading Platform with Bot Integration

TradePulse is a comprehensive trading platform that combines real-time market data visualization with automated trading bot capabilities. Built with Flask/Python backend and React frontend, it integrates directly with MetaTrader 5 for live trading.

## ✨ Features

### 📊 **Trading Dashboard**
- Real-time candlestick charts with multiple timeframes
- Live price updates via WebSocket
- Account information and balance tracking
- Trade history and performance analytics
- Responsive, modern UI design

### 🤖 **Trading Bot Integration**
- Multiple trading strategies (MA Crossover, RSI, Breakout, Combined)
- Real-time signal generation and execution
- Configurable risk management
- Live bot status monitoring
- Custom strategy support

### 🔐 **Security & Authentication**
- User authentication system
- Session management
- Secure API endpoints
- CORS protection

### 🌐 **Real-time Communication**
- WebSocket integration for live updates
- Bot status notifications
- Real-time trade signals
- Market data streaming

## 🏗️ Architecture

```
TradePulse/
├── backend/                 # Flask API Server
│   ├── trading_bot/        # Trading Bot Package
│   │   ├── bot_manager.py  # Main bot controller
│   │   ├── strategies.py   # Trading strategies
│   │   └── __init__.py     # Package init
│   ├── candlestickData.py  # Main Flask app
│   └── requirements.txt    # Python dependencies
├── frontend/               # React Application
│   ├── src/
│   │   └── components/
│   │       ├── Dashboard.js      # Main dashboard
│   │       ├── TradingBot.js     # Bot control UI
│   │       ├── CandlestickChart.js # Chart component
│   │       ├── TradeHistory.js   # Trade history
│   │       └── AccountInfo.js    # Account details
│   ├── package.json        # Node dependencies
│   └── public/             # Static files
├── start_backend.py        # Backend startup script
├── start_frontend.bat      # Frontend startup script
└── TRADING_BOT_INTEGRATION.md # Bot integration guide
```

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Node.js 16+
- MetaTrader 5 (for live trading)
- npm or yarn

### 1. **Clone and Setup**
```bash
git clone <your-repo-url>
cd TradePulse
```

### 2. **Backend Setup**
```bash
# Install Python dependencies
cd backend
pip install -r requirements.txt

# Or use the startup script (recommended)
cd ..
python start_backend.py
```

### 3. **Frontend Setup**
```bash
# Install and start frontend
cd frontend
npm install
npm start

# Or use the batch script (Windows)
cd ..
start_frontend.bat
```

### 4. **Access the Application**
- 📊 **Dashboard**: http://localhost:3000
- 🔌 **API**: http://localhost:5000
- 🤖 **Bot Control**: Dashboard → Trading Bot tab

## 🤖 Trading Bot Usage

### **Starting the Bot**
1. Navigate to the "Trading Bot" tab in the dashboard
2. Select a trading strategy
3. Configure risk parameters
4. Click "Start Bot"

### **Available Strategies**
- **MA Crossover**: Moving average crossover signals
- **RSI Strategy**: Oversold/overbought conditions
- **Breakout Strategy**: Support/resistance breakouts
- **Combined Strategy**: Multi-indicator consensus

### **Bot Configuration**
- **Max Risk per Trade**: 0.01 - 0.10 (1% - 10%)
- **Max Daily Trades**: Limit trading frequency
- **Stop Loss/Take Profit**: Risk management levels
- **Auto Trading**: Enable/disable automatic execution

## 🔧 Configuration

### **Environment Variables**
Create a `.env` file in the backend directory:
```env
MT5_SYMBOL=ETHUSD
MT5_LOGIN=your_login
MT5_PASSWORD=your_password
MT5_SERVER=your_server
FLASK_SECRET_KEY=your_secret_key
```

### **MetaTrader 5 Setup**
1. Install MetaTrader 5
2. Log in to your trading account
3. Enable API access in Tools → Options → Expert Advisors
4. Allow automated trading

## 📊 API Endpoints

### **Authentication**
- `POST /login` - User login
- `POST /logout` - User logout
- `GET /auth-check` - Check authentication status

### **Market Data**
- `GET /data` - Historical candlestick data
- `GET /status` - Server status
- `WebSocket /socket.io` - Real-time updates

### **Trading Bot**
- `GET /bot/status` - Bot status
- `POST /bot/start` - Start bot
- `POST /bot/stop` - Stop bot
- `GET /bot/config` - Get configuration
- `POST /bot/config` - Update configuration
- `GET /bot/strategies` - List strategies

### **Account**
- `GET /account` - Account information
- `GET /trade-history` - Trading history

## 🔌 WebSocket Events

### **Client → Server**
- `set_timeframe` - Change chart timeframe
- `bot_start` - Start trading bot
- `bot_stop` - Stop trading bot
- `bot_config_update` - Update bot config

### **Server → Client**
- `price_update` - Real-time price data
- `bot_update` - Bot status updates
- `bot_start_response` - Bot start confirmation
- `new_trade` - New trade notifications

## 🎯 Integrating Your Own Bot

See [TRADING_BOT_INTEGRATION.md](TRADING_BOT_INTEGRATION.md) for detailed instructions on integrating your existing trading bot code.

### **Quick Integration Steps**
1. Copy your bot code to `backend/trading_bot/`
2. Create a strategy class extending `BaseStrategy`
3. Implement the `analyze()` method
4. Add to `AVAILABLE_STRATEGIES` in `strategies.py`
5. Test with demo account first

## 🛠️ Development

### **Backend Development**
```bash
cd backend
python candlestickData.py
```

### **Frontend Development**
```bash
cd frontend
npm start
```

### **Adding New Features**
1. Backend: Add routes in `candlestickData.py`
2. Frontend: Create components in `src/components/`
3. Bot: Add strategies in `trading_bot/strategies.py`

## 📈 Performance & Monitoring

### **Bot Performance Metrics**
- Total trades executed
- Win rate percentage
- Daily P&L tracking
- Active trade monitoring
- Real-time signal generation

### **System Monitoring**
- WebSocket connection status
- MetaTrader 5 connectivity
- API response times
- Error logging and handling

## 🔒 Security Best Practices

1. **Never commit API keys** to version control
2. **Use environment variables** for sensitive data
3. **Test with demo accounts** before live trading
4. **Monitor bot performance** continuously
5. **Implement proper error handling**
6. **Use HTTPS** in production
7. **Regular security updates**

## 🐛 Troubleshooting

### **Common Issues**

**Bot not starting:**
- Check MetaTrader 5 connection
- Verify account credentials
- Check Python dependencies

**WebSocket connection failed:**
- Check CORS settings
- Verify port availability (5000, 3000)
- Check firewall settings

**No market data:**
- Ensure MetaTrader 5 is running
- Check symbol availability
- Verify market hours

**Import errors:**
- Install all requirements: `pip install -r backend/requirements.txt`
- Check Python path and virtual environment

### **Debug Mode**
Enable detailed logging:
```python
# In candlestickData.py
logging.basicConfig(level=logging.DEBUG)
```

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📞 Support

For support and questions:
- Create an issue on GitHub
- Check the troubleshooting section
- Review the integration guide

## 🔄 Version History

- **v1.0.0** - Initial release with basic trading dashboard
- **v1.1.0** - Added trading bot integration
- **v1.2.0** - Multiple strategy support and enhanced UI

---

**⚠️ Disclaimer**: Trading involves risk. This software is for educational purposes. Always test with demo accounts before live trading. The developers are not responsible for any financial losses.