#!/bin/bash
# StatsBot Log Sync Daemon Management Script

DAEMON_SCRIPT="/Users/johnhamwi/Developer/StatsBot/sync_logs_daemon.py"
PID_FILE="/Users/johnhamwi/Developer/StatsBot/logsync_daemon.pid"
LOG_DIR="/Users/johnhamwi/Developer/StatsBot/logs"
TODAY=$(date '+%Y-%m-%d')
LOG_FILE="$LOG_DIR/$TODAY/logs.log"

start_daemon() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            echo "🔄 Log sync daemon is already running (PID: $PID)"
            return 1
        else
            echo "⚠️  Removing stale PID file..."
            rm -f "$PID_FILE"
        fi
    fi
    
    echo "🚀 Starting StatsBot log sync daemon..."
    nohup python3 "$DAEMON_SCRIPT" > /dev/null 2>&1 &
    DAEMON_PID=$!
    echo $DAEMON_PID > "$PID_FILE"
    echo "✅ Daemon started with PID: $DAEMON_PID"
    echo "📄 Logs: $LOG_FILE"
}

stop_daemon() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            echo "🛑 Stopping log sync daemon (PID: $PID)..."
            kill -TERM $PID
            
            # Wait for graceful shutdown
            for i in {1..10}; do
                if ! ps -p $PID > /dev/null 2>&1; then
                    echo "✅ Daemon stopped gracefully"
                    rm -f "$PID_FILE"
                    return 0
                fi
                sleep 1
            done
            
            # Force kill if needed
            echo "⚠️  Forcing daemon stop..."
            kill -KILL $PID 2>/dev/null
            rm -f "$PID_FILE"
            echo "✅ Daemon force stopped"
        else
            echo "⚠️  Daemon not running, removing stale PID file"
            rm -f "$PID_FILE"
        fi
    else
        echo "❌ Daemon is not running"
    fi
}

status_daemon() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            echo "✅ Log sync daemon is running (PID: $PID)"
            
            # Show recent log entries
            echo ""
            echo "📊 Recent activity:"
            if [ -f "$LOG_FILE" ]; then
                tail -n 5 "$LOG_FILE" 2>/dev/null || echo "No log entries found for today"
            else
                echo "No log file found for today ($TODAY)"
            fi
            
            # Show process info
            echo ""
            echo "🔍 Process info:"
            ps -p $PID -o pid,ppid,etime,pcpu,pmem,command
        else
            echo "❌ Daemon not running (stale PID file found)"
            rm -f "$PID_FILE"
        fi
    else
        echo "❌ Daemon is not running"
    fi
}

restart_daemon() {
    echo "🔄 Restarting log sync daemon..."
    stop_daemon
    sleep 2
    start_daemon
}

show_logs() {
    if [ -f "$LOG_FILE" ]; then
        echo "📄 Showing last 20 log entries from today ($TODAY):"
        echo "=================================================="
        tail -n 20 "$LOG_FILE"
    else
        echo "❌ Log file not found: $LOG_FILE"
        echo "Available log dates:"
        ls -1 "$LOG_DIR" 2>/dev/null | grep -E '[0-9]{4}-[0-9]{2}-[0-9]{2}' || echo "No log directories found"
    fi
}

show_logs_date() {
    local date=$1
    local date_log_file="$LOG_DIR/$date/logs.log"
    
    if [ -f "$date_log_file" ]; then
        echo "📄 Showing last 20 log entries from $date:"
        echo "==========================================="
        tail -n 20 "$date_log_file"
    else
        echo "❌ Log file not found: $date_log_file"
    fi
}

follow_logs() {
    if [ -f "$LOG_FILE" ]; then
        echo "📄 Following log file for today ($TODAY) - Ctrl+C to stop:"
        echo "=========================================================="
        tail -f "$LOG_FILE"
    else
        echo "❌ Log file not found: $LOG_FILE"
        echo "Waiting for log file to be created..."
        # Create the directory structure if it doesn't exist
        mkdir -p "$(dirname "$LOG_FILE")"
        # Wait for the file to appear
        while [ ! -f "$LOG_FILE" ]; do
            sleep 1
        done
        echo "Log file created, following..."
        tail -f "$LOG_FILE"
    fi
}

show_errors() {
    local error_file="$LOG_DIR/$TODAY/errors.log"
    if [ -f "$error_file" ]; then
        echo "❌ Showing errors from today ($TODAY):"
        echo "====================================="
        cat "$error_file"
    else
        echo "✅ No errors logged for today ($TODAY)"
    fi
}

case "$1" in
    start)
        start_daemon
        ;;
    stop)
        stop_daemon
        ;;
    restart)
        restart_daemon
        ;;
    status)
        status_daemon
        ;;
    logs)
        if [ -n "$2" ]; then
            show_logs_date "$2"
        else
            show_logs
        fi
        ;;
    errors)
        show_errors
        ;;
    follow)
        follow_logs
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs [date]|errors|follow}"
        echo ""
        echo "Commands:"
        echo "  start        - Start the log sync daemon"
        echo "  stop         - Stop the log sync daemon"
        echo "  restart      - Restart the log sync daemon"
        echo "  status       - Show daemon status and recent activity"
        echo "  logs [date]  - Show last 20 log entries (optional: for specific date YYYY-MM-DD)"
        echo "  errors       - Show error logs for today"
        echo "  follow       - Follow log file in real-time"
        echo ""
        echo "Examples:"
        echo "  $0 logs              # Show today's logs"
        echo "  $0 logs 2025-07-15   # Show logs for specific date"
        exit 1
        ;;
esac 