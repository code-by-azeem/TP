import React, { useEffect, useState } from 'react';
import axios from 'axios';
import './AccountInfo.css';

const AccountInfo = () => {
    const [info, setInfo] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        // Using ID 1 for demo purposes - you would likely get this from context/auth state
        const userId = 1;
        setLoading(true);
        
        axios.get(`http://localhost:5000/account/${userId}`, { withCredentials: true })
            .then(res => {
                setInfo(res.data);
                setError(null);
            })
            .catch(err => {
                console.error("Account info fetch error:", err);
                setError("Failed to load account information");
                setInfo(null);
            })
            .finally(() => {
                setLoading(false);
            });
    }, []);

    if (loading) return <div className="account-info-container">Loading account info...</div>;
    if (error) return <div className="account-info-container">Error: {error}</div>;
    if (!info) return <div className="account-info-container">No account information available</div>;

    return (
        <div className="account-info-container">
            <h2>Account Information</h2>
            <div className="account-grid">
                <div className="info-item">
                    <span className="label">Balance:</span>
                    <span className="value">${info.balance.toFixed(2)}</span>
                </div>
                <div className="info-item">
                    <span className="label">Equity:</span>
                    <span className="value">${info.equity.toFixed(2)}</span>
                </div>
                <div className="info-item">
                    <span className="label">Margin:</span>
                    <span className="value">${info.margin.toFixed(2)}</span>
                </div>
                <div className="info-item">
                    <span className="label">Free Margin:</span>
                    <span className="value">${info.freeMargin.toFixed(2)}</span>
                </div>
                <div className="info-item">
                    <span className="label">Margin Level:</span>
                    <span className="value">{info.marginLevel.toFixed(2)}%</span>
                </div>
                <div className="info-item">
                    <span className="label">Current Profit:</span>
                    <span className={`value ${info.profit >= 0 ? 'profit' : 'loss'}`}>
                        ${info.profit.toFixed(2)}
                    </span>
                </div>
            </div>
        </div>
    );
};

export default AccountInfo; 