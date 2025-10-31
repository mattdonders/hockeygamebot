#!/bin/bash

# Start the dashboard web server
# Run this from your hockeygamebot project directory

PORT=8000

# Start server in background, suppress logs
python3 -m http.server $PORT --bind 0.0.0.0 > /dev/null 2>&1 &

# Capture the process ID
SERVER_PID=$!

# Function to get local IP address (tries multiple methods)
get_local_ip() {
    # Method 1: Try ipconfig for Mac (try multiple interfaces)
    for interface in en0 en1 en2 en3; do
        IP=$(ipconfig getifaddr $interface 2>/dev/null)
        if [ ! -z "$IP" ]; then
            echo $IP
            return
        fi
    done
    
    # Method 2: Try ip command for Linux
    IP=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K\S+')
    if [ ! -z "$IP" ]; then
        echo $IP
        return
    fi
    
    # Method 3: Try hostname -I (Linux)
    IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    if [ ! -z "$IP" ]; then
        echo $IP
        return
    fi
    
    # Method 4: Try ifconfig (older systems)
    IP=$(ifconfig 2>/dev/null | grep "inet " | grep -v 127.0.0.1 | head -1 | awk '{print $2}' | sed 's/addr://')
    if [ ! -z "$IP" ]; then
        echo $IP
        return
    fi
    
    # If all methods fail, return empty
    echo ""
}

# Get local IP address
LOCAL_IP=$(get_local_ip)

# Write port info to file for easy reference
echo "$PORT" > .dashboard_port
echo "$LOCAL_IP" >> .dashboard_port

# Print success message
echo "✅ Dashboard server started!"
echo ""
echo "📊 Access dashboard:"
echo "   Local:   http://localhost:$PORT/dashboard.html"

if [ -z "$LOCAL_IP" ]; then
    echo "   Network: (unable to detect IP - check .dashboard_port file)"
else
    echo "   Network: http://$LOCAL_IP:$PORT/dashboard.html"
fi

echo ""
echo "🔧 Process ID: $SERVER_PID"
echo "📁 Port file: .dashboard_port"
echo ""
echo "To stop: kill $SERVER_PID"
echo "To find port: cat .dashboard_port"
