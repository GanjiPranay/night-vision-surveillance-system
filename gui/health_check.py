"""
gui/health_check.py
-------------------
Backend availability and readiness polling for the Flask kiosk service.

Polls the local loopback HTTP endpoint until Flask responds with HTTP 200
or a designated timeout is exceeded. Designed to prevent the kiosk window
from rendering an empty or failed webview before the backend is fully initialized.
"""

import logging
import socket
import threading
import time
import urllib.error
import urllib.request
from typing import Optional, Tuple

logger = logging.getLogger("nvsys.gui.health_check")


class HealthChecker:
    """
    Polls the local Flask backend endpoint until it returns HTTP 200 or times out.

    Attributes:
        target_url: URL to probe for HTTP readiness (defaults to /login).
        timeout_seconds: Maximum time in seconds to wait before failing.
        poll_interval_seconds: Delay in seconds between successive probes.
        last_error: Descriptive string of the most recent failure, if any.
        elapsed_seconds: Total time spent probing during the last wait cycle.
    """

    def __init__(
        self,
        target_url: str = "http://127.0.0.1:5000/login",
        timeout_seconds: float = 30.0,
        poll_interval_seconds: float = 0.5,
    ) -> None:
        """
        Initializes the health checker with configurable probe parameters.

        Args:
            target_url: Full HTTP URL to probe for server readiness.
            timeout_seconds: Maximum duration to continue polling before giving up.
            poll_interval_seconds: Interval between consecutive health probes.
        """
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")

        self.target_url: str = target_url
        self.timeout_seconds: float = timeout_seconds
        self.poll_interval_seconds: float = poll_interval_seconds
        self.last_error: Optional[str] = None
        self.elapsed_seconds: float = 0.0

    @staticmethod
    def is_port_bound(host: str = "127.0.0.1", port: int = 5000, timeout: float = 0.5) -> bool:
        """
        Quickly tests whether a TCP port is bound and accepting connections.

        Args:
            host: IP address or hostname to probe.
            port: Port number to probe.
            timeout: Socket connection timeout in seconds.

        Returns:
            True if the port accepted the connection, False otherwise.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            try:
                sock.connect((host, port))
                return True
            except (ConnectionRefusedError, socket.timeout, OSError):
                return False

    def check_health_once(self, timeout: float = 2.0) -> Tuple[bool, int, str]:
        """
        Performs a single HTTP probe against the target URL.

        Args:
            timeout: Network request timeout in seconds for this individual probe.

        Returns:
            Tuple of (is_healthy, http_status_code, status_message).
        """
        req = urllib.request.Request(
            self.target_url,
            headers={"User-Agent": "NVSYS-Kiosk-HealthCheck/1.0"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status_code = response.getcode()
                if status_code == 200:
                    self.last_error = None
                    return True, 200, "OK"
                msg = f"Unexpected HTTP status: {status_code}"
                self.last_error = msg
                return False, status_code, msg
        except urllib.error.HTTPError as exc:
            # Note: Certain endpoints might return 302/401, but /login serves 200.
            # If redirected to /login with 200 or 302, capture accurately.
            if exc.code == 200:
                self.last_error = None
                return True, 200, "OK"
            msg = f"HTTP Error {exc.code}: {exc.reason}"
            self.last_error = msg
            return False, exc.code, msg
        except urllib.error.URLError as exc:
            reason = str(exc.reason)
            msg = f"Connection error: {reason}"
            self.last_error = msg
            return False, 0, msg
        except (TimeoutError, socket.timeout):
            msg = f"Probe timed out after {timeout:.1f}s"
            self.last_error = msg
            return False, 0, msg
        except OSError as exc:
            msg = f"Socket/OS error during probe: {exc}"
            self.last_error = msg
            return False, 0, msg

    def wait_until_ready(self, stop_event: Optional[threading.Event] = None) -> bool:
        """
        Polls the target URL repeatedly until HTTP 200 is received or timeout is reached.

        Uses non-busy waiting through threading.Event.

        Args:
            stop_event: Optional threading.Event to abort waiting prematurely.

        Returns:
            True if the server responded with HTTP 200 within timeout_seconds.
            False if the probe timed out or was interrupted.
        """
        start_time = time.monotonic()
        logger.info(
            "Waiting for Flask backend at %s (timeout=%.1fs, interval=%.2fs)...",
            self.target_url,
            self.timeout_seconds,
            self.poll_interval_seconds,
        )

        internal_event = threading.Event()
        abort_event = stop_event if stop_event is not None else internal_event

        attempt = 0
        while not abort_event.is_set():
            attempt += 1
            now = time.monotonic()
            self.elapsed_seconds = now - start_time

            if self.elapsed_seconds >= self.timeout_seconds:
                logger.error(
                    "Health check timed out after %.1fs (%d attempts). Last error: %s",
                    self.elapsed_seconds,
                    attempt,
                    self.last_error or "No response from backend",
                )
                return False

            healthy, status_code, msg = self.check_health_once(
                timeout=min(2.0, self.poll_interval_seconds)
            )
            if healthy:
                logger.info(
                    "Flask backend ready in %.2fs (attempt %d). Status: %d %s",
                    self.elapsed_seconds,
                    attempt,
                    status_code,
                    msg,
                )
                return True

            logger.debug(
                "Health check probe %d failed (elapsed: %.1fs): %s",
                attempt,
                self.elapsed_seconds,
                msg,
            )

            # Interruptible delay — avoids CPU busy-waiting
            abort_event.wait(self.poll_interval_seconds)

        logger.warning("Health check aborted via stop_event after %.1fs", self.elapsed_seconds)
        return False
