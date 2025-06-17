import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './TradingBot.css';

const TradingBot = ({ socket }) => {
  const [botStatus, setBotStatus] = useState({
    is_running: false,
    strategy: 'default',
    auto_trading: false,
    performance: {},
    active_trades: 0,
    config: {}
  });
  
  const [strategies, setStrategies] = useState(['default']);
  const [selectedStrategy, setSelectedStrategy] = useState('default');
  const [loading, setLoading] = useState(false);
  const [botUpdates, setBotUpdates] = useState([]);
  const [config, setConfig] = useState({
    max_risk_per_trade: 0.02,
    max_daily_trades: 10,
    auto_trading_enabled: false,
    stop_loss_pips: 50,
    take_profit_pips: 100
  });

  // Socket event listeners
  useEffect(() => {
    if (!socket) return;

    // Listen for bot updates
    socket.on('bot_update', (data) => {
      console.log('Bot update received:', data);
      setBotUpdates(prev => [data, ...prev.slice(0, 9)]); // Keep last 10 updates
      
      if (data.type === 'bot_status') {
        setBotStatus(prev => ({
          ...prev,
          is_running: data.status === 'started'
        }));
      }
    });

    // Listen for bot responses
    socket.on('bot_start_response', (data) => {
      console.log('Bot start response:', data);
      if (data.success) {
        setBotStatus(prev => ({ ...prev, is_running: true, strategy: data.strategy }));
      }
      setLoading(false);
    });

    socket.on('bot_stop_response', (data) => {
      console.log('Bot stop response:', data);
      if (data.success) {
        setBotStatus(prev => ({ ...prev, is_running: false }));
      }
      setLoading(false);
    });

    socket.on('bot_config_response', (data) => {
      if (data.success) {
        setConfig(data.config);
      }
    });

    socket.on('bot_error', (data) => {
      console.error('Bot error:', data.error);
      setLoading(false);
    });

    return () => {
      socket.off('bot_update');
      socket.off('bot_start_response');
      socket.off('bot_stop_response');
      socket.off('bot_config_response');
      socket.off('bot_error');
    };
  }, [socket]);

  // Fetch initial data
  useEffect(() => {
    fetchBotStatus();
    fetchStrategies();
    fetchBotConfig();
  }, []);

  const fetchBotStatus = async () => {
    try {
      const response = await axios.get('http://localhost:5000/bot/status');
      if (response.data.success) {
        setBotStatus(response.data.data);
        setSelectedStrategy(response.data.data.strategy);
      }
    } catch (error) {
      console.error('Error fetching bot status:', error);
    }
  };

  const fetchStrategies = async () => {
    try {
      const response = await axios.get('http://localhost:5000/bot/strategies');
      if (response.data.success) {
        setStrategies(response.data.data);
      }
    } catch (error) {
      console.error('Error fetching strategies:', error);
    }
  };

  const fetchBotConfig = async () => {
    try {
      const response = await axios.get('http://localhost:5000/bot/config');
      if (response.data.success) {
        setConfig(response.data.data);
      }
    } catch (error) {
      console.error('Error fetching bot config:', error);
    }
  };

  const startBot = async () => {
    setLoading(true);
    try {
      if (socket) {
        socket.emit('bot_start', { strategy: selectedStrategy });
      } else {
        const response = await axios.post('http://localhost:5000/bot/start', {
          strategy: selectedStrategy
        });
        if (response.data.success) {
          setBotStatus(prev => ({ ...prev, is_running: true, strategy: selectedStrategy }));
        }
        setLoading(false);
      }
    } catch (error) {
      console.error('Error starting bot:', error);
      setLoading(false);
    }
  };

  const stopBot = async () => {
    setLoading(true);
    try {
      if (socket) {
        socket.emit('bot_stop');
      } else {
        const response = await axios.post('http://localhost:5000/bot/stop');
        if (response.data.success) {
          setBotStatus(prev => ({ ...prev, is_running: false }));
        }
        setLoading(false);
      }
    } catch (error) {
      console.error('Error stopping bot:', error);
      setLoading(false);
    }
  };

  const updateConfig = async () => {
    try {
      if (socket) {
        socket.emit('bot_config_update', config);
      } else {
        const response = await axios.post('http://localhost:5000/bot/config', config);
        if (response.data.success) {
          setConfig(response.data.data);
        }
      }
    } catch (error) {
      console.error('Error updating config:', error);
    }
  };

  const handleConfigChange = (key, value) => {
    setConfig(prev => ({
      ...prev,
      [key]: value
    }));
  };

  const formatUpdateTime = (timestamp) => {
    return new Date(timestamp).toLocaleTimeString();
  };

  return (
    <div className="trading-bot-container">
      <div className="bot-header">
        <h2>Trading Bot Control</h2>
        <div className={`bot-status ${botStatus.is_running ? 'running' : 'stopped'}`}>
          <span className="status-indicator"></span>
          {botStatus.is_running ? 'Running' : 'Stopped'}
        </div>
      </div>

      <div className="bot-controls">
        <div className="control-group">
          <label>Strategy:</label>
          <select 
            value={selectedStrategy} 
            onChange={(e) => setSelectedStrategy(e.target.value)}
            disabled={botStatus.is_running}
          >
            {strategies.map(strategy => (
              <option key={strategy} value={strategy}>{strategy}</option>
            ))}
          </select>
        </div>

        <div className="bot-buttons">
          <button 
            onClick={startBot} 
            disabled={botStatus.is_running || loading}
            className="start-btn"
          >
            {loading ? 'Starting...' : 'Start Bot'}
          </button>
          <button 
            onClick={stopBot} 
            disabled={!botStatus.is_running || loading}
            className="stop-btn"
          >
            {loading ? 'Stopping...' : 'Stop Bot'}
          </button>
        </div>
      </div>

      <div className="bot-performance">
        <h3>Performance</h3>
        <div className="performance-grid">
          <div className="performance-item">
            <span>Total Trades:</span>
            <span>{botStatus.performance.total_trades || 0}</span>
          </div>
          <div className="performance-item">
            <span>Active Trades:</span>
            <span>{botStatus.active_trades || 0}</span>
          </div>
          <div className="performance-item">
            <span>Win Rate:</span>
            <span>{((botStatus.performance.win_rate || 0) * 100).toFixed(2)}%</span>
          </div>
          <div className="performance-item">
            <span>Daily P&L:</span>
            <span className={botStatus.performance.daily_pnl >= 0 ? 'positive' : 'negative'}>
              ${(botStatus.performance.daily_pnl || 0).toFixed(2)}
            </span>
          </div>
        </div>
      </div>

      <div className="bot-config">
        <h3>Configuration</h3>
        <div className="config-grid">
          <div className="config-item">
            <label>Max Risk per Trade:</label>
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              value={config.max_risk_per_trade}
              onChange={(e) => handleConfigChange('max_risk_per_trade', parseFloat(e.target.value))}
            />
          </div>
          <div className="config-item">
            <label>Max Daily Trades:</label>
            <input
              type="number"
              min="1"
              value={config.max_daily_trades}
              onChange={(e) => handleConfigChange('max_daily_trades', parseInt(e.target.value))}
            />
          </div>
          <div className="config-item">
            <label>Stop Loss (pips):</label>
            <input
              type="number"
              min="1"
              value={config.stop_loss_pips}
              onChange={(e) => handleConfigChange('stop_loss_pips', parseInt(e.target.value))}
            />
          </div>
          <div className="config-item">
            <label>Take Profit (pips):</label>
            <input
              type="number"
              min="1"
              value={config.take_profit_pips}
              onChange={(e) => handleConfigChange('take_profit_pips', parseInt(e.target.value))}
            />
          </div>
          <div className="config-item">
            <label>Auto Trading:</label>
            <input
              type="checkbox"
              checked={config.auto_trading_enabled}
              onChange={(e) => handleConfigChange('auto_trading_enabled', e.target.checked)}
            />
          </div>
        </div>
        <button onClick={updateConfig} className="update-config-btn">
          Update Configuration
        </button>
      </div>

      <div className="bot-updates">
        <h3>Recent Updates</h3>
        <div className="updates-list">
          {botUpdates.length === 0 ? (
            <div className="no-updates">No updates yet</div>
          ) : (
            botUpdates.map((update, index) => (
              <div key={index} className="update-item">
                <div className="update-time">{formatUpdateTime(update.timestamp)}</div>
                <div className="update-type">{update.type}</div>
                <div className="update-content">
                  {update.signal && (
                    <span className={`signal ${update.signal.type?.toLowerCase()}`}>
                      {update.signal.type} @ ${update.signal.price?.toFixed(4)}
                    </span>
                  )}
                  {update.current_price && (
                    <span>Price: ${update.current_price.toFixed(4)}</span>
                  )}
                  {update.status && (
                    <span className="status">{update.status}</span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

export default TradingBot; 