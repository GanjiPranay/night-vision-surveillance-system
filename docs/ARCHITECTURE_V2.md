# Architecture V2

## The one rule everything else depends on

`Picamera2CameraService` is the **only** code in the whole app allowed to touch a `Picamera2` object. It is created once, at process start, and lives for the app's lifetime — not created-and-destroyed per request the way V1 spawned a new `rpicam-*` subprocess per action. Every other service (recording, detection, still capture) asks this one service for frames or actions; nothing else imports `picamera2` directly.

This matters because a Raspberry Pi camera can only have one owner. `live_nirdet.py`'s `PiCameraSource` currently opens its **own** private `Picamera2()` — that code cannot be dropped in next to the Flask capture routes as-is, or the two will fight over the camera. It has to be rewritten to pull frames from the shared `Picamera2CameraService` instead.

## Two consumers, one camera, never at the same time

- **Capture/record path** — same behavior as V1: still image, or video file written to disk.
- **Detection path** — background thread reads frames (`capture_array("main")`, Y-plane only, same as `live_nirdet.py`), runs them through `NIRPersonDetectorService`, and pushes annotated frames to `StreamManager` for the browser.

Picamera2 needs a specific sensor configuration (resolution/format) per mode, so these two paths cannot run in different configurations simultaneously — same constraint V1 already had (`stop_preview()` is called before every capture/gallery view today). V2 keeps that rule, just enforced by `SurveillanceService` instead of scattered `stop_preview()` calls in `app.py`.

## Live preview, two different ways

- **Plain capture/record screens**: keep the existing look almost unchanged, using Picamera2's `Preview.DRM` positioned at the same screen rectangle the old `-p 20,80,560,380` used. Minimal template risk.
- **New AI-detection screen**: needs an MJPEG stream inside the actual page (an `<img>` tag), because bounding boxes have to be drawn into the frame in Python before the browser ever sees it. This is genuinely new plumbing, not a port.

## Threading model (reusing `live_nirdet.py`'s pattern)

Keep the same 3-stage pipeline that's already proven to hit ~39 fps on the Pi 5: **capture → inference → output**, connected by `queue.Queue(maxsize=2)` with drop-not-block semantics. The only change is the last stage: instead of `cv2.imshow` (a native window), it JPEG-encodes the annotated frame and hands it to `StreamManager`, which serves it over the new Flask route.

Reused as-is: `NCNNEngine`, `preprocess_u8`, `decode_frame`, `IoUTracker`, `verify_contract`.
Rewritten: `PiCameraSource` (must pull from the shared camera service, not open its own), `display_loop` (becomes a stream encoder, not a window).

## State safety

V1's `_preview_process` / `_recording_state` are bare module globals — safe there only because each action was a short-lived subprocess call with no concurrent thread touching that state. V2 has a background detection thread running continuously alongside Flask's request threads, so this state moves onto `Picamera2CameraService` as instance attributes guarded by a lock.
