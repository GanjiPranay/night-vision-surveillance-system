# Night Vision Surveillance System — Version 2

Flask-based night-vision kiosk for Raspberry Pi 5 and a Raspberry Pi NoIR camera.

## Version 2 features

- Picamera2 camera support.
- Normal in-page camera preview.
- AI person-detection preview.
- NCNN INT8 NIR person detector.
- MJPEG browser feed.
- Still image capture.
- MP4 video recording.
- SQLite login and PIN management.
- Image and video galleries.

## Important rules

- Picamera2 is the only real-camera interface.
- `camera_v2.py` is the only camera owner.
- The detector uses the shared camera.
- The detector reads the YUV420 Y-plane only.
- Queue size is 2.
- Person detection only.
- No PIR support.
- No software control of the illuminator.

## Install on Raspberry Pi

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-opencv python3-numpy python3-yaml ffmpeg
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt
