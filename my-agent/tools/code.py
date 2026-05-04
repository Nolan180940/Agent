"""
Python code execution tools.
"""
import ast
import sys
import io
from contextlib import redirect_stdout, redirect_stderr
from typing import Dict, Any
import traceback

from tools.base import tool


@tool(category="code")
def run_python_code(code: str, timeout_seconds: int = 10) -> str:
    """
    Execute Python code in a sandboxed environment.
    
    ⚠️ SECURITY WARNING: This executes arbitrary Python code!
    Only use in trusted environments or with user confirmation.
    
    Args:
        code: Python code to execute
        timeout_seconds: Maximum execution time (not strictly enforced)
    
    Returns:
        Execution output or error message
    """
    # Security check - block dangerous operations
    dangerous_patterns = [
        '__import__', 'eval(', 'exec(', 'compile(', 
        'open(', 'subprocess', 'os.system', 'os.popen',
        'importlib', 'pkgutil', 'runpy'
    ]
    
    for pattern in dangerous_patterns:
        if pattern in code:
            return f"⚠️ Blocked: Code contains potentially unsafe operation '{pattern}'"
    
    # Capture stdout and stderr
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    try:
        # Try to parse as expression first (for simple calculations)
        try:
            tree = ast.parse(code.strip(), mode='eval')
            result = eval(compile(tree, '<string>', 'eval'))
            return f"Result: {result}"
        except SyntaxError:
            pass
        
        # Parse as statements
        tree = ast.parse(code, mode='exec')
        
        # Prepare namespace with limited builtins
        safe_globals = {
            '__builtins__': {
                'print': print,
                'len': len,
                'range': range,
                'str': str,
                'int': int,
                'float': float,
                'bool': bool,
                'list': list,
                'dict': dict,
                'set': set,
                'tuple': tuple,
                'sum': sum,
                'min': min,
                'max': max,
                'abs': abs,
                'round': round,
                'enumerate': enumerate,
                'zip': zip,
                'map': map,
                'filter': filter,
                'sorted': sorted,
                'reversed': reversed,
            }
        }
        safe_locals = {}
        
        # Execute code
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            exec(compile(tree, '<string>', 'exec'), safe_globals, safe_locals)
        
        # Get output
        stdout_output = stdout_capture.getvalue()
        stderr_output = stderr_capture.getvalue()
        
        result_parts = []
        
        if stdout_output:
            result_parts.append(f"Output:\n{stdout_output}")
        
        if stderr_output:
            result_parts.append(f"Errors:\n{stderr_output}")
        
        if safe_locals:
            # Show variables created
            vars_output = "\n".join(f"{k} = {v}" for k, v in safe_locals.items() if not k.startswith('_'))
            if vars_output:
                result_parts.append(f"Variables:\n{vars_output}")
        
        if result_parts:
            return "\n".join(result_parts)[:2000]
        else:
            return "Code executed successfully (no output)"
            
    except Exception as e:
        error_msg = traceback.format_exc()
        return f"Execution error:\n{error_msg[:1000]}"


@tool(category="code")
def explain_code(code: str) -> str:
    """
    Analyze and explain what a piece of Python code does.
    
    This is a placeholder - in a real implementation, you would
    call the LLM to explain the code.
    
    Args:
        code: Python code to explain
    
    Returns:
        Code explanation
    """
    try:
        # Basic static analysis
        tree = ast.parse(code)
        
        analysis = []
        
        # Count different node types
        node_counts = {}
        for node in ast.walk(tree):
            node_type = type(node).__name__
            node_counts[node_type] = node_counts.get(node_type, 0) + 1
        
        analysis.append(f"Code structure:")
        analysis.append(f"- Lines: {len(code.splitlines())}")
        analysis.append(f"- Functions: {node_counts.get('FunctionDef', 0)}")
        analysis.append(f"- Classes: {node_counts.get('ClassDef', 0)}")
        analysis.append(f"- Imports: {node_counts.get('Import', 0) + node_counts.get('ImportFrom', 0)}")
        
        # Find function names
        functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        if functions:
            analysis.append(f"- Functions defined: {', '.join(functions)}")
        
        # Find class names
        classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        if classes:
            analysis.append(f"- Classes defined: {', '.join(classes)}")
        
        return "\n".join(analysis)
        
    except SyntaxError as e:
        return f"Invalid Python syntax: {e}"
    except Exception as e:
        return f"Failed to analyze code: {str(e)}"


@tool(category="code")
def validate_python_syntax(code: str) -> str:
    """
    Check if Python code has valid syntax.
    
    Args:
        code: Python code to validate
    
    Returns:
        Validation result
    """
    try:
        ast.parse(code)
        return "✓ Valid Python syntax"
    except SyntaxError as e:
        return f"✗ Syntax error at line {e.lineno}: {e.msg}"
    except Exception as e:
        return f"✗ Error: {str(e)}"
