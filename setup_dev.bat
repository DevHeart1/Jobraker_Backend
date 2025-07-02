@echo off
REM Jobraker Backend Setup Script for Windows
REM This script helps set up the development environment

echo 🚀 Setting up Jobraker Backend Development Environment...

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed. Please install Python 3.9+ first.
    pause
    exit /b 1
)

REM Show Python version
echo ✅ Python is available
python --version

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo 📦 Creating Python virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo 🔧 Activating virtual environment...
call venv\Scripts\activate

REM Upgrade pip
echo ⬆️ Upgrading pip...
python -m pip install --upgrade pip

REM Install requirements
echo 📚 Installing Python dependencies...
pip install -r requirements.txt

REM Install development dependencies
if exist "requirements-dev.txt" (
    echo 🛠️ Installing development dependencies...
    pip install -r requirements-dev.txt
)

REM Check for environment file
if not exist ".env" (
    echo 📝 Creating environment file from template...
    copy env_template.txt .env
    echo ⚠️ Please edit .env file with your actual API keys and database configuration
)

REM Check if PostgreSQL is available
where psql >nul 2>&1
if errorlevel 1 (
    echo ⚠️ PostgreSQL not found. Please install PostgreSQL with pgvector extension.
    echo    Visit: https://github.com/pgvector/pgvector for installation instructions
) else (
    echo ✅ PostgreSQL is available
)

REM Check if Redis is available
where redis-cli >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Redis not found. Please install Redis for Celery message broker.
    echo    Visit: https://github.com/microsoftarchive/redis/releases for Windows Redis
) else (
    echo ✅ Redis is available
)

echo.
echo 🎉 Setup complete! Next steps:
echo.
echo 1. Edit .env file with your API keys and database configuration
echo 2. Set up PostgreSQL database with pgvector extension
echo 3. Start Redis server
echo 4. Run database migrations: python manage.py migrate
echo 5. Create superuser: python manage.py createsuperuser
echo 6. Start development server: python manage.py runserver
echo 7. Start Celery worker: celery -A jobraker worker -l info
echo 8. Start Celery beat: celery -A jobraker beat -l info
echo.
echo 📚 Check README.md for detailed setup instructions
echo.
pause
