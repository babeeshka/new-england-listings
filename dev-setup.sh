#!/bin/bash

# Exit on error and enable debug output
set -e  # Exit on error
set -x  # Print commands as they're executed

echo "Starting setup..."

# Deactivate any active virtual environment
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo "Deactivating current virtual environment..."
    deactivate
fi

# Clean up Python cache files and build artifacts
echo "Cleaning up..."
find . -type f -name "*.pyc" -delete
find . -type d -name "__pycache__" -delete
find . -type d -name "*.egg-info" -exec rm -r {} +
find . -type d -name ".pytest_cache" -delete
find . -type d -name ".coverage" -delete
find . -type d -name "htmlcov" -delete

# Remove existing virtual environment if --clean flag is passed
if [[ "$1" == "--clean" ]]; then
    echo "Removing existing virtual environment..."
    rm -rf .venv
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Create activation scripts for different shells
echo "Creating activation scripts..."
# For bash/zsh
cat > activate.sh << 'EOL'
#!/bin/bash
source .venv/bin/activate
EOL
chmod +x activate.sh

# For fish shell
cat > activate.fish << 'EOL'
#!/usr/bin/env fish
source .venv/bin/activate.fish
EOL
chmod +x activate.fish

# Activate virtual environment (handle both Unix and Windows)
echo "Activating virtual environment..."
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    source .venv/Scripts/activate
else
    source .venv/bin/activate
fi

# Upgrade pip and install dependencies
echo "Installing dependencies..."
python -m pip install --upgrade pip setuptools wheel

# Install package in editable mode with dev dependencies
pip install -e ".[dev]"

# Install additional test dependencies
echo "Installing test dependencies..."
pip install pytest pytest-cov pytest-xdist

# Add this after the package installations
echo "Checking system dependencies..."
if ! command -v google-chrome &> /dev/null; then
    echo "Chrome is not installed. Installing Chrome..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if ! command -v brew &> /dev/null; then
            echo "Homebrew is required to install Chrome. Please install Homebrew first."
            exit 1
        fi
        brew install --cask google-chrome
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        sudo apt-get update
        sudo apt-get install -y google-chrome-stable
    else
        echo "Unsupported operating system for automatic Chrome installation"
        echo "Please install Chrome manually"
        exit 1
    fi
fi

echo "Setup complete!"
echo "Virtual environment is at: $(which python)"
echo "Python version: $(python --version)"
echo "Pip version: $(pip --version)"

echo ""
echo "=================================================================="
echo "IMPORTANT: To activate the virtual environment, use one of:"
echo "    source activate.sh        # for bash/zsh"
echo "    source activate.fish      # for fish shell"
echo "=================================================================="