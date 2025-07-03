import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import TradeHistory from './TradeHistory';
import AccountInfo from './AccountInfo';
import CandlestickChart from './CandlestickChart';
import TradingBot from './TradingBot';
import io from 'socket.io-client';
import './Dashboard.css';

const Dashboard = () => {
  const navigate = useNavigate();
  const [username, setUsername] = useState('Trader');
  const [accountData, setAccountData] = useState({
    balance: 0,
    equity: 0,
    margin: 0,
    profit: 0
  });
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('chart'); // Default to chart view
  const [socket, setSocket] = useState(null);
  
  // Fetch account data - wrapped in useCallback to prevent recreation on each render
  const fetchAccountData = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await fetch('http://localhost:5000/account', {
        credentials: 'include',
      });
      
      if (response.ok) {
        const data = await response.json();
        // Map MT5 fields to our expected format
        setAccountData({
          id: data.login || data.id,
          balance: data.balance || 0,
          equity: data.equity || 0,
          margin: data.margin || 0,
          profit: data.profit || 0,
          marginLevel: data.margin_level || data.marginLevel || 0,
          currency: data.currency || 'USD',
          leverage: data.leverage || '1:100',
          lastUpdate: data.lastUpdate || new Date().toISOString()
        });
      }
    } catch (error) {
      console.error('Error fetching account data:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);
  
  // Check if user is authenticated on component mount
  useEffect(() => {
    let newSocket = null;
    
    const checkAuth = async () => {
      try {
        const response = await fetch('http://localhost:5000/auth-check', {
          credentials: 'include',
        });
        
        const data = await response.json();
        
        if (!data.authenticated) {
          // Redirect to login page if not authenticated
          navigate('/');
        } else if (data.username) {
          setUsername(data.username);
          
          // Fetch account data
          fetchAccountData();
          
          // Initialize socket connection
          newSocket = io('http://localhost:5000', {
            transports: ['websocket', 'polling'],
            autoConnect: true,
          });
          
          setSocket(newSocket);
        }
      } catch (error) {
        console.error('Auth check error:', error);
      }
    };
    
    checkAuth();
    
    // Cleanup function
    return () => {
      if (newSocket) {
        newSocket.disconnect();
      }
    };
  }, [navigate, fetchAccountData]);
  
  const handleLogout = async () => {
    try {
      const response = await fetch('http://localhost:5000/logout', {
        method: 'POST',
        credentials: 'include',
      });
      
      if (response.ok) {
        // Redirect to login page after successful logout
        navigate('/');
      } else {
        console.error('Logout failed:', response.statusText);
      }
    } catch (error) {
      console.error('Logout error:', error);
    }
  };
  
  // Format currency with 2 decimal places
  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2
    }).format(value);
  };

  // Handler for tab switching
  const switchTab = (tab) => {
    setActiveTab(tab);
  };
  
  // Render account details tab content
  const renderAccountDetails = () => <AccountInfo />;

  // Determine what content to show based on active tab
  const renderTabContent = () => {
    switch (activeTab) {
      case 'account':
        return renderAccountDetails();
      case 'history':
        return <TradeHistory />;
      case 'bot':
        return <TradingBot socket={socket} />;
      case 'chart':
      default:
        return (
          <>
            <CandlestickChart />
          </>
        );
    }
  };
  
  return (
    <div className="dashboard-container">
      {/* Header/Navbar */}
      <header className="dashboard-header">
        <div className="header-content">
          {/* Brand */}
          <div className="brand">
            <img 
              src="/Logo.png" 
              alt="TradePulse Logo" 
              className="brand-logo"
              onError={(e) => {
                e.target.style.display = 'none';
                e.target.nextSibling.style.display = 'block';
              }}
            />
            <svg 
              xmlns="http://www.w3.org/2000/svg" 
              width="32" 
              height="32" 
              viewBox="0 0 24 24" 
              fill="none" 
              stroke="currentColor" 
              strokeWidth="2" 
              strokeLinecap="round" 
              strokeLinejoin="round"
              className="brand-logo-fallback"
              style={{display: 'none'}}
            >
              <polyline points="22 8 22 2 16 2"></polyline>
              <path d="M22 2L12 12"></path>
              <path d="M8 16l-6 6"></path>
              <path d="M19 21c1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3 1.34 3 3 3z"></path>
              <path d="M3 8a5 5 0 0 1 5-5"></path>
              <path d="M15 3a5 5 0 0 1 5 5"></path>
            </svg>
            <h1>TradePulse</h1>
          </div>

          {/* Tab Navigation */}
          <nav className="tab-navigation">
            <button 
              className={`tab-button ${activeTab === 'chart' ? 'active' : ''}`} 
              onClick={() => switchTab('chart')}
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
              </svg>
              <span>Chart</span>
            </button>
            <button 
              className={`tab-button ${activeTab === 'account' ? 'active' : ''}`} 
              onClick={() => switchTab('account')}
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
                <line x1="8" y1="21" x2="16" y2="21"></line>
                <line x1="12" y1="17" x2="12" y2="21"></line>
              </svg>
              <span>Account Info</span>
            </button>
            <button 
              className={`tab-button ${activeTab === 'history' ? 'active' : ''}`} 
              onClick={() => switchTab('history')}
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"></circle>
                <polyline points="12 6 12 12 16 14"></polyline>
              </svg>
              <span>Trade History</span>
            </button>
            <button 
              className={`tab-button ${activeTab === 'bot' ? 'active' : ''}`} 
              onClick={() => switchTab('bot')}
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 3a6 6 0 0 0-6 6v1a1 1 0 0 0 1 1h2a1 1 0 0 0 1-1V9a2 2 0 1 1 4 0v1a1 1 0 0 0 1 1h2a1 1 0 0 0 1-1V9a6 6 0 0 0-6-6z"></path>
                <path d="M9 12v6a3 3 0 0 0 6 0v-6"></path>
              </svg>
              <span>Trading Bot</span>
            </button>
          </nav>
          
          {/* User Info */}
          <div className="dashboard-user-info">
            <span className="username">{username}</span>
            <button className="logout-button" onClick={handleLogout}>
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
                <path fillRule="evenodd" d="M10 12.5a.5.5 0 0 1-.5.5h-8a.5.5 0 0 1-.5-.5v-9a.5.5 0 0 1 .5-.5h8a.5.5 0 0 1 .5.5v2a.5.5 0 0 0 1 0v-2A1.5 1.5 0 0 0 9.5 2h-8A1.5 1.5 0 0 0 0 3.5v9A1.5 1.5 0 0 0 1.5 14h8a1.5 1.5 0 0 0 1.5-1.5v-2a.5.5 0 0 0-1 0v2z"/>
                <path fillRule="evenodd" d="M15.854 8.354a.5.5 0 0 0 0-.708l-3-3a.5.5 0 0 0-.708.708L14.293 7.5H5.5a.5.5 0 0 0 0 1h8.793l-2.147 2.146a.5.5 0 0 0 .708.708l3-3z"/>
              </svg>
              <span>Logout</span>
            </button>
          </div>
        </div>
      </header>
      
      {/* Stats Panel - only show on chart view */}
      {activeTab === 'chart' && (
        <div className="dashboard-info-panels">
          <div className="info-panel">
            <h3>Balance</h3>
            <p className="value">{isLoading ? '—' : formatCurrency(accountData.balance)}</p>
          </div>
          <div className="info-panel">
            <h3>Equity</h3>
            <p className="value">{isLoading ? '—' : formatCurrency(accountData.equity)}</p>
          </div>
          <div className="info-panel">
            <h3>Margin</h3>
            <p className="value">{isLoading ? '—' : formatCurrency(accountData.margin)}</p>
          </div>
          <div className={`info-panel ${accountData.profit >= 0 ? 'profit' : 'loss'}`}>
            <h3>Profit</h3>
            <p className="value">{isLoading ? '—' : formatCurrency(accountData.profit)}</p>
          </div>
        </div>
      )}
      
      {/* Main Content */}
      <main className="main-content">
        <div className="tab-content">
          {renderTabContent()}
        </div>
      </main>
    </div>
  );
};

export default Dashboard;