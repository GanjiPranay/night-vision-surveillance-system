"""
gui/launcher.py
---------------
Main entry point for the Night Vision Surveillance System Kiosk GUI Shell.

Orchestrates the startup sequence:
  1. Spawns/verifies the local Flask backend subprocess on 127.0.0.1.
  2. Waits for health check readiness confirmation.
  3. Initializes the fullscreen Qt application window.
  4. Coordinates clean and idempotent shutdown upon window close or SIGINT/SIGTERM.

USAGE:
  python -m gui.launcher
  OR
  python gui/launcher.py [--no-fullscreen] [--timeout 30] [--port 5000]
"""

import argparse
import atexit
import logging
import signal
import sys
import threading
from typing import Optional

from gui.process_manager import FlaskProcessManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("nvsys.gui.launcher")


class KioskLauncher:
    """
    Coordinates process lifecycle, backend health verification, and GUI execution.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5000,
        timeout_seconds: float = 30.0,
        fullscreen: bool = True,
    ) -> None:
        """
        Initializes the kiosk launcher.

        Args:
            host: IP address on which the backend listens (strictly 127.0.0.1).
            port: Port on which the backend listens (default 5000).
            timeout_seconds: Max seconds to wait for backend readiness.
            fullscreen: Whether the GUI window should open in fullscreen mode.
        """
        self.host: str = host
        self.port: int = port
        self.timeout_seconds: float = timeout_seconds
        self.fullscreen: bool = fullscreen

        self.process_manager = FlaskProcessManager(
            host=self.host,
            port=self.port,
            timeout_seconds=self.timeout_seconds,
        )

        self._shutdown_lock: threading.Lock = threading.Lock()
        self._is_shutdown: bool = False
        self._qt_app: Optional[object] = None
        self._main_window: Optional[object] = None

    def shutdown(self) -> None:
        """
        Idempotent shutdown handler.

        Stops the Flask backend subprocess gracefully (SIGTERM -> SIGKILL),
        allowing the backend's camera and detector cleanup routines to run.
        """
        with self._shutdown_lock:
            if self._is_shutdown:
                return
            self._is_shutdown = True

            logger.info("Initiating kiosk shutdown sequence...")

            # Stop the backend subprocess cleanly
            try:
                self.process_manager.stop(timeout_seconds=8.0)
            except Exception as exc:
                logger.error("Error during backend process termination: %s", exc)

            # Close Qt window if still running
            if self._main_window is not None:
                try:
                    self._main_window.close()
                except Exception as exc:
                    logger.debug("Error closing Qt window during shutdown: %s", exc)
                self._main_window = None

            if self._qt_app is not None:
                try:
                    self._qt_app.quit()
                except Exception as exc:
                    logger.debug("Error quitting Qt app during shutdown: %s", exc)

            logger.info("Shutdown sequence completed.")

    def run(self) -> int:
        """
        Executes the main application lifecycle.

        Returns:
            Process exit status code (0 for clean exit, non-zero for errors).
        """
        logger.info("==================================================")
        logger.info(" NIGHT VISION SURVEILLANCE SYSTEM — KIOSK SHELL   ")
        logger.info("==================================================")

        # Register signal handlers for clean terminal termination
        def _sig_handler(signum, frame):  # noqa: ANN001
            logger.info("Received termination signal (%d). Shutting down...", signum)
            self.shutdown()
            sys.exit(0)

        try:
            signal.signal(signal.SIGINT, _sig_handler)
            signal.signal(signal.SIGTERM, _sig_handler)
        except (ValueError, OSError) as exc:
            logger.debug("Signal handler registration skipped: %s", exc)

        # Register atexit safety net
        atexit.register(self.shutdown)

        # Step 1: Start the backend server
        logger.info("Step 1/3: Starting / verifying Flask backend on %s:%d...", self.host, self.port)
        try:
            started_ok = self.process_manager.start()
            if not started_ok:
                logger.critical(
                    "Backend failed health check verification within %.1fs. Aborting.",
                    self.timeout_seconds,
                )
                self.shutdown()
                return 1
        except Exception as exc:
            logger.critical("Fatal error encountered while starting backend: %s", exc)
            self.shutdown()
            return 1

        # Step 2: Initialize GUI Toolkit
        logger.info("Step 2/3: Initializing GUI window toolkit...")
        try:
            from PyQt6.QtWidgets import QApplication
            from gui.window import KioskMainWindow
        except ImportError as exc:
            logger.critical(
                "GUI dependency missing. Please install PyQt6 and QtWebEngine:\n"
                "  sudo apt install -y python3-pyqt6.qtwebengine\n"
                "Error details: %s",
                exc,
            )
            self.shutdown()
            return 1

        # Step 3: Run Qt Event Loop
        logger.info("Step 3/3: Opening kiosk window (fullscreen=%s)...", self.fullscreen)
        target_url = f"http://{self.host}:{self.port}/login"

        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        self._qt_app = app

        # Construct and display the main window
        self._main_window = KioskMainWindow(
            target_url=target_url,
            fullscreen=self.fullscreen,
            on_close_callback=self.shutdown,
        )

        exit_code = app.exec()
        logger.info("GUI event loop finished with exit code %d.", exit_code)
        self.shutdown()
        return exit_code


def main() -> None:
    """Parses command-line arguments and runs the kiosk launcher."""
    parser = argparse.ArgumentParser(
        description="Night Vision Surveillance System — Touchscreen Kiosk Launcher"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Backend host address (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Backend port number (default: 5000)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Backend health readiness timeout in seconds (default: 30.0)",
    )
    parser.add_argument(
        "--no-fullscreen",
        action="store_true",
        help="Run in standard windowed mode (800x480) instead of fullscreen",
    )

    args = parser.parse_args()

    launcher = KioskLauncher(
        host=args.host,
        port=args.port,
        timeout_seconds=args.timeout,
        fullscreen=not args.no_fullscreen,
    )

    sys.exit(launcher.run())


if __name__ == "__main__":
    main()
