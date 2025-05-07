// frontend/src/App.js
import React from 'react';
import CandlestickChart from './components/CandlestickChart'; // We'll create this next
import './App.css'; // We'll create this too

function App() {
    return (
        <div className="App">
            <header className="App-header">
                <h1>Real-Time Candlestick Chart (React + Flask)</h1>
            </header>
            <main>
                <CandlestickChart />
            </main>
        </div>
    );
}

export default App;