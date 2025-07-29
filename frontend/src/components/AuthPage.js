import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Modal from './Modal';
import './AuthPage.css';

const AuthPage = () => {
  const [isLogin, setIsLogin] = useState(true);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  
  // Modal states
  const [modalOpen, setModalOpen] = useState(false);
  const [modalConfig, setModalConfig] = useState({
    title: '',
    message: '',
    type: 'info',
    autoCloseDelay: 0
  });
  
  const navigate = useNavigate();

  const showModal = (title, message, type = 'info', autoCloseDelay = 0) => {
    setModalConfig({ title, message, type, autoCloseDelay });
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Form validation
    if (!username || !username.trim()) {
      setError('Username is required');
      return;
    }
    if (!password || !password.trim()) {
      setError('Password is required');
      return;
    }
    
    setError('');
    setIsLoading(true);
    const endpoint = isLogin ? '/login' : '/signup';
    
    try {
      console.log(`Sending request to: http://localhost:5000${endpoint}`);
      
      const response = await fetch(`http://localhost:5000${endpoint}`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        credentials: 'include',
        mode: 'cors',
        body: JSON.stringify({ username, password }),
      });
      
      // For debugging
      console.log('Response status:', response.status);
      
      let data;
      try {
        data = await response.json();
        console.log('Response data:', data);
      } catch (parseError) {
        console.error('Failed to parse response:', parseError);
        showModal(
          'Response Error', 
          'Invalid response from server. Please try again.', 
          'error'
        );
        return;
      }
      
      if (!response.ok) {
        const errorMessage = data.error || `Error: ${response.status} - ${response.statusText}`;
        
        // Show specific modals for different error types
        if (response.status === 409) {
          // User already exists
          showModal('Account Exists', 'This username is already taken. Please choose another one.', 'error');
        } else if (response.status === 401) {
          // Invalid credentials
          showModal('Login Failed', 'Incorrect username or password. Please try again.', 'error');
        } else {
          // Generic error
          showModal('Error', errorMessage, 'error');
        }
        
        setError(errorMessage);
      } else {
        if (isLogin) {
          // Login successful - redirect to dashboard
          console.log('Login successful, navigating to dashboard');
          navigate('/dashboard');
        } else {
          // Signup successful - show success modal then redirect to login
          showModal(
            'Account Created', 
            'Your account has been created successfully! Please log in to continue.', 
            'success', 
            2000
          );
          
          // Reset form and switch to login
          setUsername('');
          setPassword('');
          
          // Wait for modal to close before switching to login
          setTimeout(() => {
            setIsLogin(true);
          }, 2000);
        }
      }
    } catch (err) {
      console.error('Auth error:', err);
      
      // Provide more specific error messages
      if (err.name === 'TypeError' && (err.message.includes('NetworkError') || err.message.includes('Failed to fetch'))) {
        showModal(
          'Network Error', 
          'Cannot connect to the server. Please check if the backend is running at http://localhost:5000', 
          'error'
        );
        
        // Also check if the server is running correctly
        try {
          const statusCheck = await fetch('http://localhost:5000/status', { 
            method: 'GET',
            mode: 'cors'
          });
          if (statusCheck.ok) {
            showModal(
              'API Connection Issue', 
              'Backend server is running but authentication failed. Check CORS settings.', 
              'error'
            );
          }
        } catch (statusErr) {
          console.log('Status check also failed, backend is likely not running');
        }
      } else {
        showModal(
          'Error', 
          `${err.name || 'Error'}: ${err.message || 'Something went wrong. Please try again.'}`, 
          'error'
        );
      }
      
      setError(`${err.name || 'Error'}: ${err.message || 'Something went wrong. Please try again.'}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleModeToggle = () => {
    setIsLogin(!isLogin);
    setError('');
    setUsername('');
    setPassword('');
  };

  return (
    <div className="auth-page-wrapper">
      {/* Left Side - Bot Image */}
      <div className="auth-left-panel">
        <div className="bot-image-container">
          <img 
            src="/bot.png" 
            alt="TradePulse Trading Bot" 
            className="bot-image"
            onError={(e) => {
              // Fallback if image doesn't exist
              e.target.style.display = 'none';
              e.target.nextSibling.style.display = 'flex';
            }}
          />
          <div className="bot-image-fallback" style={{display: 'none'}}>
            <svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="bot-fallback-icon">
              <path d="M12 8V4H8"/>
              <rect width="16" height="12" x="4" y="8" rx="2"/>
              <path d="M2 14h2"/>
              <path d="M20 14h2"/>
              <path d="M15 13v2"/>
              <path d="M9 13v2"/>
            </svg>
            <p>Trading Bot</p>
          </div>
        </div>
      </div>

      {/* Right Side - Login Form */}
      <div className="auth-right-panel">
        <div className="auth-form-section">
          {/* Welcome Header with Logo */}
          <div className="welcome-header">
            <img 
              src="/logo.png" 
              alt="TradePulse Logo" 
              className="welcome-logo"
              onError={(e) => {
                e.target.style.display = 'none';
                e.target.nextSibling.style.display = 'block';
              }}
            />
            <svg 
              xmlns="http://www.w3.org/2000/svg" 
              width="48" 
              height="48" 
              viewBox="0 0 24 24" 
              fill="none" 
              stroke="currentColor" 
              strokeWidth="2" 
              strokeLinecap="round" 
              strokeLinejoin="round"
              className="welcome-logo-fallback"
              style={{display: 'none'}}
            >
              <polyline points="22 8 22 2 16 2"></polyline>
              <path d="M22 2L12 12"></path>
              <path d="M8 16l-6 6"></path>
              <path d="M19 21c1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3 1.34 3 3 3z"></path>
              <path d="M3 8a5 5 0 0 1 5-5"></path>
              <path d="M15 3a5 5 0 0 1 5 5"></path>
            </svg>
            <h1 className="welcome-title">Welcome to TradePulse</h1>
            <p className="welcome-subtitle">Your Intelligent Trading Companion</p>
          </div>

          {/* Login/Signup Container */}
          <div className="auth-container">
            <h2>{isLogin ? 'Login' : 'Sign Up'}</h2>
            <form onSubmit={handleSubmit}>
              <input
                type="text"
                placeholder="Username"
                value={username}
                onChange={e => setUsername(e.target.value)}
                required
                disabled={isLoading}
                className={error && error.includes('Username') ? 'input-error' : ''}
              />
              <input
                type="password"
                placeholder="Password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                disabled={isLoading}
                className={error && error.includes('Password') ? 'input-error' : ''}
              />
              <button type="submit" disabled={isLoading}>
                {isLoading ? 'Processing...' : (isLogin ? 'Login' : 'Sign Up')}
              </button>
            </form>
            <p className="toggle-link">
              {isLogin ? "Don't have an account?" : "Already have an account?"}
              <button type="button" onClick={handleModeToggle} disabled={isLoading}>
                {isLogin ? 'Sign Up' : 'Login'}
              </button>
            </p>
            {error && <div className="error">{error}</div>}
          </div>
        </div>
      </div>
      
      {/* Modal component */}
      <Modal
        isOpen={modalOpen}
        onClose={closeModal}
        title={modalConfig.title}
        message={modalConfig.message}
        type={modalConfig.type}
        autoCloseDelay={modalConfig.autoCloseDelay}
      />
    </div>
  );
};

export default AuthPage; 