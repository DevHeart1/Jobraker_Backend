# Jobraker — Backend Architecture Document

**Version:** 1.1 (Enhanced)
**Date:** June 15, 2025

## 0. Document Control

| Version | Date          | Author(s)   | Summary of Changes                                   |
| :------ | :------------ | :---------- | :--------------------------------------------------- |
| 1.0     | June 2025     | Original    | Initial draft.                                       |
| 1.1     | June 15, 2025 | AI Assistant | Comprehensive review, restructuring, and elaboration. |

## 1. Introduction

### 1.1 Purpose
This document provides a comprehensive architectural overview of the Jobraker backend system. It details the system's components, their interactions, data storage strategies, deployment model, and key cross-cutting concerns such as security, scalability, and observability.

### 1.2 Scope
The scope of this document encompasses the backend services, databases, asynchronous processing systems, external integrations, and operational aspects of the Jobraker platform. It does not cover the detailed design of frontend applications or the internal workings of third-party services beyond their integration points.

### 1.3 Intended Audience
This document is intended for software architects, developers, DevOps engineers, and technical stakeholders involved in the development, maintenance, and strategic planning of the Jobraker platform.

### 1.4 Definitions and Acronyms
*   **DRF:** Django REST Framework
*   **JWT:** JSON Web Token
*   **OAuth2:** Open Authorization 2.0
*   **Celery:** Distributed Task Queue
*   **pgvector:** PostgreSQL extension for vector similarity search
*   **ANN:** Approximate Nearest Neighbor
*   **RAG:** Retrieval Augmented Generation
*   **CI/CD:** Continuous Integration / Continuous Deployment
*   **PaaS:** Platform as a Service (referring to Render)
*   **LB:** Load Balancer
*   **WS:** WebSocket
*   **CRUD:** Create, Read, Update, Delete
*   **SDK:** Software Development Kit
*   **VPC:** Virtual Private Cloud

## 2. Executive Summary
Jobraker is an innovative, autonomous job search and auto-application platform. Its backend architecture is engineered for real-time responsiveness and robust asynchronous processing. The system leverages a Python-based stack, featuring Django and Django REST Framework for its core API, Celery for distributed task management, and PostgreSQL with pgvector for advanced semantic search capabilities. Key functionalities include automated job ingestion from external sources like Adzuna, AI-powered semantic matching of jobs to user profiles using OpenAI embeddings, and automated job applications via services like Skyvern.

The platform is deployed on Render, a modern PaaS, utilizing managed services for PostgreSQL and Redis to minimize operational overhead. This architecture prioritizes scalability, reliability, security, and developer velocity, enabling rapid feature evolution and a seamless user experience.

## 3. Architectural Goals and Constraints

### 3.1 Key Architectural Goals
*   **Autonomy:** Enable automated job discovery and application processes with minimal user intervention.
*   **Responsiveness:** Provide low-latency API responses (target p90 < 200ms) for a fluid user experience.
*   **Scalability:** Design components to scale horizontally to accommodate growing user load and data volume.
*   **Reliability:** Ensure high availability and fault tolerance through robust error handling, retries, and managed infrastructure.
*   **Low Operational Overhead:** Leverage managed services and automation to simplify deployment, maintenance, and operations.
*   **Security:** Implement comprehensive security measures across all layers of the application.
*   **Extensibility:** Facilitate the addition of new features and integrations with a modular design.
*   **Developer Velocity:** Enable rapid iteration and development cycles through a well-defined architecture and modern tooling.

### 3.2 Significant Constraints
*   **Platform-as-a-Service (PaaS) Deployment:** The system is designed for deployment on Render, influencing infrastructure choices.
*   **Reliance on External Services:** Core functionalities depend on third-party APIs (Adzuna, Skyvern, OpenAI), requiring robust integration patterns.
*   **Cost Management:** Optimize resource utilization and external service usage (especially OpenAI) to maintain cost-effectiveness.

## 4. Logical Architecture

