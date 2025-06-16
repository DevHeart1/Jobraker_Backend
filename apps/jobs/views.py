from django.shortcuts import render
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Job, Application, JobAlert, SavedJob


class JobViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing jobs.
    """
    queryset = Job.objects.all()
    permission_classes = [permissions.IsAuthenticated]


class ApplicationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing job applications.
    """
    queryset = Application.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        This view should return applications for the currently authenticated user.
        """
        return Application.objects.filter(user=self.request.user)


class JobAlertViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing job alerts.
    """
    queryset = JobAlert.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        This view should return job alerts for the currently authenticated user.
        """
        return JobAlert.objects.filter(user=self.request.user)


class SavedJobViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing saved jobs.
    """
    queryset = SavedJob.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        This view should return saved jobs for the currently authenticated user.
        """
        return SavedJob.objects.filter(user=self.request.user)
