"""
URL patterns for jobs app.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Router for ViewSets
router = DefaultRouter()
router.register(r'jobs', views.JobViewSet, basename='job')
router.register(r'applications', views.ApplicationViewSet, basename='application')
router.register(r'alerts', views.JobAlertViewSet, basename='jobalert') # Added JobAlertViewSet

urlpatterns = [
    # Job search and management
    path('search/', views.JobSearchView.as_view(), name='job_search'),
    path('recommendations/', views.JobRecommendationsView.as_view(), name='job_recommendations'),
    path('auto-apply/', views.AutoApplyView.as_view(), name='auto_apply'),
    
    # Application management
    path('applications/bulk-apply/', views.BulkApplyView.as_view(), name='bulk_apply'),
    
    # Include router URLs
    path('', include(router.urls)),
]
