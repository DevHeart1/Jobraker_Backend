# PowerShell Setup Script for Jobraker Background Tasks
# =====================================================

Write-Host "🚀 Jobraker Background Task Setup (Windows)" -ForegroundColor Green
Write-Host "=" * 50

# Function to check if a command exists
function Test-Command {
    param($Command)
    try {
        if (Get-Command $Command -ErrorAction Stop) {
            return $true
        }
    }
    catch {
        return $false
    }
}

# Check system requirements
Write-Host "`n📋 Checking System Requirements..." -ForegroundColor Yellow

# Check Python
if (Test-Command python) {
    $pythonVersion = python --version
    Write-Host "  ✅ Python: $pythonVersion" -ForegroundColor Green
} else {
    Write-Host "  ❌ Python: Not found" -ForegroundColor Red
    exit 1
}

# Check Redis
if (Test-Command redis-server) {
    Write-Host "  ✅ Redis: Available" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  Redis: Not found - Install Redis for Windows or use Docker" -ForegroundColor Yellow
}

# Check if we're in the right directory
if (Test-Path "manage.py") {
    Write-Host "  ✅ Django Project: Found" -ForegroundColor Green
} else {
    Write-Host "  ❌ Django Project: manage.py not found" -ForegroundColor Red
    exit 1
}

# Install dependencies
Write-Host "`n📦 Installing Dependencies..." -ForegroundColor Yellow
try {
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    Write-Host "  ✅ Dependencies installed" -ForegroundColor Green
} catch {
    Write-Host "  ❌ Failed to install dependencies: $_" -ForegroundColor Red
}

# Run database migrations
Write-Host "`n📊 Setting up Database..." -ForegroundColor Yellow
try {
    python manage.py migrate
    Write-Host "  ✅ Database migrations completed" -ForegroundColor Green
} catch {
    Write-Host "  ❌ Database migration failed: $_" -ForegroundColor Red
}

# Test Django setup
Write-Host "`n🔧 Testing Django Setup..." -ForegroundColor Yellow
try {
    python manage.py check
    Write-Host "  ✅ Django system check passed" -ForegroundColor Green
} catch {
    Write-Host "  ❌ Django system check failed: $_" -ForegroundColor Red
}

# Test background tasks
Write-Host "`n⚙️ Testing Background Tasks..." -ForegroundColor Yellow
try {
    python manage.py test_background_tasks --test-type=health --dry-run
    Write-Host "  ✅ Background task tests completed" -ForegroundColor Green
} catch {
    Write-Host "  ⚠️  Background task test failed: $_" -ForegroundColor Yellow
}

# Create startup scripts
Write-Host "`n📝 Creating Startup Scripts..." -ForegroundColor Yellow

# Celery worker script
$workerScript = @"
@echo off
echo Starting Jobraker Celery Worker...
echo Press Ctrl+C to stop

cd /d "%~dp0"
python -m celery -A jobraker worker --loglevel=info --pool=solo
pause
"@

$workerScript | Out-File -FilePath "start_celery_worker.bat" -Encoding ASCII
Write-Host "  ✅ Created start_celery_worker.bat" -ForegroundColor Green

# Celery beat script
$beatScript = @"
@echo off
echo Starting Jobraker Celery Beat Scheduler...
echo Press Ctrl+C to stop

cd /d "%~dp0"
python -m celery -A jobraker beat --loglevel=info
pause
"@

$beatScript | Out-File -FilePath "start_celery_beat.bat" -Encoding ASCII
Write-Host "  ✅ Created start_celery_beat.bat" -ForegroundColor Green

# Django development server script
$djangoScript = @"
@echo off
echo Starting Jobraker Django Development Server...
echo Press Ctrl+C to stop

cd /d "%~dp0"
python manage.py runserver 0.0.0.0:8000
pause
"@

$djangoScript | Out-File -FilePath "start_django_server.bat" -Encoding ASCII
Write-Host "  ✅ Created start_django_server.bat" -ForegroundColor Green

