// frontend/src/components/CandlestickChart.js
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { createChart, CrosshairMode, CandlestickSeries } from 'lightweight-charts';
import io from 'socket.io-client';
import './CandlestickChart.css';

// Use consistent URL format for both HTTP and WebSocket - DO NOT include trailing slash
const FLASK_SERVER_URL = 'http://localhost:5000';

// WebSocket configuration
const SOCKET_OPTIONS = {
    transports: ['websocket', 'polling'],
    reconnectionAttempts: 10,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    timeout: 20000,
    autoConnect: true,
    forceNew: false, // Reuse existing connection if possible
    withCredentials: true,
    pingInterval: 10000, // More frequent ping (10 seconds instead of default 25s)
    pingTimeout: 8000,   // Shorter ping timeout (8 seconds)
};

// Create a global flag to track if data is being fetched to prevent duplicate requests
let isFetchingData = false;

// For logging WebSocket connection debugging messages
const logWebSocketDebug = (message) => {
  console.log(`[WebSocket] ${message}`);
};

// For logging data processing/visualization activities
const logDataDebug = (message) => {
  console.log(`[DataFlow] ${message}`);
};

// Track updates per second for performance monitoring
const updateStats = {
  lastSecond: Date.now(),
  updates: 0,
  total: 0,
  maxPerSecond: 0,
  logStats: function() {
    this.total++;
    this.updates++;
    const now = Date.now();
    if (now - this.lastSecond >= 1000) {
      // Only log when there are significant updates
      if (this.updates > 0) {
        this.maxPerSecond = Math.max(this.maxPerSecond, this.updates);
        logDataDebug(`Updates: ${this.updates}/sec (max: ${this.maxPerSecond}, total: ${this.total})`);
      }
      this.updates = 0;
      this.lastSecond = now;
    }
  }
};

