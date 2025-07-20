import React, { useState, useEffect, useCallback } from 'react';
import './TradeHistory.css';

const TradeHistory = ({ socket }) => {
  const [trades, setTrades] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [summaryStats, setSummaryStats] = useState({
    totalTrades: 0,
    openPositions: 0,
    winningTrades: 0,
    losingTrades: 0,
    realizedPL: 0,
    commission: 0,
    swap: 0
  });

  // Function to fetch account summary for accurate statistics
  const fetchAccountSummary = useCallback(async () => {
    try {
      const response = await fetch('http://localhost:5000/account-summary', {
        credentials: 'include',
      });
      
      if (response.ok) {
        const data = await response.json();
        setSummaryStats({
          totalTrades: (data.closed_trades_6m || 0) + (data.open_positions || 0),
          openPositions: data.open_positions || 0,
          winningTrades: data.winning_trades || 0,
          losingTrades: data.losing_trades || 0,
          realizedPL: data.realized_profit || 0,
          commission: 0, // Will be calculated from trades if needed
          swap: 0 // Will be calculated from trades if needed
        });
      }
    } catch (error) {
      console.error('Error fetching account summary:', error);
    }
  }, []);

  // Function to fetch trade history from server
  const fetchTradeHistory = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await fetch('http://localhost:5000/trade-history', {
        credentials: 'include',
      });
      
      if (!response.ok) {
        if (response.status === 503) {
          throw new Error('MT5 connection not available. Please ensure MT5 is running and connected.');
        } else if (response.status === 500) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.error || 'Server error occurred while fetching trade history.');
        } else if (response.status === 401) {
          throw new Error('Please login again to access trade history.');
        }
        throw new Error(`HTTP error! Status: ${response.status}`);
      }
      
      const data = await response.json();
      console.log("MT5 Trade history data received:", data);
      setTrades(data);
      setError(null);
      
      // Calculate commission and swap totals from trades
      const totalCommission = data.reduce((sum, t) => sum + (t.commission || 0), 0);
      const totalSwap = data.reduce((sum, t) => sum + (t.swap || 0), 0);
      
      setSummaryStats(prev => ({
        ...prev,
        commission: totalCommission,
        swap: totalSwap
      }));
      
      // Also fetch account summary for accurate stats
      await fetchAccountSummary();
    } catch (error) {
      console.error('Error fetching trade history:', error);
      setError(error.message || 'Failed to load trade history from MT5. Please try again later.');
    } finally {
      setIsLoading(false);
    }
  }, [fetchAccountSummary]);

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

  // Handle trade updates from WebSocket
  const handleTradeUpdate = useCallback((data) => {
    console.log('Trade update received:', data);
    setLastUpdate(new Date());

    if (data.type === 'position_opened' && data.data) {
      // Add new position to the list with real-time handling
      setTrades(prevTrades => {
        // Check if trade already exists to avoid duplicates
        const existingIndex = prevTrades.findIndex(t => t.id === data.data.id || t.ticket === data.data.ticket);
        if (existingIndex >= 0) {
          // Update existing trade with new status
          const newTrades = [...prevTrades];
          newTrades[existingIndex] = { ...data.data, isNew: true, isUpdated: true };
          return newTrades;
        } else {
          // Add new trade at the beginning with proper sorting
          const newTradesList = [{ ...data.data, isNew: true }, ...prevTrades];
          // Sort by timestamp to maintain order
          return newTradesList.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
        }
      });
      
      // Update account summary for new position - no delays
      fetchAccountSummary();
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
              // Add timestamp of update for tracking
              lastUpdateTime: new Date().toISOString()
            };
          }
          return trade;
        });
        return newTrades;
      });
      
      // Update account summary immediately for profit changes
      fetchAccountSummary();
    } else if (data.type === 'position_closed' && data.data) {
      // Handle closed position - immediate real-time processing
      setTrades(prevTrades => {
        const existingIndex = prevTrades.findIndex(t => t.id === data.data.id || t.ticket === data.data.ticket);
        if (existingIndex >= 0) {
          // Update existing trade to closed status with complete data
          const newTrades = [...prevTrades];
          newTrades[existingIndex] = { 
            ...newTrades[existingIndex], // Preserve existing data
            ...data.data, // Apply new closed data
            justClosed: true,
            is_open: false, // Ensure it's marked as closed
            closedTime: new Date().toISOString() // Track when it was closed in UI
          };
          // Resort the list to maintain timestamp order
          return newTrades.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
        } else {
          // Add new closed trade if it wasn't in the list
          const newTradesList = [{ 
            ...data.data, 
            justClosed: true, 
            is_open: false,
            closedTime: new Date().toISOString()
          }, ...prevTrades];
          return newTradesList.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
        }
      });
      
      // Immediate account summary update for closed positions
      console.log('Position closed - immediate account summary update');
      fetchAccountSummary();
    }
  }, [fetchAccountSummary]);

  // Handle account updates from WebSocket
  const handleAccountUpdate = useCallback((accountUpdate) => {
    console.log('Trade History received account update:', accountUpdate);
    
    // Update summary stats from account update
    if (accountUpdate) {
      setSummaryStats(prev => ({
        ...prev,
        openPositions: accountUpdate.open_positions || prev.openPositions,
        realizedPL: accountUpdate.realized_profit !== undefined ? accountUpdate.realized_profit : prev.realizedPL
      }));
    }
  }, []);

  useEffect(() => {
    fetchTradeHistory();
    
    // Set up WebSocket listeners for real-time updates
    if (socket) {
      console.log('Setting up trade update listener');
      socket.on('trade_update', handleTradeUpdate);
      socket.on('account_update', handleAccountUpdate);
      
      // Listen for refresh signals from backend - only for critical updates
      socket.on('refresh_trade_history', (data) => {
        console.log('Received refresh signal:', data);
        // Only refresh for truly unknown deals that weren't caught by real-time updates
        if (data.reason === 'immediate_unknown_deal' || data.reason === 'manual_force_refresh') {
          console.log('Refreshing for critical signal:', data.reason);
          fetchTradeHistory();
        }
        // Skip refresh for other signals - rely on real-time trade_update events instead
      });
      
      // Clean up listener on unmount - NO periodic refresh intervals
      return () => {
        console.log('Cleaning up trade update listener');
        socket.off('trade_update', handleTradeUpdate);
        socket.off('account_update', handleAccountUpdate);
        socket.off('refresh_trade_history');
      };
    }
  }, [socket, handleTradeUpdate, handleAccountUpdate, fetchTradeHistory, forceRefresh]);

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

  // Format currency with 2 decimal places
  const formatCurrency = (value) => {
    if (value === undefined || value === null) return '$0.00';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2
    }).format(value);
  };

  // Format date nicely
  const formatDate = (dateString) => {
    try {
      const date = new Date(dateString);
      return date.toLocaleString();
    } catch (e) {
      return dateString;
    }
  };

  // Format volume
  const formatVolume = (volume) => {
    return parseFloat(volume || 0).toFixed(2);
  };

  // Format percentage change
  const formatChangePercent = (change) => {
    if (change === undefined || change === null) return '0.00%';
    const value = parseFloat(change);
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
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
        <h2>Trade History</h2>
        <div className="header-controls">
          {lastUpdate && (
            <div className="last-update">
              <span className="update-indicator"></span>
              Last updated: {lastUpdate.toLocaleTimeString()}
            </div>
          )}
          <button 
            className="refresh-button" 
            onClick={forceRefresh}
            disabled={isLoading}
            title="Force refresh trade history (immediate)"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="23 4 23 10 17 10"></polyline>
              <polyline points="1 20 1 14 7 14"></polyline>
              <path d="m3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
            </svg>
            {isLoading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>
      {trades.length === 0 ? (
        <div className="no-trades">
          <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>
          </svg>
          <p>No trades found in your history</p>
        </div>
      ) : (
        <div className="trades-content">
          {/* Responsive table container */}
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
                  <th className="hidden-mobile">S / L</th>
                  <th className="hidden-mobile">T / P</th>
                  <th className="hidden-tablet">Time</th>
                  <th className="hidden-tablet">Price</th>
                  <th>Profit</th>
                  <th className="hidden-mobile">Change</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((trade) => (
                  <tr 
                    key={trade.id || trade.ticket} 
                    className={`
                      ${trade.profit >= 0 ? 'profit-row' : 'loss-row'} 
                      ${trade.is_open ? 'open-position' : 'closed-position'}
                      ${trade.isNew ? 'new-trade' : ''}
                      ${trade.isUpdated ? 'updated-trade' : ''}
                      ${trade.justClosed ? 'just-closed' : ''}
                    `}
                  >
                    <td>
                      {trade.id || trade.ticket}
                      {trade.isNew && <span className="new-badge">NEW</span>}
                      {trade.justClosed && <span className="closed-badge">CLOSED</span>}
                    </td>
                    <td>{formatDate(trade.timestamp || trade.time)}</td>
                    <td className="symbol-cell">
                      <span className="symbol">{trade.symbol}</span>
                      {trade.is_open && <span className="open-badge">OPEN</span>}
                    </td>
                    <td>
                      <span className={`type-badge ${trade.type === 'BUY' ? 'buy-type' : 'sell-type'}`}>
                        {trade.type}
                      </span>
                    </td>
                    <td>{formatVolume(trade.volume)}</td>
                    <td>{formatCurrency(trade.price || trade.entry_price)}</td>
                    <td className="hidden-mobile">{trade.sl && trade.sl > 0 ? formatCurrency(trade.sl) : '—'}</td>
                    <td className="hidden-mobile">{trade.tp && trade.tp > 0 ? formatCurrency(trade.tp) : '—'}</td>
                    <td className="hidden-tablet">
                      {trade.close_time ? formatDate(trade.close_time) : 
                       trade.is_open ? 'Open' : formatDate(trade.timestamp || trade.time)}
                    </td>
                    <td className="hidden-tablet">{formatCurrency(trade.exit_price || trade.current_price || trade.price || trade.entry_price)}</td>
                    <td className={`profit-cell ${trade.profit >= 0 ? 'profit' : 'loss'}`}>
                      {formatCurrency(trade.profit)}
                    </td>
                    <td className={`change-cell hidden-mobile ${trade.change_percent >= 0 ? 'profit' : 'loss'}`}>
                      {formatChangePercent(trade.change_percent)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          
          {/* Trade Summary Section - Now using backend statistics */}
          <div className="trade-details-summary">
            <h3>Trade Summary</h3>
            <div className="summary-grid">
              <div className="summary-item">
                <span className="label">Total Trades</span>
                <span className="value">{summaryStats.totalTrades}</span>
              </div>
              <div className="summary-item">
                <span className="label">Open Positions</span>
                <span className="value">{summaryStats.openPositions}</span>
              </div>
              <div className="summary-item">
                <span className="label">Profitable</span>
                <span className="value profit">{summaryStats.winningTrades}</span>
              </div>
              <div className="summary-item">
                <span className="label">Losing</span>
                <span className="value loss">{summaryStats.losingTrades}</span>
              </div>
              <div className="summary-item">
                <span className="label">Total Realized P/L</span>
                <span className={`value ${summaryStats.realizedPL >= 0 ? 'profit' : 'loss'}`}>
                  {formatCurrency(summaryStats.realizedPL)}
                </span>
              </div>
              {summaryStats.commission !== 0 && (
                <div className="summary-item">
                  <span className="label">Commission</span>
                  <span className="value">
                    {formatCurrency(summaryStats.commission)}
                  </span>
                </div>
              )}
              {summaryStats.swap !== 0 && (
                <div className="summary-item">
                  <span className="label">Swap</span>
                  <span className="value">
                    {formatCurrency(summaryStats.swap)}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TradeHistory; 