### 4.1 Layered Overview
The Jobraker backend employs a layered architecture to promote separation of concerns, modularity, and maintainability.

```mermaid
graph TD
    A[Presentation (Frontend/Mobile)] -->|REST/WebSocket (JSON)| B(API Layer - Django + DRF)
    A -->|JWT/OAuth2| B
    B -->|Post/Put/Get| C(Service Layer)
    C -->|Async Tasks| D(Asynchronous Layer - Celery)
    D -->|DB/Cache/Vector Search| E(Persistence & Cache)
    E -->|HTTP/HTTPS| F(External Services)

    subgraph "User Interaction & Core Logic"
        B[API Layer (Django + DRF)
• Auth (JWT/OAuth2)
• Profiles (CRUD, Auto-Apply Settings)
• Jobs (Search, Filters, Match Scoring)
• Applications (Manual Apply, Logging, Webhooks)
• Chat (Message Persistence, AI Reply Enqueue)
• Integrations (Encrypted Credentials)]
        C[Service Layer
• MatchService (Résumé Tokenization, pgvector ANN)
• NotificationService (Event Creation, DB Write, WS Push)
• IntegrationService (External API Facade - Retry, Metrics, Circuit Breaker)]
    end

    subgraph "Background Processing"
        D[Asynchronous Layer (Celery)
• fetch_adzuna_jobs (Job Ingestion, Embedding)
• auto_apply_jobs (Vector Similarity Search, Skyvern Apply)
• generate_bot_reply (RAG with OpenAI GPT-4.1 Mini)
• notify_user (Email/WS Notifications)]
    end

    subgraph "Data & External Systems"
        E[Persistence & Cache
• PostgreSQL (+ pgvector extension)
• Redis (Cache, Celery Broker/Backend)]
        F[External Services
• Adzuna (Job Feed via REST)
• Skyvern (Automated Application via REST)
• OpenAI (Chat & Embedding APIs)]
    end

    W[WebSocket Gateway (Django Channels - Optional)]
    A --> W
    W --> C
```

**Explanation of Layers:**

*   **Presentation Layer:** External clients (web, mobile applications) interacting with the system.
*   **API Layer (Django + DRF):** Handles incoming HTTP requests, authentication, request validation, serialization, and delegates business logic to the Service Layer or enqueues tasks for the Asynchronous Layer. Optionally includes a WebSocket Gateway (Django Channels) for real-time communication.
*   **Service Layer:** Encapsulates core business logic and orchestrates interactions between different parts of the system. Promotes reusability and testability.
*   **Asynchronous Layer (Celery):** Executes long-running, computationally intensive, or I/O-bound tasks in the background, ensuring the API layer remains responsive.
*   **Persistence & Cache Layer:** Manages data storage (PostgreSQL) and caching (Redis). Includes specialized data handling like vector embeddings with pgvector.
*   **External Services Layer:** Interfaces with third-party APIs crucial for Jobraker's functionality.

### 4.2 Key Technology Choices & Rationale
*   **Django & DRF (Python):** Rapid development, robust ecosystem, strong ORM, excellent for building REST APIs.
*   **Celery (Python):** Mature, flexible distributed task queue for handling asynchronous operations.
*   **PostgreSQL:** Powerful open-source relational database with strong transactional integrity.
    *   **pgvector:** Enables efficient semantic similarity searches directly within the database.
*   **Redis:** High-performance in-memory data store for caching, session management, and Celery message brokering.
*   **OpenAI APIs:** State-of-the-art models for natural language understanding (chat) and generating embeddings for semantic search.
*   **Skyvern:** Specialized service for automating job applications across various platforms.
*   **Render (PaaS):** Simplifies deployment and infrastructure management, allowing the team to focus on application development.

## 5. Component Deep Dive

### 5.1 API Layer (Django + DRF)
The API layer serves as the primary entry point for client applications.

