"""
Agent core logic with ReAct loop and confirmation mechanism.
"""
import ast
import inspect
import json
import asyncio
from typing import Dict, List, Optional, Callable, Any
from enum import Enum

from llm_provider import LLMProvider
from tools import get_all_tools, Tool, TOOL_REGISTRY
from database import Database

# Inject VLM provider into vision tools if available
try:
    from tools.vision import set_vlm_provider
except ImportError:
    set_vlm_provider = None


class AgentStatus(Enum):
    """Agent status for UI display."""
    IDLE = "idle"
    THINKING = "thinking"
    WAITING_CONFIRMATION = "waiting_confirmation"
    EXECUTING = "executing"
    ERROR = "error"


class AgentCore:
    """
    Core agent logic implementing ReAct (Reasoning + Acting) pattern.
    
    Features:
    - Multi-turn conversation with tool calling
    - Safety confirmation before tool execution
    - Error recovery and retry logic
    - Context window management
    """
    
    def __init__(self, llm: LLMProvider, db: Database, 
                 security_mode: str = "safe",
                 max_iterations: int = 10):
        self.llm = llm
        self.db = db
        self.security_mode = security_mode  # "safe" or "trusted"
        self.max_iterations = max_iterations
        
        # Status tracking
        self.status = AgentStatus.IDLE
        self.current_task_id: Optional[int] = None
        
        # Callbacks for UI updates
        self.on_status_change: Optional[Callable] = None
        self.on_log: Optional[Callable] = None
        self.on_confirmation_request: Optional[Callable] = None
        
        # Inject VLM provider into vision tools for screen analysis
        if set_vlm_provider and llm.provider == "siliconflow":
            set_vlm_provider(llm)
        
        # Set system prompt
        self._setup_system_prompt()
    
    def _setup_system_prompt(self):
        """Set up the agent's system prompt with tool information."""
        tools_info = []
        for name, info in TOOL_REGISTRY.items():
            params = ", ".join(info["parameters"]["properties"].keys())
            tools_info.append(f"- {name}({params}): {info['description']}")
        
        system_prompt = f"""You are a Computer Use AI assistant — you can see the screen, control the mouse & keyboard, run shell commands, and operate the browser to help users complete tasks on their Windows computer.

## Available Tools
{chr(10).join(tools_info)}

## Computer Use Instructions
1. **Think step-by-step** about what needs to be done before acting.
2. **See the screen**: Use `take_screenshot` + `analyze_screen` to understand what's visible.
3. **Find elements**: Use `find_ui_element` to locate buttons, fields, icons by description.
4. **Read text**: Use `read_screen_text` to extract visible text from the screen.
5. **Control mouse**: Use `get_mouse_position`, `move_mouse`, `click_mouse` to interact.
6. **Control keyboard**: Use `type_text`, `press_keys` for keyboard input.
7. **Run commands**: Use `run_powershell`, `run_git_bash`, `run_cmd` for shell operations.
8. **Clipboard**: Use `get_clipboard` / `set_clipboard` to read/write clipboard.
9. **Browser**: Use `open_browser`, `click_element`, `type_text` (browser) for web tasks.
10. **Code**: Use `run_python_code` for calculations and data processing.

## Computer Use Workflow
When asked to do something on the computer:
1. Take a screenshot to see the current state
2. Analyze the screen to understand what's there
3. Plan the sequence of actions (mouse moves, clicks, typing)
4. Execute actions one by one, checking results
5. When finished, summarize what was accomplished

## Tool Output Format
If native tool calling is unavailable, respond with exactly one executable tool call in one of these formats:
- Tool: tool_name(param1="value1", param2=123)
- ```json
    {{"tool": "tool_name", "params": {{"param1": "value1", "param2": 123}}}}
    ```

Do not wrap tool calls in extra explanation when you intend to execute an action.

## Important Safety Notes
- The user will see all your actions and must confirm dangerous operations
- Never attempt to bypass safety measures
- If unsure about something, ask the user for clarification
- For shell commands, prefer PowerShell on Windows; use Git Bash for git/Unix-style operations
"""
        
        self.llm.set_system_prompt(system_prompt)
    
    def _update_status(self, status: AgentStatus):
        """Update agent status and notify callback."""
        self.status = status
        if self.on_status_change:
            self.on_status_change(status)
    
    def _log(self, level: str, message: str, details: str = None):
        """Log a message and notify callback."""
        self.db.add_log(level, message, self.current_task_id, details)
        if self.on_log:
            self.on_log(level, message, details)
    
    async def _get_user_confirmation(self, tool_name: str, parameters: Dict) -> bool:
        """Request user confirmation for tool execution."""
        if self.security_mode == "trusted" and self.current_task_id:
            # Check if task is trusted
            task = self.db.get_task(self.current_task_id)
            if task and task.get("is_trusted"):
                return True
        
        # Always require confirmation in safe mode or for untrusted tasks
        if self.on_confirmation_request:
            self._update_status(AgentStatus.WAITING_CONFIRMATION)
            return await self.on_confirmation_request(tool_name, parameters)
        
        # Default to requiring confirmation
        return False
    
    def _parse_arguments(self, tool_name: str, args_source: str) -> Optional[Dict[str, Any]]:
        """Bind positional and keyword arguments to the registered tool signature."""
        try:
            signature = inspect.signature(TOOL_REGISTRY[tool_name]["function"])
            call = ast.parse(f"_tool({args_source})", mode="eval").body
            if not isinstance(call, ast.Call):
                return None

            positional_args = [ast.literal_eval(arg) for arg in call.args]
            keyword_args = {kw.arg: ast.literal_eval(kw.value) for kw in call.keywords if kw.arg}

            bound = signature.bind_partial(*positional_args, **keyword_args)
            return dict(bound.arguments)
        except Exception:
            return None

    def _extract_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """Extract tool calls from structured or code-like LLM output."""
        import re

        tool_calls: List[Dict[str, Any]] = []

        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1))
                if isinstance(parsed, dict) and parsed.get("tool"):
                    params = parsed.get("params", {})
                    if isinstance(params, dict):
                        tool_calls.append({"tool": parsed["tool"], "params": params})
                        return tool_calls
            except json.JSONDecodeError:
                pass

        tool_match = re.search(r'Tool:\s*(\w+)\((.*?)\)', response, re.DOTALL)
        if tool_match:
            tool_name = tool_match.group(1)
            params = self._parse_arguments(tool_name, tool_match.group(2).strip())
            if params is not None:
                tool_calls.append({"tool": tool_name, "params": params})
                return tool_calls

        fenced_blocks = re.findall(r'```(?:python)?\s*(.*?)\s*```', response, re.DOTALL)
        search_blocks = fenced_blocks if fenced_blocks else [response]

        for block in search_blocks:
            for match in re.finditer(r'\b([A-Za-z_][\w]*)\((.*?)\)', block, re.DOTALL):
                tool_name = match.group(1)
                if tool_name not in TOOL_REGISTRY:
                    continue

                params = self._parse_arguments(tool_name, match.group(2).strip())
                if params is None:
                    continue

                tool_calls.append({"tool": tool_name, "params": params})

        return tool_calls
    
    async def execute_tool(self, tool_name: str, parameters: Dict) -> str:
        """Execute a tool with error handling and logging."""
        self._update_status(AgentStatus.EXECUTING)
        
        # Check if tool exists
        if tool_name not in TOOL_REGISTRY:
            error_msg = f"Unknown tool: {tool_name}"
            self._log("ERROR", error_msg)
            return error_msg
        
        # Request confirmation
        confirmed = await self._get_user_confirmation(tool_name, parameters)
        if not confirmed:
            msg = f"Tool execution cancelled by user: {tool_name}"
            self._log("INFO", msg, json.dumps(parameters))
            return msg
        
        # Execute the tool
        try:
            self._log("INFO", f"Executing tool: {tool_name}", json.dumps(parameters))
            
            func = TOOL_REGISTRY[tool_name]["function"]
            
            # Handle async vs sync functions
            if asyncio.iscoroutinefunction(func):
                result = await func(**parameters)
            else:
                result = func(**parameters)
            
            # Record execution
            self.db.record_tool_execution(
                tool_name=tool_name,
                parameters=parameters,
                result=str(result),
                status="success",
                task_id=self.current_task_id,
                confirmed_by_user=True
            )
            
            self._log("INFO", f"Tool completed: {tool_name}", str(result)[:200])
            return str(result)
            
        except Exception as e:
            error_msg = f"Tool execution failed: {str(e)}"
            self._log("ERROR", error_msg)
            
            # Record failure
            self.db.record_tool_execution(
                tool_name=tool_name,
                parameters=parameters,
                result=error_msg,
                status="failed",
                task_id=self.current_task_id,
                confirmed_by_user=True
            )
            
            return error_msg
    
    async def process_message(self, message: str, task_id: int = None) -> str:
        """
        Process a user message through the ReAct loop.
        
        Args:
            message: User's instruction
            task_id: Optional task ID for tracking
        
        Returns:
            Final response to user
        """
        self.current_task_id = task_id
        self._update_status(AgentStatus.THINKING)
        
        conversation_history = []
        
        for iteration in range(self.max_iterations):
            # Build context with conversation history
            context = "\n".join(conversation_history) if conversation_history else ""
            
            if context:
                full_prompt = f"{context}\n\nUser: {message}"
            else:
                full_prompt = message
            
            # Get LLM response
            self._log("DEBUG", f"LLM thinking (iteration {iteration + 1})")
            response = await self.llm.chat(full_prompt, tools=get_all_tools())

            if isinstance(response, dict):
                response_text = response.get("content", "") or ""
                tool_calls = response.get("tool_calls", []) or []
            else:
                response_text = str(response)
                tool_calls = []

            self._log("DEBUG", f"LLM response: {response_text[:200]}...")

            extracted_calls: List[Dict[str, Any]] = []

            if tool_calls:
                for call in tool_calls:
                    function_call = call.get("function", call)
                    tool_name = function_call.get("name") or call.get("name")
                    parameters = function_call.get("arguments") or call.get("arguments") or {}

                    if isinstance(parameters, str):
                        try:
                            parameters = json.loads(parameters)
                        except json.JSONDecodeError:
                            parameters = {}

                    if tool_name and isinstance(parameters, dict):
                        extracted_calls.append({"tool": tool_name, "params": parameters})
            else:
                extracted_calls = self._extract_tool_calls(response_text)

            if extracted_calls:
                for tool_call in extracted_calls:
                    tool_name = tool_call.get("tool")
                    parameters = tool_call.get("params", {})

                    self._log("INFO", f"Planning to call: {tool_name}", json.dumps(parameters))

                    result = await self.execute_tool(tool_name, parameters)

                    conversation_history.append(f"Assistant: Called {tool_name}({parameters})")
                    conversation_history.append(f"Tool Result: {result}")

                # Tool execution complete - now ask LLM to summarize and decide if done
                conversation_history.append("Tool execution completed. Now summarize what was accomplished. Do not make any more tool calls unless absolutely necessary to complete the task.")
                
                # Get final response from LLM
                full_prompt = f"{chr(10).join(conversation_history)}\n\nUser: {message}"
                self._log("DEBUG", f"LLM thinking (final response)")
                final_response = await self.llm.chat(full_prompt, tools=get_all_tools())
                
                if isinstance(final_response, dict):
                    response_text = final_response.get("content", "") or ""
                else:
                    response_text = str(final_response)
                
                self._update_status(AgentStatus.IDLE)
                self._log("INFO", f"Response: {response_text[:200]}...")
                return response_text

            self._update_status(AgentStatus.IDLE)
            self._log("INFO", f"Response: {response_text[:200]}...")
            return response_text
        
        # Max iterations reached
        self._update_status(AgentStatus.ERROR)
        self._log("ERROR", "Max iterations reached without completing task")
        return "I'm having trouble completing this task. Could you provide more specific instructions?"
    
    async def run_workflow(self, workflow: List[Dict], task_id: int = None) -> str:
        """
        Run a predefined workflow (sequence of tool calls).
        
        Args:
            workflow: List of tool calls [{"tool": "...", "params": {...}}, ...]
            task_id: Task ID for tracking
        
        Returns:
            Execution summary
        """
        self.current_task_id = task_id
        results = []
        
        for step in workflow:
            tool_name = step.get("tool")
            parameters = step.get("params", {})
            
            if not tool_name:
                results.append(f"Skipped invalid step: {step}")
                continue
            
            result = await self.execute_tool(tool_name, parameters)
            results.append(f"{tool_name}: {result}")
        
        self._update_status(AgentStatus.IDLE)
        return "\n".join(results)
    
    def set_security_mode(self, mode: str):
        """Switch between safe and trusted modes."""
        if mode in ["safe", "trusted"]:
            self.security_mode = mode
            self._log("INFO", f"Security mode changed to: {mode}")
        else:
            raise ValueError(f"Invalid security mode: {mode}")
    
    def reset(self):
        """Reset agent state."""
        self.current_task_id = None
        self.llm.clear_history()
        self._update_status(AgentStatus.IDLE)
        self._log("INFO", "Agent reset")
