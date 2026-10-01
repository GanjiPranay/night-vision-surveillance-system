"""
gui/native_launcher.py
----------------------
Launcher entry point for the Phase 2 Native PySide6/Qt Kiosk.

Runs the complete kiosk GUI directly in-process with the backend services:
  - ZERO Flask server overhead
  - ZERO Chromium/WebEngine processes
  - Native touch responsiveness
  - Direct QImage frame streaming

USAGE:
  python -m gui.native_launcher
  OR
  python gui/native_launcher.py [--no-fullscreen]
"""

import argparse
import atexit
import logging
import signal
import sys

from PySide6.QtWidgets import QApplication

from gui.controller import SurveillanceController
from gui.native_window import NativeKioskWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("nvsys.gui.native_launcher")


def main() -> None:
    """Entry point for the Phase 2 native Qt kiosk."""
    parser = argparse.ArgumentParser(
        description="Night Vision Surveillance System — Phase 2 Native Qt Kiosk"
    )
    parser.add_argument(
        "--no-fullscreen",
        action="store_true",
        help="Run in windowed mode (800x480) instead of fullscreen",
    )
    args = parser.parse_args()

    logger.info("==================================================")
    logger.info(" NV-SYS PHASE 2 NATIVE QT KIOSK TERMINAL           ")
    logger.info("==================================================")

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    controller = SurveillanceController()

    window = NativeKioskWindow(
        controller=controller,
        fullscreen=not args.no_fullscreen,
    )

    def _sig_handler(signum, frame):  # noqa: ANN001
        logger.info("Termination signal (%d) received. Shutting down...", signum)
        controller.cleanup()
        window.close()
        app.quit()
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)
    except (ValueError, OSError) as exc:
        logger.debug("Signal handler registration skipped: %s", exc)

    atexit.register(controller.cleanup)

    exit_code = app.exec()
    logger.info("Native kiosk event loop finished with code %d.", exit_code)
    controller.cleanup()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
