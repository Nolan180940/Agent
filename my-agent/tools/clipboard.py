"""
Clipboard tools — read/write Windows clipboard.
"""
import subprocess
import sys
from typing import Optional

from tools.base import tool


def _get_clipboard_text() -> str:
    """Read text from the Windows clipboard via PowerShell."""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", "Get-Clipboard"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()
    except Exception as e:
        return f"Failed to read clipboard: {e}"


def _set_clipboard_text(text: str) -> bool:
    """Write text to the Windows clipboard via PowerShell."""
    try:
        # Escape single quotes for PowerShell
        escaped = text.replace("'", "''")
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", f"Set-Clipboard -Value '{escaped}'"],
            capture_output=True, text=True, timeout=5,
        )
        return True
    except Exception:
        return False


@tool(category="clipboard")
def get_clipboard() -> str:
    """
    Read the current text content of the Windows clipboard.

    Returns:
        The clipboard text content.
    """
    return _get_clipboard_text()


@tool(category="clipboard")
def set_clipboard(text: str) -> str:
    """
    Set the Windows clipboard to the given text.

    Args:
        text: The text to copy to the clipboard.

    Returns:
        Status message.
    """
    ok = _set_clipboard_text(text)
    if ok:
        preview = text[:80] + "..." if len(text) > 80 else text
        return f"Clipboard set to: {preview}"
    return "Failed to set clipboard."


@tool(category="clipboard")
def copy_to_clipboard(text: str) -> str:
    """
    Copy text to the Windows clipboard (alias for set_clipboard).

    Args:
        text: The text to copy.

    Returns:
        Status message.
    """
    return set_clipboard(text)


@tool(category="clipboard")
def paste_from_clipboard() -> str:
    """
    Read and return the current Windows clipboard content (alias for get_clipboard).

    Returns:
        The clipboard text content.
    """
    return _get_clipboard_text()
