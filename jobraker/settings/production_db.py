"""
Production database configuration with pgvector optimization.
"""

import os

from .base import *

# Database configuration for production
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "jobraker_prod"),
        "USER": os.environ.get("DB_USER", "jobraker"),
        "PASSWORD": os.environ.get("DB_PASSWORD"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "OPTIONS": {
            "sslmode": os.environ.get("DB_SSLMODE", "prefer"),
            "connect_timeout": 30,
            "application_name": "jobraker_backend",
        },
        "CONN_MAX_AGE": 60,  # Connection pooling
        "ATOMIC_REQUESTS": True,  # Wrap each request in a transaction
    }
}

# pgvector specific configuration
DATABASES["default"]["OPTIONS"].update(
    {
        "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        "charset": "utf8mb4",
    }
)

# Production-specific database settings
if os.environ.get("DATABASE_URL"):
    # Parse DATABASE_URL for platforms like Heroku
    import dj_database_url

    DATABASES["default"] = dj_database_url.parse(
        os.environ.get("DATABASE_URL"), conn_max_age=60
    )

# Vector search configuration
VECTOR_SEARCH = {
    "DEFAULT_DIMENSIONS": 1536,  # OpenAI embedding dimensions
    "SIMILARITY_THRESHOLD": 0.7,
    "DEFAULT_TOP_K": 10,
    "HNSW_M": 16,  # HNSW index parameter
    "HNSW_EF_CONSTRUCTION": 64,  # HNSW index parameter
    "IVFFLAT_LISTS": 100,  # IVFFlat index parameter
}

# Connection pooling for production
DATABASES["default"]["OPTIONS"]["MAX_CONNS"] = 20
DATABASES["default"]["OPTIONS"]["MIN_CONNS"] = 5

# Query optimization
DATABASES["default"]["OPTIONS"]["QUERY_TIMEOUT"] = 30
DATABASES["default"]["OPTIONS"]["STATEMENT_TIMEOUT"] = 60000  # 60 seconds

# Production logging for database queries
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "db_file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": "logs/database.log",
        },
        "vector_file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": "logs/vector_operations.log",
        },
    },
    "loggers": {
        "django.db.backends": {
            "handlers": ["db_file"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.common.vector_storage": {
            "handlers": ["vector_file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# Cache configuration for vector operations
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "KEY_PREFIX": "jobraker_cache",
        "TIMEOUT": 3600,  # 1 hour default timeout
    },
    "vector_cache": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/2"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "KEY_PREFIX": "vector_cache",
        "TIMEOUT": 7200,  # 2 hours for vector results
    },
}

# Performance monitoring
PERFORMANCE_MONITORING = {
    "TRACK_VECTOR_OPERATIONS": True,
    "SLOW_QUERY_THRESHOLD": 1.0,  # Log queries taking more than 1 second
    "TRACK_EMBEDDING_GENERATION": True,
}

# Backup configuration
BACKUP_SETTINGS = {
    "ENABLE_AUTOMATIC_BACKUPS": True,
    "BACKUP_SCHEDULE": "0 2 * * *",  # Daily at 2 AM
    "BACKUP_RETENTION_DAYS": 7,
    "BACKUP_LOCATION": os.environ.get("BACKUP_LOCATION", "/backups/"),
}

# Security settings for production
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
