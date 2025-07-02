"""
Adzuna API integration service for job data fetching.
"""

import requests
import logging
import time # For circuit breaker
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry # For retry mechanism

from apps.jobs.models import Job, JobSource
from apps.common.metrics import (
    ADZUNA_API_REQUESTS_TOTAL,
    ADZUNA_API_REQUEST_DURATION_SECONDS,
    ADZUNA_JOBS_PROCESSED_TOTAL,
    ADZUNA_API_ERRORS_TOTAL,
    ADZUNA_CIRCUIT_BREAKER_STATE_CHANGES_TOTAL
)

logger = logging.getLogger(__name__)
logger = logging.getLogger(__name__)

# Circuit Breaker States
STATE_CLOSED = "CLOSED"
STATE_OPEN = "OPEN"
STATE_HALF_OPEN = "HALF_OPEN"

class AdzunaAPIClient:
    """
    Client for interacting with Adzuna API.
    Handles job fetching, search, and data processing.
    Includes retry mechanism and basic circuit breaker.
    """
    
    BASE_URL = "https://api.adzuna.com/v1/api"
    
    # Circuit Breaker Configuration
    CB_MAX_FAILURES = 5
    CB_RESET_TIMEOUT_SECONDS = 60  # Time in seconds before trying again when circuit is OPEN
    CB_HALF_OPEN_MAX_REQUESTS = 3  # Number of requests to allow in HALF_OPEN state
    REQUEST_DELAY_SECONDS = 0.5  # Proactive delay between requests

    def __init__(self):
        self.app_id = getattr(settings, 'ADZUNA_APP_ID', '')
        self.api_key = getattr(settings, 'ADZUNA_API_KEY', '')
        
        self.session = self._configure_session()

        # Circuit Breaker State
        self._cb_state = STATE_CLOSED
        self._cb_failures = 0
        self._cb_last_failure_time = None
        self._cb_half_open_success_count = 0

        if not self.app_id or not self.api_key:
            logger.warning("Adzuna API credentials not configured. API calls will use mock data.")

    def _configure_session(self) -> requests.Session:
        """Configures the requests session with retry mechanism."""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,  # Total number of retries
            status_forcelist=[429, 500, 502, 503, 504],  # HTTP status codes to retry on
            allowed_methods=["HEAD", "GET", "OPTIONS"], # Allowed methods for retry
            backoff_factor=1  # Exponential backoff factor (e.g., 1s, 2s, 4s)
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _handle_circuit_breaker_open(self):
        """Logic for when the circuit is OPEN."""
        if self._cb_last_failure_time and \
           (time.monotonic() - self._cb_last_failure_time) > self.CB_RESET_TIMEOUT_SECONDS:
            self._cb_state = STATE_HALF_OPEN
            self._cb_half_open_success_count = 0 # Reset for HALF_OPEN
            ADZUNA_CIRCUIT_BREAKER_STATE_CHANGES_TOTAL.labels(new_state=STATE_HALF_OPEN).inc()
            logger.info("Circuit Breaker: State changed to HALF_OPEN.")
        else:
            logger.warning("Circuit Breaker: OPEN. Request blocked.")
            # ADZUNA_API_ERRORS_TOTAL.labels(endpoint='N/A', country='N/A', error_type='CircuitBreakerOpen').inc() # Handled in _make_request
            raise requests.exceptions.ConnectionError("Circuit Breaker is OPEN.")

    def _handle_circuit_breaker_failure(self):
        """Logic to handle a failure in the context of the circuit breaker."""
        self._cb_failures += 1
        self._cb_last_failure_time = time.monotonic()
        if self._cb_state == STATE_HALF_OPEN:
            self._cb_state = STATE_OPEN # Revert to OPEN if HALF_OPEN fails
            self._cb_failures = self.CB_MAX_FAILURES # Ensure it stays open
            ADZUNA_CIRCUIT_BREAKER_STATE_CHANGES_TOTAL.labels(new_state=STATE_OPEN).inc()
            logger.warning("Circuit Breaker: HALF_OPEN request failed. State changed back to OPEN.")
        elif self._cb_failures >= self.CB_MAX_FAILURES and self._cb_state != STATE_OPEN: # Avoid double increment if already open
            self._cb_state = STATE_OPEN
            ADZUNA_CIRCUIT_BREAKER_STATE_CHANGES_TOTAL.labels(new_state=STATE_OPEN).inc()
            logger.warning(f"Circuit Breaker: Max failures ({self.CB_MAX_FAILURES}) reached. State changed to OPEN.")

    def _handle_circuit_breaker_success(self):
        """Logic to handle a success in the context of the circuit breaker."""
        if self._cb_state == STATE_HALF_OPEN:
            self._cb_half_open_success_count += 1
            if self._cb_half_open_success_count >= self.CB_HALF_OPEN_MAX_REQUESTS:
                self._cb_state = STATE_CLOSED
                self._cb_failures = 0
                self._cb_last_failure_time = None
                logger.info("Circuit Breaker: HALF_OPEN requests successful. State changed to CLOSED.")
        elif self._cb_state == STATE_CLOSED: # Reset failures if it was already closed
            self._cb_failures = 0
            self._cb_last_failure_time = None


    def _make_request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make authenticated request to Adzuna API with circuit breaker and retries."""
        if self._cb_state == STATE_OPEN:
            self._handle_circuit_breaker_open() # Might raise ConnectionError or change to HALF_OPEN

        # Proactive request delay
        if self.REQUEST_DELAY_SECONDS > 0:
            time.sleep(self.REQUEST_DELAY_SECONDS)

        if not self.app_id or not self.api_key:
            # This check remains for mock data even if circuit is closed/half-open
            logger.warning("Adzuna API credentials not configured - using mock data")
            return self._get_mock_response(endpoint, params)
        
        auth_params = {'app_id': self.app_id, 'app_key': self.api_key}
        if params:
            auth_params.update(params)
        
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            response = self.session.get(url, params=auth_params, timeout=30)
            response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
            self._handle_circuit_breaker_success()
            return response.json()
        except requests.exceptions.HTTPError as e:
            # Specific handling for 429, though retry should handle it first
            if e.response.status_code == 429:
                logger.warning(f"Adzuna API rate limit hit (429): {e}. Retries configured.")
            # For other HTTP errors that persist after retries, count as failure for CB
            logger.error(f"Adzuna API HTTPError after retries: {e}")
            self._handle_circuit_breaker_failure()
            # Fallback to mock response or re-raise depending on desired strictness
            # For now, falling back to mock to prevent full stop during dev if API has issues
            return self._get_mock_response(endpoint, params)
        except requests.exceptions.RequestException as e:
            # Includes ConnectionError, Timeout, TooManyRedirects etc.
            logger.error(f"Adzuna API request failed after retries: {e}")
            self._handle_circuit_breaker_failure()
            return self._get_mock_response(endpoint, params)

    def _get_mock_response(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Return mock data for development/testing."""
        return {
            "count": 10,
            "mean": 45000,
            "results": [
                {
                    "id": f"mock_job_{i}",
                    "title": f"Software Engineer {i}",
                    "company": {
                        "display_name": f"TechCorp {i}"
                    },
                    "location": {
                        "area": ["San Francisco", "CA"],
                        "display_name": "San Francisco, CA"
                    },
                    "description": f"Exciting opportunity for a Software Engineer at TechCorp {i}...",
                    "salary_min": 80000 + (i * 5000),
                    "salary_max": 120000 + (i * 5000),
                    "salary_is_predicted": 0,
                    "created": (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "redirect_url": f"https://example.com/job/{i}",
                    "category": {
                        "tag": "it-jobs"
                    },
                    "contract_type": "permanent"
                } for i in range(1, 11)
            ]
        }
    
    def search_jobs(
        self,
        what: str = "",
        where: str = "",
        results_per_page: int = 20,
        page: int = 1,
        sort_by: str = "date",
        max_days_old: int = 7,
        salary_min: Optional[int] = None,
        salary_max: Optional[int] = None,
        full_time: Optional[bool] = None,
        part_time: Optional[bool] = None,
        contract: Optional[bool] = None,
        permanent: Optional[bool] = None,
        company: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search for jobs using Adzuna API.
        
        Args:
            what: Job title or keywords
            where: Location (city, state, etc.)
            results_per_page: Number of results per page (max 50)
            page: Page number (starting from 1)
            sort_by: Sort order ('date', 'relevance', 'salary')
            max_days_old: Maximum days since job was posted
            salary_min: Minimum salary
            salary_max: Maximum salary
            full_time: Filter for full-time jobs
            part_time: Filter for part-time jobs
            contract: Filter for contract jobs
            permanent: Filter for permanent jobs
            company: Company name filter
        
        Returns:
            API response containing job results
        """
        params = {
            'what': what,
            'where': where,
            'results_per_page': min(results_per_page, 50),  # API limit
            'sort_by': sort_by,
            'max_days_old': max_days_old,
        }
        
        # Add optional filters
        if salary_min:
            params['salary_min'] = salary_min
        if salary_max:
            params['salary_max'] = salary_max
        if full_time is not None:
            params['full_time'] = 1 if full_time else 0
        if part_time is not None:
            params['part_time'] = 1 if part_time else 0
        if contract is not None:
            params['contract'] = 1 if contract else 0
        if permanent is not None:
            params['permanent'] = 1 if permanent else 0
        if company:
            params['company'] = company
        
        # Update endpoint with page number
        endpoint = f"/jobs/{where.lower()}/search/{page}" # Standardize country to lowercase
        
        logger.info(f"Searching Adzuna jobs: what='{what}', where='{where}', page={page}, params={params}")
        return self._make_request(endpoint, params)

    def get_job_details(self, job_id: str, country: str = "us") -> Dict[str, Any]:
        """Get detailed information about a specific job."""
        endpoint = f"/jobs/{country.lower()}/details/{job_id}" # Standardize country to lowercase
        logger.info(f"Fetching job details for job_id='{job_id}', country='{country}'")
        return self._make_request(endpoint)
    
    def get_salary_data(self, job_title: str, location: str = "", country: str = "us") -> Dict[str, Any]:
        """Get salary statistics for a job title and location."""
        endpoint = "/jobs/us/histogram"
        params = {
            'what': job_title,
            'where': location,
        }
        return self._make_request(endpoint, params)
    
    def get_top_companies(self, location: str = "") -> Dict[str, Any]:
        """Get top companies in a location."""
        endpoint = "/jobs/us/top_companies"
        params = {'where': location} if location else {}
        return self._make_request(endpoint, params)


class AdzunaJobProcessor:
    """
    Processes job data from Adzuna API and saves to database.
    """
    
    def __init__(self):
        self.client = AdzunaAPIClient()
        self.job_source = self._get_or_create_job_source()
    
    def _get_or_create_job_source(self) -> JobSource:
        """Get or create Adzuna job source."""
        source, created = JobSource.objects.get_or_create(
            name="Adzuna",
            defaults={
                'source_type': 'api',
                'base_url': 'https://api.adzuna.com',
                'is_active': True,
            }
        )
        if created:
            logger.info("Created new Adzuna job source")
        return source
    
    def fetch_and_process_jobs(
        self,
        what: str = "software engineer",
        where: str = "us", 
        max_pages: int = 5,
        max_days_old: int = 7
    ) -> Dict[str, int]:
        """
        Fetch jobs from Adzuna and process them into the database.
        
        Args:
            what: Job search keywords
            where: Location to search
            max_pages: Maximum pages to fetch
            max_days_old: How many days back to search
        
        Returns:
            Dictionary with processing statistics
        """
        stats = {
            'total_found': 0,
            'processed': 0,
            'created': 0,
            'updated': 0,
            'errors': 0,
        }
        
        logger.info(f"Starting Adzuna job fetch: {what} in {where}")
        
        try:
            for page in range(1, max_pages + 1):
                response = self.client.search_jobs(
                    what=what,
                    where=where,
                    page=page,
                    max_days_old=max_days_old,
                    results_per_page=50
                )
                
                if not response or 'results' not in response:
                    logger.warning(f"No results found on page {page}")
                    break
                
                jobs = response['results']
                if not jobs:
                    logger.info(f"No more jobs found, stopping at page {page}")
                    break
                
                stats['total_found'] += len(jobs)
                
                for job_data in jobs:
                    country_label = where # Assuming 'where' is the country for this context
                    try:
                        result = self._process_job(job_data, country_label) # Pass country for metrics
                        stats['processed'] += 1
                        if result == 'created':
                            stats['created'] += 1
                        elif result == 'updated':
                            stats['updated'] += 1
                        # 'skipped' is handled by ADZUNA_JOBS_PROCESSED_TOTAL in _process_job
                    except Exception as e:
                        logger.error(f"Error processing job {job_data.get('id', 'unknown')}: {e}")
                        stats['errors'] += 1
                        ADZUNA_JOBS_PROCESSED_TOTAL.labels(country=country_label, status='error').inc()
                
                logger.info(f"Processed page {page}: {len(jobs)} jobs")
            
            # Update job source statistics
            self.job_source.last_sync_at = timezone.now()
            self.job_source.total_jobs_fetched += stats['created'] + stats['updated']
            self.job_source.successful_syncs += 1
            self.job_source.save()
            
        except Exception as e:
            logger.error(f"Error in Adzuna job fetch: {e}")
            self.job_source.failed_syncs += 1
            self.job_source.save()
            stats['errors'] += 1
        
        logger.info(f"Adzuna job fetch completed: {stats}")
        return stats

    def sync_recent_jobs(self, days: int = 1, countries: Optional[List[str]] = None) -> Dict[str, int]:
        """
        Synchronizes recent jobs from Adzuna across predefined categories and specified countries.

        Args:
            days: How many days back to search for recent jobs.
            countries: A list of country codes (e.g., ['us', 'gb']) to fetch jobs from.
                       Defaults to ['us'] if None.

        Returns:
            Dictionary with overall processing statistics.
        """
        if countries is None:
            countries = ['us']

        overall_stats = {
            'total_found': 0,
            'processed': 0,
            'created': 0,
            'updated': 0,
            'errors': 0,
        }

        # Broader categories that are likely to yield diverse results
        # These can be configured or expanded as needed
        general_categories = [
            "software development", "engineering", "project manager",
            "data analyst", "marketing", "sales", "customer service",
            "designer", "product manager", "business analyst"
        ]

        logger.info(f"Starting Adzuna recent jobs sync for {days} day(s) in countries: {countries}")

        for country_code in countries:
            logger.info(f"Fetching jobs for country: {country_code}")
            for category in general_categories:
                logger.info(f"Fetching category '{category}' for country '{country_code}'")
                try:
                    # Fetching 1 page per category to get the most recent, can be adjusted
                    stats = self.fetch_and_process_jobs(
                        what=category,
                        where=country_code,
                        max_pages=1, # Adjust as needed, 1 page to get ~50 most recent
                        max_days_old=days
                    )
                    for key in overall_stats:
                        overall_stats[key] += stats.get(key, 0)
                except Exception as e:
                    logger.error(f"Error syncing category '{category}' in '{country_code}': {e}")
                    overall_stats['errors'] += 1 # Count this as a general error for the category sync

        logger.info(f"Adzuna recent jobs sync completed: {overall_stats}")
        return overall_stats
    
    def _process_job(self, job_data: Dict[str, Any], country_label: str = 'unknown') -> str:
        """
        Process a single job from Adzuna API data.
        
        Args:
            job_data: Dictionary containing job data from Adzuna.
            country_label: The country label for metrics.

        Returns:
            'created', 'updated', or 'skipped'
        """
        external_id = str(job_data.get('id', ''))
        if not external_id:
            logger.warning("Job missing ID, skipping")
            ADZUNA_JOBS_PROCESSED_TOTAL.labels(country=country_label, status='skipped_no_id').inc()
            return 'skipped'
        
        # Extract job information
        title = job_data.get('title', '')
        company_data = job_data.get('company', {})
        company = company_data.get('display_name', '') if company_data else ''
        
        location_data = job_data.get('location', {})
        location = location_data.get('display_name', '') if location_data else ''
        
        description = job_data.get('description', '')
        salary_min = job_data.get('salary_min')
        salary_max = job_data.get('salary_max')
        external_url = job_data.get('redirect_url', '')
        
        # Parse posting date
        created_str = job_data.get('created', '')
        posted_date = None
        if created_str:
            try:
                posted_date = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
            except ValueError:
                logger.warning(f"Could not parse date: {created_str}")
                posted_date = timezone.now()
        
        # Determine job type
        contract_type = job_data.get('contract_type', '')
        job_type = self._map_contract_type(contract_type)
        
        # Check if job already exists
        existing_job = Job.objects.filter(
            external_id=external_id,
            external_source='adzuna'
        ).first()
        
        job_defaults = {
            'title': title,
            'company': company,
            'location': location,
            'description': description,
            'job_type': job_type,
            'salary_min': salary_min,
            'salary_max': salary_max,
            'external_url': external_url,
            'external_source': 'adzuna',
            'posted_date': posted_date or timezone.now(),
            'processed_for_matching': False,  # Will be set to True after embedding generation
        }
        
        if existing_job:
            # Update existing job
            for field, value in job_defaults.items():
                if value is not None:
                    setattr(existing_job, field, value)
            existing_job.save()
            ADZUNA_JOBS_PROCESSED_TOTAL.labels(country=country_label, status='updated').inc()
            
            # Queue job for embedding generation if not already processed
            if not existing_job.processed_for_matching:
                from apps.integrations.tasks import generate_job_embeddings_and_ingest_for_rag
                generate_job_embeddings_and_ingest_for_rag.delay(str(existing_job.id))
            
            return 'updated'
        else:
            # Create new job
            job_defaults['external_id'] = external_id
            new_job = Job.objects.create(**job_defaults)
            ADZUNA_JOBS_PROCESSED_TOTAL.labels(country=country_label, status='created').inc()
            
            # Queue job for embedding generation
            from apps.integrations.tasks import generate_job_embeddings_and_ingest_for_rag
            generate_job_embeddings_and_ingest_for_rag.delay(str(new_job.id))
            
            return 'created'
    
    def _map_contract_type(self, contract_type: str) -> str:
        """Map Adzuna contract type to our job type choices."""
        mapping = {
            'permanent': 'full_time',
            'contract': 'contract',
            'temporary': 'temporary',
            'part_time': 'part_time',
            'internship': 'internship',
        }
        return mapping.get(contract_type.lower(), 'full_time')
