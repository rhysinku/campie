"""Virtual objects mode: pick up, move, throw, resize and rotate shapes.

Gestures:
  - Pinch (thumb tip + index tip together) on an object -> grab it
  - Move while pinching                                  -> carry it
  - Open the pinch                                       -> drop it (it keeps your hand's speed, so you can throw)
  - Pinch the same object with BOTH hands                -> pull apart / together to resize, twist to rotate

Keys: n = new object, c = reset objects, g = toggle gravity
"""

import math
import random
from collections import deque

import cv2
import numpy as np

from handcam.core import FONT, Mode, pinch_ratio

PINCH_ON = 0.35  # pinch ratio below this grabs ...
PINCH_OFF = 0.50  # ... and above this releases (gap avoids flicker)
GRAB_MARGIN = 25  # px of slack around an object when grabbing
FRICTION = 0.93  # velocity kept per frame when floating
AIR_FRICTION = 0.995  # velocity kept per frame with gravity on
GRAVITY = 1.5  # px / frame^2
BOUNCE = 0.6  # velocity kept when hitting a wall
MAX_THROW = 60  # px / frame
MIN_SIZE, MAX_SIZE = 20, 300
SHADOW_OPACITY = 0.35

COLORS = [(60, 60, 230), (230, 140, 40), (40, 210, 240), (80, 200, 80), (200, 80, 200), (240, 200, 60)]
KINDS = ["ball", "square", "triangle", "hexagon", "star"]
HAND_COLORS = {"Left": (255, 200, 80), "Right": (80, 180, 255)}


