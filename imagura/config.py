"""Application configuration constants."""

from __future__ import annotations

# Performance
TARGET_FPS = 120
ASYNC_WORKERS = 10

# Animation durations (milliseconds)
ANIM_SWITCH_KEYS_MS = 700
ANIM_SWITCH_GALLERY_MS = 10
ANIM_TOGGLE_ZOOM_MS = 150
ANIM_OPEN_MS = 700
ANIM_ZOOM_MS = 100
GALLERY_SLIDE_MS = 150

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

# Background modes
BG_MODES = [
    {"color": (0, 0, 0), "opacity": 0.5, "blur": True},
    {"color": (0, 0, 0), "opacity": 1.0, "blur": False},
    {"color": (255, 255, 255), "opacity": 1.0, "blur": False},
    {"color": (255, 255, 255), "opacity": 0.5, "blur": True},
]

# Supported image extensions
IMG_EXTS = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".tga", ".gif", ".qoi"})
