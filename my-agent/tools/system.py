"""
Windows system automation tools using pywinauto and pyautogui.
"""
import pyautogui
from pathlib import Path
from typing import Optional, List
import subprocess
import time

# Only import pywinauto on Windows
try:
    from pywinauto import Application
    from pywinauto.findwindows import find_window
    PYWINAUTO_AVAILABLE = True
except ImportError:
    PYWINAUTO_AVAILABLE = False

from tools.base import tool


@tool(category="system")
def open_application(app_path: str) -> str:
    """
    Open a Windows application by path or name.
    
    Args:
        app_path: Full path to executable or app name (e.g., "notepad.exe", "C:\\Program Files\\App\\app.exe")
    
    Returns:
        Status message with process info
    """
    try:
        path = Path(app_path)
        
        if path.exists():
            # Full path provided
            process = subprocess.Popen([str(path)])
        else:
            # Try to find by name
            process = subprocess.Popen([app_path])
        
        return f"Launched application: {app_path} (PID: {process.pid})"
    except FileNotFoundError:
        return f"Application not found: {app_path}"
    except Exception as e:
        return f"Failed to launch {app_path}: {str(e)}"


@tool(category="system")
def close_application(window_title: str) -> str:
    """
    Close an application window by title.
    
    Args:
        window_title: Part of the window title to match
    
    Returns:
        Status message
    """
    if not PYWINAUTO_AVAILABLE:
        return "pywinauto not available (Windows only)"
    
    try:
        app = Application(backend="win32").connect(title_re=window_title)
        window = app.top_window()
        window.close()
        return f"Closed window matching: {window_title}"
    except Exception as e:
        return f"Failed to close window '{window_title}': {str(e)}"


@tool(category="system")
def get_window_list() -> str:
    """
    Get list of currently open windows.
    
    Returns:
        List of window titles
    """
    if not PYWINAUTO_AVAILABLE:
        return "pywinauto not available (Windows only)"
    
    try:
        windows = []
        for proc in Application(backend="win32").windows():
            title = proc.window_text()
            if title:  # Skip empty titles
                windows.append(f"- {title}")
        
        if windows:
            return "Open windows:\n" + "\n".join(windows[:20])  # Limit to 20
        else:
            return "No windows found"
    except Exception as e:
        return f"Failed to get window list: {str(e)}"


@tool(category="system")
def activate_window(window_title: str) -> str:
    """
    Bring a window to the foreground.
    
    Args:
        window_title: Part of the window title to match
    
    Returns:
        Status message
    """
    if not PYWINAUTO_AVAILABLE:
        return "pywinauto not available (Windows only)"
    
    try:
        app = Application(backend="win32").connect(title_re=window_title)
        window = app.top_window()
        window.set_focus()
        return f"Activated window: {window_title}"
    except Exception as e:
        return f"Failed to activate window '{window_title}': {str(e)}"


@tool(category="system")
def press_keys(key_sequence: str) -> str:
    """
    Press a sequence of keyboard keys.
    
    Special keys: {ENTER}, {TAB}, {ESC}, {CTRL}, {ALT}, {SHIFT}, {WIN}, 
                  {UP}, {DOWN}, {LEFT}, {RIGHT}, {F1}-{F12}
    
    Args:
        key_sequence: Keys to press (e.g., "{CTRL}s" for Ctrl+S, "hello{ENTER}")
    
    Returns:
        Status message
    """
    try:
        pyautogui.press(key_sequence)
        return f"Pressed keys: {key_sequence}"
    except Exception as e:
        return f"Failed to press keys '{key_sequence}': {str(e)}"


@tool(category="system")
def type_text(text: str, interval: float = 0.1) -> str:
    """
    Type text character by character (simulates human typing).
    
    Args:
        text: Text to type
        interval: Delay between keystrokes in seconds
    
    Returns:
        Status message
    """
    try:
        pyautogui.write(text, interval=interval)
        return f"Typed: {text[:50]}..." if len(text) > 50 else f"Typed: {text}"
    except Exception as e:
        return f"Failed to type text: {str(e)}"


@tool(category="system")
def move_mouse(x: int, y: int, duration: float = 0.5) -> str:
    """
    Move mouse to specific screen coordinates.
    
    Args:
        x: X coordinate (pixels from left)
        y: Y coordinate (pixels from top)
        duration: Time to take moving mouse (seconds)
    
    Returns:
        Status message with new position
    """
    try:
        pyautogui.moveTo(x, y, duration=duration)
        return f"Mouse moved to ({x}, {y})"
    except Exception as e:
        return f"Failed to move mouse: {str(e)}"


@tool(category="system")
def click_mouse(button: str = "left", clicks: int = 1) -> str:
    """
    Click mouse button at current position.
    
    Args:
        button: Button to click ("left", "right", "middle")
        clicks: Number of clicks (1=single, 2=double)
    
    Returns:
        Status message
    """
    try:
        pyautogui.click(clicks=clicks, button=button)
        click_type = f"{clicks}x " if clicks > 1 else ""
        return f"Performed {click_type}{button} click"
    except Exception as e:
        return f"Failed to click mouse: {str(e)}"


@tool(category="system")
def get_screen_size() -> str:
    """
    Get current screen resolution.
    
    Returns:
        Screen width and height
    """
    try:
        width, height = pyautogui.size()
        return f"Screen size: {width}x{height} pixels"
    except Exception as e:
        return f"Failed to get screen size: {str(e)}"


@tool(category="system")
def take_screenshot(filename: str = "screenshot.png") -> str:
    """
    Take a screenshot of the entire screen.
    
    Args:
        filename: Filename to save the screenshot
    
    Returns:
        Path to saved screenshot
    """
    try:
        path = Path(filename)
        screenshot = pyautogui.screenshot()
        screenshot.save(str(path.absolute()))
        return f"Screenshot saved to {path.absolute()}"
    except Exception as e:
        return f"Failed to take screenshot: {str(e)}"


