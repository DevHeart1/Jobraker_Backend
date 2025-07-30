"""
System status and health check endpoints.
"""

import logging

import redis
from django.core.cache import cache
from django.db import connection
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

logger = logging.getLogger(__name__)


@extend_schema(
    summary="System health check",
    description="Check the health status of various system components",
    responses={
        200: OpenApiExample(
            "Health Check Response",
            value={
                "status": "healthy",
                "database": "connected",
                "redis": "connected",
                "celery": "running",
                "ai_services": "configured",
                "recommendations": {
                    "total_jobs": 1234,
                    "total_users": 567,
                    "total_recommendations": 2345,
                },
            },
        )
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def health_check(request):
    """
    Check the health status of the system.
    """
    health_status = {
        "status": "healthy",
        "database": "unknown",
        "redis": "unknown",
        "celery": "unknown",
        "ai_services": "unknown",
        "recommendations": {},
    }

    # Check database connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        health_status["database"] = "connected"
    except Exception as e:
        health_status["database"] = f"error: {str(e)}"
        health_status["status"] = "degraded"

    # Check Redis connection
    try:
        cache.set("health_check", "test", 10)
        test_val = cache.get("health_check")
        if test_val == "test":
            health_status["redis"] = "connected"
        else:
            health_status["redis"] = "error: cache test failed"
    except Exception as e:
        health_status["redis"] = f"error: {str(e)}"
        health_status["status"] = "degraded"

    # Check AI services configuration
    try:
        from django.conf import settings

        if hasattr(settings, "OPENAI_API_KEY") and settings.OPENAI_API_KEY:
            health_status["ai_services"] = "configured"
        else:
            health_status["ai_services"] = "not configured"
    except Exception as e:
        health_status["ai_services"] = f"error: {str(e)}"

    # Get recommendation statistics
    try:
        from apps.accounts.models import User
        from apps.jobs.models import Job, RecommendedJob

        health_status["recommendations"] = {
            "total_jobs": Job.objects.count(),
            "total_users": User.objects.count(),
            "total_recommendations": RecommendedJob.objects.count(),
        }
    except Exception as e:
        health_status["recommendations"] = f"error: {str(e)}"

    return Response(health_status)


@extend_schema(
    summary="User recommendations status",
    description="Get the current user's recommendation statistics",
    responses={
        200: OpenApiExample(
            "User Recommendations Status",
            value={
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "profile_configured": True,
                "recommendations_count": 12,
                "last_updated": "2025-07-08T10:00:00Z",
                "pending_recommendations": 5,
                "viewed_recommendations": 7,
            },
        )
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def user_recommendations_status(request):
    """
    Get the current user's recommendation status.
    """
    user = request.user

    try:
        from apps.accounts.models import UserProfile
        from apps.jobs.models import RecommendedJob

        # Check if user has a profile configured
        profile_configured = hasattr(user, "profile") and user.profile.is_complete

        # Get recommendation statistics
        recommendations = RecommendedJob.objects.filter(user=user)

        status_data = {
            "user_id": str(user.id),
            "profile_configured": profile_configured,
            "recommendations_count": recommendations.count(),
            "pending_recommendations": recommendations.filter(
                status="pending_review"
            ).count(),
            "viewed_recommendations": recommendations.filter(status="viewed").count(),
            "dismissed_recommendations": recommendations.filter(
                status="dismissed"
            ).count(),
        }

        # Get last updated timestamp
        latest_rec = recommendations.order_by("-recommended_at").first()
        if latest_rec:
            status_data["last_updated"] = latest_rec.recommended_at

        return Response(status_data)

    except Exception as e:
        logger.error(f"Error getting user recommendations status: {e}")
        return Response(
            {"error": "Failed to get recommendations status"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
