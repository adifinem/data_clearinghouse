#!/bin/bash
# Simple launcher script for portfolio reconciliation system

set -e

echo "Portfolio Data Clearinghouse - Quick Start"
echo "=========================================="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt

echo ""
echo "Starting Flask application in background..."
echo "API will be available at: http://localhost:5000"
echo ""

# Start Flask app in background, redirect output to /dev/null
python app.py > /dev/null 2>&1 &
FLASK_PID=$!

# Cleanup function to kill Flask server on exit
cleanup() {
    echo ""
    echo "Shutting down Flask server (PID: $FLASK_PID)..."
    kill $FLASK_PID 2>/dev/null || true
    wait $FLASK_PID 2>/dev/null || true
    echo "Cleanup complete."
}

# Register cleanup function to run on script exit
trap cleanup EXIT INT TERM

# Give Flask a moment to start up
sleep 2

echo "Launching demo application..."
echo ""

# Run demo in foreground, passing all command-line arguments
python demo.py "$@"
