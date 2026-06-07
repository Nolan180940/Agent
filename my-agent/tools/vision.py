"""
Computer Vision tools — screenshot capture + VLM-powered screen analysis.

Uses SiliconFlow vision models (Qwen3-VL, Qwen2.5-VL) to understand
what's on the screen, locate UI elements, and guide mouse/keyboard actions.
"""
import base64
import io
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, List

import pyautogui
from PIL import Image

from tools.base import tool


# ── Screenshot helpers ──────────────────────────────────────────────────────

SCREENSHOT_DIR = Path(os.environ.get("AGENT_SCREENSHOT_DIR", "./screenshots"))
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def _capture_screenshot(
    region: Optional[tuple] = None,
    save_path: Optional[str] = None,
) -> str:
    """
    Capture a screenshot, optionally of a region.
    Returns the file path of the saved PNG.
    """
    img: Image.Image = pyautogui.screenshot(region=region)
    if save_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        save_path = str(SCREENSHOT_DIR / f"screen_{ts}.png")
    img.save(save_path, "PNG")
    return save_path


def _image_to_base64_data_uri(image: Image.Image) -> str:
    """Convert a PIL Image to a base64 data URI."""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def _get_screen_size() -> tuple:
    """Return (width, height) of the primary screen."""
    return pyautogui.size()


# ── Tools ───────────────────────────────────────────────────────────────────

@tool(category="vision")
def take_screenshot(
    region_x: int = 0,
    region_y: int = 0,
    region_w: int = 0,
    region_h: int = 0,
    save_path: str = "",
) -> str:
    """
    Take a screenshot of the entire screen or a specific region.

    Args:
        region_x: Left edge of capture region (0 for full screen).
        region_y: Top edge of capture region.
        region_w: Width of capture region.
        region_h: Height of capture region.
        save_path: Optional file path to save the screenshot.

    Returns:
        Path to the saved screenshot file.
    """
    region = None
    if region_w > 0 and region_h > 0:
        region = (region_x, region_y, region_w, region_h)

    path = _capture_screenshot(region=region, save_path=save_path or None)
    w, h = _get_screen_size()
    return f"Screenshot saved to: {path} (screen size: {w}x{h})"


@tool(category="vision")
def get_screen_size() -> str:
    """
    Get the current screen resolution.

    Returns:
        Screen width and height in pixels.
    """
    w, h = _get_screen_size()
    return f"Screen resolution: {w} x {h}"


@tool(category="vision")
def get_mouse_position() -> str:
    """
    Get the current mouse cursor position.

    Returns:
        Current (x, y) coordinates of the mouse.
    """
    x, y = pyautogui.position()
    w, h = _get_screen_size()
    return f"Mouse position: ({x}, {y}) on a {w}x{h} screen"


@tool(category="vision")
def locate_on_screen(
    image_path: str,
    confidence: float = 0.8,
) -> str:
    """
    Find the location of an image on the screen (template matching).

    Useful for locating buttons, icons, or UI elements by their appearance.

    Args:
        image_path: Path to the template image to find on screen.
        confidence: Match confidence threshold (0.0-1.0, default 0.8).

    Returns:
        Coordinates of the center of the match, or 'not found'.
    """
    try:
        location = pyautogui.locateCenterOnScreen(image_path, confidence=confidence)
        if location:
            return f"Found at: ({location.x}, {location.y})"
        return f"Image '{image_path}' not found on screen (confidence={confidence})"
    except Exception as e:
        return f"Locate failed: {e}. Try installing opencv-python for better matching."


@tool(category="vision")
def pixel_color(x: int, y: int) -> str:
    """
    Get the RGB color of a pixel at the given screen coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.

    Returns:
        RGB color string.
    """
    try:
        img = pyautogui.screenshot(region=(x, y, 1, 1))
        r, g, b = img.getpixel((0, 0))
        return f"Pixel at ({x}, {y}): RGB({r}, {g}, {b})"
    except Exception as e:
        return f"Failed to read pixel: {e}"


