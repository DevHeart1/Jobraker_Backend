"""
Health check views for monitoring the communication system.
"""

import logging
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model
from celery import current_app
from apps.notifications.email_service import EmailService
from apps.notifications.tasks import send_welcome_email_task
import redis
import json

logger = logging.getLogger(__name__)
User = get_user_model()


@require_http_methods(["GET"])
def communication_health_check(request):
    """
    Comprehensive health check for the communication system.
    
    Returns the status of:
    - Email service
    - Redis connection
    - Celery workers
    - WebSocket support
    - Database connectivity
    """
    health_status = {
        "timestamp": timezone.now().isoformat(),
        "overall_status": "healthy",
        "services": {}
    }
    
    # Check Email Service
    try:
        email_service = EmailService()
        health_status["services"]["email"] = {
            "status": "healthy",
            "backend": settings.EMAIL_BACKEND,
            "host": getattr(settings, 'EMAIL_HOST', 'console'),
            "port": getattr(settings, 'EMAIL_PORT', 'N/A'),
            "use_tls": getattr(settings, 'EMAIL_USE_TLS', False),
        }
    except Exception as e:
        health_status["services"]["email"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["overall_status"] = "degraded"
    
    # Check Redis Connection
    try:
        redis_client = redis.from_url(settings.REDIS_URL)
        redis_client.ping()
        redis_info = redis_client.info()
        health_status["services"]["redis"] = {
            "status": "healthy",
            "version": redis_info.get("redis_version"),
            "connected_clients": redis_info.get("connected_clients"),
            "used_memory_human": redis_info.get("used_memory_human"),
        }
    except Exception as e:
        health_status["services"]["redis"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["overall_status"] = "degraded"
    
    # Check Celery Workers
    try:
        celery_inspect = current_app.control.inspect()
        active_workers = celery_inspect.active()
        registered_tasks = celery_inspect.registered()
        
        if active_workers:
            worker_count = len(active_workers.keys())
            health_status["services"]["celery"] = {
                "status": "healthy",
                "active_workers": worker_count,
                "worker_names": list(active_workers.keys()),
                "task_count": sum(len(tasks) for tasks in active_workers.values()),
            }
        else:
            health_status["services"]["celery"] = {
                "status": "warning",
                "message": "No active workers found",
                "active_workers": 0,
            }
            if health_status["overall_status"] == "healthy":
                health_status["overall_status"] = "degraded"
    except Exception as e:
        health_status["services"]["celery"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["overall_status"] = "degraded"
    
    # Check WebSocket Support (Django Channels)
    try:
        # Check if channels is installed and configured
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        
        if channel_layer:
            health_status["services"]["websocket"] = {
                "status": "healthy",
                "channel_layer": str(type(channel_layer)),
                "backend": getattr(channel_layer, 'hosts', ['redis']),
            }
        else:
            health_status["services"]["websocket"] = {
                "status": "warning",
                "message": "Channel layer not configured"
            }
    except Exception as e:
        health_status["services"]["websocket"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["overall_status"] = "degraded"
    
    # Check Database Connectivity
    try:
        user_count = User.objects.count()
        health_status["services"]["database"] = {
            "status": "healthy",
            "user_count": user_count,
            "connection": "active"
        }
    except Exception as e:
        health_status["services"]["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["overall_status"] = "unhealthy"
    
    # Check Email Templates
    try:
        from django.template.loader import get_template
        templates = [
            'emails/welcome.html',
            'emails/job_alert.html',
            'emails/job_recommendations.html',
            'emails/application_status.html',
        ]
        
        template_status = {}
        for template in templates:
            try:
                get_template(template)
                template_status[template] = "found"
            except Exception:
                template_status[template] = "missing"
        
        health_status["services"]["email_templates"] = {
            "status": "healthy" if all(status == "found" for status in template_status.values()) else "warning",
            "templates": template_status
        }
    except Exception as e:
        health_status["services"]["email_templates"] = {
            "status": "unhealthy",
            "error": str(e)
        }
    
    # Add system information
    health_status["system_info"] = {
        "django_version": getattr(settings, 'DJANGO_VERSION', 'unknown'),
        "debug_mode": settings.DEBUG,
        "environment": getattr(settings, 'ENVIRONMENT', 'development'),
        "timezone": str(settings.TIME_ZONE),
    }
    
    # Set HTTP status code based on overall health
    status_code = 200
    if health_status["overall_status"] == "degraded":
        status_code = 206  # Partial Content
    elif health_status["overall_status"] == "unhealthy":
        status_code = 503  # Service Unavailable
    
    return JsonResponse(health_status, status=status_code)


@require_http_methods(["POST"])
@csrf_exempt
def test_email_endpoint(request):
    """
    Test email sending endpoint for monitoring and debugging.
    """
    try:
        data = json.loads(request.body) if request.body else {}
        email = data.get('email', 'test@example.com')
        email_type = data.get('type', 'welcome')
        
        # Send test email
        email_service = EmailService()
        
        if email_type == 'welcome':
            context = {
                'user_email': email,
                'site_url': settings.SITE_URL,
                'company_name': settings.COMPANY_NAME,
            }
            result = email_service.send_email(
                template_name='welcome',
                context=context,
                to_email=email,
                subject='Welcome to Jobraker!'
            )
        else:
            return JsonResponse({
                'status': 'error',
                'message': f'Unsupported email type: {email_type}'
            }, status=400)
        
        return JsonResponse({
            'status': 'success',
            'message': f'Test email sent successfully to {email}',
            'email_type': email_type,
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Test email failed: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=500)


@require_http_methods(["GET"])
def communication_metrics(request):
    """
    Get communication system metrics and statistics.
    """
    try:
        # Calculate date ranges
        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)
        
        metrics = {
            "timestamp": now.isoformat(),
            "email_stats": {
                "total_users": User.objects.count(),
                "active_users_24h": User.objects.filter(last_login__gte=last_24h).count(),
                "new_users_7d": User.objects.filter(date_joined__gte=last_7d).count(),
            },
            "system_uptime": {
                "status": "operational",
                "last_checked": now.isoformat(),
            }
        }
        
        # Add Celery task statistics if available
        try:
            celery_inspect = current_app.control.inspect()
            stats = celery_inspect.stats()
            if stats:
                worker_stats = list(stats.values())[0] if stats else {}
                metrics["celery_stats"] = {
                    "total_tasks": worker_stats.get('total', 0),
                    "pool_processes": worker_stats.get('pool', {}).get('processes', 0),
                }
        except Exception:
            metrics["celery_stats"] = {"status": "unavailable"}
        
        return JsonResponse(metrics)
        
    except Exception as e:
        logger.error(f"Metrics collection failed: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=500)
