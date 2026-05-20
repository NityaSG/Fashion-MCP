#!/bin/bash
# Quick setup for Fashion Trends MCP Apps bridge

echo "Fashion Trends MCP - ChatGPT UI Setup"
echo "===================================="
echo ""

if ! command -v node >/dev/null 2>&1; then
    echo "Node.js is not installed. Please install Node.js 18+ first."
    exit 1
fi

echo "Node.js version: $(node --version)"
echo ""

cd "$(dirname "$0")"

echo "Installing dependencies..."
npm install

if [ $? -ne 0 ]; then
    echo "npm install failed"
    exit 1
fi

echo ""
echo "Setup complete."
echo ""
echo "Next steps:"
echo "1. Start the Python MCP in HTTP mode:"
echo "   MCP_TRANSPORT=http python ../fashion_trends_mcp_server.py"
echo "2. Start the ChatGPT UI bridge: npm start"
echo "3. Open http://localhost:8787/preview to inspect the widget locally"
echo "4. Add the public /mcp URL to ChatGPT once both servers are reachable"
echo ""
echo "See README.md for detailed instructions."
