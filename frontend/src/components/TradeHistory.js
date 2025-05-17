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
          throw new Error(`HTTP error! Status: ${response.status}`);
        }
        
        const data = await response.json();
        setTrades(data);
        setError(null);
      } catch (error) {
        console.error('Error fetching trade history:', error);
        setError('Failed to load trade history. Please try again later.');
      } finally {
        setIsLoading(false);
      }
    };
    
    fetchTradeHistory();
  }, []);

  // Format currency with 2 decimal places
  const formatCurrency = (value) => {
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
                <th>Date & Time</th>
                <th>Symbol</th>
                <th>Type</th>
                <th>Volume</th>
                <th>Price</th>
                <th>Profit/Loss</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => (
                <tr key={trade.id} className={trade.profit >= 0 ? 'profit-row' : 'loss-row'}>
                  <td>{trade.id}</td>
                  <td>{formatDate(trade.timestamp)}</td>
                  <td>{trade.symbol}</td>
                  <td className={trade.type === 'BUY' ? 'buy-type' : 'sell-type'}>
                    {trade.type}
                  </td>
                  <td>{trade.volume}</td>
                  <td>{formatCurrency(trade.price)}</td>
                  <td className={trade.profit >= 0 ? 'profit' : 'loss'}>
                    {formatCurrency(trade.profit)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default TradeHistory; 