# ── VLM-powered screen analysis ─────────────────────────────────────────────
# These tools require the LLMProvider to be injected at runtime.
# See agent_core.py where _vlm_provider is set.

_vlm_provider = None  # Will be set by AgentCore


def set_vlm_provider(provider):
    """Inject the LLM provider for VLM screen analysis."""
    global _vlm_provider
    _vlm_provider = provider


@tool(category="vision")
async def analyze_screen(
    question: str = "Describe what you see on the screen in detail. Include the positions of any buttons, text fields, icons, and other UI elements.",
    region_x: int = 0,
    region_y: int = 0,
    region_w: int = 0,
    region_h: int = 0,
) -> str:
    """
    Take a screenshot and ask the vision model to analyze it.

    This is the core computer-vision capability — the VLM looks at your screen
    and answers questions about what it sees, locates UI elements, reads text, etc.

    Args:
        question: What to ask about the screenshot (e.g., "Where is the Submit button?",
                  "Read all the text on the screen", "What error message is shown?").
        region_x/y/w/h: Optional region to capture (0 means full screen).

    Returns:
        The VLM's analysis of the screenshot.
    """
    if _vlm_provider is None:
        return "⚠️ VLM provider not configured. Set SILICONFLOW_API_KEY and use provider=siliconflow."

    # Capture screenshot
    region = None
    if region_w > 0 and region_h > 0:
        region = (region_x, region_y, region_w, region_h)

    img = pyautogui.screenshot(region=region)
    data_uri = _image_to_base64_data_uri(img)

    # Ask VLM
    try:
        result = await _vlm_provider.chat_with_vision(
            message=question,
            images=[data_uri],
        )
        return result.get("content", str(result))
    except Exception as e:
        return f"VLM analysis failed: {e}"


@tool(category="vision")
async def find_ui_element(
    description: str,
) -> str:
    """
    Find a UI element on screen by description using computer vision.

    Takes a screenshot and asks the VLM to locate the described element,
    returning its approximate screen coordinates.

    Args:
        description: Natural language description of the element to find
                     (e.g., "the blue Submit button", "the search text field",
                     "the red error message at the top").

    Returns:
        Description of where the element is, including approximate coordinates.
    """
    if _vlm_provider is None:
        return "⚠️ VLM provider not configured."

    img = pyautogui.screenshot()
    data_uri = _image_to_base64_data_uri(img)
    w, h = _get_screen_size()

    prompt = (
        f"This is a screenshot of a {w}x{h} screen. "
        f"Find the UI element described as: '{description}'. "
        f"Return ONLY a JSON object with these fields: "
        f'{{"found": true/false, "description": "...", '
        f'"center_x": <pixel>, "center_y": <pixel>, '
        f'"bounds": {{"x": <pixel>, "y": <pixel>, "w": <pixel>, "h": <pixel>}}}}. '
        f"If not found, return {{\"found\": false, \"reason\": \"...\"}}."
    )

    try:
        result = await _vlm_provider.chat_with_vision(
            message=prompt,
            images=[data_uri],
        )
        return result.get("content", str(result))
    except Exception as e:
        return f"VLM find_ui_element failed: {e}"


@tool(category="vision")
async def read_screen_text(
    region_x: int = 0,
    region_y: int = 0,
    region_w: int = 0,
    region_h: int = 0,
) -> str:
    """
    Read all visible text on the screen (or a region) using OCR via VLM.

    Args:
        region_x/y/w/h: Optional region to read (0 means full screen).

    Returns:
        All text found on the screen.
    """
    if _vlm_provider is None:
        return "⚠️ VLM provider not configured."

    region = None
    if region_w > 0 and region_h > 0:
        region = (region_x, region_y, region_w, region_h)

    img = pyautogui.screenshot(region=region)
    data_uri = _image_to_base64_data_uri(img)

    try:
        result = await _vlm_provider.chat_with_vision(
            message="Read and transcribe ALL visible text on this screen. Include the approximate position of each text element. Be thorough and include every piece of text you can see.",
            images=[data_uri],
        )
        return result.get("content", str(result))
    except Exception as e:
        return f"VLM read_screen_text failed: {e}"
