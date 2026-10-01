"""Shared pieces for every hand-tracking mode.

Camera + virtual cam loop, hand tracking with smoothing / debouncing,
finger calibration, hand skeleton and debug overlay. A mode only has to
implement the `Mode` interface below.
"""

import json
import os
import time

os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import cv2  # noqa: E402
import mediapipe as mp  # noqa: E402
import numpy as np  # noqa: E402
import pyvirtualcam  # noqa: E402

SMOOTHING = 0.5  # 0 = no smoothing, closer to 1 = smoother but laggier
SKELETON_OPACITY = 0.35  # 0 = invisible, 1 = solid
STABLE_FRAMES = 3  # frames a gesture must hold before it counts
LOST_GRACE = 6  # frames a hand may vanish before we treat it as gone

FINGER_TIPS = [8, 12, 16, 20]
FINGER_MCPS = [5, 9, 13, 17]
FINGER_NAMES = ["I", "M", "R", "P"]
DEFAULT_THRESHOLD = 1.35
HANDS = ("Left", "Right")
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALIBRATION_FILE = os.path.join(PROJECT_DIR, "calibration.json")
SNAPSHOT_DIR = os.path.join(PROJECT_DIR, "snapshots")

FONT = cv2.FONT_HERSHEY_SIMPLEX


# ---------------------------------------------------------------- hand math

def finger_ratios(pts):
    """Tip-to-wrist distance divided by knuckle-to-wrist distance, per finger.

    Roughly 1.0 when the finger is curled and ~1.8 when straight, regardless of
    how the hand is rotated.
    """
    wrist = pts[0]
    return [
        float(np.linalg.norm(pts[tip] - wrist) / max(np.linalg.norm(pts[mcp] - wrist), 1e-6))
        for tip, mcp in zip(FINGER_TIPS, FINGER_MCPS)
    ]


def hand_size(pts):
    """Wrist to middle knuckle, in pixels - a scale reference for the hand."""
    return max(float(np.linalg.norm(pts[9] - pts[0])), 1e-6)


def pinch_ratio(pts):
    """Thumb tip to index tip distance relative to hand size (small = pinching)."""
    return float(np.linalg.norm(pts[4] - pts[8])) / hand_size(pts)


class Hand:
    """One tracked hand (Left or Right), persistent across frames."""

    def __init__(self, label):
        self.label = label
        self.lost = LOST_GRACE + 1
        self.reset()

    def reset(self):
        self.landmarks = None
        self.pts = None  # 21x2 pixel coordinates
        self.score = 0.0
        self.ratios = None
        self.up = None
        self._smooth = {}
        self._stable = {}

    @property
    def visible(self):
        """Detected in this frame."""
        return self.lost == 0

    @property
    def present(self):
        """Detected recently enough that we keep its state (strokes, grips)."""
        return self.lost <= LOST_GRACE

    def update(self, landmarks, score, w, h, thresholds):
        self.lost = 0
        self.landmarks = landmarks
        self.score = score
        self.pts = np.array([(p.x * w, p.y * h) for p in landmarks.landmark], dtype=np.float32)
        self.ratios = finger_ratios(self.pts)
        self.up = [r > t for r, t in zip(self.ratios, thresholds)]

    def mark_lost(self):
        self.lost += 1
        if self.lost == LOST_GRACE + 1:
            self.reset()

    def point(self, i):
        return tuple(int(v) for v in self.pts[i])

    def smooth(self, name, point):
        """Exponentially smoothed version of a point, tracked under `name`."""
        point = np.array(point, dtype=np.float32)
        prev = self._smooth.get(name)
        cur = point if prev is None else SMOOTHING * prev + (1 - SMOOTHING) * point
        self._smooth[name] = cur
        return tuple(int(v) for v in cur)

    def stable(self, name, raw, default="IDLE"):
        """Debounced value: `raw` must repeat STABLE_FRAMES times before it sticks."""
        cur, cand, n = self._stable.get(name, (default, default, 0))
        if raw == cand:
            n += 1
        else:
            cand, n = raw, 1
        if n >= STABLE_FRAMES:
            cur = raw
        self._stable[name] = (cur, cand, n)
        return cur


# ---------------------------------------------------------------- calibration

