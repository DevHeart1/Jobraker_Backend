# Jobraker Backend: Skyvern API Integration Documentation

**Version:** 1.0
**Last Updated:** June 15, 2025
**Status:** Initial Draft

## 0. Document Control

| Version | Date          | Author(s)    | Summary of Changes                                  |
| :------ | :------------ | :----------- | :-------------------------------------------------- |
| 1.0     | June 15, 2025 | AI Assistant | Initial comprehensive draft based on user input.    |

---

## 1. Executive Summary

This document outlines the technical integration of the Skyvern AI-powered browser automation platform within the Jobraker backend. Skyvern's capability to dynamically interpret and interact with web pages, including handling complex elements like multi-step forms, CAPTCHAs, and 2FA, is leveraged by Jobraker to automate the submission of job applications across diverse online platforms. This integration significantly enhances user efficiency by enabling batch applications and streamlines a traditionally time-consuming process. This document details the architectural design, API interactions, data workflows, error handling, security measures, and future development roadmap for this critical integration.

---

## 2. Introduction

### 2.1 Purpose
This document serves as the definitive technical guide for the Skyvern API integration within the Jobraker backend. Its primary objective is to provide engineers, architects, and relevant stakeholders with a comprehensive understanding of the integration's mechanics, operational protocols, and strategic importance to Jobraker's automated application feature.

### 2.2 Scope
The scope of this document includes:
*   Authentication and secure communication with the Skyvern API.
*   Detailed specifications of Skyvern API endpoints utilized by Jobraker.
*   The end-to-end workflow for initiating, monitoring, and processing automated job applications via Skyvern.
*   Strategies for managing errors, ensuring resilience, adhering to rate limits, and maintaining security.
*   Operational aspects, including monitoring, logging, and alert mechanisms.
*   A forward-looking perspective on potential enhancements to the integration.

This document does not cover the frontend user interface elements related to initiating auto-applications nor the internal workings of the Skyvern platform itself beyond the API contract.

### 2.3 Intended Audience
This document is intended for:
*   Backend Software Engineers involved in the development, maintenance, and troubleshooting of the Skyvern integration.
*   DevOps Engineers responsible for the deployment, monitoring, and operational stability of services interacting with Skyvern.
*   System Architects evaluating and planning the evolution of Jobraker's automation capabilities.
*   Technical Product Managers and stakeholders requiring insight into the functionality and dependencies of the automated application feature.

### 2.4 Definitions and Acronyms
*   **AI:** Artificial Intelligence
*   **API:** Application Programming Interface
*   **CAPTCHA:** Completely Automated Public Turing test to tell Computers and Humans Apart
*   **Celery:** Distributed Task Queue
*   **HTTP:** Hypertext Transfer Protocol
*   **HTTPS:** Hypertext Transfer Protocol Secure
*   **JSON:** JavaScript Object Notation
*   **LLM:** Large Language Model
*   **PII:** Personally Identifiable Information
*   **PaaS:** Platform as a Service
*   **2FA:** Two-Factor Authentication

### 2.5 Overview of Skyvern
Skyvern is an advanced AI-driven browser automation platform. It utilizes Large Language Models (LLMs) and computer vision to understand and interact with web interfaces dynamically. Unlike traditional automation tools that depend on static selectors (which break with website updates), Skyvern can navigate complex web workflows, fill forms, handle CAPTCHAs, and manage multi-step processes across a wide array of websites. This makes it particularly well-suited for automating tasks like job application submissions on diverse career portals.

---

## 3. Integration Architecture

### 3.1 High-Level Overview
The Jobraker backend orchestrates the automated job application process by leveraging the Skyvern API. When a user opts to auto-apply for jobs, or when the system identifies suitable jobs for auto-application based on user preferences, the Jobraker backend prepares the necessary data and initiates tasks with Skyvern. Skyvern then performs the browser automation, and Jobraker monitors the task progress, retrieves results, and updates the application status for the user.

### 3.2 Component Breakdown
*   **Jobraker Backend:** (Django/DRF application)
    *   Manages user profiles, job listings, and application records.
    *   Contains the `IntegrationService` which includes a Skyvern API client.
    *   Uses Celery workers for asynchronous communication with Skyvern.
