#!/bin/bash
# Production Deployment Script for Jobraker Backend

set -e

echo "🚀 Jobraker Backend - Production Deployment"
echo "=========================================="

# Configuration
PROJECT_DIR=$(pwd)
VENV_DIR="${PROJECT_DIR}/.venv"
LOG_DIR="${PROJECT_DIR}/logs"
STATIC_DIR="${PROJECT_DIR}/staticfiles"
MEDIA_DIR="${PROJECT_DIR}/media"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check environment
check_environment() {
    log_info "Checking production environment..."
    
    # Check if .env.production exists
    if [ ! -f ".env.production" ]; then
        log_error ".env.production file not found!"
        log_info "Please copy .env.production.template to .env.production and configure it"
        exit 1
    fi
    
    # Load production environment
    export $(grep -v '^#' .env.production | xargs)
    
    # Check required environment variables
    required_vars=(
        "DJANGO_SECRET_KEY"
        "DATABASE_URL"
        "REDIS_URL"
        "DJANGO_ALLOWED_HOSTS"
    )
    
    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            log_error "Required environment variable $var is not set"
            exit 1
        fi
    done
    
    log_success "Environment configuration validated"
}

# Setup directories
setup_directories() {
    log_info "Setting up required directories..."
    
    mkdir -p "$LOG_DIR"
    mkdir -p "$STATIC_DIR"
    mkdir -p "$MEDIA_DIR"
    
    # Set permissions
    chmod 755 "$LOG_DIR"
    chmod 755 "$STATIC_DIR"
    chmod 755 "$MEDIA_DIR"
    
    log_success "Directories created and configured"
}

# Install dependencies
install_dependencies() {
    log_info "Installing Python dependencies..."
    
    # Create virtual environment if it doesn't exist
    if [ ! -d "$VENV_DIR" ]; then
        python3 -m venv "$VENV_DIR"
        log_success "Virtual environment created"
    fi
    
    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install requirements
    pip install -r requirements.txt
    
    log_success "Dependencies installed"
}

# Database setup
setup_database() {
    log_info "Setting up database..."
    
    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    
    # Test database connection
    python manage.py check --database default
    
    # Run migrations
    python manage.py migrate --no-input
    
    # Create superuser if it doesn't exist
    python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(is_superuser=True).exists():
    User.objects.create_superuser(
        email='admin@${COMPANY_NAME:-jobraker}.com',
        password='admin123'  # Change this in production!
    )
    print('Superuser created')
else:
    print('Superuser already exists')
"
    
    log_success "Database setup complete"
}

# Collect static files
collect_static() {
    log_info "Collecting static files..."
    
    source "$VENV_DIR/bin/activate"
    
    # Collect static files
    python manage.py collectstatic --no-input --clear
    
    log_success "Static files collected"
}

# Health check
health_check() {
    log_info "Running health checks..."
    
    source "$VENV_DIR/bin/activate"
    
    # Django system check
    python manage.py check --deploy
    
    # Test email configuration
    python manage.py test_email --test-type welcome || log_warning "Email test failed - check SMTP configuration"
    
    log_success "Health checks completed"
}

# Create systemd service files
create_systemd_services() {
    if [ "$EUID" -ne 0 ]; then
        log_warning "Skipping systemd service creation (requires root). Run with sudo to create services."
        return
    fi
    
    log_info "Creating systemd service files..."
    
    # Django/Gunicorn service
    cat > /etc/systemd/system/jobraker-web.service << EOF
[Unit]
Description=Jobraker Web Application
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
RuntimeDirectory=jobraker
WorkingDirectory=${PROJECT_DIR}
Environment=DJANGO_SETTINGS_MODULE=jobraker.settings.production
EnvironmentFile=${PROJECT_DIR}/.env.production
ExecStart=${VENV_DIR}/bin/gunicorn jobraker.wsgi:application \\
    --bind 0.0.0.0:8000 \\
    --workers 3 \\
    --worker-class gthread \\
    --worker-connections 1000 \\
    --max-requests 1000 \\
    --max-requests-jitter 100 \\
    --timeout 30 \\
    --keep-alive 2 \\
    --log-level info \\
    --access-logfile ${LOG_DIR}/gunicorn-access.log \\
    --error-logfile ${LOG_DIR}/gunicorn-error.log
ExecReload=/bin/kill -s HUP \$MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

    # Celery worker service
    cat > /etc/systemd/system/jobraker-celery.service << EOF
[Unit]
Description=Jobraker Celery Worker
After=network.target redis.service

[Service]
Type=forking
User=www-data
Group=www-data
WorkingDirectory=${PROJECT_DIR}
Environment=DJANGO_SETTINGS_MODULE=jobraker.settings.production
EnvironmentFile=${PROJECT_DIR}/.env.production
ExecStart=${VENV_DIR}/bin/celery -A jobraker worker \\
    --loglevel=info \\
    --logfile=${LOG_DIR}/celery-worker.log \\
    --pidfile=/run/celery/worker.pid \\
    --detach
ExecStop=/bin/kill -TERM \$MAINPID
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    # Celery beat service
    cat > /etc/systemd/system/jobraker-celery-beat.service << EOF
[Unit]
Description=Jobraker Celery Beat Scheduler
After=network.target redis.service

[Service]
Type=forking
User=www-data
Group=www-data
WorkingDirectory=${PROJECT_DIR}
Environment=DJANGO_SETTINGS_MODULE=jobraker.settings.production
EnvironmentFile=${PROJECT_DIR}/.env.production
ExecStart=${VENV_DIR}/bin/celery -A jobraker beat \\
    --loglevel=info \\
    --logfile=${LOG_DIR}/celery-beat.log \\
    --pidfile=/run/celery/beat.pid \\
    --detach
ExecStop=/bin/kill -TERM \$MAINPID
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    # Create runtime directories
    mkdir -p /run/celery
    chown www-data:www-data /run/celery
    
    # Reload systemd
    systemctl daemon-reload
    
    log_success "Systemd services created"
}

# Main deployment function
main() {
    log_info "Starting production deployment..."
    
    check_environment
    setup_directories
    install_dependencies
    setup_database
    collect_static
    health_check
    create_systemd_services
    
    log_success "Production deployment completed!"
    echo ""
    log_info "Next steps:"
    echo "1. Configure your web server (nginx/apache) to proxy to :8000"
    echo "2. Start services: sudo systemctl start jobraker-web jobraker-celery jobraker-celery-beat"
    echo "3. Enable services: sudo systemctl enable jobraker-web jobraker-celery jobraker-celery-beat"
    echo "4. Monitor logs: sudo journalctl -u jobraker-web -f"
    echo ""
    log_info "Health check endpoint: http://your-domain/api/v1/notifications/health/"
}

# Run main function
main "$@"