class Calibration:
    STEPS = [
        ("OPEN HANDS", "Hold up BOTH hands, palms facing the camera, fingers spread"),
        ("FISTS", "Now make a FIST with both hands"),
    ]
    SAMPLES = 30
    GET_READY = 1.5  # seconds before samples are collected for a step

    def __init__(self):
        self.thresholds = {hand: [DEFAULT_THRESHOLD] * 4 for hand in HANDS}
        self.status = "defaults"
        self.active = False
        self.load()

    def load(self):
        try:
            with open(CALIBRATION_FILE) as f:
                data = json.load(f)
            for hand in HANDS:
                if hand in data and len(data[hand]) == 4:
                    self.thresholds[hand] = [float(v) for v in data[hand]]
            self.status = "loaded"
            return True
        except (OSError, ValueError):
            return False

    def save(self):
        with open(CALIBRATION_FILE, "w") as f:
            json.dump(self.thresholds, f, indent=2)

    def start(self):
        self.active = True
        self.step = 0
        self.step_started = time.time()
        self.samples = [{hand: [] for hand in HANDS} for _ in self.STEPS]

    @property
    def collecting(self):
        return self.active and time.time() - self.step_started >= self.GET_READY

    def add(self, hand, ratios):
        bucket = self.samples[self.step][hand]
        if self.collecting and len(bucket) < self.SAMPLES:
            bucket.append(ratios)

    def progress(self, hand):
        return len(self.samples[self.step][hand]) / self.SAMPLES

    def tick(self):
        if self.active and all(self.progress(hand) >= 1 for hand in HANDS):
            self.next_step()

    def next_step(self):
        self.step += 1
        self.step_started = time.time()
        if self.step >= len(self.STEPS):
            self.finish()

    def finish(self):
        self.active = False
        updated = []
        for hand in HANDS:
            open_s, fist_s = self.samples[0][hand], self.samples[1][hand]
            if len(open_s) < 5 or len(fist_s) < 5:
                continue
            open_med = np.median(open_s, axis=0)
            fist_med = np.median(fist_s, axis=0)
            thr = []
            for o, c, old in zip(open_med, fist_med, self.thresholds[hand]):
                # Midpoint between open and closed; ignore nonsense samples
                thr.append(float((o + c) / 2) if o - c > 0.2 else old)
            self.thresholds[hand] = thr
            updated.append(hand)
        if updated:
            self.save()
            self.status = "calibrated " + "+".join(updated)
        print(f"Calibration: {self.status}  thresholds={self.thresholds}")


# ---------------------------------------------------------------- drawing helpers

def shade(frame, x0, y0, x1, y1, alpha=0.6):
    roi = frame[y0:y1, x0:x1]
    frame[y0:y1, x0:x1] = (roi * (1 - alpha)).astype(np.uint8)


def draw_skeletons(frame, hands):
    if not hands:
        return
    overlay = frame.copy()
    for hand in hands:
        mp.solutions.drawing_utils.draw_landmarks(
            overlay, hand.landmarks, mp.solutions.hands.HAND_CONNECTIONS,
            mp.solutions.drawing_styles.get_default_hand_landmarks_style(),
            mp.solutions.drawing_styles.get_default_hand_connections_style())
    cv2.addWeighted(overlay, SKELETON_OPACITY, frame, 1 - SKELETON_OPACITY, 0, dst=frame)


