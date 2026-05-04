"""
Tools package initialization - auto-discovers and registers all tools.
"""
import importlib
from pathlib import Path

# Import base first to set up the registry
from tools.base import tool, Tool, get_all_tools, get_tool_names, TOOL_REGISTRY

# Auto-discover and import all tool modules
TOOLS_DIR = Path(__file__).parent

def _auto_discover_tools():
    """Automatically discover and import all tool modules."""
    for file_path in TOOLS_DIR.glob("*.py"):
        if file_path.name.startswith("_"):
            continue
        
        module_name = file_path.stem
        try:
            importlib.import_module(f"tools.{module_name}")
            print(f"Loaded tools from: {module_name}")
        except Exception as e:
            print(f"Warning: Failed to load tools from {module_name}: {e}")


# Auto-discover on import
_auto_discover_tools()


__all__ = [
    'tool',
    'Tool', 
    'get_all_tools',
    'get_tool_names',
    'TOOL_REGISTRY',
]
