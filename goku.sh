#!/bin/bash

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
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
    *)
        echo "Usage: goku [cli|web]"
        echo ""
        echo "Commands:"
        echo "  cli   Start the interactive terminal agent"
        echo "  web   Launch the high-fidelity web dashboard"
        exit 1
        ;;
esac