*   **Skyvern API:**
    *   Exposes RESTful endpoints for task creation, status monitoring, and result retrieval.
    *   Handles the AI-powered browser automation.
*   **Job Application Platforms:** External websites (career portals, company job pages) where Skyvern performs the application submission.

### 3.3 Workflow Diagram
```mermaid
graph TD
    A[User Action / System Trigger in Jobraker] --> B{Jobraker Backend (API Layer)}
    B -- Prepares Data (Profile, Resume, Job URLs) --> C(submit_skyvern_application Celery Task)
    C -- HTTPS POST (Run Task) --> D[Skyvern API (/v1/run-task)]
    D -- Returns task_id --> C
    C -- Stores task_id, Updates Application Status (e.g., 'PendingSkyvern') --> E[Jobraker PostgreSQL DB]

    F[Celery Beat Scheduler (Optional Polling)] --> G(check_skyvern_task_status Celery Task)
    G -- Uses stored task_id --> E
    G -- HTTPS GET (Task Status) --> H[Skyvern API (/v1/task-status/:task_id)]
    H -- Returns status (e.g., 'COMPLETED', 'FAILED') --> G
    G -- Updates Application Status --> E

    I[Skyvern Webhook (Preferred)] -- HTTPS POST (Task Completion Notification) --> J{Jobraker Webhook Receiver Endpoint}
    J -- Parses Notification, Updates Application Status --> E

    K(retrieve_skyvern_task_results Celery Task / Part of G or J)
    K -- HTTPS GET (Task Results) --> L[Skyvern API (/v1/task-results/:task_id)]
    L -- Returns results (e.g., confirmation details, errors) --> K
    K -- Stores results, Updates Application --> E
    E -- Notifies User (via NotificationService) --> M[User]
```

---

## 4. Skyvern API Integration Details

Jobraker's `IntegrationService` contains a dedicated Skyvern client responsible for all interactions with the Skyvern API.

### 4.1 Authentication
*   **Method:** Bearer Token Authentication.
*   **API Key Storage:** The Skyvern API key is a sensitive credential, stored securely as an environment variable in the Render PaaS (e.g., via Render Environment Groups). It is never hardcoded.
*   **Request Header:** Each request to the Skyvern API must include the API key in the `Authorization` header:
    ```
    Authorization: Bearer YOUR_SKYVERN_API_KEY
    Content-Type: application/json
    ```

### 4.2 Key API Endpoints

#### 4.2.1 Create Automation Task (`POST /v1/run-task`)
*   **Purpose:** Initiates a new browser automation task with Skyvern.
*   **Request Body (JSON):**
    ```json
    {
      "prompt": "Apply to the job at the following URL using the provided resume and profile information. Target URL: https://careers.example.com/jobs/12345. Fill all required fields accurately.",
      "inputs": {
        "resume_base64": "BASE64_ENCODED_RESUME_CONTENT", // Or a secure URL to the resume
        "cover_letter_base64": "BASE64_ENCODED_COVER_LETTER_CONTENT", // Optional
        "user_profile_data": {
          "full_name": "Jane Doe",
          "email": "jane.doe@example.com",
          "phone": "+1234567890",
          "linkedin_url": "https://linkedin.com/in/janedoe",
          // ... other relevant PII and application-specific answers
        },
        "target_job_url": "https://careers.example.com/jobs/12345"
        // Potentially other inputs like custom answers to specific questions if known
      },
      "webhook_url": "https://api.jobraker.com/v1/webhooks/skyvern/task-updates", // Optional: For Skyvern to send status updates
      "max_duration_seconds": 1800 // Optional: Max time for task execution
    }
    ```
*   **Prompt Engineering:** The `prompt` is crucial. It instructs Skyvern on the objective. Jobraker dynamically generates this prompt based on the target job URL and user data. It may include specific instructions for handling known quirks of certain job platforms.
*   **Response (JSON):**
    ```json
    {
      "task_id": "tsk_xxxxxxxxxxxxxxx",
      "status": "PENDING" // Or "RUNNING" if started immediately
    }
    ```
