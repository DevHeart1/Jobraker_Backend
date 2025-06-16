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
            raise ValueError("Adzuna API credentials not configured")
        
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
            raise
    
    def search_jobs(
        self,
        what: str = "",
        where: str = "",
        results_per_page: int = 50,
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
        endpoint = "/jobs/us/search/1"  # US jobs, page 1 by default
        
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
            name='Adzuna',
            defaults={
                'api_url': 'https://api.adzuna.com',
                'is_active': True,
                'sync_frequency_hours': 6,  # Sync every 6 hours
            }
        )
        if created:
            logger.info("Created Adzuna job source")
        return source
    
    def _parse_job_data(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Adzuna job data into our Job model format."""
        
        # Extract salary information
        salary_min = job_data.get('salary_min')
        salary_max = job_data.get('salary_max')
        
        # Parse location
        location_data = job_data.get('location', {})
        location_display = location_data.get('display_name', '')
        
        # Determine job type from contract info
        contract_type = job_data.get('contract_type', '').lower()
        job_type = 'full_time'  # Default
        if 'part' in contract_type:
            job_type = 'part_time'
        elif 'contract' in contract_type:
            job_type = 'contract'
        elif 'temporary' in contract_type:
            job_type = 'temporary'
        
        # Parse posted date
        created_date = job_data.get('created')
        if created_date:
            try:
                posted_date = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                posted_date = timezone.now()
        else:
            posted_date = timezone.now()
        
        return {
            'external_id': str(job_data.get('id', '')),
            'title': job_data.get('title', '')[:200],  # Truncate to model limit
            'company': job_data.get('company', {}).get('display_name', '')[:100],
            'description': job_data.get('description', ''),
            'job_type': job_type,
            'location': location_display[:200],
            'city': location_data.get('area', [])[:100] if location_data.get('area') else '',
            'country': 'US',  # Adzuna US API
            'salary_min': salary_min,
            'salary_max': salary_max,
            'salary_currency': 'USD',
            'application_url': job_data.get('redirect_url', ''),
            'posted_date': posted_date,
            'status': 'active',
        }
    
    def process_job(self, job_data: Dict[str, Any]) -> Optional[Job]:
        """Process a single job from Adzuna API."""
        try:
            parsed_data = self._parse_job_data(job_data)
            
            # Check if job already exists
            existing_job = Job.objects.filter(
                source=self.job_source,
                external_id=parsed_data['external_id']
            ).first()
            
            if existing_job:
                # Update existing job
                for field, value in parsed_data.items():
                    setattr(existing_job, field, value)
                existing_job.save()
                logger.debug(f"Updated job: {existing_job.title}")
                return existing_job
            else:
                # Create new job
                job = Job.objects.create(
                    source=self.job_source,
                    **parsed_data
                )
                logger.debug(f"Created job: {job.title}")
                return job
                
        except Exception as e:
            logger.error(f"Error processing job data: {e}")
            return None
    
    def fetch_and_process_jobs(
        self,
        what: str = "",
        where: str = "",
        max_pages: int = 5,
        max_days_old: int = 7,
        **search_params
    ) -> Dict[str, int]:
        """
        Fetch jobs from Adzuna API and process them.
        
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
        
        try:
            # First request to get total count
            response = self.client.search_jobs(
                what=what,
                where=where,
                page=1,
                max_days_old=max_days_old,
                **search_params
            )
            
            stats['total_found'] = response.get('count', 0)
            total_pages = min(
                max_pages,
                (stats['total_found'] // 50) + 1  # 50 results per page
            )
            
            logger.info(f"Fetching {stats['total_found']} jobs across {total_pages} pages")
            
            # Process each page
            for page in range(1, total_pages + 1):
                try:
                    if page > 1:
                        response = self.client.search_jobs(
                            what=what,
                            where=where,
                            page=page,
                            max_days_old=max_days_old,
                            **search_params
                        )
                    
                    jobs = response.get('results', [])
                    
                    for job_data in jobs:
                        existing_count = Job.objects.filter(
                            source=self.job_source,
                            external_id=str(job_data.get('id', ''))
                        ).count()
                        
                        job = self.process_job(job_data)
                        if job:
                            stats['processed'] += 1
                            if existing_count == 0:
                                stats['created'] += 1
                            else:
                                stats['updated'] += 1
                        else:
                            stats['errors'] += 1
                
                except Exception as e:
                    logger.error(f"Error processing page {page}: {e}")
                    stats['errors'] += len(response.get('results', []))
            
            # Update source last sync time
            self.job_source.last_sync = timezone.now()
            self.job_source.save(update_fields=['last_sync'])
            
        except Exception as e:
            logger.error(f"Error fetching jobs from Adzuna: {e}")
            stats['errors'] += 1
        
        return stats
    
    def sync_recent_jobs(self, days: int = 1) -> Dict[str, int]:
        """Sync recent jobs from multiple categories."""
        
        # Common job categories to search
        categories = [
            "software engineer",
            "data scientist",
            "product manager",
            "marketing manager",
            "sales representative",
            "customer service",
            "administrative assistant",
            "project manager",
            "business analyst",
            "designer",
        ]
        
        total_stats = {
            'total_found': 0,
            'processed': 0,
            'created': 0,
            'updated': 0,
            'errors': 0,
        }
        
        for category in categories:
            logger.info(f"Syncing jobs for category: {category}")
            stats = self.fetch_and_process_jobs(
                what=category,
                max_pages=2,  # Limit to avoid rate limiting
                max_days_old=days,
            )
            
            # Aggregate stats
            for key in total_stats:
                total_stats[key] += stats[key]
        
        logger.info(f"Adzuna sync completed: {total_stats}")
        return total_stats
