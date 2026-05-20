@echo off
REM Quick setup for Fashion Trends MCP Apps bridge

echo Fashion Trends MCP - ChatGPT UI Setup
echo ====================================
echo.

node --version >nul 2>&1
if errorlevel 1 (
    echo Node.js is not installed. Please install Node.js 18+ first.
    exit /b 1
)

echo Node.js version:
node --version
echo.

cd /d "%~dp0"

echo Installing dependencies...
call npm install

if errorlevel 1 (
    echo npm install failed
    exit /b 1
)

echo.
echo Setup complete.
echo.
echo Next steps:
echo 1. Start the Python MCP in HTTP mode:
echo    set MCP_TRANSPORT=http ^&^& python ..\fashion_trends_mcp_server.py
echo 2. Start the ChatGPT UI bridge: npm start
echo 3. Open http://localhost:8787/preview to inspect the widget locally
echo 4. Add the public /mcp URL to ChatGPT once both servers are reachable
echo.
echo See README.md for detailed instructions.
echo.
pause
