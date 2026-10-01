"""
gui/window.py
-------------
Fullscreen kiosk application window embedding the Flask web interface.

TOOLKIT SELECTION:
  Option A (Active / Default): PyQt6 + QWebEngineView
    - Install: sudo apt install python3-pyqt6.qtwebengine
      OR pip install PyQt6 PyQt6-WebEngine
  Option B (Drop-in Alternative): PySide6 + QWebEngineView
    - To switch, change the import block from `PyQt6` to `PySide6`. The API
      surface for QMainWindow, QWebEngineView, and Qt attributes is identical.
  Option C (Drop-in Alternative): GTK4 + WebKitGTK
    - Uses system packages `python3-gi`, `gir1.2-webkit-6.0`. See gui/README.md
      for the standalone GTK4 implementation snippet.

RESPONSIBILITIES:
  - Embeds the web interface via a dedicated WebEngine view
  - Runs in strict fullscreen mode on the Raspberry Pi display (no title bar, no borders)
  - Disables all browser chrome (no address bar, no tabs, no back/forward buttons)
  - Suppresses desktop context menus on long-press or right-click
  - Forwards native touchscreen events seamlessly
  - Renders a styled, readable error screen if the backend fails to load, avoiding blank screens
  - Emits clean shutdown notifications when the kiosk window is requested to close
"""

import logging
from typing import Callable, Optional

logger = logging.getLogger("nvsys.gui.window")

# =============================================================================
# Option A: PyQt6 Imports (Default)
# =============================================================================
try:
    from PyQt6.QtCore import QUrl, Qt, pyqtSignal
    from PyQt6.QtGui import QCloseEvent, QContextMenuEvent, QKeySequence, QShortcut
    from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
    QT_TOOLKIT = "PyQt6"
except ImportError:
    try:
        # Fallback to Option B: PySide6 if PyQt6 is absent
        from PySide6.QtCore import QUrl, Qt, Signal as pyqtSignal  # type: ignore
        from PySide6.QtGui import QCloseEvent, QContextMenuEvent, QKeySequence, QShortcut  # type: ignore
        from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings  # type: ignore
        from PySide6.QtWebEngineWidgets import QWebEngineView  # type: ignore
        from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget  # type: ignore
        QT_TOOLKIT = "PySide6"
    except ImportError as exc:
        raise ImportError(
            "Neither PyQt6 nor PySide6 with QtWebEngine is installed.\n"
            "On Raspberry Pi OS Bookworm, install via:\n"
            "  sudo apt install -y python3-pyqt6.qtwebengine\n"
            "Or via pip:\n"
            "  pip install -r requirements_gui.txt"
        ) from exc


