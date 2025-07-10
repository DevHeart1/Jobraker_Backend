# Communication System Setup Script for Jobraker Backend (PowerShell)

Write-Host "🚀 Setting up Jobraker Communication System..." -ForegroundColor Green

# Check if virtual environment is activated
if (-not $env:VIRTUAL_ENV) {
    Write-Host "⚠️  Warning: No virtual environment detected. Please activate your virtual environment first." -ForegroundColor Yellow
    Write-Host "   Run: python -m venv venv && .\venv\Scripts\Activate.ps1" -ForegroundColor Yellow
    exit 1
}

# Install required dependencies
Write-Host "📦 Installing dependencies..." -ForegroundColor Blue
pip install -r requirements.txt

# Check if Redis is running
Write-Host "🔴 Checking Redis connection..." -ForegroundColor Blue
python -c @"
import redis
try:
    r = redis.Redis(host='localhost', port=6379, db=0)
    r.ping()
    print('✅ Redis is running and accessible')
except Exception as e:
    print('❌ Redis connection failed:', e)
    print('   Please install and start Redis:')
    print('   - Windows: Download from https://redis.io/download')
    print('   - Or use Docker: docker run -d -p 6379:6379 redis:alpine')
    exit(1)
"@

# Check database configuration
Write-Host "🗄️  Checking database configuration..." -ForegroundColor Blue
python manage.py check --database default

# Run migrations
Write-Host "🔄 Running database migrations..." -ForegroundColor Blue
python manage.py migrate

# Create static directory if it doesn't exist
Write-Host "📁 Creating static directory..." -ForegroundColor Blue
if (-not (Test-Path "static")) {
    New-Item -ItemType Directory -Path "static"
}

# Test email configuration
Write-Host "📧 Testing email configuration..." -ForegroundColor Blue
python manage.py shell -c @"
from django.core.mail import send_mail
from django.conf import settings
print(f'Email backend: {settings.EMAIL_BACKEND}')
print(f'Email host: {settings.EMAIL_HOST}')
print('✅ Email configuration loaded successfully')
"@

# Test WebSocket configuration
Write-Host "🔌 Testing WebSocket configuration..." -ForegroundColor Blue
python manage.py shell -c @"
from channels.layers import get_channel_layer
layer = get_channel_layer()
print(f'Channel layer: {layer.__class__.__name__}')
print('✅ WebSocket configuration loaded successfully')
"@

# Test Celery configuration
Write-Host "⚙️  Testing Celery configuration..." -ForegroundColor Blue
python manage.py shell -c @"
from celery import current_app
print(f'Celery broker: {current_app.conf.broker_url}')
print(f'Celery backend: {current_app.conf.result_backend}')
print('✅ Celery configuration loaded successfully')
"@

# Check for superuser
Write-Host "👤 Checking for superuser..." -ForegroundColor Blue
python manage.py shell -c @"
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(is_superuser=True).exists():
    print('❌ No superuser found. Please create one:')
    print('   Run: python manage.py createsuperuser')
else:
    print('✅ Superuser exists')
"@

Write-Host ""
Write-Host "🎉 Communication System Setup Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "📋 Next Steps:" -ForegroundColor Cyan
Write-Host "1. Start Redis (if not already running):" -ForegroundColor White
Write-Host "   redis-server" -ForegroundColor Gray
Write-Host "   OR with Docker: docker run -d -p 6379:6379 redis:alpine" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Start Celery worker (in a new PowerShell window):" -ForegroundColor White
Write-Host "   celery -A jobraker worker --loglevel=info" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Start Celery beat scheduler (in a new PowerShell window):" -ForegroundColor White
Write-Host "   celery -A jobraker beat --loglevel=info" -ForegroundColor Gray
Write-Host ""
Write-Host "4. Start Django development server:" -ForegroundColor White
Write-Host "   python manage.py runserver" -ForegroundColor Gray
Write-Host ""
Write-Host "5. For WebSocket support, use Daphne instead:" -ForegroundColor White
Write-Host "   daphne jobraker.asgi:application" -ForegroundColor Gray
Write-Host ""
Write-Host "📧 Email Features:" -ForegroundColor Cyan
Write-Host "- Welcome emails for new users" -ForegroundColor White
Write-Host "- Job alert notifications" -ForegroundColor White
Write-Host "- Application status updates" -ForegroundColor White
Write-Host "- Job recommendations" -ForegroundColor White
Write-Host "- Password reset emails" -ForegroundColor White
Write-Host ""
Write-Host "🔌 WebSocket Features:" -ForegroundColor Cyan
Write-Host "- Real-time chat with AI assistant" -ForegroundColor White
Write-Host "- Real-time notifications" -ForegroundColor White
Write-Host "- Typing indicators" -ForegroundColor White
Write-Host "- Message persistence" -ForegroundColor White
Write-Host ""
Write-Host "🧪 Test Commands:" -ForegroundColor Cyan
Write-Host "- Test email: python manage.py test_email --test-type all" -ForegroundColor Gray
Write-Host "- Check system: python manage.py check" -ForegroundColor Gray
Write-Host "- Run tests: python manage.py test apps.notifications.tests" -ForegroundColor Gray
Write-Host ""
Write-Host "📚 Documentation:" -ForegroundColor Cyan
Write-Host "- Communication System: COMMUNICATION_SYSTEM.md" -ForegroundColor White
Write-Host "- Implementation Summary: COMMUNICATION_IMPLEMENTATION_SUMMARY.md" -ForegroundColor White
Write-Host "- API Features: API_FEATURES.md" -ForegroundColor White
Write-Host ""
Write-Host "✅ Communication system is ready for use!" -ForegroundColor Green
