"""
camera_v2.py
------------
Picamera2-backed replacement for the old camera.py (which used rpicam-still /
rpicam-vid subprocesses).

SAME PUBLIC FUNCTIONS as V1's camera.py, so app.py needs almost no changes:
    start_preview(mode), stop_preview(), capture_image(), start_recording(),
    stop_recording(), is_recording(), list_images(), list_videos(),
    delete_image(filename), delete_video(filename), storage_summary()

SIMULATION MODE: if no camera is detected, falls back to the same kind of
placeholder image/video V1 used, so the rest of the app still works.

NOT IN THIS VERSION (per the V2 spec): no PIR sensor, no IR-illuminator
control. Nothing here references either.

============================================================================
HONEST WARNING — READ BEFORE WIRING THIS INTO FLASK
============================================================================
I have not been able to run this against a real Raspberry Pi + camera — I
don't have hardware access. Picamera2's behaviour when you switch a SINGLE
camera object between preview / still-capture / video-recording modes has
real subtlety that I can't fully verify without testing.

Before you plug this into app.py, test it standalone on the Pi with a tiny
script like:

    import camera_v2 as camera
    camera.start_preview("still")
    input("check the screen, then press enter")
    camera.stop_preview()
    print(camera.capture_image())
    camera.start_recording()
    time.sleep(3)
    print(camera.stop_recording())

If `start_preview`'s on-screen positioning (Preview.DRM with x/y/width/height)
doesn't land in the right spot, or errors out, the safest fallback is to drop
the preview call and go straight to simulation-style testing on the Pi with
`camera.start_preview = lambda *a, **k: None` while we build the in-app video
page — the capture/record functions don't depend on the preview working.
============================================================================
"""

import os
import shutil
import subprocess
import threading
import time
import io
from datetime import datetime
from typing import Any, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAPTURE_ROOT = os.environ.get(
    "NV_CAPTURE_ROOT", os.path.join(BASE_DIR, "static", "captures")
)
IMAGE_DIR = os.path.join(CAPTURE_ROOT, "images")
VIDEO_DIR = os.path.join(CAPTURE_ROOT, "videos")
os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)

# Same on-screen rectangle V1 used with `-p 20,80,560,380` (x, y, width, height)
NV_PREVIEW_RECT = (20, 80, 560, 380)

try:
    from picamera2 import Picamera2, Preview
    from picamera2.encoders import H264Encoder
    from picamera2.outputs import FfmpegOutput
    CAMERA_AVAILABLE = len(Picamera2.global_camera_info()) > 0
except Exception:
    CAMERA_AVAILABLE = False

print(f"[camera_v2] image folder : {IMAGE_DIR}")
print(f"[camera_v2] video folder : {VIDEO_DIR}")
print(f"[camera_v2] camera available : {CAMERA_AVAILABLE}")

# One camera instance for the WHOLE app — never create a second one anywhere.
_lock = threading.Lock()
_cam: Optional["Picamera2"] = None
_preview_active = False
_recording_state: dict[str, Any] = {
    "filepath": None,
    "filename": None,
    "started_at": None,
}


def _get_camera():
    global _cam
    if _cam is None:
        _cam = Picamera2()
    return _cam


def _timestamp():
    # microsecond resolution — avoids two captures in the same second
    # silently overwriting each other, same fix V1 made
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")


def start_preview(mode="still"):
    """Starts the camera (no on-screen window; live view comes later, in-page)."""
    global _preview_active
    if not CAMERA_AVAILABLE:
        return
    # The AI detector and the normal preview cannot own the camera together.
    # Stop AI mode before changing back to the normal preview.
    if _detect_active:
        stop_detect_mode()
    with _lock:
        if _preview_active and _get_camera().started:
            return
        try:
            cam = _get_camera()
            if cam.started:
                cam.stop()
            cam.configure(cam.create_video_configuration(main={"size": (1280, 720)}))
            cam.start()
            _preview_active = True
        except Exception as e:
            print(f"[camera_v2] Error starting camera: {e}")


