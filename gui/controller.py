"""
gui/controller.py
-----------------
Presentation-neutral controller layer for the native Qt surveillance kiosk.

Directly bridges native Qt widgets to existing backend services without
starting a Flask server:
  - camera_v2 (Picamera2 single owner)
  - nirdet_service (NCNN INT8 person detector daemon)
  - auth (SQLite user and PIN management)

NO second Flask server is started.
NO second Picamera2 camera object is created.
NO NCNN inference runs on the GUI thread (handled by nirdet_service threads).
"""

import logging
import os
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtGui import QImage

import auth
import camera_v2 as camera
import nirdet_service

logger = logging.getLogger("nvsys.gui.controller")


class _PreviewStreamWorker(QThread):
    """
    Background worker thread that fetches preview frames from camera_v2 or
    nirdet_service and emits them as QImage objects to the GUI thread.

    Inference never runs here: nirdet_service handles inference in its own threads.
    This worker only pulls the latest rendered/annotated frame in-memory.
    """

    frame_ready = Signal(QImage)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._running = threading.Event()
        self._mode = "normal"  # "normal" or "ai"
        self._detector: Optional[nirdet_service.NIRPersonDetectorService] = None
        self._fps_delay = 0.05  # ~20 FPS display polling

    def set_detector(self, detector: nirdet_service.NIRPersonDetectorService) -> None:
        """Assigns the shared detector service instance."""
        self._detector = detector

    def set_mode(self, mode: str) -> None:
        """Switches stream source between 'normal' (camera_v2) and 'ai' (nirdet_service)."""
        self._mode = mode
        logger.info("Preview stream worker mode set to: %s", mode)

    def stop(self) -> None:
        """Signals the polling loop to stop and waits for thread termination."""
        self._running.clear()
        self.wait(timeout=2000)

    def run(self) -> None:
        """Polling loop pulling encoded JPEG frames and converting to QImage."""
        self._running.set()
        logger.info("Preview stream worker started.")

        while self._running.is_set():
            t_start = time.monotonic()
            jpeg_bytes: Optional[bytes] = None

            try:
                if self._mode == "ai" and self._detector is not None:
                    jpeg_bytes = self._detector.get_latest_jpeg()
                else:
                    jpeg_bytes = camera.get_frame_jpeg(width=640)
            except Exception as exc:
                logger.error("Error retrieving preview frame: %s", exc)

            if jpeg_bytes:
                img = QImage.fromData(jpeg_bytes, "JPEG")
                if not img.isNull():
                    self.frame_ready.emit(img)

            # Throttle to avoid pegging the CPU
            elapsed = time.monotonic() - t_start
            sleep_time = max(0.01, self._fps_delay - elapsed)
            time.sleep(sleep_time)

        logger.info("Preview stream worker stopped.")