*   **Module Breakdown:**
    *   `accounts`: Manages user authentication (JWT/OAuth2), profile creation and updates (CRUD), and auto-apply preference settings.
    *   `jobs`: Provides read-only access to job listings, supporting advanced filtering, pagination, and dynamic annotation of match scores.
    *   `applications`: Handles manual job applications, logs application history, and can receive status updates via webhooks (e.g., from Skyvern).
    *   `chat`: Persists chat messages between users and the AI assistant; enqueues tasks for AI response generation.
    *   `integrations`: Securely stores and manages encrypted credentials for external services (Adzuna, Skyvern, potentially Gmail, LinkedIn for future features).
    *   `notifications`: Offers an API for clients to pull notifications and mark them as read.
*   **Design Principles:**
    *   **Statelessness:** API servers are stateless, facilitating horizontal scaling and simplifying deployment.
    *   **RESTful Conventions:** Adherence to REST principles for resource naming, HTTP methods, and status codes.
    *   **Versioning:** API versioning (e.g., `/api/v1/...`) will be implemented to manage changes and maintain backward compatibility. (Implicitly, the doc uses `/auth/*` etc., suggesting a base path, but explicit versioning is a good practice).
    *   **Permissions & Throttling:** DRF's permission and throttling classes are utilized to control access and prevent abuse.

### 5.2 Service Layer
This layer abstracts business logic from the API views and asynchronous tasks.

*   **Purpose and Responsibilities:**
    *   Decouples business rules from presentation/delivery concerns.
    *   Enhances code reusability across different entry points (API vs. tasks).
    *   Improves testability by allowing logic to be tested in isolation.
*   **Service Object Details (`services.py`):**
    *   `MatchService`:
        *   Processes and tokenizes user résumés and job descriptions.
        *   Leverages `pgvector` for Approximate Nearest Neighbor (ANN) search to find semantically similar jobs/profiles.
        *   Calculates and returns a percentage-based match score.
    *   `NotificationService`:
        *   Acts as a central factory for creating various types of notifications (system events, user-specific alerts).
        *   Persists notifications to the database.
        *   Can optionally push real-time notifications over WebSockets if a user has an active connection.
    *   `IntegrationService`:
        *   Provides a unified facade for interacting with external API clients (Adzuna, Skyvern, OpenAI).
        *   Implements common patterns like request retries (with exponential backoff), metrics collection for external calls, and circuit breaker patterns to handle external service unavailability gracefully.

### 5.3 Asynchronous Processing Layer (Celery)
Handles tasks that are not suitable for synchronous execution within an API request-response cycle.

*   **Role and Importance:**
    *   Ensures API responsiveness by offloading time-consuming operations.
    *   Enables scheduled and periodic tasks critical for platform autonomy.
    *   Manages resource-intensive computations like embedding generation and AI interactions.
*   **Task Breakdown & Queueing Strategy:**
    *   **Tasks:**
        *   `fetch_adzuna_jobs`: Scheduled (e.g., every 30 minutes via Celery Beat). Performs paginated calls to Adzuna's `/search` endpoint, upserts job data into the `Job` table, generates embeddings for job descriptions (e.g., using OpenAI), and stores these vectors in `pgvector`.
        *   `auto_apply_jobs`: Scheduled (e.g., hourly via Celery Beat). For each user profile with `auto_apply=True`:
            1.  Queries `Job` vectors within a specified cosine similarity radius of the user's profile vector.
            2.  Filters results based on the user's defined match score threshold and other criteria.
            3.  Calls Skyvern's `/apply` endpoint for eligible jobs.
        *   `generate_bot_reply`: Triggered on a new user message in the chat. Implements a Retrieval Augmented Generation (RAG) loop:
            1.  Gathers relevant context (e.g., recent chat history, user profile information, application statuses) using function-calling capabilities.
            2.  Sends the context and user query to OpenAI's GPT-4.1 Mini (or a similar model).
            3.  Stores the AI-generated bot reply.
        *   `notify_user`: Triggered by events like application status changes or new relevant job matches. Emits notifications via configured channels (e.g., email, WebSocket push).
    *   **Queueing Strategy:**
        *   Multiple Celery queues are utilized to prioritize tasks and isolate workloads (e.g., `default`, `cpu_intensive`, `io_bound`, `chat_processing`). This prevents long-running or resource-heavy tasks in one category from blocking others.
        *   Workers are configured to consume tasks from specific queues.

