import React, { useEffect, useState } from 'react';
import axios from 'axios';
import './AccountInfo.css';

const AccountInfo = () => {
    const [info, setInfo] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        // Fetch account info directly from MT5 - no ID needed since MT5 handles authentication
        setLoading(true);
        
        axios.get(`http://localhost:5000/account`, { withCredentials: true })
            .then(res => {
                console.log("MT5 Account data received:", res.data); // Debug log
                setInfo(res.data);
                setError(null);
            })
            .catch(err => {
                console.error("Account info fetch error:", err);
                if (err.response?.status === 503) {
                    setError("MT5 connection not available. Please ensure MT5 is running and connected.");
                } else {
                    setError("Failed to load account information from MT5");
                }
                setInfo(null);
            })
            .finally(() => {
                setLoading(false);
            });
    }, []);

    if (loading) return <div className="account-info-container">Loading account info...</div>;
    if (error) return <div className="account-info-container">Error: {error}</div>;
    if (!info) return <div className="account-info-container">No account information available</div>;

    // Helper function to format field names for display
    const formatFieldLabel = (key) => {
        const labelMap = {
            'login': 'LOGIN ID',
            'trade_mode': 'TRADE MODE',
            'leverage': 'LEVERAGE',
            'limit_orders': 'MAX ORDERS',
            'margin_so_mode': 'MARGIN SO MODE',
            'trade_allowed': 'TRADING ALLOWED',
            'trade_expert': 'EXPERT ADVISORS',
            'margin_so_call': 'MARGIN CALL',
            'margin_so_so': 'STOP OUT',
            'currency': 'CURRENCY',
            'balance': 'BALANCE',
            'credit': 'CREDIT',
            'profit': 'PROFIT/LOSS',
            'equity': 'EQUITY',
            'margin': 'MARGIN',
            'margin_free': 'FREE MARGIN',
            'freeMargin': 'FREE MARGIN',
            'margin_level': 'MARGIN LEVEL',
            'marginLevel': 'MARGIN LEVEL',
            'margin_call': 'MARGIN CALL',
            'margin_stop_out': 'MARGIN STOP OUT',
            'margin_initial': 'INITIAL MARGIN',
            'margin_maintenance': 'MAINTENANCE MARGIN',
            'assets': 'ASSETS',
            'liabilities': 'LIABILITIES',
            'commission_blocked': 'BLOCKED COMMISSION',
            'name': 'ACCOUNT NAME',
            'server': 'SERVER',
            'company': 'COMPANY',
            'username': 'USERNAME',
            'lastUpdate': 'LAST UPDATED'
        };
        return labelMap[key] || key.replace(/_/g, ' ').toUpperCase();
    };

    // Helper function to format field values
    const formatFieldValue = (key, value) => {
        if (value === undefined || value === null || value === '') {
            return 'N/A';
        }

        // Currency/money fields
        if (['balance', 'credit', 'profit', 'equity', 'margin', 'margin_free', 'freeMargin',
             'margin_initial', 'margin_maintenance', 'assets', 'liabilities', 'commission_blocked'].includes(key)) {
            return `$${Number(value).toFixed(2)}`;
        }

        // Percentage fields
        if (['margin_level', 'marginLevel', 'margin_so_call', 'margin_so_so', 'margin_call', 'margin_stop_out'].includes(key)) {
            return `${Number(value).toFixed(1)}%`;
        }

        // Boolean fields
        if (['trade_allowed', 'trade_expert'].includes(key)) {
            return value ? 'Yes' : 'No';
        }

        // Date fields
        if (key === 'lastUpdate') {
            return new Date(value).toLocaleString();
        }

        // Default: return as string
        return String(value);
    };

    // Define field order and grouping
    const primaryFields = [
        'login', 'username', 'balance', 'equity', 'margin', 'margin_free', 'freeMargin'
    ];

    const tradingFields = [
        'leverage', 'currency', 'trade_allowed', 'trade_expert', 'limit_orders'
    ];

    const marginFields = [
        'margin_level', 'marginLevel', 'margin_so_call', 'margin_so_so', 'margin_call', 
        'margin_stop_out', 'margin_initial', 'margin_maintenance'
    ];

    const financialFields = [
        'profit', 'credit', 'assets', 'liabilities', 'commission_blocked'
    ];

    const serverFields = [
        'server', 'company', 'name'
    ];

    const otherFields = ['lastUpdate'];

    // Function to render a field group
    const renderFieldGroup = (fields, title) => {
        const fieldsToRender = fields.filter(field => info.hasOwnProperty(field) && info[field] !== undefined);
        if (fieldsToRender.length === 0) return null;

        return (
            <div className="field-group" key={title}>
                <h3 className="group-title">{title}</h3>
                <div className="group-grid">
                    {fieldsToRender.map(field => (
                        <div className="info-item" key={field}>
                            <span className="label">{formatFieldLabel(field)}:</span>
                            <span className={`value ${field === 'profit' && info[field] < 0 ? 'loss' : field === 'profit' && info[field] >= 0 ? 'profit' : ''}`}>
                                {formatFieldValue(field, info[field])}
                            </span>
                        </div>
                    ))}
                </div>
            </div>
        );
    };

    // Get any additional fields not in our predefined groups
    const allKnownFields = [...primaryFields, ...tradingFields, ...marginFields, ...financialFields, ...serverFields, ...otherFields, 'id'];
    const additionalFields = Object.keys(info).filter(key => !allKnownFields.includes(key));

    return (
        <div className="account-info-container">
            <h2>Account Details</h2>
            <div className="account-sections">
                {renderFieldGroup(primaryFields, 'Account Information')}
                {renderFieldGroup(tradingFields, 'Trading Settings')}
                {renderFieldGroup(marginFields, 'Margin Information')}
                {renderFieldGroup(financialFields, 'Financial Details')}
                {renderFieldGroup(serverFields, 'Server Information')}
                
                {/* Render any additional MT5 fields that weren't in our predefined groups */}
                {additionalFields.length > 0 && renderFieldGroup(additionalFields, 'Additional MT5 Fields')}
                
                {renderFieldGroup(otherFields, 'System Information')}
            </div>
        </div>
    );
};

export default AccountInfo; 