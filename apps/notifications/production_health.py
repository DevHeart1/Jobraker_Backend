"""
Enhanced production health checks and monitoring.
"""

import logging
import os
import time
from datetime import datetime, timedelta

import psutil
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.notifications.health_checks import (check_celery, check_database,
                                              check_email_service, check_redis,
                                              check_templates, check_websocket)

logger = logging.getLogger(__name__)
User = get_user_model()


@require_http_methods(["GET"])
def production_health_check(request):
    """
    Comprehensive production health check with system metrics.
    """
    start_time = time.time()

    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "system": "jobraker-production",
        "version": getattr(settings, "RELEASE_VERSION", "1.0.0"),
        "environment": "production",
        "checks": {},
        "metrics": {},
        "performance": {},
    }

    overall_healthy = True

    # Core service checks
    core_checks = {
        "database": check_database,
        "redis": check_redis,
        "email": check_email_service,
        "celery": check_celery,
        "websocket": check_websocket,
        "templates": check_templates,
    }

    for check_name, check_func in core_checks.items():
        try:
            result = check_func()
            health_status["checks"][check_name] = result
            if not result.get("healthy", False):
                overall_healthy = False
        except Exception as e:
            health_status["checks"][check_name] = {
                "healthy": False,
                "status": f"Check failed: {str(e)}",
            }
            overall_healthy = False

    # System metrics
    try:
        health_status["metrics"] = get_system_metrics()
    except Exception as e:
        logger.error(f"Failed to collect system metrics: {e}")
        health_status["metrics"] = {"error": str(e)}

    # Performance metrics
    try:
        health_status["performance"] = get_performance_metrics()
    except Exception as e:
        logger.error(f"Failed to collect performance metrics: {e}")
        health_status["performance"] = {"error": str(e)}

    # Additional production checks
    try:
        production_checks = check_production_requirements()
        health_status["checks"]["production"] = production_checks
        if not production_checks.get("healthy", False):
            overall_healthy = False
    except Exception as e:
        health_status["checks"]["production"] = {
            "healthy": False,
            "status": f"Production check failed: {str(e)}",
        }
        overall_healthy = False

    # Calculate response time
    response_time = time.time() - start_time
    health_status["response_time_ms"] = round(response_time * 1000, 2)

    health_status["status"] = "healthy" if overall_healthy else "unhealthy"

    return JsonResponse(health_status, status=200 if overall_healthy else 503)


def get_system_metrics():
    """Get system resource metrics."""
    return {
        "cpu": {
            "usage_percent": psutil.cpu_percent(interval=1),
            "count": psutil.cpu_count(),
            "load_average": os.getloadavg() if hasattr(os, "getloadavg") else None,
        },
        "memory": {
            "total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
            "available_gb": round(psutil.virtual_memory().available / (1024**3), 2),
            "usage_percent": psutil.virtual_memory().percent,
        },
        "disk": {
            "total_gb": round(psutil.disk_usage("/").total / (1024**3), 2),
            "free_gb": round(psutil.disk_usage("/").free / (1024**3), 2),
            "usage_percent": psutil.disk_usage("/").percent,
        },
        "network": {
            "bytes_sent": psutil.net_io_counters().bytes_sent,
            "bytes_recv": psutil.net_io_counters().bytes_recv,
        },
    }


def get_performance_metrics():
    """Get application performance metrics."""
    # Database query performance
    db_start = time.time()
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    db_time = (time.time() - db_start) * 1000

    # Cache performance
    cache_start = time.time()
    cache.set("health_check", "test", 60)
    cache.get("health_check")
    cache_time = (time.time() - cache_start) * 1000

    return {
        "database_response_ms": round(db_time, 2),
        "cache_response_ms": round(cache_time, 2),
        "active_connections": len(connection.queries) if settings.DEBUG else "N/A",
    }


def check_production_requirements():
    """Check production-specific requirements."""
    issues = []

    # Check DEBUG setting
    if getattr(settings, "DEBUG", True):
        issues.append("DEBUG is True in production")

    # Check SECRET_KEY
    if (
        not getattr(settings, "SECRET_KEY", None)
        or settings.SECRET_KEY == "dev-secret-key-please-change-in-production"
    ):
        issues.append("SECRET_KEY not properly configured")

    # Check ALLOWED_HOSTS
    if not getattr(settings, "ALLOWED_HOSTS", None):
        issues.append("ALLOWED_HOSTS not configured")

    # Check HTTPS settings
    if not getattr(settings, "SECURE_SSL_REDIRECT", False):
        issues.append("HTTPS redirect not enabled")

    # Check static files
    static_root = getattr(settings, "STATIC_ROOT", None)
    if not static_root or not os.path.exists(static_root):
        issues.append("Static files not collected")

    # Check log directory
    log_dir = os.path.join(settings.BASE_DIR, "logs")
    if not os.path.exists(log_dir):
        issues.append("Log directory does not exist")

    return {
        "healthy": len(issues) == 0,
        "status": (
            "All production requirements met"
            if len(issues) == 0
            else f"{len(issues)} issues found"
        ),
        "issues": issues,
    }


