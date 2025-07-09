#!/bin/bash

# Jobraker Backend Startup Script
# This script checks configuration and starts the necessary services

echo "🚀 Starting Jobraker Backend..."
echo "=================================="

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "💡 Copy env_template.txt to .env and configure your API keys"
    echo "   cp env_template.txt .env"
    exit 1
fi

echo "✅ Environment file found"

# Check Python environment
if ! command -v python &> /dev/null; then
    echo "❌ Python not found!"
    echo "💡 Please install Python 3.9+ and activate your virtual environment"
    exit 1
fi

echo "✅ Python environment ready"

# Install dependencies if needed
if [ ! -d "venv" ] && [ ! -f "requirements.txt.installed" ]; then
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
    touch requirements.txt.installed
fi

# Run migrations
echo "🗄️ Running database migrations..."
python manage.py migrate

# Check API configuration
echo "🔧 Checking API configuration..."
python manage.py test_apis --quick

# Collect static files
echo "📁 Collecting static files..."
python manage.py collectstatic --noinput

echo ""
echo "🎉 Jobraker Backend is ready!"
echo "=================================="
echo "🌐 Start the server: python manage.py runserver"
echo "⚡ Start Celery workers: celery -A jobraker worker -l info"
echo "📋 Start Celery beat: celery -A jobraker beat -l info"
echo "🧪 Test APIs: python manage.py test_apis"
echo ""
echo "📚 API Documentation: http://localhost:8000/api/docs/"
echo "🔧 Admin Panel: http://localhost:8000/admin/"
