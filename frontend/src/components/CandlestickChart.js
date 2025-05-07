// frontend/src/components/CandlestickChart.js
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { createChart, CrosshairMode, CandlestickSeries } from 'lightweight-charts';
import { io } from 'socket.io-client';
import './CandlestickChart.css';

const FLASK_SERVER_URL = 'http://127.0.0.1:5000';

function CandlestickChart() {
    const chartContainerRef = useRef(null);
    const chartRef = useRef(null);
    const candlestickSeriesRef = useRef(null);
    const socketRef = useRef(null);

    const [timeframe, setTimeframe] = useState('1m');
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState(null);
    const [isConnected, setIsConnected] = useState(false);

    // Fetch historical data (remains the same)
    const fetchHistoricalData = useCallback(async (selectedTimeframe) => {
        setIsLoading(true);
        setError(null);
        console.log(`Fetching historical: ${selectedTimeframe}...`);
        try {
            const apiUrl = `${FLASK_SERVER_URL}/data?timeframe=${selectedTimeframe}`;
            const response = await fetch(apiUrl);
            if (!response.ok) {
                let errorMsg = `HTTP ${response.status}`;
                try { errorMsg = (await response.json()).error || errorMsg; } catch(e){}
                throw new Error(errorMsg);
            }
            const data = await response.json();
            console.log(`Received ${data.length} historical points.`);
            const formattedData = data
                .map(item => ({ time: Number(item.time), open: Number(item.open), high: Number(item.high), low: Number(item.low), close: Number(item.close) }))
                .sort((a, b) => a.time - b.time);

            if (candlestickSeriesRef.current) {
                candlestickSeriesRef.current.setData(formattedData);
                console.log("Historical data set.");
            } else { console.warn("Series ref not available for hist data."); }
        } catch (err) { setError(`Hist. fetch failed: ${err.message}`); console.error(err); }
        finally { setIsLoading(false); }
    }, []);

    // Effect for chart initialization
    useEffect(() => {
        if (!chartContainerRef.current || chartRef.current) return;
        console.log("Initializing chart instance...");
        try {
            // --- CORRECTED Chart Options Structure ---
            const chartOptions = {
                 width: chartContainerRef.current.clientWidth > 0 ? chartContainerRef.current.clientWidth : 600,
                 height: 600,
                 layout: {
                    background: { type: 'solid', color: '#000000' }, // Black Background
                    textColor: 'rgba(255, 255, 255, 0.9)',
                    // --- CHANGE: attributionLogo is NESTED inside layout ---
                    attributionLogo: false,
                    // --- End of Change ---
                 },
                 grid: {
                    vertLines: { color: 'rgba(197, 203, 206, 0.1)' },
                    horzLines: { color: 'rgba(197, 203, 206, 0.1)' }
                 },
                 crosshair: { mode: CrosshairMode.Normal },
                 rightPriceScale: { borderColor: 'rgba(197, 203, 206, 0.6)' },
                 timeScale: { borderColor: 'rgba(197, 203, 206, 0.6)', timeVisible: true, secondsVisible: timeframe === '1m' },
                 // Watermark option removed as attributionLogo is the correct one
             };
             // --- End Chart Options ---

            const chart = createChart(chartContainerRef.current, chartOptions);
            chartRef.current = chart;

            const seriesOptions = {
                 upColor: '#26a69a', downColor: '#ef5350', borderDownColor: '#ef5350', borderUpColor: '#26a69a', wickDownColor: '#ef5350', wickUpColor: '#26a69a',
             };
            const series = chart.addSeries(CandlestickSeries, seriesOptions);
            candlestickSeriesRef.current = series;

            console.log("Chart and series initialized.");
            fetchHistoricalData(timeframe); // Fetch initial data

        } catch (err) { setError(`Chart Init Failed: ${err.message}`); setIsLoading(false); console.error(err); }

        // Setup resize listener
        const handleResize = () => { /* ... resize logic ... */ };
        window.addEventListener('resize', handleResize); handleResize();

        // Cleanup function for chart
        return () => { /* ... chart cleanup ... */ };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []); // Runs once

    // Effect for WebSocket connection management (remains the same)
    useEffect(() => {
        if (!candlestickSeriesRef.current || socketRef.current) { return; }
        console.log("WebSocket: Attempting connection...");
        setError(null);
        const socket = io(FLASK_SERVER_URL, { transports: ['websocket'] });
        socketRef.current = socket;
        const handleConnect = () => { console.log(`WS: CONNECTED! ID: ${socket.id}`); setIsConnected(true); setError(null); };
        const handleDisconnect = (reason) => { console.warn(`WS: DISCONNECTED. Reason: ${reason}`); setIsConnected(false); };
        const handleConnectError = (err) => { console.error('WS: Conn Error!', err); setIsConnected(false); setError(`WS Err: ${err.message}`); };
        const handlePriceUpdate = (newCandleData) => { if (candlestickSeriesRef.current) candlestickSeriesRef.current.update(newCandleData); };
        socket.on('connect', handleConnect); socket.on('disconnect', handleDisconnect); socket.on('connect_error', handleConnectError); socket.on('price_update', handlePriceUpdate);
        return () => { console.log("WS Cleanup: Disconnecting socket..."); socket.off('connect', handleConnect); socket.off('disconnect', handleDisconnect); socket.off('connect_error', handleConnectError); socket.off('price_update', handlePriceUpdate); socket.disconnect(); socketRef.current = null; setIsConnected(false); };
    }, []); // Corrected dependency

    // Effect for handling timeframe changes (remains the same)
    useEffect(() => {
        if (!candlestickSeriesRef.current || isLoading) return;
        console.log(`Timeframe changed: ${timeframe}. Fetching hist...`);
        chartRef.current?.timeScale().applyOptions({ secondsVisible: timeframe === '1m' });
        fetchHistoricalData(timeframe);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [timeframe]);

    // Handler for dropdown change (remains the same)
    const handleTimeframeChange = (event) => { setTimeframe(event.target.value); };

    // Render the UI (remains the same)
    return (
        <div className="chart-section">
            {/* Controls */}
            <div className="controls">
                {/* ... select, status indicator, loading, error spans ... */}
                 <label htmlFor="timeframe">Select Timeframe:</label>
                 <select id="timeframe" value={timeframe} onChange={handleTimeframeChange} disabled={isLoading}>
                      <option value="1m">1 Minute</option>
                      <option value="5m">5 Minutes</option>
                      <option value="1h">1 Hour</option>
                      <option value="4h">4 Hours</option>
                      <option value="1d">1 Day</option>
                      <option value="1w">1 Week</option>
                 </select>
                 <span className={`status-indicator ${isConnected ? 'connected' : 'disconnected'}`}>
                     {isConnected ? '● Real-time Connected' : '○ Real-time Disconnected'}
                 </span>
                 {isLoading && <span className="status-loading">Loading...</span>}
                 {error && <span className="status-error" title={error}>Error!</span>}
            </div>
            {/* Chart Container */}
            <div ref={chartContainerRef} className="chart-container" />
            {/* Error Placeholder */}
             {!isLoading && error && !chartRef.current && ( <div className="chart-placeholder-error"> Could not load chart. {error} </div> )}
        </div>
    );
}

export default CandlestickChart;