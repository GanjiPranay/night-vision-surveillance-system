# V2 Implementation Plan

## Route → backend map (V1 → V2)

| Route | Method | V1 calls | V2 calls |
|---|---|---|---|
| `/` | GET | redirect only | unchanged |
| `/login` | GET/POST | `auth.verify_login` | unchanged (SQLite auth untouched) |
| `/logout` | GET | `camera.stop_preview()` | `SurveillanceService.release_camera()` |
| `/manual` | GET/POST | static page | unchanged |
| `/dashboard` | GET | `camera.stop_preview()` | `SurveillanceService.release_camera()` |
| `/capture/image` GET | | starts overlay preview | `SurveillanceService.start_preview("still")` |
| `/capture/image` POST | | `camera.capture_image()` | `SurveillanceService.capture_image()` |
| `/capture/image/exit` | GET | `camera.stop_preview()` | `SurveillanceService.release_camera()` |
| `/capture/video` GET | | starts overlay preview | `SurveillanceService.start_preview("video")` |
| `/capture/video/start` POST | | `camera.start_recording()` | `SurveillanceService.start_recording()` |
| `/capture/video/stop` POST | | `camera.stop_recording()` | `SurveillanceService.stop_recording()` |
| `/capture/video/exit` | GET | stop recording or preview | same, via `SurveillanceService` |
| `/media/images/<f>`, `/media/videos/<f>` | GET | `send_file` from `IMAGE_DIR`/`VIDEO_DIR` | unchanged — paths now owned by `StorageManager` |
| `/gallery/images`, `/gallery/videos` | GET | `camera.list_images/videos()` | `StorageManager.list_images/videos()` |
| `/gallery/*/delete/<f>` | POST | `camera.delete_image/video()` | `StorageManager.delete_image/video()` |
| `/change_password` | GET/POST | `auth.change_password` | unchanged |
| `/settings` | GET | `camera.storage_summary()` | `StorageManager.storage_summary()` + `HealthService.camera_status()` |
| **NEW** `/live_detect` (name TBD) | GET | *does not exist in V1* | `NIRPersonDetectorService` + `StreamManager` — new route, new template |

No template needs structural changes for the first 6 rows — same variable names in, same variable names out (`camera_available`, `saved_filename`, `stats`, etc.).

## Why the last row is new work, not a port

None of the current templates (`capture_image.html`, `capture_video.html`) contain a live video element — the "LIVE FEED" box is a static placeholder `div`. The actual picture the operator sees came from an OS-level camera overlay window (`rpicam-still -p 20,80,560,380`) sitting *behind* the browser, not from anything in the page's HTML/JS. Picamera2 can reproduce that same overlay trick (`Preview.DRM` at the same rectangle) for plain capture/record — so those two screens can stay pixel-identical with almost no template change.

But showing **AI bounding boxes** requires the boxes to be drawn into the picture itself, which only works if the picture is actually inside the browser page (an `<img>` tag fed by an MJPEG stream, like the `/video_feed` route mentioned in the project overview). That page doesn't exist yet in this repo. It's new template + new route + new backend, not a migration of anything already there.

## Test suite

`tests/test_camera_preview.py` patches V1 internals directly — `camera.subprocess.Popen`, `camera._preview_process`, `camera._recording_state`. None of that exists once the backend is Picamera2. These tests need to be **rewritten against `SurveillanceService`'s public methods** (does calling `start_recording()` then `stop_recording()` return a filename; does `release_camera()` actually free the camera), not patched to keep passing. Treat the old file as a spec of *behavior* to preserve, not code to reuse.

## Suggested build order

1. `Picamera2CameraService` + `SimulatedCameraService`, exposing the *same* function surface `camera.py` already has (`start_preview`, `stop_preview`, `capture_image`, `start_recording`, `stop_recording`, `is_recording`, `list_images`, `list_videos`, `delete_image`, `delete_video`, `storage_summary`). `app.py` needs almost no changes at this stage — lowest-risk path to a working V2 with full V1 feature parity.
2. Rewrite the test suite against that service's public methods. Confirm parity.
3. Only then add `NIRPersonDetectorService` + `StreamManager` + the new live-detect route/template on top of the same camera instance (see `ARCHITECTURE_V2.md` and `MODEL_INTEGRATION.md`).