class SurveillanceController(QObject):
    """
    Central controller managing application state, camera lifecycle,
    detector controls, and user authentication for native Qt widgets.
    """

    # Signals for UI synchronization
    frame_received = Signal(QImage)
    recording_ticked = Signal(int)  # elapsed seconds
    recording_state_changed = Signal(bool, str)  # is_recording, message
    auth_changed = Signal(bool, str)  # is_authenticated, username
    status_notified = Signal(str, str)  # level (info/error/warn), message

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.current_user: Optional[str] = None
        self._preview_mode = "normal"  # "normal" or "ai"

        # Initialize SQLite database schema
        auth.init_db()

        # Instantiate shared detector service wrapping camera_v2
        self.detector = nirdet_service.NIRPersonDetectorService(camera)

        # Background preview stream worker
        self._stream_worker = _PreviewStreamWorker()
        self._stream_worker.set_detector(self.detector)
        self._stream_worker.frame_ready.connect(self._on_frame_ready)

        # Timer for recording duration
        self._rec_timer = QTimer(self)
        self._rec_timer.setInterval(1000)
        self._rec_timer.timeout.connect(self._on_rec_tick)
        self._rec_start_time: Optional[float] = None

    def _on_frame_ready(self, img: QImage) -> None:
        """Relays frame from background worker to Qt widgets."""
        self.frame_received.emit(img)

    def _on_rec_tick(self) -> None:
        """Emits elapsed recording duration."""
        if self._rec_start_time is not None:
            elapsed = int(time.monotonic() - self._rec_start_time)
            self.recording_ticked.emit(elapsed)

    # ── Authentication Services ───────────────────────────────────────────────

    def get_operator_list(self) -> List[str]:
        """Returns registered operator usernames."""
        return auth.get_all_usernames()

    def login(self, username: str, pin: str) -> Tuple[bool, str]:
        """Authenticates an operator with their 4-digit PIN."""
        if not auth.is_valid_pin(pin):
            return False, "PIN must be exactly 4 digits."

        user = auth.verify_login(username, pin)
        if user is not None:
            self.current_user = user["username"]
            self.auth_changed.emit(True, self.current_user)
            logger.info("Operator %s logged in.", self.current_user)
            return True, "Login successful."

        return False, "Incorrect Operator ID or PIN."

    def logout(self) -> None:
        """Logs out the active operator and stops any running capture preview."""
        logger.info("Operator %s logging out.", self.current_user or "unknown")
        if self.is_recording():
            self.stop_recording()
        self.stop_preview()
        self.current_user = None
        self.auth_changed.emit(False, "")

    def change_pin(self, old_pin: str, new_pin: str, confirm_pin: str) -> Tuple[bool, str]:
        """Validates and updates the operator PIN."""
        if not self.current_user:
            return False, "No operator currently logged in."

        if new_pin != confirm_pin:
            return False, "New PIN and confirmation do not match."

        if not auth.is_valid_pin(new_pin):
            return False, "New PIN must be exactly 4 digits (0-9)."

        success, msg = auth.change_password(self.current_user, old_pin, new_pin)
        return success, msg

    # ── Preview & Stream Management ───────────────────────────────────────────

    def start_preview(self, mode: str = "normal") -> None:
        """Activates camera capture preview stream."""
        self._preview_mode = mode
        if mode == "ai":
            camera.start_detect_mode()
            self.detector.start()
        else:
            self.detector.stop()
            camera.stop_detect_mode()

        self._stream_worker.set_mode(mode)
        if not self._stream_worker.isRunning():
            self._stream_worker.start()

    def set_preview_mode(self, mode: str) -> None:
        """Toggles between normal preview and AI detection preview on the fly."""
        if mode == self._preview_mode:
            return

        self._preview_mode = mode
        if mode == "ai":
            camera.start_detect_mode()
            self.detector.start()
        else:
            self.detector.stop()
            camera.stop_detect_mode()

        self._stream_worker.set_mode(mode)

    def stop_preview(self) -> None:
        """Stops the preview stream worker and releases AI detection mode."""
        if self._stream_worker.isRunning():
            self._stream_worker.stop()
        self.detector.stop()
        camera.stop_detect_mode()
        camera.stop_preview()

    # ── Media Capture & Storage ───────────────────────────────────────────────

    def capture_image(self) -> Tuple[bool, Optional[str]]:
        """
        Captures a still image from the camera. If AI preview is active,
        saves the current annotated frame. Otherwise invokes camera.capture_image().
        """
        if self._preview_mode == "ai":
            jpeg = self.detector.get_latest_jpeg()
            if jpeg:
                filename = f"image_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S_%f')}.jpg"
                filepath = os.path.join(camera.IMAGE_DIR, filename)
                try:
                    with open(filepath, "wb") as f:
                        f.write(jpeg)
                    logger.info("Saved AI still capture: %s", filename)
                    return True, filename
                except OSError as exc:
                    logger.error("Failed saving AI snapshot: %s", exc)
                    return False, None

        filename = camera.capture_image()
        if filename:
            return True, filename
        return False, None

    def start_recording(self) -> bool:
        """Begins an MP4 video recording session."""
        if camera.is_recording():
            return True

        if self._preview_mode == "ai":
            camera.stop_detect_mode()

        camera.start_recording()
        self._rec_start_time = time.monotonic()
        self._rec_timer.start()
        self.recording_state_changed.emit(True, "Recording started.")
        return True

    def stop_recording(self) -> Tuple[bool, Optional[str]]:
        """Stops active MP4 video recording and finalizes the file."""
        if not camera.is_recording():
            return False, None

        self._rec_timer.stop()
        self._rec_start_time = None
        filename = camera.stop_recording()

        if self._preview_mode == "ai":
            camera.start_detect_mode()

        self.recording_state_changed.emit(False, "Recording stopped.")
        if filename:
            return True, filename
        return False, None

    def is_recording(self) -> bool:
        """Returns True if a recording session is active."""
        return camera.is_recording()

    def list_images(self) -> List[str]:
        """Lists captured still image filenames newest-first."""
        return camera.list_images()

    def list_videos(self) -> List[str]:
        """Lists captured video filenames newest-first."""
        return camera.list_videos()

    def delete_image(self, filename: str) -> bool:
        """Deletes an image file from the storage directory."""
        return camera.delete_image(filename)

    def delete_video(self, filename: str) -> bool:
        """Deletes a video file from the storage directory."""
        return camera.delete_video(filename)

    def get_image_path(self, filename: str) -> str:
        """Returns the absolute file path for a stored image."""
        return os.path.join(camera.IMAGE_DIR, filename)

    def get_video_path(self, filename: str) -> str:
        """Returns the absolute file path for a stored video."""
        return os.path.join(camera.VIDEO_DIR, filename)

    def get_storage_summary(self) -> Dict[str, object]:
        """Retrieves camera health, disk usage, and file counts."""
        return camera.storage_summary()

    def get_detector_status(self) -> Dict[str, object]:
        """Retrieves current NCNN detector telemetry and inference FPS."""
        return self.detector.status()

    # ── Shutdown Cleanup ──────────────────────────────────────────────────────

    def cleanup(self) -> None:
        """Gracefully halts workers, detector threads, and releases camera hardware."""
        logger.info("Executing controller cleanup...")
        if self.is_recording():
            self.stop_recording()
        self.stop_preview()
        logger.info("Controller cleanup complete.")