class Obj:
    def __init__(self, kind, x, y, size, color):
        self.kind = kind
        self.pos = np.array([x, y], dtype=np.float32)
        self.vel = np.zeros(2, dtype=np.float32)
        self.size = float(size)  # radius
        self.angle = 0.0  # radians
        self.color = color
        self.holders = ()  # labels of the hands holding it last frame
        self.grip = None  # data to keep the grip consistent while held

    def contains(self, p, margin=0):
        return np.linalg.norm(self.pos - p) <= self.size + margin

    def outline(self, offset=(0, 0)):
        cx, cy = self.pos + offset
        if self.kind == "star":
            n, radii = 10, [self.size, self.size * 0.45]
        else:
            n = {"square": 4, "triangle": 3, "hexagon": 6}[self.kind]
            radii = [self.size]
        start = self.angle - math.pi / 2 + (math.pi / 4 if self.kind == "square" else 0)
        pts = [
            (cx + radii[i % len(radii)] * math.cos(start + 2 * math.pi * i / n),
             cy + radii[i % len(radii)] * math.sin(start + 2 * math.pi * i / n))
            for i in range(n)
        ]
        return np.array(pts, dtype=np.int32)

    def draw(self, frame, highlight):
        dark = tuple(int(c * 0.55) for c in self.color)
        center = tuple(int(v) for v in self.pos)
        r = int(self.size)
        if self.kind == "ball":
            cv2.circle(frame, center, r, self.color, -1, cv2.LINE_AA)
            cv2.circle(frame, center, r, dark, 3, cv2.LINE_AA)
            # Shine so it reads as a sphere
            shine = (int(self.pos[0] - r * 0.35), int(self.pos[1] - r * 0.35))
            cv2.circle(frame, shine, max(r // 4, 2), (255, 255, 255), -1, cv2.LINE_AA)
            edge = None
        else:
            edge = self.outline()
            cv2.fillPoly(frame, [edge], self.color, cv2.LINE_AA)
            cv2.polylines(frame, [edge], True, dark, 3, cv2.LINE_AA)
        if highlight:
            if edge is None:
                cv2.circle(frame, center, r + 6, (255, 255, 255), 2, cv2.LINE_AA)
            else:
                cv2.polylines(frame, [edge], True, (255, 255, 255), 2, cv2.LINE_AA)

    def draw_shadow(self, frame):
        if self.kind == "ball":
            cv2.circle(frame, (int(self.pos[0] + 12), int(self.pos[1] + 16)), int(self.size), (0, 0, 0), -1, cv2.LINE_AA)
        else:
            cv2.fillPoly(frame, [self.outline((12, 16))], (0, 0, 0), cv2.LINE_AA)


class Grip:
    def __init__(self):
        self.pinching = False
        self.ratio = None
        self.point = None
        self.held = None
        self.trail = deque(maxlen=5)  # recent pinch points, for throw speed

    def velocity(self):
        if len(self.trail) < 2:
            return np.zeros(2, dtype=np.float32)
        v = (self.trail[-1] - self.trail[0]) / (len(self.trail) - 1)
        speed = np.linalg.norm(v)
        return v * (MAX_THROW / speed) if speed > MAX_THROW else v


class ObjectsMode(Mode):
    name = "objects"
    keys_help = "| [n]ew object [c] reset [g]ravity"

    def __init__(self, w, h):
        super().__init__(w, h)
        self.gravity = False
        self.grips = {"Left": Grip(), "Right": Grip()}
        self.reset_objects()

    def reset_objects(self):
        self.objects = []
        for i, kind in enumerate(KINDS):
            x = self.w * (i + 1) / (len(KINDS) + 1)
            self.objects.append(Obj(kind, x, self.h * 0.6, 55, COLORS[i % len(COLORS)]))
        for grip in self.grips.values():
            grip.held = None

    def add_random(self):
        self.objects.append(Obj(random.choice(KINDS), self.w / 2 + random.uniform(-200, 200), self.h * 0.4,
                                random.uniform(35, 75), random.choice(COLORS)))

    def reset_hands(self):
        for grip in self.grips.values():
            grip.pinching = False
            grip.held = None
            grip.trail.clear()

    def object_at(self, p):
        for obj in reversed(self.objects):  # topmost first
            if obj.contains(p, GRAB_MARGIN):
                return obj
        return None

    def release(self, grip):
        obj = grip.held
        grip.held = None
        if obj is not None and not any(g.held is obj for g in self.grips.values()):
            obj.vel = grip.velocity()

    def update(self, hands):
        for label, hand in hands.items():
            grip = self.grips[label]
            if not hand.present:
                self.release(grip)
                grip.pinching = False
                grip.point = grip.ratio = None
                grip.trail.clear()
                continue
            if not hand.visible:
                continue  # briefly lost: keep holding

            grip.ratio = pinch_ratio(hand.pts)
            grip.point = np.array(hand.smooth("pinch", (hand.pts[4] + hand.pts[8]) / 2), dtype=np.float32)
            grip.trail.append(grip.point)
            if not grip.pinching and grip.ratio < PINCH_ON:
                grip.pinching = True
                grip.held = self.object_at(grip.point)
                if grip.held is not None:
                    self.objects.remove(grip.held)
                    self.objects.append(grip.held)  # bring to front
            elif grip.pinching and grip.ratio > PINCH_OFF:
                grip.pinching = False
                self.release(grip)

        for obj in self.objects:
            holders = tuple(label for label, g in self.grips.items() if g.held is obj)
            if holders != obj.holders:
                self.rebase(obj, holders)
            if len(holders) == 1:
                obj.pos = self.grips[holders[0]].point + obj.grip["offset"]
                obj.vel[:] = 0
            elif len(holders) == 2:
                a, b = self.grips["Left"].point, self.grips["Right"].point
                g = obj.grip
                dist = max(float(np.linalg.norm(b - a)), 1.0)
                twist = math.atan2(b[1] - a[1], b[0] - a[0]) - g["angle0"]
                obj.size = float(np.clip(g["size0"] * dist / g["dist0"], MIN_SIZE, MAX_SIZE))
                obj.angle = g["obj_angle0"] + twist
                obj.pos = (a + b) / 2 + g["offset"]
                obj.vel[:] = 0
            else:
                self.step_physics(obj)

    def rebase(self, obj, holders):
        """Store how the object sits relative to the hand(s) now holding it."""
        obj.holders = holders
        if len(holders) == 1:
            obj.grip = {"offset": obj.pos - self.grips[holders[0]].point}
        elif len(holders) == 2:
            a, b = self.grips["Left"].point, self.grips["Right"].point
            obj.grip = {
                "dist0": max(float(np.linalg.norm(b - a)), 1.0),
                "size0": obj.size,
                "angle0": math.atan2(b[1] - a[1], b[0] - a[0]),
                "obj_angle0": obj.angle,
                "offset": obj.pos - (a + b) / 2,
            }
        else:
            obj.grip = None

    def step_physics(self, obj):
        if self.gravity:
            obj.vel[1] += GRAVITY
            obj.vel *= AIR_FRICTION
        else:
            obj.vel *= FRICTION
        obj.pos += obj.vel
        r = obj.size
        for axis, limit in ((0, self.w), (1, self.h)):
            if obj.pos[axis] < r:
                obj.pos[axis], obj.vel[axis] = r, abs(obj.vel[axis]) * BOUNCE
            elif obj.pos[axis] > limit - r:
                obj.pos[axis], obj.vel[axis] = limit - r, -abs(obj.vel[axis]) * BOUNCE
        if self.gravity and obj.pos[1] >= self.h - r - 1:
            obj.vel[0] *= 0.9  # floor friction so things settle

    def draw_scene(self, frame):
        out = frame.copy()
        held = [obj for obj in self.objects if obj.holders]
        if held:
            shadow = out.copy()
            for obj in held:
                obj.draw_shadow(shadow)
            cv2.addWeighted(shadow, SHADOW_OPACITY, out, 1 - SHADOW_OPACITY, 0, dst=out)
        hover = {self.object_at(g.point) for g in self.grips.values() if g.point is not None and not g.pinching}
        for obj in self.objects:
            obj.draw(out, highlight=bool(obj.holders) or obj in hover)
        return out

    def draw_ui(self, frame, show_debug):
        for label, grip in self.grips.items():
            if grip.point is None:
                continue
            p = tuple(int(v) for v in grip.point)
            color = (0, 255, 0) if grip.pinching else HAND_COLORS[label]
            cv2.circle(frame, p, 10 if grip.pinching else 14, color, -1 if grip.pinching else 2, cv2.LINE_AA)
            if show_debug:
                text = "HOLD" if grip.held is not None else ("PINCH" if grip.pinching else "OPEN")
                cv2.putText(frame, text, (p[0] + 16, p[1] - 16), FONT, 0.5, (255, 255, 255), 2, cv2.LINE_AA)

    def on_key(self, key):
        if key == ord("n"):
            self.add_random()
        elif key == ord("c"):
            self.reset_objects()
        elif key == ord("g"):
            self.gravity = not self.gravity
        else:
            return False
        return True

    def status(self):
        return f"objects: {len(self.objects)}   gravity: {'on' if self.gravity else 'off'}"

    def hand_debug(self, hand):
        grip = self.grips[hand.label]
        if grip.ratio is None:
            return ""
        state = f"HOLD {grip.held.kind}" if grip.held is not None else ("PINCH" if grip.pinching else "open")
        return f"pinch {grip.ratio:.2f} (<{PINCH_ON})  {state:13}"

    def hand_color(self, label):
        return HAND_COLORS[label]
