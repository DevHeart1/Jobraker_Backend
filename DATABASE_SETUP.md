# Database Persistence & Vector Storage Setup Guide

## 🚀 Production Database Setup

### 1. PostgreSQL with pgvector Installation

#### Ubuntu/Debian
```bash
# Install PostgreSQL
sudo apt update
sudo apt install postgresql postgresql-contrib

# Install pgvector
sudo apt install postgresql-15-pgvector

# Or build from source
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install
```

#### Using Docker
```bash
# Run PostgreSQL with pgvector
docker run -d \
  --name jobraker-postgres \
  -e POSTGRES_DB=jobraker_prod \
  -e POSTGRES_USER=jobraker \
  -e POSTGRES_PASSWORD=your_secure_password \
  -p 5432:5432 \
  -v postgres_data:/var/lib/postgresql/data \
  pgvector/pgvector:pg15
```

### 2. Database Configuration

#### Environment Variables
```bash
# Production database settings
export DB_NAME=jobraker_prod
export DB_USER=jobraker
export DB_PASSWORD=your_secure_password
export DB_HOST=your_db_host
export DB_PORT=5432
export DB_SSLMODE=require
```

#### Setup Script
```bash
# Run the setup script
chmod +x setup_postgres.sh
./setup_postgres.sh
```

### 3. Django Database Setup

#### Run Migrations
```bash
# Apply database migrations
python manage.py migrate

# Set up pgvector indexes
python manage.py manage_db --operation setup
```

#### Initialize Vector Storage
```bash
# Sync existing jobs for embeddings
python manage.py manage_db --operation stats

# Process unprocessed jobs
python manage.py shell -c "
from apps.integrations.tasks_enhanced import sync_unprocessed_jobs
sync_unprocessed_jobs.delay()
"
```

## 🔧 Vector Storage Implementation

### Key Features
- **Automatic Embedding Generation**: Jobs and user profiles get embeddings automatically
- **Efficient Similarity Search**: Using pgvector's HNSW and IVFFlat indexes
- **Batch Processing**: Optimized for large datasets
- **Storage Management**: Automatic cleanup of old embeddings

### Vector Storage Service Usage

```python
from apps.common.vector_storage import VectorStorageService

# Initialize service
vector_service = VectorStorageService()

# Store embeddings
documents = [
    {
        'text_content': 'Job description...',
        'embedding': [0.1, 0.2, ...],  # 1536-dimensional vector
        'source_type': 'job_listing',
        'source_id': 'job_123',
        'metadata': {'company': 'TechCorp', 'location': 'SF'}
    }
]

stats = vector_service.store_embeddings_batch(documents)
print(f"Stored: {stats}")

# Search similar vectors
results = vector_service.search_similar_vectors(
    query_embedding=[0.1, 0.2, ...],
    top_k=10,
    similarity_threshold=0.8,
    source_types=['job_listing']
)
```

## 📊 Performance Optimization

### Database Indexes
```sql
-- HNSW index for fast approximate search
CREATE INDEX vector_document_embedding_hnsw_idx 
ON common_vectordocument 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- IVFFlat index for exact search
CREATE INDEX vector_document_embedding_ivfflat_idx 
ON common_vectordocument 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

### Query Optimization
```python
# Optimized similarity search
similar_docs = VectorDocument.objects.annotate(
    similarity=1 - CosineDistance('embedding', query_embedding)
).filter(
    similarity__gte=0.8,
    source_type='job_listing'
).order_by('-similarity')[:10]
```

## 🔄 Background Tasks

### Celery Configuration
```python
# Scheduled tasks for vector operations
CELERY_BEAT_SCHEDULE = {
    'sync-unprocessed-jobs': {
        'task': 'apps.integrations.tasks_enhanced.sync_unprocessed_jobs',
        'schedule': 3600.0,  # Every hour
    },
    'cleanup-old-embeddings': {
        'task': 'apps.integrations.tasks_enhanced.cleanup_old_embeddings',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
    'reindex-vector-database': {
        'task': 'apps.integrations.tasks_enhanced.reindex_vector_database',
        'schedule': crontab(hour=3, minute=0, day_of_week=1),  # Weekly
    },
}
```

### Task Monitoring
```bash
# Monitor Celery workers
celery -A jobraker worker -l info

# Monitor task execution
celery -A jobraker flower
```

## 🛠 Management Commands

### Database Management
```bash
# Show database statistics
python manage.py manage_db --operation stats

# Optimize database performance
python manage.py manage_db --operation optimize

# Clean up old data (dry run)
python manage.py manage_db --operation cleanup --days 30 --dry-run

# Reindex vector database
python manage.py manage_db --operation reindex

# Create backup
python manage.py manage_db --operation backup
```

### Vector Operations
```bash
# Process unprocessed jobs
python manage.py shell -c "
from apps.integrations.tasks_enhanced import sync_unprocessed_jobs
sync_unprocessed_jobs.delay()
"

# Batch process specific jobs
python manage.py shell -c "
from apps.integrations.tasks_enhanced import batch_process_jobs_for_embeddings
job_ids = ['job1', 'job2', 'job3']
batch_process_jobs_for_embeddings.delay(job_ids)
"
```

## 📈 Monitoring & Maintenance

### Health Checks
```bash
# Check system health
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/v1/common/health/

# Check vector storage statistics
python manage.py manage_db --operation stats
```

### Performance Monitoring
```python
# Monitor vector operations
from apps.common.vector_storage import VectorStorageService

vector_service = VectorStorageService()
stats = vector_service.get_storage_stats()

print(f"Total documents: {stats['total_documents']}")
print(f"Storage size: {stats['storage_size']}")
print(f"By source type: {stats['by_source_type']}")
```

### Backup Strategy
```bash
# Automated backup script
#!/bin/bash
BACKUP_DIR="/backups/jobraker"
DATE=$(date +%Y%m%d_%H%M%S)

# Create database backup
pg_dump -h $DB_HOST -U $DB_USER -d $DB_NAME > $BACKUP_DIR/db_$DATE.sql

# Create embeddings backup
python manage.py manage_db --operation backup

# Clean old backups (keep 7 days)
find $BACKUP_DIR -name "*.sql" -mtime +7 -delete
```

## 🔒 Security Considerations

### Database Security
```bash
# Enable SSL
export DB_SSLMODE=require

# Use connection pooling
export DB_CONN_MAX_AGE=60

# Set up read replicas for scaling
export DB_READ_REPLICA_HOST=replica.example.com
```

### Vector Data Security
```python
# Encrypt sensitive embeddings
VECTOR_ENCRYPTION = {
    'ENABLE_ENCRYPTION': True,
    'ENCRYPTION_KEY': os.environ.get('VECTOR_ENCRYPTION_KEY'),
    'ALGORITHM': 'AES-256-GCM'
}
```

## 🚀 Deployment Checklist

- [ ] PostgreSQL with pgvector installed
- [ ] Database migrations applied
- [ ] Vector indexes created
- [ ] Celery workers running
- [ ] Background tasks scheduled
- [ ] Monitoring configured
- [ ] Backup strategy implemented
- [ ] SSL certificates configured
- [ ] Environment variables set
- [ ] Health checks passing

## 📚 Additional Resources

- [pgvector Documentation](https://github.com/pgvector/pgvector)
- [PostgreSQL Performance Tuning](https://wiki.postgresql.org/wiki/Performance_Optimization)
- [Django Database Optimization](https://docs.djangoproject.com/en/stable/topics/db/optimization/)
- [Celery Best Practices](https://docs.celeryq.dev/en/stable/userguide/tasks.html#best-practices)
