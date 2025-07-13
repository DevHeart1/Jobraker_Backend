#!/usr/bin/env powershell

# Jobraker Backend - Celery Worker Startup Script
# This script starts Celery workers for background task processing

Write-Host "🚀 Starting Jobraker Celery Workers..." -ForegroundColor Green

# Set environment
$env:DJANGO_SETTINGS_MODULE = "jobraker.settings"

# Check if Redis is available
Write-Host "📡 Checking Redis connection..." -ForegroundColor Yellow
try {
    $redisTest = redis-cli ping 2>$null
    if ($redisTest -eq "PONG") {
        Write-Host "✅ Redis is available" -ForegroundColor Green
        $env:CELERY_TASK_ALWAYS_EAGER = "False"
    } else {
        throw "Redis not responding"
    }
} catch {
    Write-Host "⚠️ Redis not available - using eager execution" -ForegroundColor Yellow
    $env:CELERY_TASK_ALWAYS_EAGER = "True"
}

# Start Celery worker
Write-Host "🔄 Starting Celery worker..." -ForegroundColor Cyan
& celery -A jobraker worker --loglevel=info --pool=solo

Write-Host "✅ Celery worker started successfully!" -ForegroundColor Green
