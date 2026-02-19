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
    echo "♻️ Updating existing installation at $GOKU_DIR..."
    # If it's a git repo, pull latest
    if [ -d "$GOKU_DIR/.git" ]; then
        cd "$GOKU_DIR"
        git pull
    else
        # If it's not a git repo (e.g. from previous local copy), warn or backup?
        # For simplicity, we'll just overwrite/update
        echo "⚠️  Directory exists but is not a git repository. Continuing..."
    fi
else
    echo "📁 Creating installation directory at $GOKU_DIR..."
    mkdir -p "$GOKU_DIR"
fi

# 3. Determine Source (Local or Remote)
# If BASH_SOURCE is empty or we are piped, we are likely running from curl
if [ -z "${BASH_SOURCE[0]}" ] || [ "${BASH_SOURCE[0]}" == "$0" ]; then
    # Remote Install
    echo "⬇️  Downloading Goku Agent from $REPO_URL..."
    
    if [ -d "$GOKU_DIR/.git" ]; then
        cd "$GOKU_DIR"
        git pull
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
    cp -r "$SOURCE_DIR/." "$GOKU_DIR/"
fi


# 4. Virtual Environment Setup
echo "🐍 Setting up virtual environment..."
cd "$GOKU_DIR"
if [ -d "venv" ]; then
    echo "🗑️ Removing existing virtual environment..."
    rm -rf venv
fi
$PYTHON_CMD -m venv venv
source venv/bin/activate
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
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

# 7. Final Instructions
echo ""
echo "--------------------------------------------------------"
echo "✅ Goku AI Agent installed successfully!"
echo ""
echo "Commands:"
echo "  goku cli    - Launch interactive terminal agent"
echo "  goku web    - Launch high-fidelity web dashboard"
echo ""
echo "Ensure '$BIN_DIR' is in your PATH."
echo "If not, add 'export PATH=\$PATH:$BIN_DIR' to your .bashrc/.zshrc"
echo "--------------------------------------------------------"
echo "🐉 Happy building with Goku!"
