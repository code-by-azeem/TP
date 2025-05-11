import React, { useEffect, useRef } from 'react';
import { createChart } from 'lightweight-charts';
import io from 'socket.io-client';
import './TradingChart.css';

const TradingChart = () => {
    const chartContainerRef = useRef();
    const chartRef = useRef();
    const candlestickSeriesRef = useRef();
    const socketRef = useRef();

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

        // Connect to WebSocket
        socketRef.current = io('http://localhost:5000');

        // Handle real-time updates
        socketRef.current.on('price_update', (data) => {
            candlestickSeries.update(data);
        });

        // Handle historical data
        const fetchHistoricalData = async () => {
            try {
                const response = await fetch('http://localhost:5000/data?timeframe=1m');
                const data = await response.json();
                candlestickSeries.setData(data);
            } catch (error) {
                console.error('Error fetching historical data:', error);
            }
        };

        fetchHistoricalData();

        // Handle window resize
        const handleResize = () => {
            chart.applyOptions({
                width: chartContainerRef.current.clientWidth,
            });
        };

        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            socketRef.current.disconnect();
            chart.remove();
        };
    }, []);

    return (
        <div className="trading-chart-container">
            <div className="chart-header">
                <h2>XAUUSD</h2>
                <div className="timeframe-selector">
                    <button className="active">1m</button>
                    <button>5m</button>
                    <button>15m</button>
                    <button>1h</button>
                    <button>4h</button>
                    <button>1d</button>
                </div>
            </div>
            <div ref={chartContainerRef} className="chart-container" />
        </div>
    );
};

export default TradingChart; 