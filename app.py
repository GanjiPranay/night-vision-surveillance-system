"""
app.py
------
Main Flask app. Run this file to start the server:

    python app.py

Then open a browser to http://localhost:5000  (on the Pi, kiosk mode
will do this automatically - see README.md).
"""

import functools
from flask import Flask, render_template, request, redirect, url_for, session, flash

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
    return render_template("settings.html", stats=stats)


if __name__ == "__main__":
    # host="0.0.0.0" lets you open the app from another device on the
    # same network too (useful for testing from your phone/laptop while
    # the Flask server runs on the Pi).
    app.run(host="0.0.0.0", port=5000, debug=False)
