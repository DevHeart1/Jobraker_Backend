# Jobraker - Technical Stack Documentation

[![Version](https://img.shields.io/badge/version-1.0-blue.svg)]()
[![Status](https://img.shields.io/badge/status-draft-yellow.svg)]()
[![Last Updated](https://img.shields.io/badge/last%20updated-June%2015%2C%202025-green.svg)]()

---

## Document Information

| Field              | Value                                      |
|--------------------|--------------------------------------------|
| Document Title     | Jobraker Technical Stack Documentation     |
| Version            | 1.0.0                                      |
| Status             | Draft                                      |
| Classification     | Confidential                               |
| Created By         | Engineering Team                           |
| Created Date       | June 15, 2025                              |
| Last Modified      | June 15, 2025                              |
| Next Review Date   | July 15, 2025                              |

---

## Table of Contents

1.  [Introduction](#1-introduction)
2.  [Guiding Principles](#2-guiding-principles)
3.  [High-Level Architecture Overview](#3-high-level-architecture-overview)
4.  [Core Backend Technologies](#4-core-backend-technologies)
    4.1. [Programming Language: Python](#41-programming-language-python)
    4.2. [Web Framework: Django](#42-web-framework-django)
    4.3. [API Layer: Django REST Framework (DRF)](#43-api-layer-django-rest-framework-drf)
    4.4. [Admin Dashboard: django-jazzmin](#44-admin-dashboard-django-jazzmin)
5.  [Data Storage & Management](#5-data-storage--management)
    5.1. [Primary Database: PostgreSQL](#51-primary-database-postgresql)
    5.2. [Vector Database: PgVector](#52-vector-database-pgvector)
6.  [Caching Layer](#6-caching-layer)
    6.1. [In-Memory Cache: Redis](#61-in-memory-cache-redis)
7.  [Asynchronous Task Processing](#7-asynchronous-task-processing)
    7.1. [Task Queue: Celery](#71-task-queue-celery)
    7.2. [Message Broker: Redis](#72-message-broker-redis)
    7.3. [Scheduler: Celery Beat](#73-scheduler-celery-beat)
8.  [Real-Time Communication](#8-real-time-communication)
    8.1. [WebSockets: Django Channels (Optional)](#81-websockets-django-channels-optional)
9.  [Third-Party API Integrations](#9-third-party-api-integrations)
    9.1. [Adzuna API](#91-adzuna-api)
    9.2. [Skyvern API](#92-skyvern-api)
    9.3. [OpenAI API (GPT-4.1 Mini & Embeddings)](#93-openai-api-gpt-41-mini--embeddings)
10. [Security & Compliance](#10-security--compliance)
    10.1. [Authentication & Authorization](#101-authentication--authorization)
    10.2. [Data Encryption](#102-data-encryption)
    10.3. [Input Validation & Sanitization](#103-input-validation--sanitization)
    10.4. [Security Headers](#104-security-headers)
    10.5. [Dependency Management](#105-dependency-management)
    10.6. [Compliance](#106-compliance)
11. [Development & DevOps](#11-development--devops)
    11.1. [Version Control: Git](#111-version-control-git)
    11.2. [Containerization: Docker](#112-containerization-docker)
    11.3. [Orchestration: Kubernetes (Future)](#113-orchestration-kubernetes-future)
    11.4. [CI/CD: GitHub Actions](#114-cicd-github-actions)
    11.5. [Testing Frameworks](#115-testing-frameworks)
    11.6. [Code Quality & Formatting](#116-code-quality--formatting)
12. [Monitoring & Logging](#12-monitoring--logging)
    12.1. [Application Performance Monitoring (APM)](#121-application-performance-monitoring-apm)
    12.2. [Infrastructure Monitoring](#122-infrastructure-monitoring)
    12.3. [Logging](#123-logging)
13. [Scalability & Performance](#13-scalability--performance)
14. [Future Considerations](#14-future-considerations)
15. [Conclusion](#15-conclusion)

---

## 1. Introduction
This document provides a comprehensive overview of the technical stack powering the Jobraker backend. Jobraker is an autonomous job search and application platform designed for scalability, high performance, and robust security. The selected technologies aim to facilitate rapid development, maintainability, and the ability to integrate advanced AI-driven features seamlessly.

## 2. Guiding Principles
The technology choices for Jobraker are guided by the following principles:
- **Scalability**: Ability to handle a growing number of users and data volume.
- **Performance**: Ensuring fast response times and efficient processing.
- **Reliability**: Building a robust and fault-tolerant system.
- **Security**: Prioritizing data protection and secure operations.
- **Maintainability**: Choosing well-documented and community-supported technologies.
- **Developer Productivity**: Leveraging frameworks and tools that enhance development speed and quality.
- **Cost-Effectiveness**: Balancing performance and features with operational costs.

## 3. High-Level Architecture Overview
Jobraker employs a modular, service-oriented architecture. The backend is primarily built using Django, serving a RESTful API consumed by the frontend and other potential clients. Asynchronous tasks are offloaded to Celery workers, and data is persisted in PostgreSQL, with Redis serving as a caching layer and message broker.

```mermaid
graph TD
    User[User/Frontend] -->|HTTPS| APIGateway[API Gateway / Load Balancer]

    subgraph BackendServices [Jobraker Backend Services]
        APIGateway --> DjangoApp[Django REST API Servers]
        DjangoApp -->|User Auth, Business Logic| AuthNAuthZ[Authentication/Authorization]
        DjangoApp -->|CRUD Operations| PostgreSQL[(PostgreSQL Database)]
        DjangoApp -->|Cache Read/Write| RedisCache[(Redis Cache)]
        DjangoApp -->|Enqueue Tasks| CeleryQueue[Celery Task Queue (Redis)]

        CeleryWorkers[Celery Workers] -->|Dequeue Tasks| CeleryQueue
        CeleryWorkers -->|DB Operations| PostgreSQL
        CeleryWorkers -->|External API Calls| ThirdPartyAPIs[Third-Party APIs]
        CeleryWorkers -->|Cache Updates| RedisCache

        CeleryBeat[Celery Beat Scheduler] -->|Schedule Tasks| CeleryQueue
    end

    subgraph DataStores
        PostgreSQL -->|Vector Search| PgVectorExt[PgVector Extension]
    end

    subgraph ExternalServices [External Services]
        ThirdPartyAPIs --> Adzuna[Adzuna API]
        ThirdPartyAPIs --> Skyvern[Skyvern API]
        ThirdPartyAPIs --> OpenAI[OpenAI API]
    end

    style User fill:#f9f,stroke:#333,stroke-width:2px
    style APIGateway fill:#bbf,stroke:#333,stroke-width:2px
    style DjangoApp fill:#lightgreen,stroke:#333,stroke-width:2px
    style CeleryWorkers fill:#lightgreen,stroke:#333,stroke-width:2px
    style CeleryBeat fill:#lightgreen,stroke:#333,stroke-width:2px
    style PostgreSQL fill:#lightblue,stroke:#333,stroke-width:2px
    style RedisCache fill:#orange,stroke:#333,stroke-width:2px
    style CeleryQueue fill:#orange,stroke:#333,stroke-width:2px
    style ThirdPartyAPIs fill:#lightgrey,stroke:#333,stroke-width:2px
```
*(This diagram provides a simplified view. Detailed interactions are described in subsequent sections.)*

## 4. Core Backend Technologies

### 4.1. Programming Language: Python
- **Version**: 3.10+
- **Why Python?**: Chosen for its extensive libraries, strong community support, readability, and suitability for web development, data science, and AI/ML applications. Python's ecosystem allows for rapid development and integration of various components.

### 4.2. Web Framework: Django
- **Version**: 4.x (Latest stable release at the time of development)
- **Why Django?**: Django is a high-level Python web framework that encourages rapid development and clean, pragmatic design. It’s selected for its:
    - **Robust ORM**: Simplifies database interactions and schema management.
    - **"Batteries-included" Philosophy**: Provides many common web development tools out-of-the-box (admin, authentication, templating).
    - **Scalability**: Proven ability to scale for high-traffic applications.
    - **Security Features**: Built-in protection against common web vulnerabilities (XSS, CSRF, SQL injection).
    - **Strong Community**: Extensive documentation and third-party packages.
- **Key Django Components Utilized**:
    - **Models**: Defining the structure of application data.
    - **Views**: Handling request-response logic.
    - **Templates**: (Primarily for the admin interface and potentially server-side rendered utility pages).
    - **Forms**: Data validation and handling.
    - **Middleware**: Custom request/response processing.
    - **Built-in Admin Interface**: For data management and operational tasks.

### 4.3. API Layer: Django REST Framework (DRF)
- **Version**: Latest stable release.
- **Why DRF?**: DRF is a powerful and flexible toolkit for building Web APIs on top of Django. It's essential for:
    - **Rapid API Development**: Provides abstractions like ViewSets and Serializers.
    - **Serialization**: Easily converts complex data types (e.g., Django models) to JSON and vice-versa.
    - **Authentication & Permissions**: Integrates seamlessly with Django's authentication system and provides fine-grained access control.
    - **Extensibility**: Highly customizable to fit specific API requirements.
- **Main Components & Usage**:
    - **Serializers**: Define how data is represented and validated.
    - **ViewSets & Generic Views**: Reduce boilerplate code for common API patterns (CRUD operations).
    - **Routers**: Automatically generate URL configurations for ViewSets.
    - **Authentication Classes**: JWT and potentially OAuth2 for securing API endpoints.
    - **Permission Classes**: Control access to API resources based on user roles or other conditions.
    - **Throttling**: Implement rate limiting to protect the API from abuse.
    - **Pagination**: Handle large datasets efficiently.

### 4.4. Admin Dashboard: django-jazzmin
- **Version**: Latest stable release.
- **Why django-jazzmin?**: `django-jazzmin` provides a modern, responsive, and highly customizable admin theme for Django, based on AdminLTE 3 and Bootstrap 4. It significantly enhances the user experience of the default Django admin interface.
- **Key Features Leveraged**:
    - Modern, responsive design suitable for various devices.
    - Customizable side menu, top menu, and user interface elements.
    - Improved visual aesthetics and usability over the default admin.
    - Modal windows for a smoother workflow.
- **Integration**:
    ```python
    # settings.py
    INSTALLED_APPS = [
        'jazzmin', # Should be listed before 'django.contrib.admin'
        'django.contrib.admin',
        # ... other apps
    ]

    JAZZMIN_SETTINGS = {
        "site_title": "Jobraker Admin",
        "site_header": "Jobraker",
        "site_brand": "Jobraker",
        # ... other customization options
    }
    ```

## 5. Data Storage & Management

### 5.1. Primary Database: PostgreSQL
- **Version**: 14+ (or latest stable managed version from cloud provider)
- **Why PostgreSQL?**: PostgreSQL is a powerful, open-source object-relational database system known for its reliability, feature robustness, and performance. It's chosen for:
    - **ACID Compliance**: Ensures data integrity.
    - **Extensibility**: Supports custom data types, functions, and extensions like PgVector.
    - **Scalability**: Handles large datasets and complex queries efficiently.
    - **JSONB Support**: Efficiently store and query semi-structured JSON data.
    - **Full-Text Search**: Built-in capabilities for text searching.
    - **Strong Community & Ecosystem**: Well-supported by Django and cloud providers.
- **Schema Design Highlights**: The database schema, managed via Django models, includes tables for:
    - `UserProfiles`: User credentials, personal details, job preferences, resume information.
    - `JobListings`: Aggregated job data from sources like Adzuna (title, description, company, location, salary, etc.).
    - `Applications`: Tracks user job applications, status (applied, interview, offer, rejected), and related metadata.
    - `Notifications`: Stores real-time notifications for users.
    - `ChatMessages`: Logs interactions between users and the AI assistant.
    - `APITokens`: Stores API keys or tokens for third-party service access.
    - `AuditLogs`: Tracks significant actions within the system.

### 5.2. Vector Database: PgVector
- **Type**: PostgreSQL Extension
- **Why PgVector?**: `PgVector` adds vector similarity search capabilities directly within PostgreSQL. This is crucial for:
    - **Semantic Search**: Moving beyond keyword matching to find jobs or candidates based on contextual meaning.
    - **Recommendation Engines**: Powering more relevant job recommendations.
    - **Embedding Storage**: Storing and querying embeddings generated from resumes, job descriptions, and user profiles (e.g., using OpenAI embeddings).
- **Integration**:
    - Leverages OpenAI's text embedding models (e.g., `text-embedding-ada-002` or newer) to convert text data into vector embeddings.
    - These embeddings are stored in `vector` columns within PostgreSQL tables.
    - `PgVector` provides operators and indexing (e.g., HNSW, IVFFlat) for efficient k-NN (k-Nearest Neighbors) similarity searches.

## 6. Caching Layer

### 6.1. In-Memory Cache: Redis
- **Version**: 6.x+ (or latest stable managed version)
- **Why Redis?**: Redis is an open-source, in-memory data structure store, used as a database, cache, and message broker. It's chosen for:
    - **High Performance**: Extremely fast read/write operations due to its in-memory nature.
    - **Versatile Data Structures**: Supports strings, hashes, lists, sets, sorted sets, etc.
    - **Scalability & Persistence Options**: Can be configured for various levels of persistence and clustering.
- **Use Cases in Jobraker**:
    - **API Response Caching**: Cache responses from external APIs (e.g., Adzuna) to reduce latency and avoid rate limits.
    - **Session Management**: Store user session data for quick authentication checks if not using purely stateless JWTs for all session aspects.
    - **Frequently Accessed Data**: Cache user profiles, popular job listings, or system configurations.
    - **Rate Limiting**: Store counters for API rate limiting.
    - **Celery Message Broker**: (See Section 7.2)
    - **Distributed Locks**: For coordinating tasks among multiple workers.

## 7. Asynchronous Task Processing

### 7.1. Task Queue: Celery
- **Version**: 5.x+
- **Why Celery?**: Celery is a distributed task queue system that allows for asynchronous execution of tasks outside the main application's request-response cycle. This is critical for:
    - **Improving API Response Times**: Offloading long-running operations (e.g., API calls, complex computations, email sending).
    - **Background Processing**: Handling tasks like job scraping, application submissions, and AI model inferences without blocking user interactions.
    - **Scalability**: Celery workers can be scaled independently to handle varying task loads.
    - **Reliability**: Supports task retries, error handling, and monitoring.
- **Key Tasks Managed by Celery**:
    - **Job Search Fetching**: Periodically fetching new job listings from Adzuna and other sources.
    - **Auto-Apply Submissions**: Automating job application submissions via the Skyvern API.
    - **AI Chat Completions & Embeddings**: Processing requests to the OpenAI API for chat responses and generating text embeddings.
    - **Notification Delivery**: Sending email or push notifications.
    - **Data Processing & Aggregation**: Performing batch operations or analytics.

### 7.2. Message Broker: Redis
- **Why Redis as a Broker for Celery?**: While RabbitMQ is also a common choice, Redis is often simpler to set up and manage for many use cases, especially if already used for caching. It provides sufficient reliability and performance for Jobraker's initial needs.
- **Role**: Manages the queue of tasks, ensuring that tasks are delivered from the Django application (producer) to the Celery workers (consumers).

### 7.3. Scheduler: Celery Beat
- **Why Celery Beat?**: Celery Beat is a scheduler that triggers tasks at regular intervals.
- **Scheduled Tasks**:
    - **Periodic Job Listing Fetch**: e.g., every 30 minutes to an hour to retrieve fresh job listings from Adzuna.
    - **Auto-Apply Job Check**: e.g., hourly, to identify and process jobs meeting user auto-apply criteria.
    - **Data Maintenance Tasks**: e.g., daily cleanup of old logs or temporary data.
    - **Report Generation**: e.g., daily or weekly generation of system performance reports.

## 8. Real-Time Communication

### 8.1. WebSockets: Django Channels (Optional / Future Enhancement)
- **Why WebSockets?**: To enable bi-directional, real-time communication between the client (frontend) and the backend.
- **Potential Use Cases**:
    - **Live Chat**: For the AI-powered assistant, providing instant responses.
    - **Real-time Notifications**: Instant updates on job application status, new relevant jobs, or interview reminders without requiring page reloads.
    - **Collaborative Features**: (If any are planned in the future).
- **Implementation**: `Django Channels` extends Django to handle WebSockets, chat protocols, IoT protocols, and more, asynchronously. It integrates well with the Django ecosystem.

## 9. Third-Party API Integrations
Jobraker relies on several third-party APIs to deliver its core functionality. Robust integration includes proper error handling, retry mechanisms (e.g., exponential backoff), rate limit management, and secure credential storage.

### 9.1. Adzuna API
- **Purpose**: Fetching comprehensive job listings.
- **Key Endpoints**: `/search` (for job retrieval based on various parameters like title, location, salary).
- **Rate Limits & Management**: Adzuna's free tier has limitations (e.g., 2,500 requests/month). The backend implements:
    - Caching of search results to minimize redundant API calls.
    - Intelligent querying to maximize information gain per call.
    - Monitoring of API usage against quotas.
    - Graceful degradation or user notification if limits are approached.

### 9.2. Skyvern API
- **Purpose**: Automating the submission of job applications.
- **Key Endpoints**: `/apply` (to submit applications, fill forms, upload resumes).
- **Rate Limits & Management**:
    - Adherence to negotiated rate limits based on Jobraker's subscription.
    - Internal queuing and throttling of application submissions to stay within limits.
    - Secure handling of user credentials required for application submissions.
    - Robust error tracking and reporting for failed submissions.

### 9.3. OpenAI API (GPT-4.1 Mini & Embeddings)
- **Purpose**:
    - **AI Chat Assistant**: Powering interactive conversations using GPT-4.1 Mini (via `POST /v1/chat/completions`).
    - **Semantic Matching**: Generating text embeddings for job descriptions, user profiles, and resumes to enable advanced semantic search and matching (via embedding models like `text-embedding-ada-002` or newer).
- **Rate Limits & Management**:
    - Token usage monitoring and optimization (e.g., prompt engineering, response length control).
    - Caching of common queries or embeddings where appropriate.
    - Asynchronous processing of API calls via Celery to avoid blocking user requests.

## 10. Security & Compliance

### 10.1. Authentication & Authorization
- **JWT (JSON Web Tokens)**: Primary mechanism for stateless API authentication. Tokens are issued upon successful login and validated on subsequent requests.
    - Short-lived access tokens and longer-lived refresh tokens.
- **OAuth 2.0 (via `django-allauth` or similar)**: For third-party authentication (e.g., "Sign in with Google/LinkedIn"), simplifying user registration and login.
- **Django's Permission System**: Combined with DRF permissions for role-based access control (RBAC) and object-level permissions, ensuring users can only access their own data or perform actions they are authorized for.

### 10.2. Data Encryption
- **In Transit**: SSL/TLS enforced for all communication between clients, the backend, and external services (HTTPS).
- **At Rest**:
    - **Database Encryption**: Utilizing encryption features provided by PostgreSQL or the cloud database service (e.g., AWS RDS encryption).
    - **Sensitive Fields**: Application-level encryption for highly sensitive data fields (e.g., API keys for user-linked services) using libraries like `cryptography`.
    - **Resume Files**: Encrypting stored resume files.
    - **AES-256**: Target encryption standard.

### 10.3. Input Validation & Sanitization
- **DRF Serializers**: Used extensively for validating incoming API request data (data types, formats, required fields).
- **Django Forms**: For any server-side rendered forms (e.g., in the admin).
- **ORM Protection**: Django's ORM helps prevent SQL injection vulnerabilities.
- **Output Encoding**: Ensuring that data rendered in templates or API responses is properly encoded to prevent XSS attacks.

### 10.4. Security Headers
Implementation of standard security headers to protect against common web vulnerabilities:
- `Content-Security-Policy`
- `Strict-Transport-Security`
- `X-Content-Type-Options`
- `X-Frame-Options`
- `Referrer-Policy`

### 10.5. Dependency Management
- **Regular Updates**: Keeping all libraries and frameworks (Python, Django, third-party packages) up-to-date to patch known vulnerabilities.
- **Vulnerability Scanning**: Using tools like `pip-audit` or GitHub Dependabot to identify and address vulnerabilities in dependencies.

### 10.6. Compliance
- Adherence to data privacy regulations like **GDPR** and **CCPA**, including:
    - User consent mechanisms.
    - Data access and deletion requests.
    - Data breach notification procedures.
    - Privacy Impact Assessments.

## 11. Development & DevOps

### 11.1. Version Control: Git
- **Platform**: GitHub (or similar like GitLab, Bitbucket).
- **Workflow**: Feature branching (e.g., Gitflow or GitHub Flow), pull requests, code reviews.

### 11.2. Containerization: Docker
- **Purpose**: Standardizing development, testing, and deployment environments. Ensures consistency across different machines and stages.
- **`Dockerfile`**: Defines the application image.
- **`docker-compose.yml`**: For managing multi-container local development environments (app, database, Redis, Celery workers).

### 11.3. Orchestration: Kubernetes (Future / As Scalability Demands)
- **Purpose**: Automating deployment, scaling, and management of containerized applications in production.
- **Consideration**: While potentially overkill for initial launch, it's a target for when the application scales significantly.

### 11.4. CI/CD: GitHub Actions
- **Purpose**: Automating the build, test, and deployment pipeline.
- **Workflows**:
    - Run linters and formatters on every push/PR.
    - Execute automated tests (unit, integration).
    - Build Docker images.
    - Deploy to staging and production environments upon successful merges to specific branches.

### 11.5. Testing Frameworks
- **Unit Testing**: Python's `unittest` module or `pytest` (preferred for its flexibility and rich feature set). Django's test client for API endpoint testing.
- **Integration Testing**: Testing interactions between different components (e.g., API and database).
- **Mocking**: Using `unittest.mock` for isolating components during tests.
- **Code Coverage**: Tools like `coverage.py` to measure test coverage.

### 11.6. Code Quality & Formatting
- **Linters**: `Flake8` for enforcing PEP 8 style guide and detecting common errors.
- **Formatters**: `Black` for consistent code formatting, `isort` for organizing imports.
- **Pre-commit Hooks**: Automating linting and formatting before commits.

## 12. Monitoring & Logging

### 12.1. Application Performance Monitoring (APM)
- **Tools**: Sentry (for error tracking and performance monitoring), New Relic, or Datadog.
- **Purpose**: Tracking API endpoint performance, identifying bottlenecks, monitoring error rates, and tracing requests.

### 12.2. Infrastructure Monitoring
- **Tools**: Prometheus & Grafana, or cloud provider-specific tools (e.g., AWS CloudWatch).
- **Purpose**: Monitoring server health (CPU, memory, disk, network), database performance, cache performance, and Celery queue lengths.

### 12.3. Logging
- **Framework**: Python's built-in `logging` module, configured for structured logging (e.g., JSON format).
- **Centralized Logging**: ELK Stack (Elasticsearch, Logstash, Kibana) or cloud-based solutions (e.g., AWS CloudWatch Logs, Grafana Loki).
- **Log Levels**: Proper use of DEBUG, INFO, WARNING, ERROR, CRITICAL levels.

## 13. Scalability & Performance
The chosen stack is designed with scalability and performance in mind:
- **Stateless Application Servers**: Django applications can be scaled horizontally by running multiple instances behind a load balancer.
- **Scalable Celery Workers**: Celery workers can be scaled independently based on task queue load.
- **Database Scalability**: PostgreSQL supports read replicas and partitioning. Cloud-managed versions offer easy scaling.
- **Redis Scalability**: Redis can be clustered for higher availability and throughput.
- **Efficient Querying**: Use of Django ORM best practices, database indexing (including GiST/GIN for PgVector).
- **Caching**: Aggressive caching strategies to reduce database load and API latency.
- **Asynchronous Operations**: Offloading non-critical tasks to Celery.

## 14. Future Considerations
- **GraphQL**: As an alternative or addition to REST APIs for more flexible data fetching.
- **Serverless Functions**: For specific, event-driven tasks to optimize costs and scalability.
- **Advanced AI/ML Models**: Developing custom ML models for more sophisticated job matching or career path prediction.
- **Data Warehousing & BI**: For more complex analytics beyond the operational database.

## 15. Conclusion
The Jobraker backend technical stack is a carefully selected combination of mature, scalable, and feature-rich technologies. Centered around Python and Django, it leverages PostgreSQL for robust data storage, Redis for caching and task queuing, and Celery for asynchronous processing. This stack provides a solid foundation for building a high-performance, secure, and AI-driven job automation platform, with clear paths for future growth and evolution.

---

*This document is subject to updates as the Jobraker platform evolves.*
