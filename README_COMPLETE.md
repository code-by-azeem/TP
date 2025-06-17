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

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Node.js 16+
- MetaTrader 5 (for live trading)
- npm or yarn

### 1. **Backend Setup**
```bash
# Install Python dependencies
cd backend
pip install -r requirements.txt

# Or use the startup script (recommended)
cd ..
python start_backend.py
```

### 2. **Frontend Setup**
```bash
# Install and start frontend
cd frontend
npm install
npm start

# Or use the batch script (Windows)
cd ..
start_frontend.bat
```

### 3. **Access the Application**
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

## 🎯 Integrating Your Own Bot

See [TRADING_BOT_INTEGRATION.md](TRADING_BOT_INTEGRATION.md) for detailed instructions.

## 📈 Performance & Monitoring

### **Bot Performance Metrics**
- Total trades executed
- Win rate percentage
- Daily P&L tracking
- Active trade monitoring
- Real-time signal generation

## 🔒 Security Best Practices

1. **Never commit API keys** to version control
2. **Use environment variables** for sensitive data
3. **Test with demo accounts** before live trading
4. **Monitor bot performance** continuously

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

---

**⚠️ Disclaimer**: Trading involves risk. This software is for educational purposes. Always test with demo accounts before live trading. 