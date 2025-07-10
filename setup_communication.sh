#!/bin/bash
# Communication System Setup Script for Jobraker Backend

echo "🚀 Setting up Jobraker Communication System..."

# Check if virtual environment is activated
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "⚠️  Warning: No virtual environment detected. Please activate your virtual environment first."
    echo "   Run: python -m venv venv && source venv/bin/activate"
    exit 1
fi

# Install required dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Check if Redis is running
echo "🔴 Checking Redis connection..."
python -c "
import redis
try:
    r = redis.Redis(host='localhost', port=6379, db=0)
    r.ping()
    print('✅ Redis is running and accessible')
except Exception as e:
    print('❌ Redis connection failed:', e)
    print('   Please install and start Redis:')
    print('   - Windows: Download from https://redis.io/download')
    print('   - macOS: brew install redis && brew services start redis')
    print('   - Linux: sudo apt-get install redis-server && sudo systemctl start redis')
    exit(1)
"

# Check database configuration
echo "🗄️  Checking database configuration..."
python manage.py check --database default

# Run migrations
echo "🔄 Running database migrations..."
python manage.py migrate

# Create static directory if it doesn't exist
echo "📁 Creating static directory..."
mkdir -p static

# Test email configuration
echo "📧 Testing email configuration..."
python manage.py shell -c "
from django.core.mail import send_mail
from django.conf import settings
print(f'Email backend: {settings.EMAIL_BACKEND}')
print(f'Email host: {settings.EMAIL_HOST}')
print('✅ Email configuration loaded successfully')
"

# Test WebSocket configuration
echo "🔌 Testing WebSocket configuration..."
python manage.py shell -c "
from channels.layers import get_channel_layer
layer = get_channel_layer()
print(f'Channel layer: {layer.__class__.__name__}')
print('✅ WebSocket configuration loaded successfully')
"

# Test Celery configuration
echo "⚙️  Testing Celery configuration..."
python manage.py shell -c "
from celery import current_app
print(f'Celery broker: {current_app.conf.broker_url}')
print(f'Celery backend: {current_app.conf.result_backend}')
print('✅ Celery configuration loaded successfully')
"

# Create superuser if none exists
echo "👤 Checking for superuser..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(is_superuser=True).exists():
    print('❌ No superuser found. Please create one:')
    print('   Run: python manage.py createsuperuser')
else:
    print('✅ Superuser exists')
"

echo ""
echo "🎉 Communication System Setup Complete!"
echo ""
echo "📋 Next Steps:"
echo "1. Start Redis (if not already running):"
echo "   redis-server"
echo ""
echo "2. Start Celery worker (in a new terminal):"
echo "   celery -A jobraker worker --loglevel=info"
echo ""
echo "3. Start Celery beat scheduler (in a new terminal):"
echo "   celery -A jobraker beat --loglevel=info"
echo ""
echo "4. Start Django development server:"
echo "   python manage.py runserver"
echo ""
echo "5. For WebSocket support, use Daphne instead:"
echo "   daphne jobraker.asgi:application"
echo ""
echo "📧 Email Features:"
echo "- Welcome emails for new users"
echo "- Job alert notifications"
echo "- Application status updates"
echo "- Job recommendations"
echo "- Password reset emails"
echo ""
echo "🔌 WebSocket Features:"
echo "- Real-time chat with AI assistant"
echo "- Real-time notifications"
echo "- Typing indicators"
echo "- Message persistence"
echo ""
echo "🧪 Test Commands:"
echo "- Test email: python manage.py test_email --test-type all"
echo "- Check system: python manage.py check"
echo "- Run tests: python manage.py test apps.notifications.tests"
echo ""
echo "📚 Documentation:"
echo "- Communication System: COMMUNICATION_SYSTEM.md"
echo "- Implementation Summary: COMMUNICATION_IMPLEMENTATION_SUMMARY.md"
echo "- API Features: API_FEATURES.md"
echo ""
echo "✅ Communication system is ready for use!"
