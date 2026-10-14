#!/usr/bin/env bash
set -e

# Always run from the project root directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Starting RepoDoctor Preflight Checks ==="

# 1. Check Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Error: Docker command not found in PATH."
    echo "RepoDoctor requires Docker to run tests safely in an isolated sandbox container."
    echo "Please install Docker Desktop from https://www.docker.com/products/docker-desktop"
    exit 1
fi

# 2. Check Docker daemon is running
if ! docker info &> /dev/null; then
    echo "Error: Docker is installed, but the Docker daemon is not running."
    echo "Please launch Docker Desktop and wait until the engine has started before running RepoDoctor."
    exit 1
fi
echo "✓ Docker is installed and daemon is running."

# 3. Check / create Python virtual environment
if [ ! -d ".venv" ]; then
    echo "Virtual environment (.venv) not found. Creating .venv..."
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        echo "Error: Python 3 is not installed or not in PATH."
        exit 1
    fi

    "$PYTHON_CMD" -m venv .venv
    echo "Installing runtime dependencies into .venv from requirements.txt..."
    .venv/bin/pip install --upgrade pip --quiet
    .venv/bin/pip install -r requirements.txt --quiet
    echo "✓ Virtual environment created and requirements installed."
else
    echo "✓ Virtual environment (.venv) found."
fi

# Activate virtual environment
source .venv/bin/activate

# 4. Check .env exists
if [ ! -f ".env" ]; then
    echo "Error: .env configuration file not found."
    echo "Please copy .env.example to .env and configure your keys:"
    echo "  cp .env.example .env"
    exit 1
fi

# 5. Check needed keys are non-empty (never printing secret values)
python - << 'EOF'
import sys
import os
from dotenv import dotenv_values

env = dotenv_values(".env")

# Determine active provider (defaults to gemini if unset)
provider = (env.get("LLM_PROVIDER") or os.getenv("LLM_PROVIDER") or "gemini").strip().lower()

needed = []
if provider == "anthropic":
    needed.append("ANTHROPIC_API_KEY")
    needed.append("GITHUB_TOKEN")
elif provider == "mock":
    # Mock mode does not make external LLM calls
    pass
else:  # default "gemini"
    needed.append("GEMINI_API_KEY")
    needed.append("GITHUB_TOKEN")

missing = []
for key in needed:
    val = env.get(key)
    if val is None or not str(val).strip():
        missing.append(key)

if missing:
    print(f"Error: The following required environment variable(s) for provider '{provider}' are missing or empty in .env:")
    for key in missing:
        print(f"  - {key}")
    print("\nPlease populate these variables in your .env file before starting.")
    sys.exit(1)
else:
    print(f"✓ Configuration verified for provider '{provider}' (all required keys are set).")
EOF

# 6. Start uvicorn server on 127.0.0.1:8000
echo "=========================================================="
echo "Starting RepoDoctor on http://127.0.0.1:8000"
echo "Open http://127.0.0.1:8000 in your browser to use the UI."
echo "Press Ctrl+C to stop the server."
echo "=========================================================="

exec uvicorn backend.main:app --host 127.0.0.1 --port 8000
