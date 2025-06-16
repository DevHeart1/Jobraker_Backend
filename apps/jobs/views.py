from django.shortcuts import render
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiExample, OpenApiResponse
from drf_spectacular.openapi import OpenApiTypes
from .models import Job, Application, SavedJob, JobAlert, JobSource
from .serializers import (
    JobSerializer, JobListSerializer, ApplicationSerializer, SavedJobSerializer,
    JobAlertSerializer, JobSearchSerializer, BulkApplySerializer,
    JobSearchResultSerializer, JobRecommendationSerializer, ApplicationStatsSerializer,
    SuccessResponseSerializer, ErrorResponseSerializer
)

User = get_user_model()


class JobViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing jobs.
    """
    queryset = Job.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Filter jobs based on user preferences and permissions.
        """
        queryset = Job.objects.all()
        
        # Add filtering logic here
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(title__icontains=search)
        
        location = self.request.query_params.get('location', None)
        if location:
            queryset = queryset.filter(location__icontains=location)
        
        company = self.request.query_params.get('company', None)
        if company:
            queryset = queryset.filter(company__icontains=company)
        
        return queryset.order_by('-posted_date')
    
    @action(detail=True, methods=['post'])
    def save(self, request, pk=None):
        """
        Save a job for later.
        """
        job = self.get_object()
        saved_job, created = SavedJob.objects.get_or_create(
            user=request.user,
            job=job
        )
        
        if created:
            return Response({'message': 'Job saved successfully'})
        else:
            return Response({'message': 'Job already saved'})
    
    @action(detail=True, methods=['delete'])
    def unsave(self, request, pk=None):
        """
        Remove a job from saved jobs.
        """
        job = self.get_object()
        try:
            saved_job = SavedJob.objects.get(user=request.user, job=job)
            saved_job.delete()
            return Response({'message': 'Job removed from saved jobs'})
        except SavedJob.DoesNotExist:
            return Response(
                {'error': 'Job not found in saved jobs'}, 
                status=status.HTTP_404_NOT_FOUND
            )


class ApplicationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing job applications.
    """
    queryset = Application.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Return applications for the current user only.
        """
        return Application.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        """
        Create application for the current user.
        """
        serializer.save(user=self.request.user)


class JobSearchView(APIView):
    """
    Advanced job search with filters and AI-powered matching.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """
        Search jobs with advanced filters.
        """
        # TODO: Implement advanced search with AI matching
        queryset = Job.objects.all()
        
        # Basic filters
        filters = {}
        if request.query_params.get('title'):
            filters['title__icontains'] = request.query_params.get('title')
        if request.query_params.get('company'):
            filters['company__icontains'] = request.query_params.get('company')
        if request.query_params.get('location'):
            filters['location__icontains'] = request.query_params.get('location')
        if request.query_params.get('remote'):
            filters['is_remote'] = request.query_params.get('remote').lower() == 'true'
        
        if filters:
            queryset = queryset.filter(**filters)
        
        # Salary range filter
        min_salary = request.query_params.get('min_salary')
        max_salary = request.query_params.get('max_salary')
        if min_salary:
            queryset = queryset.filter(salary_min__gte=min_salary)
        if max_salary:
            queryset = queryset.filter(salary_max__lte=max_salary)
        
        jobs = queryset.order_by('-posted_date')[:50]  # Limit results
        
        # TODO: Add AI-powered job matching and ranking
        
        return Response({
            'count': jobs.count() if hasattr(jobs, 'count') else len(jobs),
            'results': [
                {
                    'id': job.id,
                    'title': job.title,
                    'company': job.company,
                    'location': job.location,
                    'salary_min': job.salary_min,
                    'salary_max': job.salary_max,
                    'is_remote': job.is_remote,
                    'posted_date': job.posted_date,
                    'url': job.url,
                } for job in jobs
            ]
        })


class JobRecommendationsView(APIView):
    """
    AI-powered job recommendations based on user profile and preferences.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """
        Get personalized job recommendations.
        """
        # TODO: Implement AI-powered job recommendations
        # This would use the user's profile, skills, experience, and preferences
        # to recommend relevant jobs using vector similarity search
        
        user = request.user
        
        # For now, return a simple set of recent jobs
        # This should be replaced with actual AI recommendations
        jobs = Job.objects.all().order_by('-posted_date')[:10]
        
        return Response({
            'message': 'AI-powered recommendations coming soon',
            'recommendations': [
                {
                    'id': job.id,
                    'title': job.title,
                    'company': job.company,
                    'location': job.location,
                    'match_score': 0.85,  # Placeholder score
                    'reasons': ['Skills match', 'Location preference']  # Placeholder
                } for job in jobs
            ]
        })


class AutoApplyView(APIView):
    """
    Automated job application using AI and Skyvern integration.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Start automated application process for selected jobs.
        """
        job_ids = request.data.get('job_ids', [])
        
        if not job_ids:
            return Response(
                {'error': 'No job IDs provided'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # TODO: Implement auto-apply using Skyvern
        # This would:
        # 1. Validate user has complete profile and resume
        # 2. Queue jobs for automated application
        # 3. Use Skyvern to fill out application forms
        # 4. Track application status
        
        return Response({
            'message': 'Auto-apply feature coming soon',
            'queued_jobs': len(job_ids)
        })


class BulkApplyView(APIView):
    """
    Apply to multiple jobs at once.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Apply to multiple jobs with bulk operation.
        """
        job_ids = request.data.get('job_ids', [])
        cover_letter = request.data.get('cover_letter', '')
        
        if not job_ids:
            return Response(
                {'error': 'No job IDs provided'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        applied_jobs = []
        failed_jobs = []
        
        for job_id in job_ids:
            try:
                job = Job.objects.get(id=job_id)
                
                # Check if already applied
                if Application.objects.filter(user=request.user, job=job).exists():
                    failed_jobs.append({
                        'job_id': job_id,
                        'error': 'Already applied to this job'
                    })
                    continue
                
                # Create application
                application = Application.objects.create(
                    user=request.user,
                    job=job,
                    cover_letter=cover_letter,
                    status='submitted'
                )
                
                applied_jobs.append({
                    'job_id': job_id,
                    'application_id': application.id,
                    'job_title': job.title,
                    'company': job.company
                })
                
            except Job.DoesNotExist:
                failed_jobs.append({
                    'job_id': job_id,
                    'error': 'Job not found'
                })
            except Exception as e:
                failed_jobs.append({
                    'job_id': job_id,
                    'error': str(e)
                })
        
        return Response({
            'message': f'Applied to {len(applied_jobs)} jobs',
            'applied_jobs': applied_jobs,
            'failed_jobs': failed_jobs
        })
