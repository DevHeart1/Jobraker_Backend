"""
Health check views for the communication system.
"""

import json
import logging
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.core.mail import get_connection
from django.core.cache import cache
from django.contrib.auth import get_user_model
from celery import current_app as celery_app
from apps.notifications.email_service import EmailService
from apps.chat.models import ChatSession, ChatMessage

logger = logging.getLogger(__name__)
User = get_user_model()


@require_http_methods(["GET"])
def health_check(request):
    """
    Comprehensive health check for the communication system.
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "system": "jobraker-communication",
        "version": "1.0.0",
        "checks": {}
    }
    
    overall_healthy = True
    
    # Check email service
    email_status = check_email_service()
    health_status["checks"]["email"] = email_status
    if not email_status["healthy"]:
        overall_healthy = False
    
    # Check Celery
    celery_status = check_celery()
    health_status["checks"]["celery"] = celery_status
    if not celery_status["healthy"]:
        overall_healthy = False
    
    # Check Redis/Cache
    redis_status = check_redis()
    health_status["checks"]["redis"] = redis_status
    if not redis_status["healthy"]:
        overall_healthy = False
    
    # Check WebSocket/Channels
    websocket_status = check_websocket()
    health_status["checks"]["websocket"] = websocket_status
    if not websocket_status["healthy"]:
        overall_healthy = False
    
    # Check database connectivity
    db_status = check_database()
    health_status["checks"]["database"] = db_status
    if not db_status["healthy"]:
        overall_healthy = False
    
    # Check templates
    templates_status = check_templates()
    health_status["checks"]["templates"] = templates_status
    if not templates_status["healthy"]:
        overall_healthy = False
    
    health_status["status"] = "healthy" if overall_healthy else "unhealthy"
    
    return JsonResponse(
        health_status,
        status=200 if overall_healthy else 503
    )


def check_email_service():
    """Check email service health."""
    try:
        # Test email backend connection
        connection = get_connection()
        connection.open()
        connection.close()
        
        # Test EmailService initialization
        email_service = EmailService()
        
        return {
            "healthy": True,
            "status": "Email service operational",
            "backend": settings.EMAIL_BACKEND,
            "host": getattr(settings, 'EMAIL_HOST', 'console'),
            "port": getattr(settings, 'EMAIL_PORT', 'N/A')
        }
    except Exception as e:
        logger.error(f"Email service health check failed: {str(e)}")
        return {
            "healthy": False,
            "status": f"Email service error: {str(e)}",
            "backend": getattr(settings, 'EMAIL_BACKEND', 'unknown')
        }


def check_celery():
    """Check Celery worker health."""
    try:
        # Check if Celery is configured
        if not hasattr(settings, 'CELERY_BROKER_URL'):
            return {
                "healthy": False,
                "status": "Celery not configured"
            }
        
        # Test Celery worker availability
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        
        if stats:
            active_workers = len(stats)
            return {
                "healthy": True,
                "status": f"Celery operational with {active_workers} worker(s)",
                "workers": list(stats.keys()) if stats else [],
                "broker": settings.CELERY_BROKER_URL
            }
        else:
            return {
                "healthy": False,
                "status": "No Celery workers available",
                "broker": settings.CELERY_BROKER_URL
            }
    except Exception as e:
        logger.error(f"Celery health check failed: {str(e)}")
        return {
            "healthy": False,
            "status": f"Celery error: {str(e)}"
        }


def check_redis():
    """Check Redis/Cache health."""
    try:
        # Test cache connectivity
        test_key = "health_check_test"
        test_value = f"test_{datetime.now().timestamp()}"
        
        cache.set(test_key, test_value, timeout=60)
        retrieved_value = cache.get(test_key)
        cache.delete(test_key)
        
        if retrieved_value == test_value:
            return {
                "healthy": True,
                "status": "Redis/Cache operational",
                "backend": settings.CACHES.get('default', {}).get('BACKEND', 'unknown')
            }
        else:
            return {
                "healthy": False,
                "status": "Redis/Cache read/write test failed"
            }
    except Exception as e:
        logger.error(f"Redis health check failed: {str(e)}")
        return {
            "healthy": False,
            "status": f"Redis error: {str(e)}"
        }


def check_websocket():
    """Check WebSocket/Channels health."""
    try:
        # Check if Channels is configured
        channel_layers = getattr(settings, 'CHANNEL_LAYERS', {})
        
        if not channel_layers:
            return {
                "healthy": False,
                "status": "Django Channels not configured"
            }
        
        # Check channel layer backend
        default_layer = channel_layers.get('default', {})
        backend = default_layer.get('BACKEND', 'unknown')
        
        return {
            "healthy": True,
            "status": "WebSocket/Channels configured",
            "backend": backend,
            "channel_layers": list(channel_layers.keys())
        }
    except Exception as e:
        logger.error(f"WebSocket health check failed: {str(e)}")
        return {
            "healthy": False,
            "status": f"WebSocket error: {str(e)}"
        }


def check_database():
    """Check database connectivity."""
    try:
        # Test basic database operations
        user_count = User.objects.count()
        chat_session_count = ChatSession.objects.count()
        chat_message_count = ChatMessage.objects.count()
        
        return {
            "healthy": True,
            "status": "Database operational",
            "statistics": {
                "users": user_count,
                "chat_sessions": chat_session_count,
                "chat_messages": chat_message_count
            }
        }
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        return {
            "healthy": False,
            "status": f"Database error: {str(e)}"
        }


def check_templates():
    """Check email template availability."""
    try:
        from django.template.loader import get_template
        from django.template import TemplateDoesNotExist
        
        # Check if required templates exist
        required_templates = [
            'emails/welcome.html',
            'emails/job_alert.html',
            'emails/application_status_update.html',
            'emails/job_recommendations.html',
            'emails/application_follow_up.html'
        ]
        
        missing_templates = []
        for template in required_templates:
            try:
                get_template(template)
            except TemplateDoesNotExist:
                missing_templates.append(template)
        
        if missing_templates:
            return {
                "healthy": False,
                "status": f"Missing templates: {', '.join(missing_templates)}",
                "missing_templates": missing_templates
            }
        
        return {
            "healthy": True,
            "status": "All email templates available",
            "templates_checked": required_templates
        }
    except Exception as e:
        logger.error(f"Template health check failed: {str(e)}")
        return {
            "healthy": False,
            "status": f"Template check error: {str(e)}"
        }


@require_http_methods(["GET"])
def metrics(request):
    """
    Communication system metrics endpoint.
    """
    try:
        # Get metrics from the last 24 hours
        last_24h = datetime.now() - timedelta(hours=24)
        
        # Email metrics (would require email tracking table in production)
        metrics_data = {
            "timestamp": datetime.now().isoformat(),
            "period": "last_24_hours",
            "email": {
                "total_sent": 0,  # Would be tracked in production
                "total_failed": 0,
                "templates_used": {
                    "welcome": 0,
                    "job_alert": 0,
                    "application_status": 0,
                    "recommendations": 0,
                    "follow_up": 0
                }
            },
            "chat": {
                "active_sessions": ChatSession.objects.filter(
                    updated_at__gte=last_24h
                ).count(),
                "total_messages": ChatMessage.objects.filter(
                    timestamp__gte=last_24h
                ).count(),
                "unique_users": ChatSession.objects.filter(
                    updated_at__gte=last_24h
                ).values('user').distinct().count()
            },
            "system": {
                "total_users": User.objects.count(),
                "active_users_24h": User.objects.filter(
                    last_login__gte=last_24h
                ).count() if hasattr(User, 'last_login') else 0
            }
        }
        
        return JsonResponse(metrics_data)
    except Exception as e:
        logger.error(f"Metrics endpoint failed: {str(e)}")
        return JsonResponse({
            "error": "Failed to retrieve metrics",
            "details": str(e)
        }, status=500)


@require_http_methods(["POST"])
@csrf_exempt
def test_endpoint(request):
    """
    Test endpoint for communication system components.
    """
    try:
        # Handle JSON parsing more safely
        if request.body:
            try:
                data = json.loads(request.body.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = {}
        else:
            data = {}
            
        test_type = data.get('test_type', 'all')
        
        results = {}
        
        if test_type in ['all', 'email']:
            # Test email sending
            try:
                email_service = EmailService()
                test_result = email_service.send_test_email("test@example.com")
                results['email'] = {
                    "success": test_result,
                    "message": "Test email sent successfully" if test_result else "Email test failed"
                }
            except Exception as e:
                results['email'] = {
                    "success": False,
                    "message": f"Email test error: {str(e)}"
                }
        
        if test_type in ['all', 'cache']:
            # Test cache operations
            try:
                test_key = f"test_{datetime.now().timestamp()}"
                cache.set(test_key, "test_value", timeout=60)
                retrieved = cache.get(test_key)
                cache.delete(test_key)
                
                results['cache'] = {
                    "success": retrieved == "test_value",
                    "message": "Cache test successful" if retrieved == "test_value" else "Cache test failed"
                }
            except Exception as e:
                results['cache'] = {
                    "success": False,
                    "message": f"Cache test error: {str(e)}"
                }
        
        return JsonResponse({
            "test_results": results,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Test endpoint failed: {str(e)}")
        return JsonResponse({
            "error": "Test execution failed",
            "details": str(e)
        }, status=500)
