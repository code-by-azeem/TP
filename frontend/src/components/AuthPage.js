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