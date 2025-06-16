"""
Development settings for jobraker project.
"""

from .base import *

# Debug settings
DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0', '*']

# Database for development
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Override with PostgreSQL if DATABASE_URL is provided
DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL:
    try:
        import dj_database_url
        DATABASES['default'] = dj_database_url.parse(DATABASE_URL)
    except ImportError:
        # dj_database_url not installed, use environment variables
        pass

# Development-specific middleware
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# CORS settings for development
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:8080',
    'http://127.0.0.1:8080',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'https://localhost:8000',
    'https://127.0.0.1:8000',
]

CORS_ALLOW_ALL_ORIGINS = True  # Only for development

# CSRF settings for development
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'https://localhost:8000',
    'https://127.0.0.1:8000',
    'http://0.0.0.0:8000',
]

# Disable HTTPS redirect in development
SECURE_SSL_REDIRECT = False

# Email backend for development (console)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Logging for development
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'jobraker': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}

# Development tools
INSTALLED_APPS += [
    'django_extensions',
]

# Celery eager execution for development
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# External API Integrations
ADZUNA_APP_ID = os.getenv('ADZUNA_APP_ID', '')
ADZUNA_API_KEY = os.getenv('ADZUNA_API_KEY', '')

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4')

SKYVERN_API_KEY = os.getenv('SKYVERN_API_KEY', '')
SKYVERN_BASE_URL = os.getenv('SKYVERN_BASE_URL', 'https://api.skyvern.com')

# Celery Configuration
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_ENABLE_UTC = True

# Redis Configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/1')

# Cache Configuration
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}
