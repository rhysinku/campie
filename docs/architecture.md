# Architecture

## Layout

| File | Responsibility |
|---|---|
| `main.py` | Parses command-line options and calls `handcam.core.run()` with the registered modes |
| `handcam/core.py` | Everything shared: camera, virtual camera, MediaPipe tracking, `Hand` state, `Calibration`, skeleton and debug overlays, key handling, the `Mode` base class |
| `handcam/modes/__init__.py` | `MODES` list, which sets the order `m` cycles through and the default mode |
| `handcam/modes/draw.py` | `DrawMode`: canvas, palette, pause button, draw/hover/erase gestures |
| `handcam/modes/objects.py` | `ObjectsMode`: shapes, pinch grab, two-hand resize/rotate, throw physics |

## Frame pipeline

Each frame in `core.run()`:

1. **Capture** a frame from the webcam and mirror it, so moving your hand right moves it right on screen.
2. **Track**: MediaPipe Hands returns up to 2 hands with 21 landmarks each, labelled `Left` / `Right`.
3. **Update hands**: each `Hand` gets pixel coordinates, finger ratios and up/down flags.
   Hands not seen this frame are marked lost.
4. **Calibration or mode**: during calibration, finger ratios are collected.
   Otherwise `mode.update(hands)` handles the input.
5. **Render**, in layers:
   1. `mode.draw_scene(frame)`: the content (drawing canvas or shapes)
   2. The hand skeleton (see-through)
   3. `mode.draw_ui(frame, show_debug)`: bars, buttons, cursors
   4. The debug overlay
   5. The calibration dialog
6. **Output**: the frame is sent to the virtual camera and shown in the preview.
7. **Keys**: global keys are handled in core, and everything else goes to `mode.on_key()`.

## Hand tracking helpers (`core.py`)

**`finger_ratios(pts)`**: for each finger, the tip-to-wrist distance divided by the
knuckle-to-wrist distance. It is about 1.0 when curled and about 1.8 when straight.
Because it is a ratio of distances, it works at any hand angle or distance from
the camera.

**`pinch_ratio(pts)`**: the thumb-tip to index-tip distance divided by hand size
(wrist to middle knuckle).

**`Hand`**: persistent per-hand state:

| Member | Meaning |
|---|---|
| `pts` | 21×2 landmark pixel coordinates |
| `ratios`, `up` | Finger ratios and calibrated up/down flags |
| `visible` | Detected this frame |
| `present` | Detected within the last `LOST_GRACE` frames; use it to keep strokes or grips alive through brief tracking drop-outs |
| `smooth(name, point)` | Exponential smoothing of any point, tracked separately per `name` |
| `stable(name, raw)` | Debounced value: `raw` must repeat `STABLE_FRAMES` times before it is returned |
| `point(i)` | Landmark `i` as an integer tuple |

### MediaPipe landmark indices

```
0 wrist
1-4   thumb   (4 = tip)
5-8   index   (5 = knuckle, 8 = tip)
9-12  middle  (9 = knuckle, 12 = tip)
13-16 ring
17-20 pinky
```

## Adding a new mode

1. Create `handcam/modes/mymode.py`:

```python
import cv2

from handcam.core import FONT, Mode


class MyMode(Mode):
    name = "mymode"                 # used by --mode and shown in the debug bar
    keys_help = "| [x] do something"
    ui_top = 0                      # y where the debug panel starts (below your own top bar)

    def update(self, hands):
        for label, hand in hands.items():
            if not hand.visible:
                continue
            self.tip = hand.smooth("tip", hand.pts[8])

    def draw_scene(self, frame):
        return frame                # content drawn under the skeleton

    def draw_ui(self, frame, show_debug):
        cv2.putText(frame, "hello", (20, 60), FONT, 1, (255, 255, 255), 2)

    def on_key(self, key):
        return key == ord("x")      # True if handled

    def reset_hands(self):
        pass                        # drop grips/strokes when switching modes

    def hand_debug(self, hand):
        return "my state"           # shown on the hand's debug line
```

2. Register it in `handcam/modes/__init__.py`:

```python
from handcam.modes.mymode import MyMode

MODES = [DrawMode, ObjectsMode, MyMode]
```

That's it: `--mode mymode` works and `m` cycles to it. The calibration, skeleton,
debug overlay and virtual camera come from core.

Avoid giving your mode keys that core already uses: `m`, `Tab`, `d`, `l`, `k`, `s`, `q` and `Esc`.

## Tuning constants

| Constant | File | Default | Effect |
|---|---|---|---|
| `SMOOTHING` | core | `0.5` | Higher is steadier but adds lag |
| `SKELETON_OPACITY` | core | `0.35` | Skeleton visibility (0 to 1) |
| `STABLE_FRAMES` | core | `3` | Frames a gesture must hold before it counts |
| `LOST_GRACE` | core | `6` | Frames a hand may vanish before strokes or grips are dropped |
| `DEFAULT_THRESHOLD` | core | `1.35` | Finger-up threshold before calibration |
| `BRUSH_SIZE`, `ERASER_SIZE` | draw | `8`, `60` | Pixels |
| `BUTTON_DWELL` | draw | `0.7` | Seconds to hover on PAUSE |
| `PINCH_ON`, `PINCH_OFF` | objects | `0.35`, `0.50` | Grab and release thresholds; the gap between them stops flicker |
| `GRAB_MARGIN` | objects | `25` | Extra pixels around a shape that still count as grabbing it |
| `FRICTION`, `GRAVITY`, `BOUNCE` | objects | `0.93`, `1.5`, `0.6` | Physics feel |
| `MAX_THROW` | objects | `60` | Throw speed cap (px/frame) |
