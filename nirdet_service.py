"""
nirdet_service.py  --  NIRPersonDetectorService
-----------------------------------------------
Runs your tested NIRDet person detector on frames from the SHARED camera
(camera_v2) and publishes annotated JPEG pictures for the web page.

DESIGN RULES (from the V2 spec)
  * The model runtime is REUSED, not copied: everything that does real work
    (model loading, preprocessing, decoding, NMS, tracking, contract check,
    capture/inference threads with 2-slot drop-stale queues) is imported
    straight from live_nirdet.py, untouched.
  * Only ONE thing is new: instead of an OpenCV window, the last stage draws
    the boxes and encodes a JPEG for the browser.
  * The threshold comes from NIRPed.yaml (deploy_score_thresh), never from a
    literal in this file.
  * PERSON detector only (the model has one class).
  * If anything fails to load (missing file, contract mismatch, no ncnn), the
    service records the error and detection stays OFF -- the rest of the app
    keeps working.

IMPORT ORDER: import this module BEFORE camera_v2 in app.py. live_nirdet sets
the OpenMP thread variables at import time and they must be set before the
ncnn library is loaded.

NOT TESTED ON REAL HARDWARE YET.
"""

import os
import queue
import threading
import time

try:
    import live_nirdet as nd          # sets OMP_* env vars first thing
    import cv2
    _IMPORT_ERROR = None
except (Exception, SystemExit) as exc:   # keep the kiosk alive without AI
    nd = None
    cv2 = None
    _IMPORT_ERROR = f"detector runtime could not be imported: {exc}"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.environ.get("NIRDET_MODEL_DIR", os.path.join(BASE_DIR, "models"))

PARAM_FILE = "nirdet-int8.param"
BIN_FILE = "nirdet-int8.bin"
PROFILE_FILE = "NIRPed.yaml"
# the sidecar has been seen under both names
CONTRACT_CANDIDATES = ("nirdet-int8.contract.json", "nirdet-int8_contract.json")

# Detection switches itself off if nobody has looked at it for this long
# (page closed, tab left), so it never keeps burning CPU in the background.
IDLE_STOP_SECONDS = 8.0


class _SharedCameraSource:
    """Lets live_nirdet's capture_thread read frames from camera_v2.

    If the camera is momentarily busy (photo being taken, mode switching) it
    just waits and carries on -- it must NOT return None, because None means
    'end of video' to capture_thread and would shut everything down.
    """
    name = "camera_v2 (shared Picamera2, Y plane)"

    def __init__(self, camera, stop_event):
        self._camera = camera
        self._stop = stop_event
        self._n = 0

    def read(self):
        while not self._stop.is_set():
            y = self._camera.get_frame_y()
            if y is not None:
                self._n += 1
                if self._n % 30 == 1:
                    print(f"[detect-debug] camera frame #{self._n}, shape={y.shape}")
                return y
            time.sleep(0.05)
        return None

    def close(self):
        pass


