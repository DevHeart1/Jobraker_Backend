# Jobraker Backend Structure Documentation

[![Version](https://img.shields.io/badge/version-1.0-blue.svg)]()
[![Status](https://img.shields.io/badge/status-draft-yellow.svg)]()
[![Last Updated](https://img.shields.io/badge/last%20updated-June%2015%2C%202025-green.svg)]()

---

## Table of Contents
1. [Directory Structure Overview](#1-directory-structure-overview)
2. [Core Django Settings](#2-core-django-settings)
3. [Application Structure](#3-application-structure)
4. [API Endpoints](#4-api-endpoints)
5. [Task Management](#5-task-management)
6. [Security & Compliance](#6-security--compliance)
7. [Monitoring & Logging](#7-monitoring--logging)
8. [Conclusion](#8-conclusion)

---

## 1. Directory Structure Overview

```text
jobraker/
│
├── jobraker/                        # Main Django project directory
│   ├── __init__.py
│   ├── settings.py                  # Settings for the entire project
│   ├── urls.py                      # Global URLs for the project
│   ├── wsgi.py                      # WSGI entry point for deployment
│   └── asgi.py                      # ASGI entry point for WebSockets
│
├── apps/                            # Custom Django apps for Jobraker functionality
│   ├── accounts/                    # User authentication and profile management
│   ├── jobs/                        # Job search and job-related functionality
│   ├── chat/                        # AI chat functionality and interactions
│   ├── notifications/               # Notification management
│   └── integrations/                # Third-party integrations (Adzuna, Skyvern, OpenAI)
│
├── static/                          # Static files (CSS, JS, images)
├── templates/                       # HTML templates (if needed)
└── manage.py                        # Django management script
```

- **Modular App Design:** Each feature is encapsulated in its own Django app, supporting maintainability and scalability.
- **Separation of Concerns:** Business logic, API endpoints, and admin configurations are isolated per app.

---

## 2. Core Django Settings (`settings.py`)

### Installed Apps
```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'jazzmin',  # Admin interface customization
    'apps.accounts',
    'apps.jobs',
    'apps.chat',
    'apps.notifications',
    'apps.integrations',
]
```
- **jazzmin:** Modernizes the Django admin interface.
- **rest_framework:** Enables RESTful API development.
- **Custom Apps:** Modularizes features for maintainability.

### Database Configuration
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'jobraker_db',
        'USER': 'jobraker_user',
        'PASSWORD': 'your_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```
- **PostgreSQL:** Robust, scalable RDBMS for all structured data.

### Celery Configuration
```python
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
```
- **Celery + Redis:** Asynchronous task processing for background jobs.

### JWT Authentication
```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
}
```
- **JWT:** Secure, stateless authentication for APIs.

### CORS Configuration
```python
CORS_ALLOWED_ORIGINS = [
    'https://yourfrontend.com',
]
```
- **CORS:** Secure cross-origin communication with the frontend.

---

## 3. Application Structure

### apps/accounts/
- **Purpose:** User authentication and profile management.
- **Models:**
    - `User`: Extends Django User for additional profile info.
    - `Profile`: Stores job preferences, application status, resume data.

### apps/jobs/
- **Purpose:** Job search, job listings, and job applications.
- **Models:**
    - `Job`: Stores job listing data from Adzuna.
    - `Application`: Tracks user job applications.
- **Views:**
    - `JobViewSet`: Search and view job details.
    - `ApplicationViewSet`: Manage job applications.

### apps/chat/
- **Purpose:** AI chat interactions (GPT-4.1 Mini).
- **Models:**
    - `ChatMessage`: Stores chat history.
- **Views:**
    - `ChatMessageViewSet`: Handles chat messages.
- **Tasks:**
    - `generate_bot_reply`: Celery task for AI responses.

### apps/notifications/
- **Purpose:** Notifications for job application statuses and alerts.
- **Models:**
    - `Notification`: Stores notifications.
- **Views:**
    - `NotificationViewSet`: Retrieve notifications.

### apps/integrations/
- **Purpose:** Integrations with Adzuna, Skyvern, OpenAI.
- **Models:**
    - `Integration`: Stores API credentials/settings.
- **Views:**
    - `IntegrationViewSet`: Manage integrations.
- **Tasks:**
    - `fetch_adzuna_jobs`, `auto_apply_jobs`: Celery tasks for API interaction.

---

## 4. API Endpoints

### Job Listings API
```python
# apps/jobs/views.py
class JobViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Job.objects.all().order_by('-posted_at')
    serializer_class = JobSerializer
    permission_classes = [permissions.IsAuthenticated]
    # Filters: title, location, salary, etc.
```
- **Endpoint:** `/api/jobs/` (GET)
- **Query Params:** title, location, remote, salary, etc.

### Job Application API
```python
# apps/jobs/views.py
class ApplicationViewSet(viewsets.ModelViewSet):
    queryset = Application.objects.all()
    serializer_class = ApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]
```
- **Endpoint:** `/api/applications/` (POST, GET)

### AI Chat API
```python
# apps/chat/views.py
class ChatMessageViewSet(viewsets.ModelViewSet):
    queryset = ChatMessage.objects.all()
    serializer_class = ChatMessageSerializer
    permission_classes = [permissions.IsAuthenticated]
```
- **Endpoint:** `/api/chat/` (POST, GET)

### Integration API
```python
# apps/integrations/views.py
class IntegrationViewSet(viewsets.ModelViewSet):
    queryset = Integration.objects.all()
    serializer_class = IntegrationSerializer
    permission_classes = [permissions.IsAuthenticated]
```
- **Endpoint:** `/api/integrations/` (POST, GET)

---

## 5. Task Management

### Celery Tasks
- `generate_bot_reply`: Generates AI-powered chat responses.
- `fetch_adzuna_jobs`: Fetches new job listings from Adzuna.
- `auto_apply_jobs`: Automatically applies for jobs based on user criteria.

### Scheduling Tasks
- **Celery Beat:** Schedules periodic tasks (e.g., job fetching every 30 minutes, auto-apply hourly).

---

## 6. Security & Compliance

### Authentication & Authorization
- **JWT Authentication:** Secure, stateless user authentication.
- **Role-Based Access:** Admins have full access; users access only their data.

### Data Privacy & Compliance
- **GDPR Compliance:** Users can delete accounts/data; data encrypted in transit (TLS) and at rest (AES-256).
- **RBAC:** Access to sensitive data is role-restricted.

---

## 7. Monitoring & Logging

### Prometheus & Grafana
- **Metrics:** Task execution times, API response times, job statuses.
- **Alerting:** Threshold-based alerts (e.g., Celery retries, high latency).

### Sentry
- **Error Monitoring:** Tracks/logs errors in job applications, API failures, AI processing.

---

## 8. Conclusion

The Jobraker backend structure is modular, scalable, and secure, supporting efficient job automation, AI-driven features, and robust integrations. This architecture enables rapid feature development, easy maintenance, and high performance, while ensuring compliance and a seamless user experience.

---

*This document is maintained by the Jobraker engineering team and is updated as the platform evolves.*
