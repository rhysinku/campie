# Hand Cam

A Python virtual webcam that tracks **both of your hands** and lets you interact
with the video using gestures: draw in the air, or pick up and throw virtual
objects. The result is sent to a virtual camera, so Discord, Zoom, Google Meet,
OBS, and so on can use it like a normal webcam.

```
real webcam ──► OpenCV ──► MediaPipe Hands ──► mode (draw / objects) ──► pyvirtualcam ──► /dev/video10 ──► Discord
```

## Features

- **Two hands at once**: each hand has its own brush or grip.
- **Draw mode**: draw with your index finger, pick colours from the on-screen
  palette, erase with an open palm, and pause with an on-screen button.
- **Objects mode**: pinch to grab shapes, move and throw them, or resize and
  rotate them with both hands. Gravity is optional.
- **Calibration**: learns your open hand and fist once, then saves it to
  `calibration.json`.
- **Hand skeleton overlay**: see-through and on by default.
- **Debug overlay**: shows FPS, the current gesture, and live per-finger readings.
- **Pluggable modes**: add a new mode by writing one class.

## Quick start

```bash
git clone https://github.com/rhysinku/campie.git
cd campie
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python main.py                  # draw mode
python main.py --mode objects   # objects mode
```

Then in Discord go to **User Settings → Voice & Video → Camera** and choose
**ItsGiving**. The first run asks you to calibrate: show open hands, then fists.

> The virtual camera driver (`v4l2loopback`) must be loaded first, and no other
> app may be using your real webcam. See [docs/setup.md](docs/setup.md).

## Controls at a glance

| Key | Action |
|---|---|
| `m` / `Tab` | Switch mode |
| `d` | Show or hide the debug overlay |
| `l` | Show or hide the hand skeleton |
| `k` | Recalibrate |
| `s` | Save a snapshot to `snapshots/` |
| `q` / `Esc` | Quit |

Keys only work while the **preview window** is focused. Gestures and mode-specific
keys are in [docs/usage.md](docs/usage.md).

## Project structure

```
campie/
├── main.py                 # entry point: run this
├── requirements.txt
├── calibration.json        # created by calibration (per user, not committed)
├── snapshots/              # created when you press `s`
├── handcam/
│   ├── __init__.py
│   ├── core.py             # camera, virtual cam, tracking, calibration, overlays, main loop
│   └── modes/
│       ├── __init__.py     # MODES list: register new modes here
│       ├── draw.py         # air drawing mode
│       └── objects.py      # virtual objects mode
└── docs/
    ├── setup.md            # install, virtual camera driver, Discord
    ├── usage.md            # modes, gestures, keys, options, calibration
    ├── architecture.md     # how it works, adding a new mode, tuning
    └── troubleshooting.md  # common problems
```

## Documentation

- [Setup](docs/setup.md): dependencies, `v4l2loopback`, using it in Discord
- [Usage](docs/usage.md): gestures, keys, command-line options, calibration
- [Architecture](docs/architecture.md): code layout, frame pipeline, writing a new mode, tuning constants
- [Troubleshooting](docs/troubleshooting.md): camera busy, missing modules, tracking issues

## Requirements

- Linux with `v4l2loopback` (tested on Ubuntu 24.04, Python 3.12)
- A webcam
- `opencv-python`, `mediapipe` (0.10.21, which uses the `mp.solutions` API), `pyvirtualcam`, `numpy<2`