def draw_debug(frame, fps, mode, calib, hands):
    w = frame.shape[1]
    y0, line_h = mode.ui_top, 24
    shade(frame, 0, y0, w, y0 + line_h * 4 + 10)
    extra = mode.status()
    cv2.putText(frame, f"FPS {fps:4.1f}   mode: {mode.name}   calib: {calib.status}" + (f"   {extra}" if extra else ""),
                (10, y0 + line_h), FONT, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(frame, "[m]ode [d]ebug [l]andmarks [k] recalibrate [s]ave [q]uit   " + mode.keys_help,
                (10, y0 + line_h * 2), FONT, 0.5, (200, 200, 200), 1, cv2.LINE_AA)
    for row, label in enumerate(("Right", "Left"), start=3):
        hand = hands[label]
        y = y0 + line_h * row
        if hand.ratios is None:
            cv2.putText(frame, f"{label:5}  not detected", (10, y), FONT, 0.55, (150, 150, 150), 1, cv2.LINE_AA)
            continue
        fingers = " ".join(
            f"{n}:{r:.2f}/{t:.2f}{'+' if u else '-'}"
            for n, r, t, u in zip(FINGER_NAMES, hand.ratios, calib.thresholds[label], hand.up)
        )
        text = f"{label:5}  conf {hand.score:.2f}  {mode.hand_debug(hand)}   {fingers}"
        cv2.putText(frame, text, (10, y), FONT, 0.55, mode.hand_color(label), 1, cv2.LINE_AA)


def draw_calibration(frame, calib):
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = w // 2 - 380, h // 2 - 110, w // 2 + 380, h // 2 + 110
    shade(frame, x0, y0, x1, y1, 0.75)
    title, hint = calib.STEPS[calib.step]
    cv2.putText(frame, f"CALIBRATION {calib.step + 1}/{len(calib.STEPS)}: {title}",
                (x0 + 20, y0 + 40), FONT, 0.9, (0, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(frame, hint, (x0 + 20, y0 + 75), FONT, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
    if not calib.collecting:
        left = calib.GET_READY - (time.time() - calib.step_started)
        cv2.putText(frame, f"get ready... {left:.1f}", (x0 + 20, y0 + 110), FONT, 0.7, (0, 200, 255), 2, cv2.LINE_AA)
    for i, hand in enumerate(HANDS):
        by = y0 + 130 + i * 30
        p = calib.progress(hand)
        cv2.putText(frame, hand, (x0 + 20, by + 16), FONT, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.rectangle(frame, (x0 + 100, by), (x1 - 20, by + 20), (120, 120, 120), 1)
        cv2.rectangle(frame, (x0 + 100, by), (x0 + 100 + int((x1 - 120 - x0) * p), by + 20), (0, 220, 0), -1)
    cv2.putText(frame, "SPACE = skip this step (e.g. if you only use one hand)",
                (x0 + 20, y1 - 12), FONT, 0.5, (180, 180, 180), 1, cv2.LINE_AA)


# ---------------------------------------------------------------- modes

class Mode:
    """Base class for an interactive mode. Override what you need."""

    name = "base"
    keys_help = ""
    ui_top = 0  # y where the debug panel starts (below the mode's own top bar)

    def __init__(self, w, h):
        self.w, self.h = w, h

    def update(self, hands):
        """Handle input. `hands` maps "Left"/"Right" to Hand."""

    def draw_scene(self, frame):
        """Return the frame with the mode's content (under the skeleton)."""
        return frame

    def draw_ui(self, frame, show_debug):
        """Draw UI on top of the skeleton (bars, cursors)."""

    def on_key(self, key):
        """Handle a key press. Return True if used."""
        return False

    def reset_hands(self):
        """Called when switching away from / back to this mode."""

    def status(self):
        return ""

    def hand_debug(self, hand):
        return ""

    def hand_color(self, label):
        return (255, 255, 255)


# ---------------------------------------------------------------- main loop

def open_camera(args):
    cap = cv2.VideoCapture(args.camera, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)
    ok, frame = cap.read()
    if not ok:
        raise SystemExit(f"Could not read from camera {args.camera} (is another app using it?)")
    return cap, frame.shape[1], frame.shape[0]


def run(args, mode_classes):
    cap, w, h = open_camera(args)
    print(f"Camera {args.camera}: {w}x{h}")

    modes = [cls(w, h) for cls in mode_classes]
    current = next(i for i, m in enumerate(modes) if m.name == args.mode)
    hands = {label: Hand(label) for label in HANDS}
    calib = Calibration()
    if args.calibrate or calib.status != "loaded":
        calib.start()
    show_debug = not args.no_debug
    show_landmarks = not args.no_landmarks

    tracker = mp.solutions.hands.Hands(
        max_num_hands=2,
        model_complexity=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.6,
    )

    fps, last = 0.0, time.time()
    with pyvirtualcam.Camera(width=w, height=h, fps=args.fps, device=args.device,
                             fmt=pyvirtualcam.PixelFormat.BGR) as vcam:
        print(f"Virtual camera running on {vcam.device} - pick it in Discord/Zoom/Meet/OBS.")
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame = cv2.flip(frame, 1)  # mirror so it feels natural

            now = time.time()
            fps = 0.9 * fps + 0.1 * (1 / max(now - last, 1e-6))
            last = now

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            result = tracker.process(rgb)

            seen = set()
            if result.multi_hand_landmarks:
                for lm, handed in zip(result.multi_hand_landmarks, result.multi_handedness):
                    label = handed.classification[0].label
                    if label in seen:  # both detected as same side; skip duplicate
                        continue
                    seen.add(label)
                    hands[label].update(lm, handed.classification[0].score, w, h, calib.thresholds[label])
            for label, hand in hands.items():
                if label not in seen:
                    hand.mark_lost()

            mode = modes[current]
            if calib.active:
                for hand in hands.values():
                    if hand.visible:
                        calib.add(hand.label, hand.ratios)
                calib.tick()
            else:
                mode.update(hands)

            out = mode.draw_scene(frame)
            if show_landmarks or calib.active:
                draw_skeletons(out, [hand for hand in hands.values() if hand.visible])
            mode.draw_ui(out, show_debug)
            if show_debug:
                draw_debug(out, fps, mode, calib, hands)
            if calib.active:
                draw_calibration(out, calib)

            vcam.send(out)

            if args.no_preview:
                vcam.sleep_until_next_frame()
                continue
            cv2.imshow("Hand Cam (preview)", out)
            key = cv2.waitKey(1) & 0xFF
            if key == 255:
                continue
            if key in (ord("q"), 27):
                break
            elif key in (ord("m"), 9):  # m or Tab
                mode.reset_hands()
                current = (current + 1) % len(modes)
                modes[current].reset_hands()
                print(f"Mode: {modes[current].name}")
            elif key == ord("d"):
                show_debug = not show_debug
            elif key == ord("l"):
                show_landmarks = not show_landmarks
            elif key == ord("k"):
                calib.start()
            elif key == ord(" ") and calib.active:
                calib.next_step()
            elif key == ord("s"):
                os.makedirs(SNAPSHOT_DIR, exist_ok=True)
                name = os.path.join(SNAPSHOT_DIR, time.strftime("snapshot_%Y%m%d_%H%M%S.png"))
                cv2.imwrite(name, out)
                print(f"Saved {name}")
            else:
                mode.on_key(key)

    cap.release()
    tracker.close()
    cv2.destroyAllWindows()