*   **Jobraker Action:** The returned `task_id` is stored in the Jobraker database, typically linked to the `Application` record, to track this specific Skyvern automation attempt.

#### 4.2.2 Monitor Task Status (`GET /v1/task-status/{task_id}`)
*   **Purpose:** Retrieves the current status of a previously created task.
*   **URL Parameter:** `task_id` (obtained from the task creation response).
*   **Response (JSON):**
    ```json
    {
      "task_id": "tsk_xxxxxxxxxxxxxxx",
      "status": "COMPLETED", // Other statuses: PENDING, RUNNING, FAILED, CANCELED, REQUIRES_ATTENTION
      "message": "Application submitted successfully.", // Optional: status message
      "created_at": "2025-06-15T10:00:00Z",
      "updated_at": "2025-06-15T10:05:00Z"
    }
    ```
*   **Jobraker Action:** Used for polling if webhooks are not implemented or as a fallback. The `Application` record in Jobraker is updated based on the status.

#### 4.2.3 Retrieve Task Results (`GET /v1/task-results/{task_id}`)
*   **Purpose:** Fetches detailed results or outputs of a completed task.
*   **URL Parameter:** `task_id`.
*   **Response (JSON):**
    ```json
    {
      "task_id": "tsk_xxxxxxxxxxxxxxx",
      "status": "COMPLETED",
      "data": {
        "application_confirmation_id": "APP-CONF-98765",
        "submission_timestamp": "2025-06-15T10:04:55Z",
        "screenshots_urls": [
          "https://skyvern.results.storage/screenshot1.png",
          "https://skyvern.results.storage/screenshot_confirmation.png"
        ],
        "logs": [
          "Navigated to job page.",
          "Filled personal details.",
          "Uploaded resume.",
          "Handled CAPTCHA.",
          "Application submitted."
        ]
      },
      "error_details": null // Populated if status is FAILED
    }
    ```
*   **Jobraker Action:** Stores relevant confirmation details (e.g., `application_confirmation_id`) in the `Application` record. Logs or screenshot URLs might be stored for auditing or troubleshooting.

---

## 5. Job Application Workflow in Jobraker (using Skyvern)

**Step 1: Task Initiation (User or System Triggered)**
*   A user selects jobs for auto-application, or Jobraker's `auto_apply_jobs` Celery task identifies eligible jobs based on user preferences and match scores.

**Step 2: Data Preparation by Jobraker Backend**
*   The backend retrieves the user's profile information (name, contact, experience snippets), resume (e.g., from S3, potentially converting to Base64 if required by Skyvern), and the target job URL(s).
*   It constructs the detailed `prompt` and `inputs` for the Skyvern API.

**Step 3: Asynchronous Skyvern Task Creation**
*   A Celery task (`submit_skyvern_application`) is dispatched for each job application.
*   This task calls the Skyvern API's `/v1/run-task` endpoint via the `IntegrationService`.
*   The `Application` record in Jobraker's database is created or updated with an initial status (e.g., `PENDING_SKYVERN_SUBMISSION`) and the `skyvern_task_id`.

**Step 4: Skyvern Task Execution**
*   Skyvern receives the task and executes the browser automation: navigates to the job URL, fills forms, uploads files, handles CAPTCHAs/2FA as per its AI capabilities.

**Step 5: Status Updates and Result Handling**
*   **Webhook (Preferred):** If a `webhook_url` was provided, Skyvern sends POST requests to Jobraker's webhook receiver endpoint upon significant status changes (e.g., `COMPLETED`, `FAILED`). The Jobraker webhook handler parses the notification, updates the `Application` status and stores results.
*   **Polling (Fallback):** If webhooks are not used or fail, a scheduled Celery task (`check_skyvern_task_status`) periodically queries Skyvern's `/v1/task-status/{task_id}` endpoint for pending tasks. If a task is `COMPLETED` or `FAILED`, it then calls `/v1/task-results/{task_id}`.
*   The `Application` record is updated with the final status (e.g., `APPLIED_VIA_SKYVERN`, `SKYVERN_APPLICATION_FAILED`) and any relevant confirmation data or error messages from Skyvern.