### 5.4 Persistence & Caching Layer

*   **PostgreSQL (+ pgvector):**
    *   **Role:** Primary datastore for all relational data, including user profiles, job listings, applications, chat messages, and notifications.
    *   **pgvector:** Enables storing and searching high-dimensional vector embeddings directly within PostgreSQL, crucial for semantic search and job matching.
    *   **Schema:** Detailed in Section 6.1.
*   **Redis:**
    *   **Role:**
        *   **Caching:** Caches frequently accessed data (e.g., resolved job details, user session information) to reduce database load and improve API latency.
        *   **Celery Broker:** Acts as the message broker for Celery, managing task queues.
        *   **Celery Backend:** Stores task results and states.
        *   **Rate Limiting:** Can be used to store counters for API rate limiting.

### 5.5 External Service Integrations
Interactions with third-party services are managed through the `IntegrationService`.

*   **Adzuna:** REST API for ingesting job feeds.
*   **Skyvern:** REST API for automating job applications.
*   **OpenAI:** APIs for chat completion (GPT models) and text embeddings.
*   **Resilience:** Integrations are designed with fault tolerance in mind, including retries, timeouts, and circuit breakers.

## 6. Data Model and Management

### 6.1 Database Schema (Key Tables)

| Table          | Notes                                                                                                | Key Fields (Illustrative)                                                                 |
| :------------- | :--------------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------------- |
| `auth_user`    | Standard Django user model.                                                                          | `id`, `username`, `email`, `password`, `is_active`, `date_joined`                         |
| `user_profile` | One-to-one with `auth_user`. Stores extended user information.                                       | `user_id (FK)`, `role`, `skills (JSONB)`, `resume_url`, `auto_apply_flag`, `match_threshold` |
| `job`          | Stores job listings.                                                                                 | `id (PK)`, `adzuna_id (UNIQUE)`, `title`, `description`, `company`, `location`, `payload (JSONB)`, `embedding (vector[1536])` |
| `application`  | Tracks job applications made by users.                                                               | `id (PK)`, `profile_id (FK)`, `job_id (FK)`, `status (ENUM)`, `auto_applied (BOOL)`, `applied_at`, `updated_at` |
| `chat_message` | Stores messages in chat conversations.                                                               | `id (PK)`, `profile_id (FK)`, `conversation_id`, `role (ENUM: user/assistant/system)`, `content (TEXT)`, `parent_id (FK, for threading)`, `created_at` |
| `notification` | Stores notifications for users.                                                                      | `id (PK)`, `profile_id (FK)`, `type (ENUM)`, `message`, `payload (JSONB)`, `is_read (BOOL)`, `created_at` |
| `integration`  | Stores encrypted credentials and status for third-party service integrations per user/system.        | `id (PK)`, `profile_id (FK, optional)`, `provider (ENUM)`, `credentials (AES-encrypted)`, `is_connected (BOOL)`, `last_synced_at` |

### 6.2 Indexing Strategy
Effective indexing is crucial for query performance.

*   **GIN Index on `user_profile.skills` (JSONB):** Facilitates efficient searching for users based on specific skills (tag-like search).
*   **pgvector Approximate Index (IVFFlat) on `job.embedding`:**
    *   **Type:** IVFFlat with `nlist` (e.g., 200 lists) is chosen for a balance between search speed and accuracy for high-dimensional vector similarity searches.
    *   **Rationale:** Essential for fast semantic matching of jobs to profiles and vice-versa. The number of lists (`nlist`) is a tunable parameter based on dataset size and performance requirements.
