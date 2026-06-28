"""Application configuration constants."""

from __future__ import annotations

# Application metadata (shown in the About tab). Keep APP_VERSION in sync with
# pyproject.toml.
APP_NAME = "Imagura"
APP_VERSION = "2.1.0"
APP_AUTHOR = "Barmagloth"
APP_LICENSE = "MIT"
APP_YEAR = "2026"

# Interface language ("ru" or "en"). Overridden at startup from user settings.
LANGUAGE = "ru"

# Performance
TARGET_FPS = 120
ASYNC_WORKERS = 10

# Animation durations (milliseconds)
ANIM_SWITCH_KEYS_MS = 250
RAPID_NAV_SKIP_THRESHOLD = 4  # Skip animations when queue exceeds this
ANIM_SWITCH_GALLERY_MS = 150
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
MAX_ANIM_FRAMES = 600
MAX_ANIM_MEMORY_MB = 256
ANIMATED_CONTENT_CACHE_MAX_MB = 256
ANIMATED_CONTENT_CACHE_MAX_ITEMS = 4
FULL_IMAGE_CACHE_MAX_MB = 256
FULL_IMAGE_CACHE_MAX_ITEMS = 4
DEFAULT_GALLERY_SORT_KEY = "name"
DEFAULT_GALLERY_SORT_DESC = False

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
FONT_DISPLAY_SIZE = 28
FONT_ANTIALIAS = True
SHOW_SCALE_OVERLAY = True

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

# Background blur (DWM acrylic). On by default for the frosted look; turn it off
# for smooth window move/resize (acrylic makes the DWM recomposite every step,
# which freezes resizing on Windows).
BLUR_ENABLED = True

# Settings modal window color schemes (NOT app background!)
SETTINGS_MODAL_COLORS_TRANSPARENT = {
    "window_bg": (232, 229, 225, 255),
    "window_border": (160, 155, 145, 255),
    "title_color": (40, 35, 30, 255),
    "text_color": (35, 30, 25, 255),
    "text_secondary": (70, 65, 60, 255),
    "header_text": (50, 45, 40, 255),
    "input_bg": (245, 242, 238, 255),
    "input_border": (160, 155, 145, 255),
    "input_text": (30, 25, 20, 255),
    "input_active_border": (80, 120, 160, 255),
    "input_active_bg": (250, 248, 245, 255),
    "value_color": (40, 90, 130, 255),
    "hover_bg": (225, 220, 215, 255),
    "selection_bg": (160, 180, 200, 200),
    "tab_active": (245, 242, 238, 255),
    "tab_text": (55, 50, 45, 255),
    "tab_text_active": (25, 20, 15, 255),
    "hint_color": (80, 75, 70, 255),
    "close_btn": (140, 90, 90, 255),
    "close_btn_hover": (180, 60, 60, 255),
    "overlay": (12, 11, 9, 120),
}

SETTINGS_MODAL_COLORS_LIGHT = {
    "window_bg": (235, 235, 235, 255),
    "window_border": (165, 165, 165, 255),
    "title_color": (25, 25, 25, 255),
    "text_color": (35, 35, 35, 255),
    "text_secondary": (80, 80, 80, 255),
    "header_text": (55, 55, 55, 255),
    "input_bg": (250, 250, 250, 255),
    "input_border": (170, 170, 170, 255),
    "input_text": (20, 20, 20, 255),
    "input_active_border": (60, 120, 180, 255),
    "input_active_bg": (255, 255, 255, 255),
    "value_color": (35, 90, 150, 255),
    "hover_bg": (230, 232, 235, 255),
    "selection_bg": (160, 190, 220, 200),
    "tab_active": (250, 250, 250, 255),
    "tab_text": (60, 60, 60, 255),
    "tab_text_active": (15, 15, 15, 255),
    "hint_color": (75, 75, 75, 255),
    "close_btn": (150, 70, 70, 255),
    "close_btn_hover": (200, 50, 50, 255),
    "overlay": (0, 0, 0, 120),
}

SETTINGS_MODAL_COLORS_DARK = {
    "window_bg": (50, 52, 58, 255),
    "window_border": (85, 90, 100, 255),
    "title_color": (235, 235, 240, 255),
    "text_color": (215, 215, 220, 255),
    "text_secondary": (155, 155, 165, 255),
    "header_text": (175, 175, 185, 255),
    "input_bg": (60, 63, 70, 255),
    "input_border": (95, 100, 110, 255),
    "input_text": (235, 235, 240, 255),
    "input_active_border": (90, 150, 210, 255),
    "input_active_bg": (65, 70, 80, 255),
    "value_color": (115, 175, 235, 255),
    "hover_bg": (65, 70, 80, 255),
    "selection_bg": (70, 110, 160, 200),
    "tab_active": (65, 70, 80, 255),
    "tab_text": (155, 155, 165, 255),
    "tab_text_active": (235, 235, 240, 255),
    "hint_color": (140, 140, 150, 255),
    "close_btn": (170, 90, 90, 255),
    "close_btn_hover": (210, 70, 70, 255),
    "overlay": (0, 0, 0, 120),
}

# Settings modal window dimensions and layout
SETTINGS_MODAL_WIDTH = 600
SETTINGS_MODAL_HEIGHT = 480
SETTINGS_MODAL_SHADOW_OFFSET = 8
SETTINGS_MODAL_TITLE_Y = 14
SETTINGS_MODAL_CLOSE_SIZE = 28
SETTINGS_MODAL_CLOSE_MARGIN = 12

# Settings modal tabs
SETTINGS_TAB_HEIGHT = 32
SETTINGS_TAB_PADDING = 10  # Horizontal padding inside each tab
SETTINGS_TAB_GAP = 2       # Gap between tabs
SETTINGS_TAB_START_X = 15  # Left margin for tabs
SETTINGS_TAB_TOP_Y = 45    # Distance from window top to tabs

# Settings modal content area
SETTINGS_CONTENT_PADDING_X = 25
SETTINGS_CONTENT_ITEM_HEIGHT = 32
SETTINGS_CONTENT_SUB_INDENT = 20  # Extra indent for sub-items
SETTINGS_CONTENT_VALUE_WIDTH = 100
SETTINGS_CONTENT_VALUE_MARGIN = 30
SETTINGS_CONTENT_BORDER_MARGIN = 15
SETTINGS_CONTENT_FOOTER_HEIGHT = 45

# Window constraints
MIN_WINDOW_WIDTH = 400
MIN_WINDOW_HEIGHT = 300
NAV_EDGE_MIN_PX = 60  # Minimum navigation zone width in pixels
GALLERY_MIN_HEIGHT_PX = 80  # Minimum gallery height in pixels

# Supported image extensions (kept for backward compatibility)
IMG_EXTS = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".tga", ".gif", ".qoi"})


def get_supported_extensions() -> frozenset:
    """Return all extensions supported by registered viewers."""
    from .viewers import get_registry
    return get_registry().supported_extensions()
