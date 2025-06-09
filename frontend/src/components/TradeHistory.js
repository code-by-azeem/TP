import React, { useState, useEffect } from 'react';
import './TradeHistory.css';

const TradeHistory = () => {
  const [trades, setTrades] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchTradeHistory = async () => {
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
        console.log("MT5 Trade history data received:", data); // Debug log
        setTrades(data);
        setError(null);
      } catch (error) {
        console.error('Error fetching trade history:', error);
        setError(error.message || 'Failed to load trade history from MT5. Please try again later.');
      } finally {
        setIsLoading(false);
      }
    };
    
    fetchTradeHistory();
  }, []);

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
      <h2>Trade History</h2>
      {trades.length === 0 ? (
        <div className="no-trades">
          <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>
          </svg>
          <p>No trades found in your history</p>
        </div>
      ) : (
        <div className="trades-table-container">
          <table className="trades-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>DATE & TIME</th>
                <th>SYMBOL</th>
                <th>TYPE</th>
                <th>VOLUME</th>
                <th>PRICE</th>
                <th>S / L</th>
                <th>T / P</th>
                <th>TIME</th>
                <th>PRICE</th>
                <th>PROFIT</th>
                <th>CHANGE</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => (
                <tr key={trade.id || trade.ticket} className={`${trade.profit >= 0 ? 'profit-row' : 'loss-row'} ${trade.is_open ? 'open-position' : 'closed-position'}`}>
                  <td>{trade.id || trade.ticket}</td>
                  <td>{formatDate(trade.timestamp || trade.time)}</td>
                  <td className="symbol-cell">
                    {trade.symbol}
                    {trade.is_open && <span className="open-badge">OPEN</span>}
                  </td>
                  <td className={trade.type === 'BUY' ? 'buy-type' : 'sell-type'}>
                    {trade.type}
                  </td>
                  <td>{formatVolume(trade.volume)}</td>
                  <td>{formatCurrency(trade.price || trade.entry_price)}</td>
                  <td>{trade.sl && trade.sl > 0 ? formatCurrency(trade.sl) : '—'}</td>
                  <td>{trade.tp && trade.tp > 0 ? formatCurrency(trade.tp) : '—'}</td>
                  <td>
                    {trade.close_time ? formatDate(trade.close_time) : 
                     trade.is_open ? 'Open' : formatDate(trade.timestamp || trade.time)}
                  </td>
                  <td>{formatCurrency(trade.exit_price || trade.current_price || trade.price || trade.entry_price)}</td>
                  <td className={trade.profit >= 0 ? 'profit' : 'loss'}>
                    {formatCurrency(trade.profit)}
                  </td>
                  <td className={trade.change_percent >= 0 ? 'profit' : 'loss'}>
                    {formatChangePercent(trade.change_percent)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          
          {/* Additional Trade Details Section */}
          <div className="trade-details-summary">
            <h3>Trade Summary</h3>
            <div className="summary-grid">
              <div className="summary-item">
                <span className="label">Total Trades:</span>
                <span className="value">{trades.length}</span>
              </div>
              <div className="summary-item">
                <span className="label">Profitable Trades:</span>
                <span className="value profit">{trades.filter(t => (t.profit || 0) > 0).length}</span>
              </div>
              <div className="summary-item">
                <span className="label">Losing Trades:</span>
                <span className="value loss">{trades.filter(t => (t.profit || 0) < 0).length}</span>
              </div>
              <div className="summary-item">
                <span className="label">Total Profit/Loss:</span>
                <span className={`value ${trades.reduce((sum, t) => sum + (t.profit || 0), 0) >= 0 ? 'profit' : 'loss'}`}>
                  {formatCurrency(trades.reduce((sum, t) => sum + (t.profit || 0), 0))}
                </span>
              </div>
              {trades.some(t => t.commission) && (
                <div className="summary-item">
                  <span className="label">Total Commission:</span>
                  <span className="value">
                    {formatCurrency(trades.reduce((sum, t) => sum + (t.commission || 0), 0))}
                  </span>
                </div>
              )}
              {trades.some(t => t.swap) && (
                <div className="summary-item">
                  <span className="label">Total Swap:</span>
                  <span className="value">
                    {formatCurrency(trades.reduce((sum, t) => sum + (t.swap || 0), 0))}
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