#!/bin/bash
# Jobraker Communication System - Quick Start Script

echo "🚀 Starting Jobraker Communication System..."

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found. Please run setup first:"
    echo "   python -m venv .venv"
    echo "   source .venv/bin/activate  # Linux/Mac"
    echo "   .venv\\Scripts\\activate     # Windows"
    echo "   pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
echo "📦 Activating virtual environment..."
source .venv/bin/activate

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "⚙️  Creating .env file from template..."
    cp env_template.txt .env
    echo "✅ .env file created. Please update with your API keys."
fi

# Run migrations
echo "🗄️  Running database migrations..."
python manage.py migrate

# Start development server
echo "🌐 Starting Django development server..."
echo "📧 Email backend: Console (development mode)"
echo "🔌 WebSocket support: Enabled"
echo "🏥 Health check: http://localhost:8000/api/v1/notifications/health/"
echo ""
echo "✅ System ready! Visit http://localhost:8000"
echo ""

python manage.py runserver 0.0.0.0:8000
