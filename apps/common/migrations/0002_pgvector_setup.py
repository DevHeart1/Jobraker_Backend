# Generated migration for pgvector setup

import django.contrib.postgres.indexes
from django.db import connection, migrations, models


def setup_pgvector(apps, schema_editor):
    """Set up pgvector extension and indexes - only for PostgreSQL"""
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            # Create pgvector extension
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")

            # Add HNSW index for vector similarity search
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS vector_document_embedding_hnsw_idx 
                ON common_vectordocument 
                USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64);
            """
            )

            # Add IVFFlat index as alternative for large datasets
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS vector_document_embedding_ivfflat_idx 
                ON common_vectordocument 
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
            """
            )

            # Create compound indexes for common queries
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS vector_document_source_type_created_idx 
                ON common_vectordocument (source_type, created_at DESC);
            """
            )

            # Add statistics for query planner
            cursor.execute(
                """
                CREATE STATISTICS IF NOT EXISTS vector_document_stats 
                ON source_type, source_id, created_at 
                FROM common_vectordocument;
            """
            )


def reverse_pgvector(apps, schema_editor):
    """Reverse pgvector setup - only for PostgreSQL"""
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("DROP STATISTICS IF EXISTS vector_document_stats;")
            cursor.execute("DROP INDEX IF EXISTS vector_document_embedding_hnsw_idx;")
            cursor.execute(
                "DROP INDEX IF EXISTS vector_document_embedding_ivfflat_idx;"
            )
            cursor.execute(
                "DROP INDEX IF EXISTS vector_document_source_type_created_idx;"
            )
            cursor.execute("DROP EXTENSION IF EXISTS vector;")


class Migration(migrations.Migration):

    dependencies = [
        ("common", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(setup_pgvector, reverse_pgvector),
    ]
