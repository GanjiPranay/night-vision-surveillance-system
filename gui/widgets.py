"""
gui/widgets.py
--------------
Native PySide6/Qt widgets for the Night Vision Surveillance System kiosk.

Implements all primary kiosk screens with a tactical dark military theme
designed for 800x480 touchscreen usability:
  - LoginWidget
  - ManualWidget
  - DashboardWidget
  - CaptureImageWidget
  - CaptureVideoWidget
  - GalleryWidget
  - SettingsWidget
  - ChangePinWidget
"""

import os
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gui.controller import SurveillanceController

TACTICAL_STYLE = """
QWidget {
    background-color: #060A07;
    color: #C8FFDA;
    font-family: 'Share Tech Mono', 'Rajdhani', monospace;
    font-size: 14px;
}

QFrame.card {
    background-color: #0F1A12;
    border: 1px solid #1E3024;
    border-radius: 6px;
}

QPushButton {
    background-color: #007A1E;
    color: #FFFFFF;
    border: 1px solid #00FF41;
    border-radius: 4px;
    padding: 12px 20px;
    font-weight: bold;
    font-size: 14px;
    letter-spacing: 1px;
}

QPushButton:pressed {
    background-color: #00FF41;
    color: #060A07;
}

QPushButton.btn-ghost {
    background-color: transparent;
    border: 1px solid #1E3024;
    color: #00FF41;
}

QPushButton.btn-ghost:pressed {
    background-color: rgba(0, 255, 65, 0.15);
}

QPushButton.btn-danger {
    background-color: #C42B20;
    border: 1px solid #FF3B30;
    color: #FFFFFF;
}

QPushButton.btn-danger:pressed {
    background-color: #FF3B30;
    color: #000000;
}

QLineEdit, QComboBox {
    background-color: #0C1410;
    border: 1px solid #1E3024;
    border-radius: 4px;
    padding: 10px;
    color: #00FF41;
    font-size: 16px;
}

QLineEdit:focus, QComboBox:focus {
    border: 1px solid #00FF41;
}

QLabel.title {
    color: #00FF41;
    font-size: 20px;
    font-weight: bold;
    letter-spacing: 2px;
}

QLabel.badge {
    background-color: rgba(0, 255, 65, 0.1);
    color: #00FF41;
    border: 1px solid #00FF41;
    padding: 4px 8px;
    border-radius: 3px;
    font-size: 12px;
}

QLabel.error-banner {
    background-color: rgba(255, 59, 48, 0.15);
    color: #FF3B30;
    border: 1px solid #FF3B30;
    padding: 10px;
    border-radius: 4px;
}
"""


