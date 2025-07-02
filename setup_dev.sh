#!/bin/bash

# Jobraker Backend Setup Script
# This script helps set up the development environment

echo "🚀 Setting up Jobraker Backend Development Environment..."

# Check if Python is installed
if ! command -v python &> /dev/null; then
    echo "❌ Python is not installed. Please install Python 3.9+ first."
    exit 1
fi

# Check Python version
python_version=$(python --version 2>&1 | awk '{print $2}')
echo "✅ Python version: $python_version"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating Python virtual environment..."
    python -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️ Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "📚 Installing Python dependencies..."
pip install -r requirements.txt

# Install development dependencies
if [ -f "requirements-dev.txt" ]; then
    echo "🛠️ Installing development dependencies..."
    pip install -r requirements-dev.txt
fi

# Check for environment file
if [ ! -f ".env" ]; then
    echo "📝 Creating environment file from template..."
    cp env_template.txt .env
    echo "⚠️ Please edit .env file with your actual API keys and database configuration"
fi

# Check if PostgreSQL is installed
if command -v psql &> /dev/null; then
    echo "✅ PostgreSQL is available"
else
    echo "⚠️ PostgreSQL not found. Please install PostgreSQL with pgvector extension."
    echo "   Visit: https://github.com/pgvector/pgvector for installation instructions"
fi

# Check if Redis is installed
if command -v redis-cli &> /dev/null; then
    echo "✅ Redis is available"
else
    echo "⚠️ Redis not found. Please install Redis for Celery message broker."
    echo "   Visit: https://redis.io/download for installation instructions"
fi

echo ""
echo "🎉 Setup complete! Next steps:"
echo ""
echo "1. Edit .env file with your API keys and database configuration"
echo "2. Set up PostgreSQL database with pgvector extension"
echo "3. Start Redis server"
echo "4. Run database migrations: python manage.py migrate"
echo "5. Create superuser: python manage.py createsuperuser"
echo "6. Start development server: python manage.py runserver"
echo "7. Start Celery worker: celery -A jobraker worker -l info"
echo "8. Start Celery beat: celery -A jobraker beat -l info"
echo ""
echo "📚 Check README.md for detailed setup instructions"
