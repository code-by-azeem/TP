@echo off
echo.
echo 🚀 Starting TradePulse Frontend...
echo ====================================
echo.

cd frontend

echo 📦 Checking dependencies...
if not exist "node_modules" (
    echo Installing dependencies...
    npm install
)

echo.
echo 🌐 Starting React development server...
echo 📊 Opening dashboard at: http://localhost:3000
echo 🛑 Press Ctrl+C to stop
echo ====================================
echo.

npm start

pause 