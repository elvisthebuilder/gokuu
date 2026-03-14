#!/bin/bash

# Get the directory where this script is located (resolving symlinks)
SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do # resolve $SOURCE until the file is no longer a symlink
  DIR="$( cd -P "$( dirname "$SOURCE" )" >/dev/null 2>&1 && pwd )"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE" # if $SOURCE was a relative symlink, we need to resolve it relative to the path where the symlink file was located
done
SCRIPT_DIR="$( cd -P "$( dirname "$SOURCE" )" >/dev/null 2>&1 && pwd )"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"

# Fallback to system python if venv doesn't exist (unlikely if installed correctly)
if [ ! -f "$VENV_PYTHON" ]; then
    VENV_PYTHON="python3"
fi

case "$1" in
    cli)
        shift
        # Start the CLI interactive mode
        $VENV_PYTHON "$SCRIPT_DIR/client/app.py" interactive "$@"
        ;;
    web)
        shift
        echo "🐉 Starting Goku Web Dashboard..."
        # Start the backend in the background
        $VENV_PYTHON "$SCRIPT_DIR/server/main.py" &
        BACKEND_PID=$!
        
        # Wait a moment for server to start
        sleep 2
        
        # Open browser
        if command -v xdg-open > /dev/null; then
            xdg-open "http://localhost:8000"
        elif command -v open > /dev/null; then
            open "http://localhost:8000"
        else
            echo "✅ Server started at http://localhost:8000"
        fi
        
        # Keep script running to manage process
        wait $BACKEND_PID
        ;;
    logs)
        shift
        # Call the logs command in app.py
        $VENV_PYTHON "$SCRIPT_DIR/client/app.py" logs "$@"
        ;;
    update)
        shift
        echo "⬇️  Checking for updates..."
        cd "$SCRIPT_DIR"
        
        # Check if git is available
        if ! command -v git &> /dev/null; then
            echo "❌ Git is required for updates but not installed."
            exit 1
        fi

        # Check if it's a git repo
        if [ ! -d ".git" ]; then
            echo "❌ This installation is not a git repository. Cannot update automatically."
            exit 1
        fi

        # Pull latest changes
        if git pull | grep -q "Already up to date"; then
             echo "✅ Goku is already up to date!"
        else
             echo "🚀 Update found! Re-running installer..."
             # Make sure install.sh is executable
             chmod +x ./install.sh
             ./install.sh
        fi
        ;;
    start)
        echo "🚀 Starting Goku Background Gateway..."
        sudo systemctl start goku-gateway
        echo "✅ Gateway started. Run 'goku status' to verify."
        ;;
    stop)
        echo "🛑 Stopping Goku Background Gateway..."
        sudo systemctl stop goku-gateway
        echo "✅ Gateway stopped."
        ;;
    restart)
        echo "🔄 Restarting Goku Background Gateway..."
        sudo systemctl restart goku-gateway
        echo "✅ Gateway restarted."
        ;;
    status)
        sudo systemctl status goku-gateway
        ;;
    *)
        echo "Usage: goku [cli|web|logs|update|start|stop|restart|status]"
        echo ""
        echo "Interfaces:"
        echo "  cli      Start the interactive terminal agent"
        echo "  web      Launch the high-fidelity web dashboard"
        echo ""
        echo "Operations:"
        echo "  logs     View diagnostic logs"
        echo "  update   Pull latest version and re-install"
        echo ""
        echo "Background Gateway (Bots & Pollers):"
        echo "  start    Start the background gateway service"
        echo "  stop     Stop the background gateway service"
        echo "  restart  Restart the background gateway service"
        echo "  status   Check if the gateway is running"
        exit 1
        ;;
esac
