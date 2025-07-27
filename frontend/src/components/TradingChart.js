import React, { useEffect, useRef, useState } from 'react';
import { createChart } from 'lightweight-charts';
import io from 'socket.io-client';
import './TradingChart.css';

const TradingChart = () => {
    const chartContainerRef = useRef();
    const chartRef = useRef();
    const candlestickSeriesRef = useRef();
    const socketRef = useRef();
    const lastUpdateRef = useRef(Date.now());
    
    const [isConnected, setIsConnected] = useState(false);
    const [lastUpdateTime, setLastUpdateTime] = useState(null);

    // Throttle function for updates
    const shouldUpdate = (minInterval = 250) => {
        const now = Date.now();
        if (now - lastUpdateRef.current >= minInterval) {
            lastUpdateRef.current = now;
            return true;
        }
        return false;
    };

    useEffect(() => {
        // Initialize chart
        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { color: '#1e222d' },
                textColor: '#d1d4dc',
            },
            grid: {
                vertLines: { color: '#2a2e39' },
                horzLines: { color: '#2a2e39' },
            },
            width: chartContainerRef.current.clientWidth,
            height: 500,
            timeScale: {
                timeVisible: true,
                secondsVisible: false,
            },
        });

        const candlestickSeries = chart.addCandlestickSeries({
            upColor: '#26a69a',
            downColor: '#ef5350',
            borderVisible: false,
            wickUpColor: '#26a69a',
            wickDownColor: '#ef5350',
        });

        chartRef.current = chart;
        candlestickSeriesRef.current = candlestickSeries;

        // Connect to WebSocket with optimized settings
        socketRef.current = io('http://localhost:5000', {
            transports: ['websocket', 'polling'],
            timeout: 5000,
        });

        // Connection status tracking
        socketRef.current.on('connect', () => {
            console.log('TradingChart: Connected to WebSocket');
            setIsConnected(true);
            
            // Request optimized updates
            socketRef.current.emit('set_update_frequency', {
                frequency: 'balanced',
                max_delay: 250
            });
        });

        socketRef.current.on('disconnect', () => {
            console.log('TradingChart: Disconnected from WebSocket');
            setIsConnected(false);
        });

        // Handle real-time updates with throttling
        socketRef.current.on('price_update', (data) => {
            // Throttle updates to prevent overwhelming the chart
            if (!shouldUpdate(250)) {
                return;
            }

            if (data && candlestickSeriesRef.current) {
                try {
                    candlestickSeriesRef.current.update(data);
                    setLastUpdateTime(new Date().toLocaleTimeString());
                } catch (error) {
                    console.error('Error updating chart:', error);
                }
            }
        });

        // Handle trade execution events (no throttling - important events)
        socketRef.current.on('trade_executed', (data) => {
            console.log('TradingChart: Trade executed', data);
            
            if (data && data.price && candlestickSeriesRef.current) {
                try {
                    // Create immediate price tick for trade execution
                    const tradeTick = {
                        time: Math.floor(Date.now() / 1000),
                        open: data.price,
                        high: data.price,
                        low: data.price,
                        close: data.price
                    };
                    candlestickSeriesRef.current.update(tradeTick);
                    setLastUpdateTime(new Date().toLocaleTimeString());
                } catch (error) {
                    console.error('Error showing trade execution:', error);
                }
            }
        });

        // Handle historical data
        const fetchHistoricalData = async () => {
            try {
                const response = await fetch('http://localhost:5000/data?timeframe=1m');
                if (response.ok) {
                    const data = await response.json();
                    if (data && Array.isArray(data) && candlestickSeriesRef.current) {
                        candlestickSeriesRef.current.setData(data);
                        console.log('TradingChart: Historical data loaded');
                    }
                }
            } catch (error) {
                console.error('Error fetching historical data:', error);
            }
        };

        fetchHistoricalData();

        // Cleanup function
        return () => {
            if (socketRef.current) {
                socketRef.current.disconnect();
            }
            if (chartRef.current) {
                chartRef.current.remove();
            }
        };
    }, []);

    // Handle resize
    useEffect(() => {
        const handleResize = () => {
            if (chartRef.current && chartContainerRef.current) {
                chartRef.current.applyOptions({
                    width: chartContainerRef.current.clientWidth,
                });
            }
        };

        window.addEventListener('resize', handleResize);
        return () => window.removeEventListener('resize', handleResize);
    }, []);

    return (
        <div className="trading-chart">
            <div className="chart-header">
                <h3>ETHUSD Chart</h3>
                <div className="chart-status">
                    <span className={`status-indicator ${isConnected ? 'connected' : 'disconnected'}`}>
                        {isConnected ? '🟢 Live' : '🔴 Offline'}
                    </span>
                    {lastUpdateTime && (
                        <span className="last-update">
                            Updated: {lastUpdateTime}
                        </span>
                    )}
                </div>
            </div>
            <div ref={chartContainerRef} className="chart-container" />
        </div>
    );
};

export default TradingChart; 