"""
Skyvern API Integration Service
Handles automated job application submissions via Skyvern.
"""
import requests
import logging
import time
from typing import Dict, Any, Optional
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

# --- Prometheus Metrics Definition (conceptual) ---
SKYVERN_API_CALLS_TOTAL = Counter(
    'jobraker_skyvern_api_calls_total',
    'Total calls made to Skyvern API.',
    ['endpoint', 'status_code']
)
SKYVERN_API_CALL_DURATION_SECONDS = Histogram(
    'jobraker_skyvern_api_call_duration_seconds',
    'Latency of Skyvern API calls.',
    ['endpoint']
)
SKYVERN_API_ERRORS_TOTAL = Counter(
    'jobraker_skyvern_api_errors_total',
    'Total errors encountered during Skyvern API calls.',
    ['endpoint', 'error_type']
)
SKYVERN_CIRCUIT_BREAKER_STATE_CHANGES_TOTAL = Counter(
    'jobraker_skyvern_circuit_breaker_state_changes_total',
    'Total number of Skyvern API circuit breaker state changes.',
    ['new_state']
)
SKYVERN_APPLICATION_SUBMISSIONS_TOTAL = Counter(
    'jobraker_skyvern_application_submissions_total',
    'Total job applications submitted via Skyvern.',
    ['status'] # e.g., success, failed, requires_attention
)
# --- End Prometheus Metrics Definition ---

# Circuit Breaker States
STATE_CLOSED = "CLOSED"
STATE_OPEN = "OPEN"
STATE_HALF_OPEN = "HALF_OPEN"

