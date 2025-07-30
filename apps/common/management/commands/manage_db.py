"""
Database management utilities for Jobraker Backend.
"""

import logging
import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

from apps.common.vector_storage import VectorStorageService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Manage database operations including vector storage optimization"

    def add_arguments(self, parser):
        parser.add_argument(
            "--operation",
            type=str,
            choices=["setup", "optimize", "stats", "cleanup", "reindex", "backup"],
            required=True,
            help="Database operation to perform",
        )
        parser.add_argument(
            "--days", type=int, default=30, help="Number of days for cleanup operations"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without actually doing it",
        )

    def handle(self, *args, **options):
        operation = options["operation"]

        if operation == "setup":
            self.setup_database()
        elif operation == "optimize":
            self.optimize_database()
        elif operation == "stats":
            self.show_database_stats()
        elif operation == "cleanup":
            self.cleanup_database(options["days"], options["dry_run"])
        elif operation == "reindex":
            self.reindex_database()
        elif operation == "backup":
            self.backup_database()

    def setup_database(self):
        """Set up database with pgvector extension and indexes."""
        self.stdout.write(self.style.SUCCESS("🚀 Setting up database..."))

        try:
            with connection.cursor() as cursor:
                # Create pgvector extension
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                self.stdout.write(self.style.SUCCESS("✅ pgvector extension created"))

                # Create HNSW index
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS vector_document_embedding_hnsw_idx 
                    ON common_vectordocument 
                    USING hnsw (embedding vector_cosine_ops)
                    WITH (m = 16, ef_construction = 64);
                """
                )
                self.stdout.write(self.style.SUCCESS("✅ HNSW index created"))

                # Create IVFFlat index
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS vector_document_embedding_ivfflat_idx 
                    ON common_vectordocument 
                    USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100);
                """
                )
                self.stdout.write(self.style.SUCCESS("✅ IVFFlat index created"))

                # Update statistics
                cursor.execute("ANALYZE common_vectordocument;")
                self.stdout.write(self.style.SUCCESS("✅ Statistics updated"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error setting up database: {e}"))

    def optimize_database(self):
        """Optimize database performance."""
        self.stdout.write(self.style.SUCCESS("⚡ Optimizing database..."))

        try:
            with connection.cursor() as cursor:
                # Vacuum and analyze
                cursor.execute("VACUUM ANALYZE common_vectordocument;")
                self.stdout.write(self.style.SUCCESS("✅ Vacuum and analyze completed"))

                # Update table statistics
                cursor.execute("ANALYZE common_vectordocument;")

                # Check index usage
                cursor.execute(
                    """
                    SELECT indexname, idx_scan, idx_tup_read, idx_tup_fetch 
                    FROM pg_stat_user_indexes 
                    WHERE relname = 'common_vectordocument'
                """
                )

                indexes = cursor.fetchall()
                for index in indexes:
                    self.stdout.write(
                        f"Index: {index[0]}, Scans: {index[1]}, Tuples Read: {index[2]}"
                    )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error optimizing database: {e}"))

    def show_database_stats(self):
        """Show database statistics."""
        self.stdout.write(self.style.SUCCESS("📊 Database Statistics"))

        try:
            vector_service = VectorStorageService()
            stats = vector_service.get_storage_stats()

            self.stdout.write(f"Total documents: {stats.get('total_documents', 0)}")
            self.stdout.write(f"Storage size: {stats.get('storage_size', 'Unknown')}")

            # Show by source type
            by_source = stats.get("by_source_type", {})
            for source_type, count in by_source.items():
                self.stdout.write(f"  {source_type}: {count}")

            # Show vector indexes
            indexes = stats.get("vector_indexes", [])
            if indexes:
                self.stdout.write("Vector indexes:")
                for index in indexes:
                    self.stdout.write(f"  - {index}")

            # Show database size
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT pg_size_pretty(pg_database_size(current_database()))
                """
                )
                db_size = cursor.fetchone()[0]
                self.stdout.write(f"Database size: {db_size}")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error getting stats: {e}"))

    def cleanup_database(self, days: int, dry_run: bool):
        """Clean up old data."""
        self.stdout.write(
            self.style.SUCCESS(f"🧹 Cleaning up data older than {days} days...")
        )

        try:
            vector_service = VectorStorageService()

            if dry_run:
                self.stdout.write(
                    self.style.WARNING("DRY RUN - No actual cleanup performed")
                )
                # Show what would be deleted
                from datetime import timedelta

                from django.utils import timezone

                cutoff_date = timezone.now() - timedelta(days=days)

                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT source_type, COUNT(*) 
                        FROM common_vectordocument 
                        WHERE created_at < %s 
                        GROUP BY source_type
                    """,
                        [cutoff_date],
                    )

                    results = cursor.fetchall()
                    total = sum(count for _, count in results)

                    self.stdout.write(f"Would delete {total} documents:")
                    for source_type, count in results:
                        self.stdout.write(f"  {source_type}: {count}")
            else:
                deleted_count = vector_service.cleanup_old_vectors(days)
                self.stdout.write(
                    self.style.SUCCESS(f"✅ Deleted {deleted_count} old documents")
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error cleaning up: {e}"))

    def reindex_database(self):
        """Rebuild database indexes."""
        self.stdout.write(self.style.SUCCESS("🔄 Reindexing database..."))

        try:
            vector_service = VectorStorageService()
            success = vector_service.reindex_vectors()

            if success:
                self.stdout.write(self.style.SUCCESS("✅ Reindexing completed"))
            else:
                self.stdout.write(
                    self.style.WARNING(
                        "⚠️  Reindexing not available in development mode"
                    )
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error reindexing: {e}"))

    def backup_database(self):
        """Create database backup."""
        self.stdout.write(self.style.SUCCESS("💾 Creating database backup..."))

        try:
            from datetime import datetime

            backup_filename = (
                f"jobraker_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
            )
            backup_path = os.path.join("/tmp", backup_filename)

            # Use pg_dump for backup
            import subprocess

            cmd = [
                "pg_dump",
                "-h",
                settings.DATABASES["default"]["HOST"],
                "-p",
                str(settings.DATABASES["default"]["PORT"]),
                "-U",
                settings.DATABASES["default"]["USER"],
                "-d",
                settings.DATABASES["default"]["NAME"],
                "-f",
                backup_path,
                "--verbose",
            ]

            env = os.environ.copy()
            env["PGPASSWORD"] = settings.DATABASES["default"]["PASSWORD"]

            result = subprocess.run(cmd, env=env, capture_output=True, text=True)

            if result.returncode == 0:
                self.stdout.write(
                    self.style.SUCCESS(f"✅ Backup created: {backup_path}")
                )

                # Show backup size
                backup_size = os.path.getsize(backup_path)
                self.stdout.write(f"Backup size: {backup_size / (1024*1024):.2f} MB")
            else:
                self.stdout.write(
                    self.style.ERROR(f"❌ Backup failed: {result.stderr}")
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error creating backup: {e}"))
