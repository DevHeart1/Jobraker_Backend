"""
Adzuna API integration service for job data fetching.
"""

import requests
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from apps.jobs.models import Job, JobSource

logger = logging.getLogger(__name__)


class AdzunaAPIClient:
    """
    Client for interacting with Adzuna API.
    Handles job fetching, search, and data processing.
    """
    
    BASE_URL = "https://api.adzuna.com/v1/api"
    
    def __init__(self):
        self.app_id = getattr(settings, 'ADZUNA_APP_ID', '')
        self.api_key = getattr(settings, 'ADZUNA_API_KEY', '')
        self.session = requests.Session()
        
        if not self.app_id or not self.api_key:
            logger.warning("Adzuna API credentials not configured")
    
    def _make_request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make authenticated request to Adzuna API."""
        if not self.app_id or not self.api_key:
            logger.warning("Adzuna API credentials not configured - using mock data")
            return self._get_mock_response(endpoint, params)
        
        # Add authentication parameters
        auth_params = {
            'app_id': self.app_id,
            'app_key': self.api_key,
        }
        
        if params:
            auth_params.update(params)
        
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            response = self.session.get(url, params=auth_params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Adzuna API request failed: {e}")
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
        where: str = "us",
        results_per_page: int = 50,
        page: int = 1,
        max_days_old: int = 7,
        sort_by: str = "date"
    ) -> Dict[str, Any]:
        """
        Search for jobs on Adzuna.
        
        Args:
            what: Job title or keywords
            where: Location (default: "us" for United States)
            results_per_page: Number of results per page (max 50)
            page: Page number to fetch
            max_days_old: How many days back to search
            sort_by: Sort order ("date", "salary", "relevance")
        
        Returns:
            Dictionary containing search results
        """
        endpoint = f"/jobs/{where}/search/{page}"
        
        params = {
            'what': what,
            'results_per_page': min(results_per_page, 50),
            'max_days_old': max_days_old,
            'sort_by': sort_by,
        }
        
        logger.info(f"Searching Adzuna jobs: what='{what}', where='{where}', page={page}")
        return self._make_request(endpoint, params)
    
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
        endpoint = f"/jobs/us/search/{page}"
        
        return self._make_request(endpoint, params)

    def get_job_details(self, job_id: str, country: str = "us") -> Dict[str, Any]:
        """Get detailed information about a specific job."""
        endpoint = f"/jobs/{country}/details/{job_id}"
        return self._make_request(endpoint)
    
    def get_job_details(self, job_id: str) -> Dict[str, Any]:
        """Get detailed information for a specific job."""
        endpoint = f"/jobs/us/{job_id}"
        return self._make_request(endpoint)
    
    def get_salary_data(self, job_title: str, location: str = "") -> Dict[str, Any]:
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
                'sync_frequency': 'hourly'
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
                    try:
                        result = self._process_job(job_data)
                        stats['processed'] += 1
                        if result == 'created':
                            stats['created'] += 1
                        elif result == 'updated':
                            stats['updated'] += 1
                    except Exception as e:
                        logger.error(f"Error processing job {job_data.get('id', 'unknown')}: {e}")
                        stats['errors'] += 1
                
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
    
    def _process_job(self, job_data: Dict[str, Any]) -> str:
        """
        Process a single job from Adzuna API data.
        
        Returns:
            'created', 'updated', or 'skipped'
        """
        external_id = str(job_data.get('id', ''))
        if not external_id:
            logger.warning("Job missing ID, skipping")
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
            source=self.job_source
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
            'posted_date': posted_date or timezone.now(),
            'source': self.job_source,
        }
        
        if existing_job:
            # Update existing job
            for field, value in job_defaults.items():
                if value is not None:
                    setattr(existing_job, field, value)
            existing_job.save()
            return 'updated'
        else:
            # Create new job
            job_defaults['external_id'] = external_id
            Job.objects.create(**job_defaults)
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
