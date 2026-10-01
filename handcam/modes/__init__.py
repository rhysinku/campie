"""Available modes. The first one is the default; `m` cycles through them in this order."""

from handcam.modes.draw import DrawMode
from handcam.modes.objects import ObjectsMode

MODES = [DrawMode, ObjectsMode]
