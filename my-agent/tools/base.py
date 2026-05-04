"""
Tool base class and decorator for automatic registration.
"""
from typing import Callable, Dict, Any, List
import inspect
import functools


# Global registry for tools
TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {}


def tool(func: Callable = None, *, name: str = None, 
         description: str = None, category: str = "general"):
    """
    Decorator to register a function as a tool.
    
    Can be used as @tool or @tool(name="custom_name", description="...")
    
    Args:
        func: The function to decorate
        name: Optional custom name for the tool
        description: Optional custom description (auto-extracted from docstring if not provided)
        category: Category for grouping tools (e.g., "browser", "system", "code")
    """
    def decorator(fn: Callable):
        # Extract function signature
        sig = inspect.signature(fn)
        
        # Build parameter schema
        parameters = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        for param_name, param in sig.parameters.items():
            param_type = "string"  # default
            
            # Infer type from annotation
            if param.annotation != inspect.Parameter.empty:
                if param.annotation == int:
                    param_type = "integer"
                elif param.annotation == float:
                    param_type = "number"
                elif param.annotation == bool:
                    param_type = "boolean"
                elif param.annotation == dict:
                    param_type = "object"
                elif param.annotation == list:
                    param_type = "array"
            
            parameters["properties"][param_name] = {
                "type": param_type,
                "description": f"Parameter {param_name}"
            }
            
            # Check if required (no default value)
            if param.default == inspect.Parameter.empty:
                parameters["required"].append(param_name)
        
        # Get description from docstring if not provided
        tool_description = description or fn.__doc__ or "No description available"
        tool_description = tool_description.strip().split('\n')[0]  # First line only
        
        # Register tool
        tool_name = name or fn.__name__
        TOOL_REGISTRY[tool_name] = {
            "name": tool_name,
            "description": tool_description,
            "function": fn,
            "parameters": parameters,
            "category": category,
        }
        
        # Preserve original function metadata
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            # Handle both sync and async functions
            if inspect.iscoroutine(result):
                return await result
            return result
        
        return wrapper
    
    if func is not None:
        return decorator(func)
    return decorator


class Tool:
    """Base class for tool collections (optional, can also use @tool decorator directly)."""
    
    @classmethod
    def get_tools(cls) -> List[Dict]:
        """Get all registered tools in Ollama function-calling format."""
        tools = []
        for tool_info in TOOL_REGISTRY.values():
            tools.append({
                "type": "function",
                "function": {
                    "name": tool_info["name"],
                    "description": tool_info["description"],
                    "parameters": tool_info["parameters"],
                }
            })
        return tools
    
    @classmethod
    def get_tool_by_name(cls, name: str):
        """Get a tool function by name."""
        if name in TOOL_REGISTRY:
            return TOOL_REGISTRY[name]["function"]
        return None
    
    @classmethod
    def execute_tool(cls, name: str, **kwargs):
        """Execute a tool by name with given parameters."""
        if name not in TOOL_REGISTRY:
            raise ValueError(f"Unknown tool: {name}")
        
        func = TOOL_REGISTRY[name]["function"]
        
        # Call the function
        result = func(**kwargs)
        
        # Handle async functions
        if inspect.iscoroutine(result):
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            return loop.run_until_complete(result)
        
        return result
    
    @classmethod
    def get_tool_schema(cls, name: str) -> Dict:
        """Get tool schema for LLM function calling."""
        if name not in TOOL_REGISTRY:
            return None
        
        info = TOOL_REGISTRY[name]
        return {
            "type": "function",
            "function": {
                "name": info["name"],
                "description": info["description"],
                "parameters": info["parameters"],
            }
        }


def get_all_tools() -> List[Dict]:
    """Get all registered tools in Ollama format."""
    return Tool.get_tools()


def get_tool_names() -> List[str]:
    """Get list of all registered tool names."""
    return list(TOOL_REGISTRY.keys())
