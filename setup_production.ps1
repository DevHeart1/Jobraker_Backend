# PowerShell Production Setup Script for Jobraker Backend
# Run as Administrator for full setup

param(
    [switch]$SkipDependencies,
    [switch]$SetupDatabase,
    [switch]$ConfigureServices
)

Write-Host "🚀 Starting Jobraker Backend Production Setup (Windows)" -ForegroundColor Green

# Check if running as administrator
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Error "This script requires Administrator privileges. Please run PowerShell as Administrator."
    exit 1
}

# Load environment variables from .env.production
if (-not (Test-Path ".env.production")) {
    Write-Error ".env.production file not found! Please copy .env.production template and configure it."
    exit 1
}

Write-Host "Loading production environment variables..." -ForegroundColor Yellow
Get-Content ".env.production" | Where-Object { $_ -notmatch '^#' -and $_ -match '=' } | ForEach-Object {
    $parts = $_ -split '=', 2
    if ($parts.Length -eq 2) {
        [Environment]::SetEnvironmentVariable($parts[0], $parts[1], "Process")
    }
}

# Install Python dependencies
if (-not $SkipDependencies) {
    Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
    pip install -r requirements.txt
    pip install gunicorn psycopg2-binary redis uvicorn[standard] daphne
}

# PostgreSQL setup (requires manual installation)
if ($SetupDatabase) {
    Write-Host "Setting up PostgreSQL database..." -ForegroundColor Yellow
    Write-Host "Please ensure PostgreSQL is installed and running." -ForegroundColor Cyan
    
    $dbName = $env:DB_NAME
    $dbUser = $env:DB_USER
    $dbPassword = $env:DB_PASSWORD
    
    # Create database and user (you'll need to run these manually in psql)
    $sqlCommands = @"
CREATE DATABASE $dbName;
CREATE USER $dbUser WITH PASSWORD '$dbPassword';
GRANT ALL PRIVILEGES ON DATABASE $dbName TO $dbUser;
ALTER USER $dbUser CREATEDB;
\c $dbName
CREATE EXTENSION IF NOT EXISTS vector;
"@
    
    Write-Host "Please run the following SQL commands in PostgreSQL:" -ForegroundColor Cyan
    Write-Host $sqlCommands -ForegroundColor White
}

# Django setup
Write-Host "Setting up Django application..." -ForegroundColor Yellow
$env:DJANGO_SETTINGS_MODULE = "jobraker.settings.production"

python manage.py collectstatic --noinput
python manage.py migrate

# Create superuser
Write-Host "Creating superuser..." -ForegroundColor Yellow
$createSuperuserScript = @"
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(email='admin@example.com').exists():
    User.objects.create_superuser('admin@example.com', 'admin123', first_name='Admin', last_name='User')
    print('Superuser created: admin@example.com / admin123')
else:
    print('Superuser already exists')
"@

echo $createSuperuserScript | python manage.py shell

# Windows Services setup
if ($ConfigureServices) {
    Write-Host "Setting up Windows Services..." -ForegroundColor Yellow
    
    # Create service scripts
    $startDjangoScript = @"
@echo off
cd /d "$PWD"
set DJANGO_SETTINGS_MODULE=jobraker.settings.production
daphne -b 0.0.0.0 -p 8000 jobraker.asgi:application
"@
    
    $startCeleryWorkerScript = @"
@echo off
cd /d "$PWD"
set DJANGO_SETTINGS_MODULE=jobraker.settings.production
celery -A jobraker worker -l info
"@
    
    $startCeleryBeatScript = @"
@echo off
cd /d "$PWD"
set DJANGO_SETTINGS_MODULE=jobraker.settings.production
celery -A jobraker beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
"@
    
    # Save scripts
    $startDjangoScript | Out-File -FilePath "start_django_prod.bat" -Encoding ASCII
    $startCeleryWorkerScript | Out-File -FilePath "start_celery_worker_prod.bat" -Encoding ASCII
    $startCeleryBeatScript | Out-File -FilePath "start_celery_beat_prod.bat" -Encoding ASCII
    
    Write-Host "Created production service scripts:" -ForegroundColor Green
    Write-Host "- start_django_prod.bat" -ForegroundColor White
    Write-Host "- start_celery_worker_prod.bat" -ForegroundColor White
    Write-Host "- start_celery_beat_prod.bat" -ForegroundColor White
}

# Create IIS configuration (optional)
$webConfig = @"
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <system.webServer>
    <handlers>
      <add name="PythonHandler" path="*" verb="*" modules="httpPlatformHandler" resourceType="Unspecified"/>
    </handlers>
    <httpPlatform processPath="$PWD\venv\Scripts\python.exe"
                  arguments="$PWD\manage.py runserver 127.0.0.1:8000"
                  stdoutLogEnabled="true"
                  stdoutLogFile="$PWD\logs\stdout.log"
                  startupTimeLimit="60"
                  requestTimeout="00:04:00">
      <environmentVariables>
        <environmentVariable name="DJANGO_SETTINGS_MODULE" value="jobraker.settings.production" />
      </environmentVariables>
    </httpPlatform>
  </system.webServer>
</configuration>
"@

$webConfig | Out-File -FilePath "web.config" -Encoding UTF8

Write-Host "✅ Production setup completed!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Ensure PostgreSQL and Redis are running" -ForegroundColor White
Write-Host "2. Update .env.production with your actual API keys" -ForegroundColor White
Write-Host "3. Run the service scripts to start the application:" -ForegroundColor White
Write-Host "   - start_django_prod.bat (Django with WebSocket support)" -ForegroundColor White
Write-Host "   - start_celery_worker_prod.bat (Background tasks)" -ForegroundColor White
Write-Host "   - start_celery_beat_prod.bat (Scheduled tasks)" -ForegroundColor White
Write-Host "4. Configure your web server (IIS/nginx) to proxy to port 8000" -ForegroundColor White
Write-Host ""
Write-Host "Default superuser: admin@example.com / admin123" -ForegroundColor Yellow
Write-Host "Application will be available at: http://localhost:8000" -ForegroundColor Green