@require_http_methods(["GET"])
def production_metrics(request):
    """
    Detailed production metrics endpoint.
    """
    try:
        last_24h = datetime.now() - timedelta(hours=24)

        metrics = {
            "timestamp": datetime.now().isoformat(),
            "system": get_system_metrics(),
            "application": {
                "total_users": User.objects.count(),
                "active_users_24h": (
                    User.objects.filter(last_login__gte=last_24h).count()
                    if hasattr(User, "last_login")
                    else 0
                ),
                "uptime_seconds": get_uptime_seconds(),
            },
            "database": get_database_metrics(),
            "cache": get_cache_metrics(),
            "errors": get_error_metrics(),
        }

        return JsonResponse(metrics)
    except Exception as e:
        logger.error(f"Production metrics failed: {e}")
        return JsonResponse(
            {
                "error": "Failed to collect production metrics",
                "details": str(e),
                "timestamp": datetime.now().isoformat(),
            },
            status=500,
        )


def get_uptime_seconds():
    """Get application uptime in seconds."""
    try:
        boot_time = psutil.boot_time()
        return int(time.time() - boot_time)
    except:
        return None


def get_database_metrics():
    """Get database performance metrics."""
    try:
        with connection.cursor() as cursor:
            # Get database size
            cursor.execute(
                """
                SELECT 
                    pg_size_pretty(pg_database_size(current_database())) as size,
                    (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') as active_connections
            """
            )
            result = cursor.fetchone()

            return {
                "size": result[0] if result else "unknown",
                "active_connections": result[1] if result else 0,
                "total_connections": (
                    connection.queries_limit
                    if hasattr(connection, "queries_limit")
                    else "unknown"
                ),
            }
    except Exception as e:
        return {"error": str(e)}


def get_cache_metrics():
    """Get cache performance metrics."""
    try:
        # Test cache operations
        test_key = f"metrics_test_{int(time.time())}"

        # Write test
        start_time = time.time()
        cache.set(test_key, "test_value", 60)
        write_time = (time.time() - start_time) * 1000

        # Read test
        start_time = time.time()
        cache.get(test_key)
        read_time = (time.time() - start_time) * 1000

        # Cleanup
        cache.delete(test_key)

        return {
            "write_time_ms": round(write_time, 2),
            "read_time_ms": round(read_time, 2),
            "backend": str(cache.__class__.__name__),
        }
    except Exception as e:
        return {"error": str(e)}


def get_error_metrics():
    """Get error metrics from logs."""
    try:
        log_file = os.path.join(settings.BASE_DIR, "logs", "production.log")
        if not os.path.exists(log_file):
            return {"status": "No log file found"}

        # Count recent errors (last hour)
        one_hour_ago = datetime.now() - timedelta(hours=1)
        error_count = 0
        warning_count = 0

        with open(log_file, "r") as f:
            for line in f.readlines()[-1000:]:  # Last 1000 lines
                if "ERROR" in line:
                    error_count += 1
                elif "WARNING" in line:
                    warning_count += 1

        return {
            "errors_last_hour": error_count,
            "warnings_last_hour": warning_count,
            "log_file_size_mb": round(os.path.getsize(log_file) / (1024 * 1024), 2),
        }
    except Exception as e:
        return {"error": str(e)}


@require_http_methods(["POST"])
@csrf_exempt
def production_action(request):
    """
    Production management actions endpoint.
    """
    try:
        import json

        data = json.loads(request.body.decode("utf-8")) if request.body else {}
        action = data.get("action")

        if action == "clear_cache":
            cache.clear()
            return JsonResponse(
                {
                    "success": True,
                    "message": "Cache cleared successfully",
                    "timestamp": datetime.now().isoformat(),
                }
            )

        elif action == "collect_static":
            call_command("collectstatic", "--noinput")
            return JsonResponse(
                {
                    "success": True,
                    "message": "Static files collected successfully",
                    "timestamp": datetime.now().isoformat(),
                }
            )

        elif action == "migrate":
            call_command("migrate", "--noinput")
            return JsonResponse(
                {
                    "success": True,
                    "message": "Database migrations applied successfully",
                    "timestamp": datetime.now().isoformat(),
                }
            )

        else:
            return JsonResponse(
                {
                    "error": "Unknown action",
                    "available_actions": ["clear_cache", "collect_static", "migrate"],
                },
                status=400,
            )

    except Exception as e:
        logger.error(f"Production action failed: {e}")
        return JsonResponse(
            {
                "error": "Action failed",
                "details": str(e),
                "timestamp": datetime.now().isoformat(),
            },
            status=500,
        )
