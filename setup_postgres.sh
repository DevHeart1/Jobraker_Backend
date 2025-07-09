#!/bin/bash

# Production PostgreSQL Setup Script for Jobraker Backend
# This script sets up PostgreSQL with pgvector extension for production use

set -e

# Database configuration
DB_NAME=${DB_NAME:-jobraker_prod}
DB_USER=${DB_USER:-jobraker}
DB_PASSWORD=${DB_PASSWORD:-$(openssl rand -base64 32)}
DB_HOST=${DB_HOST:-localhost}
DB_PORT=${DB_PORT:-5432}

echo "🚀 Setting up PostgreSQL with pgvector for Jobraker Backend..."

# Check if PostgreSQL is installed
if ! command -v psql &> /dev/null; then
    echo "❌ PostgreSQL is not installed. Please install PostgreSQL first."
    exit 1
fi

# Create database and user
echo "📦 Creating database and user..."
sudo -u postgres psql -c "CREATE USER $DB_USER WITH ENCRYPTED PASSWORD '$DB_PASSWORD';"
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"

# Install pgvector extension
echo "🔧 Installing pgvector extension..."
sudo -u postgres psql -d $DB_NAME -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Set up additional configurations
echo "⚙️ Configuring database settings..."
sudo -u postgres psql -d $DB_NAME -c "ALTER ROLE $DB_USER SET client_encoding TO 'utf8';"
sudo -u postgres psql -d $DB_NAME -c "ALTER ROLE $DB_USER SET default_transaction_isolation TO 'read committed';"
sudo -u postgres psql -d $DB_NAME -c "ALTER ROLE $DB_USER SET timezone TO 'UTC';"

# Create indexes for better performance
echo "📊 Creating performance indexes..."
sudo -u postgres psql -d $DB_NAME -c "
-- Indexes will be created by Django migrations, but we can prepare
-- the database for optimal vector operations
SET maintenance_work_mem = '2GB';
SET max_parallel_workers_per_gather = 4;
"

# Output connection details
echo "✅ PostgreSQL setup completed successfully!"
echo ""
echo "📝 Database connection details:"
echo "Database: $DB_NAME"
echo "User: $DB_USER"
echo "Password: $DB_PASSWORD"
echo "Host: $DB_HOST"
echo "Port: $DB_PORT"
echo ""
echo "🔗 Connection string for Django:"
echo "postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"
echo ""
echo "⚠️  Make sure to update your .env file with these credentials!"
