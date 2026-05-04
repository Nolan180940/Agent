"""
Browser automation tools using Playwright.
Includes special support for Google Colab.
"""
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from typing import Optional, Dict, Any
import asyncio
import base64
from pathlib import Path

from tools.base import tool


# Global browser instance (singleton pattern)
_browser: Optional[Browser] = None
_context: Optional[BrowserContext] = None
_page: Optional[Page] = None
_playwright = None


async def get_browser(browser_type: str = "chromium", headless: bool = False) -> Browser:
    """Get or create browser instance."""
    global _browser, _playwright
    
    if _browser is None or not _browser.is_connected():
        _playwright = await async_playwright().start()
        browser_launcher = getattr(_playwright, browser_type)
        _browser = await browser_launcher.launch(headless=headless)
    
    return _browser


async def get_context() -> BrowserContext:
    """Get or create browser context."""
    global _context, _browser
    
    if _context is None:
        browser = await get_browser()
        _context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
    
    return _context


async def get_page() -> Page:
    """Get or create page."""
    global _page, _context
    
    if _page is None or _page.is_closed():
        context = await get_context()
        _page = await context.new_page()
    
    return _page


@tool(category="browser")
async def open_browser(url: str) -> str:
    """
    Open a URL in the browser.
    
    Args:
        url: The URL to open (e.g., "https://www.google.com")
    
    Returns:
        Status message with page title
    """
    try:
        page = await get_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        title = await page.title()
        return f"Successfully opened {url} - Title: {title}"
    except Exception as e:
        return f"Failed to open {url}: {str(e)}"


@tool(category="browser")
async def close_browser() -> str:
    """
    Close the browser and clean up resources.
    
    Returns:
        Status message
    """
    global _page, _context, _browser, _playwright
    
    try:
        if _page:
            await _page.close()
            _page = None
        if _context:
            await _context.close()
            _context = None
        if _browser:
            await _browser.close()
            _browser = None
        if _playwright:
            await _playwright.stop()
            _playwright = None
        
        return "Browser closed successfully"
    except Exception as e:
        return f"Error closing browser: {str(e)}"


@tool(category="browser")
async def click_element(selector: str, description: str = "") -> str:
    """
    Click an element on the page.
    
    Args:
        selector: CSS selector for the element (e.g., "button#submit", "a[href='/login']")
        description: Optional description of what's being clicked
    
    Returns:
        Status message
    """
    try:
        page = await get_page()
        element = await page.wait_for_selector(selector, timeout=5000)
        await element.click()
        
        desc = f" ({description})" if description else ""
        return f"Clicked element '{selector}'{desc}"
    except Exception as e:
        return f"Failed to click '{selector}': {str(e)}"


@tool(category="browser")
async def type_text(selector: str, text: str, clear_first: bool = True) -> str:
    """
    Type text into an input field.
    
    Args:
        selector: CSS selector for the input element
        text: Text to type
        clear_first: Whether to clear existing content first
    
    Returns:
        Status message
    """
    try:
        page = await get_page()
        element = await page.wait_for_selector(selector, timeout=5000)
        
        if clear_first:
            await element.fill("")
        
        await element.type(text, delay=50)  # 50ms delay between keystrokes
        return f"Typed '{text[:30]}...' into '{selector}'" if len(text) > 30 else f"Typed '{text}' into '{selector}'"
    except Exception as e:
        return f"Failed to type into '{selector}': {str(e)}"


@tool(category="browser")
async def get_page_content() -> str:
    """
    Get the text content of the current page.
    
    Returns:
        Page text content (truncated to 2000 chars)
    """
    try:
        page = await get_page()
        content = await page.inner_text("body")
        return content[:2000] + ("..." if len(content) > 2000 else "")
    except Exception as e:
        return f"Failed to get page content: {str(e)}"


