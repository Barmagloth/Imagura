"""Windows-specific utilities - blur effects, window handling, paths."""

from __future__ import annotations
import sys
import ctypes
from typing import Optional, Tuple


def get_short_path_name(long_path: str) -> str:
    """Convert a long path to 8.3 short path format (Windows only).

    This helps with paths containing unicode characters that some
    C libraries can't handle properly.
    """
    if sys.platform != 'win32':
        return long_path

    try:
        from ctypes import wintypes

        _GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW
        _GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        _GetShortPathNameW.restype = wintypes.DWORD

        output_buf_size = 0
        while True:
            output_buf = ctypes.create_unicode_buffer(output_buf_size)
            needed = _GetShortPathNameW(long_path, output_buf, output_buf_size)
            if needed == 0:
                return long_path
            if needed <= output_buf_size:
                return output_buf.value
            output_buf_size = needed
    except Exception:
        return long_path


def get_work_area() -> Tuple[int, int, int, int]:
    """Get the desktop work area (excluding taskbar).

    Returns:
        Tuple of (x, y, width, height). Returns (0, 0, 0, 0) on failure.
    """
    if sys.platform != 'win32':
        return 0, 0, 0, 0

    try:
        user32 = ctypes.windll.user32

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        rect = RECT()
        SPI_GETWORKAREA = 48
        user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    except Exception:
        return 0, 0, 0, 0


