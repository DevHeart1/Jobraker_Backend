# 🚀 Jobraker API Integration Setup Guide

This guide will help you configure the external API integrations for the Jobraker backend system.

## 📋 Required API Integrations

### 🤖 OpenAI API
**Purpose**: AI-powered job assistance, chat functionality, and resume analysis

**Setup Steps**:
1. Go to [OpenAI API](https://platform.openai.com/api-keys)
2. Create an account or sign in
3. Generate a new API key
4. Add to your `.env` file:
   ```bash
   OPENAI_API_KEY=sk-your-openai-api-key-here
   OPENAI_MODEL=gpt-4o-mini
   OPENAI_EMBEDDING_MODEL=text-embedding-3-small
   ```

**Usage Costs**:
- GPT-4o-mini: ~$0.15/1M input tokens, ~$0.60/1M output tokens
- text-embedding-3-small: ~$0.02/1M tokens

### 💼 Adzuna Jobs API
**Purpose**: Job listing aggregation and search functionality

**Setup Steps**:
1. Go to [Adzuna Developer Portal](https://developer.adzuna.com/)
2. Register for a developer account
3. Create a new application
4. Get your App ID and API Key
5. Add to your `.env` file:
   ```bash
   ADZUNA_APP_ID=your-app-id-here
   ADZUNA_API_KEY=your-api-key-here
   ```

**API Limits**:
- Free tier: 1,000 calls/month
- Paid plans available for higher usage

### 🕷️ Skyvern API
**Purpose**: Automated job application submission

**Setup Steps**:
1. Go to [Skyvern](https://www.skyvern.com/)
2. Sign up for an account
3. Get your API key from the dashboard
4. Add to your `.env` file:
   ```bash
   SKYVERN_API_KEY=your-skyvern-api-key-here
   SKYVERN_BASE_URL=https://api.skyvern.com
   ```

**Note**: Skyvern is a specialized service for web automation. Contact their team for pricing.

## 🛠️ Testing Your API Setup

### Quick Configuration Check
```bash
python manage.py test_apis --quick
```

### Full API Integration Test
```bash
python manage.py test_apis --verbose
```

### Test Specific API
```bash
python manage.py test_apis --api openai --verbose
python manage.py test_apis --api adzuna --verbose  
python manage.py test_apis --api skyvern --verbose
```

## 🔧 Troubleshooting

### Common Issues

#### OpenAI API Issues
- **Invalid API Key**: Ensure your API key starts with `sk-` and is correctly copied
- **Quota Exceeded**: Check your OpenAI usage dashboard
- **Model Not Available**: Verify you have access to the specified model

#### Adzuna API Issues
- **Authentication Failed**: Double-check your App ID and API Key
- **Rate Limit Exceeded**: Free tier has monthly limits
- **No Results**: Some search queries may return empty results

#### Skyvern API Issues
- **Authentication Failed**: Verify your API key is correct
- **Service Unavailable**: Skyvern may have service maintenance

### Debug Steps
1. Check your `.env` file for correct API keys
2. Verify your internet connection
3. Check API service status pages
4. Review Django logs for detailed error messages

## 🌐 API Endpoints for Testing

Once configured, you can test the APIs through the Django admin or API endpoints:

- **API Status**: `GET /api/integrations/status/`
- **Test Connection**: `GET /api/integrations/test/{service}/`
- **Trigger Job Sync**: `POST /api/integrations/sync/`

## 📊 Monitoring API Usage

### View API Status Dashboard
Navigate to `/admin/` and check the Integrations section for:
- API call statistics
- Error rates
- Rate limit status
- Last successful calls

### Prometheus Metrics
The system exposes Prometheus metrics for monitoring:
- `jobraker_openai_api_calls_total`
- `jobraker_adzuna_api_calls_total`
- `jobraker_skyvern_api_calls_total`

## 🔐 Security Best Practices

1. **Environment Variables**: Never commit API keys to version control
2. **Key Rotation**: Regularly rotate your API keys
3. **Rate Limiting**: Monitor and respect API rate limits
4. **Error Handling**: Implement proper error handling and retries
5. **Logging**: Log API calls for debugging but not sensitive data

## 📈 Cost Optimization

### OpenAI
- Use shorter prompts when possible
- Implement caching for repeated queries
- Monitor token usage through the dashboard

### Adzuna
- Cache job listings to reduce API calls
- Use incremental sync instead of full sync
- Implement circuit breakers for failed calls

### Skyvern
- Batch application submissions
- Use webhooks instead of polling for status updates
- Implement proper error handling and retries

## 🚀 Next Steps

After setting up the APIs:

1. **Test Integration**: Run the test command to verify everything works
2. **Configure Celery**: Set up Redis and Celery workers for background processing
3. **Set Up Database**: Configure PostgreSQL with pgvector for production
4. **Monitor Performance**: Set up logging and monitoring for API calls
5. **Scale Appropriately**: Monitor usage and upgrade API plans as needed

## 📞 Support

If you encounter issues:

1. Check the Django logs: `python manage.py runserver --verbosity=2`
2. Run the diagnostic command: `python manage.py test_apis --verbose`
3. Review API provider documentation
4. Check service status pages for outages

## 📝 Example .env Configuration

```bash
# External API Keys
OPENAI_API_KEY=sk-your-openai-api-key-here
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

ADZUNA_APP_ID=your-app-id-here
ADZUNA_API_KEY=your-api-key-here

SKYVERN_API_KEY=your-skyvern-api-key-here
SKYVERN_BASE_URL=https://api.skyvern.com

# Database Configuration
DB_NAME=jobraker_dev
DB_USER=jobraker
DB_PASSWORD=your_password_here
DB_HOST=localhost
DB_PORT=5432

# Redis Configuration
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

Happy integrating! 🎉
