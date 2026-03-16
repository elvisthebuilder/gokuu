#!/bin/bash

set -e

# Goku AI Agent Installer
GOKU_DIR="$HOME/.goku-agent"
BIN_DIR="$HOME/.local/bin"
REPO_URL="https://github.com/elvisthebuilder/gokuu.git"

echo "🐉 Welcome to the Goku AI Agent Installer!"

# 1. System Check & Dependencies
# 1. System Check & Dependencies
echo "🔍 Checking system dependencies..."
if [[ "$OSTYPE" == "linux-gnu"* ]] || [[ "$OSTYPE" == "darwin"* ]]; then
    # Function to check if a command exists
    command_exists() {
        command -v "$1" >/dev/null 2>&1
    }

    # Try to find a specific compatible python version
    if command_exists python3.12; then
        PYTHON_CMD="python3.12"
    elif command_exists python3.11; then
        PYTHON_CMD="python3.11"
    elif command_exists python3.10; then
        PYTHON_CMD="python3.10"
    elif command_exists python3; then
        PYTHON_CMD="python3"
    else
        echo "❌ Python 3 is required but not installed."
        exit 1
    fi
    echo "Using $PYTHON_CMD"
else
    echo "⚠️  Unsupported OS type: $OSTYPE. Proceeding with caution."
    PYTHON_CMD="python3"
fi

# Check for git
if ! command -v git &> /dev/null; then
    echo "❌ Git is required but not installed. Please install git and try again."
    exit 1
fi

# 2. Setup Directory
if [ -d "$GOKU_DIR" ]; then
    # If it's a git repo, force-update to avoid merge conflicts from local copies
    if [ -d "$GOKU_DIR/.git" ]; then
        cd "$GOKU_DIR"
        git fetch origin
        git reset --hard origin/main
        git clean -fd --quiet --exclude=qdrant_data
    else
        # If it's not a git repo (e.g. from previous local copy), warn or backup?
        # For simplicity, we'll just overwrite/update
        echo "⚠️  Directory exists but is not a git repository. Continuing..."
    fi
else
    echo "📁 Creating installation directory at $GOKU_DIR..."
    mkdir -p "$GOKU_DIR"
    mkdir -p "$GOKU_DIR/qdrant_data"
    mkdir -p "$GOKU_DIR/logs"
fi

# 3. Determine Source (Local or Remote)
# If BASH_SOURCE is empty or we are piped, we are likely running from curl
if [ -z "${BASH_SOURCE[0]}" ] || [ "${BASH_SOURCE[0]}" == "$0" ]; then
    # Remote Install
    echo "⬇️  Downloading Goku Agent from $REPO_URL..."
    
    if [ -d "$GOKU_DIR/.git" ]; then
        cd "$GOKU_DIR"
        git fetch origin
        git reset --hard origin/main
        git clean -fd --quiet --exclude=qdrant_data --exclude=server/personalities
    else
        # Clean directory if it exists but is empty or not a repo (safe init)
        # But we already checked above.
        # If directory exists and is NOT a git repo, 'git clone' will fail if not empty.
        # We'll try to clone into a temp dir and move, or just clone directly if empty.
        if [ "$(ls -A $GOKU_DIR)" ]; then
             echo "⚠️  Target directory $GOKU_DIR is not empty. Backing up..."
             mv "$GOKU_DIR" "${GOKU_DIR}.bak.$(date +%s)"
             mkdir -p "$GOKU_DIR"
        fi
        git clone "$REPO_URL" "$GOKU_DIR"
    fi
else
    # Local Install (running ./install.sh)
    SOURCE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
    echo "📦 Copying local files from $SOURCE_DIR to $GOKU_DIR..."
    
    # Backup user-data files that must not be overwritten by the local copy
    MAPPING_BACKUP=""
    if [ -f "$GOKU_DIR/server/personalities/mapping.json" ]; then
        MAPPING_BACKUP=$(cat "$GOKU_DIR/server/personalities/mapping.json")
    fi
    
    cp -r "$SOURCE_DIR/." "$GOKU_DIR/"
    
    # Restore the persona mapping file after the copy
    if [ -n "$MAPPING_BACKUP" ]; then
        mkdir -p "$GOKU_DIR/server/personalities"
        echo "$MAPPING_BACKUP" > "$GOKU_DIR/server/personalities/mapping.json"
        echo "✅ Persona channel mappings preserved."
    fi
fi


# 4. Virtual Environment Setup
echo "🐍 Setting up virtual environment..."
cd "$GOKU_DIR"
if [ ! -d "venv" ]; then
    echo "📁 Creating new virtual environment..."
    $PYTHON_CMD -m venv venv
else
    echo "✅ Using existing virtual environment."
fi

# Ensure we use the venv's python/pip directly for robustness
VENV_PIP="$GOKU_DIR/venv/bin/pip"
VENV_PYTHON="$GOKU_DIR/venv/bin/python3"

# Upgrade pip with retry
echo "⬆️  Upgrading pip..."
for i in {1..3}; do
    if $VENV_PYTHON -m pip install --upgrade pip; then
        break
    else
        if [ $i -eq 3 ]; then
            echo "❌ Failed to upgrade pip after 3 attempts."
            # We don't exit here, maybe requirements will still work
        else
            echo "⚠️  Pip upgrade failed. Retrying in 5s (Attempt $i/3)..."
            sleep 5
        fi
    fi
