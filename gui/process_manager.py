"""
gui/process_manager.py
----------------------
Manages the lifecycle of the local Flask application subprocess.

Ensures that only a single instance of the Flask backend runs, monitors
its startup and runtime health, captures stderr for diagnostics, and ensures
clean, graceful shutdown (SIGTERM -> graceful exit -> SIGKILL fallback).
"""

import collections
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Deque, List, Optional, Tuple

from gui.health_check import HealthChecker

logger = logging.getLogger("nvsys.gui.process_manager")


class FlaskProcessManager:
    """
    Spawns, monitors, and terminates the background Flask kiosk service.

    Attributes:
        app_path: Path to the backend `app.py`.
        host: Local bind host (strictly 127.0.0.1 by default).
        port: Local bind port (5000 by default).
        timeout_seconds: Maximum time to wait for health check confirmation.
        is_externally_managed: True if the backend was already running before this launcher.
    """

    def __init__(
        self,
        app_path: Optional[Path] = None,
        host: str = "127.0.0.1",
        port: int = 5000,
        timeout_seconds: float = 30.0,
    ) -> None:
        """
        Initializes the process manager with target paths and network settings.

        Args:
            app_path: Absolute or relative Path to backend app.py. If None,
                      resolves to ../app.py relative to this file.
            host: IP address on which Flask should listen (defaults to 127.0.0.1).
            port: Port on which Flask should listen (defaults to 5000).
            timeout_seconds: Maximum duration to wait for backend readiness.
        """
        if app_path is None:
            # Default to the app.py in the parent folder of gui/
            self.app_path: Path = (Path(__file__).resolve().parent.parent / "app.py").resolve()
        else:
            self.app_path = Path(app_path).resolve()

        self.host: str = host
        self.port: int = port
        self.timeout_seconds: float = timeout_seconds

        self._process: Optional[subprocess.Popen] = None
        self._is_externally_managed: bool = False
        self._shutdown_lock: threading.Lock = threading.Lock()
        self._is_shutdown: bool = False

        # Ring buffers for capturing output without memory leaks
        self._stdout_buffer: Deque[str] = collections.deque(maxlen=200)
        self._stderr_buffer: Deque[str] = collections.deque(maxlen=200)
        self._reader_threads: List[threading.Thread] = []
        self._stop_reading_event: threading.Event = threading.Event()

        self.health_checker = HealthChecker(
            target_url=f"http://{self.host}:{self.port}/login",
            timeout_seconds=self.timeout_seconds,
            poll_interval_seconds=0.5,
        )

    @property
    def is_running(self) -> bool:
        """Checks if the managed subprocess or external service is currently alive."""
        if self._is_externally_managed:
            return HealthChecker.is_port_bound(self.host, self.port)
        if self._process is not None:
            return self._process.poll() is None
        return False

    @property
    def pid(self) -> Optional[int]:
        """Returns the process ID of the managed backend subprocess, if applicable."""
        if self._process is not None:
            return self._process.pid
        return None

    def _pipe_reader(self, pipe, buffer: Deque[str], stream_name: str) -> None:
        """
        Daemon thread worker that reads lines from a subprocess pipe into a deque.

        Args:
            pipe: Subprocess output stream (stdout or stderr).
            buffer: Ring buffer storing the latest lines.
            stream_name: Label used for debug logging ('stdout' or 'stderr').
        """
        try:
            for line in iter(pipe.readline, b""):
                if self._stop_reading_event.is_set():
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip()
                buffer.append(decoded)
                if stream_name == "stderr":
                    logger.warning("[Flask stderr] %s", decoded)
                else:
                    logger.debug("[Flask stdout] %s", decoded)
        except (OSError, ValueError) as exc:
            logger.debug("Pipe reader %s stopped: %s", stream_name, exc)
        finally:
            try:
                pipe.close()
            except OSError:
                pass

    def start(self) -> bool:
        """
        Starts the Flask backend subprocess if not already running.

        Guarantees that duplicate processes are never spawned if port 5000
        is already bound. Monitors for immediate crashes during the first 5 seconds.

        Returns:
            True if the server is healthy and responding with HTTP 200.
            False if startup failed or timed out.

        Raises:
            FileNotFoundError: If app.py is missing.
            RuntimeError: If Flask process terminates immediately with an error.
        """
        # Step 1: Check if port is already bound
        if HealthChecker.is_port_bound(self.host, self.port):
            logger.info("Port %d is already bound. Probing existing backend...", self.port)
            if self.health_checker.check_health_once(timeout=2.0)[0]:
                logger.info("Existing Flask backend is already healthy. Reusing running service.")
                self._is_externally_managed = True
                return True
            logger.warning(
                "Port %d is bound but did not return HTTP 200 immediately. Waiting for readiness...",
                self.port,
            )
            if self.health_checker.wait_until_ready():
                logger.info("Existing service became ready.")
                self._is_externally_managed = True
                return True
            raise RuntimeError(
                f"Port {self.port} is already in use by another process, but is not responding "
                f"properly to health checks. Please terminate the conflicting process."
            )

        # Step 2: Validate app.py path
        if not self.app_path.is_file():
            raise FileNotFoundError(f"Backend application script not found at {self.app_path}")

        # Step 3: Configure environment
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["NV_HOST"] = self.host
        env["NV_PORT"] = str(self.port)
        env["FLASK_RUN_HOST"] = self.host
        env["FLASK_RUN_PORT"] = str(self.port)

        cmd = [sys.executable, "-u", str(self.app_path)]
        working_dir = str(self.app_path.parent)

        logger.info("Launching Flask backend: %s (cwd=%s)", " ".join(cmd), working_dir)

        try:
            self._process = subprocess.Popen(
                cmd,
                cwd=working_dir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,
            )
        except OSError as exc:
            logger.error("Failed to execute backend subprocess: %s", exc)
            raise RuntimeError(f"Unable to spawn Flask backend: {exc}") from exc

        # Step 4: Start background stream reader threads
        self._stop_reading_event.clear()
        t_out = threading.Thread(
            target=self._pipe_reader,
            args=(self._process.stdout, self._stdout_buffer, "stdout"),
            daemon=True,
            name="flask-stdout-reader",
        )
        t_err = threading.Thread(
            target=self._pipe_reader,
            args=(self._process.stderr, self._stderr_buffer, "stderr"),
            daemon=True,
            name="flask-stderr-reader",
        )
        self._reader_threads = [t_out, t_err]
        t_out.start()
        t_err.start()

        # Step 5: Check for early crash within the first 5 seconds
        early_check_deadline = time.monotonic() + 5.0
        while time.monotonic() < early_check_deadline:
            retcode = self._process.poll()
            if retcode is not None:
                # Process exited prematurely!
                time.sleep(0.2)  # allow pipe reader to catch trailing output
                stderr_summary = "\n".join(list(self._stderr_buffer)[-20:])
                logger.error(
                    "Flask backend terminated unexpectedly within 5s with exit code %d.\n%s",
                    retcode,
                    stderr_summary,
                )
                raise RuntimeError(
                    f"Flask backend exited prematurely with returncode {retcode}.\n"
                    f"Error tail:\n{stderr_summary or '(no stderr captured)'}"
                )
            if HealthChecker.is_port_bound(self.host, self.port, timeout=0.1):
                # Backend bound the port early, proceed to full health check
                break
            time.sleep(0.2)

        # Step 6: Wait for HTTP 200 readiness
        logger.info("Subprocess active (pid=%d). Awaiting backend health...", self._process.pid)
        is_ready = self.health_checker.wait_until_ready()
        if not is_ready:
            stderr_summary = "\n".join(list(self._stderr_buffer)[-20:])
            logger.error(
                "Flask backend failed to report healthy within %.1fs.\nRecent stderr:\n%s",
                self.timeout_seconds,
                stderr_summary,
            )
            self.stop()
            return False

        logger.info("Flask backend successfully initialized and verified ready.")
        return True

    def stop(self, timeout_seconds: float = 8.0) -> None:
        """
        Stops the Flask backend process cleanly and idempotently.

        Sends SIGTERM first to allow atexit/signal handlers to release camera
        resources and save pending writes. If the process does not terminate
        within timeout_seconds, escalates to SIGKILL.

        Args:
            timeout_seconds: Maximum seconds to wait after SIGTERM before sending SIGKILL.
        """
        with self._shutdown_lock:
            if self._is_shutdown:
                logger.debug("Process manager stop() called multiple times — ignoring.")
                return

            if self._is_externally_managed:
                logger.info(
                    "Backend was already running prior to GUI launch. Leaving external service intact."
                )
                self._is_shutdown = True
                return

            proc = self._process
            if proc is None:
                self._is_shutdown = True
                return

            pid = proc.pid
            logger.info("Initiating graceful shutdown of Flask backend (pid=%d)...", pid)

            try:
                if proc.poll() is None:
                    # Send SIGTERM for graceful application teardown
                    proc.send_signal(signal.SIGTERM)
                    try:
                        proc.wait(timeout=timeout_seconds)
                        logger.info("Flask backend (pid=%d) terminated cleanly.", pid)
                    except subprocess.TimeoutExpired:
                        logger.warning(
                            "Flask backend (pid=%d) did not terminate within %.1fs. Sending SIGKILL...",
                            pid,
                            timeout_seconds,
                        )
                        proc.kill()
                        proc.wait(timeout=3.0)
                        logger.info("Flask backend (pid=%d) killed forcefully.", pid)
            except OSError as exc:
                logger.error("Error encountered while terminating backend process: %s", exc)
            finally:
                self._stop_reading_event.set()
                self._process = None
                self._is_shutdown = True

    def get_recent_logs(self) -> Tuple[List[str], List[str]]:
        """
        Returns recent lines of stdout and stderr captured from the Flask process.

        Returns:
            Tuple of (stdout_lines, stderr_lines).
        """
        return list(self._stdout_buffer), list(self._stderr_buffer)