class SkyvernAPIClient:
    BASE_URL = "https://api.skyvern.com/v1" # Placeholder URL from docs

    # Circuit Breaker Configuration
    CB_MAX_FAILURES = 3
    CB_RESET_TIMEOUT_SECONDS = 120
    CB_HALF_OPEN_MAX_REQUESTS = 2
    REQUEST_DELAY_SECONDS = 1 # Skyvern might be more sensitive to rapid calls

    def __init__(self):
        self.api_key = getattr(settings, 'SKYVERN_API_KEY', None)
        self.session = self._configure_session()

        self._cb_state = STATE_CLOSED
        self._cb_failures = 0
        self._cb_last_failure_time = None
        self._cb_half_open_success_count = 0

        if not self.api_key:
            logger.warning("Skyvern API key not configured. SkyvernAPIClient will not be able to make calls.")

    def _configure_session(self) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"], # Skyvern uses POST for run-task
            backoff_factor=1
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _get_headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise ValueError("Skyvern API key is not configured.")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    # --- Circuit Breaker Methods (similar to Adzuna's) ---
    def _handle_circuit_breaker_open(self):
        if self._cb_last_failure_time and \
           (time.monotonic() - self._cb_last_failure_time) > self.CB_RESET_TIMEOUT_SECONDS:
            self._cb_state = STATE_HALF_OPEN
            self._cb_half_open_success_count = 0
            SKYVERN_CIRCUIT_BREAKER_STATE_CHANGES_TOTAL.labels(new_state=STATE_HALF_OPEN).inc()
            logger.info("Skyvern Circuit Breaker: State changed to HALF_OPEN.")
        else:
            logger.warning("Skyvern Circuit Breaker: OPEN. Request blocked.")
            raise requests.exceptions.ConnectionError("Skyvern Circuit Breaker is OPEN.")

    def _handle_circuit_breaker_failure(self):
        self._cb_failures += 1
        self._cb_last_failure_time = time.monotonic()
        if self._cb_state == STATE_HALF_OPEN:
            self._cb_state = STATE_OPEN
            self._cb_failures = self.CB_MAX_FAILURES
            SKYVERN_CIRCUIT_BREAKER_STATE_CHANGES_TOTAL.labels(new_state=STATE_OPEN).inc()
            logger.warning("Skyvern Circuit Breaker: HALF_OPEN request failed. State changed back to OPEN.")
        elif self._cb_failures >= self.CB_MAX_FAILURES and self._cb_state != STATE_OPEN:
            self._cb_state = STATE_OPEN
            SKYVERN_CIRCUIT_BREAKER_STATE_CHANGES_TOTAL.labels(new_state=STATE_OPEN).inc()
            logger.warning(f"Skyvern Circuit Breaker: Max failures ({self.CB_MAX_FAILURES}) reached. State changed to OPEN.")

    def _handle_circuit_breaker_success(self):
        if self._cb_state == STATE_HALF_OPEN:
            self._cb_half_open_success_count += 1
            if self._cb_half_open_success_count >= self.CB_HALF_OPEN_MAX_REQUESTS:
                self._cb_state = STATE_CLOSED
                self._cb_failures = 0
                self._cb_last_failure_time = None
                SKYVERN_CIRCUIT_BREAKER_STATE_CHANGES_TOTAL.labels(new_state=STATE_CLOSED).inc()
                logger.info("Skyvern Circuit Breaker: HALF_OPEN requests successful. State changed to CLOSED.")
        elif self._cb_state == STATE_CLOSED and self._cb_failures > 0:
            logger.info(f"Skyvern Circuit Breaker: Successful request in CLOSED state. Resetting failures from {self._cb_failures} to 0.")
            self._cb_failures = 0
            self._cb_last_failure_time = None
    # --- End Circuit Breaker Methods ---

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            logger.error("Skyvern API key not configured. Cannot make request.")
            SKYVERN_API_ERRORS_TOTAL.labels(endpoint=endpoint, error_type='ConfigurationError').inc()
            return None # Or raise an exception

        if self._cb_state == STATE_OPEN:
            try:
                self._handle_circuit_breaker_open()
            except requests.exceptions.ConnectionError:
                 SKYVERN_API_CALLS_TOTAL.labels(endpoint=endpoint, status_code='circuit_breaker_open').inc()
                 SKYVERN_API_ERRORS_TOTAL.labels(endpoint=endpoint, error_type='CircuitBreakerOpen').inc()
                 return None


        if self.REQUEST_DELAY_SECONDS > 0:
            time.sleep(self.REQUEST_DELAY_SECONDS)

        url = f"{self.BASE_URL}{endpoint}"
        headers = self._get_headers()

        start_time = time.monotonic()
        status_code_label = 'error_no_response'
        response_json = None

        try:
            if method.upper() == 'POST':
                response = self.session.post(url, headers=headers, json=data, params=params, timeout=60) # Longer timeout for task creation
            elif method.upper() == 'GET':
                response = self.session.get(url, headers=headers, params=params, timeout=30)
            else:
                SKYVERN_API_ERRORS_TOTAL.labels(endpoint=endpoint, error_type='UnsupportedMethod').inc()
                logger.error(f"Unsupported HTTP method: {method}")
                return None

            status_code_label = str(response.status_code)
            SKYVERN_API_CALLS_TOTAL.labels(endpoint=endpoint, status_code=status_code_label).inc()
            response.raise_for_status()

            response_json = response.json()
            self._handle_circuit_breaker_success()

        except requests.exceptions.HTTPError as e:
            logger.error(f"Skyvern API HTTPError for {method} {endpoint}: {e} (Status: {status_code_label})")
            self._handle_circuit_breaker_failure()
            SKYVERN_API_ERRORS_TOTAL.labels(endpoint=endpoint, error_type='HTTPError').inc()
        except requests.exceptions.RequestException as e:
            logger.error(f"Skyvern API RequestException for {method} {endpoint}: {e}")
            self._handle_circuit_breaker_failure()
            SKYVERN_API_ERRORS_TOTAL.labels(endpoint=endpoint, error_type=e.__class__.__name__).inc()
        finally:
            duration = time.monotonic() - start_time
            SKYVERN_API_CALL_DURATION_SECONDS.labels(endpoint=endpoint).observe(duration)

        return response_json

    def run_task(self, prompt: str, inputs: Dict[str, Any], webhook_url: Optional[str] = None, max_duration_seconds: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Initiates a new browser automation task with Skyvern.
        Corresponds to POST /v1/run-task
        """
        endpoint = "/run-task"
        payload = {
            "prompt": prompt,
            "inputs": inputs,
        }
        if webhook_url:
            payload["webhook_url"] = webhook_url
        if max_duration_seconds:
            payload["max_duration_seconds"] = max_duration_seconds

        logger.info(f"Skyvern: Initiating task with prompt: {prompt[:100]}...")
        return self._make_request("POST", endpoint, data=payload)

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the current status of a previously created task.
        Corresponds to GET /v1/task-status/{task_id}
        """
        endpoint = f"/task-status/{task_id}"
        logger.info(f"Skyvern: Fetching status for task_id: {task_id}")
        return self._make_request("GET", endpoint)

    def get_task_results(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetches detailed results or outputs of a completed task.
        Corresponds to GET /v1/task-results/{task_id}
        """
        endpoint = f"/task-results/{task_id}"
        logger.info(f"Skyvern: Fetching results for task_id: {task_id}")
        return self._make_request("GET", endpoint)

# Example usage (for testing, not part of the class)
if __name__ == '__main__':
    # This block would not run in Django context directly
    # Mock settings for standalone testing
    class MockSettings:
        SKYVERN_API_KEY = "your_skyvern_api_key_here_if_testing_live" # Keep None for no actual calls

    settings.configure(default_settings=MockSettings()) # Minimal config

    logging.basicConfig(level=logging.INFO)

    client = SkyvernAPIClient()
    if client.api_key:
        # Example: Run a task
        # Note: This would make a real API call if SKYVERN_API_KEY is set
        # mock_inputs = {
        # "resume_base64": "...",
        # "user_profile_data": {"full_name": "Test User"},
        # "target_job_url": "https://example.com/job/123"
        # }
        # task_info = client.run_task("Apply to job at target_job_url.", mock_inputs)
        # if task_info and task_info.get("task_id"):
        #     logger.info(f"Task created: {task_info}")
        #     task_id = task_info["task_id"]
        #     status = client.get_task_status(task_id)
        #     logger.info(f"Task status: {status}")
        #     results = client.get_task_results(task_id) # Might be None if not completed
        #     logger.info(f"Task results: {results}")
        # else:
        #     logger.error("Failed to create Skyvern task or API key not set.")
        pass
    else:
        logger.info("Skyvern client initialized without API key, live tests skipped.")

    # Test circuit breaker logic (conceptual)
    # To test this, you'd need to mock requests.Session().post/get to raise errors
    # for _ in range(6):
    #     try:
    #         client._make_request("POST", "/run-task", data={"prompt":"test"}) # Mocked to fail
    #     except Exception as e:
    #         logger.info(f"Caught expected error: {e}")
    #     time.sleep(0.1)

    # logger.info(f"CB state after failures: {client._cb_state}")
    # time.sleep(SkyvernAPIClient.CB_RESET_TIMEOUT_SECONDS + 5)
    # try:
    #     client._make_request("POST", "/run-task", data={"prompt":"test"}) # Should be half-open
    # except Exception as e:
    #     logger.info(f"Caught expected error during half-open: {e}")
    # logger.info(f"CB state after reset attempt: {client._cb_state}")
    pass
