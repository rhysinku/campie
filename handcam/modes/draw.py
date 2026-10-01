"""Air drawing mode.

Gestures (per hand, each hand has its own brush):
  - Index finger up only        -> draw
  - Index + middle fingers up   -> hover; touch the palette bar at the top to pick a color
  - Open palm (4 fingers up)    -> erase around the palm
  - Anything else (e.g. fist)   -> pen up
  - Hover over the PAUSE button (top right) for a moment to stop / resume drawing

Keys: 1-8 = right hand color, Shift+1-8 (!@#$%^&*) = left hand color,
      p / SPACE = pause, c = clear
"""

import time

import cv2
import numpy as np

from handcam.core import FONT, Mode

PALETTE = [
    ("red", (0, 0, 255)),
    ("orange", (0, 140, 255)),
    ("yellow", (0, 230, 255)),
    ("green", (0, 200, 0)),
    ("cyan", (255, 220, 0)),
    ("blue", (255, 80, 0)),
    ("purple", (200, 0, 160)),
    ("white", (255, 255, 255)),
]
PALETTE_HEIGHT = 70
BUTTON_WIDTH = 170  # pause button at the right end of the palette bar
BUTTON_DWELL = 0.7  # seconds to hover on the button before it toggles
BRUSH_SIZE = 8
ERASER_SIZE = 60
SHIFT_DIGITS = "!@#$%^&*"


def classify(up):
    index, middle, ring, pinky = up
    if index and middle and ring and pinky:
        return "ERASE"
    if index and middle and not ring:
        return "HOVER"
    if index and not middle and not ring:
        return "DRAW"
    return "IDLE"


def merge(frame, canvas):
    gray = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)
    mask_inv = cv2.bitwise_not(mask)
    bg = cv2.bitwise_and(frame, frame, mask=mask_inv)
    fg = cv2.bitwise_and(canvas, canvas, mask=mask)
    return cv2.add(bg, fg)


class Brush:
    def __init__(self, color_idx):
        self.color_idx = color_idx
        self.mode = "IDLE"
        self.prev_point = None
        self.button_since = None  # when this hand started hovering the pause button
        self.button_fired = False

    @property
    def color(self):
        return PALETTE[self.color_idx][1]


