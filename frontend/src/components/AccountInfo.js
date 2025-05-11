import React, { useEffect, useState } from 'react';
import axios from 'axios';
import './AccountInfo.css';

const AccountInfo = () => {
    const [info, setInfo] = useState(null);

    useEffect(() => {
        axios.get('http://localhost:5000/account', { withCredentials: true })
            .then(res => setInfo(res.data))
            .catch(() => setInfo(null));
    }, []);

    if (!info) return <div>Loading account info...</div>;

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