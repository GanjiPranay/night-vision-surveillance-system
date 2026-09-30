# Camera & Settings — V2 changes

`settings.html` needs zero template changes. Only where its data comes from changes:

| Field shown | V1 source | V2 source |
|---|---|---|
| Camera Module status | `shutil.which("rpicam-still") is not None` | Picamera2 device probe (e.g. `Picamera2.global_camera_info()` non-empty) |
| Saved Images / Videos count | `camera.list_images/videos()` | `StorageManager.list_images/videos()` |
| Storage Used / Free | `shutil.disk_usage()` | unchanged |
| Logged-in Operator | `session.username` | unchanged |

## Explicitly out of scope for this version (per spec)

- No PIR sensor field, config, or placeholder anywhere in Settings.
- No IR-illuminator on/off control, brightness, or status field. The illuminator physically exists and may be manually switched, but the software must not reference, configure, or display anything about it.
- No user-editable detection threshold. It's a measured model property (`deploy_score_thresh` in the profile), not a setting — matches the "no threshold literal" rule in `MODEL_INTEGRATION.md`.
