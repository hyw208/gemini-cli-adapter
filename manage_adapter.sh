#!/bin/bash

# Configuration
PID_FILE=".adapter.pid"
LOG_FILE="adapter.log"
START_SCRIPT="start.py"
PORT=5001

# Find python3
if [ -z "$PYTHON_CMD" ]; then
    PIPX_PYTHON="$HOME/.local/pipx/venvs/flask/bin/python"
    if [ -f "$PIPX_PYTHON" ]; then
        PYTHON_CMD="$PIPX_PYTHON -u"
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON_CMD="python3 -u"
    elif command -v python >/dev/null 2>&1; then
        PYTHON_CMD="python -u"
    else
        echo "❌ Error: python3 or python not found in PATH."
        exit 1
    fi
fi

# Ensure we're in the script's directory
cd "$(dirname "$0")"

function start() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "✅ Adapter is already running (PID: $PID)"
            return
        else
            echo "⚠️  PID file exists but process is dead. Cleaning up."
            rm "$PID_FILE"
        fi
    fi

    echo "🚀 Starting Adapter..."
    # Run start.py in background, redirect output to log file
    # We use nohup to keep it running if the shell closes
    nohup $PYTHON_CMD $START_SCRIPT > "$LOG_FILE" 2>&1 &
    
    PID=$!
    echo "$PID" > "$PID_FILE"
    
    # Wait a moment for it to start
    sleep 2
    
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "✅ Adapter started (PID: $PID)"
        echo "📄 Logs are being written to $LOG_FILE"
    else
        echo "❌ Failed to start adapter. Check $LOG_FILE for details."
        rm "$PID_FILE"
        exit 1
    fi
}

function stop() {
    # 1. Try stopping via PID file
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "🛑 Stopping Adapter (PID: $PID)..."
            # Kill the process group to ensure children (like Flask reloader) are also killed
            kill -TERM -"$PID" 2>/dev/null || kill -TERM "$PID"
            
            # Wait for it to die
            for i in {1..5}; do
                if ! ps -p "$PID" > /dev/null 2>&1; then
                    echo "✅ Adapter stopped"
                    rm "$PID_FILE"
                    break
                fi
                sleep 1
            done
            
            if [ -f "$PID_FILE" ]; then
                echo "⚠️  Process didn't stop, force killing..."
                kill -9 -"$PID" 2>/dev/null || kill -9 "$PID"
                sleep 1
                rm "$PID_FILE"
                echo "✅ Adapter force stopped"
            fi
        else
            echo "⚠️  Process $PID not found, cleaning up PID file"
            rm "$PID_FILE"
        fi
    fi

    # 2. Safety check: ensure nothing is listening on the port
    PORT_PID=$(lsof -t -i :$PORT)
    if [ -n "$PORT_PID" ]; then
        echo "⚠️  Found orphaned processes on port $PORT (PIDs: $PORT_PID). Cleaning up..."
        for p in $PORT_PID; do
            kill -9 "$p" 2>/dev/null
        done
        echo "✅ Port $PORT cleared"
    fi
}

function status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "✅ Adapter is RUNNING (PID: $PID)"
            return 0
        else
            echo "❌ Adapter is STOPPED (PID file exists but process is dead)"
            return 1
        fi
    else
        echo "❌ Adapter is STOPPED"
        return 1
    fi
}

function health() {
    echo "🔍 Checking health on port $PORT..."
    if command -v curl >/dev/null 2>&1; then
        RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT/v1beta/models)
        if [ "$RESPONSE" == "200" ]; then
            echo "✅ Adapter is healthy (HTTP 200)"
        else
            echo "❌ Adapter returned HTTP $RESPONSE"
            return 1
        fi
    else
        echo "⚠️  curl not found, skipping HTTP health check."
        status
    fi
}

function logs() {
    echo "📄 Tailing logs (Ctrl+C to exit)..."
    tail -f "$LOG_FILE"
}

case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        stop
        sleep 1
        start
        ;;
    status)
        status
        ;;
    health)
        health
        ;;
    logs)
        logs
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|health|logs}"
        exit 1
        ;;
esac
