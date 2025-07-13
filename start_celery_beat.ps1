#!/usr/bin/env powershell

# Jobraker Backend - Celery Beat Scheduler Startup Script
# This script starts Celery Beat for scheduled tasks

Write-Host "⏰ Starting Jobraker Celery Beat Scheduler..." -ForegroundColor Green

# Set environment
$env:DJANGO_SETTINGS_MODULE = "jobraker.settings"

# Start Celery beat
Write-Host "📅 Starting Celery beat scheduler..." -ForegroundColor Cyan
& celery -A jobraker beat --loglevel=info

Write-Host "✅ Celery beat scheduler started!" -ForegroundColor Green