class NIRPersonDetectorService:
    def __init__(self, camera):
        self._camera = camera
        self._lock = threading.Lock()
        self._latest_lock = threading.Lock()
        self._loaded = False
        self.error = _IMPORT_ERROR
        self._stop = threading.Event()
        self._stop.set()
        self._threads = []
        self._enc_thread = None
        self._latest = None
        self._last_seen = 0.0
        self.info = {"fps": 0.0, "confirmed": 0}

    # ------------------------------------------------------------------
    def _load(self):
        """Load + verify the model ONCE. Sets self.error instead of raising."""
        if self._loaded or nd is None:
            return
        try:
            nd.check_omp_threads(nd._DEFAULT_THREADS)
            cfg = nd.get_config()
            nd._apply_profile_lite(cfg, os.path.join(MODEL_DIR, PROFILE_FILE))

            strides = tuple(int(s) for s in cfg.model.strides)
            contract_path = None
            for name in CONTRACT_CANDIDATES:
                p = os.path.join(MODEL_DIR, name)
                if os.path.isfile(p):
                    contract_path = p
                    break
            if contract_path is None:
                raise SystemExit(
                    f"model contract file not found in {MODEL_DIR} "
                    f"(looked for {CONTRACT_CANDIDATES}). Detection stays off "
                    f"until the contract can be verified.")
            nd.verify_contract(nd.load_contract(contract_path), cfg, strides)

            score_thresh = cfg.eval.deploy_score_thresh
            if score_thresh is None:
                raise SystemExit("no deploy_score_thresh in the profile; "
                                 "refusing to invent one.")
            flat = nd.load_flat_field(cfg.aug.flat_field_path)
            self._pp = dict(out_h=int(cfg.data.img_h), out_w=int(cfg.data.img_w),
                            clahe_enabled=bool(cfg.aug.clahe_enabled),
                            clahe_clip=float(cfg.aug.clahe_clip),
                            clahe_grid=int(cfg.aug.clahe_grid),
                            flat_field=flat)
            self._dec = dict(strides=strides, img_h=int(cfg.data.img_h),
                             img_w=int(cfg.data.img_w),
                             score_thresh=float(score_thresh),
                             iou_thresh=float(cfg.model.nms_iou_thresh),
                             max_det=int(cfg.model.max_det))
            self._track_cfg = dict(iou_match=cfg.eval.track_iou_match,
                                   confirm_hits=cfg.eval.track_confirm_hits,
                                   max_missed=cfg.eval.track_max_missed)
            self._engine = nd.NCNNEngine(
                os.path.join(MODEL_DIR, PARAM_FILE),
                os.path.join(MODEL_DIR, BIN_FILE),
                strides, threads=int(nd._DEFAULT_THREADS))
            self._loaded = True
            self.error = None
        except SystemExit as exc:            # live_nirdet reports errors this way
            self.error = str(exc)
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"

    # ------------------------------------------------------------------
    def start(self):
        """Start detecting. Returns True if running, False if it could not."""
        with self._lock:
            self._stop_locked()
            self._load()
            if not self._loaded:
                return False
            print("[detector] Starting shared camera detect mode...", flush=True)
            self._camera.start_detect_mode()
            print("[detector] Shared camera detect mode started.", flush=True)
            self._stop = threading.Event()
            self._latest = None
            self._last_seen = time.time()
            stats = {"n": 0, "dropped": 0, "display_dropped": 0,
                     "t_pre": 0.0, "t_net": 0.0, "t_dec": 0.0}
            self._stats = stats
            self._tracker = nd.IoUTracker(**self._track_cfg)
            cap_q = queue.Queue(maxsize=2)      # same bounded queues as the
            out_q = queue.Queue(maxsize=2)      # tested script: drop, never wait
            src = _SharedCameraSource(self._camera, self._stop)
            t_cap = threading.Thread(
                target=nd.capture_thread,
                args=(src, cap_q, self._stop, stats), daemon=True)
            t_inf = threading.Thread(
                target=nd.inference_thread,
                args=(self._engine, cap_q, out_q, self._stop,
                      self._pp, self._dec, stats), daemon=True)
            t_enc = threading.Thread(
                target=self._encode_loop, args=(out_q, stats), daemon=True)
            self._threads = [t_cap, t_inf, t_enc]
            self._enc_thread = t_enc
            for t in self._threads:
                t.start()
            return True

    def stop(self):
        with self._lock:
            self._stop_locked()

    def _stop_locked(self):
        self._stop.set()
        for t in self._threads:
            if t.is_alive() and t is not threading.current_thread():
                t.join(timeout=3.0)
        self._threads = []
        self._enc_thread = None
        self._camera.stop_detect_mode()

    def is_running(self):
        t = self._enc_thread
        return bool(t is not None and t.is_alive() and not self._stop.is_set())

    def get_latest_jpeg(self):
        """Newest annotated picture (JPEG bytes) or None. Calling this counts
        as 'someone is watching' and keeps detection alive."""
        self._last_seen = time.time()
        with self._latest_lock:
            return self._latest

    def status(self):
        return {"loaded": self._loaded, "running": self.is_running(),
                "error": self.error, **self.info}

    # ------------------------------------------------------------------
    def _encode_loop(self, out_q, stats):
        """Replaces live_nirdet's display_loop: same tracker + same drawing,
        but the result goes to a JPEG for the browser instead of a window."""
        last = time.perf_counter()
        fps = 0.0
        n_empty = 0
        n_items = 0
        try:
            while not self._stop.is_set():
                if time.time() - self._last_seen > IDLE_STOP_SECONDS:
                    break
                try:
                    item = out_q.get(timeout=0.5)
                except queue.Empty:
                    n_empty += 1
                    if n_empty % 10 == 1:
                        print(f"[detect-debug] encode loop: still waiting (empty #{n_empty})")
                    continue
                n_items += 1
                if n_items % 30 == 1:
                    print(f"[detector] Processed {n_items} detection frames.", flush=True)
                if item is nd._STOP:
                    print("[detect-debug] got STOP sentinel")
                    break
                canvas, boxes, scores = item
                tracks = self._tracker.update(boxes, scores)

                now = time.perf_counter()
                dt = now - last
                last = now
                if dt > 0:
                    fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps > 0 else 1.0 / dt

                vis = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
                n_conf = 0
                for t in tracks:
                    if not t.confirmed:
                        continue
                    n_conf += 1
                    x1, y1, x2, y2 = (int(round(v)) for v in t.box)
                    cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(vis, f"PERSON {t.score:.2f}",
                                (x1, max(12, y1 - 4)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1,
                                cv2.LINE_AA)
                cv2.putText(
                    vis,
                    f"FPS {fps:4.1f}   PERSONS {n_conf}",
                    (8, 20),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 220, 255),
                    1,
                    cv2.LINE_AA,
                )

                ok, buf = cv2.imencode(".jpg", vis,
                                       [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ok:
                    with self._latest_lock:
                        self._latest = buf.tobytes()
                    self.info = {"fps": round(fps, 1), "confirmed": n_conf}
        finally:
            self._stop.set()
