"""Move files to the platform trash/recycle bin."""

from __future__ import annotations

import os
import sys
from typing import Optional

from ..logging import log


def delete_to_trash(file_path: str, platform_name: Optional[str] = None) -> bool:
    """Move a file to the platform trash/recycle bin.

    Returns False instead of permanently deleting when a platform implementation
    is not available.
    """
    platform_name = platform_name or sys.platform
    if platform_name == "win32":
        return _delete_to_windows_recycle_bin(file_path)

    log(f"[DELETE] Trash is not implemented on {platform_name}")
    return False


def _delete_to_windows_recycle_bin(file_path: str) -> bool:
    """Move a file to the Windows recycle bin via SHFileOperationW."""
    try:
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("wFunc", wintypes.UINT),
                ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR),
                ("fFlags", wintypes.WORD),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        fo_delete = 3
        fof_allow_undo = 0x0040
        fof_no_confirmation = 0x0010
        fof_silent = 0x0004

        file_op = SHFILEOPSTRUCTW()
        file_op.hwnd = None
        file_op.wFunc = fo_delete
        file_op.pFrom = file_path + "\0\0"
        file_op.pTo = None
        file_op.fFlags = fof_allow_undo | fof_no_confirmation | fof_silent
        file_op.fAnyOperationsAborted = False
        file_op.hNameMappings = None
        file_op.lpszProgressTitle = None

        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(file_op))
        if result == 0 and not file_op.fAnyOperationsAborted:
            log(f"[DELETE] Sent to recycle bin: {os.path.basename(file_path)}")
            return True

        log(f"[DELETE][ERR] SHFileOperationW failed: {result}")
        return False
    except Exception as exc:
        log(f"[DELETE][ERR] Failed to delete: {exc!r}")
        return False
