"""
Centralized metrics definitions for the Jobraker backend.
This prevents duplicate metric registration errors.
"""

try:
    from prometheus_client import Counter, Histogram

    # Adzuna metrics
    ADZUNA_API_REQUESTS_TOTAL = Counter(
        "jobraker_adzuna_api_requests_total",
        "Total requests made to Adzuna API.",
        ["endpoint", "status_code", "country"],
    )

    ADZUNA_API_REQUEST_DURATION_SECONDS = Histogram(
        "jobraker_adzuna_api_request_duration_seconds",
        "Latency of Adzuna API calls.",
        ["endpoint", "country"],
    )

    ADZUNA_JOBS_PROCESSED_TOTAL = Counter(
        "jobraker_adzuna_jobs_processed_total",
        "Total Adzuna jobs processed by the system.",
        ["country", "status"],
    )

    ADZUNA_API_ERRORS_TOTAL = Counter(
        "jobraker_adzuna_api_errors_total",
        "Total errors encountered during Adzuna API calls from client perspective.",
        ["endpoint", "country", "error_type"],
    )

    ADZUNA_CIRCUIT_BREAKER_STATE_CHANGES_TOTAL = Counter(
        "jobraker_adzuna_circuit_breaker_state_changes_total",
        "Total number of Adzuna API circuit breaker state changes.",
        ["new_state"],
    )

    # OpenAI metrics
    OPENAI_API_CALLS_TOTAL = Counter(
        "jobraker_openai_api_calls_total",
        "Total calls made to OpenAI API.",
        ["type", "model", "status"],
    )

    OPENAI_API_CALL_DURATION_SECONDS = Histogram(
        "jobraker_openai_api_call_duration_seconds",
        "Latency of OpenAI API calls.",
        ["type", "model"],
    )

    OPENAI_MODERATION_CHECKS_TOTAL = Counter(
        "jobraker_openai_moderation_checks_total",
        "Total moderation checks performed.",
        ["target"],
    )

    OPENAI_MODERATION_FLAGGED_TOTAL = Counter(
        "jobraker_openai_moderation_flagged_total",
        "Total content flagged by moderation.",
        ["target"],
    )

    # Skyvern metrics
    SKYVERN_APPLICATION_SUBMISSIONS_TOTAL = Counter(
        "jobraker_skyvern_application_submissions_total",
        "Total job applications submitted via Skyvern.",
        ["status"],
    )

except ImportError:
    # Create mock objects if prometheus_client is not available
    class MockMetric:
        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            pass

        def observe(self, *args, **kwargs):
            pass

    ADZUNA_API_REQUESTS_TOTAL = MockMetric()
    ADZUNA_API_REQUEST_DURATION_SECONDS = MockMetric()
    ADZUNA_JOBS_PROCESSED_TOTAL = MockMetric()
    ADZUNA_API_ERRORS_TOTAL = MockMetric()
    ADZUNA_CIRCUIT_BREAKER_STATE_CHANGES_TOTAL = MockMetric()
    OPENAI_API_CALLS_TOTAL = MockMetric()
    OPENAI_API_CALL_DURATION_SECONDS = MockMetric()
    OPENAI_MODERATION_CHECKS_TOTAL = MockMetric()
    OPENAI_MODERATION_FLAGGED_TOTAL = MockMetric()
    SKYVERN_APPLICATION_SUBMISSIONS_TOTAL = MockMetric()
