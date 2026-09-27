"""
camera.py
---------
Wraps the rpicam-still / rpicam-vid commands you already tested manually.

IMPORTANT FOR TESTING BEFORE THE PI ARRIVES:
If this code runs on a laptop/PC that does NOT have rpicam-still installed
(i.e. no Raspberry Pi camera stack present), it automatically switches to
"simulation mode" and generates a placeholder image/video instead of
crashing. This lets you click through the entire app right now.
On the real Raspberry Pi 5, rpicam-still/rpicam-vid will be found
automatically and the real camera will be used - no code changes needed.
"""

import os
import shutil
import signal
import subprocess
import time
from datetime import datetime
from typing import Any, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# >>> CHANGED ---------------------------------------------------------------
# ORIGINAL CODE:
#     IMAGE_DIR = os.path.join(BASE_DIR, "static", "captures", "images")
#     VIDEO_DIR = os.path.join(BASE_DIR, "static", "captures", "videos")
#
# WHY: camera.py SAVES into the folder sitting next to camera.py, but the
# templates told the browser to fetch /static/captures/images/... which Flask
# RESOLVES next to app.py. Two paths, computed in two different files, with
# nothing tying them together. The moment they point at different folders the
# file is on disk but every URL 404s -> broken preview + empty gallery.
# Now one shared root feeds the writer AND the reader, so "where the camera
# saves" and "what the browser reads" can never drift apart. Override it on
# the Pi with:  NV_CAPTURE_ROOT=/some/folder python app.py
CAPTURE_ROOT = os.environ.get(
    "NV_CAPTURE_ROOT", os.path.join(BASE_DIR, "static", "captures")
)
IMAGE_DIR = os.path.join(CAPTURE_ROOT, "images")
VIDEO_DIR = os.path.join(CAPTURE_ROOT, "videos")
# >>> END CHANGED -----------------------------------------------------------

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)

# >>> CHANGED ---------------------------------------------------------------
# The two print() lines are NEW (original had nothing here). WHY: seeing the
# resolved folder in the terminal turns a silent path mismatch into a fact you
# can compare against the folder you open in the file manager.
print(f"[NV-SYS] image folder : {IMAGE_DIR}")
print(f"[NV-SYS] video folder : {VIDEO_DIR}")
# >>> END CHANGED -----------------------------------------------------------

CAMERA_AVAILABLE = shutil.which("rpicam-still") is not None
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None

# Holds the state of an in-progress recording (only one at a time,
# which is all this single-camera kiosk needs).
_recording_state: dict[str, Any] = {
    "process": None,     # the running rpicam-vid subprocess (real camera only)
    "filepath": None,
    "filename": None,
    "started_at": None,
}

_preview_process: Optional[subprocess.Popen[Any]] = None


def _timestamp():
    # >>> CHANGED -----------------------------------------------------------
    # ORIGINAL CODE:
    #     return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    #
    # WHY: second-resolution names meant two captures inside the same second
    # produced the SAME filename - the second silently overwrote the first, and
    # the browser (having already cached that URL, including a failed load)
    # could keep showing a stale result. Microseconds make every name unique.
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    # >>> END CHANGED -------------------------------------------------------


def start_preview(mode="still"):
    """Starts the native hardware preview overlay using rpicam-still or rpicam-vid."""
    global _preview_process
    stop_preview()

    if not CAMERA_AVAILABLE:
        return

    cmd = []
    if mode == "still":
        cmd = ["rpicam-still", "-t", "0", "-p", "20,80,560,380"]
    elif mode == "video":
        cmd = ["rpicam-vid", "-t", "0", "-p", "20,80,560,380"]

    try:
        _preview_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        print(f"Error starting preview process: {e}")


def stop_preview():
    """Stops the active hardware preview overlay."""
    global _preview_process
    if _preview_process is not None:
        try:
            if _preview_process.poll() is None:
                _preview_process.terminate()
                _preview_process.wait(timeout=2)
        except Exception:
            try:
                _preview_process.kill()
            except Exception:
                pass
        finally:
            _preview_process = None


def capture_image(capture_seconds=2):
    """Captures a single photo. Returns the saved filename."""
    # Ensure the preview is stopped before capturing so the camera is free
    stop_preview()

    filename = f"image_{_timestamp()}.jpg"
    filepath = os.path.join(IMAGE_DIR, filename)

    if CAMERA_AVAILABLE:
        # Same command you tested manually, just with a dynamic filename.
        subprocess.run(
            ["rpicam-still", "-t", str(capture_seconds * 1000), "-o", filepath],
            check=True,
        )
    else:
        _make_placeholder_image(filepath)

    return filename


