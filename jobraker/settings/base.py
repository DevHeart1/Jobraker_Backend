"""
Django settings for jobraker project.

Base settings shared across all environments.
"""

import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-change-me-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DJANGO_DEBUG', 'False').lower() == 'true'

ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', '').split(',') if os.getenv('DJANGO_ALLOWED_HOSTS') else []

# Application definition
DJANGO_APPS = [
    'jazzmin',  # Enhanced admin interface
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'drf_spectacular',
    'corsheaders',
    'django_celery_beat',
    'django_celery_results',
    'django_elasticsearch_dsl', # Added for Elasticsearch
]

LOCAL_APPS = [
    'apps.accounts',
    'apps.jobs',
    'apps.chat',
    'apps.notifications',
    'apps.integrations',
    'apps.common', # Added the new common app
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# Custom User Model
AUTH_USER_MODEL = 'accounts.User'

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'jobraker.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'jobraker.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'jobraker_db'),
        'USER': os.getenv('DB_USER', 'jobraker_user'),
        'PASSWORD': os.getenv('DB_PASSWORD', 'jobraker_pass'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

# Parse database URL if provided
DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL:
    try:
        import dj_database_url
        DATABASES['default'] = dj_database_url.parse(DATABASE_URL)
    except ImportError:
        # dj_database_url not installed, use manual parsing
        pass

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# JWT Configuration
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
}

# API Documentation
SPECTACULAR_SETTINGS = {
    'TITLE': 'Jobraker API',
    'DESCRIPTION': 'AI-powered autonomous job search and application platform',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# Cache Configuration (Redis)
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

# Celery Configuration
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# External API Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
ADZUNA_APP_ID = os.getenv('ADZUNA_APP_ID', '')
ADZUNA_API_KEY = os.getenv('ADZUNA_API_KEY', '')
SKYVERN_API_KEY = os.getenv('SKYVERN_API_KEY', '')

# Pinecone Configuration
PINECONE_API_KEY = os.getenv('PINECONE_API_KEY', None)
PINECONE_ENVIRONMENT = os.getenv('PINECONE_ENVIRONMENT', None)
PINECONE_INDEX_NAME = os.getenv('PINECONE_INDEX_NAME', 'jobraker-default-index')
PINECONE_NAMESPACE = os.getenv('PINECONE_NAMESPACE', 'jobraker-default-ns') # Default namespace for Pinecone
PINECONE_INDEX_DIMENSION = int(os.getenv('PINECONE_INDEX_DIMENSION', '1536')) # Default dimension for embeddings
PINECONE_INDEX_METRIC = os.getenv('PINECONE_INDEX_METRIC', 'cosine') # Default metric for embeddings

# Security Configuration
CORS_ALLOWED_ORIGINS = os.getenv('CORS_ALLOWED_ORIGINS', '').split(',') if os.getenv('CORS_ALLOWED_ORIGINS') else []
CORS_ALLOW_CREDENTIALS = True

# Jazzmin Admin Configuration
JAZZMIN_SETTINGS = {
    'site_title': 'Jobraker Admin',
    'site_header': 'Jobraker Administration',
    'site_brand': 'Jobraker',
    'welcome_sign': 'Welcome to Jobraker Admin Panel',
    'copyright': 'Jobraker Inc.',
}

# Elasticsearch Configuration
ELASTICSEARCH_URL = os.getenv('ELASTICSEARCH_URL', 'http://localhost:9200')

ELASTICSEARCH_DSL = {
    'default': {
        'hosts': ELASTICSEARCH_URL,
        # 'http_auth': ('username', 'password'), # Optional: if your ES is secured
        # 'timeout': 30, # Optional: global timeout for requests
    },
}

ELASTICSEARCH_JOB_INDEX_NAME = os.getenv('ELASTICSEARCH_JOB_INDEX_NAME', 'jobraker-jobs')


# Optional: If you want to auto-sync model updates to Elasticsearch using signals
# ELASTICSEARCH_DSL_AUTOSYNC = True # Default is False. Manage via signals manually for more control.
# ELASTICSEARCH_DSL_AUTO_REFRESH = False # Default is False. Controls refresh after auto-sync.
