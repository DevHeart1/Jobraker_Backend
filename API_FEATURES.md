# Jobraker Backend API Documentation

## Overview
This document outlines the AI-powered job recommendation system implementation for the Jobraker backend. The system provides intelligent job matching, resume analysis, and chat-based career assistance.

## 🚀 New Features Implemented

### 1. AI-Powered Job Recommendations
- **Endpoint**: `POST /api/v1/jobs/recommendations/generate/`
- **Description**: Generates personalized job recommendations using AI embeddings
- **Authentication**: Required

### 2. Resume Analysis & Processing
- **Endpoint**: `POST /api/v1/auth/upload-resume/`
- **Description**: Upload and automatically process resumes for profile enhancement
- **Supported Formats**: PDF, DOC, DOCX (max 5MB)
- **Authentication**: Required

### 3. Chat Assistant
- **Endpoint**: `POST /api/v1/chat/send/`
- **Description**: Interactive AI assistant for career guidance and job search help
- **Authentication**: Required

### 4. Job Matching Service
- **Endpoint**: `GET /api/v1/jobs/recommendations/`
- **Description**: Retrieve AI-generated job recommendations
- **Authentication**: Required

### 5. System Health & Status
- **Endpoint**: `GET /api/v1/common/health/`
- **Description**: Check system health and component status
- **Authentication**: Required

## 🔧 Technical Implementation

### Backend Architecture
- **Vector Database**: PostgreSQL with pgvector for similarity search
- **AI Service**: OpenAI GPT-4 for embeddings and chat completions
- **Task Queue**: Celery with Redis for background processing
- **API Framework**: Django REST Framework with comprehensive documentation

### Key Components

#### 1. Vector Similarity Search (`apps/common/vector_service.py`)
```python
class VectorDBService:
    def search_similar_documents(self, query_embedding, top_n=5, filter_criteria=None):
        # Performs cosine similarity search using pgvector
        # Returns ranked results with similarity scores
```

#### 2. Job Matching Service (`apps/jobs/services.py`)
```python
class JobMatchService:
    def find_matching_jobs_for_user(self, user_profile_id, top_n=10):
        # Finds relevant jobs based on user profile embedding
        # Filters out already applied/dismissed jobs
    
    def generate_recommendations_for_user(self, user_profile_id, num_recommendations=10):
        # Generates and stores job recommendations
        # Updates RecommendedJob model with new matches
```

#### 3. OpenAI Integration (`apps/integrations/services/openai_service.py`)
```python
class OpenAIJobAssistant:
    def generate_embedding(self, text):
        # Generates vector embeddings for job descriptions and user profiles
    
    def generate_chat_completion(self, messages):
        # Handles chat conversations with AI assistant
```

### Database Models

#### Job Recommendations
```python
class RecommendedJob(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    score = models.FloatField()  # AI-calculated match score
    status = models.CharField(max_length=20)  # pending_review, viewed, dismissed
    algorithm_version = models.CharField(max_length=50)
    recommended_at = models.DateTimeField(auto_now_add=True)
```

#### User Profile Embeddings
```python
class UserProfile(models.Model):
    # ... existing fields ...
    profile_embedding = VectorField(dimensions=1536)  # OpenAI embedding
    skills_embedding = VectorField(dimensions=1536)   # Skills-specific embedding
```

### Background Tasks

#### Automatic Embedding Generation
- **Job Embeddings**: Generated on job creation/update via Django signals
- **User Profile Embeddings**: Generated on profile update
- **Resume Processing**: Extracts information and updates user profiles

#### Scheduled Tasks (Celery Beat)
- **Daily Recommendations**: Generates fresh recommendations for all users
- **Job Alerts**: Processes user-defined job alert criteria
- **Application Follow-ups**: Sends reminder notifications

## 📊 API Endpoints

### Authentication & User Management
- `POST /api/v1/auth/register/` - User registration
- `POST /api/v1/auth/login/` - User login
- `GET /api/v1/auth/me/` - Current user info
- `POST /api/v1/auth/upload-resume/` - Resume upload & processing

### Job Management
- `GET /api/v1/jobs/jobs/` - List jobs with filtering
- `GET /api/v1/jobs/search/` - Advanced job search
- `GET /api/v1/jobs/recommendations/` - Get user recommendations
- `POST /api/v1/jobs/recommendations/generate/` - Generate new recommendations

### Applications
- `POST /api/v1/jobs/applications/` - Apply to job
- `GET /api/v1/jobs/applications/` - List user applications
- `POST /api/v1/jobs/applications/bulk-apply/` - Bulk job application

### Chat Assistant
- `POST /api/v1/chat/send/` - Send message to AI assistant
- `GET /api/v1/chat/sessions/` - List chat sessions
- `POST /api/v1/chat/sessions/` - Create new chat session

### System Status
- `GET /api/v1/common/health/` - System health check
- `GET /api/v1/common/user-recommendations-status/` - User recommendation status

## 🔒 Security & Authentication

All endpoints require JWT authentication except:
- User registration
- User login
- API documentation endpoints

## 📈 Performance & Scaling

### Optimizations Implemented
- **Database Indexing**: Optimized indexes for vector similarity searches
- **Caching**: Redis caching for frequently accessed data
- **Background Processing**: Celery for compute-intensive tasks
- **Pagination**: Implemented for all list endpoints

### Monitoring & Logging
- **Structured Logging**: Comprehensive logging for debugging and monitoring
- **Health Checks**: System component health monitoring
- **Error Handling**: Graceful error handling with meaningful responses

## 🚀 Deployment Considerations

### Environment Variables
Required environment variables are documented in `.env` file:
- `OPENAI_API_KEY` - OpenAI API key for AI features
- `REDIS_URL` - Redis connection for Celery
- `DATABASE_URL` - PostgreSQL with pgvector extension

### Docker Configuration
The project includes Docker configuration for easy deployment:
- `docker-compose.yml` - Multi-container setup
- `Dockerfile` - Application container
- `requirements.txt` - Python dependencies

### Celery Workers
For production deployment, run separate processes:
```bash
# Start Celery worker
celery -A jobraker worker -l info

# Start Celery beat (scheduler)
celery -A jobraker beat -l info
```

## 📝 API Documentation

Interactive API documentation is available at:
- **Swagger UI**: `/api/docs/` (when running locally)
- **ReDoc**: `/api/redoc/` (when running locally)
- **OpenAPI Schema**: `/api/schema/`

## 🧪 Testing

The implementation includes comprehensive test coverage:
- Unit tests for all services
- Integration tests for API endpoints
- End-to-end tests for complete workflows

Run tests with:
```bash
python manage.py test
```

## 🔮 Future Enhancements

1. **Advanced ML Models**: Integration with custom ML models for job matching
2. **Real-time Notifications**: WebSocket support for live updates
3. **Interview Preparation**: AI-powered interview question generation
4. **Salary Insights**: Market-based salary recommendations
5. **Company Insights**: AI-generated company analysis and culture fit

## 🤝 Contributing

The codebase follows Django best practices and includes:
- Comprehensive documentation
- Type hints where applicable
- Consistent error handling
- Modular, reusable components

For development setup, see `SETUP.md` in the project root.
