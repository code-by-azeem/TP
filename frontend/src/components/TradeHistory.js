import React, { useEffect, useState } from 'react';
import axios from 'axios';
import './TradeHistory.css';

const TradeHistory = () => {
    const [trades, setTrades] = useState([]);

    useEffect(() => {
        axios.get('http://localhost:5000/trade-history', { withCredentials: true })
            .then(res => setTrades(res.data))
            .catch(() => setTrades([]));
    }, []);

    return (
        <div className="trade-history-container">
            <h2>Trade History</h2>
            <div className="trade-list">
                <table>
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Symbol</th>
                            <th>Type</th>
                            <th>Volume</th>
                            <th>Price</th>
                            <th>Profit</th>
                        </tr>
                    </thead>
                    <tbody>
                        {trades.map((trade, idx) => (
                            <tr key={idx}>
                                <td>{trade.time}</td>
                                <td>{trade.symbol}</td>
                                <td>{trade.type}</td>
                                <td>{trade.volume}</td>
                                <td>{trade.price}</td>
                                <td>{trade.profit}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default TradeHistory; 