function CandlestickChart() {
    const chartContainerRef = useRef(null);
    const chartRef = useRef(null);
    const candlestickSeriesRef = useRef(null);
    const socketRef = useRef(null);
    const lastUpdateRef = useRef(null);
    const dataLoadedRef = useRef(false);  // Track if data has been loaded
    const timeframeRef = useRef('1m');  // Keep track of current timeframe in a ref
    const reconnectTimeoutRef = useRef(null); // For tracking reconnection attempts
    const reconnectCountRef = useRef(0); // Track connection attempts

    const [timeframe, setTimeframe] = useState('1m');
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState(null);
    const [isConnected, setIsConnected] = useState(false);
    const [lastUpdateTime, setLastUpdateTime] = useState(null);
    const [isFullscreen, setIsFullscreen] = useState(false);

    // Helper function to ensure timestamp is in seconds (not milliseconds)
    const normalizeTimestamp = useCallback((timestamp) => {
        // Handle different types of timestamp inputs
        if (timestamp === undefined || timestamp === null) {
            console.error("Invalid timestamp (null or undefined)");
            return Math.floor(Date.now() / 1000); // Fallback to current time
        }
        
        // If it's an object (potentially a Date or something else)
        if (typeof timestamp === 'object') {
            // Try to use valueOf() for Date objects
            if (timestamp.valueOf && typeof timestamp.valueOf === 'function') {
                timestamp = timestamp.valueOf();
            } else {
                // If we can't extract a value, use current time
                console.error("Unable to extract numeric value from timestamp object:", timestamp);
                return Math.floor(Date.now() / 1000);
            }
        }
        
        // Convert string to number if needed
        if (typeof timestamp === 'string') {
            // Try to parse as number first
            const parsed = Number(timestamp);
            if (!isNaN(parsed)) {
                timestamp = parsed;
            } else {
                // Try to parse as date string
                try {
                    const date = new Date(timestamp);
                    if (!isNaN(date.getTime())) {
                        timestamp = date.getTime();
                    } else {
                        throw new Error("Invalid date string");
                    }
                } catch (e) {
                    console.error("Failed to parse timestamp string:", timestamp, e);
                    return Math.floor(Date.now() / 1000);
                }
            }
        }
        
        let timeValue = Number(timestamp);
        if (isNaN(timeValue)) { 
            console.error("Invalid timestamp after conversion attempts:", timestamp);
            return Math.floor(Date.now() / 1000); // Fallback to current time in seconds
        }
        
        // If timestamp is likely in milliseconds (e.g., > 10 digits for typical Unix seconds)
        if (timeValue > 99999999999) { // Heuristic for ms vs s
            timeValue = Math.floor(timeValue / 1000);
        }
        
        // Ensure we return an integer
        return Math.floor(timeValue);
    }, []);

    // Helper function to create dummy data if needed - wrapped in useCallback to prevent recreation on each render
    const createDummyData = useCallback(() => {
        // Ensure timestamp is in seconds
        const now = Math.floor(Date.now() / 1000);
        
        const timeframeInSeconds = {
            '1m': 60,
            '5m': 300,
            '1h': 3600,
            '4h': 14400,
            '1d': 86400,
            '1w': 604800
        };
        
        // Get the current timeframe or default to 1m
        const currentTf = timeframeRef.current || '1m';
        const interval = timeframeInSeconds[currentTf] || 60;
        const dummyData = [];
        
        // Base price and volatility for more realistic movement
        const basePrice = 2636;
        let currentPrice = basePrice;
        
        // Create 100 candles
        for (let i = 100; i >= 0; i--) {
            // Ensure the timestamp is a simple integer number of seconds
            const time = Math.floor(now - (i * interval));
            
            // Calculate price movement with trend
            const priceChange = (Math.random() > 0.5 ? 1 : -1) * Math.random() * 5;
            currentPrice += priceChange;
            
            // Create candle with open/close
            const open = currentPrice;
            const close = currentPrice * (1 + (Math.random() * 0.006 - 0.003));
            const high = Math.max(open, close) * 1.002;
            const low = Math.min(open, close) * 0.998;
            
            // Only add properly formatted data points with integer timestamps
            dummyData.push({
                time: time,
                open: parseFloat(open.toFixed(2)),
                high: parseFloat(high.toFixed(2)),
                low: parseFloat(low.toFixed(2)),
                close: parseFloat(close.toFixed(2))
            });
        }
        
        console.log("Generated dummy data sample:", dummyData.slice(0, 2));
        return dummyData;
    }, [timeframeRef]);

    // Fetch historical data - defined early to avoid "used before defined" warnings
    const fetchHistoricalData = useCallback(async (selectedTimeframe) => {
        if (!chartRef.current || !candlestickSeriesRef.current) {
            console.warn("Chart refs not ready for fetching data");
            return;
        }
        
        // Check global fetching flag to prevent multiple simultaneous requests
        if (isFetchingData) {
            console.log("Already fetching data, request ignored");
            return;
        }
        
        logDataDebug(`Fetching historical data for timeframe: ${selectedTimeframe}`);
        
        // Update the timeframe ref to ensure all components are in sync
        timeframeRef.current = selectedTimeframe;
        
        // Set loading state and fetching flag
        setIsLoading(true);
        isFetchingData = true;
        setError(null);
        
        // Fetch count tracking for logging
        console.log(`Fetching data for timeframe: ${selectedTimeframe}`);
        
        try {
            const apiUrl = `${FLASK_SERVER_URL}/data?timeframe=${selectedTimeframe}`;
            logDataDebug(`Requesting data from: ${apiUrl}`);
            
            // Update fetch headers to avoid CORS issues - remove cache-control header
            const response = await fetch(apiUrl, {
                credentials: 'include',
                headers: {
                    'Accept': 'application/json'
                    // Removed 'Cache-Control' header which caused CORS preflight failure
                }
            });
            
            // Check for service unavailable (MT5 connection issues)
            if (response.status === 503) {
                console.warn("MT5 connection unavailable, using dummy data");
                const dummyData = createDummyData();
                candlestickSeriesRef.current.setData(dummyData);
                chartRef.current.timeScale().fitContent();
                dataLoadedRef.current = true;
                return;
            }
            
            // Other error types
            if (!response.ok) {
                let errorMsg = `HTTP ${response.status}`;
                try { 
                    const errorData = await response.json();
                    errorMsg = errorData.error || errorMsg; 
                } catch(e) {
                    console.error("Failed to parse error response:", e);
                }
                throw new Error(errorMsg);
            }
            
            // Parse the response
            const responseData = await response.json();
            
            // Handle the response format
            let chartData;
            if (responseData && responseData.dummy_data) {
                // This is dummy data with the new format
                chartData = responseData.data;
                
                // Display any error message
                if (responseData.error) {
                    setError(`MT5 Warning: ${responseData.error}`);
                }
            } else {
                // Standard data array format
                chartData = responseData;
                logDataDebug(`Received ${chartData.length} historical points for timeframe ${selectedTimeframe}`);
            }
            
            if (!chartData || chartData.length === 0) {
                console.warn("Received empty data set, using client dummy data");
                const dummyData = createDummyData();
                candlestickSeriesRef.current.setData(dummyData);
                chartRef.current.timeScale().fitContent();
                dataLoadedRef.current = true;
                return;
            }
            
            // Log the raw data sample for debugging
            logDataDebug(`Raw data sample (first 2 items): ${JSON.stringify(chartData.slice(0, 2))}`);
            
            // Format the data for the chart
            const formattedData = chartData
                .map(item => {
                    try {
                        // Handle possible null or undefined values
                        if (!item || typeof item !== 'object') {
                            console.error("Invalid data point:", item);
                            return null;
                        }
                        
                        // Use our robust timestamp normalization on each item
                        let timeValue;
                        
                        // Handle case where time might be an object
                        if (typeof item.time === 'object') {
                            // If it's an object (like a Date), convert to timestamp and normalize
                            timeValue = normalizeTimestamp(item.time.valueOf ? item.time.valueOf() : Date.now());
                        } else {
                            // Otherwise try to normalize whatever we have
                            timeValue = normalizeTimestamp(item.time);
                        }
                        
                        // Ensure all values are properly converted to numbers
                        const openValue = Number(item.open);
                        const highValue = Number(item.high);
                        const lowValue = Number(item.low);
                        const closeValue = Number(item.close);
                        
                        // Validate each value to ensure they are proper numbers
                        if (isNaN(timeValue) || isNaN(openValue) || isNaN(highValue) || isNaN(lowValue) || isNaN(closeValue)) {
                            console.error("Invalid data point values:", { 
                                time: item.time, 
                                normalizedTime: timeValue,
                                open: item.open, 
                                high: item.high, 
                                low: item.low, 
                                close: item.close 
                            });
                            return null;
                        }
                        
                        // Debug log for the first few items
                        if (chartData.indexOf(item) < 3) {
                            console.log(`Timestamp conversion: ${item.time} (${typeof item.time}) → ${timeValue} (${typeof timeValue})`);
                        }
                        
                        return { 
                            time: timeValue, 
                            open: openValue, 
                            high: highValue, 
                            low: lowValue, 
                            close: closeValue 
                        };
                    } catch (err) {
                        console.error("Error formatting data point:", err, item);
                        return null;
                    }
                })
                .filter(item => item !== null) // Remove any invalid items
                .sort((a, b) => a.time - b.time);

            logDataDebug(`Formatted ${formattedData.length} data points for ${selectedTimeframe}`);
            
            if (formattedData.length === 0) {
                console.error("All data points were invalid, using dummy data");
                const dummyData = createDummyData();
                candlestickSeriesRef.current.setData(dummyData);
                chartRef.current.timeScale().fitContent();
                dataLoadedRef.current = true;
                return;
            }
            
            // Set the data in the chart
            try {
                // Final validation before setting data to chart
                const validFormattedData = formattedData.map(candle => {
                    // Ensure time is a primitive number (not an object, string, etc.)
                    if (typeof candle.time !== 'number') {
                        console.error("Invalid time format detected before chart update:", candle.time);
                        // Convert to number one final time
                        candle.time = normalizeTimestamp(candle.time);
                    }
                    return candle;
                });
                
                // Log some sample data for debugging
                if (validFormattedData.length > 0) {
                    console.log("Sample data before setData:", 
                        validFormattedData.slice(0, 3).map(d => ({
                            time: d.time, 
                            time_type: typeof d.time, 
                            open: d.open
                        }))
                    );
                }
                
                // IMPORTANT: Use setData, not update for historical data
                candlestickSeriesRef.current.setData(validFormattedData);
                logDataDebug(`Successfully set ${validFormattedData.length} historical candles`);
                
                // Store the last candle time for later comparison
                if (validFormattedData.length > 0) {
                    const lastCandle = validFormattedData[validFormattedData.length - 1];
                    window.lastCandleTime = lastCandle.time;
                    logDataDebug(`Last historical candle time: ${new Date(lastCandle.time * 1000).toISOString()}`);
                }
            } catch (chartErr) {
                console.error("Error setting data to chart:", chartErr);
                setError(`Chart error: ${chartErr.message}`);
                return;
            }
            
            // Ensure chart fits all data
            try {
                chartRef.current.timeScale().fitContent();
                logDataDebug("Chart fitted to content");
            } catch (fitErr) {
                console.error("Error fitting chart content:", fitErr);
            }
            
            // Mark data as loaded
            dataLoadedRef.current = true;
            
        } catch (err) { 
            console.error(`Historical data fetch error for ${selectedTimeframe}:`, err);
            setError(`Data fetch failed: ${err.message}`);
            
            // Use dummy data as fallback for any error
            console.log("Using dummy data due to fetch error");
            const dummyData = createDummyData();
            candlestickSeriesRef.current.setData(dummyData);
            chartRef.current.timeScale().fitContent();
            dataLoadedRef.current = true;
        } finally { 
            setIsLoading(false);
            // Reset the fetching flag
            isFetchingData = false;
        }
    }, [normalizeTimestamp, createDummyData]);

    // Refactored handler for M1 candlestick updates from backend - defined early to avoid "used before defined" warnings
    const handleCandleUpdate = useCallback((m1Candle) => {
        if (!candlestickSeriesRef.current || !chartRef.current) {
            console.warn("Chart not ready for candle update");
            return;
        }

        try {
            // Make sure we have a valid candle object first
            if (!m1Candle || typeof m1Candle !== 'object') {
                console.error("Invalid candle data received:", m1Candle);
                return;
            }

            // Convert incoming data to proper types FIRST, outside requestAnimationFrame
            // Handle case where time might be an object or string instead of a number
            let m1Time;
            if (typeof m1Candle.time === 'object') {
                // If it's an object (like a Date), convert to timestamp and normalize
                m1Time = normalizeTimestamp(m1Candle.time.valueOf ? m1Candle.time.valueOf() : Date.now());
            } else {
                // Otherwise try to normalize whatever we have
                m1Time = normalizeTimestamp(m1Candle.time);
            }
            
            const m1Open = Number(m1Candle.open);
            const m1High = Number(m1Candle.high);
            const m1Low = Number(m1Candle.low);
            const m1Close = Number(m1Candle.close);

            // Validation before animation frame
            if (isNaN(m1Time) || isNaN(m1Open) || isNaN(m1High) || isNaN(m1Low) || isNaN(m1Close)) {
                console.error("Invalid candle data received:", m1Candle);
                return;
            }
            
            // Format the candle with proper types
            const candle = {
                time: m1Time,
                open: m1Open,
                high: m1High,
                low: m1Low,
                close: m1Close
            };

            // Log pre-update for debugging
            console.log(`Updating candle - time: ${m1Time} (${typeof m1Time}) - original:`, m1Candle.time);

            // Now use requestAnimationFrame with properly formatted data
            requestAnimationFrame(() => {
                // Update UI state for activity indication
                lastUpdateRef.current = new Date();
                setLastUpdateTime(new Date().toLocaleTimeString([], { 
                    hour: 'numeric', 
                    minute: '2-digit', 
                    second: '2-digit', 
                    hour12: true 
                }));
                updateStats.logStats();

                // Use the already-validated candle data
                candlestickSeriesRef.current.update(candle);
                
                // Log update
                logDataDebug(`Updated candle at ${new Date(m1Time*1000).toLocaleTimeString()}: O:${m1Open.toFixed(2)} H:${m1High.toFixed(2)} L:${m1Low.toFixed(2)} C:${m1Close.toFixed(2)}`);
            });
        } catch (err) {
            console.error("Error updating candle:", err, m1Candle);
        }
    }, [normalizeTimestamp]);

    // Implementation of the handleReconnect function with exponential backoff - defined early to avoid "used before defined" warnings
    const handleReconnect = useCallback(() => {
        // Clear any existing reconnect timeout
        if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
            reconnectTimeoutRef.current = null;
        }

        // Calculate delay with exponential backoff (1s, 2s, 4s, 8s, etc.)
        const delay = Math.min(1000 * Math.pow(2, reconnectCountRef.current), 30000); // Cap at 30 seconds
        
        logWebSocketDebug(`Reconnection attempt ${reconnectCountRef.current + 1} scheduled in ${delay}ms`);
        
        // Increment reconnect counter
        reconnectCountRef.current += 1;
        
        // Schedule reconnection
        reconnectTimeoutRef.current = setTimeout(() => {
            // Don't try endlessly
            if (reconnectCountRef.current > 10) {
                logWebSocketDebug('Maximum reconnection attempts reached, giving up');
                setError('Connection lost. Please refresh the page to reconnect.');
                return;
            }
            
            logWebSocketDebug(`Attempting to reconnect (attempt ${reconnectCountRef.current})`);
            
            // Initialize socket with the current timeframe
            if (initSocketRef.current) {
                initSocketRef.current();
            }
        }, delay);
    }, []);

    // Fix dependency cycle by using useRef for the socket initialization function
    const initSocketRef = useRef(null);
    
    // Initialize Socket.IO connection with proper error handling and reconnection
    const initializeSocket = useCallback(() => {
        if (socketRef.current) {
            // Clean up existing socket properly
            socketRef.current.removeAllListeners();
            socketRef.current.close();
        }

        logWebSocketDebug(`Attempting to connect to WebSocket at ${FLASK_SERVER_URL} with timeframe ${timeframeRef.current}`);
        
        try {
            // Improved transport selection - explicitly prefer websocket
            const connectionOptions = {
                ...SOCKET_OPTIONS,
                query: { 
                    timeframe: timeframeRef.current,
                    client_version: '1.1.0',
                    update_mode: 'realtime' // Request real-time mode explicitly
                },
                transports: ['websocket'], // Start with WebSocket only
                upgrade: true // Allow upgrading from polling if needed
            };
            
            logWebSocketDebug(`Connection options: ${JSON.stringify(connectionOptions)}`);
            
            // Create a new socket instance with the correct configuration
            socketRef.current = io(FLASK_SERVER_URL, connectionOptions);

            // Connection event handling
            socketRef.current.on('connect', () => {
                logWebSocketDebug(`Socket connected: ${socketRef.current.id} via ${socketRef.current.io.engine.transport.name}`);
                setIsConnected(true);
                setError(null);
                reconnectCountRef.current = 0; // Reset reconnection attempts
                
                // Socket connected successfully
                
                // Request initial data with the current timeframe
                socketRef.current.emit('set_timeframe', { 
                    timeframe: timeframeRef.current,
                    full_history: true // Request complete history
                });
                
                // Let the server know we're ready for real-time updates
                socketRef.current.emit('client_ready', { 
                    timeframe: timeframeRef.current, 
                    clientInfo: {
                        timestamp: new Date().getTime(),
                        userAgent: navigator.userAgent,
                        screen: `${window.innerWidth}x${window.innerHeight}`,
                        update_frequency: 'high'
                    }
                });
                
                // Request high-frequency updates (100ms or faster if possible)
                socketRef.current.emit('set_update_frequency', {
                    frequency: 'realtime',
                    max_delay: 50  // Target 50ms between updates for smoother experience
                });

                // Set high-frequency update mode
                socketRef.current.emit('set_update_mode', { 
                    mode: 'high_frequency',
                    preferred_interval: 100 // 100ms for smoother updates
                });
            });

            // Track transport changes
            socketRef.current.io.engine.on('transportChange', (transport) => {
                logWebSocketDebug(`Transport changed to: ${transport.name}`);
            });
            
            // Log upgraded connections
            socketRef.current.io.engine.on('upgrade', (transport) => {
                logWebSocketDebug(`Connection upgraded to: ${transport}`);
            });

            // Connection acknowledgment from server
            socketRef.current.on('connection_ack', (data) => {
                logWebSocketDebug(`Connection acknowledged by server: ${JSON.stringify(data)}`);
                setLastUpdateTime(new Date().toLocaleTimeString([], { 
                    hour: 'numeric', 
                    minute: '2-digit', 
                    second: '2-digit', 
                    hour12: true 
                }));
            });

            // Handle price updates
            socketRef.current.on('price_update', (data) => {
                if (!data) {
                    console.error("Received empty price update");
                    return;
                }
                
                try {
                    // Debug log to see what format we're receiving
                    console.debug("Received price update:", JSON.stringify(data).substring(0, 200));
                    
                    // Process the update if we have valid data
                    if (data && (data.timeframe || data.time)) {
                        // Check if this update is for our current timeframe or if timeframe not specified
                        const updateTimeframe = data.timeframe || timeframeRef.current;
                        
                        // First, validate and fix the timestamp before any processing
                        if (data.time) {
                            // Ensure time is a proper number, not an object
                            if (typeof data.time === 'object') {
                                console.log("Converting object timestamp from WebSocket:", data.time);
                                data.time = normalizeTimestamp(data.time.valueOf ? data.time.valueOf() : Date.now());
                            } else {
                                data.time = normalizeTimestamp(data.time);
                            }
                            
                            // Final check that it's a number
                            if (typeof data.time !== 'number') {
                                console.error("Failed to convert timestamp to number:", data.time);
                                data.time = Math.floor(Date.now() / 1000); // Use current time as fallback
                            }
                        }
                        
                        if (updateTimeframe === timeframeRef.current) {
                            // Process the update for the current timeframe
                            handleCandleUpdate(data);
                        } else {
                            // Log timeframe mismatch but don't block processing
                            logDataDebug(`Timeframe mismatch: received ${updateTimeframe}, expecting ${timeframeRef.current}`);
                        }
                        
                        // Update UI state regardless of the timeframe (shows user there's activity)
                        setLastUpdateTime(new Date().toLocaleTimeString([], { 
                            hour: 'numeric', 
                            minute: '2-digit', 
                            second: '2-digit', 
                            hour12: true 
                        }));
                    } else {
                        console.warn("Received invalid price update structure:", data);
                    }
                } catch (err) {
                    console.error("Error processing price update:", err, data);
                }
            });

            // Connection status updates
            socketRef.current.on('connection_status', (data) => {
                console.log("Connection status update:", data);
                if (data.status === 'disconnected') {
                    setError(`MT5 connection lost: ${data.message || 'No connection to trading server'}`);
                } else if (data.status === 'connected') {
                    setError(null);
                }
            });

            // Handle disconnections
            socketRef.current.on('disconnect', (reason) => {
                logWebSocketDebug(`Socket disconnected. Reason: ${reason}`);
                setIsConnected(false);
                
                // Only trigger reconnect for certain disconnection reasons
                if (reason === 'io server disconnect' || reason === 'transport close' || reason === 'ping timeout') {
                    logWebSocketDebug(`Critical disconnect reason: ${reason}. Will handle reconnection.`);
                    handleReconnect();
                } else if (reason === 'io client disconnect') {
                    // This is an intentional disconnect - don't auto-reconnect
                    logWebSocketDebug('Client-initiated disconnect. Not auto-reconnecting.');
                } else {
                    // For other disconnect reasons, let the built-in reconnection handle it
                    logWebSocketDebug(`Using built-in reconnection for reason: ${reason}`);
                }
                
                // Log disconnect reason
                if (reason !== 'io client disconnect') {
                    console.log(`Disconnect logged: ${reason} at ${new Date().toLocaleTimeString()}`);
                }
            });

            // Handle connection errors
            socketRef.current.on('connect_error', (err) => {
                logWebSocketDebug(`Socket connection error: ${err.message}`);
                setIsConnected(false);
                setError(`Connection error: ${err.message}`);
                
                console.log(`Connect Error logged: ${err.message} at ${new Date().toLocaleTimeString()}`);
                
                // Let the socket's built-in reconnection handle this
            });

            // Handle reconnection attempts
            socketRef.current.io.on('reconnect_attempt', (attemptNumber) => {
                logWebSocketDebug(`Socket reconnection attempt ${attemptNumber}`);
            });

            // Handle successful reconnection
            socketRef.current.io.on('reconnect', (attemptNumber) => {
                logWebSocketDebug(`Socket reconnected after ${attemptNumber} attempts`);
                setError(null);
                
                // Request data refresh on successful reconnection
                setTimeout(() => {
                    if (socketRef.current && socketRef.current.connected) {
                        socketRef.current.emit('set_timeframe', { timeframe: timeframeRef.current });
                        logWebSocketDebug(`Refreshed timeframe data after reconnection: ${timeframeRef.current}`);
                    }
                }, 500);
            });

            // Handle failed reconnection
            socketRef.current.io.on('reconnect_failed', () => {
                logWebSocketDebug('Socket reconnection failed');
                setError('Failed to reconnect after multiple attempts. Please refresh the page.');
            });

            // Socket error event
            socketRef.current.on('error', (err) => {
                logWebSocketDebug(`Socket error: ${err.message}`);
                console.log(`Socket Error logged: ${err.message} at ${new Date().toLocaleTimeString()}`);
            });

            // Pong responses (for tracking latency)
            socketRef.current.on('pong', (latency) => {
                logWebSocketDebug(`Pong received with latency: ${latency}ms`);
            });
            
            // Set up activity pings to keep connection alive and detect silent failures
            const pingInterval = setInterval(() => {
                if (socketRef.current && socketRef.current.connected) {
                    const pingStart = new Date();
                    socketRef.current.emit('ping_server', { timestamp: pingStart.getTime() }, (response) => {
                        const latency = new Date() - pingStart;
                        logWebSocketDebug(`Ping response received with latency: ${latency}ms`);
                        
                        // Update the last update reference to show activity
                        lastUpdateRef.current = new Date();
                    });
                }
            }, 10000); // Send heartbeat ping every 10 seconds
            
            // Cleanup ping interval on component unmount
            return () => {
                clearInterval(pingInterval);
                if (socketRef.current) {
                    socketRef.current.disconnect();
                }
            };
        } catch (err) {
            logWebSocketDebug(`Failed to initialize socket: ${err.message}`);
            setError(`Failed to connect: ${err.message}`);
            handleReconnect();
        }
    }, [handleCandleUpdate, handleReconnect, normalizeTimestamp]);

    // Store the function in ref to break dependency cycle
    useEffect(() => {
        initSocketRef.current = initializeSocket;
    }, [initializeSocket]);

    // Set up the chart when component mounts
    useEffect(() => {
        if (!chartContainerRef.current || chartRef.current) return;
        
        const initTimer = setTimeout(() => {
            console.log("Initializing chart instance...");
            try {
                // --- Chart Options Structure ---
                const chartOptions = {
                    width: chartContainerRef.current.clientWidth > 0 ? chartContainerRef.current.clientWidth : 600,
                    height: 600,
                    layout: {
                        background: { type: 'solid', color: '#000000' }, 
                        textColor: 'rgba(255, 255, 255, 0.9)',
                        attributionLogo: false, // Remove TradingView logo
                    },
                    grid: {
                        vertLines: { color: 'rgba(197, 203, 206, 0.1)' },
                        horzLines: { color: 'rgba(197, 203, 206, 0.1)' }
                    },
                    crosshair: { mode: CrosshairMode.Normal },
                    rightPriceScale: { 
                        borderColor: 'rgba(197, 203, 206, 0.6)',
                        autoScale: true,
                    },
                    timeScale: { 
                        borderColor: 'rgba(197, 203, 206, 0.6)', 
                        timeVisible: true, 
                        secondsVisible: false,
                        rightOffset: 12,
                        barSpacing: 6,
                        lockVisibleTimeRangeOnResize: true,
                        rightBarStaysOnScroll: true,
                        borderVisible: true,
                        visible: true,
                    },
                };

                // Create the chart instance
                const chart = createChart(chartContainerRef.current, chartOptions);
                chartRef.current = chart;
                
                // Configure candlestick series options
                const candlestickSeriesOptions = {
                    upColor: '#26a69a', 
                    downColor: '#ef5350', 
                    borderDownColor: '#ef5350', 
                    borderUpColor: '#26a69a', 
                    wickDownColor: '#ef5350', 
                    wickUpColor: '#26a69a',
                    priceFormat: {
                        type: 'price',
                        precision: 2,
                        minMove: 0.01,
                    }
                };
                
                // Add a candlestick series using v5 method
                const series = chart.addSeries(CandlestickSeries, candlestickSeriesOptions);
                candlestickSeriesRef.current = series;
                
                // Override the update method to ensure timestamps are always numeric
                const originalUpdate = series.update.bind(series);
                series.update = (candle) => {
                    try {
                        if (!candle) return;
                        
                        // Ensure time is a numeric timestamp, not an object
                        if (typeof candle.time === 'object') {
                            console.log("Converting object timestamp to number before update:", candle.time);
                            candle.time = normalizeTimestamp(candle.time.valueOf ? candle.time.valueOf() : Date.now());
                        } else if (typeof candle.time !== 'number') {
                            console.log("Converting non-number timestamp to number:", candle.time);
                            candle.time = normalizeTimestamp(candle.time);
                        }
                        
                        // Convert all values to proper numbers
                        const safeCandle = {
                            time: Number(candle.time),
                            open: Number(candle.open),
                            high: Number(candle.high),
                            low: Number(candle.low),
                            close: Number(candle.close)
                        };
                        
                        // Call the original update with the safe candle
                        return originalUpdate(safeCandle);
                    } catch (err) {
                        console.error("Error in series update:", err, candle);
                    }
                };
                
                // Override the setData method to ensure all timestamps are numeric
                const originalSetData = series.setData.bind(series);
                series.setData = (candles) => {
                    try {
                        if (!candles || !Array.isArray(candles)) {
                            console.warn("Invalid data for setData:", candles);
                            return originalSetData([]);
                        }
                        
                        // Process each candle to ensure proper format
                        const safeCandles = candles.map(candle => {
                            // Skip invalid candles
                            if (!candle) return null;
                            
                            // Ensure time is a numeric timestamp, not an object
                            let candleTime;
                            if (typeof candle.time === 'object') {
                                candleTime = normalizeTimestamp(candle.time.valueOf ? candle.time.valueOf() : Date.now());
                            } else {
                                candleTime = normalizeTimestamp(candle.time);
                            }
                            
                            // Skip candles with invalid time
                            if (isNaN(candleTime)) {
                                console.warn("Skipping candle with invalid time:", candle);
                                return null;
                            }
                            
                            return {
                                time: candleTime,
                                open: Number(candle.open),
                                high: Number(candle.high),
                                low: Number(candle.low),
                                close: Number(candle.close)
                            };
                        }).filter(candle => candle !== null);
                        
                        if (safeCandles.length > 0) {
                            console.log("Setting data with first timestamp:", safeCandles[0].time, "of type:", typeof safeCandles[0].time);
                        }
                        
                        // Call the original setData with the safe candles
                        return originalSetData(safeCandles);
                    } catch (err) {
                        console.error("Error in series setData:", err);
                        return originalSetData([]);
                    }
                };
                
                // Batch rendering for high-frequency updates
                let updateBatch = [];
                let batchUpdateTimer = null;
                
                // Define batch update function available to the component
                window.batchUpdateChart = (update) => {
                    if (!candlestickSeriesRef.current) return;
                    
                    // Add to batch
                    updateBatch.push(update);
                    
                    // If timeout isn't set, schedule an update
                    if (!batchUpdateTimer) {
                        batchUpdateTimer = setTimeout(() => {
                            if (updateBatch.length > 0) {
                                try {
                                    // Process all updates at once
                                    const lastUpdate = updateBatch[updateBatch.length - 1];
                                    candlestickSeriesRef.current.update(lastUpdate);
                                    
                                    if (updateBatch.length > 1) {
                                        logDataDebug(`Batch processed ${updateBatch.length} updates`);
                                    }
                                } catch (err) {
                                    console.error("Error in batch update:", err);
                                }
                                updateBatch = [];
                            }
                            batchUpdateTimer = null;
                        }, 8); // ~120fps
                    }
                };
                
                // Set up window resize handler
                const handleResize = () => { 
                    if (chartRef.current && chartContainerRef.current) {
                        const rect = chartContainerRef.current.getBoundingClientRect();
                        const width = Math.max(rect.width, 300);
                        const height = Math.max(rect.height, 200);
                        
                        chartRef.current.applyOptions({
                            width: width,
                            height: height,
                            timeScale: {
                                timeVisible: true,
                                secondsVisible: width > 600, // Show seconds only on larger screens
                                rightOffset: width > 768 ? 12 : 8,
                                barSpacing: width > 768 ? 6 : 4,
                                borderVisible: true,
                                visible: true,
                                fixLeftEdge: false,
                                fixRightEdge: false,
                                lockVisibleTimeRangeOnResize: true,
                                rightBarStaysOnScroll: true,
                                borderColor: 'rgba(197, 203, 206, 0.6)',
                            }
                        });
                    }
                };
                
                window.addEventListener('resize', handleResize);
                handleResize(); // Initial call
                
                // Fetch historical data and initialize WebSocket after chart setup
                fetchHistoricalData(timeframeRef.current)
                    .then(() => {
                        initializeSocket();
                        // Fit content after data loaded
                        chartRef.current.timeScale().fitContent();
                    })
                    .catch(err => {
                        console.error("Failed to load historical data:", err);
                        // Use dummy data as fallback
                        const dummyData = createDummyData();
                        if (candlestickSeriesRef.current && dummyData.length > 0) {
                            candlestickSeriesRef.current.setData(dummyData);
                            chartRef.current.timeScale().fitContent();
                        }
                        initializeSocket();
                    });
                
                // Add global error handler for chart operations
                window.addEventListener('error', (event) => {
                    // Check if the error is from the chart library
                    if (event.message && event.message.includes("Cannot update oldest data")) {
                        console.error("Caught chart error:", event.message);
                        event.preventDefault(); // Prevent the error from propagating
                        
                        // Try to recover by refreshing the data
                        try {
                            if (candlestickSeriesRef.current) {
                                console.log("Attempting recovery from chart error...");
                                
                                // Clear the chart data
                                candlestickSeriesRef.current.setData([]);
                                
                                // Queue a refresh after a short delay
                                setTimeout(() => {
                                    if (fetchHistoricalData && !isFetchingData) {
                                        fetchHistoricalData(timeframeRef.current)
                                            .catch(err => console.error("Error during recovery:", err));
                                    }
                                }, 500);
                            }
                        } catch (recoveryErr) {
                            console.error("Failed to recover from chart error:", recoveryErr);
                        }
                        
                        return true; // Indicate we've handled the error
                    }
                });
                
                // Cleanup when component unmounts
                return () => {
                    console.log("Cleaning up chart resources...");
                    window.removeEventListener('resize', handleResize);
                    if (socketRef.current) {
                        socketRef.current.disconnect();
                        socketRef.current = null;
                    }
                    if (chartRef.current) {
                        chartRef.current.remove();
                        chartRef.current = null;
                    }
                    clearTimeout(initTimer);
                };
            } catch (err) {
                console.error("Chart initialization error:", err);
                setError(`Chart Init Failed: ${err.message}`);
                setIsLoading(false);
            }
        }, 100);
        
        return () => clearTimeout(initTimer);
    }, [fetchHistoricalData, initializeSocket, normalizeTimestamp, handleCandleUpdate, createDummyData]);

    // Effect for handling timeframe changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => {
        if (!candlestickSeriesRef.current || !chartRef.current || isLoading) return;
        
        console.log(`Timeframe state changed to ${timeframe}, ref is ${timeframeRef.current}`);
        
        // Update timescale options if needed, e.g., secondsVisible
                                const container = chartContainerRef.current;
                        const rect = container ? container.getBoundingClientRect() : { width: 600 };
                        const containerWidth = Math.max(rect.width, 300);
                        
                        chartRef.current.timeScale().applyOptions({ 
                            timeVisible: true,
                            secondsVisible: containerWidth > 600 && (timeframe === '1m' || timeframe === '5m'), // Show seconds for smaller timeframes only on larger screens
                            rightOffset: containerWidth > 768 ? 12 : 8,
                            barSpacing: containerWidth > 768 ? 6 : 4,
                            borderVisible: true,
                            visible: true,
                            fixLeftEdge: false,
                            fixRightEdge: false,
                            lockVisibleTimeRangeOnResize: true,
                            rightBarStaysOnScroll: true,
                            borderColor: 'rgba(197, 203, 206, 0.6)',
                        });
        
        if (timeframeRef.current !== timeframe) {
            console.log(`Timeframe changed from ${timeframeRef.current} to ${timeframe}. Fetching new historical data...`);
            
            // Update the ref to the new timeframe before any operations
            timeframeRef.current = timeframe;
            dataLoadedRef.current = false;
            
            // Clear existing data from the series for the new timeframe
            if (candlestickSeriesRef.current) {
                try {
                    // Use empty array of the correct format to avoid type errors
                    console.log("Clearing chart data for timeframe change");
                    
                    // Important: Set data to empty array to fully clear existing data
                    candlestickSeriesRef.current.setData([]);
                    
                    // Force the chart to redraw and clear any cached data
                    if (chartRef.current) {
                        chartRef.current.timeScale().fitContent();
                        const container = chartContainerRef.current;
                        const rect = container ? container.getBoundingClientRect() : { width: 600 };
                        const containerWidth = Math.max(rect.width, 300);
                        
                        chartRef.current.applyOptions({
                            timeScale: {
                                rightOffset: containerWidth > 768 ? 12 : 8,
                                barSpacing: containerWidth > 768 ? 6 : 4,
                                fixLeftEdge: true,
                                lockVisibleTimeRangeOnResize: true,
                                rightBarStaysOnScroll: true,
                                borderVisible: true,
                                borderColor: 'rgba(197, 203, 206, 0.6)',
                                visible: true,
                                timeVisible: true,
                                secondsVisible: containerWidth > 600 && (timeframe === '1m' || timeframe === '5m')
                            }
                        });
                    }
                    
                    console.log("Cleared chart series data for timeframe change");
                } catch (err) {
                    console.error("Failed to clear chart series data:", err);
                }
            }
            
            // Set loading state to show the user something is happening
            setIsLoading(true);
            
            // Force disconnection with the new timeframe to ensure clean state
            if (socketRef.current) {
                logWebSocketDebug(`Closing current socket to change timeframe to ${timeframe}`);
                socketRef.current.close();
                socketRef.current = null; // Ensure we create a new socket instance
            }
            
            // Reset fetching flag to ensure we can fetch
            isFetchingData = false;
            
            // Wait briefly for cleanup to complete
            setTimeout(() => {
                // Fetch new historical data for the new timeframe
                fetchHistoricalData(timeframe)
                    .then(() => {
                        setIsLoading(false);
                        
                        // Force a reconnection with the new timeframe
                        if (initSocketRef.current) {
                            initSocketRef.current();
                            
                            // Ensure timeframe is set after reconnection
                            setTimeout(() => {
                                if (socketRef.current && socketRef.current.connected) {
                                    socketRef.current.emit('set_timeframe', { timeframe });
                                    logWebSocketDebug(`Explicitly set timeframe to ${timeframe} after reconnection`);
                                }
                            }, 500);
                        }
                    })
                    .catch(err => {
                        console.error(`Error fetching data for new timeframe ${timeframe}:`, err);
                        setIsLoading(false);
                        setError(`Failed to load ${timeframe} data: ${err.message}`);
                        
                        // Try using dummy data as fallback
                        try {
                            const dummyData = createDummyData();
                            if (candlestickSeriesRef.current && dummyData.length > 0) {
                                candlestickSeriesRef.current.setData(dummyData);
                                chartRef.current.timeScale().fitContent();
                                console.log(`Using dummy data for timeframe ${timeframe} due to fetch error`);
                            }
                        } catch (dummyErr) {
                            console.error("Failed to create dummy data:", dummyErr);
                        }
                    });
            }, 100); // Short delay to ensure clean state
        } else {
            // console.log(`Timeframe ${timeframe} unchanged, skipping full historical fetch.`);
        }
    }, [timeframe, fetchHistoricalData, isLoading, createDummyData]);

    // Monitor for no updates and trigger reconnection if needed
    useEffect(() => {
        // Track last heartbeat from server (moved outside of callback)
        const lastHeartbeatRef = { current: new Date() };
        
        const checkConnectionHealth = () => {
            const now = new Date();
            const lastUpdate = lastUpdateRef.current ? new Date(lastUpdateRef.current) : null;
            
            // Update heartbeat when we receive data or are connected
            if (isConnected) {
                lastHeartbeatRef.current = now;
            }
            
            if (isConnected) {
                // For data updates - looking for stale data
                if (lastUpdate) {
                    const timeSinceLastUpdate = now - lastUpdate;
                    
                    // More tolerant threshold - 30 seconds if connected
                    if (timeSinceLastUpdate > 30000) {
                        logWebSocketDebug(`No data updates for ${Math.floor(timeSinceLastUpdate/1000)}s. Sending ping to check connection...`);
                        
                        // Instead of immediate reconnect, try a ping first
                        if (socketRef.current && socketRef.current.connected) {
                            socketRef.current.emit('ping_server', { timestamp: now.getTime() }, (response) => {
                                // If we get response, update heartbeat
                                lastHeartbeatRef.current = new Date();
                                logWebSocketDebug('Server responded to ping - connection is alive');
                            });
                            
                            // Set timeout to check if ping was successful
                            setTimeout(() => {
                                const timeSincePing = new Date() - now;
                                // If no heartbeat update in 5s after ping, reconnect
                                if (timeSincePing > 5000 && now - lastHeartbeatRef.current >= 5000) {
                                    logWebSocketDebug('No response to ping, connection appears dead. Reconnecting...');
                                    if (socketRef.current) {
                                        socketRef.current.disconnect();
                                        // Short delay before reconnect attempt
                                        setTimeout(() => {
                                            if (initSocketRef.current) {
                                                initSocketRef.current();
                                            }
                                        }, 500);
                                    }
                                }
                            }, 5000);
                        }
                    }
                }
            } else {
                // Not connected, check if we should try to reconnect
                const timeSinceHeartbeat = now - lastHeartbeatRef.current;
                if (timeSinceHeartbeat > 10000 && !socketRef.current?.connected) {
                    // If we've been disconnected for 10 seconds, trigger reconnect
                    logWebSocketDebug(`Disconnected for ${Math.floor(timeSinceHeartbeat/1000)}s. Attempting reconnect...`);
                    if (initSocketRef.current) {
                        initSocketRef.current();
                    }
                }
            }
        };
        
        // Set up more frequent health checks (every 5 seconds)
        const connectionCheckInterval = setInterval(checkConnectionHealth, 5000);
        
        return () => {
            clearInterval(connectionCheckInterval);
        };
    }, [isConnected]);

    // Handle fullscreen toggle with proper event handling
    const toggleFullscreen = () => {
        const chartContainer = chartContainerRef.current;
        if (!chartContainer) return;

        if (!document.fullscreenElement) {
            // Enter fullscreen
            if (chartContainer.requestFullscreen) {
                chartContainer.requestFullscreen();
            } else if (chartContainer.mozRequestFullScreen) {
                chartContainer.mozRequestFullScreen();
            } else if (chartContainer.webkitRequestFullscreen) {
                chartContainer.webkitRequestFullscreen();
            } else if (chartContainer.msRequestFullscreen) {
                chartContainer.msRequestFullscreen();
            }
        } else {
            // Exit fullscreen
            if (document.exitFullscreen) {
                document.exitFullscreen();
            } else if (document.mozCancelFullScreen) {
                document.mozCancelFullScreen();
            } else if (document.webkitExitFullscreen) {
                document.webkitExitFullscreen();
            } else if (document.msExitFullscreen) {
                document.msExitFullscreen();
            }
        }
    };

    // Listen for fullscreen changes to update state and resize chart
    useEffect(() => {
        const handleFullscreenChange = () => {
            const isCurrentlyFullscreen = !!(
                document.fullscreenElement ||
                document.mozFullScreenElement ||
                document.webkitFullscreenElement ||
                document.msFullscreenElement
            );
            
            setIsFullscreen(isCurrentlyFullscreen);
            
            // Resize chart after fullscreen state change
            setTimeout(() => {
                if (chartRef.current) {
                    const container = chartContainerRef.current;
                    if (container) {
                        const rect = container.getBoundingClientRect();
                        chartRef.current.applyOptions({
                            width: rect.width,
                            height: rect.height,
                        });
                        chartRef.current.timeScale().fitContent();
                    }
                }
            }, 100);
        };

        // Add fullscreen event listeners
        document.addEventListener('fullscreenchange', handleFullscreenChange);
        document.addEventListener('mozfullscreenchange', handleFullscreenChange);
        document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
        document.addEventListener('msfullscreenchange', handleFullscreenChange);

        return () => {
            document.removeEventListener('fullscreenchange', handleFullscreenChange);
            document.removeEventListener('mozfullscreenchange', handleFullscreenChange);
            document.removeEventListener('webkitfullscreenchange', handleFullscreenChange);
            document.removeEventListener('msfullscreenchange', handleFullscreenChange);
        };
    }, []);

    // Enhanced resize handling for better responsiveness
    useEffect(() => {
        const handleResize = () => {
            const container = chartContainerRef.current;
            if (container && chartRef.current) {
                // Get container dimensions
                const rect = container.getBoundingClientRect();
                
                // Ensure minimum dimensions
                const width = Math.max(rect.width, 300);
                const height = Math.max(rect.height, 200);
                
                chartRef.current.applyOptions({
                    width: width,
                    height: height,
                    timeScale: {
                        timeVisible: true,
                        secondsVisible: width > 600, // Show seconds only on larger screens
                        rightOffset: width > 768 ? 12 : 8,
                        barSpacing: width > 768 ? 6 : 4,
                        borderVisible: true,
                        visible: true,
                        fixLeftEdge: false,
                        fixRightEdge: false,
                        lockVisibleTimeRangeOnResize: true,
                        rightBarStaysOnScroll: true,
                        borderColor: 'rgba(197, 203, 206, 0.6)',
                    }
                });
                
                // Fit content after resize
                setTimeout(() => {
                    if (chartRef.current) {
                        chartRef.current.timeScale().fitContent();
                    }
                }, 50);
            }
        };

        // Create ResizeObserver for better responsiveness
        let resizeObserver;
        if (window.ResizeObserver && chartContainerRef.current) {
            resizeObserver = new ResizeObserver(() => {
                handleResize();
            });
            resizeObserver.observe(chartContainerRef.current);
        }

        // Fallback window resize listener
        window.addEventListener('resize', handleResize);
        
        // Initial resize
        handleResize();

        return () => {
            window.removeEventListener('resize', handleResize);
            if (resizeObserver) {
                resizeObserver.disconnect();
            }
        };
    }, []); // Empty dependency array since this should only run once on mount

    // Handler for timeframe dropdown change
    const handleTimeframeChange = (event) => { 
        const newTimeframe = event.target.value;
        console.log(`Timeframe changing from ${timeframe} to ${newTimeframe}`);
        
        // Just update the state, the useEffect will handle the rest
        setTimeframe(newTimeframe);
        
        // Log user-initiated timeframe change
        logWebSocketDebug(`User changed timeframe from ${timeframe} to ${newTimeframe}`);
    };

    // UI rendering
    return (
        <div className="chart-section">
            <div className="controls">
                <label htmlFor="timeframe">Select Timeframe:</label>
                <select 
                    id="timeframe" 
                    value={timeframe} 
                    onChange={handleTimeframeChange} 
                    disabled={isLoading}
                >
                    <option value="1m">1 Minute</option>
                    <option value="5m">5 Minutes</option>
                    <option value="1h">1 Hour</option>
                    <option value="4h">4 Hours</option>
                    <option value="1d">1 Day</option>
                    <option value="1w">1 Week</option>
                </select>
                
                {/* Connection status indicator */}
                <div className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
                    <div className="status-icon"></div>
                    {isConnected ? (
                        <span>Real-time Connected {lastUpdateTime && `(Last: ${lastUpdateTime.split(':')[0]}:${lastUpdateTime.split(':')[1]})`}</span>
                    ) : (
                        <span>{isLoading ? "Connecting..." : "Disconnected"}</span>
                    )}
                </div>
            </div>
            
            <div ref={chartContainerRef} className="chart-container">
                <button 
                    className="fullscreen-toggle" 
                    onClick={toggleFullscreen}
                    title={isFullscreen ? "Exit Fullscreen" : "Enter Fullscreen"}
                >
                    {isFullscreen ? (
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"></path>
                        </svg>
                    ) : (
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"></path>
                        </svg>
                    )}
                </button>
            </div>
            
            {!isLoading && error && !chartRef.current && (
                <div className="chart-placeholder-error">
                    Could not load chart. {error}
                </div>
            )}
        </div>
    );
}

export default CandlestickChart;