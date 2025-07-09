# Generated migration for pgvector setup

from django.db import migrations, models
import django.contrib.postgres.indexes


class Migration(migrations.Migration):

    dependencies = [
        ('common', '0001_initial'),
    ]

    operations = [
        # Create pgvector extension
        migrations.RunSQL(
            "CREATE EXTENSION IF NOT EXISTS vector;",
            reverse_sql="DROP EXTENSION IF EXISTS vector;",
        ),
        
        # Add HNSW index for vector similarity search
        migrations.RunSQL(
            """
            CREATE INDEX IF NOT EXISTS vector_document_embedding_hnsw_idx 
            ON common_vectordocument 
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
            """,
            reverse_sql="DROP INDEX IF EXISTS vector_document_embedding_hnsw_idx;",
        ),
        
        # Add IVFFlat index as alternative for large datasets
        migrations.RunSQL(
            """
            CREATE INDEX IF NOT EXISTS vector_document_embedding_ivfflat_idx 
            ON common_vectordocument 
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100);
            """,
            reverse_sql="DROP INDEX IF EXISTS vector_document_embedding_ivfflat_idx;",
        ),
        
        # Create compound indexes for common queries
        migrations.RunSQL(
            """
            CREATE INDEX IF NOT EXISTS vector_document_source_type_created_idx 
            ON common_vectordocument (source_type, created_at DESC);
            """,
            reverse_sql="DROP INDEX IF EXISTS vector_document_source_type_created_idx;",
        ),
        
        # Add statistics for query planner
        migrations.RunSQL(
            """
            CREATE STATISTICS IF NOT EXISTS vector_document_stats 
            ON source_type, source_id, created_at 
            FROM common_vectordocument;
            """,
            reverse_sql="DROP STATISTICS IF EXISTS vector_document_stats;",
        ),
    ]
