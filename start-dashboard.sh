#!/bin/bash

# Start the dashboard web server
# Run this from your hockeygamebot project directory

PORT=8000

# Start server in background, suppress logs
python3 -m http.server $PORT --bind 0.0.0.0 > /dev/null 2>&1 &

# Capture the process ID
SERVER_PID=$!

# Get local IP address (works on Mac and Linux)
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}')

# Print success message
echo "✅ Dashboard server started!"
echo ""
echo "📊 Access dashboard:"
echo "   Local:   http://localhost:$PORT/dashboard.html"
echo "   Network: http://$LOCAL_IP:$PORT/dashboard.html"
echo ""
echo "🔧 Process ID: $SERVER_PID"
echo ""
echo "To stop: kill $SERVER_PID"