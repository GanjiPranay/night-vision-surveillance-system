"""
app.py
------
Main Flask app. Run this file to start the server:

    python app.py

Then open a browser to http://localhost:5000  (on the Pi, kiosk mode
will do this automatically - see README.md).
"""

import functools
import os
import subprocess
import threading
import time
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    send_from_directory,  # >>> CHANGED - NEW import for the media routes below
    send_file,
    abort,
)
# >>> CHANGED: the ORIGINAL import line was - and had no send_from_directory:
#     from flask import Flask, render_template, request, redirect, url_for, session, flash
# >>> END CHANGED

import auth
import camera

app = Flask(__name__)

# IMPORTANT: change this to a random string before real deployment.
app.secret_key = "please-change-this-secret-key"

auth.init_db()


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/")
def index():
    if "username" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = auth.verify_login(username, password)
        if user:
            session["username"] = user["username"]
            return redirect(url_for("manual"))
        flash("Wrong username or password. Please try again.")
    usernames = auth.get_all_usernames()
    return render_template("login.html", usernames=usernames)


@app.route("/logout")
def logout():
    camera.stop_preview()
    session.clear()
    return redirect(url_for("login"))



@app.route("/manual", methods=["GET", "POST"])
@login_required
def manual():
    if request.method == "POST":
        return redirect(url_for("dashboard"))
    return render_template("manual.html")


@app.route("/dashboard")
@login_required
def dashboard():
    camera.stop_preview()
    return render_template("dashboard.html")


@app.route("/capture/image", methods=["GET", "POST"])
@login_required
def capture_image_page():
    saved_filename = None
    if request.method == "POST":
        saved_filename = camera.capture_image()
    else:
        # Start the hardware preview overlay when entering the capture screen
        camera.start_preview("still")
    return render_template(
        "capture_image.html",
        saved_filename=saved_filename,
        camera_available=camera.CAMERA_AVAILABLE,
    )


@app.route("/capture/image/exit")
@login_required
def capture_image_exit():
    camera.stop_preview()
    return redirect(url_for("dashboard"))


@app.route("/capture/video")
@login_required
def capture_video_page():
    saved_filename = request.args.get("saved")
    if not saved_filename:
        # Start the hardware preview overlay when entering the video screen (before recording)
        camera.start_preview("video")
    return render_template(
        "capture_video.html",
        saved_filename=saved_filename,
        camera_available=camera.CAMERA_AVAILABLE,
    )


@app.route("/capture/video/start", methods=["POST"])
@login_required
def capture_video_start():
    if not camera.is_recording():
        camera.start_recording()
    return {"status": "recording"}


@app.route("/capture/video/stop", methods=["POST"])
@login_required
def capture_video_stop():
    filename = camera.stop_recording()
    return {"status": "saved", "filename": filename}


@app.route("/capture/video/exit")
@login_required
def capture_video_exit():
    if camera.is_recording():
        # Cleanly stop and auto-save the video in progress
        camera.stop_recording()
    else:
        camera.stop_preview()
    return redirect(url_for("dashboard"))



# ---------------------------------------------------------------------------
# >>> CHANGED - THESE TWO ROUTES ARE COMPLETELY NEW. Nothing was removed:
# the original app.py had no /media/... routes at all.
#
# WHAT THE TEMPLATES USED TO ASK FOR (the original, un-patched URLs):
#     url_for('static', filename='captures/images/' ~ saved_filename)
#     url_for('static', filename='captures/images/' ~ img)
#     url_for('static', filename='captures/videos/' ~ saved_filename)
#     url_for('static', filename='captures/videos/' ~ vid)
#
# WHY THE CHANGE: Flask's /static/... route serves "<folder of app.py>/static",
# while camera.py writes into "<folder of camera.py>/static/captures/...".
# Those are the same directory only by coincidence - and when they differ, the
# file really is on disk but every URL returns 404 (broken preview rectangle
# plus an empty gallery). send_from_directory(camera.IMAGE_DIR, ...) can never
# drift, because it is the exact same variable that was used to write the file.
# ---------------------------------------------------------------------------
@app.route("/media/images/<path:filename>")
@login_required
def media_image(filename):
    # Some older Pi captures have no .jpg extension. Send those files with
    # an explicit image type so the browser can display them correctly.
    path = os.path.join(camera.IMAGE_DIR, filename)
    if not os.path.isfile(path) or os.path.commonpath(
        [os.path.realpath(path), os.path.realpath(camera.IMAGE_DIR)]
    ) != os.path.realpath(camera.IMAGE_DIR):
        abort(404)

    mimetype = "image/jpeg"
    try:
        with open(path, "rb") as image_file:
            if image_file.read(8) == b"\x89PNG\r\n\x1a\n":
                mimetype = "image/png"
    except OSError:
        abort(404)
    return send_file(path, mimetype=mimetype, conditional=True)


@app.route("/media/videos/<path:filename>")
@login_required
def media_video(filename):
    return send_from_directory(camera.VIDEO_DIR, filename, conditional=True)


@app.route("/gallery/images")
@login_required
def gallery_images():
    images = camera.list_images()
    return render_template("gallery_images.html", images=images)


@app.route("/gallery/images/delete/<filename>", methods=["POST"])
@login_required
def delete_image_route(filename):
    camera.delete_image(filename)
    return redirect(url_for("gallery_images"))


@app.route("/gallery/videos")
@login_required
def gallery_videos():
    videos = camera.list_videos()
    return render_template("gallery_videos.html", videos=videos)


@app.route("/gallery/videos/delete/<filename>", methods=["POST"])
@login_required
def delete_video_route(filename):
    camera.delete_video(filename)
    return redirect(url_for("gallery_videos"))


@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password_page():
    message = None
    if request.method == "POST":
        old = request.form.get("old_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if new != confirm:
            message = ("error", "New PINs do not match.")
        elif not auth.is_valid_pin(new):
            message = ("error", "PIN must be exactly 4 digits (0-9).")
        else:
            ok, msg = auth.change_password(session["username"], old, new)
            message = ("success" if ok else "error", msg)
    return render_template("change_password.html", message=message)


@app.route("/settings")
@login_required
def settings_page():
    stats = camera.storage_summary()
    # >>> CHANGED -----------------------------------------------------------
    # ORIGINAL CODE:
    #     stats = camera.storage_summary()
    #     return render_template("settings.html", stats=stats)
    #
    # WHY: these two extra keys let the Settings page print the real folders
    # this running server writes to and serves from, so you can compare them
    # against the folder you open in the file manager.
    stats["image_dir"] = camera.IMAGE_DIR
    stats["video_dir"] = camera.VIDEO_DIR
    # >>> END CHANGED -------------------------------------------------------
    return render_template("settings.html", stats=stats)


def _open_browser():
    """Wait for Flask to start, then launch Chromium pointing at the app."""
    time.sleep(1.5)
    # Try both common Chromium binary names on Raspberry Pi OS
    for binary in ("chromium-browser", "chromium"):
        try:
            subprocess.Popen(
                [binary, "--start-fullscreen", "http://127.0.0.1:5000"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            break  # Stop after the first one that works
        except FileNotFoundError:
            continue  # Try the next binary name


if __name__ == "__main__":
    # Launch Chromium automatically in a background thread so you don't
    # have to click the URL in the terminal manually.
    #threading.Thread(target=_open_browser, daemon=True).start()

    # host="0.0.0.0" lets you open the app from another device on the
    # same network too (useful for testing from your phone/laptop while
    # the Flask server runs on the Pi).
    app.run(host="0.0.0.0", port=5000, debug=False)