class TopBar(QWidget):
    """Reusable header displaying view title, active operator, and back button."""

    back_clicked = Signal()

    def __init__(self, title: str, operator: str = "", show_back: bool = True, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        if show_back:
            self.btn_back = QPushButton("← BACK")
            self.btn_back.setProperty("class", "btn-ghost")
            self.btn_back.clicked.connect(self.back_clicked.emit)
            layout.addWidget(self.btn_back)

        self.lbl_title = QLabel(f"// {title.upper()}")
        self.lbl_title.setProperty("class", "title")
        layout.addWidget(self.lbl_title)

        layout.addStretch()

        self.lbl_op = QLabel(f"OP: {operator}" if operator else "")
        self.lbl_op.setProperty("class", "badge")
        layout.addWidget(self.lbl_op)


# 1. Login Screen
class LoginWidget(QWidget):
    authenticated = Signal()

    def __init__(self, controller: SurveillanceController, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.controller = controller

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setProperty("class", "card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(30, 30, 30, 30)
        card_layout.setSpacing(16)
        card.setFixedWidth(400)

        title = QLabel("NIGHT VISION SURVEILLANCE")
        title.setProperty("class", "title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("Operator Authentication Required")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #88BBA0; font-size: 12px;")

        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)

        self.error_label = QLabel()
        self.error_label.setProperty("class", "error-banner")
        self.error_label.setVisible(False)
        card_layout.addWidget(self.error_label)

        card_layout.addWidget(QLabel("Operator ID:"))
        self.combo_user = QComboBox()
        self.combo_user.addItems(self.controller.get_operator_list())
        card_layout.addWidget(self.combo_user)

        card_layout.addWidget(QLabel("4-Digit Access PIN:"))
        self.edit_pin = QLineEdit()
        self.edit_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_pin.setMaxLength(4)
        self.edit_pin.setPlaceholderText("••••")
        card_layout.addWidget(self.edit_pin)

        keypad_grid = QGridLayout()
        keypad_grid.setSpacing(6)
        buttons = [
            ("1", 0, 0), ("2", 0, 1), ("3", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("7", 2, 0), ("8", 2, 1), ("9", 2, 2),
            ("CLR", 3, 0), ("0", 3, 1), ("DEL", 3, 2),
        ]
        for text, r, c in buttons:
            btn = QPushButton(text)
            btn.setProperty("class", "btn-ghost")
            btn.setFixedHeight(44)
            btn.clicked.connect(lambda _, t=text: self._on_keypad(t))
            keypad_grid.addWidget(btn, r, c)
        card_layout.addLayout(keypad_grid)

        self.btn_auth = QPushButton("AUTHENTICATE")
        self.btn_auth.clicked.connect(self._do_login)
        card_layout.addWidget(self.btn_auth)

        layout.addWidget(card)

    def _on_keypad(self, key: str) -> None:
        curr = self.edit_pin.text()
        if key == "CLR":
            self.edit_pin.clear()
        elif key == "DEL":
            self.edit_pin.setText(curr[:-1])
        elif len(curr) < 4:
            self.edit_pin.setText(curr + key)

    def _do_login(self) -> None:
        user = self.combo_user.currentText()
        pin = self.edit_pin.text()
        ok, msg = self.controller.login(user, pin)
        if ok:
            self.error_label.setVisible(False)
            self.edit_pin.clear()
            self.authenticated.emit()
        else:
            self.error_label.setText(msg)
            self.error_label.setVisible(True)
            self.edit_pin.clear()


# 2. Operator Briefing Screen
class ManualWidget(QWidget):
    proceed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)

        card = QFrame()
        card.setProperty("class", "card")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(30, 24, 30, 24)
        c_layout.setSpacing(14)

        title = QLabel("// OPERATOR BRIEFING //")
        title.setProperty("class", "title")
        c_layout.addWidget(title)

        steps = [
            "01  Capture Image — Point NoIR camera; tap Capture Image to save timestamped JPEG.",
            "02  Record Video — Tap Start Recording to capture MP4 footage. Tap Stop when finished.",
            "03  View Media — Review saved recordings and snapshots in local galleries.",
            "04  Change PIN — Keep access secure by updating your personal PIN periodically.",
            "05  Settings — Review hardware camera status and local SD card storage gauges.",
        ]
        for s in steps:
            lbl = QLabel(s)
            lbl.setStyleSheet("color: #C8FFDA; font-size: 13px; line-height: 1.5;")
            c_layout.addWidget(lbl)

        warn = QLabel("WARNING: Do not power off while recording is active.")
        warn.setStyleSheet("color: #FFB300; font-weight: bold; margin-top: 10px;")
        c_layout.addWidget(warn)

        btn_ack = QPushButton("ACKNOWLEDGED — PROCEED TO MENU")
        btn_ack.clicked.connect(self.proceed.emit)
        c_layout.addWidget(btn_ack)

        layout.addWidget(card)


# 3. Main Dashboard Menu
class DashboardWidget(QWidget):
    navigate = Signal(str)
    logout = Signal()

    def __init__(self, controller: SurveillanceController, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.controller = controller

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 16, 20, 20)

        header = QHBoxLayout()
        self.lbl_header = QLabel("NV-SYS // MAIN MENU")
        self.lbl_header.setProperty("class", "title")
        header.addWidget(self.lbl_header)
        header.addStretch()

        self.lbl_operator = QLabel("OPERATOR: J1")
        self.lbl_operator.setProperty("class", "badge")
        header.addWidget(self.lbl_operator)

        btn_logout = QPushButton("LOGOUT")
        btn_logout.setProperty("class", "btn-ghost")
        btn_logout.clicked.connect(self.logout.emit)
        header.addWidget(btn_logout)
        self.layout.addLayout(header)

        grid = QGridLayout()
        grid.setSpacing(16)

        tiles = [
            ("A", "Capture Image", "capture_image", 0, 0),
            ("B", "Record Video", "capture_video", 0, 1),
            ("C", "View Images", "gallery_images", 0, 2),
            ("D", "View Videos", "gallery_videos", 1, 0),
            ("E", "Change PIN", "change_pin", 1, 1),
            ("F", "Settings", "settings", 1, 2),
        ]
        for key, label, dest, r, c in tiles:
            tile_btn = QPushButton(f"[{key}]  {label}")
            tile_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            tile_btn.setMinimumHeight(110)
            tile_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0F1A12;
                    border: 2px solid #1E3024;
                    color: #00FF41;
                    font-size: 16px;
                    text-align: left;
                    padding-left: 20px;
                }
                QPushButton:pressed {
                    background-color: #007A1E;
                    color: #FFFFFF;
                }
            """)
            tile_btn.clicked.connect(lambda _, d=dest: self.navigate.emit(d))
            grid.addWidget(tile_btn, r, c)

        self.layout.addLayout(grid)

    def refresh(self) -> None:
        user = self.controller.current_user or "GUEST"
        self.lbl_operator.setText(f"OPERATOR: {user}")


# 4. Image Capture View
class CaptureImageWidget(QWidget):
    back_to_menu = Signal()

    def __init__(self, controller: SurveillanceController, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)

        self.topbar = TopBar("Capture Image", show_back=True)
        self.topbar.back_clicked.connect(self._on_back)
        self.layout.addWidget(self.topbar)

        content = QHBoxLayout()

        self.viewfinder = QLabel()
        self.viewfinder.setFixedSize(512, 360)
        self.viewfinder.setStyleSheet("background-color: #000000; border: 1px solid #1E3024;")
        self.viewfinder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(self.viewfinder)

        controls = QVBoxLayout()
        controls.setSpacing(14)

        controls.addWidget(QLabel("Preview Mode:"))
        mode_box = QHBoxLayout()
        self.btn_normal = QPushButton("NORMAL")
        self.btn_normal.clicked.connect(lambda: self._set_mode("normal"))
        self.btn_ai = QPushButton("AI NIRDET")
        self.btn_ai.clicked.connect(lambda: self._set_mode("ai"))
        mode_box.addWidget(self.btn_normal)
        mode_box.addWidget(self.btn_ai)
        controls.addLayout(mode_box)

        self.lbl_status = QLabel("Ready for acquisition.")
        controls.addWidget(self.lbl_status)

        self.btn_capture = QPushButton("CAPTURE IMAGE")
        self.btn_capture.setFixedHeight(54)
        self.btn_capture.clicked.connect(self._do_capture)
        controls.addWidget(self.btn_capture)

        controls.addStretch()

        self.btn_quit = QPushButton("QUIT FEED")
        self.btn_quit.setProperty("class", "btn-ghost")
        self.btn_quit.clicked.connect(self._on_back)
        controls.addWidget(self.btn_quit)

        content.addLayout(controls)
        self.layout.addLayout(content)

    def activate(self) -> None:
        self.topbar.lbl_op.setText(f"OP: {self.controller.current_user or ''}")
        self.controller.frame_received.connect(self._update_frame)
        self.controller.start_preview(mode="normal")
        self._set_mode("normal")

    def deactivate(self) -> None:
        try:
            self.controller.frame_received.disconnect(self._update_frame)
        except (RuntimeError, TypeError):
            pass
        self.controller.stop_preview()

    def _set_mode(self, mode: str) -> None:
        self.controller.set_preview_mode(mode)
        if mode == "normal":
            self.btn_normal.setStyleSheet("background-color: #007A1E; color: white;")
            self.btn_ai.setStyleSheet("background-color: #152019; color: #88BBA0;")
        else:
            self.btn_normal.setStyleSheet("background-color: #152019; color: #88BBA0;")
            self.btn_ai.setStyleSheet("background-color: #007A1E; color: white;")

    def _update_frame(self, img: QImage) -> None:
        pixmap = QPixmap.fromImage(img).scaled(
            self.viewfinder.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self.viewfinder.setPixmap(pixmap)

    def _do_capture(self) -> None:
        self.btn_capture.setEnabled(False)
        self.btn_capture.setText("ACQUIRING…")
        ok, filename = self.controller.capture_image()
        if ok and filename:
            self.lbl_status.setText(f"SAVED: {filename}")
        else:
            self.lbl_status.setText("Capture failed.")
        self.btn_capture.setText("CAPTURE IMAGE")
        self.btn_capture.setEnabled(True)

    def _on_back(self) -> None:
        self.deactivate()
        self.back_to_menu.emit()


# 5. Video Capture View
class CaptureVideoWidget(QWidget):
    back_to_menu = Signal()

    def __init__(self, controller: SurveillanceController, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)

        self.topbar = TopBar("Record Video", show_back=True)
        self.topbar.back_clicked.connect(self._on_back)
        self.layout.addWidget(self.topbar)

        content = QHBoxLayout()

        self.viewfinder = QLabel()
        self.viewfinder.setFixedSize(512, 360)
        self.viewfinder.setStyleSheet("background-color: #000000; border: 1px solid #1E3024;")
        self.viewfinder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(self.viewfinder)

        controls = QVBoxLayout()
        controls.setSpacing(14)

        controls.addWidget(QLabel("Preview Mode:"))
        mode_box = QHBoxLayout()
        self.btn_normal = QPushButton("NORMAL")
        self.btn_normal.clicked.connect(lambda: self._set_mode("normal"))
        self.btn_ai = QPushButton("AI NIRDET")
        self.btn_ai.clicked.connect(lambda: self._set_mode("ai"))
        mode_box.addWidget(self.btn_normal)
        mode_box.addWidget(self.btn_ai)
        controls.addLayout(mode_box)

        self.lbl_rec_badge = QLabel("REC  00:00")
        self.lbl_rec_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_rec_badge.setStyleSheet("""
            background-color: #FF3B30; color: #FFFFFF; font-weight: bold;
            font-size: 16px; border-radius: 4px; padding: 6px;
        """)
        self.lbl_rec_badge.setVisible(False)
        controls.addWidget(self.lbl_rec_badge)

        self.btn_toggle_rec = QPushButton("START RECORDING")
        self.btn_toggle_rec.setFixedHeight(54)
        self.btn_toggle_rec.clicked.connect(self._toggle_recording)
        controls.addWidget(self.btn_toggle_rec)

        self.lbl_status = QLabel("Standby.")
        controls.addWidget(self.lbl_status)

        controls.addStretch()

        self.btn_quit = QPushButton("QUIT FEED")
        self.btn_quit.setProperty("class", "btn-ghost")
        self.btn_quit.clicked.connect(self._on_back)
        controls.addWidget(self.btn_quit)

        content.addLayout(controls)
        self.layout.addLayout(content)

    def activate(self) -> None:
        self.topbar.lbl_op.setText(f"OP: {self.controller.current_user or ''}")
        self.controller.frame_received.connect(self._update_frame)
        self.controller.recording_ticked.connect(self._update_timer)
        self.controller.start_preview(mode="normal")
        self._set_mode("normal")
        self.lbl_rec_badge.setVisible(False)
        self.btn_toggle_rec.setText("START RECORDING")

    def deactivate(self) -> None:
        if self.controller.is_recording():
            self.controller.stop_recording()
        try:
            self.controller.frame_received.disconnect(self._update_frame)
            self.controller.recording_ticked.disconnect(self._update_timer)
        except (RuntimeError, TypeError):
            pass
        self.controller.stop_preview()

    def _set_mode(self, mode: str) -> None:
        self.controller.set_preview_mode(mode)
        if mode == "normal":
            self.btn_normal.setStyleSheet("background-color: #007A1E; color: white;")
            self.btn_ai.setStyleSheet("background-color: #152019; color: #88BBA0;")
        else:
            self.btn_normal.setStyleSheet("background-color: #152019; color: #88BBA0;")
            self.btn_ai.setStyleSheet("background-color: #007A1E; color: white;")

    def _update_frame(self, img: QImage) -> None:
        pixmap = QPixmap.fromImage(img).scaled(
            self.viewfinder.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self.viewfinder.setPixmap(pixmap)

    def _update_timer(self, elapsed_seconds: int) -> None:
        mins = elapsed_seconds // 60
        secs = elapsed_seconds % 60
        self.lbl_rec_badge.setText(f"REC  {mins:02d}:{secs:02d}")

    def _toggle_recording(self) -> None:
        if not self.controller.is_recording():
            self.controller.start_recording()
            self.lbl_rec_badge.setVisible(True)
            self.btn_toggle_rec.setText("STOP RECORDING")
            self.btn_toggle_rec.setProperty("class", "btn-danger")
            self.lbl_status.setText("Recording in progress...")
        else:
            self.btn_toggle_rec.setEnabled(False)
            self.btn_toggle_rec.setText("SAVING…")
            ok, filename = self.controller.stop_recording()
            self.lbl_rec_badge.setVisible(False)
            self.btn_toggle_rec.setText("START RECORDING")
            self.btn_toggle_rec.setProperty("class", "")
            self.btn_toggle_rec.setEnabled(True)
            if ok and filename:
                self.lbl_status.setText(f"SAVED: {filename}")
            else:
                self.lbl_status.setText("Recording stopped (no file).")

    def _on_back(self) -> None:
        self.deactivate()
        self.back_to_menu.emit()


# 6. Media Gallery View
class GalleryWidget(QWidget):
    back_to_menu = Signal()

    def __init__(self, controller: SurveillanceController, media_type: str = "images", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.media_type = media_type

        self.layout = QVBoxLayout(self)
        self.topbar = TopBar(f"Saved {media_type.capitalize()}", show_back=True)
        self.topbar.back_clicked.connect(self.back_to_menu.emit)
        self.layout.addWidget(self.topbar)

        content = QHBoxLayout()

        self.list_widget = QListWidget()
        self.list_widget.setFixedWidth(280)
        self.list_widget.currentRowChanged.connect(self._on_select_file)
        content.addWidget(self.list_widget)

        v_panel = QVBoxLayout()
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("background-color: #0F1A12; border: 1px solid #1E3024;")
        v_panel.addWidget(self.preview_label)

        btn_box = QHBoxLayout()
        self.btn_delete = QPushButton("DELETE SELECTED FILE")
        self.btn_delete.setProperty("class", "btn-danger")
        self.btn_delete.clicked.connect(self._do_delete)
        btn_box.addWidget(self.btn_delete)
        v_panel.addLayout(btn_box)

        content.addLayout(v_panel)
        self.layout.addLayout(content)

    def activate(self) -> None:
        self.list_widget.clear()
        files = self.controller.list_images() if self.media_type == "images" else self.controller.list_videos()

        for f in files:
            self.list_widget.addItem(QListWidgetItem(f))

        if not files:
            self.preview_label.setText("NO CAPTURES STORED")
            self.btn_delete.setEnabled(False)
        else:
            self.list_widget.setCurrentRow(0)
            self.btn_delete.setEnabled(True)

    def _on_select_file(self, row: int) -> None:
        item = self.list_widget.item(row)
        if not item:
            return
        filename = item.text()
        if self.media_type == "images":
            path = self.controller.get_image_path(filename)
            if os.path.exists(path):
                pixmap = QPixmap(path).scaled(
                    480, 320,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.preview_label.setPixmap(pixmap)
        else:
            path = self.controller.get_video_path(filename)
            size_mb = os.path.getsize(path) / (1024 * 1024) if os.path.exists(path) else 0.0
            self.preview_label.setText(f"VIDEO CLIP\n\n{filename}\n\nSize: {size_mb:.2f} MB\nFormat: MP4 (H.264)")

    def _do_delete(self) -> None:
        item = self.list_widget.currentItem()
        if not item:
            return
        filename = item.text()
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Permanently delete {filename}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self.media_type == "images":
                self.controller.delete_image(filename)
            else:
                self.controller.delete_video(filename)
            self.activate()


# 7. Settings Screen
class SettingsWidget(QWidget):
    back_to_menu = Signal()

    def __init__(self, controller: SurveillanceController, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.controller = controller
        layout = QVBoxLayout(self)

        self.topbar = TopBar("System Settings & Status", show_back=True)
        self.topbar.back_clicked.connect(self.back_to_menu.emit)
        layout.addWidget(self.topbar)

        card = QFrame()
        card.setProperty("class", "card")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(30, 24, 30, 24)
        c_layout.setSpacing(12)

        self.lbl_camera = QLabel()
        self.lbl_images = QLabel()
        self.lbl_videos = QLabel()
        self.lbl_storage = QLabel()
        self.lbl_detector = QLabel()

        for lbl in (self.lbl_camera, self.lbl_images, self.lbl_videos, self.lbl_storage, self.lbl_detector):
            c_layout.addWidget(lbl)

        c_layout.addStretch()
        layout.addWidget(card)

    def activate(self) -> None:
        summary = self.controller.get_storage_summary()
        det = self.controller.get_detector_status()

        cam_status = "ONLINE (Picamera2)" if summary.get("camera_available") else "SIMULATION MODE"
        self.lbl_camera.setText(f"Camera Hardware : {cam_status}")
        self.lbl_images.setText(f"Saved Images    : {summary.get('image_count', 0)} files")
        self.lbl_videos.setText(f"Saved Videos    : {summary.get('video_count', 0)} files")
        self.lbl_storage.setText(
            f"Disk Storage    : {summary.get('free_gb', 0.0)} GB free / {summary.get('total_gb', 0.0)} GB total"
        )
        det_status = f"FPS={det.get('fps', 0.0):.1f} | Loaded={det.get('loaded')} | Confirmed={det.get('confirmed', 0)}"
        self.lbl_detector.setText(f"NIRDet Detector : {det_status}")


# 8. Operator PIN Change Screen
class ChangePinWidget(QWidget):
    back_to_menu = Signal()

    def __init__(self, controller: SurveillanceController, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.controller = controller
        layout = QVBoxLayout(self)

        self.topbar = TopBar("Change PIN", show_back=True)
        self.topbar.back_clicked.connect(self.back_to_menu.emit)
        layout.addWidget(self.topbar)

        card = QFrame()
        card.setProperty("class", "card")
        card.setFixedWidth(400)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(30, 24, 30, 24)
        c_layout.setSpacing(14)

        self.lbl_msg = QLabel()
        self.lbl_msg.setProperty("class", "error-banner")
        self.lbl_msg.setVisible(False)
        c_layout.addWidget(self.lbl_msg)

        c_layout.addWidget(QLabel("Current PIN:"))
        self.edit_old = QLineEdit()
        self.edit_old.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_old.setMaxLength(4)
        c_layout.addWidget(self.edit_old)

        c_layout.addWidget(QLabel("New PIN:"))
        self.edit_new = QLineEdit()
        self.edit_new.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_new.setMaxLength(4)
        c_layout.addWidget(self.edit_new)

        c_layout.addWidget(QLabel("Confirm New PIN:"))
        self.edit_confirm = QLineEdit()
        self.edit_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_confirm.setMaxLength(4)
        c_layout.addWidget(self.edit_confirm)

        btn_save = QPushButton("UPDATE PIN")
        btn_save.clicked.connect(self._do_update)
        c_layout.addWidget(btn_save)

        center_box = QHBoxLayout()
        center_box.addStretch()
        center_box.addWidget(card)
        center_box.addStretch()
        layout.addLayout(center_box)

    def _do_update(self) -> None:
        old = self.edit_old.text()
        new = self.edit_new.text()
        confirm = self.edit_confirm.text()

        ok, msg = self.controller.change_pin(old, new, confirm)
        self.lbl_msg.setText(msg)
        self.lbl_msg.setVisible(True)
        if ok:
            self.lbl_msg.setStyleSheet("background-color: rgba(0, 255, 65, 0.15); color: #00FF41;")
            self.edit_old.clear()
            self.edit_new.clear()
            self.edit_confirm.clear()
        else:
            self.lbl_msg.setStyleSheet("background-color: rgba(255, 59, 48, 0.15); color: #FF3B30;")