*   **Composite Index on `application(profile_id, status)`:** Optimizes queries for fetching a user's applications filtered by status, common in dashboards.
*   **Standard Indexes:** Primary keys (PK) are automatically indexed. Foreign keys (FK) are typically indexed to improve join performance and referential integrity checks. Indexes on timestamp fields (`created_at`, `updated_at`) are beneficial for range queries and sorting.

### 6.3 Data Lifecycle and Integrity
*   **Data Validation:** Implemented at the API layer (DRF serializers) and within model save methods.
*   **Referential Integrity:** Enforced by PostgreSQL using foreign key constraints.
*   **Data Backups:** Managed by Render for PostgreSQL (e.g., daily full backups with point-in-time recovery options).
*   **Data Archival/Deletion:** Strategies for archiving old data (e.g., old job listings, inactive user data) will be developed as the platform matures to manage storage costs and maintain performance.

## 7. Key Workflows and Data Flows

### 7.1 User Registration and Authentication
1.  User registers via API (`/auth/register/`) with email/password or OAuth2.
2.  `accounts` module handles user creation, profile initialization.
3.  JWT access and refresh tokens are issued.
4.  User logs in (`/auth/login/`), receives new JWTs.
5.  Subsequent API requests include JWT access token in `Authorization` header.

### 7.2 Job Ingestion and Semantic Matching (via `fetch_adzuna_jobs` task)
1.  Celery Beat triggers `fetch_adzuna_jobs`.
2.  Task queries Adzuna API for new/updated job listings.
3.  Job data is cleaned, transformed, and an embedding vector is generated for the description using OpenAI.
4.  Job details and embedding are upserted into the `job` table. `pgvector` index is updated.

### 7.3 Manual Job Application
1.  User searches for jobs (`/jobs/ GET`). The `MatchService` (called by the DRF ViewSet) annotates results with `match_score` based on semantic similarity between user profile vector and job embedding vectors.
2.  User clicks "Apply" on a job. Frontend sends a request to `/applications/ POST` with `job_id`.
3.  DRF ViewSet creates an `Application` record with `status='pending_manual_submission'`.
4.  A Celery task `submit_manual_application(application_id)` is enqueued.
5.  The task retrieves application details and calls the Skyvern API to submit the application.
6.  Upon successful Skyvern response (e.g., 201 Created), the task updates `Application.status` to `'applied'` and triggers a notification via `NotificationService`.

### 7.4 Automated Job Application (Auto-Apply Loop via `auto_apply_jobs` task)
1.  Celery Beat triggers `auto_apply_jobs`.
2.  Task iterates through users with `auto_apply_flag=True` and a valid `match_threshold`.
3.  For each user, `MatchService` queries `job.embedding` using `pgvector` to find jobs semantically similar to the user's profile vector, exceeding their `match_threshold`.
4.  Filters out already applied or dismissed jobs.
5.  For each eligible job, the task calls Skyvern API to submit the application.
6.  An `Application` record is created with `status='applied'` and `auto_applied=True`.
7.  `NotificationService` informs the user of the auto-application (potentially with a WebSocket push if active).

### 7.5 AI Chat (RAG) Interaction
1.  User sends a message via frontend. Frontend POSTs to `/chat/`.
2.  DRF ViewSet persists the message in `chat_message` table with `role='user'` and enqueues `generate_bot_reply(message_id)` Celery task.
3.  `generate_bot_reply` task:
    a.  Retrieves recent conversation history and relevant user context (profile, applications) using predefined "tool" functions.
    b.  Constructs a prompt for OpenAI's GPT-4.1 Mini, including history, context, and the new user message.
    c.  May involve multiple calls to OpenAI if using function-calling to gather more specific data from local DB functions (e.g., "get_application_status_for_job_X").
    d.  Receives the final AI-generated answer.
4.  Task stores the AI's response in `chat_message` with `role='assistant'`.
5.  Frontend polls `/chat/` for new messages or receives the new message via a WebSocket push from `NotificationService` (if `notify_user` is triggered by new assistant message).

