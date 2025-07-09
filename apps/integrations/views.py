from django.shortcuts import render
from django.conf import settings
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.openapi import OpenApiTypes
import logging

logger = logging.getLogger(__name__)


@extend_schema(
    summary="Handle external webhooks",
    description="Process incoming webhooks from external job services and automation platforms",
    tags=['Integrations'],
    parameters=[
        OpenApiParameter(
            name='service',
            description='Service name (adzuna, skyvern, etc.)',
            required=True,
            type=OpenApiTypes.STR,
            location=OpenApiParameter.PATH
        )
    ],
    request=OpenApiExample(
        'Webhook Payload',
        summary='Example webhook data',
        description='Webhook payload from external service',
        value={
            "event": "job_created",
            "data": {
                "job_id": "ext_123",
                "title": "Software Engineer",
                "company": "TechCorp"
            },
            "timestamp": "2025-06-16T08:00:00Z"
        }
    ),
    responses={
        200: OpenApiExample(
            'Webhook Processed',
            summary='Webhook successfully processed',
            description='Confirmation of webhook processing',
            value={
                "message": "Adzuna webhook received",
                "processed": True,
                "timestamp": "2025-06-16T08:00:00Z"
            }
        ),
        400: OpenApiExample(
            'Unknown Service',
            summary='Unsupported webhook service',
            description='Service not recognized or supported',
            value={
                "error": "Unknown service"
            }
        )
    }
)
class WebhookView(APIView):
    """
    External service webhook handler for real-time data processing.
    
    Handles incoming webhooks from various external services:
    - Adzuna: Job posting updates and notifications
    - Skyvern: Automation task completion and status updates
    - LinkedIn: Profile updates and connection events
    - Indeed: Application status changes
    
    Processes webhook data and triggers appropriate internal actions
    such as job synchronization, user notifications, or data updates.
    """
    permission_classes = []  # Public endpoint for webhooks
    
    def post(self, request, service=None):
        """
        Process incoming webhook from specified external service.
        
        Validates webhook authenticity and processes the payload
        based on the service type and event data.
        """
        if service == 'adzuna':
            # TODO: Handle Adzuna webhooks
            return Response({'message': 'Adzuna webhook received'})
        elif service == 'skyvern':
            return self._handle_skyvern_webhook(request)
        else:
            return Response(
                {'error': 'Unknown service'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

    def _verify_skyvern_webhook_signature(self, request):
        """
        Placeholder for Skyvern webhook signature verification.
        """
        # from django.conf import settings
        # import hmac # For actual signature verification
        # import hashlib
        #
        # skyvern_signature = request.headers.get('X-Skyvern-Signature') # Example header
        # shared_secret = getattr(settings, 'SKYVERN_WEBHOOK_SECRET', None)
        #
        # if not skyvern_signature or not shared_secret:
        #     logger.warning("Skyvern webhook: Missing signature or shared secret for verification.")
        #     return False # Fail if essential components are missing for verification
        #
        # payload_body = request.body
        # # Example: `calculated_signature = hmac.new(shared_secret.encode(), payload_body, hashlib.sha256).hexdigest()`
        # # if not hmac.compare_digest(calculated_signature, skyvern_signature):
        # #     logger.warning("Skyvern webhook: Invalid signature.")
        # #     return False
        #
        # logger.info("Skyvern webhook: Signature (placeholder) verified.")
        # return True

        from django.conf import settings
        import hmac
        import hashlib

        skyvern_signature_header = request.headers.get('X-Skyvern-Signature') # Common header, confirm with Skyvern docs
        shared_secret = getattr(settings, 'SKYVERN_WEBHOOK_SECRET', None)

        if not skyvern_signature_header:
            logger.warning("Skyvern webhook: Missing 'X-Skyvern-Signature' header.")
            return False

        if not shared_secret:
            logger.error("Skyvern webhook: SKYVERN_WEBHOOK_SECRET is not configured in settings. Cannot verify signature.")
            # In a production system, you might want to return False here to block unverified webhooks.
            # For debugging or if an insecure mode is explicitly desired for dev, one might allow it,
            # but it's a security risk. Defaulting to secure: verification fails if secret is missing.
            return False

        payload_body = request.body # Raw body bytes

        try:
            # Calculate the expected signature
            expected_signature = hmac.new(
                shared_secret.encode('utf-8'),
                payload_body,
                hashlib.sha256
            ).hexdigest()

            # Securely compare the signatures
            if hmac.compare_digest(expected_signature, skyvern_signature_header):
                logger.info("Skyvern webhook: Signature verified successfully.")
                return True
            else:
                logger.warning(f"Skyvern webhook: Invalid signature. Header: {skyvern_signature_header}, Calculated: {expected_signature}")
                return False
        except Exception as e:
            logger.error(f"Skyvern webhook: Error during signature verification: {e}")
            return False

    def _handle_skyvern_webhook(self, request):
        """
        Handles incoming webhooks from Skyvern.
        Updates the corresponding Application model instance.
        """
        import json # Moved import here
        from django.utils import timezone
        from apps.jobs.models import Application # Ensure this path is correct
        # from .tasks import retrieve_skyvern_task_results_task # If needed

        logger = logging.getLogger(__name__) # Ensure logger is defined or passed

        if not self._verify_skyvern_webhook_signature(request): # Self is needed for instance method
            return Response({"error": "Invalid signature."}, status=status.HTTP_403_FORBIDDEN)

        try:
            payload = json.loads(request.body.decode('utf-8'))
            logger.info(f"Received Skyvern webhook payload: {payload}")
        except json.JSONDecodeError:
            logger.error("Skyvern webhook: Invalid JSON payload.")
            return Response({"error": "Invalid JSON payload."}, status=status.HTTP_400_BAD_REQUEST)

        skyvern_task_id = payload.get("task_id")
        skyvern_status = payload.get("status")
        skyvern_data = payload.get("data")
        skyvern_error_details = payload.get("error_details")

        if not skyvern_task_id or not skyvern_status:
            logger.error(f"Skyvern webhook: Missing task_id or status in payload: {payload}")
            return Response({"error": "Missing task_id or status."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            application = Application.objects.get(skyvern_task_id=skyvern_task_id)
        except Application.DoesNotExist:
            logger.warning(f"Skyvern webhook: Update for unknown Skyvern task_id {skyvern_task_id}. No matching application.")
            return Response({"message": "Webhook for unknown task_id received."}, status=status.HTTP_200_OK)
        except Application.MultipleObjectsReturned:
            logger.error(f"Skyvern webhook: Multiple applications for Skyvern task_id {skyvern_task_id}. Critical error.")
            return Response({"error": "Internal error: multiple applications for task_id."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        logger.info(f"Processing Skyvern webhook for AppID: {application.id}, SkyvernTaskID: {skyvern_task_id}, SkyvernStatus: {skyvern_status}")

        original_app_status = application.status
        new_app_status = original_app_status
        fields_to_update = ['updated_at']
        response_changed_application = False

        current_response_data = application.skyvern_response_data or {}

        if skyvern_status == "COMPLETED":
            new_app_status = 'submitted'
            if not application.applied_at:
                application.applied_at = timezone.now()
                fields_to_update.append('applied_at')
            current_response_data.update(skyvern_data or {}) # Merge new data
            application.skyvern_response_data = current_response_data
            fields_to_update.append('skyvern_response_data')
        elif skyvern_status == "FAILED":
            new_app_status = 'skyvern_submission_failed'
            current_response_data.update(skyvern_error_details or skyvern_data or {"error": "Task failed as per webhook."})
            application.skyvern_response_data = current_response_data
            fields_to_update.append('skyvern_response_data')
        elif skyvern_status == "CANCELED":
            new_app_status = 'skyvern_canceled'
            current_response_data.update({"status_reason": "canceled", "details": skyvern_data or skyvern_error_details})
            application.skyvern_response_data = current_response_data
            fields_to_update.append('skyvern_response_data')
        elif skyvern_status == "REQUIRES_ATTENTION":
            new_app_status = 'skyvern_requires_attention'
            current_response_data.update(skyvern_data or skyvern_error_details or {"status_reason": "requires_attention"})
            application.skyvern_response_data = current_response_data
            fields_to_update.append('skyvern_response_data')
        elif skyvern_status in ["PENDING", "RUNNING"]:
            if application.status not in ['submitting_via_skyvern']:
                new_app_status = 'submitting_via_skyvern'
        else:
            logger.warning(f"Skyvern webhook: Unhandled Skyvern status '{skyvern_status}' for task {skyvern_task_id}.")

        if new_app_status != original_app_status or 'applied_at' in fields_to_update or 'skyvern_response_data' in fields_to_update:
            application.status = new_app_status
            if 'status' not in fields_to_update: fields_to_update.append('status')

            fields_to_update = list(set(fields_to_update)) # Ensure unique fields
            application.save(update_fields=fields_to_update)
            response_changed_application = True
            logger.info(f"Application {application.id} updated via webhook. Status: {original_app_status} -> {new_app_status}.")
        else:
            logger.info(f"Application {application.id} status ({original_app_status}) effectively unchanged by Skyvern webhook status {skyvern_status}.")

        return Response({"message": "Webhook processed.", "application_updated": response_changed_application})


@extend_schema(
    summary="Check API integration status",
    description="Get the current status and health of all external API integrations",
    tags=['Integrations'],
    responses={
        200: OpenApiExample(
            'API Status',
            summary='Status of all API integrations',
            description='Health check results for external services',
            value={
                "adzuna": {
                    "status": "active",
                    "last_sync": "2025-06-16T07:00:00Z",
                    "jobs_synced": 1250,
                    "api_limit_remaining": 850
                },
                "openai": {
                    "status": "active",
                    "last_request": "2025-06-16T08:15:00Z",
                    "requests_today": 145,
                    "token_usage": 12500
                },
                "skyvern": {
                    "status": "active",
                    "last_automation": "2025-06-16T08:00:00Z",
                    "active_tasks": 3,
                    "completed_today": 25
                },
                "linkedin": {
                    "status": "inactive",
                    "last_sync": None,
                    "error": "API credentials not configured"
                }
            }
        ),
        401: OpenApiExample(
            'Unauthorized',
            value={'error': 'Authentication required'},
            response_only=True
        )
    }
)
class ApiStatusView(APIView):
    """
    External API integration status monitoring.
    
    Provides real-time status information for all external integrations:
    - Connection status and health checks
    - Last successful operation timestamps
    - Usage statistics and rate limits
    - Error states and diagnostic information
    - Performance metrics and response times
    
    Useful for system monitoring and troubleshooting integration issues.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """
        Check and return status of all external API integrations.
        
        Performs health checks and returns comprehensive status information
        for monitoring and diagnostic purposes.
        """
        from .services.config_service import APIConfigurationService, test_celery_tasks, test_database_connectivity
        
        try:
            config_service = APIConfigurationService()
            
            # Get comprehensive API status
            api_status = config_service.check_all_apis()
            
            # Add Celery and database status
            api_status['celery'] = test_celery_tasks()
            api_status['database'] = test_database_connectivity()
            
            return Response(api_status, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error checking API status: {e}")
            return Response(
                {"error": "Failed to check API status", "details": str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema(
    summary="Trigger job synchronization",
    description="Manually trigger job data synchronization from external sources",
    tags=['Integrations'],
    request=OpenApiExample(
        'Job Sync Request',
        summary='Trigger job sync for specific source',
        description='Request to sync jobs from external source',
        value={
            "source": "adzuna",
            "full_sync": False,
            "max_jobs": 1000
        }
    ),
    responses={
        200: OpenApiExample(
            'Sync Triggered',
            summary='Job synchronization started',
            description='Sync task queued successfully',
            value={
                "message": "Job sync triggered for adzuna",
                "status": "queued",
                "task_id": "celery_task_123",
                "estimated_completion": "2025-06-16T08:30:00Z"
            }
        ),
        400: OpenApiExample(
            'Invalid Request',
            value={'error': 'Invalid source specified'},
            response_only=True
        ),
        401: OpenApiExample(
            'Unauthorized',
            value={'error': 'Authentication required'},
            response_only=True
        )
    }
)
class JobSyncView(APIView):
    """
    Manual job synchronization trigger for external data sources.
    
    Allows administrators to manually trigger job data synchronization:
    - Full sync: Complete refresh of all job data
    - Incremental sync: Only new/updated jobs since last sync
    - Source-specific sync: Target specific job boards or APIs
    - Batch processing: Handle large datasets efficiently
    
    Uses Celery for asynchronous processing to prevent request timeouts.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Trigger manual job synchronization from external sources.
        
        Queues background tasks for data fetching and processing.
        """
        source = request.data.get('source', 'all')
        full_sync = request.data.get('full_sync', False)
        max_days_old = request.data.get('max_days_old', 1)
        
        try:
            from .tasks import fetch_adzuna_jobs
            
            if source == 'adzuna' or source == 'all':
                # Trigger Adzuna job fetching
                task = fetch_adzuna_jobs.delay(
                    categories=None,  # Fetch all categories
                    max_days_old=max_days_old
                )
                
                return Response({
                    'message': f'Job sync triggered for {source}',
                    'status': 'queued',
                    'task_id': task.id,
                    'source': source,
                    'max_days_old': max_days_old
                }, status=status.HTTP_200_OK)
            
            else:
                return Response({
                    'error': f'Unsupported source: {source}',
                    'supported_sources': ['adzuna', 'all']
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Error triggering job sync for {source}: {e}")
            return Response({
                'error': 'Failed to trigger job sync',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    summary="Test API connection",
    description="Test connectivity and authentication with external APIs",
    tags=['Integrations'],
    parameters=[
        OpenApiParameter(
            name='service',
            description='Service to test (adzuna, openai, skyvern)',
            required=True,
            type=OpenApiTypes.STR,
            location=OpenApiParameter.PATH
        )
    ],
    responses={
        200: OpenApiExample(
            'Connection Test Success',
            summary='API connection successful',
            description='Connection test passed with API details',
            value={
                "service": "adzuna",
                "status": "connected",
                "response_time": 245,
                "api_version": "1.2.3",
                "rate_limit": {
                    "remaining": 950,
                    "reset_at": "2025-06-16T09:00:00Z"
                }
            }
        ),
        400: OpenApiExample(
            'Connection Test Failed',
            summary='API connection failed',
            description='Connection test failed with error details',
            value={
                "service": "adzuna",
                "status": "failed",
                "error": "Invalid API credentials",
                "error_code": "AUTH_FAILED"
            }
        ),
        401: OpenApiExample(
            'Unauthorized',
            value={'error': 'Authentication required'},
            response_only=True
        )
    }
)
class ApiTestView(APIView):
    """
    API connection testing and diagnostics.
    
    Tests connectivity and authentication with external services:
    - Validates API credentials and permissions
    - Measures response times and performance
    - Checks API rate limits and quotas
    - Verifies service availability and status
    - Provides diagnostic information for troubleshooting
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, service):
        """
        Test connection to specified external API service.
        
        Performs authentication test and basic API call to verify connectivity.
        """
        from .services.config_service import APIConfigurationService
        
        try:
            config_service = APIConfigurationService()
            
            if service == 'adzuna':
                result = config_service.check_adzuna_api()
            elif service == 'openai':
                result = config_service.check_openai_api()
            elif service == 'skyvern':
                result = config_service.check_skyvern_api()
            else:
                return Response({
                    'error': f'Unknown service: {service}',
                    'supported_services': ['adzuna', 'openai', 'skyvern']
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Add service name to result
            result['service'] = service
            
            return Response(result, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error testing {service} API: {e}")
            return Response({
                'service': service,
                'status': 'error',
                'message': f'Failed to test {service} API connection',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    summary="Get integration configuration",
    description="Retrieve configuration settings for external integrations",
    tags=['Integrations'],
    responses={
        200: OpenApiExample(
            'Integration Config',
            summary='Integration configuration settings',
            description='Current configuration for all integrations',
            value={
                "adzuna": {
                    "enabled": True,
                    "sync_frequency": "hourly",
                    "max_jobs_per_sync": 1000,
                    "last_configured": "2025-06-15T10:00:00Z"
                },
                "openai": {
                    "enabled": True,
                    "model": "gpt-4",
                    "max_tokens": 2000,
                    "temperature": 0.7
                },
                "skyvern": {
                    "enabled": True,
                    "max_concurrent_tasks": 5,
                    "retry_attempts": 3,
                    "timeout_minutes": 10
                }
            }
        ),
        401: OpenApiExample(
            'Unauthorized',
            value={'error': 'Authentication required'},
            response_only=True
        )
    }
)
class IntegrationConfigView(APIView):
    """
    Integration configuration management.
    
    Manages configuration settings for external service integrations:
    - API credentials and authentication settings
    - Sync frequencies and batch sizes
    - Rate limiting and retry policies
    - Feature flags and service enablement
    - Performance and optimization parameters
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """
        Get current integration configuration settings.
        
        Returns configuration for all enabled integrations.
        """
        from .services.config_service import APIConfigurationService
        
        try:
            config_service = APIConfigurationService()
            
            # Get quick status without making API calls
            quick_status = config_service.get_quick_status()
            
            # Build configuration response
            config_data = {
                'adzuna': {
                    'configured': quick_status['adzuna_configured'],
                    'app_id_set': bool(config_service.adzuna_app_id),
                    'api_key_set': bool(config_service.adzuna_api_key),
                    'sync_frequency': 'hourly',  # From Celery beat schedule
                    'max_jobs_per_sync': 1000
                },
                'openai': {
                    'configured': quick_status['openai_configured'],
                    'api_key_set': bool(config_service.openai_api_key),
                    'model': getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini'),
                    'embedding_model': getattr(settings, 'OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small')
                },
                'skyvern': {
                    'configured': quick_status['skyvern_configured'],
                    'api_key_set': bool(config_service.skyvern_api_key),
                    'base_url': config_service.skyvern_base_url,
                    'max_concurrent_tasks': 5,
                    'retry_attempts': 3
                },
                'summary': {
                    'all_configured': quick_status['all_configured'],
                    'total_configured': sum([
                        quick_status['openai_configured'],
                        quick_status['adzuna_configured'], 
                        quick_status['skyvern_configured']
                    ])
                }
            }
            
            return Response(config_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error retrieving integration config: {e}")
            return Response({
                'error': 'Failed to retrieve configuration',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @extend_schema(
        summary="Update integration configuration",
        description="Update configuration settings for external integrations",
        request=OpenApiExample(
            'Config Update',
            summary='Update integration settings',
            description='New configuration values',
            value={
                "adzuna": {
                    "sync_frequency": "daily",
                    "max_jobs_per_sync": 2000
                },
                "openai": {
                    "temperature": 0.8,
                    "max_tokens": 3000
                }
            }
        ),
        responses={
            200: OpenApiExample(
                'Config Updated',
                summary='Configuration updated successfully',
                value={
                    "message": "Integration configuration updated",
                    "updated_services": ["adzuna", "openai"]
                }
            ),
            400: OpenApiExample(
                'Invalid Config',
                value={'error': 'Invalid configuration values'},
                response_only=True
            )
        }
    )
    def patch(self, request):
        """
        Update specific integration configuration settings.
        
        Allows partial updates to integration configurations.
        """
        # TODO: Implement config updates
        return Response({
            'message': 'Integration configuration update coming soon'
        })
