"""Native file-open dialogs.

The generic app can run without this module doing anything. Windows gets a
small ctypes-backed dialog so the packaged exe is usable when launched without
command-line arguments or images in the current directory.
"""

from __future__ import annotations

import ctypes
import os
import sys
from typing import Optional


def build_image_file_filter() -> str:
    """Return a Windows common-dialog filter for registered image formats."""
    from ..viewers import get_registry

    patterns = sorted({f"*{ext}" for ext in get_registry().supported_extensions()})
    image_patterns = ";".join(patterns) if patterns else "*.png;*.jpg;*.jpeg;*.gif;*.webp"
    return f"Images\0{image_patterns}\0All files\0*.*\0\0"


def _log_dialog(message: str) -> None:
    try:
        from ..logging import log

        log(f"[DIALOG] {message}")
    except Exception:
        pass


def open_image_file_dialog(owner_hwnd: Optional[int] = None, initial_dir: Optional[str] = None) -> Optional[str]:
    """Show a native image file picker and return the selected path, if any."""
    if sys.platform != "win32":
        return None

    selected = _open_image_file_dialog_pywin32(initial_dir)
    if selected:
        return selected

    return _open_image_file_dialog_ctypes(owner_hwnd, initial_dir)


def _open_image_file_dialog_pywin32(initial_dir: Optional[str] = None) -> Optional[str]:
    try:
        import pywintypes
        import win32con
        import win32gui

        flags = (
            win32con.OFN_EXPLORER
            | win32con.OFN_FILEMUSTEXIST
            | win32con.OFN_PATHMUSTEXIST
            | win32con.OFN_NOCHANGEDIR
            | win32con.OFN_HIDEREADONLY
        )
        fname, _custom_filter, _flags = win32gui.GetOpenFileNameW(
            InitialDir=initial_dir if initial_dir and os.path.isdir(initial_dir) else os.getcwd(),
            Flags=flags,
            File="",
            DefExt="",
            Title="Open image",
            Filter=build_image_file_filter(),
            FilterIndex=1,
        )
        return fname if fname else None
    except Exception as exc:
        if exc.__class__.__name__ == "error" and getattr(exc, "winerror", None) == 0:
            return None
        _log_dialog(f"pywin32 GetOpenFileNameW failed: {exc!r}")
        return None


def _open_image_file_dialog_ctypes(owner_hwnd: Optional[int] = None, initial_dir: Optional[str] = None) -> Optional[str]:
    if sys.platform != "win32":
        return None

    try:
        from ctypes import wintypes

        class OPENFILENAMEW(ctypes.Structure):
            _fields_ = [
                ("lStructSize", wintypes.DWORD),
                ("hwndOwner", wintypes.HWND),
                ("hInstance", wintypes.HINSTANCE),
                ("lpstrFilter", wintypes.LPCWSTR),
                ("lpstrCustomFilter", wintypes.LPWSTR),
                ("nMaxCustFilter", wintypes.DWORD),
                ("nFilterIndex", wintypes.DWORD),
                ("lpstrFile", wintypes.LPWSTR),
                ("nMaxFile", wintypes.DWORD),
                ("lpstrFileTitle", wintypes.LPWSTR),
                ("nMaxFileTitle", wintypes.DWORD),
                ("lpstrInitialDir", wintypes.LPCWSTR),
                ("lpstrTitle", wintypes.LPCWSTR),
                ("Flags", wintypes.DWORD),
                ("nFileOffset", wintypes.WORD),
                ("nFileExtension", wintypes.WORD),
                ("lpstrDefExt", wintypes.LPCWSTR),
                ("lCustData", wintypes.LPARAM),
                ("lpfnHook", ctypes.c_void_p),
                ("lpTemplateName", wintypes.LPCWSTR),
                ("pvReserved", ctypes.c_void_p),
                ("dwReserved", wintypes.DWORD),
                ("FlagsEx", wintypes.DWORD),
            ]

        buffer_size = 32768
        file_buffer = ctypes.create_unicode_buffer(buffer_size)
        filter_buffer = ctypes.create_unicode_buffer(build_image_file_filter())
        title_buffer = ctypes.create_unicode_buffer("Open image")
        initial_dir_buffer = (
            ctypes.create_unicode_buffer(initial_dir)
            if initial_dir and os.path.isdir(initial_dir)
            else None
        )

        ofn = OPENFILENAMEW()
        ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
        ofn.hwndOwner = owner_hwnd or 0
        ofn.lpstrFilter = ctypes.cast(filter_buffer, wintypes.LPCWSTR)
        ofn.nFilterIndex = 1
        ofn.lpstrFile = file_buffer
        ofn.nMaxFile = buffer_size
        if initial_dir_buffer is not None:
            ofn.lpstrInitialDir = ctypes.cast(initial_dir_buffer, wintypes.LPCWSTR)
        ofn.lpstrTitle = ctypes.cast(title_buffer, wintypes.LPCWSTR)
        ofn.Flags = (
            0x00000004  # OFN_HIDEREADONLY
            | 0x00000008  # OFN_NOCHANGEDIR
            | 0x00000800  # OFN_PATHMUSTEXIST
            | 0x00001000  # OFN_FILEMUSTEXIST
            | 0x00080000  # OFN_EXPLORER
        )

        comdlg32 = ctypes.windll.comdlg32
        comdlg32.GetOpenFileNameW.argtypes = [ctypes.POINTER(OPENFILENAMEW)]
        comdlg32.GetOpenFileNameW.restype = wintypes.BOOL

        if not comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
            err = comdlg32.CommDlgExtendedError()
            if err:
                _log_dialog(f"ctypes GetOpenFileNameW failed: CommDlgExtendedError={err}")
            return None
        selected = file_buffer.value
        return selected if selected else None
    except Exception as exc:
        _log_dialog(f"ctypes GetOpenFileNameW failed: {exc!r}")
        return None
