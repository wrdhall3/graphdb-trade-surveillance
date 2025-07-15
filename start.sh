#!/bin/bash

# Trade Surveillance System Startup Script

echo "🚀 Starting Trade Surveillance System..."

# Check if environment file exists
if [ ! -f ".env" ]; then
    echo "⚠️  Environment file not found. Creating from template..."
    cp env.example .env
    echo "📝 Please edit .env with your configuration before continuing"
    exit 1
fi

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
echo "🔍 Checking prerequisites..."

if ! command_exists python3; then
    echo "❌ Python 3 is not installed. Please install Python 3.8+"
    exit 1
fi

if ! command_exists node; then
    echo "❌ Node.js is not installed. Please install Node.js 16+"
    exit 1
fi

if ! command_exists npm; then
    echo "❌ npm is not installed. Please install npm"
    exit 1
fi

echo "✅ Prerequisites check passed"

# Setup backend
echo "🐍 Setting up backend..."
cd backend

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install Python dependencies
echo "📥 Installing Python dependencies..."
pip install -r requirements.txt

# Start backend in background
echo "🚀 Starting backend server..."
python main.py &
BACKEND_PID=$!

# Wait for backend to be ready with health check
echo "⏳ Waiting for backend to be ready..."
BACKEND_READY=false
for i in {1..30}; do
    if curl -s http://localhost:8000/ready >/dev/null 2>&1; then
        echo "✅ Backend is ready after ${i} seconds"
        BACKEND_READY=true
        break
    fi
    echo "⏳ Backend not ready yet (attempt $i/30)..."
    sleep 1
done

if [ "$BACKEND_READY" = false ]; then
    echo "❌ Backend failed to start within 30 seconds"
    echo "🔍 Backend logs:"
    ps aux | grep python | grep main.py
    exit 1
fi

# Check if backend is still running
if ps -p $BACKEND_PID > /dev/null; then
    echo "✅ Backend started successfully (PID: $BACKEND_PID)"
else
    echo "❌ Backend process died"
    exit 1
fi

# Setup frontend
echo "⚛️  Setting up frontend..."
cd ../frontend

# Install Node.js dependencies
echo "📥 Installing Node.js dependencies..."
npm install

# Start frontend
echo "🚀 Starting frontend development server..."
echo "💡 The frontend will automatically wait for the backend to be ready"
npm start &
FRONTEND_PID=$!

# Wait for frontend to start
echo "⏳ Waiting for frontend to start..."
sleep 10

echo "🎉 Trade Surveillance System is now running!"
echo ""
echo "📊 Backend API: http://localhost:8000"
echo "🌐 Frontend UI: http://localhost:3000"
echo "📚 API Documentation: http://localhost:8000/docs"
echo "🔍 Health Check: http://localhost:8000/health"
echo "🚀 Ready Check: http://localhost:8000/ready"
echo ""
echo "To stop the system, run: kill $BACKEND_PID $FRONTEND_PID"
echo ""
echo "💡 Make sure your Neo4j database is running and configured in .env"
echo "🔑 Add your OpenAI API key to .env for NLP features"
echo ""
echo "🐛 If you see proxy errors, wait ~30 seconds for backend initialization to complete"

# Keep script running
wait 