class DrawMode(Mode):
    name = "draw"
    keys_help = "| [c]lear [p]ause 1-8 / Shift+1-8 colors"
    ui_top = PALETTE_HEIGHT

    def __init__(self, w, h):
        super().__init__(w, h)
        self.canvas = np.zeros((h, w, 3), dtype=np.uint8)
        self.brushes = {"Left": Brush(5), "Right": Brush(0)}
        self.paused = False
        self.cursors = []

    def reset_hands(self):
        for brush in self.brushes.values():
            brush.prev_point = None
            brush.button_since = None
            brush.mode = "IDLE"

    def palette_index_at(self, x):
        return min(max(x * len(PALETTE) // (self.w - BUTTON_WIDTH), 0), len(PALETTE) - 1)

    def update_pause_button(self, brush, tip):
        """Return True when this hand has hovered on the pause button long enough."""
        if tip[1] < PALETTE_HEIGHT and tip[0] >= self.w - BUTTON_WIDTH:
            if brush.button_since is None:
                brush.button_since = time.time()
            if not brush.button_fired and time.time() - brush.button_since >= BUTTON_DWELL:
                brush.button_fired = True
                return True
        else:
            brush.button_since = None
            brush.button_fired = False
        return False

    def update(self, hands):
        self.cursors = []
        for label, hand in hands.items():
            brush = self.brushes[label]
            if not hand.present:
                brush.prev_point = None
                brush.mode = "IDLE"
                continue
            if not hand.visible:
                continue  # briefly lost: keep the stroke so it reconnects

            tip = hand.smooth("tip", hand.pts[8])
            mode = brush.mode = hand.stable("gesture", classify(hand.up))

            if mode == "HOVER" and self.update_pause_button(brush, tip):
                self.paused = not self.paused
            elif mode != "HOVER":
                brush.button_since = None
                brush.button_fired = False

            if self.paused and mode in ("DRAW", "ERASE"):
                brush.prev_point = None
                self.cursors.append(("PAUSED", tip, brush))
            elif mode == "ERASE":
                palm = hand.point(9)
                cv2.circle(self.canvas, palm, ERASER_SIZE, (0, 0, 0), -1)
                self.cursors.append((mode, palm, brush))
                brush.prev_point = None
            elif mode == "HOVER":
                if tip[1] < PALETTE_HEIGHT and tip[0] < self.w - BUTTON_WIDTH:
                    brush.color_idx = self.palette_index_at(tip[0])
                self.cursors.append((mode, tip, brush))
                brush.prev_point = None
            elif mode == "DRAW":
                if tip[1] > PALETTE_HEIGHT:
                    if brush.prev_point is not None:
                        cv2.line(self.canvas, brush.prev_point, tip, brush.color, BRUSH_SIZE, cv2.LINE_AA)
                    brush.prev_point = tip
                else:
                    brush.prev_point = None
                self.cursors.append((mode, tip, brush))
            else:
                brush.prev_point = None
                self.cursors.append((mode, tip, brush))

    def draw_scene(self, frame):
        return merge(frame, self.canvas)

    def draw_ui(self, frame, show_debug):
        self.draw_palette(frame)
        for mode, pt, brush in self.cursors:
            if mode == "ERASE":
                cv2.circle(frame, pt, ERASER_SIZE, (200, 200, 200), 2)
            elif mode == "HOVER":
                cv2.circle(frame, pt, BRUSH_SIZE + 6, brush.color, 2)
            elif mode == "DRAW":
                cv2.circle(frame, pt, BRUSH_SIZE, brush.color, -1)
            elif mode == "PAUSED":
                cv2.circle(frame, pt, BRUSH_SIZE + 6, (160, 160, 160), 2)
            if show_debug:
                cv2.putText(frame, mode, (pt[0] + 14, pt[1] - 14), FONT, 0.5, (255, 255, 255), 2, cv2.LINE_AA)
        if self.paused:
            cv2.putText(frame, "DRAWING PAUSED", (self.w // 2 - 150, self.h - 30), FONT, 1.0, (0, 0, 255), 3, cv2.LINE_AA)

    def draw_palette(self, frame):
        w = self.w
        box_w = (w - BUTTON_WIDTH) // len(PALETTE)
        for i, (_, color) in enumerate(PALETTE):
            x0 = i * box_w
            x1 = w - BUTTON_WIDTH if i == len(PALETTE) - 1 else x0 + box_w
            cv2.rectangle(frame, (x0, 0), (x1, PALETTE_HEIGHT), color, -1)
            cv2.putText(frame, str(i + 1), (x0 + box_w // 2 - 6, PALETTE_HEIGHT // 2 + 8), FONT, 0.6, (60, 60, 60), 1)
            # Mark which hand currently uses this color
            if self.brushes["Left"].color_idx == i:
                cv2.putText(frame, "L", (x0 + 8, 24), FONT, 0.7, (0, 0, 0), 2)
            if self.brushes["Right"].color_idx == i:
                cv2.putText(frame, "R", (x1 - 24, PALETTE_HEIGHT - 10), FONT, 0.7, (0, 0, 0), 2)
        self.draw_pause_button(frame)
        cv2.rectangle(frame, (0, 0), (w, PALETTE_HEIGHT), (40, 40, 40), 2)

    def draw_pause_button(self, frame):
        w = self.w
        x0 = w - BUTTON_WIDTH
        cv2.rectangle(frame, (x0, 0), (w, PALETTE_HEIGHT), (0, 0, 170) if self.paused else (50, 50, 50), -1)
        # Dwell progress fills the button from the bottom
        since = [b.button_since for b in self.brushes.values() if b.button_since is not None and not b.button_fired]
        if since:
            p = min((time.time() - min(since)) / BUTTON_DWELL, 1)
            cv2.rectangle(frame, (x0, int(PALETTE_HEIGHT * (1 - p))), (w, PALETTE_HEIGHT), (0, 160, 255), -1)
        label = "RESUME" if self.paused else "PAUSE"
        cv2.putText(frame, label, (x0 + 22, PALETTE_HEIGHT // 2 + 10), FONT, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.line(frame, (x0, 0), (x0, PALETTE_HEIGHT), (40, 40, 40), 2)

    def on_key(self, key):
        if key == ord("c"):
            self.canvas[:] = 0
        elif key in (ord("p"), ord(" ")):
            self.paused = not self.paused
        elif ord("1") <= key <= ord(str(len(PALETTE))):
            self.brushes["Right"].color_idx = key - ord("1")
        elif chr(key) in SHIFT_DIGITS[:len(PALETTE)]:
            self.brushes["Left"].color_idx = SHIFT_DIGITS.index(chr(key))
        else:
            return False
        return True

    def status(self):
        return "PAUSED" if self.paused else ""

    def hand_debug(self, hand):
        brush = self.brushes[hand.label]
        return f"{brush.mode:5}  {PALETTE[brush.color_idx][0]}"

    def hand_color(self, label):
        return self.brushes[label].color
