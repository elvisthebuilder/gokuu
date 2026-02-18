#!/bin/bash

set -e

# Goku AI Agent Installer
GOKU_DIR="$HOME/.goku-agent"
BIN_DIR="$HOME/.local/bin"

echo "🐉 Welcome to the Goku AI Agent Installer!"

# 1. System Check & Dependencies
echo "🔍 Checking system dependencies..."
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    PYTHON_CMD="python3"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    PYTHON_CMD="python3"
else
    echo "⚠️  Unsupported OS type: $OSTYPE. Proceeding with caution."
    PYTHON_CMD="python3"
fi

# 2. Setup Directory
if [ -d "$GOKU_DIR" ]; then
    echo "♻️ Updating existing installation at $GOKU_DIR..."
else
    echo "📁 Creating installation directory at $GOKU_DIR..."
    mkdir -p "$GOKU_DIR"
fi

# 3. Reference Current Directory as source (imitating extraction/clone)
SOURCE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo "📦 Copying files to $GOKU_DIR..."
cp -r "$SOURCE_DIR/." "$GOKU_DIR/"

# 4. Virtual Environment Setup
echo "🐍 Setting up virtual environment..."
cd "$GOKU_DIR"
$PYTHON_CMD -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 5. Build Web Frontend if possible
if command -v npm > /dev/null; then
    echo "🌐 Building web frontend..."
    cd "$GOKU_DIR/web"
    npm install
    npm run build
    cd "$GOKU_DIR"
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
