"""Hand-tracking virtual camera - run this one file.

    python main.py                  # starts in draw mode
    python main.py --mode objects   # starts in objects mode

Press m (or Tab) in the preview window to switch modes.

Common keys:
  m / Tab = switch mode   d = debug overlay   l = hand skeleton   k = recalibrate
  s = save snapshot   q / Esc = quit   SPACE = skip calibration step
Mode keys are listed in handcam/modes/ (and in the debug bar). See README.md.
"""

import argparse

from handcam.core import run
from handcam.modes import MODES


def main():
    parser = argparse.ArgumentParser(description="Hand-tracking virtual camera")
    parser.add_argument("--mode", choices=[m.name for m in MODES], default=MODES[0].name, help="mode to start in")
    parser.add_argument("--camera", type=int, default=0, help="real webcam index (default 0)")
    parser.add_argument("--device", default="/dev/video10", help="v4l2loopback device for the virtual cam")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--no-preview", action="store_true", help="don't open a preview window")
    parser.add_argument("--no-landmarks", action="store_true", help="start with the hand skeletons hidden")
    parser.add_argument("--no-debug", action="store_true", help="start with the debug overlay hidden")
    parser.add_argument("--calibrate", action="store_true", help="redo calibration even if one is saved")
    run(parser.parse_args(), MODES)


if __name__ == "__main__":
    main()
