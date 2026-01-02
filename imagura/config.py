"""Application configuration constants."""

from __future__ import annotations

# Performance
TARGET_FPS = 120
ASYNC_WORKERS = 10

# Animation durations (milliseconds)
ANIM_SWITCH_KEYS_MS = 250
ANIM_SWITCH_GALLERY_MS = 10
ANIM_TOGGLE_ZOOM_MS = 150
ANIM_OPEN_MS = 300
ANIM_ZOOM_MS = 150
GALLERY_SLIDE_MS = 150  # Animation time for gallery slide in/out

# View defaults
FIT_DEFAULT_SCALE = 0.95
FIT_OPEN_SCALE = 0.60
OPEN_ALPHA_START = 0.4

# Zoom
ZOOM_STEP_KEYS = 0.05
ZOOM_STEP_WHEEL = 0.1
MAX_ZOOM = 20.0  # Maximum zoom level (2000%)

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
KEY_REPEAT_DELAY = 0.4      # Seconds before key repeat starts
KEY_REPEAT_INTERVAL = 0.08  # Seconds between repeats

# Font settings
# Font is loaded at this base size - using larger size for better quality when scaling down
FONT_SIZE = 32
# Display size for filename overlay (can be different from load size)
FONT_DISPLAY_SIZE = 27
FONT_ANTIALIAS = True

# Hotkeys (raylib key codes)
# See: https://github.com/raysan5/raylib/blob/master/src/raylib.h
KEY_TOGGLE_HUD = 73         # KEY_I
KEY_TOGGLE_FILENAME = 78    # KEY_N
KEY_CYCLE_BG = 86           # KEY_V
KEY_DELETE_IMAGE = 261      # KEY_DELETE
KEY_ZOOM_IN = 265           # KEY_UP
KEY_ZOOM_IN_ALT = 87        # KEY_W
KEY_ZOOM_OUT = 264          # KEY_DOWN
KEY_ZOOM_OUT_ALT = 83       # KEY_S
KEY_TOGGLE_ZOOM = 90        # KEY_Z
KEY_TOGGLE_WINDOW = 70      # KEY_F
KEY_NEXT_IMAGE = 262        # KEY_RIGHT
KEY_NEXT_IMAGE_ALT = 68     # KEY_D
KEY_PREV_IMAGE = 263        # KEY_LEFT
KEY_PREV_IMAGE_ALT = 65     # KEY_A
KEY_CLOSE = 256             # KEY_ESCAPE

# Top toolbar
TOOLBAR_TRIGGER_FRAC = 0.05  # Top 5% triggers toolbar
TOOLBAR_TRIGGER_MIN_PX = 60  # Minimum trigger zone height in pixels
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

# Settings menu color schemes
SETTINGS_COLORS_TRANSPARENT = {
    "window_bg": (180, 177, 173, 255),
    "window_border": (140, 135, 125, 255),
    "title_color": (50, 45, 40, 255),
    "text_color": (40, 35, 30, 255),
    "text_secondary": (80, 75, 70, 255),
    "header_text": (60, 55, 50, 255),
    "input_bg": (245, 242, 238, 255),
    "input_border": (160, 155, 145, 255),
    "input_text": (30, 25, 20, 255),
    "input_active_border": (80, 120, 160, 255),
    "input_active_bg": (250, 248, 245, 255),
    "value_color": (50, 100, 140, 255),
    "hover_bg": (210, 205, 198, 255),
    "selection_bg": (160, 180, 200, 200),
    "tab_active": (245, 242, 238, 255),
    "tab_text": (60, 55, 50, 255),
    "tab_text_active": (30, 25, 20, 255),
    "hint_color": (110, 105, 100, 255),
    "close_btn": (140, 90, 90, 255),
    "close_btn_hover": (180, 60, 60, 255),
    "overlay": (80, 75, 70, 120),
}

SETTINGS_COLORS_LIGHT = {
    "window_bg": (185, 185, 185, 255),
    "window_border": (150, 150, 150, 255),
    "title_color": (30, 30, 30, 255),
    "text_color": (40, 40, 40, 255),
    "text_secondary": (90, 90, 90, 255),
    "header_text": (70, 70, 70, 255),
    "input_bg": (250, 250, 250, 255),
    "input_border": (170, 170, 170, 255),
    "input_text": (20, 20, 20, 255),
    "input_active_border": (60, 120, 180, 255),
    "input_active_bg": (255, 255, 255, 255),
    "value_color": (40, 100, 160, 255),
    "hover_bg": (220, 225, 230, 255),
    "selection_bg": (160, 190, 220, 200),
    "tab_active": (250, 250, 250, 255),
    "tab_text": (70, 70, 70, 255),
    "tab_text_active": (20, 20, 20, 255),
    "hint_color": (120, 120, 120, 255),
    "close_btn": (150, 70, 70, 255),
    "close_btn_hover": (200, 50, 50, 255),
    "overlay": (0, 0, 0, 100),
}

SETTINGS_COLORS_DARK = {
    "window_bg": (45, 47, 52, 255),
    "window_border": (80, 85, 95, 255),
    "title_color": (230, 230, 235, 255),
    "text_color": (210, 210, 215, 255),
    "text_secondary": (150, 150, 160, 255),
    "header_text": (170, 170, 180, 255),
    "input_bg": (55, 58, 65, 255),
    "input_border": (90, 95, 105, 255),
    "input_text": (230, 230, 235, 255),
    "input_active_border": (90, 150, 210, 255),
    "input_active_bg": (60, 65, 75, 255),
    "value_color": (110, 170, 230, 255),
    "hover_bg": (60, 65, 75, 255),
    "selection_bg": (70, 110, 160, 200),
    "tab_active": (60, 65, 75, 255),
    "tab_text": (150, 150, 160, 255),
    "tab_text_active": (230, 230, 235, 255),
    "hint_color": (110, 110, 120, 255),
    "close_btn": (170, 90, 90, 255),
    "close_btn_hover": (210, 70, 70, 255),
    "overlay": (0, 0, 0, 150),
}

# Window constraints
MIN_WINDOW_WIDTH = 400
MIN_WINDOW_HEIGHT = 300
NAV_EDGE_MIN_PX = 60  # Minimum navigation zone width in pixels
GALLERY_MIN_HEIGHT_PX = 80  # Minimum gallery height in pixels

# Supported image extensions
IMG_EXTS = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".tga", ".gif", ".qoi"})