@tool(category="system")
def wait_seconds(seconds: int) -> str:
    """
    Wait for specified number of seconds.
    
    Useful for allowing UI elements to load between actions.
    
    Args:
        seconds: Number of seconds to wait
    
    Returns:
        Status message
    """
    try:
        time.sleep(seconds)
        return f"Waited for {seconds} seconds"
    except Exception as e:
        return f"Failed to wait: {str(e)}"


@tool(category="system")
def run_command(command: str, shell: bool = True) -> str:
    """
    Run a command in the system shell.
    
    ⚠️ Use with caution - this executes arbitrary commands!
    
    Args:
        command: Command to execute
        shell: Whether to run through shell (default True)
    
    Returns:
        Command output (stdout + stderr, truncated to 1000 chars)
    """
    try:
        result = subprocess.run(
            command,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        output = result.stdout + result.stderr
        truncated = output[:1000] + ("..." if len(output) > 1000 else "")
        
        status = "Success" if result.returncode == 0 else f"Failed (exit code {result.returncode})"
        return f"{status}:\n{truncated}"
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds"
    except Exception as e:
        return f"Failed to run command: {str(e)}"


# ── Advanced mouse control ──────────────────────────────────────────────────

@tool(category="system")
def drag_mouse(
    from_x: int, from_y: int,
    to_x: int, to_y: int,
    duration: float = 0.5,
    button: str = "left",
) -> str:
    """
    Drag the mouse from one position to another (click and hold, move, release).

    Useful for drag-and-drop operations, selecting text, moving windows, etc.

    Args:
        from_x: Starting X coordinate.
        from_y: Starting Y coordinate.
        to_x: Ending X coordinate.
        to_y: Ending Y coordinate.
        duration: Time to take for the drag movement (seconds).
        button: Mouse button to hold ("left", "right", "middle").

    Returns:
        Status message.
    """
    try:
        pyautogui.moveTo(from_x, from_y, duration=0.1)
        pyautogui.drag(to_x - from_x, to_y - from_y, duration=duration, button=button)
        return f"Dragged mouse from ({from_x}, {from_y}) to ({to_x}, {to_y})"
    except Exception as e:
        return f"Failed to drag mouse: {e}"


@tool(category="system")
def scroll(clicks: int = -3) -> str:
    """
    Scroll the mouse wheel at the current position.

    Args:
        clicks: Number of scroll clicks. Positive = up, negative = down.
                (e.g., -3 scrolls down 3 clicks, 5 scrolls up 5 clicks)

    Returns:
        Status message.
    """
    try:
        pyautogui.scroll(clicks)
        direction = "up" if clicks > 0 else "down"
        return f"Scrolled {direction} {abs(clicks)} clicks"
    except Exception as e:
        return f"Failed to scroll: {e}"


@tool(category="system")
def hotkey(keys: str) -> str:
    """
    Press a key combination (e.g., Ctrl+C, Alt+Tab, Win+R).

    Args:
        keys: Keys separated by '+' (e.g., "ctrl+c", "alt+tab", "win+r", "ctrl+shift+esc").

    Returns:
        Status message.
    """
    try:
        key_list = [k.strip() for k in keys.split("+")]
        pyautogui.hotkey(*key_list)
        return f"Pressed hotkey: {keys}"
    except Exception as e:
        return f"Failed to press hotkey '{keys}': {e}"


@tool(category="system")
def double_click(x: int = 0, y: int = 0, button: str = "left") -> str:
    """
    Double-click at the given coordinates (or current position if x,y=0).

    Args:
        x: X coordinate (0 = current position).
        y: Y coordinate (0 = current position).
        button: Mouse button ("left", "right", "middle").

    Returns:
        Status message.
    """
    try:
        if x != 0 or y != 0:
            pyautogui.moveTo(x, y, duration=0.2)
        pyautogui.doubleClick(button=button)
        pos = pyautogui.position()
        return f"Double-clicked ({button}) at ({pos.x}, {pos.y})"
    except Exception as e:
        return f"Failed to double-click: {e}"


@tool(category="system")
def right_click(x: int = 0, y: int = 0) -> str:
    """
    Right-click at the given coordinates (or current position if x,y=0).

    Args:
        x: X coordinate (0 = current position).
        y: Y coordinate (0 = current position).

    Returns:
        Status message.
    """
    try:
        if x != 0 or y != 0:
            pyautogui.moveTo(x, y, duration=0.2)
        pyautogui.rightClick()
        pos = pyautogui.position()
        return f"Right-clicked at ({pos.x}, {pos.y})"
    except Exception as e:
        return f"Failed to right-click: {e}"


@tool(category="system")
def mouse_position() -> str:
    """
    Get the current mouse cursor position.

    Returns:
        Current (x, y) coordinates.
    """
    try:
        x, y = pyautogui.position()
        return f"Mouse at ({x}, {y})"
    except Exception as e:
        return f"Failed to get mouse position: {e}"


@tool(category="system")
def screenshot_region(
    x: int, y: int, width: int, height: int,
    filename: str = "screenshot_region.png",
) -> str:
    """
    Take a screenshot of a specific screen region.

    Args:
        x: Left edge of region.
        y: Top edge of region.
        width: Width of region.
        height: Height of region.
        filename: File to save the screenshot.

    Returns:
        Path to saved screenshot.
    """
    try:
        path = Path(filename)
        screenshot = pyautogui.screenshot(region=(x, y, width, height))
        screenshot.save(str(path.absolute()))
        return f"Region screenshot saved to {path.absolute()}"
    except Exception as e:
        return f"Failed to take region screenshot: {e}"
