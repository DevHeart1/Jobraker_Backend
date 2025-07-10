# Jobraker Communication System - Quick Start Script (PowerShell)

Write-Host "🚀 Starting Jobraker Communication System..." -ForegroundColor Green

# Check if virtual environment exists
if (-not (Test-Path ".venv")) {
    Write-Host "❌ Virtual environment not found. Please run setup first:" -ForegroundColor Red
    Write-Host "   python -m venv .venv"
    Write-Host "   .venv\Scripts\activate"
    Write-Host "   pip install -r requirements.txt"
    exit 1
}

# Activate virtual environment
Write-Host "📦 Activating virtual environment..." -ForegroundColor Yellow
& ".venv\Scripts\activate.ps1"

# Check if .env exists
if (-not (Test-Path ".env")) {
    Write-Host "⚙️  Creating .env file from template..." -ForegroundColor Yellow
    Copy-Item "env_template.txt" ".env"
    Write-Host "✅ .env file created. Please update with your API keys." -ForegroundColor Green
}

# Run migrations
Write-Host "🗄️  Running database migrations..." -ForegroundColor Yellow
python manage.py migrate

# Start development server
Write-Host "🌐 Starting Django development server..." -ForegroundColor Green
Write-Host "📧 Email backend: Console (development mode)" -ForegroundColor Cyan
Write-Host "🔌 WebSocket support: Enabled" -ForegroundColor Cyan
Write-Host "🏥 Health check: http://localhost:8000/api/v1/notifications/health/" -ForegroundColor Cyan
Write-Host ""
Write-Host "✅ System ready! Visit http://localhost:8000" -ForegroundColor Green
Write-Host ""

python manage.py runserver 0.0.0.0:8000