def stop_preview():
    global _preview_active
    if not CAMERA_AVAILABLE:
        return
    with _lock:
        try:
            cam = _get_camera()
            if cam.started:
                cam.stop()
        except Exception as e:
            print(f"[camera_v2] Error stopping camera: {e}")
        finally:
            _preview_active = False


def capture_image():
    """Captures a single photo. Returns the saved filename."""
    if _detect_active:
        stop_detect_mode()
    stop_preview()
    filename = f"image_{_timestamp()}.jpg"
    filepath = os.path.join(IMAGE_DIR, filename)
    if CAMERA_AVAILABLE:
        with _lock:
            cam = _get_camera()
            still_cfg = cam.create_still_configuration()
            # switch_mode_and_capture_file: starts the camera if needed,
            # captures in still config, then leaves it stopped again.
            cam.switch_mode_and_capture_file(still_cfg, filepath)
            if cam.started:
                cam.stop()
    else:
        _make_placeholder_image(filepath)
    return filename

_rec_thread = None
_rec_stop = threading.Event()
_rec_started = threading.Event()
_rec_error = None

def get_frame_jpeg(width=640):
    """One live-view picture (JPEG bytes), or None if the camera isn't running."""
    if not CAMERA_AVAILABLE:
        return _make_placeholder_frame()
    with _lock:
        cam = _get_camera()
        if not cam.started:
            return None
        try:
            arr = cam.capture_array("main")
        except Exception as e:
            print(f"[camera_v2] live frame error: {e}")
            return None
    from PIL import Image
    img = Image.fromarray(arr[:, :, :3])
    img.thumbnail((width, width))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


def _make_placeholder_frame():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (640, 360), (45, 106, 79))
    ImageDraw.Draw(img).text(
        (20, 170), "SIMULATED LIVE FEED  " + datetime.now().strftime("%H:%M:%S"),
        fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    time.sleep(0.1)
    return buf.getvalue()


def _recording_worker(filepath):
    """Stays alive for the WHOLE recording (ffmpeg dies if this thread ends)."""
    global _rec_error
    try:
        with _lock:
            cam = _get_camera()
            cam.configure(cam.create_video_configuration(main={"size": (1280, 720)}))
            cam.start_recording(H264Encoder(), FfmpegOutput(filepath))
    except Exception as e:
        _rec_error = e
        _rec_started.set()
        return
    _rec_started.set()
    _rec_stop.wait()
    with _lock:
        try:
            cam.stop_recording()
        except Exception as e:
            print(f"[camera_v2] Error stopping recording: {e}")

def start_recording():
    """Starts a video recording that keeps going until stop_recording()."""
    global _rec_thread, _rec_error
    filename = f"video_{_timestamp()}.mp4"
    filepath = os.path.join(VIDEO_DIR, filename)
    if _detect_active:
        stop_detect_mode()
    stop_preview()
    if CAMERA_AVAILABLE:
        _rec_error = None
        _rec_stop.clear()
        _rec_started.clear()
        _rec_thread = threading.Thread(
            target=_recording_worker, args=(filepath,), daemon=True)
        _rec_thread.start()
        _rec_started.wait(timeout=15)
        if _rec_error is not None:
            raise _rec_error
    _recording_state["filepath"] = filepath
    _recording_state["filename"] = filename
    _recording_state["started_at"] = time.time()


def stop_recording():
    """Stops the current recording and returns the saved filename."""
    filename = _recording_state["filename"]
    filepath = _recording_state["filepath"]
    started_at = _recording_state["started_at"]
    elapsed = max(1, round(time.time() - (started_at or time.time())))

    if CAMERA_AVAILABLE:
        _rec_stop.set()
        if _rec_thread is not None:
            _rec_thread.join(timeout=20)
    else:
        _make_placeholder_video(filepath, elapsed)

    _recording_state["filepath"] = None
    _recording_state["filename"] = None
    _recording_state["started_at"] = None
    return filename
    
def is_recording():
    return _recording_state["started_at"] is not None
    
# ---------------------------------------------------------------------
# Everything below is UNCHANGED from V1's camera.py — pure filesystem
# bookkeeping, no rpicam or picamera2 dependency at all.
# ---------------------------------------------------------------------

def list_images():
    files = []
    for filename in os.listdir(IMAGE_DIR):
        path = os.path.join(IMAGE_DIR, filename)
        if not os.path.isfile(path):
            continue
        if filename.lower().endswith((".jpg", ".jpeg", ".png")):
            files.append(filename)
            continue
        try:
            with open(path, "rb") as f:
                header = f.read(8)
                if header.startswith(b"\xff\xd8\xff") or header == b"\x89PNG\r\n\x1a\n":
                    files.append(filename)
        except OSError:
            continue
    files.sort(reverse=True)
    return files


def list_videos():
    files = [f for f in os.listdir(VIDEO_DIR) if f.lower().endswith((".mp4", ".h264"))]
    files.sort(reverse=True)
    return files


def delete_image(filename):
    path = os.path.join(IMAGE_DIR, filename)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def delete_video(filename):
    path = os.path.join(VIDEO_DIR, filename)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def storage_summary():
    total, used, free = shutil.disk_usage(BASE_DIR)
    return {
        "image_count": len(list_images()),
        "video_count": len(list_videos()),
        "free_gb": round(free / (1024 ** 3), 1),
        "total_gb": round(total / (1024 ** 3), 1),
        "camera_available": CAMERA_AVAILABLE,
    }


# ---------------------------------------------------------------------
# Simulation helpers — same purpose as V1, only used when no camera exists.
# ---------------------------------------------------------------------

def _make_placeholder_image(filepath):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (640, 480), color=(45, 106, 79))
    draw = ImageDraw.Draw(img)
    draw.text((20, 220), "SIMULATED IMAGE (V2 / Picamera2)", fill=(255, 255, 255))
    draw.text((20, 250), "(no camera detected on this machine)", fill=(255, 255, 255))
    img.save(filepath)
    time.sleep(0.5)