**Step 6: User Notification**
*   Jobraker's `NotificationService` informs the user about the outcome of the automated application (success or failure with reasons, if available).

---

## 6. Advanced Interaction Handling by Skyvern

Skyvern's AI-driven approach allows it to manage complex web interactions that often challenge traditional automation:
*   **Multi-Step Forms:** Skyvern can navigate through multiple pages or stages of an application form, maintaining context.
*   **CAPTCHA Challenges:** Skyvern has built-in capabilities to solve various types of CAPTCHAs. Jobraker relies on Skyvern to handle these transparently.
*   **Two-Factor Authentication (2FA):** If a job platform requires login and 2FA, Skyvern may be able to handle it if pre-configured or if it can interact with user-provided one-time passwords (this requires careful security consideration and user consent, and might be out of scope for initial MVP).
*   **File Uploads:** Skyvern can handle file upload dialogs for resumes, cover letters, etc., using the Base64 encoded file content provided by Jobraker or by accessing secure URLs.
*   **Dynamic Content & Layout Changes:** Skyvern's LLM and computer vision approach makes it resilient to website layout changes that would break selector-based automation.

Jobraker's role is to provide Skyvern with the most accurate and complete data possible in the `inputs` to facilitate these interactions.

---

## 7. Error Handling and Resilience

*   **Skyvern API Errors:**
    *   The `IntegrationService` client for Skyvern handles standard HTTP errors (4xx, 5xx).
    *   `401 Unauthorized`: Critical. Skyvern API key issue. Alert admin, halt Skyvern tasks.
    *   `400 Bad Request`: Issue with Jobraker's request payload. Log details, potentially flag the specific job/profile for review.
    *   `429 Too Many Requests`: Handled by rate limiting logic (Section 8).
    *   `5xx Server Error (Skyvern side)`: Implement retries with exponential backoff.
*   **Retry Mechanisms:**
    *   Celery tasks calling Skyvern API implement retries for transient network issues or Skyvern `5xx` errors.
    *   The `IntegrationService` may also have internal retries for API calls.
*   **Circuit Breaker:** A circuit breaker pattern is applied to Skyvern API calls. If calls consistently fail, the circuit opens, preventing further calls for a period, and alerts are triggered.
*   **Skyvern Task Failures:**
    *   If Skyvern reports a task as `FAILED`, Jobraker retrieves the `error_details` from `/v1/task-results`.
    *   The `Application` status is updated to reflect failure (e.g., `SKYVERN_APPLICATION_FAILED`).
    *   The error details are logged. If the error is actionable by the user (e.g., "Resume format not supported by this site"), this information is relayed.
    *   Persistent failures for specific job sites might indicate a need to refine Skyvern prompts or report issues to Skyvern support.
*   **Jobraker-Side Failures:** Errors within Jobraker (e.g., database issues while updating application status) are handled by Jobraker's standard error logging and alerting (Sentry).

---

## 8. Rate Limiting and Quota Management

*   **Skyvern API Limits:** Skyvern may impose rate limits on API calls or concurrent task executions. Jobraker must be aware of these limits (obtained from Skyvern documentation or account details).
*   **Jobraker's Throttling Strategies:**
    *   Celery queues for Skyvern tasks (`skyvern_submissions`) are managed to control the rate of new task creation, preventing overwhelming the Skyvern API or exceeding concurrency limits.
    *   The number of concurrent Celery workers processing these queues can be adjusted.
    *   If `429 Too Many Requests` is received, the system backs off and retries after the `Retry-After` interval or a calculated delay.
*   **Usage Monitoring:**
    *   Jobraker tracks the number of Skyvern tasks created and their statuses.
    *   Metrics on task success/failure rates and average duration are collected.
    *   Alerts can be configured if failure rates are high or if `429` errors become frequent.

---

## 9. Security Considerations

*   **API Key Management:**
    *   Skyvern API key is stored securely as an encrypted environment variable in Render.
    *   Access is restricted to the `IntegrationService`.
    *   Consider periodic key rotation if supported and deemed necessary.