## 8. Deployment Architecture (Render Platform)

### 8.1 Service Topology
| Render Service      | Container Image                 | Role                                      | Scaling Strategy                                     | Notes                               |
| :------------------ | :------------------------------ | :---------------------------------------- | :--------------------------------------------------- | :---------------------------------- |
| `jobraker-web`      | `ghcr.io/org/jobraker:latest`   | Django + Gunicorn (Web Server)            | Auto-scale 1–10 instances; e.g., 512 MiB RAM each    | Handles API & WebSocket traffic.    |
| `jobraker-worker`   | Same image, `CMD celery ... -Q default,io_bound` | Celery Workers (Default, I/O Queues) | Auto-scale 1–50 dynos; based on queue depth/CPU | Processes general & I/O tasks.      |
| `jobraker-cpu-worker`| Same image, `CMD celery ... -Q cpu_intensive` | Celery Workers (CPU Queues)            | Auto-scale 1-10 dynos; based on queue depth/CPU  | Handles CPU-bound tasks (matching). |
| `jobraker-beat`     | Same image, `CMD celery ... beat` | Celery Beat (Scheduler)                   | 1 replica (singleton)                                | Schedules periodic tasks.           |
| `PostgreSQL`        | Render Managed Service          | Primary Database                          | Vertical scaling (e.g., 2 vCPU / 8 GiB RAM)          | Daily full backups.                 |
| `Redis`             | Render Managed Service          | Cache, Celery Broker/Backend              | Vertical scaling (e.g., 1 GiB RAM)                   |                                     |
| `Static/Media`      | Render Disk / Cloudflare R2     | Static assets & user media (resumes)      | CDN for performance                                  | R2 provides S3-compatible API.      |

*   All services operate behind a Render-provided TLS load balancer.
*   Health checks are exposed at `/healthz/` endpoint for monitoring by Render.

### 8.2 Build and Deployment Pipeline (CI/CD)
1.  **Pull Request (PR):** Developer pushes changes to a feature branch and opens a PR against `main`.
    *   **GitHub Actions Trigger:** Automatically runs linters (`ruff`), static analysis (`bandit` for security), and unit/integration tests (`pytest`).
2.  **Merge to `main`:** Upon successful checks and code review, PR is merged.
    *   **GitHub Actions Trigger:**
        *   Builds Docker container image.
        *   Pushes image to GitHub Container Registry (GHCR) tagged with commit SHA and `latest`.
        *   Optionally, runs migration smoke tests against a staging environment.
3.  **Render Auto-Deploy:**
    *   Render service (configured with a deploy hook or watching GHCR) detects the new image.
    *   Render initiates a new deployment:
        *   Pulls the new image.
        *   Runs database migrations (`python manage.py migrate`).
        *   Performs a rolling update of web/worker instances, gated by health checks.
4.  **Canary Deployment (Optional but Recommended):**
    *   A small percentage of traffic (e.g., 5%) is routed to a canary dyno running the new version for a defined period (e.g., 10 minutes).
    *   Monitored for errors/performance regressions before full rollout. Render might offer features to facilitate this, or it can be managed with more advanced LB configurations if available.

### 8.3 Environment Configuration
*   Render Environment Groups are used to manage environment variables (secrets, API keys, settings) securely for different environments (dev, staging, prod).
*   Configuration is separated from code, following Twelve-Factor App principles.

## 9. Cross-Cutting Concerns

