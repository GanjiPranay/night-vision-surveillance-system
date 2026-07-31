# Night Vision Surveillance System

A touch-first Flask-based kiosk application for a Raspberry Pi 5 with a Raspberry Pi Camera Module 3 NoIR and a 5-inch touchscreen. It is designed for low-latency image and video capture in field or tactical-style surveillance workflows.

This project provides a simple operator interface for:
- logging in with a username and 4-digit PIN,
- reading a short operating manual,
- capturing still images,
- recording video,
- viewing saved media in galleries,
- changing the current operator PIN,
- checking basic storage usage.

The app works on a real Raspberry Pi camera setup and can also be tested on a laptop or desktop without camera hardware through simulation mode.

---

## Overview

The application presents a dark, low-glare, touch-friendly interface styled for night or low-light use. It is intended for a single operator with minimal interaction:

- log in,
- review the manual screen,
- access the dashboard,
- capture an image or start recording video,
- review and manage saved files.

The experience is optimized for a kiosk setup where everything is large, readable, and easy to tap.

---

## Features

### Authentication and operator access
- Username-based login
- 4-digit PIN authentication
- SQLite-backed user database
- Default operator accounts created automatically on first launch
- PIN change screen for the current operator

### Capture workflow
- Capture still images and save them as timestamped JPEG files
- Record videos and save them as timestamped MP4 files
- Use a live hardware preview overlay when available
- Provide a persistent Quit Feed button for clean exit
- Automatically save an in-progress recording if the user exits mid-recording

### Media management
- Gallery for saved images
- Gallery for saved videos
- Delete media files from the galleries
- Play or view saved media directly in the browser

### Operator interface
- Dark tactical-style theme
- Large touch targets
- Green and amber visual accents for a night-view style
- Simple dashboard layout for rapid navigation

### System status
- Storage usage summary
- Camera availability detection
- Simulation mode for development and testing on non-Pi machines

---

## Project structure

```text
capture_system/
├── app.py
├── auth.py
├── camera.py
├── database.db
├── pyrightconfig.json
├── requirements.txt
├── README.md
├── static/
│   ├── captures/
│   │   ├── images/
│   │   └── videos/
│   └── css/
│       └── style.css
├── templates/
│   ├── base.html
│   ├── capture_image.html
│   ├── capture_video.html
│   ├── change_password.html
│   ├── dashboard.html
│   ├── gallery_images.html
│   ├── gallery_videos.html
│   ├── login.html
│   ├── manual.html
│   ├── settings.html
└── tests/
    └── test_camera_preview.py
```

### Key files
- app.py: Flask app and route definitions
- camera.py: camera command handling, preview lifecycle, recording control, and media saving
- auth.py: login, PIN checks, password hashing, and database setup
- templates/: HTML pages for the web UI
- static/: CSS and saved media files
- tests/: regression tests for the camera preview and recording flow

---

## How the app works

1. The Flask server starts from app.py.
2. The operator opens the app in a browser.
3. The login page appears.
4. After login, the operator sees the manual screen.
5. The dashboard provides access to image capture, video capture, gallery, settings, and PIN change.
6. When the operator enters the capture screen, the app starts the camera preview overlay.
7. The operator captures an image or starts recording video.
8. Files are saved into the relevant folder inside static/captures.

### Camera preview behavior
The application uses a native Raspberry Pi camera preview overlay instead of streaming frames over HTTP. This keeps the feed responsive and low-latency.

On the Raspberry Pi, the preview is started with the native camera commands and displayed directly on the screen. On a laptop or desktop without the camera stack installed, the app falls back to simulation mode.

### Auto-save while recording
If the operator quits the video feed during an active recording, the app stops the recording cleanly and saves the file captured up to that moment.

---

## Installation

### Requirements
The app requires Python 3.10+ and the packages listed in requirements.txt.

### Setup
```bash
cd capture_system
python -m venv venv
source venv/bin/activate
# On Windows use: venv\Scripts\activate
pip install -r requirements.txt
```

### Run the app
```bash
python app.py
```

Then open:
```text
http://localhost:5000
```

---

## Default login credentials

The app creates default operator accounts automatically when it first starts.

Default usernames:
- J1
- J2
- J3
- J4

Default PIN for each account:
- 1234

It is recommended to change the PIN after first login.

---

## Camera support

### On a Raspberry Pi
The app is designed to use the following camera tools:
- rpicam-still
- rpicam-vid

These commands are used to start the preview overlay and perform capture and recording.

### On a non-Pi machine
If the camera tools are not present, the app will not crash. Instead, it will:
- simulate an image capture,
- simulate a video recording,
- save placeholder media so the interface can still be tested end to end.

This is useful for development before the hardware is available.

---

## Media storage

Captured files are stored in:
- static/captures/images/
- static/captures/videos/

The application creates these directories automatically if they do not exist.

Files are saved with timestamps in their filenames so they remain unique.

---

## Testing

A regression test file is included for the camera preview and recording logic.

Run tests with:
```bash
python -m unittest discover -s tests -v
```

This verifies that the preview lifecycle and recording stop behavior are functioning correctly.

---

## Recommended GitHub repository structure

```text
night-vision-surveillance-system/
├── app.py
├── auth.py
├── camera.py
├── database.db
├── pyrightconfig.json
├── requirements.txt
├── README.md
├── static/
│   ├── captures/
│   │   ├── images/
│   │   └── videos/
│   └── css/
│       └── style.css
├── templates/
│   ├── base.html
│   ├── capture_image.html
│   ├── capture_video.html
│   ├── change_password.html
│   ├── dashboard.html
│   ├── gallery_images.html
│   ├── gallery_videos.html
│   ├── login.html
│   ├── manual.html
│   ├── settings.html
└── tests/
    └── test_camera_preview.py
```

---

## Future improvements

Possible future enhancements:
- admin panel for managing operators
- configurable camera settings
- storage quota warnings
- logging and audit trail
- remote monitoring or export features
- improved kiosk startup and boot automation on Raspberry Pi

---

## Summary

This project is a complete Flask-based operator interface for a Raspberry Pi surveillance capture system. It supports login, media capture, galleries, PIN changes, storage monitoring, and a low-latency hardware preview workflow for image and video capture.

It is practical for testing on a laptop today and for deployment on a Raspberry Pi later, with the camera commands and UI already aligned with the current implementation.