*   **Data Encryption:**
    *   All communication with the Skyvern API is over HTTPS.
    *   Sensitive user data (resume content, PII in `inputs`) sent to Skyvern must be handled with care. While Skyvern is responsible for its platform's security, Jobraker ensures data is encrypted in transit.
    *   Jobraker's internal storage of resumes and PII follows its own encryption-at-rest policies.
*   **Access Control:** Only authorized Jobraker backend services (specifically, Celery workers running the `submit_skyvern_application` task via `IntegrationService`) can initiate tasks with Skyvern.
*   **Data Privacy & PII Handling:**
    *   Jobraker only sends the minimum necessary PII to Skyvern required for a successful application.
    *   Users are informed (e.g., in privacy policy and terms of service) that their data will be processed by a third-party automation service for auto-applications.
    *   Jobraker relies on Skyvern's data handling and privacy policies for data processed on their platform.
*   **Audit Logging:** All Skyvern API requests (task creation, status checks) initiated by Jobraker are logged with timestamps, task IDs, and key parameters for auditing and troubleshooting.

---

## 10. Monitoring and Logging

*   **Logging:**
    *   Celery tasks interacting with Skyvern log detailed information: task initiation, Skyvern `task_id` received, parameters sent, status updates polled/received, final results, errors.
    *   Logs are structured (JSON) and sent to a centralized logging system.
*   **Metrics (Prometheus/Grafana):**
    *   `skyvern_api_requests_total`: Counter for requests to Skyvern (labeled by endpoint, status code).
    *   `skyvern_api_request_duration_seconds`: Histogram for Skyvern API call latency.
    *   `skyvern_tasks_created_total`: Counter for new tasks initiated.
    *   `skyvern_tasks_completed_total`: Counter for successfully completed Skyvern tasks.
    *   `skyvern_tasks_failed_total`: Counter for failed Skyvern tasks (labeled by error type if possible).
    *   `skyvern_task_duration_seconds`: Histogram for end-to-end Skyvern task completion time.
*   **Alerting (Alertmanager/Sentry):**
    *   Alerts for critical Skyvern API errors (e.g., `401 Unauthorized`).
    *   Alerts if Skyvern task failure rate exceeds a defined threshold.
    *   Alerts for repeated `429 Too Many Requests` errors.
    *   Sentry for capturing exceptions within Jobraker's Skyvern integration logic.

---

## 11. Future Enhancements

*   **Granular Real-Time Feedback:** Explore deeper integration with Skyvern if they offer more granular real-time progress updates (e.g., "Step 1 of 5 completed: Personal Details Entered") to display richer feedback to the user in Jobraker.
*   **Dynamic Prompt Optimization:** Develop a system to A/B test different Skyvern prompts for specific job platforms or application types to improve success rates.
*   **User-Provided Overrides/Inputs:** Allow users to provide specific answers to known tricky questions for certain applications, which Jobraker can then pass to Skyvern in the `inputs`.
*   **Smart Retry for Application Failures:** If a Skyvern task fails due to a potentially remediable issue (e.g., a website was temporarily down), implement a smarter retry logic in Jobraker, perhaps after a longer delay or with a slightly modified prompt.
*   **Cost-Benefit Analysis of Skyvern Usage:** Continuously monitor the cost of Skyvern services against the benefits (application success rates, user satisfaction) to optimize usage.
*   **Direct Resume URL Passthrough:** If Skyvern supports directly fetching resumes from a secure URL (e.g., a pre-signed S3 URL provided by Jobraker) instead of Base64 encoding, implement this to simplify data handling.

---

## 12. Conclusion

The integration of Skyvern's AI-powered browser automation capabilities into the Jobraker backend is a strategic enhancement that significantly streamlines the job application process for users. By abstracting the complexities of interacting with diverse job platforms, Jobraker, through Skyvern, offers a powerful auto-apply feature. This document has detailed the architecture, API usage, workflows, and operational considerations for this integration, emphasizing security, resilience, and monitoring. As both Jobraker and Skyvern evolve, this integration will continue to be refined to maximize efficiency and user success in the job market.

---

## 13. References

*   Skyvern API Documentation (Official - Link to be added)
*   Jobraker Backend Architecture Document (`Backend_Architecture_Advanced.md`)
*   Jobraker Application Flow Document (`App_Flow.md`)

---