def _make_placeholder_video(filepath, duration_seconds):
    if shutil.which("ffmpeg") is not None:
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi",
                 "-i", f"color=c=darkgreen:s=640x480:d={duration_seconds}",
                 filepath],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return
        except Exception:
            pass
    time.sleep(min(duration_seconds, 2))
    open(filepath, "wb").close()
    
    
_detect_active = False


def start_detect_mode():
    """Switches the shared camera into the format the person detector needs.
    Call stop_detect_mode() before using capture/record/preview again."""
    global _detect_active, _preview_active
    if not CAMERA_AVAILABLE:
        return
    # Stop the normal preview before switching the shared camera to YUV420.
    if _preview_active:
        stop_preview()
    with _lock:
        if _detect_active:
            return
        try:
            cam = _get_camera()
            if cam.started:
                cam.stop()
            cfg = cam.create_video_configuration(
                main={"size": (1280, 720), "format": "YUV420"})
            cam.configure(cfg)
            cam.start()
            _detect_active = True
            _preview_active = False
        except Exception as e:
            print(f"[camera_v2] Error starting detect mode: {e}")


def stop_detect_mode():
    global _detect_active
    if not CAMERA_AVAILABLE or not _detect_active:
        return
    with _lock:
        try:
            _get_camera().stop()
        except Exception as e:
            print(f"[camera_v2] Error stopping detect mode: {e}")
        finally:
            _detect_active = False


def get_frame_y():
    """One Y-plane (grayscale) frame for the detector, or None if detect
    mode isn't running or a frame isn't ready yet."""
    if not CAMERA_AVAILABLE or not _detect_active:
        return None
    with _lock:
        try:
            cam = _get_camera()
            if not cam.started:
                return None
            yuv = cam.capture_array("main")
            if yuv.ndim == 3:
                yuv = yuv[:, :, 0]
            expected_height = 720
            if yuv.shape[0] == expected_height:
                return yuv
            if yuv.shape[0] >= expected_height:
                return yuv[:expected_height, :]
            print(f"[camera_v2] Unexpected YUV frame shape: {yuv.shape}")
            return None
        except Exception as e:
            print(f"[camera_v2] Error reading detector frame: {e}")
            return None
