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

# Automation: Ensure Qdrant is running for memory persistence
ensure_qdrant() {
    if ! command -v docker &> /dev/null; then
        echo "⚠️  Docker is not installed. Continuous memory will be disabled."
        return 1
    fi

    # Ensure data directory exists
    QDRANT_DATA="$HOME/.goku-agent/qdrant_data"
    mkdir -p "$QDRANT_DATA"

    # Check for Docker permissions
    DOCKER_CMD="docker"
    if ! docker ps > /dev/null 2>&1; then
        if docker ps 2>&1 | grep -q "permission denied"; then
            echo "🔐 Docker requires sudo permissions..."
            DOCKER_CMD="sudo docker"
        else
            echo "⚠️  Docker is installed but not running. Continuous memory will be disabled."
            return 1
        fi
    fi

    # Check if container is running
    if ! $DOCKER_CMD ps --format '{{.Names}}' | grep -q "^goku-qdrant$"; then
        echo "🧠 Starting Qdrant Vector Engine..."
        # Try to start it if it exists but is stopped
        if $DOCKER_CMD ps -a --format '{{.Names}}' | grep -q "^goku-qdrant$"; then
            $DOCKER_CMD start goku-qdrant >/dev/null
        else
            # Create and start it
            $DOCKER_CMD run -d \
                --name goku-qdrant \
                -p 6333:6333 \
                -p 6334:6334 \
                -v "$QDRANT_DATA:/qdrant/storage" \
                --restart always \
                qdrant/qdrant:latest >/dev/null
        fi
        
        # Wait for Qdrant to be ready (max 5s)
        for i in {1..5}; do
            if curl -s http://localhost:6333/health | grep -q "ok"; then
                echo "✅ Qdrant is ONLINE."
                break
            fi
            sleep 1
        done
    fi
}

case "$1" in
    cli)
        shift
        ensure_qdrant
        # Start the CLI interactive mode
        $VENV_PYTHON "$SCRIPT_DIR/client/app.py" interactive "$@"
        ;;
    web)
        shift
        ensure_qdrant
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
    channel)
        shift
        subcommand=$1
        shift
        if [ "$subcommand" == "logs" ]; then
            $VENV_PYTHON "$SCRIPT_DIR/client/app.py" channel-logs "$@"
        else
            echo "❌ Unknown channel subcommand: $subcommand. Try 'goku channel logs'"
            exit 1
        fi
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

        # Fetch and check for changes
        git fetch origin
        LOCAL=$(git rev-parse HEAD)
        REMOTE=$(git rev-parse @{u})
        
        if [ "$LOCAL" = "$REMOTE" ]; then
             echo "✅ Goku is already up to date!"
        else
             echo "🚀 Update found! Re-running installer..."
             git reset --hard origin/main
             git clean -fd --quiet --exclude=qdrant_data --exclude=server/personalities
             
             # Make sure install.sh is executable
             chmod +x ./install.sh
             ./install.sh
        fi
        ;;
    start)
        ensure_qdrant
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
        ensure_qdrant
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