### 9.1 Scalability and Performance
*   **Horizontal Scaling:** Stateless API (`jobraker-web`) and Celery worker (`jobraker-worker`, `jobraker-cpu-worker`) services are designed for horizontal scaling based on load or queue depth.
*   **Asynchronous Processing:** Offloading non-critical path operations to Celery ensures API responsiveness.
*   **Task Fan-Out & Queue Separation:** Distributing tasks across different Celery queues (e.g., `default`, `cpu_intensive`, `io_bound`, `chat`) prevents resource contention and allows independent scaling of worker pools for different task types.
*   **Database Optimization:**
    *   Efficient queries, appropriate indexing (including `pgvector` for ANN).
    *   Connection pooling (e.g., `pgBouncer` provided or configured with Render's Postgres).
    *   Read replicas for PostgreSQL can be introduced if read load becomes a bottleneck for analytics or non-critical read paths.
*   **Caching:** Redis is used extensively for caching API responses, session data, and frequently accessed database query results.
*   **Content Delivery Network (CDN):** Static assets and media files served via CDN (e.g., Cloudflare with R2) to reduce latency and server load.

### 9.2 Reliability and Fault Tolerance
*   **Idempotent Tasks:** Celery tasks are designed to be idempotent where possible (e.g., using unique task keys derived from `job_id + profile_id` for application submissions) to prevent duplicate processing on retries.
*   **Retry Mechanisms:** Implemented in `IntegrationService` for external API calls and within Celery tasks for transient failures, typically with exponential backoff.
*   **Dead Letter Queues (DLQs):** Configure Celery to route tasks that fail repeatedly to a DLQ for manual inspection and re-processing if necessary.
*   **Back-Pressure Handling:** Mechanisms like temporarily disabling auto-apply via a feature flag if Redis queue depth exceeds a critical threshold (e.g., > 50k items) to prevent system overload.
*   **Managed Services:** Leveraging Render's managed PostgreSQL and Redis reduces the burden of manual backups, patching, and failover management.
*   **Health Checks:** Implemented for all services, allowing Render's infrastructure to automatically restart unhealthy instances.

### 9.3 Security Architecture
*   **Transport Layer Security (TLS):** TLS 1.3 (or latest stable) enforced for all external communication (API, WebSockets). Render's load balancer handles TLS termination.
*   **Authentication & Authorization:**
    *   **JWT:** Short-lived access tokens (e.g., 15 minutes) and longer-lived refresh tokens (e.g., 30 days) for user sessions. Secure storage of refresh tokens (e.g., `HttpOnly` cookies).
    *   **OAuth2:** Integration with trusted identity providers (e.g., Google, LinkedIn) via `django-allauth`.
    *   **Permissions:** Granular permissions enforced at the API layer using DRF's permission system.
*   **Secrets Management:**
    *   Render Environment Groups for storing API keys, database credentials, and other secrets.
    *   Secrets are encrypted at rest by Render.
*   **Data-at-Rest Encryption:**
    *   PostgreSQL disk encryption provided by Render.
    *   Résumé files (and other sensitive media) encrypted server-side (e.g., AES-256) before storage in Cloudflare R2 or Render disk.
    *   Column-level encryption for highly sensitive fields in the database (e.g., external service credentials in `integration` table) using libraries like `django-fernet-fields`.
*   **Input Validation & Sanitization:** Rigorous validation of all incoming data at the API layer (DRF serializers) to prevent injection attacks (SQLi, XSS).
*   **Row-Level Security:** Ensured by DRF through queryset filtering based on the authenticated user (e.g., users can only access their own profiles, applications). Verified by unit tests.
*   **Egress Control:** External calls to services like Adzuna and Skyvern are routed through an egress VPC or NAT gateway with a static IP, allowing these services to add the IP to their allow-lists.
*   **Regular Security Audits:** Code reviews, dependency scanning (e.g., `pip-audit`), and periodic penetration testing (planned).
*   **Rate Limiting & Throttling:** Implemented at the API gateway or within DRF to prevent abuse.

### 9.4 Observability (Monitoring, Logging, Alerting)
*   **Metrics Collection:**
    *   **Tooling:** Prometheus sidecar containers in each application pod (web, workers).
    *   **Exports:** Metrics from Gunicorn, Celery, Django (e.g., `django-prometheus`), and database performance.
*   **Dashboards:**
    *   **Tooling:** Grafana (potentially using Render's Grafana plugin or a self-hosted instance).
    *   **Visualizations:** Key performance indicators (KPIs) such as API latency (p50, p90, p99), error rates, task execution times, queue lengths, OpenAI API usage, and costs.
*   **Logging:**
    *   **Strategy:** Centralized, structured logging (JSON format).
    *   **Pipeline:** Application logs streamed via Render's log stream to a log aggregation service (e.g., Logtail, then potentially to an ELK stack - Elasticsearch, Logstash, Kibana - or similar for advanced querying and analysis).
*   **Error Tracking:**
    *   **Tooling:** Sentry.
    *   **Integration:** Captures unhandled exceptions from Django/DRF and Celery task failures, providing stack traces, context, and alerting.
*   **Alerting:**
    *   Configured in Grafana/Prometheus Alertmanager or Sentry for critical issues (e.g., high error rates, increased latency, long queue times, Sentry error spikes).
*   **Cost Guard (OpenAI):**
    *   A daily scheduled task (e.g., Render cron job running a small script/Lambda) queries the OpenAI usage API.
    *   Posts an alert to Slack (or another notification channel) if daily/monthly spend exceeds a predefined budget threshold (e.g., > 80%).

## 10. Extensibility Roadmap (Backend Focus)
This outlines potential future enhancements and strategic directions for the backend architecture.

| Milestone             | Detail                                                                                                                               | Architectural Impact                                                                                                                               |
| :-------------------- | :----------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Embeddings v2**     | Evaluate and potentially replace OpenAI `text-embedding-3-small` with a locally hosted model (e.g., via LlamaCPP, Sentence Transformers) if cost becomes prohibitive or specific model characteristics are needed. | Introduce new service/Celery task for local embedding generation; manage local model lifecycle; potential increase in compute requirements for workers. |
| **Streaming Chat**    | Transition WebSocket-based chat to Server-Sent Events (SSE) for potentially simpler infrastructure and better handling of unidirectional server-to-client updates. | Modify Django Channels setup or replace with an SSE-compatible ASGI handler; update client-side handling.                                          |
| **Document Indexing & Talent Marketplace** | Scan uploaded résumés, parse skills/experience, and store their embeddings in `pgvector`. Enable cross-user talent search for HR platforms or internal recruiting tools. | Extend `MatchService` and `user_profile` model; new API endpoints for talent search; enhanced security/privacy controls for cross-user data access. |
| **GraphQL Gateway**   | Introduce a GraphQL API gateway for public partner access (e.g., HR platforms, job boards) to offer more flexible data querying capabilities. | Add a GraphQL library (e.g., Graphene-Django); define GraphQL schema; manage authentication and authorization for partner APIs.                     |
| **Advanced Analytics Pipeline** | Implement a data pipeline (e.g., using Kafka, Spark, or dbt with a data warehouse) for more sophisticated analytics on job market trends, user behavior, and platform performance. | Introduce new components for data ingestion, transformation, and storage (data lake/warehouse); new reporting/dashboarding tools.                  |
| **Multi-Region Deployment** | Explore deploying the application across multiple geographic regions for improved disaster recovery, lower latency for global users, and data residency compliance. | Significant infrastructure changes; data replication strategies; global load balancing; updates to CI/CD and service discovery.                     |

## 11. Conclusion
The Jobraker backend architecture is a sophisticated, layered system designed to deliver a responsive, autonomous, and intelligent job search experience. By strategically combining the strengths of Django/DRF for robust API development, Celery for scalable asynchronous processing, PostgreSQL with pgvector for advanced semantic search, and leveraging Render's managed PaaS capabilities, the platform is well-positioned for operational efficiency and rapid feature development.

The architecture emphasizes modularity, scalability, security, and observability, providing a solid foundation for current functionalities and future growth. The clear separation of concerns, coupled with a robust CI/CD pipeline and comprehensive monitoring, ensures that Jobraker can adapt to evolving user needs and technological advancements while maintaining high standards of reliability and performance. This design balances developer velocity with the demands of an enterprise-grade application, setting Jobraker on a path for sustained success and innovation in the autonomous job application space.
