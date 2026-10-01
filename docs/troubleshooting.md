# Troubleshooting

### `ModuleNotFoundError: No module named 'cv2'`

You are using the system Python instead of the project's virtual environment.

```bash
source venv/bin/activate      # then: python main.py
# or
./venv/bin/python main.py
```

### `Could not read from camera 0 (is another app using it?)`

Another app has the real webcam open. Find out which:

```bash
fuser /dev/video0
ps -o pid,cmd -p <pid>
```

Turn the camera off in that app (Discord, Firefox/Chrome tabs, OBS), or switch
Discord's camera to **ItsGiving**. If you have several webcams, try `--camera 1`.

### `error: unrecognized arguments`

Check for typos or stray punctuation, e.g. `--calibrate.` (with a full stop)
is not the same as `--calibrate`. Run `python main.py --help` to list the options.

### "ItsGiving" doesn't show up in Discord

- Start Hand Cam **first**, then open Discord's camera list.
- The module must be loaded with `exclusive_caps=1`. Check with
  `cat /sys/module/v4l2loopback/parameters/exclusive_caps` (first value should be `Y`).
- Fully quit Discord, including from the tray, and reopen it.

See [setup.md](setup.md#2-virtual-camera-driver-v4l2loopback).

### pyvirtualcam error about the device

The virtual camera module isn't loaded, or it is at a different number.
List the devices:

```bash
for d in /sys/class/video4linux/*; do echo "$d: $(cat $d/name)"; done
```

Then load the module (see setup), or pass the right device with `--device /dev/videoN`.

### Lines are broken or gestures flicker

- Turn on the debug overlay (`d`) and watch the finger readings. If a finger
  hovers around its threshold, recalibrate (`k`).
- Improve the lighting and keep your whole hand in view. Tracking struggles
  in dim light and when the hand is at the edge of the frame.
- Increase `STABLE_FRAMES` or `LOST_GRACE` in `handcam/core.py`.

### Grabbing objects is too hard or too easy

Watch `pinch 0.xx` in the debug bar while you pinch and release. Then adjust
`PINCH_ON` (grab) and `PINCH_OFF` (release) in `handcam/modes/objects.py`.

### Left and right hands are swapped

The frame is mirrored before tracking so the labels match your real hands.
If your camera already mirrors its image, remove the `cv2.flip(frame, 1)` line
in `handcam/core.py`.

### Keys do nothing

Click the **preview window** first; keys are read from that window only.
With `--no-preview` there are no keyboard shortcuts.

### Low FPS

Lower the resolution (`--width 960 --height 540`), or set `model_complexity=0`
in `handcam/core.py` for a faster but less precise hand model.
