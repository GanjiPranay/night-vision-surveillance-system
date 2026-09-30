# Model Integration — NIRPersonDetectorService

## What gets reused, verbatim, from `live_nirdet.py`

- `NCNNEngine` — loads `nirdet-int8.param` / `nirdet-int8.bin`, runs inference. Initialize once at service startup; never re-create per frame (the pool allocators exist specifically to avoid that cost).
- `preprocess_u8` (from `preprocess.py`) — flat-field → CLAHE → letterbox. Runs on the raw Y-plane frame, at raw resolution, before the model sees it.
- `decode_frame` + `greedy_nms` — turns the three raw output blobs per detection level into boxes + scores.
- `IoUTracker` — confirms a detection only after it persists a few frames, so single-frame false positives don't flash up on screen.
- `verify_contract` — must run once at service startup against `nirdet-int8.contract.json`. If it fails, **the detection feature refuses to start** but the rest of the app (capture/gallery/settings) keeps working — detection is additive, not load-bearing for the core kiosk.

## Rules that must not be relaxed (from the spec)

- **Threshold is never a literal in code.** It comes from `NIRPed.yaml`'s `deploy_score_thresh` (currently `0.43`), loaded the same way `_apply_profile_lite` does it in `live_nirdet.py`. If that profile is ever missing, the service must refuse to start detection rather than invent a default — same as the CLI tool does today.
- **Single class only.** The service reports "person" detections. Don't add a class/label field that could be mistaken for multi-class support — clean extension point, not a stub.
- **`NIRDET_THREADS` environment variable** must be set *before* `ncnn` (or anything importing it) is imported — it's read by OpenMP at library load time. `app.py`'s entrypoint needs to set this before any detection-related import, mirroring the top of `live_nirdet.py`.
- **Y-plane only, no color conversion.** Picamera2 must be configured for `YUV420`, and the detector reads only the Y plane — exactly what `PiCameraSource` does today. Converting to BGR first would silently change what CLAHE and the model see.

## Data flow into the new Flask route

```
Picamera2CameraService (shared camera)
        │ Y-plane frame
        ▼
capture thread ──Queue(2)──▶ inference thread ──Queue(2)──▶ stream encoder
                             (preprocess → NCNN → decode → track)      │
                                                                       ▼
                                                          StreamManager → browser <img>
```

Same drop-not-block queue discipline as `live_nirdet.py`: a slow browser/network connection must never make the camera thread stall.
