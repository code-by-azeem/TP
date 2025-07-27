import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './TradingBot.css';

const TradingBot = ({ socket }) => {
  // Bot management state
  const [bots, setBots] = useState([]);
  const [botIdCounter, setBotIdCounter] = useState(1);
  const [selectedBotDetail, setSelectedBotDetail] = useState(null);
  
  // Strategy and configuration state
  const [strategies] = useState([
    'moving_average',
    'rsi_strategy', 
    'breakout_strategy',
    'combined_strategy',
    'bollinger_bands',
    'macd_strategy',        // New MACD strategy
    'stochastic_strategy',  // New Stochastic strategy
    'vwap_strategy',        // New VWAP strategy
    'test_strategy',
    'always_signal'
  ]);
  const [selectedStrategy, setSelectedStrategy] = useState('default');
  const [loading, setLoading] = useState(false);
  const [botUpdates, setBotUpdates] = useState([]);
  
  // Advanced configuration state
  const [config, setConfig] = useState({
    max_risk_per_trade: 0.02,
    max_daily_trades: 10,
    auto_trading_enabled: false,
    stop_loss_pips: 50,
    take_profit_pips: 100,
    // Advanced configuration fields
    risk_reward_ratio: 2.0,
    entry_trigger: 'signal_confirmation',
    exit_trigger: 'stop_loss_take_profit',
    leverage: 1,
    trade_size: 1000,
    strategy_parameters: {
      period: 14,
      threshold: 0.02
    },
    time_window: '24h',
    asset_type: 'spot',
    indicator_settings: {
      rsi_period: 14,
      ma_period: 20,
      bb_period: 20,
      bb_deviation: 2
    },
    max_loss_threshold: 100,
    auto_stop_enabled: true,
    max_consecutive_losses: 10
  });
  
  const [originalConfig, setOriginalConfig] = useState(config);
  const [configModified, setConfigModified] = useState(false);

  // Check if config has been modified
  useEffect(() => {
    const isModified = JSON.stringify(config) !== JSON.stringify(originalConfig);
    setConfigModified(isModified);
  }, [config, originalConfig]);

  // Socket event listeners
  useEffect(() => {
    if (!socket) return;

    // Request active bots when component mounts (for page refresh recovery)
    socket.emit('get_active_bots');

    // Listen for active bots response
    socket.on('active_bots_response', (data) => {
      console.log('Active bots response:', data);
      if (data.success && data.bots && data.bots.length > 0) {
        const restoredBots = data.bots.map((botData, index) => {
          // Extract bot number from bot_id (e.g., "bot_1" -> 1)
          const botNumberMatch = botData.bot_id.match(/bot_(\d+)/);
          const botNumber = botNumberMatch ? parseInt(botNumberMatch[1]) : index + 1;
          
          // Map performance data with proper fallbacks
          const performance = botData.performance || {};
          
          return {
            id: botData.bot_id,
            label: `Bot ${botNumber}`,
            strategy: botData.strategy,
            status: botData.is_running ? 'running' : 'stopped',
            config: botData.config || config,
            performance: {
              total_trades: performance.total_trades || 0,
              active_trades: performance.active_trades || 0,
              win_rate: performance.win_rate || 0,
              daily_pnl: performance.daily_pnl || 0,
              total_pnl: performance.total_pnl || 0,
              total_profit: performance.total_profit || 0,
              unrealized_pnl: performance.unrealized_pnl || 0,
              winning_trades: performance.winning_trades || 0,
              losing_trades: performance.losing_trades || 0,
              max_drawdown: performance.max_drawdown || 0,
              recent_trades: performance.recent_trades || []
            },
            trade_history: botData.trade_history || [],
            created_at: new Date(botData.bot_start_time || botData.created_at || Date.now()),
            last_activity: new Date(botData.last_activity || Date.now()),
            magic_number: botData.magic_number,  // Store magic number for debugging
            bot_start_time: botData.bot_start_time
          };
        });
        
        setBots(restoredBots);
        
        // Update bot counter to avoid ID conflicts
        const maxBotNumber = Math.max(
          ...restoredBots.map(bot => {
            const match = bot.id.match(/bot_(\d+)/);
            return match ? parseInt(match[1]) : 0;
          }),
          0
        );
        setBotIdCounter(maxBotNumber + 1);
        
        console.log(`Restored ${restoredBots.length} active bots from backend`);
        
        // Log performance data for debugging
        restoredBots.forEach(bot => {
          console.log(`Bot ${bot.id}: ${bot.performance.total_trades} trades, ${bot.performance.win_rate}% win rate, $${bot.performance.total_pnl} P&L`);
        });
      }
    });

    // Listen for bot updates
    socket.on('bot_update', (data) => {
      console.log('Bot update received:', data);
      setBotUpdates(prev => [data, ...prev.slice(0, 9)]);
      
      // Update specific bot data if bot_id is provided
      if (data.bot_id) {
        setBots(prevBots => 
          prevBots.map(bot => 
            bot.id === data.bot_id 
              ? { 
                  ...bot, 
                  performance: {
                    // Prioritize new performance data when available
                    total_trades: data.performance?.total_trades ?? bot.performance.total_trades,
                    active_trades: data.performance?.active_trades ?? data.active_trades ?? bot.performance.active_trades,
                    win_rate: data.performance?.win_rate ?? bot.performance.win_rate,
                    daily_pnl: data.performance?.daily_pnl ?? bot.performance.daily_pnl,
                    total_pnl: data.performance?.total_pnl ?? bot.performance.total_pnl,
                    total_profit: data.performance?.total_profit ?? bot.performance.total_profit,
                    unrealized_pnl: data.performance?.unrealized_pnl ?? bot.performance.unrealized_pnl,
                    winning_trades: data.performance?.winning_trades ?? bot.performance.winning_trades,
                    losing_trades: data.performance?.losing_trades ?? bot.performance.losing_trades,
                    max_drawdown: data.performance?.max_drawdown ?? bot.performance.max_drawdown,
                    recent_trades: data.performance?.recent_trades ?? bot.performance.recent_trades
                  },
                  current_price: data.current_price,
                  last_signal: data.signal,
                  lastUpdate: new Date() 
                }
              : bot
          )
        );
        
        // Enhanced logging for debugging data sync issues
        if (data.performance) {
          console.log(`📊 Bot ${data.bot_id} update:`, {
            backend_data: {
              total_trades: data.performance.total_trades,
              active_trades: data.performance.active_trades,
              unrealized_pnl: data.performance.unrealized_pnl,
              total_pnl: data.performance.total_pnl,
              magic_number: data.performance.magic_number
            },
            frontend_active_trades: data.active_trades,
            current_price: data.current_price
          });
          
          // Log any data mismatches
          if (data.performance.active_trades !== data.active_trades) {
            console.warn(`⚠️ Active trades mismatch for ${data.bot_id}: performance=${data.performance.active_trades}, direct=${data.active_trades}`);
          }
        }
      }
    });

    socket.on('bot_start_response', (data) => {
      console.log('Bot start response:', data);
      setLoading(false);
    });

    socket.on('bot_stop_response', (data) => {
      console.log('Bot stop response:', data);
      setLoading(false);
      
      // Remove bot from frontend state when stopped
      if (data.success && data.bot_id) {
        setBots(prevBots => prevBots.filter(bot => bot.id !== data.bot_id));
      }
    });

    socket.on('bot_error', (data) => {
      console.error('Bot error:', data.error);
      setLoading(false);
    });

    socket.on('trade_executed', (data) => {
      console.log('Trade executed:', data);
      setBotUpdates(prev => [{
        type: 'trade_executed',
        bot_id: data.bot_id,
        ticket: data.ticket,
        signal: data.signal,
        volume: data.volume,
        price: data.price,
        timestamp: data.timestamp
      }, ...prev.slice(0, 9)]);
      
      // Update specific bot's performance IMMEDIATELY with the new data
      if (data.bot_id && data.performance) {
        setBots(prevBots => 
          prevBots.map(bot => 
            bot.id === data.bot_id 
              ? { 
                  ...bot,
                  performance: {
                    // Use the fresh performance data from the trade execution
                    total_trades: data.performance.total_trades || 0,
                    active_trades: data.performance.active_trades || 0,
                    win_rate: data.performance.win_rate || 0,
                    daily_pnl: data.performance.daily_pnl || 0,
                    total_pnl: data.performance.total_pnl || 0,
                    total_profit: data.performance.total_profit || 0,
                    unrealized_pnl: data.performance.unrealized_pnl || 0,
                    winning_trades: data.performance.winning_trades || 0,
                    losing_trades: data.performance.losing_trades || 0,
                    max_drawdown: data.performance.max_drawdown || 0,
                    recent_trades: data.performance.recent_trades || bot.performance.recent_trades
                  },
                  trade_history: [
                    {
                      ticket: data.ticket,
                      type: data.signal?.type,
                      volume: data.volume,
                      price: data.price,
                      timestamp: data.timestamp
                    },
                    ...bot.trade_history.slice(0, 9)
                  ],
                  last_activity: new Date()
                }
              : bot
          )
        );
        
        // Log the immediate performance update
        console.log(`IMMEDIATE UPDATE - Bot ${data.bot_id}: ${data.performance.total_trades} trades, ${data.performance.win_rate}% win rate, $${data.performance.total_pnl} P&L`);
      }
    });

    socket.on('trade_error', (data) => {
      console.error('Trade error:', data);
      setBotUpdates(prev => [{
        type: 'trade_error',
        error: data.error,
        details: data.details,
        timestamp: data.timestamp
      }, ...prev.slice(0, 9)]);
    });

    socket.on('force_update_response', (data) => {
      console.log('Force update response:', data);
      if (data.success) {
        console.log(`✅ Force update successful for ${data.bot_id}:`, data.performance);
        // The performance update will come through the regular bot_update handler
      } else {
        console.error(`❌ Force update failed: ${data.error}`);
      }
    });

    socket.on('trade_completed', (data) => {
      console.log('Trade completed:', data);
      setBotUpdates(prev => [{
        type: 'trade_completed',
        bot_id: data.bot_id,
        trade_data: data.trade_data,
        timestamp: data.timestamp
      }, ...prev.slice(0, 9)]);
      
      // Force immediate performance update and trade history refresh
      if (data.bot_id) {
        setBots(prevBots => 
          prevBots.map(bot => 
            bot.id === data.bot_id 
              ? { 
                  ...bot,
                  last_activity: new Date()
                }
              : bot
          )
        );
        
        // Emit signal to refresh trade history
        window.dispatchEvent(new CustomEvent('refreshTradeHistory', {
          detail: { reason: 'trade_completed', bot_id: data.bot_id }
        }));
        
        console.log(`🎯 Trade completed for ${data.bot_id} - triggering trade history refresh`);
      }
    });

    return () => {
      socket.off('active_bots_response');
      socket.off('bot_update');
      socket.off('bot_start_response');
      socket.off('bot_stop_response');
      socket.off('bot_error');
      socket.off('trade_executed');
      socket.off('trade_error');
      socket.off('force_update_response');
      socket.off('trade_completed');
    };
  }, [socket, config]); // Added config to dependency array

  // Create new bot instance
  const createBot = () => {
    const newBot = {
      id: `bot_${botIdCounter}`,
      label: `Bot ${botIdCounter}`,
      strategy: selectedStrategy,
      status: 'running', // running, stopped, auto_stopped
      config: { ...config },
      performance: {
        total_trades: 0,
        active_trades: 0,
        win_rate: 0,
        daily_pnl: 0,
        total_pnl: 0,
        consecutive_losses: 0,
        max_drawdown: 0
      },
      trade_history: [],
      created_at: new Date(),
      last_activity: new Date()
    };

    setBots(prev => [...prev, newBot]);
    setBotIdCounter(prev => prev + 1);
    setLoading(true);

    // Start the bot via socket or API
    if (socket) {
      socket.emit('bot_start', { 
        bot_id: newBot.id,
        strategy: selectedStrategy,
        config: config 
      });
    }
  };

  // Stop a specific bot
  const stopBot = (botId) => {
    setBots(prevBots => 
      prevBots.map(bot => 
        bot.id === botId 
          ? { ...bot, status: 'stopped', last_activity: new Date() }
          : bot
      )
    );

    if (socket) {
      socket.emit('bot_stop', { bot_id: botId });
    }
  };



  // Get bot status color
  const getBotStatusColor = (bot) => {
    if (bot.status === 'stopped' || bot.status === 'auto_stopped') {
      return '#9ca3af'; // Gray
    }
    const totalPnL = bot.performance.total_pnl || bot.performance.total_profit || 0;
    return totalPnL >= 0 ? '#52c41a' : '#ef4444'; // Green/Red
  };

  // Update configuration
  const updateConfig = async () => {
    try {
      if (socket) {
        socket.emit('bot_config_update', config);
      } else {
        const response = await axios.post('http://localhost:5000/bot/config', config);
        if (response.data.success) {
          setOriginalConfig({ ...config });
          setConfigModified(false);
        }
      }
    } catch (error) {
      console.error('Error updating config:', error);
    }
  };

  const handleConfigChange = (key, value) => {
    if (key.includes('.')) {
      const keys = key.split('.');
      setConfig(prev => ({
        ...prev,
        [keys[0]]: {
          ...prev[keys[0]],
          [keys[1]]: value
        }
      }));
    } else {
      setConfig(prev => ({
        ...prev,
        [key]: value
      }));
    }
  };

  const formatUpdateTime = (timestamp) => {
    return new Date(timestamp).toLocaleTimeString();
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD'
    }).format(amount);
  };

  // Fetch detailed bot data and show modal
  const fetchAndShowBotDetails = async (bot) => {
    try {
      console.log(`Fetching detailed data for bot ${bot.id}`);
      const response = await fetch(`/bot-details/${bot.id}`);
      if (response.ok) {
        const detailData = await response.json();
        if (detailData.success) {
          // Create enhanced bot object with fresh data from backend
          const enhancedBot = {
            ...bot,
            performance: {
              total_trades: detailData.bot_details.performance.total_trades,
              active_trades: detailData.bot_details.performance.active_trades,
              win_rate: detailData.bot_details.performance.win_rate,
              winning_trades: detailData.bot_details.performance.winning_trades,
              losing_trades: detailData.bot_details.performance.losing_trades,
              total_profit: detailData.bot_details.performance.realized_pnl,
              unrealized_pnl: detailData.bot_details.performance.unrealized_pnl,
              total_pnl: detailData.bot_details.performance.total_pnl,
              daily_pnl: detailData.bot_details.performance.daily_pnl,
              max_drawdown: detailData.bot_details.performance.max_drawdown,
              recent_trades: detailData.bot_details.recent_trades
            },
            open_positions: detailData.bot_details.open_positions,
            fresh_data_timestamp: new Date().toISOString()
          };
          
          console.log(`Bot ${bot.id} fresh details:`, {
            total_trades: enhancedBot.performance.total_trades,
            active_trades: enhancedBot.performance.active_trades,
            win_rate: enhancedBot.performance.win_rate,
            total_pnl: enhancedBot.performance.total_pnl
          });
          
          setSelectedBotDetail(enhancedBot);
        } else {
          console.error('Failed to fetch bot details:', detailData.error);
          // Fallback to existing bot data
          setSelectedBotDetail(bot);
        }
      } else {
        console.error('Failed to fetch bot details, using cached data');
        // Fallback to existing bot data
        setSelectedBotDetail(bot);
      }
    } catch (error) {
      console.error('Error fetching bot details:', error);
      // Fallback to existing bot data
      setSelectedBotDetail(bot);
    }
  };

  return (
    <div className="trading-bot-container">
      {/* Header with Bot Stack */}
      <div className="bot-header">
        <div className="header-left">
          <h2>Trading Bot Control</h2>
          <div className="bot-summary">
            <span className="active-bots">Active Bots: {bots.filter(b => b.status === 'running').length}</span>
            <span className="total-pnl">
              Total P&L: {formatCurrency(bots.reduce((sum, bot) => sum + (bot.performance.total_pnl || bot.performance.total_profit || 0), 0))}
            </span>
          </div>
        </div>
        
        {/* Bot Stack Panel */}
        <div className="bot-stack">
          <h3>Active Bots</h3>
          <div className="bot-stack-grid">
            {bots.length === 0 ? (
              <div className="no-bots">No bots running</div>
            ) : (
              bots.map(bot => (
                <div 
                  key={bot.id} 
                  className={`bot-card ${bot.status}`}
                  onClick={() => fetchAndShowBotDetails(bot)}
                  style={{ borderColor: getBotStatusColor(bot) }}
                >
                  <div className="bot-card-header">
                    <span className="bot-label">{bot.label}</span>
                    <div 
                      className="bot-status-indicator"
                      style={{ backgroundColor: getBotStatusColor(bot) }}
                    />
                  </div>
                  <div className="bot-card-info">
                    <div className="bot-strategy">{bot.strategy}</div>
                    <div className="bot-pnl" style={{ color: getBotStatusColor(bot) }}>
                      {formatCurrency(bot.performance.total_pnl || bot.performance.total_profit || 0)}
                    </div>
                    <div className="bot-stats">
                      <span className="stat">Trades: {bot.performance.total_trades || 0}</span>
                      <span className="stat">Win Rate: {(bot.performance.win_rate || 0).toFixed(1)}%</span>
                    </div>
                  </div>
                  <button 
                    className="bot-close-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      stopBot(bot.id);
                    }}
                  >
                    ✕
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="bot-sections">
        {/* Strategy Selection */}
        <div className="strategy-selection">
          <h3>Bot Strategy Selection</h3>
          <div className="strategy-dropdown-container">
            <label>Select Strategy:</label>
            <select 
              value={selectedStrategy} 
              onChange={(e) => setSelectedStrategy(e.target.value)}
              className="strategy-select"
            >
              {strategies.map(strategy => (
                <option key={strategy} value={strategy}>
                  {strategy.replace('_', ' ').toUpperCase()}
                </option>
              ))}
            </select>
            <div className="strategy-description">
              {selectedStrategy === 'default' && '⚡ Always Signal - GUARANTEED to generate signals immediately for testing'}
              {selectedStrategy === 'moving_average' && '📈 Moving Average Crossover - Buy when short MA crosses above long MA'}
              {selectedStrategy === 'rsi_strategy' && '📊 RSI Strategy - Buy oversold (<30), sell overbought (>70)'}
              {selectedStrategy === 'breakout_strategy' && '🚀 Breakout Strategy - Trade when price breaks support/resistance'}
              {selectedStrategy === 'combined_strategy' && '🎯 Combined Strategy - Uses multiple indicators (requires 2+ agreements)'}
              {selectedStrategy === 'bollinger_bands' && '📉 Bollinger Bands - Buy at lower band, sell at upper band'}
              {selectedStrategy === 'macd_strategy' && '⚡ MACD Strategy - Trade on MACD line crossing signal line (12/26/9)'}
              {selectedStrategy === 'frequent_macd' && '🔄 Frequent MACD - Faster MACD signals with shorter periods (5/10/3)'}
              {selectedStrategy === 'stochastic_strategy' && '🌊 Stochastic Oscillator - Momentum-based overbought/oversold signals'}
              {selectedStrategy === 'vwap_strategy' && '💰 VWAP Strategy - Trade when price deviates significantly from volume-weighted average'}
              {selectedStrategy === 'test_strategy' && '🧪 Test Strategy - Generates alternating signals every 30 seconds for testing'}
              {selectedStrategy === 'always_signal' && '⚡ Always Signal - GUARANTEED to generate signals every second for testing'}
            </div>
          </div>
        </div>

        {/* Advanced Configuration */}
        <div className="bot-config advanced-config">
          <h3>Advanced Configuration</h3>
          
          {/* Basic Trading Parameters */}
          <div className="config-section">
            <h4>Basic Trading Parameters</h4>
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
                  className="config-input"
                />
              </div>
              <div className="config-item">
                <label>Trade Size (USD):</label>
                <input
                  type="number"
                  min="100"
                  value={config.trade_size}
                  onChange={(e) => handleConfigChange('trade_size', parseInt(e.target.value))}
                  className="config-input"
                />
              </div>
              <div className="config-item">
                <label>Leverage:</label>
                <select
                  value={config.leverage}
                  onChange={(e) => handleConfigChange('leverage', parseInt(e.target.value))}
                  className="config-input"
                >
                  <option value={1}>1x</option>
                  <option value={2}>2x</option>
                  <option value={5}>5x</option>
                  <option value={10}>10x</option>
                  <option value={20}>20x</option>
                </select>
              </div>
              <div className="config-item">
                <label>Asset Type:</label>
                <select
                  value={config.asset_type}
                  onChange={(e) => handleConfigChange('asset_type', e.target.value)}
                  className="config-input"
                >
                  <option value="spot">Spot</option>
                  <option value="futures">Futures</option>
                  <option value="options">Options</option>
                </select>
              </div>
            </div>
          </div>

          {/* Risk Management */}
          <div className="config-section">
            <h4>Risk Management</h4>
            <div className="config-grid">
              <div className="config-item">
                <label>Risk-Reward Ratio:</label>
                <input
                  type="number"
                  step="0.1"
                  min="0.5"
                  max="10"
                  value={config.risk_reward_ratio}
                  onChange={(e) => handleConfigChange('risk_reward_ratio', parseFloat(e.target.value))}
                  className="config-input"
                />
              </div>
              <div className="config-item">
                <label>Stop Loss (pips):</label>
                <input
                  type="number"
                  min="1"
                  value={config.stop_loss_pips}
                  onChange={(e) => handleConfigChange('stop_loss_pips', parseInt(e.target.value))}
                  className="config-input"
                />
              </div>
              <div className="config-item">
                <label>Take Profit (pips):</label>
                <input
                  type="number"
                  min="1"
                  value={config.take_profit_pips}
                  onChange={(e) => handleConfigChange('take_profit_pips', parseInt(e.target.value))}
                  className="config-input"
                />
              </div>
              <div className="config-item">
                <label>Max Loss Threshold ($):</label>
                <input
                  type="number"
                  min="50"
                  value={config.max_loss_threshold}
                  onChange={(e) => handleConfigChange('max_loss_threshold', parseInt(e.target.value))}
                  className="config-input"
                />
              </div>
            </div>
          </div>

          {/* Trading Rules */}
          <div className="config-section">
            <h4>Trading Rules</h4>
            <div className="config-grid">
              <div className="config-item">
                <label>Entry Trigger:</label>
                <select
                  value={config.entry_trigger}
                  onChange={(e) => handleConfigChange('entry_trigger', e.target.value)}
                  className="config-input"
                >
                  <option value="signal_confirmation">Signal Confirmation</option>
                  <option value="breakout">Breakout</option>
                  <option value="pullback">Pullback</option>
                  <option value="reversal">Reversal</option>
                </select>
              </div>
              <div className="config-item">
                <label>Exit Trigger:</label>
                <select
                  value={config.exit_trigger}
                  onChange={(e) => handleConfigChange('exit_trigger', e.target.value)}
                  className="config-input"
                >
                  <option value="stop_loss_take_profit">Stop Loss / Take Profit</option>
                  <option value="trailing_stop">Trailing Stop</option>
                  <option value="time_based">Time Based</option>
                  <option value="signal_reversal">Signal Reversal</option>
                </select>
              </div>
              <div className="config-item">
                <label>Max Daily Trades:</label>
                <input
                  type="number"
                  min="1"
                  value={config.max_daily_trades}
                  onChange={(e) => handleConfigChange('max_daily_trades', parseInt(e.target.value))}
                  className="config-input"
                />
              </div>
              <div className="config-item">
                <label>Time Window:</label>
                <select
                  value={config.time_window}
                  onChange={(e) => handleConfigChange('time_window', e.target.value)}
                  className="config-input"
                >
                  <option value="1h">1 Hour</option>
                  <option value="4h">4 Hours</option>
                  <option value="8h">8 Hours</option>
                  <option value="24h">24 Hours</option>
                  <option value="always">Always On</option>
                </select>
              </div>
            </div>
          </div>

          {/* Indicator Settings */}
          <div className="config-section">
            <h4>Indicator Settings</h4>
            <div className="config-grid">
              <div className="config-item">
                <label>RSI Period:</label>
                <input
                  type="number"
                  min="5"
                  max="50"
                  value={config.indicator_settings.rsi_period}
                  onChange={(e) => handleConfigChange('indicator_settings.rsi_period', parseInt(e.target.value))}
                  className="config-input"
                />
              </div>
              <div className="config-item">
                <label>Moving Average Period:</label>
                <input
                  type="number"
                  min="5"
                  max="200"
                  value={config.indicator_settings.ma_period}
                  onChange={(e) => handleConfigChange('indicator_settings.ma_period', parseInt(e.target.value))}
                  className="config-input"
                />
              </div>
              <div className="config-item">
                <label>Bollinger Bands Period:</label>
                <input
                  type="number"
                  min="5"
                  max="50"
                  value={config.indicator_settings.bb_period}
                  onChange={(e) => handleConfigChange('indicator_settings.bb_period', parseInt(e.target.value))}
                  className="config-input"
                />
              </div>
              <div className="config-item">
                <label>BB Deviation:</label>
                <input
                  type="number"
                  step="0.1"
                  min="1"
                  max="3"
                  value={config.indicator_settings.bb_deviation}
                  onChange={(e) => handleConfigChange('indicator_settings.bb_deviation', parseFloat(e.target.value))}
                  className="config-input"
                />
              </div>
            </div>
          </div>

          {/* Auto-Stop Settings */}
          <div className="config-section">
            <h4>Auto-Stop Settings</h4>
            <div className="config-grid">
              <div className="config-item checkbox-item">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={config.auto_stop_enabled}
                    onChange={(e) => handleConfigChange('auto_stop_enabled', e.target.checked)}
                    className="config-checkbox"
                  />
                  <span>Enable Auto-Stop</span>
                </label>
              </div>
              <div className="config-item">
                <label>Max Consecutive Losses:</label>
                <input
                  type="number"
                  min="3"
                  max="20"
                  value={config.max_consecutive_losses}
                  onChange={(e) => handleConfigChange('max_consecutive_losses', parseInt(e.target.value))}
                  className="config-input"
                />
              </div>
              <div className="config-item checkbox-item">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={config.auto_trading_enabled}
                    onChange={(e) => handleConfigChange('auto_trading_enabled', e.target.checked)}
                    className="config-checkbox"
                  />
                  <span>Enable Auto Trading</span>
                </label>
                <div className="config-warning">
                  {!config.auto_trading_enabled && (
                    <small style={{color: '#ff6b6b', fontSize: '12px'}}>
                      ⚠️ Auto trading is disabled - signals will be generated but no orders will be placed
                    </small>
                  )}
                  {config.auto_trading_enabled && (
                    <small style={{color: '#52c41a', fontSize: '12px'}}>
                      ✅ Auto trading is enabled - orders will be placed automatically
                    </small>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Control Buttons */}
          <div className="config-controls">
            <button 
              onClick={updateConfig} 
              disabled={!configModified}
              className={`update-config-btn black-btn ${!configModified ? 'disabled' : ''}`}
            >
              Update Configuration
            </button>
            <button 
              onClick={createBot} 
              disabled={loading || !selectedStrategy}
              className="start-bot-btn black-btn"
            >
              {loading ? 'Creating Bot...' : 'Start New Bot'}
            </button>
          </div>
        </div>

        {/* Recent Updates Section */}
        <div className="bot-updates">
          <h3>Recent Updates</h3>
          <div className="updates-list">
            {botUpdates.length === 0 ? (
              <div className="no-updates">No updates yet</div>
            ) : (
              botUpdates.map((update, index) => (
                <div key={index} className="update-item">
                  <div className="update-indicator"></div>
                  <div className="update-content">
                    <div className="update-header">
                      <span className="update-type">{update.type}</span>
                      <span className="update-time">{formatUpdateTime(update.timestamp)}</span>
                    </div>
                    <div className="update-details">
                      {update.bot_id && (
                        <span className="bot-badge">
                          {bots.find(b => b.id === update.bot_id)?.label || update.bot_id}
                        </span>
                      )}
                      {update.signal && (
                        <span className={`signal-badge ${update.signal.type?.toLowerCase()}`}>
                          {update.signal.type} @ ${update.signal.price?.toFixed(4)}
                        </span>
                      )}
                      {update.current_price && (
                        <span className="price-badge">
                          Price: ${update.current_price.toFixed(4)}
                        </span>
                      )}
                      {update.next_analysis_in && (
                        <span className="timer-badge">
                          Next analysis in: {update.next_analysis_in}s
                        </span>
                      )}
                      {update.ticket && (
                        <span className="ticket-badge">
                          Ticket: {update.ticket}
                        </span>
                      )}
                      {update.volume && (
                        <span className="volume-badge">
                          Volume: {update.volume}
                        </span>
                      )}
                      {update.error && (
                        <span className="error-badge">
                          ❌ {update.error}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Bot Detail Modal */}
      {selectedBotDetail && (
        <div className="bot-detail-modal-overlay" onClick={() => setSelectedBotDetail(null)}>
          <div className="bot-detail-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{selectedBotDetail.label} Details</h3>
              <button 
                className="modal-close"
                onClick={() => setSelectedBotDetail(null)}
              >
                ✕
              </button>
            </div>
            
            <div className="modal-content">
              {/* Performance Metrics */}
              <div className="modal-section">
                <h4>Performance Metrics</h4>
                <div className="performance-grid">
                  <div className="performance-item">
                    <span className="label">Total Trades</span>
                    <span className="value">{selectedBotDetail.performance.total_trades}</span>
                  </div>
                  <div className="performance-item">
                    <span className="label">Active Trades</span>
                    <span className="value">{selectedBotDetail.performance.active_trades}</span>
                  </div>
                  <div className="performance-item">
                    <span className="label">Win Rate</span>
                    <span className="value profit">{(selectedBotDetail.performance.win_rate || 0).toFixed(1)}%</span>
                  </div>
                  <div className="performance-item">
                    <span className="label">Winning Trades</span>
                    <span className="value profit">{selectedBotDetail.performance.winning_trades || 0}</span>
                  </div>
                  <div className="performance-item">
                    <span className="label">Losing Trades</span>
                    <span className="value loss">{selectedBotDetail.performance.losing_trades || 0}</span>
                  </div>
                  <div className="performance-item">
                    <span className="label">Realized P&L</span>
                    <span className={`value ${(selectedBotDetail.performance.total_profit || 0) >= 0 ? 'profit' : 'loss'}`}>
                      {formatCurrency(selectedBotDetail.performance.total_profit || 0)}
                    </span>
                  </div>
                  <div className="performance-item">
                    <span className="label">Unrealized P&L</span>
                    <span className={`value ${(selectedBotDetail.performance.unrealized_pnl || 0) >= 0 ? 'profit' : 'loss'}`}>
                      {formatCurrency(selectedBotDetail.performance.unrealized_pnl || 0)}
                    </span>
                  </div>
                  <div className="performance-item">
                    <span className="label">Total P&L</span>
                    <span className={`value ${(selectedBotDetail.performance.total_pnl || 0) >= 0 ? 'profit' : 'loss'}`}>
                      {formatCurrency(selectedBotDetail.performance.total_pnl || 0)}
                    </span>
                  </div>
                  <div className="performance-item">
                    <span className="label">Daily P&L</span>
                    <span className={`value ${(selectedBotDetail.performance.daily_pnl || 0) >= 0 ? 'profit' : 'loss'}`}>
                      {formatCurrency(selectedBotDetail.performance.daily_pnl || 0)}
                    </span>
                  </div>
                  <div className="performance-item">
                    <span className="label">Max Drawdown</span>
                    <span className="value loss">{formatCurrency(selectedBotDetail.performance.max_drawdown || 0)}</span>
                  </div>
                </div>
              </div>

              {/* Trade History */}
              <div className="modal-section">
                <h4>Recent Trade History</h4>
                <div className="trade-history">
                  {(!selectedBotDetail.performance.recent_trades || selectedBotDetail.performance.recent_trades.length === 0) ? (
                    <div className="no-trades">No trades yet</div>
                  ) : (
                    selectedBotDetail.performance.recent_trades.map((trade, index) => (
                      <div key={index} className="trade-item">
                        <div className="trade-info">
                          <span className={`trade-type ${trade.type}`}>{trade.type.toUpperCase()}</span>
                          <span className="trade-ticket">#{trade.ticket}</span>
                          <span className="trade-price">${trade.price.toFixed(4)}</span>
                          <span className="trade-volume">{trade.volume} lots</span>
                        </div>
                        <div className="trade-result">
                          <span className={`trade-pnl ${trade.profit >= 0 ? 'profit' : 'loss'}`}>
                            {formatCurrency(trade.profit)}
                          </span>
                          <span className="trade-time">{formatUpdateTime(trade.time)}</span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Bot Configuration */}
              <div className="modal-section">
                <h4>Bot Configuration</h4>
                <div className="config-display">
                  <div className="config-row">
                    <span className="config-label">Strategy:</span>
                    <span className="config-value">{selectedBotDetail.strategy}</span>
                  </div>
                  <div className="config-row">
                    <span className="config-label">Risk per Trade:</span>
                    <span className="config-value">{(selectedBotDetail.config.max_risk_per_trade * 100).toFixed(1)}%</span>
                  </div>
                  <div className="config-row">
                    <span className="config-label">Trade Size:</span>
                    <span className="config-value">{formatCurrency(selectedBotDetail.config.trade_size)}</span>
                  </div>
                  <div className="config-row">
                    <span className="config-label">Leverage:</span>
                    <span className="config-value">{selectedBotDetail.config.leverage}x</span>
                  </div>
                  <div className="config-row">
                    <span className="config-label">Max Loss Threshold:</span>
                    <span className="config-value">{formatCurrency(selectedBotDetail.config.max_loss_threshold)}</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="modal-actions">
              <button 
                className="force-update-btn"
                onClick={() => {
                  if (socket) {
                    console.log(`🔄 Forcing performance update for ${selectedBotDetail.id}`);
                    socket.emit('force_performance_update', { bot_id: selectedBotDetail.id });
                  }
                }}
                style={{
                  marginRight: '10px',
                  backgroundColor: '#4CAF50',
                  color: 'white',
                  border: 'none',
                  padding: '10px 20px',
                  borderRadius: '5px',
                  cursor: 'pointer'
                }}
              >
                🔄 Force Update
              </button>
              <button 
                className="stop-bot-btn"
                onClick={() => {
                  stopBot(selectedBotDetail.id);
                  setSelectedBotDetail(null);
                }}
                disabled={selectedBotDetail.status !== 'running'}
              >
                Stop Bot
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TradingBot; 