# 🔗 External API Integration Setup Guide

This guide will help you configure and test the external API integrations for the Jobraker backend.

## 📋 Required API Credentials

### 1. OpenAI API (Required for AI Features)
- **Purpose**: Chat assistant, job advice, resume analysis, embeddings
- **Get API Key**: Visit [OpenAI API Keys](https://platform.openai.com/api-keys)
- **Cost**: Usage-based pricing, very affordable for development
- **Setup**:
  ```bash
  OPENAI_API_KEY=sk-your-openai-api-key-here
  OPENAI_MODEL=gpt-4o-mini
  OPENAI_EMBEDDING_MODEL=text-embedding-3-small
  ```

### 2. Adzuna Jobs API (Required for Job Data)
- **Purpose**: Fetch job listings from major job boards
- **Get Credentials**: Register at [Adzuna Developer Portal](https://developer.adzuna.com/)
- **Cost**: Free tier available with rate limits
- **Setup**:
  ```bash
  ADZUNA_APP_ID=your-app-id-here
  ADZUNA_API_KEY=your-api-key-here
  ```

### 3. Skyvern API (Optional - For Auto-Apply)
- **Purpose**: Automated job application submission
- **Get API Key**: Contact [Skyvern](https://skyvern.com/) for access
- **Cost**: Contact Skyvern for pricing
- **Setup**:
  ```bash
  SKYVERN_API_KEY=your-skyvern-api-key-here
  SKYVERN_BASE_URL=https://api.skyvern.com
  ```

## 🚀 Quick Setup Steps

1. **Copy Environment File**:
   ```bash
   cp env_template.txt .env
   ```

2. **Add Your API Keys**:
   Edit `.env` file and add your actual API credentials.

3. **Test Your Configuration**:
   ```bash
   python manage.py test_apis
   ```

4. **Quick Configuration Check**:
   ```bash
   python manage.py test_apis --quick
   ```

5. **Test Specific Service**:
   ```bash
   python manage.py test_apis --service openai
   python manage.py test_apis --service adzuna
   python manage.py test_apis --service skyvern
   ```

## 🧪 Testing API Integrations

### Using Management Commands
```bash
# Test all APIs
python manage.py test_apis

# Quick configuration check (no API calls)
python manage.py test_apis --quick

# Test specific service
python manage.py test_apis --service openai
```

### Using API Endpoints
```bash
# Check all API status
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     http://localhost:8000/api/integrations/status/

# Test specific API
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     http://localhost:8000/api/integrations/test/openai/

# Trigger job sync
curl -X POST \
     -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"source": "adzuna", "max_days_old": 1}' \
     http://localhost:8000/api/integrations/sync/
```

## 📊 Integration Status Levels

- **✅ Success**: API is configured and working correctly
- **⚠️ Warning**: API is configured but has minor issues
- **❌ Error**: API is not configured or has connection problems
- **🔧 Not Configured**: API credentials not provided

## 🔧 Troubleshooting

### OpenAI API Issues
- **Invalid API Key**: Check your API key at [OpenAI Platform](https://platform.openai.com/api-keys)
- **Rate Limits**: OpenAI has usage limits; check your account limits
- **Model Not Available**: Ensure you have access to the specified model

### Adzuna API Issues
- **Authentication Failed**: Verify both APP_ID and API_KEY are correct
- **Rate Limits**: Free tier has rate limits; check your usage
- **No Jobs Returned**: Try different search parameters or location

### Skyvern API Issues
- **Connection Failed**: Check if SKYVERN_BASE_URL is correct
- **Authentication**: Verify your API key with Skyvern support
- **Service Unavailable**: Skyvern may be in maintenance

### Celery Issues
- **Workers Not Found**: Start Celery workers:
  ```bash
  celery -A jobraker worker -l info
  ```
- **Broker Connection**: Ensure Redis is running:
  ```bash
  redis-server
  ```

## 🎯 Minimum Required Setup

For basic functionality, you need:

1. **OpenAI API** - For AI features (chat, advice, embeddings)
2. **Adzuna API** - For job data
3. **Redis** - For Celery task queue
4. **PostgreSQL** - For database (SQLite works for development)

Skyvern is optional and only needed for automated job applications.

## 🔄 Background Tasks

Once APIs are configured, background tasks will:

1. **Fetch Jobs**: Automatically sync jobs from Adzuna every hour
2. **Generate Embeddings**: Create AI embeddings for job matching
3. **Process Applications**: Handle automated job applications via Skyvern
4. **Send Notifications**: Email users about job matches and updates

## 📈 Monitoring

- **API Status**: `/api/integrations/status/`
- **Configuration**: `/api/integrations/config/`
- **Manual Sync**: `/api/integrations/sync/`
- **Test APIs**: `/api/integrations/test/{service}/`

## 🔒 Security Notes

- Never commit `.env` file to version control
- Rotate API keys regularly
- Use environment-specific credentials
- Monitor API usage and costs
- Implement rate limiting for production

## 💡 Development Tips

- Use mock responses when APIs are not configured
- Test with small job sync batches first
- Monitor Celery task logs for debugging
- Use the quick test mode for fast configuration checks

Need help? Check the logs at `logs/` directory or run the test command for detailed diagnostics.