def start_recording():
    """Starts a video recording that keeps going until stop_recording() is called."""
    # Ensure the preview is stopped before starting recording so the camera is free
    stop_preview()

    filename = f"video_{_timestamp()}.mp4"
    filepath = os.path.join(VIDEO_DIR, filename)

    if CAMERA_AVAILABLE:
        # "-t 0" tells rpicam-vid to record with no time limit, until it
        # receives a stop signal (which stop_recording() sends below).
        # We pass -p 20,80,560,380 so the preview overlay is displayed during recording.
        process = subprocess.Popen(
            ["rpicam-vid", "-t", "0", "-p", "20,80,560,380", "--codec", "libav",
             "--libav-format", "mp4", "-o", filepath]
        )
    else:
        process = None  # simulation mode - nothing actually running

    _recording_state["process"] = process
    _recording_state["filepath"] = filepath
    _recording_state["filename"] = filename
    _recording_state["started_at"] = time.time()



def is_recording():
    return _recording_state["started_at"] is not None


def stop_recording():
    """Stops the current recording and returns the saved filename."""
    filename = _recording_state["filename"]
    filepath = _recording_state["filepath"]
    process = _recording_state["process"]
    started_at = _recording_state["started_at"]
    elapsed = max(1, round(time.time() - (started_at or time.time())))

    if CAMERA_AVAILABLE and process is not None:
        # Ask rpicam-vid to stop cleanly (same as pressing Ctrl+C) and
        # wait for it to finish writing the file.
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
        else:
            time.sleep(0.2)
    else:
        _make_placeholder_video(filepath, elapsed)

    _recording_state["process"] = None
    _recording_state["filepath"] = None
    _recording_state["filename"] = None
    _recording_state["started_at"] = None

    return filename


def list_images():
    files = []
    for filename in os.listdir(IMAGE_DIR):
        path = os.path.join(IMAGE_DIR, filename)
        if not os.path.isfile(path):
            continue

        # New captures normally have .jpg/.jpeg/.png. Older captures on the
        # Pi have no extension, so check their first bytes as a fallback.
        if filename.lower().endswith((".jpg", ".jpeg", ".png")):
            files.append(filename)
            continue

        try:
            with open(path, "rb") as image_file:
                header = image_file.read(8)
            if header.startswith(b"\xff\xd8\xff") or header == b"\x89PNG\r\n\x1a\n":
                files.append(filename)
        except OSError:
            continue

    files.sort(reverse=True)  # newest first
    return files


def list_videos():
    files = [
        f for f in os.listdir(VIDEO_DIR)
        if f.lower().endswith((".mp4", ".h264"))
    ]
    files.sort(reverse=True)  # newest first
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
    """Simple stats used on the Settings page."""
    total, used, free = shutil.disk_usage(BASE_DIR)
    return {
        "image_count": len(list_images()),
        "video_count": len(list_videos()),
        "free_gb": round(free / (1024 ** 3), 1),
        "total_gb": round(total / (1024 ** 3), 1),
        "camera_available": CAMERA_AVAILABLE,
    }


# ---------------------------------------------------------------------
# Simulation helpers - only used when there is no real camera detected
# (i.e. while developing on a laptop, before the Pi + camera are ready)
# ---------------------------------------------------------------------

def _make_placeholder_image(filepath):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (640, 480), color=(45, 106, 79))
    draw = ImageDraw.Draw(img)
    draw.text((20, 220), "SIMULATED IMAGE", fill=(255, 255, 255))
    draw.text((20, 250), "(no camera detected on this machine)", fill=(255, 255, 255))
    img.save(filepath)
    time.sleep(0.5)  # mimic the small delay a real capture has


def _make_placeholder_video(filepath, duration_seconds):
    if FFMPEG_AVAILABLE:
        try:
            # We try generating the video with ffmpeg.
            # On some Windows environments, the drawtext filter can cause a crash (exit code 3221225477)
            # if fontconfig is missing or misconfigured. So we wrap it in try-except.
            subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "lavfi",
                    "-i", f"color=c=darkgreen:s=640x480:d={duration_seconds}",
                    "-vf",
                    "drawtext=text='SIMULATED VIDEO':fontcolor=white:fontsize=28:x=40:y=200",
                    filepath,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except Exception:
            # Try without drawtext if it failed
            try:
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-f", "lavfi",
                        "-i", f"color=c=darkgreen:s=640x480:d={duration_seconds}",
                        filepath,
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except Exception:
                pass

    # Fallback if ffmpeg is missing or failed
    time.sleep(min(duration_seconds, 2))
    open(filepath, "wb").close()
