"""
gui/native_window.py
--------------------
Main native Qt kiosk application window orchestrating all screens and views.

Features:
  - Zero Flask server required
  - Zero browser/WebKit/WebEngine memory overhead
  - Direct frame streaming to QPixmap via controller signals
  - Smooth QStackedWidget navigation between all 8 application views
  - True borderless fullscreen kiosk presentation
  - Clean shutdown handling
"""

import logging
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QContextMenuEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QStackedWidget

from gui.controller import SurveillanceController
from gui.widgets import (
    CaptureImageWidget,
    CaptureVideoWidget,
    ChangePinWidget,
    DashboardWidget,
    GalleryWidget,
    LoginWidget,
    ManualWidget,
    SettingsWidget,
    TACTICAL_STYLE,
)

logger = logging.getLogger("nvsys.gui.native_window")


class NativeKioskWindow(QMainWindow):
    """
    Top-level kiosk window managing the native Qt navigation stack.
    """

    def __init__(
        self,
        controller: Optional[SurveillanceController] = None,
        fullscreen: bool = True,
    ) -> None:
        super().__init__()
        self.controller = controller or SurveillanceController(self)
        self.fullscreen = fullscreen

        self.setWindowTitle("Night Vision Surveillance System — Tactical Console")
        self.setStyleSheet(TACTICAL_STYLE)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)

        # Create Navigation Stack
        self.stack = QStackedWidget(self)
        self.setCentralWidget(self.stack)

        # Initialize Views
        self.view_login = LoginWidget(self.controller)
        self.view_manual = ManualWidget()
        self.view_dashboard = DashboardWidget(self.controller)
        self.view_capture_img = CaptureImageWidget(self.controller)
        self.view_capture_vid = CaptureVideoWidget(self.controller)
        self.view_gallery_img = GalleryWidget(self.controller, media_type="images")
        self.view_gallery_vid = GalleryWidget(self.controller, media_type="videos")
        self.view_settings = SettingsWidget(self.controller)
        self.view_pin = ChangePinWidget(self.controller)

        # Register to Stack
        self.stack.addWidget(self.view_login)         # Index 0
        self.stack.addWidget(self.view_manual)        # Index 1
        self.stack.addWidget(self.view_dashboard)     # Index 2
        self.stack.addWidget(self.view_capture_img)   # Index 3
        self.stack.addWidget(self.view_capture_vid)   # Index 4
        self.stack.addWidget(self.view_gallery_img)   # Index 5
        self.stack.addWidget(self.view_gallery_vid)   # Index 6
        self.stack.addWidget(self.view_settings)      # Index 7
        self.stack.addWidget(self.view_pin)           # Index 8

        # Wire Navigation Flow
        self.view_login.authenticated.connect(self._goto_manual)
        self.view_manual.proceed.connect(self._goto_dashboard)

        self.view_dashboard.navigate.connect(self._on_dashboard_navigate)
        self.view_dashboard.logout.connect(self._goto_login)

        self.view_capture_img.back_to_menu.connect(self._goto_dashboard)
        self.view_capture_vid.back_to_menu.connect(self._goto_dashboard)
        self.view_gallery_img.back_to_menu.connect(self._goto_dashboard)
        self.view_gallery_vid.back_to_menu.connect(self._goto_dashboard)
        self.view_settings.back_to_menu.connect(self._goto_dashboard)
        self.view_pin.back_to_menu.connect(self._goto_dashboard)

        # Apply Fullscreen / Kiosk Geometry
        if self.fullscreen:
            self.setWindowFlags(
                Qt.WindowType.Window
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.CustomizeWindowHint
            )
            self.showFullScreen()
        else:
            self.resize(800, 480)
            self.show()

        # Keyboard hotkey for maintenance (Ctrl+Q exits)
        self.quit_shortcut = QShortcut(QKeySequence("Ctrl+Q"), self)
        self.quit_shortcut.activated.connect(self.close)

        # Initial view is Login
        self.stack.setCurrentWidget(self.view_login)
        logger.info("Native kiosk window initialized.")

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Suppresses all desktop context menus on touch holding."""
        event.accept()

    def _goto_login(self) -> None:
        """Transitions to login screen."""
        self.controller.logout()
        self.stack.setCurrentWidget(self.view_login)

    def _goto_manual(self) -> None:
        """Transitions to operator briefing."""
        self.stack.setCurrentWidget(self.view_manual)

    def _goto_dashboard(self) -> None:
        """Transitions to main dashboard menu."""
        self.view_dashboard.refresh()
        self.stack.setCurrentWidget(self.view_dashboard)

    def _on_dashboard_navigate(self, target: str) -> None:
        """Routes dashboard tile selections to the appropriate screen."""
        logger.info("Navigating to view: %s", target)
        if target == "capture_image":
            self.stack.setCurrentWidget(self.view_capture_img)
            self.view_capture_img.activate()
        elif target == "capture_video":
            self.stack.setCurrentWidget(self.view_capture_vid)
            self.view_capture_vid.activate()
        elif target == "gallery_images":
            self.stack.setCurrentWidget(self.view_gallery_img)
            self.view_gallery_img.activate()
        elif target == "gallery_videos":
            self.stack.setCurrentWidget(self.view_gallery_vid)
            self.view_gallery_vid.activate()
        elif target == "settings":
            self.stack.setCurrentWidget(self.view_settings)
            self.view_settings.activate()
        elif target == "change_pin":
            self.stack.setCurrentWidget(self.view_pin)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Releases camera and stops background workers on close."""
        logger.info("Native kiosk window closing. Cleaning up backend...")
        try:
            self.view_capture_img.deactivate()
            self.view_capture_vid.deactivate()
            self.controller.cleanup()
        except Exception as exc:
            logger.error("Error during native window close cleanup: %s", exc)
        event.accept()
