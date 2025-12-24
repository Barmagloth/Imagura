"""Application configuration constants."""

from __future__ import annotations

# Performance
TARGET_FPS = 120
ASYNC_WORKERS = 10

# Animation durations (milliseconds)
ANIM_SWITCH_KEYS_MS = 200
ANIM_SWITCH_GALLERY_MS = 10
ANIM_TOGGLE_ZOOM_MS = 150
ANIM_OPEN_MS = 300
ANIM_ZOOM_MS = 100
GALLERY_SLIDE_MS = 50

# View defaults
FIT_DEFAULT_SCALE = 0.95
FIT_OPEN_SCALE = 0.60
OPEN_ALPHA_START = 0.4

# Zoom
ZOOM_STEP_KEYS = 0.01
ZOOM_STEP_WHEEL = 0.1

# Close button
CLOSE_BTN_RADIUS = 28
CLOSE_BTN_MARGIN = 20
CLOSE_BTN_ALPHA_MIN = 0.0
CLOSE_BTN_ALPHA_FAR = 0.1
CLOSE_BTN_ALPHA_MAX = 0.5
CLOSE_BTN_ALPHA_HOVER = 1.0
CLOSE_BTN_BG_ALPHA_MAX = 0.5

# Navigation buttons
NAV_BTN_RADIUS = 40
NAV_BTN_BG_ALPHA_MAX = 0.5

# Image limits
MAX_IMAGE_DIMENSION = 8192
MAX_FILE_SIZE_MB = 200
HEAVY_FILE_SIZE_MB = 10
HEAVY_MIN_SHORT_SIDE = 4000

# Gallery
GALLERY_HEIGHT_FRAC = 0.12
GALLERY_TRIGGER_FRAC = 0.08
GALLERY_THUMB_SPACING = 20
GALLERY_MIN_SCALE = 0.7
GALLERY_MIN_ALPHA = 0.3
GALLERY_SETTLE_DEBOUNCE_S = 0.12

# Thumbnails
THUMB_CACHE_LIMIT = 400
THUMB_CACHE_DIR = ".imagura_cache"
THUMB_PADDING = 6
THUMB_PRELOAD_SPAN = 40
THUMB_BUILD_BUDGET_PER_FRAME = 2

# Input
DOUBLE_CLICK_TIME_MS = 300
IDLE_THRESHOLD_SECONDS = 0.5

# Font settings
FONT_SIZE = 26
FONT_ANTIALIAS = True

# Hotkeys (raylib key codes)
# See: https://github.com/raysan5/raylib/blob/master/src/raylib.h
KEY_TOGGLE_HUD = 73         # KEY_I
KEY_TOGGLE_FILENAME = 78    # KEY_N
KEY_CYCLE_BG = 86           # KEY_V
KEY_DELETE_IMAGE = 261      # KEY_DELETE
KEY_ZOOM_IN = 265           # KEY_UP
KEY_ZOOM_OUT = 264          # KEY_DOWN
KEY_TOGGLE_ZOOM = 70        # KEY_F
KEY_NEXT_IMAGE = 262        # KEY_RIGHT
KEY_NEXT_IMAGE_ALT = 68     # KEY_D
KEY_PREV_IMAGE = 263        # KEY_LEFT
KEY_PREV_IMAGE_ALT = 65     # KEY_A
KEY_CLOSE = 256             # KEY_ESCAPE

# Top toolbar
TOOLBAR_TRIGGER_FRAC = 0.05  # Top 5% triggers toolbar
TOOLBAR_HEIGHT = 60
TOOLBAR_BTN_RADIUS = 24
TOOLBAR_BTN_SPACING = 20
TOOLBAR_BG_ALPHA = 0.6
TOOLBAR_SLIDE_MS = 150

# Context menu
MENU_ITEM_HEIGHT = 36
MENU_ITEM_WIDTH = 160
MENU_PADDING = 8
MENU_BG_ALPHA = 0.9
MENU_HOVER_ALPHA = 0.3

# Background modes
BG_MODES = [
    {"color": (0, 0, 0), "opacity": 0.5, "blur": True},
    {"color": (0, 0, 0), "opacity": 1.0, "blur": False},
    {"color": (255, 255, 255), "opacity": 1.0, "blur": False},
    {"color": (255, 255, 255), "opacity": 0.5, "blur": True},
]

# Supported image extensions
IMG_EXTS = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".tga", ".gif", ".qoi"})
