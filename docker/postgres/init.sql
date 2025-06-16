-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create additional indexes for better performance
CREATE INDEX IF NOT EXISTS idx_gin_trgm ON pg_trgm USING gin (text gin_trgm_ops);

-- Set up database optimizations
ALTER SYSTEM SET shared_preload_libraries = 'pg_stat_statements';
ALTER SYSTEM SET track_activity_query_size = 2048;
ALTER SYSTEM SET pg_stat_statements.track = 'all';
