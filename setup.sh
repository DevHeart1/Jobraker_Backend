#!/bin/bash

# Jobraker Backend Setup Script
# This script sets up the development environment for Jobraker

set -e

echo "🚀 Setting up Jobraker Backend Development Environment"
echo "=================================================="

# Check if Python 3.9+ is installed
python_version=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
required_version="3.9"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ Python 3.9+ is required. Current version: $python_version"
    exit 1
fi

echo "✅ Python version check passed: $python_version"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️ Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📚 Installing dependencies..."
pip install -r requirements.txt

# Install development dependencies
echo "🛠️ Installing development dependencies..."
pip install -r requirements-dev.txt

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "⚙️ Creating .env file from template..."
    cp .env.example .env
    echo "📝 Please edit .env file with your configuration"
fi

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p logs media static templates

# Check if Docker is available
if command -v docker &> /dev/null; then
    echo "🐳 Docker is available"
    
    # Ask if user wants to start services with Docker
    read -p "Do you want to start PostgreSQL and Redis with Docker? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🚀 Starting Docker services..."
        docker-compose up -d db redis
        
        # Wait for services to be ready
        echo "⏳ Waiting for services to be ready..."
        sleep 10
    fi
else
    echo "⚠️ Docker not found. Please install PostgreSQL and Redis manually."
fi

# Run migrations
echo "🗄️ Running database migrations..."
python manage.py makemigrations
python manage.py migrate

# Create superuser if in interactive mode
if [ -t 0 ]; then
    read -p "Do you want to create a superuser? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        python manage.py createsuperuser
    fi
fi

# Collect static files
echo "📄 Collecting static files..."
python manage.py collectstatic --noinput

echo ""
echo "🎉 Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your API keys and configuration"
echo "2. Start the development server: python manage.py runserver"
echo "3. Start Celery worker: celery -A jobraker worker --loglevel=info"
echo "4. Start Celery beat: celery -A jobraker beat --loglevel=info"
echo ""
echo "API Documentation will be available at: http://localhost:8000/api/docs/"
echo "Admin panel will be available at: http://localhost:8000/admin/"
echo ""
echo "Happy coding! 🚀"