class WinBlur:
    """Windows blur effect manager using DWM API."""

    # DWM Window Attributes
    DWMWA_NCRENDERING_POLICY = 2
    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
    DWMWA_SYSTEMBACKDROP_TYPE = 38
    DWMWA_MICA_EFFECT = 1029  # Undocumented, for older Win11 builds

    # System backdrop types (Windows 11 22H2+)
    DWMSBT_AUTO = 0
    DWMSBT_NONE = 1
    DWMSBT_MAINWINDOW = 2      # Mica
    DWMSBT_TRANSIENTWINDOW = 3  # Acrylic
    DWMSBT_TABBEDWINDOW = 4    # Tabbed Mica

    # Track which method succeeded
    _active_method: Optional[str] = None

    @staticmethod
    def _get_windows_build() -> int:
        """Get Windows build number."""
        if sys.platform != 'win32':
            return 0
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
            build = winreg.QueryValueEx(key, "CurrentBuildNumber")[0]
            winreg.CloseKey(key)
            return int(build)
        except Exception:
            return 0

    @staticmethod
    def _set_window_attribute(hwnd: int, attr: int, value: int) -> bool:
        """Set a DWM window attribute."""
        if sys.platform != 'win32':
            return False
        try:
            dwmapi = ctypes.windll.dwmapi
            val = ctypes.c_int(value)
            res = dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd),
                ctypes.c_uint(attr),
                ctypes.byref(val),
                ctypes.sizeof(val)
            )
            return res == 0
        except Exception:
            return False

    @staticmethod
    def _extend_frame_into_client(hwnd: int, extend: bool = True) -> bool:
        """Extend or reset window frame into client area."""
        if sys.platform != 'win32':
            return False
        try:
            dwmapi = ctypes.windll.dwmapi

            class MARGINS(ctypes.Structure):
                _fields_ = [
                    ("cxLeftWidth", ctypes.c_int),
                    ("cxRightWidth", ctypes.c_int),
                    ("cyTopHeight", ctypes.c_int),
                    ("cyBottomHeight", ctypes.c_int),
                ]

            if extend:
                margins = MARGINS(-1, -1, -1, -1)  # Extend to entire window
            else:
                margins = MARGINS(0, 0, 0, 0)  # Reset to normal
            res = dwmapi.DwmExtendFrameIntoClientArea(
                ctypes.c_void_p(hwnd),
                ctypes.byref(margins)
            )
            return res == 0
        except Exception:
            return False

    @staticmethod
    def _set_composition_attribute(hwnd: int, accent_state: int, gradient_color: int = 0) -> bool:
        """Set Windows composition attribute with specified accent state."""
        if sys.platform != 'win32':
            return False
        try:
            user32 = ctypes.windll.user32

            class ACCENT_POLICY(ctypes.Structure):
                _fields_ = [
                    ("AccentState", ctypes.c_int),
                    ("AccentFlags", ctypes.c_int),
                    ("GradientColor", ctypes.c_uint),
                    ("AnimationId", ctypes.c_int),
                ]

            class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
                _fields_ = [
                    ("Attribute", ctypes.c_int),
                    ("Data", ctypes.c_void_p),
                    ("SizeOfData", ctypes.c_size_t),
                ]

            WCA_ACCENT_POLICY = 19

            accent = ACCENT_POLICY()
            accent.AccentState = accent_state
            accent.AccentFlags = 2 if accent_state != 0 else 0
            accent.GradientColor = gradient_color
            accent.AnimationId = 0

            data = WINDOWCOMPOSITIONATTRIBDATA()
            data.Attribute = WCA_ACCENT_POLICY
            data.Data = ctypes.addressof(accent)
            data.SizeOfData = ctypes.sizeof(accent)

            SetWindowCompositionAttribute = getattr(user32, 'SetWindowCompositionAttribute', None)
            if SetWindowCompositionAttribute:
                result = SetWindowCompositionAttribute(ctypes.c_void_p(hwnd), ctypes.byref(data))
                return result != 0
            return False
        except Exception:
            return False

    # Accent states as class constants for testing
    ACCENT_DISABLED = 0
    ACCENT_ENABLE_GRADIENT = 1
    ACCENT_ENABLE_TRANSPARENTGRADIENT = 2
    ACCENT_ENABLE_BLURBEHIND = 3
    ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
    ACCENT_ENABLE_HOSTBACKDROP = 5

    @classmethod
    def test_mode(cls, hwnd: Optional[int], mode: int) -> str:
        """Test different blur/transparency modes. Returns description."""
        if not hwnd:
            return "No hwnd"

        # First disable everything
        cls._set_composition_attribute(hwnd, cls.ACCENT_DISABLED, 0)
        cls._set_window_attribute(hwnd, cls.DWMWA_SYSTEMBACKDROP_TYPE, cls.DWMSBT_NONE)

        descriptions = {
            0: "All disabled",
            1: "ExtendFrame only",
            2: "ACCENT_ENABLE_BLURBEHIND (3)",
            3: "ACCENT_ENABLE_ACRYLICBLURBEHIND (4) transparent",
            4: "ACCENT_ENABLE_ACRYLICBLURBEHIND (4) dark tint",
            5: "ACCENT_ENABLE_HOSTBACKDROP (5)",
            6: "DWMSBT_TRANSIENTWINDOW (acrylic backdrop)",
            7: "DWMSBT_MAINWINDOW (mica backdrop)",
            8: "Backdrop + BLURBEHIND combo",
            9: "Backdrop + HOSTBACKDROP combo",
        }

        if mode == 0:
            cls._extend_frame_into_client(hwnd, False)
            cls._active_method = None
        elif mode == 1:
            cls._extend_frame_into_client(hwnd, True)
            cls._active_method = "extend_frame"
        elif mode == 2:
            cls._extend_frame_into_client(hwnd, True)
            cls._set_composition_attribute(hwnd, cls.ACCENT_ENABLE_BLURBEHIND, 0x00000000)
            cls._active_method = "blur_behind"
        elif mode == 3:
            cls._extend_frame_into_client(hwnd, True)
            cls._set_composition_attribute(hwnd, cls.ACCENT_ENABLE_ACRYLICBLURBEHIND, 0x01000000)
            cls._active_method = "acrylic_transparent"
        elif mode == 4:
            cls._extend_frame_into_client(hwnd, True)
            cls._set_composition_attribute(hwnd, cls.ACCENT_ENABLE_ACRYLICBLURBEHIND, 0x99000000)
            cls._active_method = "acrylic_dark"
        elif mode == 5:
            cls._extend_frame_into_client(hwnd, True)
            cls._set_composition_attribute(hwnd, cls.ACCENT_ENABLE_HOSTBACKDROP, 0)
            cls._active_method = "host_backdrop"
        elif mode == 6:
            cls._extend_frame_into_client(hwnd, True)
            cls._set_window_attribute(hwnd, cls.DWMWA_SYSTEMBACKDROP_TYPE, cls.DWMSBT_TRANSIENTWINDOW)
            cls._active_method = "backdrop_acrylic"
        elif mode == 7:
            cls._extend_frame_into_client(hwnd, True)
            cls._set_window_attribute(hwnd, cls.DWMWA_SYSTEMBACKDROP_TYPE, cls.DWMSBT_MAINWINDOW)
            cls._active_method = "backdrop_mica"
        elif mode == 8:
            cls._extend_frame_into_client(hwnd, True)
            cls._set_window_attribute(hwnd, cls.DWMWA_SYSTEMBACKDROP_TYPE, cls.DWMSBT_TRANSIENTWINDOW)
            cls._set_composition_attribute(hwnd, cls.ACCENT_ENABLE_BLURBEHIND, 0x00000000)
            cls._active_method = "backdrop+blur"
        elif mode == 9:
            cls._extend_frame_into_client(hwnd, True)
            cls._set_window_attribute(hwnd, cls.DWMWA_SYSTEMBACKDROP_TYPE, cls.DWMSBT_TRANSIENTWINDOW)
            cls._set_composition_attribute(hwnd, cls.ACCENT_ENABLE_HOSTBACKDROP, 0)
            cls._active_method = "backdrop+host"

        return descriptions.get(mode, f"Unknown mode {mode}")

    @classmethod
    def enable(cls, hwnd: Optional[int]) -> None:
        """Enable blur/transparency effect on window."""
        if not hwnd:
            return

        cls._active_method = None
        build = cls._get_windows_build()

        # Extend frame into client area (required for all methods)
        cls._extend_frame_into_client(hwnd, True)

        # Windows 11 (build 22000+)
        if build >= 22000:
            # Try host backdrop (gives transparency on Win11)
            if cls._set_composition_attribute(hwnd, cls.ACCENT_ENABLE_HOSTBACKDROP, 0):
                cls._active_method = "host_backdrop"
                return

        # Windows 10 or fallback
        # Acrylic with semi-transparent dark tint (60% opacity)
        if cls._set_composition_attribute(hwnd, cls.ACCENT_ENABLE_ACRYLICBLURBEHIND, 0x99000000):
            cls._active_method = "acrylic"
            return

        # Basic blur
        if cls._set_composition_attribute(hwnd, cls.ACCENT_ENABLE_BLURBEHIND, 0x00000000):
            cls._active_method = "blur"
            return

    @classmethod
    def disable(cls, hwnd: Optional[int]) -> None:
        """Disable blur effect on window."""
        if not hwnd:
            return

        # Disable composition attribute
        cls._set_composition_attribute(hwnd, cls.ACCENT_DISABLED, 0)

        # Disable backdrop
        cls._set_window_attribute(hwnd, cls.DWMWA_SYSTEMBACKDROP_TYPE, cls.DWMSBT_NONE)

        # Reset frame extension
        cls._extend_frame_into_client(hwnd, extend=False)
        cls._active_method = None


def get_window_handle_from_raylib() -> Optional[int]:
    """Get HWND from raylib window."""
    try:
        # Import here to avoid circular dependency
        from .rl_compat import rl

        if hasattr(rl, "get_window_handle"):
            return int(ctypes.cast(rl.get_window_handle(), ctypes.c_void_p).value or 0)
        if hasattr(rl, "GetWindowHandle"):
            return int(ctypes.cast(rl.GetWindowHandle(), ctypes.c_void_p).value or 0)
    except Exception:
        pass

    # Fallback: find by window title
    if sys.platform == 'win32':
        try:
            user32 = ctypes.windll.user32
            user32.FindWindowW.restype = ctypes.c_void_p
            return int(user32.FindWindowW(None, "Viewer")) or None
        except Exception:
            pass

    return None
