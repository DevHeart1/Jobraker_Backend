#!/bin/bash
# PostgreSQL + pgvector Setup Script for Production

set -e

echo "🗄️  Setting up PostgreSQL with pgvector for Jobraker..."

# Check if PostgreSQL is installed
if ! command -v psql &> /dev/null; then
    echo "❌ PostgreSQL is not installed. Please install PostgreSQL first."
    echo "   Ubuntu/Debian: sudo apt-get install postgresql postgresql-contrib"
    echo "   CentOS/RHEL: sudo yum install postgresql postgresql-server"
    echo "   macOS: brew install postgresql"
    exit 1
fi

# Check if we're running as postgres user or have sudo access
if [ "$EUID" -eq 0 ]; then
    POSTGRES_USER="postgres"
    SUDO_PREFIX=""
elif command -v sudo &> /dev/null; then
    POSTGRES_USER="postgres"
    SUDO_PREFIX="sudo -u postgres"
else
    echo "❌ This script needs to be run as root or with sudo access"
    exit 1
fi

# Configuration from environment or defaults
DB_NAME="${DB_NAME:-jobraker_prod}"
DB_USER="${DB_USER:-jobraker_user}"
DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -base64 32)}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

echo "📋 Database Configuration:"
echo "   Database: $DB_NAME"
echo "   User: $DB_USER"
echo "   Host: $DB_HOST"
echo "   Port: $DB_PORT"
echo ""

# Start PostgreSQL service
echo "🚀 Starting PostgreSQL service..."
if command -v systemctl &> /dev/null; then
    sudo systemctl start postgresql
    sudo systemctl enable postgresql
elif command -v service &> /dev/null; then
    sudo service postgresql start
fi

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL to be ready..."
sleep 3

# Create database and user
echo "👤 Creating database and user..."
$SUDO_PREFIX psql -c "CREATE DATABASE $DB_NAME;" 2>/dev/null || echo "Database $DB_NAME already exists"
$SUDO_PREFIX psql -c "CREATE USER $DB_USER WITH ENCRYPTED PASSWORD '$DB_PASSWORD';" 2>/dev/null || echo "User $DB_USER already exists"
$SUDO_PREFIX psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" 
$SUDO_PREFIX psql -c "ALTER USER $DB_USER CREATEDB;" # Allow user to create test databases

# Install pgvector extension
echo "🔧 Installing pgvector extension..."

# Check if pgvector is available
if $SUDO_PREFIX psql -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null; then
    echo "✅ pgvector extension installed successfully"
else
    echo "⚠️  pgvector extension not found. Installing from source..."
    
    # Install build dependencies
    if command -v apt-get &> /dev/null; then
        sudo apt-get update
        sudo apt-get install -y build-essential git postgresql-server-dev-all
    elif command -v yum &> /dev/null; then
        sudo yum groupinstall -y "Development Tools"
        sudo yum install -y git postgresql-devel
    elif command -v brew &> /dev/null; then
        # macOS with Homebrew
        if ! brew list pgvector &> /dev/null; then
            brew install pgvector
        fi
    fi
    
    # Clone and build pgvector (Linux only)
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        cd /tmp
        git clone --branch v0.5.1 https://github.com/pgvector/pgvector.git
        cd pgvector
        make
        sudo make install
        
        # Install the extension in our database
        $SUDO_PREFIX psql -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector;"
        echo "✅ pgvector extension built and installed successfully"
    fi
fi

# Create vector-specific configurations
echo "⚙️  Configuring PostgreSQL for vector operations..."
$SUDO_PREFIX psql -d "$DB_NAME" -c "
-- Create extension if not exists
CREATE EXTENSION IF NOT EXISTS vector;

-- Optimize for vector operations
ALTER SYSTEM SET shared_preload_libraries = 'vector';
ALTER SYSTEM SET max_connections = 200;
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';
ALTER SYSTEM SET maintenance_work_mem = '64MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET default_statistics_target = 100;
"

# Test the installation
echo "🧪 Testing pgvector installation..."
if $SUDO_PREFIX psql -d "$DB_NAME" -c "SELECT vector_dims('[1,2,3]'::vector);" &> /dev/null; then
    echo "✅ pgvector is working correctly"
else
    echo "❌ pgvector test failed"
    exit 1
fi

# Create connection string
CONNECTION_STRING="postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"

echo ""
echo "🎉 PostgreSQL + pgvector setup complete!"
echo ""
echo "📝 Add this to your .env file:"
echo "DATABASE_URL=$CONNECTION_STRING"
echo "DB_NAME=$DB_NAME"
echo "DB_USER=$DB_USER"
echo "DB_PASSWORD=$DB_PASSWORD"
echo "DB_HOST=$DB_HOST"
echo "DB_PORT=$DB_PORT"
echo ""
echo "🔐 IMPORTANT: Save the database password securely!"
echo "Password: $DB_PASSWORD"
echo ""
echo "🚀 Next steps:"
echo "1. Update your .env file with the database configuration"
echo "2. Run: python manage.py migrate"
echo "3. Run: python manage.py collectstatic"
echo "4. Start your application!"