@tool(category="browser")
async def take_screenshot(filename: str = "screenshot.png") -> str:
    """
    Take a screenshot of the current page.
    
    Args:
        filename: Filename to save the screenshot
    
    Returns:
        Path to saved screenshot
    """
    try:
        page = await get_page()
        path = Path(filename)
        await page.screenshot(path=str(path.absolute()))
        return f"Screenshot saved to {path.absolute()}"
    except Exception as e:
        return f"Failed to take screenshot: {str(e)}"


@tool(category="browser")
async def run_in_colab(script_content: str, timeout_seconds: int = 60) -> str:
    """
    Open Google Colab and paste Python code to execute.
    
    This is a specialized tool for running Python code in Google Colab environment.
    
    Args:
        script_content: Python code to execute in Colab
        timeout_seconds: Maximum time to wait for execution
    
    Returns:
        Execution status and output (if available)
    """
    try:
        page = await get_page()
        
        # Step 1: Navigate to Colab
        await page.goto("https://colab.research.google.com", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)  # Wait for UI to load
        
        # Step 2: Click "New Notebook" or handle welcome dialog
        try:
            # Try to click "File" menu then "New notebook"
            await page.click('text="File"', timeout=5000)
            await asyncio.sleep(0.5)
            await page.click('text="New notebook"', timeout=5000)
        except:
            # Alternative: look for "New Notebook" button directly
            try:
                await page.click('button:has-text("New Notebook")', timeout=5000)
            except:
                pass  # May already be in a notebook
        
        await asyncio.sleep(3)  # Wait for notebook to initialize
        
        # Step 3: Find the code cell and paste content
        # Colab uses CodeMirror for code editing
        try:
            # Click in the code cell area
            code_cell = await page.wait_for_selector('.input-area', timeout=10000)
            await code_cell.click()
            await asyncio.sleep(0.5)
            
            # Select all and delete (clear existing content)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Delete")
            await asyncio.sleep(0.5)
            
            # Paste the script content
            await page.keyboard.type(script_content, delay=30)
            await asyncio.sleep(1)
            
            # Step 4: Execute the cell (Shift+Enter)
            await page.keyboard.press("Shift+Enter")
            
            # Step 5: Wait for execution
            await asyncio.sleep(min(timeout_seconds, 10))  # Initial wait
            
            # Check for output
            try:
                output_element = await page.wait_for_selector('.output-area', timeout=5000)
                output_text = await output_element.inner_text()
                
                if output_text:
                    return f"Colab execution completed. Output:\n{output_text[:500]}"
            except:
                pass
            
            return "Code pasted and executed in Colab. Check browser for results."
            
        except Exception as e:
            return f"Failed to interact with Colab: {str(e)}"
            
    except Exception as e:
        return f"Failed to open Colab: {str(e)}"


@tool(category="browser")
async def search_google(query: str) -> str:
    """
    Perform a Google search.
    
    Args:
        query: Search query string
    
    Returns:
        Search results summary
    """
    try:
        # Encode query for URL
        from urllib.parse import quote
        encoded_query = quote(query)
        url = f"https://www.google.com/search?q={encoded_query}"
        
        page = await get_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        # Wait for results
        await asyncio.sleep(2)
        
        # Get result titles
        try:
            titles = await page.query_selector_all('h3')
            results = []
            for title in titles[:5]:  # Top 5 results
                text = await title.inner_text()
                if text:
                    results.append(f"- {text}")
            
            return f"Search results for '{query}':\n" + "\n".join(results)
        except:
            return f"Opened Google search for '{query}'"
            
    except Exception as e:
        return f"Failed to search Google: {str(e)}"


@tool(category="browser")
async def press_key(key: str) -> str:
    """
    Press a keyboard key on the page.
    
    Common keys: Enter, Tab, Escape, ArrowUp, ArrowDown, etc.
    
    Args:
        key: Key name to press
    
    Returns:
        Status message
    """
    try:
        page = await get_page()
        await page.keyboard.press(key)
        return f"Pressed key: {key}"
    except Exception as e:
        return f"Failed to press key '{key}': {str(e)}"