class KioskWebView(QWebEngineView):
    """
    Custom WebEngineView tailored for kiosk operation.

    Suppresses context menus, handles touch event attributes, and renders
    tactical error pages on network disconnects.
    """

    def __init__(self, initial_url: str, parent: Optional[QWidget] = None) -> None:
        """
        Initializes the kiosk web view.

        Args:
            initial_url: The URL to load upon creation (e.g. http://127.0.0.1:5000/login).
            parent: Optional parent QWidget.
        """
        super().__init__(parent)
        self.initial_url: str = initial_url
        self._is_showing_error: bool = False

        # Configure Touch & Kiosk settings
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)

        # Configure WebEngine settings
        settings = self.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )

        # Hook page loading status
        self.loadFinished.connect(self._on_load_finished)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """
        Suppresses right-click and touch-and-hold context menus entirely.

        Args:
            event: The context menu event to discard.
        """
        # Discard the event so no context menu is presented to the operator
        event.accept()

    def _on_load_finished(self, success: bool) -> None:
        """
        Handles completion of page navigation.

        If navigation failed (e.g. backend unreachable or crashed), displays
        an informative tactical recovery page rather than leaving a blank screen.

        Args:
            success: True if the web page loaded successfully, False otherwise.
        """
        if success:
            self._is_showing_error = False
            logger.debug("Page loaded successfully: %s", self.url().toString())
            return

        # Do not loop if error page itself triggered the signal
        if self._is_showing_error:
            return

        self._is_showing_error = True
        logger.error("WebEngine failed to load URL: %s. Rendering error screen.", self.initial_url)
        self._render_error_page()

    def _render_error_page(self) -> None:
        """Renders an inline tactical dark-themed error screen."""
        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="UTF-8">
          <style>
            body {{
              background-color: #060A07;
              color: #00FF41;
              font-family: 'Share Tech Mono', monospace, monospace;
              display: flex;
              flex-direction: column;
              align-items: center;
              justify-content: center;
              height: 100vh;
              margin: 0;
              user-select: none;
            }}
            .card {{
              border: 1px solid #1E3024;
              background: #0F1A12;
              padding: 32px;
              border-radius: 8px;
              text-align: center;
              max-width: 500px;
              box-shadow: 0 0 20px rgba(0, 255, 65, 0.15);
            }}
            h1 {{
              margin-top: 0;
              font-size: 20px;
              letter-spacing: 2px;
              color: #FFB300;
            }}
            p {{
              color: #C8FFDA;
              font-size: 14px;
              line-height: 1.6;
            }}
            .btn {{
              margin-top: 24px;
              background: #007A1E;
              color: #FFFFFF;
              border: 1px solid #00FF41;
              padding: 12px 24px;
              font-size: 14px;
              font-weight: bold;
              border-radius: 4px;
              cursor: pointer;
              letter-spacing: 1px;
            }}
            .btn:active {{
              background: #00FF41;
              color: #060A07;
            }}
          </style>
        </head>
        <body>
          <div class="card">
            <h1>// BACKEND UNAVAILABLE</h1>
            <p>
              The kiosk shell was unable to connect to the surveillance backend at
              <code>{self.initial_url}</code>.
            </p>
            <p>
              Please verify that the local Flask service is running and retry connection.
            </p>
            <button class="btn" onclick="window.location.href='{self.initial_url}'">
              RETRY CONNECTION
            </button>
          </div>
        </body>
        </html>
        """
        self.setHtml(error_html, QUrl("about:blank"))


class KioskMainWindow(QMainWindow):
    """
    Fullscreen top-level application window for the Raspberry Pi kiosk.

    Eliminates all window frames, borders, and browser navigation widgets.
    """

    window_closed = pyqtSignal()

    def __init__(
        self,
        target_url: str = "http://127.0.0.1:5000/login",
        fullscreen: bool = True,
        on_close_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        """
        Constructs the kiosk main window.

        Args:
            target_url: Full URL to load upon launch.
            fullscreen: Whether to present in borderless fullscreen mode.
            on_close_callback: Optional function invoked when window closes.
        """
        super().__init__()
        self.target_url: str = target_url
        self.on_close_callback: Optional[Callable[[], None]] = on_close_callback

        self.setWindowTitle("Night Vision Surveillance Terminal")

        # Create web view
        self.webview = KioskWebView(initial_url=self.target_url, parent=self)

        # Set central widget
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.webview)
        self.setCentralWidget(container)

        # Apply Kiosk Flags
        if fullscreen:
            # Frameless window hint + true fullscreen
            self.setWindowFlags(
                Qt.WindowType.Window
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.CustomizeWindowHint
            )
            self.showFullScreen()
        else:
            self.resize(800, 480)
            self.show()

        # Keyboard shortcuts for development/maintenance (Ctrl+Q to exit)
        self.quit_shortcut = QShortcut(QKeySequence("Ctrl+Q"), self)
        self.quit_shortcut.activated.connect(self.close)

        # Begin loading the target URL
        logger.info("Kiosk window initialized (%s). Loading %s", QT_TOOLKIT, self.target_url)
        self.webview.load(QUrl(self.target_url))

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Intercepts window close events to trigger launcher shutdown.

        Args:
            event: Window close event.
        """
        logger.info("Kiosk main window received close event.")
        self.window_closed.emit()
        if self.on_close_callback is not None:
            try:
                self.on_close_callback()
            except Exception as exc:
                logger.error("Error executing window close callback: %s", exc)
        event.accept()
