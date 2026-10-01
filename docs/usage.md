# Usage

```bash
python main.py [options]
```

## Command-line options

| Option | Default | Description |
|---|---|---|
| `--mode {draw,objects}` | `draw` | Mode to start in |
| `--camera N` | `0` | Real webcam index (`/dev/videoN`) |
| `--device PATH` | `/dev/video10` | Virtual camera device to write to |
| `--width`, `--height` | `1280`, `720` | Capture resolution |
| `--fps` | `30` | Target frame rate |
| `--calibrate` | off | Redo calibration even if one is saved |
| `--no-landmarks` | off | Start with the hand skeleton hidden |
| `--no-debug` | off | Start with the debug overlay hidden |
| `--no-preview` | off | No preview window (keyboard shortcuts are unavailable) |

## Global keys

Keys only work while the **preview window** is focused.

| Key | Action |
|---|---|
| `m` / `Tab` | Switch to the next mode (each mode keeps its state, e.g. your drawing) |
| `d` | Show or hide the debug overlay |
| `l` | Show or hide the hand skeleton |
| `k` | Start calibration again |
| `Space` | Skip the current calibration step (only during calibration) |
| `s` | Save a snapshot PNG to `snapshots/` |
| `q` / `Esc` | Quit |

---

## Calibration

Fingers are detected as "up" or "down" by comparing how far each fingertip is
from the wrist. Everyone's hands differ, so the app measures yours once:

1. **Open hands:** hold up both hands, palms facing the camera, fingers spread.
2. **Fists:** make a fist with both hands.

Each step waits 1.5 seconds for you to get into position, then collects 30
frames per hand. A per-finger threshold is set halfway between your open and
closed readings and saved to `calibration.json`.

- Later runs load the file automatically, and the debug bar shows `calib: loaded`.
- Recalibrate with `k` or `--calibrate` if the lighting or camera position changes a lot.
- Press `Space` to skip a step, for example if you only use one hand. Hands without
  samples keep their previous or default thresholds.
- Delete `calibration.json` to go back to the defaults.

---

## Draw mode

Each hand has its own brush. The right hand starts red and the left starts blue.

| Gesture | Action |
|---|---|
| ☝️ Index finger only | **Draw** |
| ✌️ Index + middle | **Hover**: move without drawing; touch a palette colour to select it |
| 🖐 Open palm (4 fingers) | **Erase** around the palm |
| ✊ Fist / anything else | Pen up |
| ✌️ Hold on **PAUSE** for 0.7 s | Pause or resume drawing |

The palette bar marks which colour each hand is using with **L** and **R**. The
pause button fills orange while you hover on it, then toggles. While paused,
drawing and erasing are disabled but you can still pick colours.

| Key | Action |
|---|---|
| `1`–`8` | Set the right hand colour |
| `Shift` + `1`–`8` | Set the left hand colour |
| `p` / `Space` | Pause or resume drawing |
| `c` | Clear the drawing |

---

## Objects mode

Five shapes start on screen: ball, square, triangle, hexagon and star.

| Gesture | Action |
|---|---|
| 🤏 Pinch (thumb tip + index tip) on a shape | **Grab** it; it gets a shadow and comes to the front |
| Move while pinching | **Carry** it |
| Open the pinch while moving | **Throw**: it keeps your hand's speed and bounces off the edges |
| 🤏🤏 Pinch the same shape with **both** hands | Pull apart or together to **resize**, twist to **rotate** |

A shape gets a white outline when your pinch point is over it, before you
grab. The cursor is a ring when open and a solid green dot while pinching.

| Key | Action |
|---|---|
| `n` | Add a random shape |
| `c` | Reset the shapes |
| `g` | Turn gravity on or off |

---

## Debug overlay

Turned on and off with `d`. It shows:

- **Line 1:** FPS, current mode, calibration status, and mode status (paused, object count, gravity).
- **Line 2:** Available keys.
- **One line per hand:** detection confidence, mode-specific state, and each finger as
  `I:1.80/1.40+`, which means the reading, then the threshold, then `+` for up or `-` for down
  (I = index, M = middle, R = ring, P = pinky).
  - Draw mode adds the gesture (`DRAW` / `HOVER` / `ERASE` / `IDLE`) and colour.
  - Objects mode adds the pinch reading, e.g. `pinch 0.22 (<0.35)`, and `HOLD <shape>` / `PINCH` / `open`.

The current gesture is also written next to each fingertip.