# All-in-one startup script
$allScript = @"
@echo off
echo Starting All Jobraker Services...
echo.

echo Starting Redis Server (if available)...
start "Redis Server" redis-server

timeout /t 3 /nobreak > nul

echo Starting Celery Worker...
start "Celery Worker" cmd /k "cd /d "%~dp0" && python -m celery -A jobraker worker --loglevel=info --pool=solo"

timeout /t 3 /nobreak > nul

echo Starting Celery Beat...
start "Celery Beat" cmd /k "cd /d "%~dp0" && python -m celery -A jobraker beat --loglevel=info"

timeout /t 3 /nobreak > nul

echo Starting Django Server...
start "Django Server" cmd /k "cd /d "%~dp0" && python manage.py runserver 0.0.0.0:8000"

echo.
echo All services started in separate windows.
echo Close this window or press any key to exit.
pause > nul
"@

$allScript | Out-File -FilePath "start_all_services.bat" -Encoding ASCII
Write-Host "  ✅ Created start_all_services.bat" -ForegroundColor Green

# Test script
$testScript = @"
@echo off
echo Testing Jobraker Background Tasks...
echo.

cd /d "%~dp0"

echo Testing system health...
python manage.py test_background_tasks --test-type=health

echo.
echo Testing job processing...
python manage.py test_background_tasks --test-type=jobs --dry-run

echo.
echo Testing AI processing...
python manage.py test_background_tasks --test-type=ai --dry-run

echo.
echo Testing notifications...
python manage.py test_background_tasks --test-type=notifications --dry-run

echo.
echo Testing completed. Press any key to exit.
pause > nul
"@

$testScript | Out-File -FilePath "test_background_tasks.bat" -Encoding ASCII
Write-Host "  ✅ Created test_background_tasks.bat" -ForegroundColor Green

# Show final status
Write-Host "`n🎉 Setup Completed!" -ForegroundColor Green
Write-Host "=" * 50

Write-Host "`n📋 Next Steps:" -ForegroundColor Yellow
Write-Host "1. Start Redis server (if not running):" -ForegroundColor White
Write-Host "   - Install Redis for Windows or use Docker" -ForegroundColor Gray
Write-Host "   - Or use: docker run -d -p 6379:6379 redis:alpine" -ForegroundColor Gray

Write-Host "`n2. Configure environment variables in .env file:" -ForegroundColor White
Write-Host "   - REDIS_URL=redis://localhost:6379/0" -ForegroundColor Gray
Write-Host "   - CELERY_BROKER_URL=redis://localhost:6379/0" -ForegroundColor Gray
Write-Host "   - ADZUNA_API_KEY=your_adzuna_key" -ForegroundColor Gray
Write-Host "   - SKYVERN_API_KEY=your_skyvern_key" -ForegroundColor Gray
Write-Host "   - OPENAI_API_KEY=your_openai_key" -ForegroundColor Gray

Write-Host "`n3. Start services using the created batch files:" -ForegroundColor White
Write-Host "   - start_all_services.bat (starts everything)" -ForegroundColor Gray
Write-Host "   - Or start individually with:" -ForegroundColor Gray
Write-Host "     • start_celery_worker.bat" -ForegroundColor Gray
Write-Host "     • start_celery_beat.bat" -ForegroundColor Gray
Write-Host "     • start_django_server.bat" -ForegroundColor Gray

Write-Host "`n4. Test the setup:" -ForegroundColor White
Write-Host "   - test_background_tasks.bat" -ForegroundColor Gray
Write-Host "   - Or: python manage.py test_background_tasks" -ForegroundColor Gray

Write-Host "`n5. Monitor system health:" -ForegroundColor White
Write-Host "   - Visit: http://localhost:8000/api/v1/notifications/health/" -ForegroundColor Gray
Write-Host "   - Check logs in terminal windows" -ForegroundColor Gray

Write-Host "`n🚀 Background task processing is now ready!" -ForegroundColor Green
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
