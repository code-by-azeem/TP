import React, { useState, useEffect, useCallback } from 'react';
import './TradeHistory.css';

const TradeHistory = ({ socket }) => {
  const [trades, setTrades] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);
  // Note: Removed summaryStats state - now calculated directly from trades data

  // Function to fetch trade history from server
  const fetchTradeHistory = useCallback(async (isBackgroundRefresh = false) => {
    // Only show loading for manual/initial refreshes, not background refreshes
    if (!isBackgroundRefresh) {
      setIsLoading(true);
    }
    
    try {
      const response = await fetch('http://localhost:5000/trade-history', {
        credentials: 'include',
      });
      
      if (response.ok) {
        const data = await response.json();
        console.log('Fetched trade history:', data);
        
        if (Array.isArray(data)) {
          // Process the trade data
          const processedTrades = data.map(trade => ({
            ...trade,
            // Ensure numerical values are properly formatted
            volume: parseFloat(trade.volume) || 0,
            price: parseFloat(trade.price) || 0,
            profit: parseFloat(trade.profit) || 0,
            change_percent: parseFloat(trade.change_percent) || 0,
            current_price: parseFloat(trade.current_price) || parseFloat(trade.price) || 0,
            exit_price: parseFloat(trade.exit_price) || parseFloat(trade.current_price) || 0,
            sl: parseFloat(trade.sl) || 0,
            tp: parseFloat(trade.tp) || 0,
          }));
          
          setTrades(processedTrades);
          setLastUpdate(new Date());
          setError(null);
          
          if (!isBackgroundRefresh) {
            console.log(`✅ Trade history updated: ${processedTrades.length} trades loaded`);
          } else {
            console.log(`🔄 Background refresh completed: ${processedTrades.length} trades`);
          }
        } else {
          console.error('Invalid trade data format:', data);
          setError('Invalid data format received');
        }
      } else {
        const errorData = await response.json();
        console.error('Failed to fetch trade history:', errorData);
        setError(errorData.error || 'Failed to fetch trade history');
      }
    } catch (error) {
      console.error('Error fetching trade history:', error);
      setError('Connection error - please try again');
    } finally {
      if (!isBackgroundRefresh) {
        setIsLoading(false);
      }
    }
  }, []);

  // Force refresh function for immediate updates
  const forceRefresh = useCallback(async () => {
    try {
      setIsLoading(true);
      
      // First trigger backend refresh
      await fetch('http://localhost:5000/force-refresh-trades', {
        credentials: 'include'
      });
      
      // Wait a moment for backend to process
      await new Promise(resolve => setTimeout(resolve, 500));
      
      // Then fetch latest data
      await fetchTradeHistory();
    } catch (error) {
      console.error('Error forcing refresh:', error);
      // Fallback to regular fetch
      await fetchTradeHistory();
    }
  }, [fetchTradeHistory]);

  // Handle real-time trade updates from WebSocket
  const handleTradeUpdate = useCallback((data) => {
    console.log('📡 Real-time trade update received:', data);
    setLastUpdate(new Date());

    if (data.type === 'position_opened' && data.data) {
      // Add new position to the list with real-time handling
      setTrades(prevTrades => {
        // Check if trade already exists to avoid duplicates
        const existingIndex = prevTrades.findIndex(t => t.id === data.data.id || t.ticket === data.data.ticket);
        if (existingIndex >= 0) {
          // Update existing trade with new status
          const newTrades = [...prevTrades];
          newTrades[existingIndex] = { 
            ...data.data, 
            isNew: true, 
            isUpdated: true,
            // Preserve bot attribution if it exists
            bot_id: data.data.bot_id || newTrades[existingIndex].bot_id,
            bot_name: data.data.bot_name || newTrades[existingIndex].bot_name,
            is_bot_trade: data.data.is_bot_trade || newTrades[existingIndex].is_bot_trade
          };
          return newTrades;
        } else {
          // Add new trade at the beginning with proper sorting
          const newTradesList = [{ 
            ...data.data, 
            isNew: true,
            // Ensure bot attribution is included
            is_bot_trade: data.data.is_bot_trade || false,
            bot_id: data.data.bot_id || null,
            bot_name: data.data.bot_name || null
          }, ...prevTrades];
          // Sort by timestamp to maintain order
          return newTradesList.sort((a, b) => new Date(b.timestamp || b.time) - new Date(a.timestamp || a.time));
        }
      });
      
      console.log('✅ New position added to trade history with bot attribution');
    } else if (data.type === 'position_updated' && data.data) {
      // Update existing position with live P/L changes - real-time responsive
      setTrades(prevTrades => {
        const newTrades = prevTrades.map(trade => {
          if (trade.id === data.data.id || trade.ticket === data.data.ticket) {
            return { 
              ...trade, 
              ...data.data, 
              isUpdated: true,
              // Preserve visual indicators if they exist
              isNew: trade.isNew,
              justClosed: trade.justClosed,
              // Preserve bot attribution
              bot_id: trade.bot_id || data.data.bot_id,
              bot_name: trade.bot_name || data.data.bot_name,
              is_bot_trade: trade.is_bot_trade || data.data.is_bot_trade,
              // Add timestamp of update for tracking
              lastUpdateTime: new Date().toISOString()
            };
          }
          return trade;
        });
        return newTrades;
      });
      
      console.log('📊 Position updated with live P/L changes');
    } else if (data.type === 'position_closed' && data.data) {
      // Handle closed position - update immediately, then refresh for complete data
      setTrades(prevTrades => {
        const newTrades = prevTrades.map(trade => {
          if (trade.id === data.data.id || trade.ticket === data.data.ticket) {
            return {
              ...trade,
              ...data.data,
              is_open: false,
              justClosed: true,
              // Preserve bot attribution
              bot_id: trade.bot_id || data.data.bot_id,
              bot_name: trade.bot_name || data.data.bot_name,
              is_bot_trade: trade.is_bot_trade || data.data.is_bot_trade,
              closedTime: new Date().toISOString()
            };
          }
          return trade;
        });
        return newTrades;
      });
      
      console.log('🎯 Position closed - updated immediately in trade history');
      
      // Trigger a background refresh for complete data without showing loading
      setTimeout(() => {
        console.log('🔄 Background refresh for closed trade complete data');
        fetchTradeHistory(true); // Background refresh
      }, 3000); // 3-second delay to ensure backend processing is complete
    }
  }, [fetchTradeHistory]);

  // Handle account updates from WebSocket (for summary stats)
  const handleAccountUpdate = useCallback((accountData) => {
    console.log('💰 Account update received for trade history:', accountData);
    // Account updates help us know when to refresh for accuracy
    // The summary stats are now calculated directly from trades, so we just log this
  }, []);

  useEffect(() => {
    // Initial load
    fetchTradeHistory();
    
    // Set up smart refresh system - much less frequent since we have real-time updates
    const refreshInterval = setInterval(() => {
      // Only refresh every 2 minutes for data consistency, not for real-time updates
      console.log('🔄 Periodic consistency check');
      fetchTradeHistory(true); // Background refresh for consistency
    }, 120000); // 2 minutes instead of 30 seconds
    
    // Set up WebSocket listeners for real-time updates
    if (socket) {
      console.log('🔌 Setting up WebSocket listeners for real-time trade updates');
      
      // Real-time trade updates (position changes, P/L updates)
      socket.on('trade_update', handleTradeUpdate);
      socket.on('account_update', handleAccountUpdate);
      
      // Bot-specific events for immediate response
      socket.on('trade_executed', (data) => {
        console.log('🤖 Bot trade executed - adding to history immediately:', data);
        // Add the new trade immediately without waiting for refresh
        if (data.bot_id && data.ticket) {
          setTrades(prevTrades => {
            // Check if trade already exists
            const existingIndex = prevTrades.findIndex(t => t.id === data.ticket || t.ticket === data.ticket);
            if (existingIndex === -1) {
              // Add new trade at the beginning
              const newTrade = {
                id: data.ticket,
                ticket: data.ticket,
                timestamp: data.timestamp,
                time: data.timestamp,
                symbol: data.signal?.symbol || 'ETHUSD',
                type: data.signal?.action || 'BUY',
                volume: data.volume || 1.0,
                price: data.price || 0,
                entry_price: data.price || 0,
                current_price: data.price || 0,
                sl: data.sl || 0,
                tp: data.tp || 0,
                profit: 0, // Initial profit is 0
                raw_profit: 0,
                commission: 0,
                swap: 0,
                change_percent: 0,
                comment: `TradePulse_${data.bot_id}`,
                magic: data.magic || 0,
                is_open: true,
                isNew: true, // Visual indicator
                // Bot attribution
                bot_id: data.bot_id,
                bot_name: `Bot ${data.bot_id.split('_')[1] || data.bot_id}`,
                is_bot_trade: true
              };
              return [newTrade, ...prevTrades];
            }
            return prevTrades;
          });
        }
        // Trigger a delayed refresh to get complete data with backend attribution
        setTimeout(() => {
          console.log('🔄 Fetching complete trade data after bot execution');
          fetchTradeHistory(true); // Background refresh
        }, 3000); // 3-second delay to ensure backend processing
      });
      
      // Bot trade completion events
      socket.on('trade_completed', (data) => {
        console.log('✅ Bot trade completed - updating history:', data);
        // Trigger refresh for final trade data with complete P/L
        setTimeout(() => {
          console.log('🔄 Fetching final trade data after completion');
          fetchTradeHistory(true); // Background refresh
        }, 2000); // 2-second delay for backend processing
      });
      
      // Backend refresh signals (for critical updates only)
      socket.on('refresh_trade_history', (data) => {
        console.log('🔄 Backend refresh signal received:', data);
        // Only refresh for critical signals, not routine updates
        if (data.reason === 'immediate_closed_trade' || 
            data.reason === 'manual_force_refresh' ||
            data.reason === 'critical_update') {
          setTimeout(() => fetchTradeHistory(true), 1000); // Background refresh
        }
      });
    }
    
    // Listen for custom refresh events (from other components)
    const handleCustomRefreshEvent = (event) => {
      console.log('🔄 Custom refresh event triggered:', event.detail);
      // Only refresh if it's a critical update
      if (event.detail?.reason === 'trade_completed' || 
          event.detail?.reason === 'critical_update') {
        setTimeout(() => fetchTradeHistory(), 1000);
      }
    };
    
    window.addEventListener('refreshTradeHistory', handleCustomRefreshEvent);
    
    return () => {
      clearInterval(refreshInterval);
      window.removeEventListener('refreshTradeHistory', handleCustomRefreshEvent);
      
      // Clean up WebSocket listeners
      if (socket) {
        console.log('🔌 Cleaning up WebSocket listeners');
        socket.off('trade_update', handleTradeUpdate);
        socket.off('account_update', handleAccountUpdate);
        socket.off('trade_executed');
        socket.off('trade_completed');
        socket.off('refresh_trade_history');
      }
    };
  }, [fetchTradeHistory, socket, handleTradeUpdate, handleAccountUpdate]);

  // Clean up visual indicators after a few seconds
  useEffect(() => {
    const timer = setTimeout(() => {
      setTrades(prevTrades => 
        prevTrades.map(trade => ({
          ...trade,
          isNew: false,
          isUpdated: false,
          justClosed: false
        }))
      );
    }, 5000); // Remove indicators after 5 seconds

    return () => clearTimeout(timer);
  }, [trades]);

  // Removed periodic refresh - relying on real-time WebSocket updates only
  // No automatic refresh intervals to prevent unwanted page refreshes

  // Format currency values
  const formatCurrency = (value) => {
    const num = parseFloat(value);
    if (isNaN(num)) return '$0.00';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(num);
  };

  // Format date and time
  const formatDateTime = (dateString) => {
    try {
      const date = new Date(dateString);
      return date.toLocaleString();
    } catch (e) {
      return dateString;
    }
  };

  // Format change percentage
  const formatChangePercent = (value) => {
    const num = parseFloat(value);
    if (isNaN(num)) return '0.00%';
    const sign = num >= 0 ? '+' : '';
    return `${sign}${num.toFixed(2)}%`;
  };

  if (isLoading) {
    return (
      <div className="trade-history-container">
        <h2>Trade History</h2>
        <div className="loading-indicator">
          <div className="spinner"></div>
          <p>Loading trade history...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="trade-history-container">
        <h2>Trade History</h2>
        <div className="error-message">
          <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="trade-history-container">
      <div className="trade-history-header">
        <h2 className="trade-history-title">
          Trade History
          {socket && socket.connected && (
            <span className="connection-status connected" title="Real-time connection active">
              🟢 Live
            </span>
          )}
        </h2>
        <div className="header-controls">
          <button 
            className="refresh-button" 
            onClick={forceRefresh}
            disabled={isLoading}
          >
            <span>🔄</span>
            {isLoading ? 'Refreshing...' : 'Manual Refresh'}
          </button>
          {lastUpdate && (
            <div className="last-update-info">
              <span>Last updated: {lastUpdate.toLocaleTimeString()}</span>
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="error-message">
          <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="15" y1="9" x2="9" y2="15"></line>
            <line x1="9" y1="9" x2="15" y2="15"></line>
          </svg>
          <p>{error}</p>
        </div>
      )}

      {isLoading && trades.length === 0 ? (
        <div className="loading-indicator">
          <div className="spinner"></div>
          <p>Loading trade history...</p>
        </div>
      ) : trades.length === 0 ? (
        <div className="no-trades">
          <svg xmlns="http://www.w3.org/2000/svg" width="60" height="60" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
            <line x1="9" y1="9" x2="15" y2="15"></line>
            <line x1="15" y1="9" x2="9" y2="15"></line>
          </svg>
          <p>No trades found. Start trading to see your history here.</p>
        </div>
      ) : (
        <div className="trades-content">
          {/* Trade Summary Section */}
          <div className="trade-details-summary">
            <h3>Trade Summary</h3>
            <div className="summary-grid">
              <div className="summary-item">
                <span className="label">Total Trades</span>
                <span className="value">{trades.length}</span>
              </div>
              <div className="summary-item">
                <span className="label">Open Positions</span>
                <span className="value">{trades.filter(trade => trade.is_open).length}</span>
              </div>
              <div className="summary-item">
                <span className="label">Closed Trades</span>
                <span className="value">{trades.filter(trade => !trade.is_open).length}</span>
              </div>
              <div className="summary-item">
                <span className="label">Winning Trades</span>
                <span className="value profit">{trades.filter(trade => !trade.is_open && trade.profit > 0).length}</span>
              </div>
              <div className="summary-item">
                <span className="label">Losing Trades</span>
                <span className="value loss">{trades.filter(trade => !trade.is_open && trade.profit < 0).length}</span>
              </div>
              <div className="summary-item">
                <span className="label">Win Rate</span>
                <span className="value">
                  {(() => {
                    const closedTrades = trades.filter(trade => !trade.is_open);
                    const winningTrades = closedTrades.filter(trade => trade.profit > 0);
                    return closedTrades.length > 0 ? `${((winningTrades.length / closedTrades.length) * 100).toFixed(1)}%` : '0.0%';
                  })()}
                </span>
              </div>
              <div className="summary-item">
                <span className="label">Total P&L</span>
                <span className={`value ${trades.reduce((sum, trade) => sum + (parseFloat(trade.profit) || 0), 0) >= 0 ? 'profit' : 'loss'}`}>
                  {formatCurrency(trades.reduce((sum, trade) => sum + (parseFloat(trade.profit) || 0), 0))}
                </span>
              </div>
              <div className="summary-item">
                <span className="label">Realized P&L</span>
                <span className={`value ${trades.filter(trade => !trade.is_open).reduce((sum, trade) => sum + (parseFloat(trade.profit) || 0), 0) >= 0 ? 'profit' : 'loss'}`}>
                  {formatCurrency(trades.filter(trade => !trade.is_open).reduce((sum, trade) => sum + (parseFloat(trade.profit) || 0), 0))}
                </span>
              </div>
              <div className="summary-item">
                <span className="label">Unrealized P&L</span>
                <span className={`value ${trades.filter(trade => trade.is_open).reduce((sum, trade) => sum + (parseFloat(trade.profit) || 0), 0) >= 0 ? 'profit' : 'loss'}`}>
                  {formatCurrency(trades.filter(trade => trade.is_open).reduce((sum, trade) => sum + (parseFloat(trade.profit) || 0), 0))}
                </span>
              </div>
              <div className="summary-item">
                <span className="label">Bot Trades</span>
                <span className="value">{trades.filter(trade => trade.is_bot_trade).length}</span>
              </div>
              <div className="summary-item">
                <span className="label">Manual Trades</span>
                <span className="value">{trades.filter(trade => !trade.is_bot_trade).length}</span>
              </div>
              <div className="summary-item">
                <span className="label">Average Trade</span>
                <span className={`value ${(() => {
                  const closedTrades = trades.filter(trade => !trade.is_open);
                  const avgProfit = closedTrades.length > 0 ? closedTrades.reduce((sum, trade) => sum + (parseFloat(trade.profit) || 0), 0) / closedTrades.length : 0;
                  return avgProfit >= 0 ? 'profit' : 'loss';
                })()}`}>
                  {(() => {
                    const closedTrades = trades.filter(trade => !trade.is_open);
                    const avgProfit = closedTrades.length > 0 ? closedTrades.reduce((sum, trade) => sum + (parseFloat(trade.profit) || 0), 0) / closedTrades.length : 0;
                    return formatCurrency(avgProfit);
                  })()}
                </span>
              </div>
            </div>
          </div>

          {/* Trade History Table */}
          <div className="trades-table-container">
            <table className="trades-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Date & Time</th>
                  <th>Symbol</th>
                  <th>Type</th>
                  <th>Volume</th>
                  <th>Price</th>
                  <th className="hidden-mobile">S/L</th>
                  <th className="hidden-mobile">T/P</th>
                  <th className="hidden-tablet">Time</th>
                  <th>Price</th>
                  <th>Profit</th>
                  <th>Change</th>
                  <th>Bot</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((trade, index) => (
                  <tr 
                    key={trade.id || index} 
                    className={`
                      ${trade.is_open ? 'open-position' : ''}
                      ${trade.profit > 0 ? 'profit-row' : trade.profit < 0 ? 'loss-row' : ''}
                      ${trade.isNew ? 'new-trade' : ''}
                      ${trade.isUpdated ? 'updated-trade' : ''}
                      ${trade.justClosed ? 'just-closed' : ''}
                    `.trim()}
                  >
                    <td>{trade.id || trade.ticket}</td>
                    <td>{formatDateTime(trade.timestamp || trade.time)}</td>
                    <td>
                      <div className="symbol-cell">
                        <span className="symbol">{trade.symbol}</span>
                        {trade.is_open && <span className="open-badge">Live</span>}
                      </div>
                    </td>
                    <td>
                      <span className={`type-badge ${trade.type.toLowerCase() === 'buy' ? 'buy-type' : 'sell-type'}`}>
                        {trade.type}
                      </span>
                    </td>
                    <td>{trade.volume}</td>
                    <td>{formatCurrency(trade.price || trade.entry_price)}</td>
                    <td className="hidden-mobile">{trade.sl ? formatCurrency(trade.sl) : '—'}</td>
                    <td className="hidden-mobile">{trade.tp ? formatCurrency(trade.tp) : '—'}</td>
                    <td className="hidden-tablet">
                      {trade.is_open ? (
                        <span className="live-time">Live</span>
                      ) : (
                        formatDateTime(trade.close_time || trade.exit_time)
                      )}
                    </td>
                    <td>{formatCurrency(trade.current_price || trade.exit_price || trade.price)}</td>
                    <td className={`profit-cell ${trade.profit >= 0 ? 'profit' : 'loss'}`}>
                      {formatCurrency(trade.profit)}
                    </td>
                    <td className={`change-cell ${trade.change_percent >= 0 ? 'profit' : 'loss'}`}>
                      {formatChangePercent(trade.change_percent)}
                    </td>
                    <td className="bot-column">
                      {trade.is_bot_trade ? (
                        <span className="bot-badge" title={`Magic Number: ${trade.magic}`}>
                          🤖 {trade.bot_name || 'Unknown Bot'}
                        </span>
                      ) : (
                        <span className="manual-trade" title="Manual Trade">
                          👤 Manual
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default TradeHistory; 