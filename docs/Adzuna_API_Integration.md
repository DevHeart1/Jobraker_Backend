# Jobraker Backend: Adzuna API Integration Documentation

**Version:** 1.0
**Last Updated:** June 15, 2025
**Status:** Initial Draft

## 0. Document Control

| Version | Date          | Author(s)    | Summary of Changes                                     |
| :------ | :------------ | :----------- | :----------------------------------------------------- |
| 1.0     | June 15, 2025 | AI Assistant | Initial draft based on user-provided information.    |

---

## 1. Executive Summary

This document provides a comprehensive technical overview of the Adzuna API integration within the Jobraker backend system. Adzuna serves as a critical external data source, supplying extensive job advertisement data that underpins Jobraker's core functionalities, including job discovery, semantic matching, and market analytics. This document details the authentication mechanisms, utilized API endpoints, data ingestion and processing workflows, error handling strategies, rate limiting considerations, security protocols, and potential future enhancements. The integration is designed for robustness, scalability, and efficiency, ensuring a continuous and reliable flow of high-quality job data into the Jobraker ecosystem.

---

## 2. Introduction

### 2.1 Purpose
The purpose of this document is to provide a definitive technical reference for the integration of the Adzuna API within the Jobraker backend. It aims to equip engineers, architects, and technical stakeholders with a thorough understanding of how Jobraker leverages Adzuna data, the technical implementation details, and the operational best practices associated with this integration.

### 2.2 Scope
This document covers all aspects of the Adzuna API integration, including:
*   Authentication and authorization with the Adzuna API.
*   Detailed descriptions of consumed Adzuna API endpoints (Job Search, Job Details, Salary Data, Regional Data).
*   The end-to-end data flow, from fetching raw data to its processing, storage, and utilization within Jobraker.
*   Strategies for error handling, resilience, rate limit management, and security.
*   Monitoring and logging practices for the integration.
*   A roadmap for future enhancements and optimizations.

This document does not cover Jobraker's frontend interaction with the processed job data or the internal architecture of the Adzuna API itself beyond what is necessary for successful integration.

### 2.3 Intended Audience
This document is intended for:
*   Backend Software Engineers responsible for developing and maintaining the integration.
*   DevOps Engineers responsible for deploying and monitoring the integration.
*   System Architects involved in planning the evolution of Jobraker's data sources.
*   Technical Product Managers and stakeholders requiring an understanding of this key data dependency.

### 2.4 Definitions and Acronyms
*   **API:** Application Programming Interface
*   **CRUD:** Create, Read, Update, Delete
*   **DRF:** Django REST Framework
*   **HTTP:** Hypertext Transfer Protocol
*   **HTTPS:** Hypertext Transfer Protocol Secure
*   **JSON:** JavaScript Object Notation
*   **JWT:** JSON Web Token
*   **PaaS:** Platform as a Service
*   **RLS:** Row-Level Security
*   **SDK:** Software Development Kit
*   **TTL:** Time To Live (for caching)

---

## 3. Adzuna API Integration Architecture

### 3.1 Overview
The Adzuna API integration is a vital component of Jobraker's data ingestion pipeline. It is primarily managed by a dedicated Celery task (`fetch_adzuna_jobs`) orchestrated by Celery Beat for periodic execution. This task interacts with the Adzuna API via a specialized client within the `IntegrationService`, which encapsulates logic for authentication, request formation, response parsing, error handling, and rate limit adherence.

### 3.2 Authentication
Jobraker authenticates with the Adzuna API using an `app_id` and `app_key`.
*   **Credential Storage:** These credentials are treated as sensitive secrets and are securely stored as environment variables within the Render PaaS environment (e.g., using Render Environment Groups). They are never hardcoded into the application source code.
*   **Request Authorization:** For each API request, the `app_id` and `app_key` are included as query parameters, as per Adzuna API specifications. All communication occurs over HTTPS.

### 3.3 Consumed Adzuna API Endpoints

The Jobraker backend primarily utilizes the following Adzuna API endpoints:

#### 3.3.1 Job Search Endpoint
*   **URL:** `https://api.adzuna.com/v1/api/jobs/{country}/search/{page}`
*   **Method:** `GET`
*   **Purpose:** Retrieves paginated lists of job advertisements based on specified search criteria. This is the main endpoint for ingesting job listings.
*   **Key Parameters Used by Jobraker:**
    *   `app_id`: (Required) Jobraker's Adzuna application ID.
    *   `app_key`: (Required) Jobraker's Adzuna application key.
    *   `country`: (Required) Target country code (e.g., `gb`, `us`, `de`). Jobraker may iterate through a list of configured target countries.
    *   `page`: (Required) Page number for results, managed by the ingestion task to fetch all available jobs.
    *   `results_per_page`: Number of results per page (e.g., 50, Adzuna's maximum).
    *   `what`: Keywords for job titles, skills (e.g., "python developer", "project manager"). The ingestion task may use broad terms or iterate through categories.
    *   `where`: Location query (e.g., "London", "Berlin", "New York").
    *   `salary_min`: Minimum salary filter.
    *   `full_time`: Filter for full-time positions (1 for true).
    *   `permanent`: Filter for permanent positions (1 for true).
    *   `sort_by`: Sorting criteria (e.g., `date` for newest jobs, `salary` - though date is often preferred for ingestion).
    *   `to_date`, `from_date`: Potentially used for incremental updates, fetching jobs posted within a specific timeframe.
*   **Example Request (Conceptual):**
    `https://api.adzuna.com/v1/api/jobs/gb/search/1?app_id=YOUR_APP_ID&app_key=YOUR_APP_KEY&what=software&where=london&results_per_page=50&sort_by=date`
*   **Example JSON Response Snippet:**
    ```json
    {
      "count": 12345,
      "results": [
        {
          "id": "1234567890",
          "title": "Senior Software Engineer",
          "location": {
            "display_name": "London, UK",
            "area": ["UK", "London"]
          },
          "company": { "display_name": "Tech Solutions Ltd." },
          "created": "2025-06-15T10:00:00Z",
          "salary_min": 70000,
          "salary_max": 90000,
          "description": "Join our innovative team...",
          "contract_type": "permanent",
          "redirect_url": "https://www.adzuna.co.uk/jobs/details/1234567890?v=..."
        }
        // ... more results
      ]
    }
    ```

#### 3.3.2 Job Details Endpoint (Less Frequently Used for Bulk Ingestion)
*   **URL:** `https://api.adzuna.com/v1/api/jobs/{country}/ad/{job_id}`
*   **Method:** `GET`
*   **Purpose:** Retrieves detailed information for a single job listing, identified by its Adzuna job ID. This might be used on-demand if a user requests more details not initially stored, or for specific enrichment tasks, but is generally avoided for bulk ingestion due to rate limits.
*   **Key Parameters:** `app_id`, `app_key`, `country`, `job_id`.
*   **Response:** Detailed JSON object for the specific job.

#### 3.3.3 Salary Data Endpoint
*   **URL:** `https://api.adzuna.com/v1/api/salary/{country}/history`
*   **Method:** `GET`
*   **Purpose:** Retrieves historical salary data for specific job titles and locations. This data can be used for analytics, providing salary insights to users, or for benchmarking.
*   **Key Parameters:** `app_id`, `app_key`, `country`, `location0`, `location1` (for regions), `title_only` (for job title).
*   **Example Request:**
    `https://api.adzuna.com/v1/api/salary/gb/history?app_id=YOUR_APP_ID&app_key=YOUR_APP_KEY&location0=UK&location1=London&title_only=software%20engineer`
*   **Response:** JSON object with historical salary trends (average, min, max).

#### 3.3.4 Regional Data (Geodata) Endpoint
*   **URL:** `https://api.adzuna.com/v1/api/jobs/{country}/geodata`
*   **Method:** `GET`
*   **Purpose:** Provides counts of job advertisements in specific sub-regions. Useful for regional job market analytics.
*   **Key Parameters:** `app_id`, `app_key`, `country`, `location0`, `location1`, etc. for location hierarchy.
*   **Response:** JSON object with job counts for the specified region(s).

---

## 4. Data Ingestion and Processing Workflow

The ingestion of job data from Adzuna is a critical background process within Jobraker.

**Diagram: Adzuna Data Ingestion Flow**
```mermaid
graph TD
    A[Celery Beat Scheduler] -- Triggers --> B(fetch_adzuna_jobs Celery Task)
    B -- Forms Request --> C{Adzuna API Client (in IntegrationService)}
    C -- HTTPS GET --> D[Adzuna API Endpoints]
    D -- JSON Response --> C
    C -- Parses & Validates --> E{Raw Job Data}
    B -- Iterates/Paginates --> C
    E -- Transformation & Normalization --> F{Standardized Job Data}
    F -- Deduplication --> G{Unique Job Listings}
    G -- Embedding Generation (OpenAI) --> H{Jobs with Embeddings}
    H -- Bulk Upsert --> I[Jobraker PostgreSQL DB (JobListing Table)]
    I -- Updates --> J(pgvector Index)
    K[Error Handling & Logging] -- Monitors --> B
    L[Rate Limit Manager] -- Controls --> C
```

**Step 1: Scheduled Task Execution**
*   A Celery Beat task (`fetch_adzuna_jobs`) is scheduled to run periodically (e.g., every 30-60 minutes). The schedule is configurable.

**Step 2: API Request Construction and Execution**
*   The `fetch_adzuna_jobs` task iterates through configured countries and search parameter combinations.
*   It uses the `IntegrationService` to construct requests for the Adzuna Job Search endpoint, handling pagination to retrieve all relevant new or updated listings since the last run (if using date filters).
*   The `IntegrationService` manages API key injection and adherence to Adzuna's request format.

**Step 3: Data Retrieval and Parsing**
*   The Adzuna API returns job listings in JSON format.
*   The `IntegrationService` parses the JSON response, performing initial validation (e.g., checking for expected fields, response structure).

**Step 4: Data Transformation and Normalization**
*   **Standardization:** Raw data from Adzuna is transformed into Jobraker's internal `JobListing` model schema. This involves:
    *   Mapping Adzuna fields to Jobraker fields.
    *   Normalizing location data (e.g., standardizing city/country names).
    *   Normalizing company names (e.g., "Tech Ltd." vs "Tech Limited").
    *   Standardizing contract types, job categories.
    *   Converting date formats.
*   **Data Cleaning:** Removing HTML tags from descriptions, handling missing values gracefully.

**Step 5: Deduplication**
*   Before storing, job listings are checked for duplicates against existing records in the Jobraker database.
*   Deduplication logic typically uses the Adzuna job ID (`id` field in their response) as the primary unique identifier. If not available or for cross-source deduplication, a combination of title, company, location, and description hash might be used.

**Step 6: Semantic Embedding Generation (Optional but Recommended)**
*   For unique, new, or significantly updated job listings, the job description (and potentially title) is sent to an embedding service (e.g., OpenAI's `text-embedding-3-small` API via another Celery task or a direct call if performance allows).
*   The resulting vector embedding is stored with the job listing, enabling semantic search capabilities.

**Step 7: Database Storage**
*   Processed, unique, and potentially embedded job listings are bulk upserted (insert or update if exists) into the Jobraker `JobListing` table in PostgreSQL.
*   If `pgvector` is used, the vector index on the embedding column is updated.

**Step 8: Logging and Monitoring**
*   The entire process is logged extensively, including the number of jobs fetched, processed, added, updated, and any errors encountered.
*   Metrics (e.g., API call latency, number of jobs ingested) are exported to Prometheus for monitoring in Grafana.

---

## 5. Error Handling and Resilience

Robust error handling is crucial for maintaining a reliable data pipeline.

*   **API Error Codes:** The `IntegrationService` interprets HTTP status codes from Adzuna:
    *   `200 OK`: Success.
    *   `400 Bad Request`: Log error, investigate request parameters. Unlikely for scheduled tasks if parameters are static.
    *   `401 Unauthorized`: Critical error. API keys may be invalid or expired. Trigger an immediate alert to administrators. Halt further requests until resolved.
    *   `403 Forbidden`: Similar to 401, indicates an access issue.
    *   `404 Not Found`: For specific resource requests (e.g., Job Details). Log and skip if not critical.
    *   `429 Too Many Requests`: Handled by rate limiting logic (see Section 6).
    *   `5xx Server Error (Adzuna side)`: Adzuna server issues. Implement retries.
*   **Retry Mechanisms:**
    *   For transient errors (e.g., network issues, Adzuna `5xx` errors, `429` if not handled by proactive throttling), the `IntegrationService` or Celery task implements an exponential backoff with jitter retry strategy.
    *   Example: Retry up to 5 times, with delays of 1s, 2s, 4s, 8s, 16s (+ random jitter).
*   **Circuit Breaker:** A circuit breaker pattern (e.g., using a library like `pybreaker`) is implemented within the `IntegrationService`. If Adzuna API calls fail repeatedly (e.g., 5 consecutive failures), the circuit opens for a configurable period (e.g., 5 minutes), preventing further calls and reducing load on both systems. After the timeout, a limited number of trial requests are allowed; if successful, the circuit closes.
*   **Task-Level Error Handling:** Celery tasks have their own error handling. If `fetch_adzuna_jobs` fails critically after retries, it logs the error comprehensively (e.g., to Sentry) and may send an alert. It should not crash the worker but terminate gracefully for that run.
*   **Data Validation Errors:** If fetched data fails validation during transformation (e.g., unexpected format), the specific job record is skipped, logged with details, and the process continues for other records.

---

## 6. Rate Limiting and Quota Management

Adzuna API enforces rate limits (e.g., 1,000 requests/day for the free tier, potentially higher for paid plans). Effective management is essential.

*   **Proactive Throttling:**
    *   Jobraker's `IntegrationService` includes a client-side rate limiter (e.g., token bucket or leaky bucket algorithm) to control the frequency of requests sent to Adzuna, ensuring it stays below the known limit over a period.
    *   The ingestion task (`fetch_adzuna_jobs`) is designed to spread its requests over time if a large number of pages need to be fetched, rather than making many requests in a short burst.
*   **Caching (for on-demand user-facing features, not bulk ingestion):**
    *   If Jobraker were to use Adzuna endpoints directly for user-facing searches (which it primarily does not, preferring its own DB), responses for common queries would be cached in Redis with an appropriate TTL. This is less relevant for the primary bulk ingestion workflow.
*   **Reactive Handling (`429 Too Many Requests`):**
    *   If a `429` response is received, the `IntegrationService` respects the `Retry-After` header if provided.
    *   If not provided, it falls back to the exponential backoff strategy and may temporarily halt new requests for a longer period.
*   **Monitoring Usage:**
    *   The number of API calls made to Adzuna is tracked (e.g., Prometheus counter).
    *   Alerts are configured if usage approaches the daily/monthly quota (e.g., 80% of limit), allowing administrators to investigate or consider plan upgrades.
*   **Prioritized Ingestion:** If nearing rate limits, the ingestion task might prioritize fetching data from specific key countries or categories.

---

## 7. Security Considerations

*   **API Key Security:**
    *   Adzuna `app_id` and `app_key` are stored as encrypted environment variables in Render.
    *   Access to these variables is restricted within the Jobraker backend.
    *   Keys are never exposed in client-side code or version control.
    *   Regular review and potential rotation of API keys if supported by Adzuna and deemed necessary.
*   **HTTPS Enforcement:** All communication with the Adzuna API is exclusively over HTTPS, ensuring data confidentiality and integrity during transit.
*   **Restricted Access:** The `IntegrationService` and the Celery workers performing Adzuna calls are internal backend components. Direct external access to trigger Adzuna API calls through Jobraker is not permitted.
*   **Data Handling:**
    *   Data retrieved from Adzuna is processed and stored in Jobraker's database. Access to this database is controlled by standard database security measures and application-level permissions (RLS).
    *   Jobraker adheres to its own privacy policy regarding the storage and use of job data, even if sourced externally.
*   **Input Sanitization (for parameters sent to Adzuna):** While most parameters are system-generated, any user-derived input used in `what` or `where` parameters for on-demand calls (if any) would be sanitized.

---

## 8. Monitoring and Logging

*   **Logging:**
    *   The `fetch_adzuna_jobs` Celery task and `IntegrationService` generate detailed logs for each run and API interaction.
    *   Logs include: timestamp, task ID, API endpoint called, parameters used, success/failure status, number of records fetched/processed, errors encountered (with stack traces if applicable).
    *   Logs are structured (e.g., JSON format) and shipped to a centralized logging platform (e.g., Logtail, ELK stack) for analysis and troubleshooting.
*   **Metrics (Prometheus/Grafana):**
    *   `adzuna_api_requests_total`: Counter for total requests made to Adzuna (labeled by endpoint, country, status code).
    *   `adzuna_api_request_duration_seconds`: Histogram for Adzuna API call latency.
    *   `adzuna_jobs_ingested_total`: Counter for the number of new jobs successfully ingested.
    *   `adzuna_jobs_updated_total`: Counter for existing jobs updated.
    *   `adzuna_api_errors_total`: Counter for errors encountered during API calls.
    *   `celery_task_succeeded_total{task_name="fetch_adzuna_jobs"}`
    *   `celery_task_failed_total{task_name="fetch_adzuna_jobs"}`
*   **Alerting (Alertmanager/Sentry):**
    *   Alerts for critical API errors (e.g., `401 Unauthorized`, persistent `5xx` errors).
    *   Alerts if the `fetch_adzuna_jobs` task fails repeatedly.
    *   Alerts if API request rate approaches defined limits.
    *   Sentry integration for capturing and reporting exceptions within the Celery task or service.

---

## 9. Future Enhancements

*   **Dynamic Parameter Optimization:** Implement logic to dynamically adjust search parameters (`what`, `where`, `category`) for the `fetch_adzuna_jobs` task based on observed job market activity or areas where Jobraker has fewer listings, to maximize the relevance of ingested jobs.
*   **Delta Ingestion using Adzuna `id`:** If Adzuna API supports filtering by a "last seen Adzuna ID" or a more precise "updated since" timestamp beyond just date, leverage this for more efficient delta/incremental ingestion, reducing the volume of data fetched and processed.
*   **Expanded Country Coverage:** Systematically expand the list of countries from which jobs are ingested, based on Jobraker's strategic market expansion. This would involve adding new country codes to the ingestion task's configuration.
*   **Direct Feedback Loop for Job Quality:** If users flag jobs sourced from Adzuna as low quality, expired, or inaccurate, implement a mechanism to potentially deprioritize or filter similar jobs from future Adzuna ingestions, or even report back to Adzuna if they have a mechanism for this.
*   **Automated Category Mapping Refinement:** Use NLP techniques to improve the mapping of Adzuna's job categories or titles to Jobraker's internal taxonomy, enhancing search relevance and filtering.
*   **Integration with Adzuna Job Widget/API for "Apply on Company Site":** For jobs where Adzuna provides a direct link to the original application page, ensure this is captured and prioritized to enhance the user application experience, potentially bypassing intermediate tracking links if they add no value.

---

## 10. Conclusion

The Adzuna API integration is a cornerstone of Jobraker's ability to provide a comprehensive and timely database of job opportunities to its users. Through careful architectural design, robust error handling, diligent rate limit management, and strong security practices, Jobraker ensures that this external dependency is managed effectively and reliably. The detailed data ingestion and processing workflow transforms raw Adzuna data into valuable, structured information, directly powering core platform features. Continuous monitoring and a roadmap for future enhancements will ensure that the Adzuna integration continues to evolve, supporting Jobraker's mission to deliver an exceptional job search experience.

---

## 11. References

*   Official Adzuna API Documentation (Link to be added if available publicly)
*   Jobraker Backend Architecture Document (`Backend_Architecture_Advanced.md`)
*   Jobraker Application Flow Document (`App_Flow.md`)
*   Jobraker Celery Task Management Guidelines (Internal Document)

---