done

if [ -f "requirements.txt" ]; then
    echo "📦 Installing dependencies from requirements.txt..."
    for i in {1..3}; do
        if $VENV_PYTHON -m pip install -r requirements.txt; then
            echo "✅ Dependencies installed successfully."
            break
        else
            if [ $i -eq 3 ]; then
                echo "❌ Failed to install dependencies after 3 attempts. Please check your internet connection."
                exit 1
            else
                echo "⚠️  Dependency installation failed. Retrying in 10s (Attempt $i/3)..."
                sleep 10
            fi
        fi
    done
else
    echo "⚠️  requirements.txt not found! Skipping pip install."
fi

# 5. Build Web Frontend if possible
if command -v npm > /dev/null; then
    if [ -d "$GOKU_DIR/web" ]; then
        echo "🌐 Building web frontend..."
        cd "$GOKU_DIR/web"
        npm install
        npm run build
        cd "$GOKU_DIR"
    else
        echo "⚠️  Web directory not found. Skipping web build."
    fi
else
    echo "⚠️  'npm' not found. Skipping web build. You may need to build it manually."
fi

# 6. Global Command Setup
echo "🚀 Linking goku command..."
mkdir -p "$BIN_DIR"
chmod +x "$GOKU_DIR/goku.sh"
ln -sf "$GOKU_DIR/goku.sh" "$BIN_DIR/goku"

# 7. Path Configuration
echo "🔧 Configuring PATH..."
SHELL_CONFIG=""
case "$SHELL" in
    */zsh)
        SHELL_CONFIG="$HOME/.zshrc"
        ;;
    */bash)
        SHELL_CONFIG="$HOME/.bashrc"
        ;;
    *)
        # Fallback to bashrc if unknown or other
        if [ -f "$HOME/.bashrc" ]; then
            SHELL_CONFIG="$HOME/.bashrc"
        elif [ -f "$HOME/.zshrc" ]; then
             SHELL_CONFIG="$HOME/.zshrc"
        fi
        ;;
esac

if [ -n "$SHELL_CONFIG" ]; then
    EXPORT_CMD="export PATH=\"\$PATH:$BIN_DIR\""
    if grep -q "$BIN_DIR" "$SHELL_CONFIG"; then
        echo "✅ PATH already configured in $SHELL_CONFIG"
    else
        echo "➕ Adding $BIN_DIR to PATH in $SHELL_CONFIG"
        echo "" >> "$SHELL_CONFIG"
        echo "# Goku AI Agent" >> "$SHELL_CONFIG"
        echo "$EXPORT_CMD" >> "$SHELL_CONFIG"
    fi
else
    echo "⚠️  Could not detect shell configuration file. Please manually add '$BIN_DIR' to your PATH."
fi

# 8. Setup Systemd Gateway Service
echo "⚙️  Configuring Background Gateway Service..."
SERVICE_FILE="/etc/systemd/system/goku-gateway.service"
SERVICE_CONTENT="[Unit]
Description=Goku AI Background Gateway (Telegram, WhatsApp, Job Poller)
After=network-online.target

[Service]
User=$USER
WorkingDirectory=$GOKU_DIR
Environment=\"PATH=$GOKU_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin\"
ExecStart=$GOKU_DIR/venv/bin/python3 $GOKU_DIR/server/gateway.py
Restart=always
RestartSec=5
StandardOutput=append:$GOKU_DIR/logs/goku.log
StandardError=append:$GOKU_DIR/logs/goku.log

[Install]
WantedBy=multi-user.target"

# Ask for sudo specifically for systemd if possible, or skip if missing perms
if command -v systemctl > /dev/null; then
    echo "Requires sudo to install systemd service..."
    if sudo bash -c "echo \"$SERVICE_CONTENT\" > $SERVICE_FILE"; then
        sudo systemctl daemon-reload
        sudo systemctl enable goku-gateway.service
        echo "✅ Systemd service installed. You can start it with: goku start"
    else
        echo "⚠️  Failed to create systemd service (sudo required). You can manually run the gateway via 'python3 server/gateway.py'."
    fi
else
    echo "⚠️  systemctl not found. Background service creation skipped."
fi

# 9. Final Instructions
echo ""
echo "--------------------------------------------------------"
echo "✅ Goku AI Agent installed successfully!"
echo ""
echo "Commands:"
echo "  goku cli      - Launch interactive terminal agent"
echo "  goku web      - Launch high-fidelity web dashboard"
echo "  goku start    - Start the background bots (Gateway)"
echo "  goku stop     - Stop the background bots"
echo "  goku status   - Check background bot status"
echo ""
if [ -n "$SHELL_CONFIG" ]; then
    echo "🔄 Please run 'source $SHELL_CONFIG' or restart your terminal to use the 'goku' command."
else
    echo "Ensure '$BIN_DIR' is in your PATH."
    echo "If not, add 'export PATH=\$PATH:$BIN_DIR' to your .bashrc/.zshrc"
fi
echo "--------------------------------------------------------"
echo "🐉 Happy building with Goku!"
