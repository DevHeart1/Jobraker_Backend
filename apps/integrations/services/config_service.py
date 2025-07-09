"""
API Integration Configuration and Testing Service
"""

import logging
import requests
from typing import Dict, Any, Optional
from django.conf import settings

logger = logging.getLogger(__name__)


class APIConfigurationService:
    """
    Service for testing and validating external API integrations.
    """

    def __init__(self):
        self.openai_api_key = getattr(settings, 'OPENAI_API_KEY', '')
        self.adzuna_app_id = getattr(settings, 'ADZUNA_APP_ID', '')
        self.adzuna_api_key = getattr(settings, 'ADZUNA_API_KEY', '')
        self.skyvern_api_key = getattr(settings, 'SKYVERN_API_KEY', '')
        self.skyvern_base_url = getattr(settings, 'SKYVERN_BASE_URL', 'https://api.skyvern.com')

    def check_all_apis(self) -> Dict[str, Any]:
        """
        Check the status of all external API integrations.
        
        Returns:
            Dictionary with status of each API
        """
        return {
            'openai': self.check_openai_api(),
            'adzuna': self.check_adzuna_api(),
            'skyvern': self.check_skyvern_api(),
            'summary': self._get_summary()
        }

    def check_openai_api(self) -> Dict[str, Any]:
        """
        Test OpenAI API connection and credentials.
        """
        if not self.openai_api_key:
            return {
                'status': 'error',
                'message': 'OpenAI API key not configured',
                'configured': False
            }

        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.openai_api_key)
            
            # Test with a simple embedding request
            response = client.embeddings.create(
                model=getattr(settings, 'OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small'),
                input="test connection"
            )
            
            if response and response.data:
                return {
                    'status': 'success',
                    'message': 'OpenAI API connection successful',
                    'configured': True,
                    'model': getattr(settings, 'OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small'),
                    'embedding_dimension': len(response.data[0].embedding)
                }
            else:
                return {
                    'status': 'error',
                    'message': 'OpenAI API returned empty response',
                    'configured': True
                }

        except Exception as e:
            return {
                'status': 'error',
                'message': f'OpenAI API test failed: {str(e)}',
                'configured': True
            }

    def check_adzuna_api(self) -> Dict[str, Any]:
        """
        Test Adzuna API connection and credentials.
        """
        if not self.adzuna_app_id or not self.adzuna_api_key:
            return {
                'status': 'error',
                'message': 'Adzuna API credentials not configured',
                'configured': False
            }

        try:
            # Test with a simple job search request
            url = "https://api.adzuna.com/v1/api/jobs/us/search/1"
            params = {
                'app_id': self.adzuna_app_id,
                'app_key': self.adzuna_api_key,
                'results_per_page': 1,
                'what': 'software engineer'
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if 'results' in data:
                return {
                    'status': 'success',
                    'message': 'Adzuna API connection successful',
                    'configured': True,
                    'total_jobs_available': data.get('count', 0)
                }
            else:
                return {
                    'status': 'error',
                    'message': 'Adzuna API returned unexpected response format',
                    'configured': True
                }

        except requests.exceptions.RequestException as e:
            return {
                'status': 'error',
                'message': f'Adzuna API test failed: {str(e)}',
                'configured': True
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Adzuna API test error: {str(e)}',
                'configured': True
            }

    def check_skyvern_api(self) -> Dict[str, Any]:
        """
        Test Skyvern API connection and credentials.
        """
        if not self.skyvern_api_key:
            return {
                'status': 'error',
                'message': 'Skyvern API key not configured',
                'configured': False
            }

        try:
            # Test with a simple status check or list tasks endpoint
            headers = {
                'Authorization': f'Bearer {self.skyvern_api_key}',
                'Content-Type': 'application/json'
            }
            
            # Try to get a list of recent tasks (if endpoint exists)
            url = f"{self.skyvern_base_url}/v1/tasks"
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 401:
                return {
                    'status': 'error',
                    'message': 'Skyvern API authentication failed - invalid API key',
                    'configured': True
                }
            elif response.status_code == 404:
                # If tasks endpoint doesn't exist, try a different approach
                return {
                    'status': 'warning',
                    'message': 'Skyvern API key appears valid but tasks endpoint not found',
                    'configured': True
                }
            elif response.status_code in [200, 403]:  # 403 might indicate valid auth but insufficient permissions
                return {
                    'status': 'success',
                    'message': 'Skyvern API connection successful',
                    'configured': True,
                    'base_url': self.skyvern_base_url
                }
            else:
                return {
                    'status': 'warning',
                    'message': f'Skyvern API returned status {response.status_code}',
                    'configured': True
                }

        except requests.exceptions.RequestException as e:
            return {
                'status': 'error',
                'message': f'Skyvern API test failed: {str(e)}',
                'configured': True
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Skyvern API test error: {str(e)}',
                'configured': True
            }

    def _get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of API configuration status.
        """
        apis = ['openai', 'adzuna', 'skyvern']
        configured_count = 0
        working_count = 0
        
        for api_name in apis:
            if api_name == 'openai' and self.openai_api_key:
                configured_count += 1
            elif api_name == 'adzuna' and (self.adzuna_app_id and self.adzuna_api_key):
                configured_count += 1
            elif api_name == 'skyvern' and self.skyvern_api_key:
                configured_count += 1
        
        return {
            'total_apis': len(apis),
            'configured_apis': configured_count,
            'configuration_complete': configured_count == len(apis),
            'message': f'{configured_count}/{len(apis)} APIs configured'
        }

    def get_quick_status(self) -> Dict[str, Any]:
        """
        Get a quick status check without making actual API calls.
        """
        return {
            'openai_configured': bool(self.openai_api_key),
            'adzuna_configured': bool(self.adzuna_app_id and self.adzuna_api_key),
            'skyvern_configured': bool(self.skyvern_api_key),
            'all_configured': all([
                self.openai_api_key,
                self.adzuna_app_id and self.adzuna_api_key,
                self.skyvern_api_key
            ])
        }


def test_celery_tasks() -> Dict[str, Any]:
    """
    Test basic Celery task functionality.
    """
    try:
        from jobraker.celery import app
        
        # Test task discovery
        inspect = app.control.inspect()
        active_tasks = inspect.active()
        registered_tasks = inspect.registered()
        
        if active_tasks is not None or registered_tasks is not None:
            return {
                'status': 'success',
                'message': 'Celery workers are active and responsive',
                'workers_connected': bool(active_tasks),
                'tasks_registered': bool(registered_tasks)
            }
        else:
            return {
                'status': 'warning',
                'message': 'Celery broker is accessible but no workers found',
                'workers_connected': False
            }
    
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Celery test failed: {str(e)}',
            'workers_connected': False
        }


def test_database_connectivity() -> Dict[str, Any]:
    """
    Test database connectivity and basic operations.
    """
    try:
        from django.db import connection
        from apps.jobs.models import Job
        
        # Test basic connectivity
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        
        # Test model operations
        job_count = Job.objects.count()
        
        return {
            'status': 'success',
            'message': 'Database connection successful',
            'total_jobs': job_count,
            'database_engine': connection.settings_dict['ENGINE']
        }
    
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Database test failed: {str(e)}'
        }
