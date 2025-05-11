import React from 'react';
import AccountInfo from './AccountInfo';
import TradeHistory from './TradeHistory';
import CandlestickChart from './CandlestickChart';

const Dashboard = () => (
  <div>
    <h1>Dashboard</h1>
    <AccountInfo />
    <CandlestickChart />
    <TradeHistory />
  </div>
);

export default Dashboard;