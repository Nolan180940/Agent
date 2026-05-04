"""
Agent core logic with ReAct loop and confirmation mechanism.
"""
import json
import asyncio
from typing import Dict, List, Optional, Callable, Any
from enum import Enum

from llm_provider import LLMProvider
from tools.base import get_all_tools, Tool, TOOL_REGISTRY
from database import Database


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
        
        # Set system prompt
        self._setup_system_prompt()
    
    def _setup_system_prompt(self):
        """Set up the agent's system prompt with tool information."""
        tools_info = []
        for name, info in TOOL_REGISTRY.items():
            params = ", ".join(info["parameters"]["properties"].keys())
            tools_info.append(f"- {name}({params}): {info['description']}")
        
        system_prompt = f"""You are an AI assistant that can control the user's computer to help them complete tasks.

## Available Tools
{chr(10).join(tools_info)}

## Instructions
1. Think step-by-step about what needs to be done
2. Use tools to accomplish tasks
3. For browser operations, use browser.* tools
4. For Windows operations, use system.* tools  
5. For code execution, use code.* tools
6. Always explain what you're doing before doing it
7. If a tool fails, try to recover or ask for help
8. When finished, summarize what was accomplished

## Important Safety Notes
- The user will see all your actions and must confirm dangerous operations
- Never attempt to bypass safety measures
- If unsure about something, ask the user for clarification
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
    
    def _parse_tool_call(self, response: str) -> Optional[Dict]:
        """
        Parse tool call from LLM response.
        
        Looks for patterns like:
        - Tool: tool_name(param1="value1", param2="value2")
        - Call tool_name with param1="value1"
        - ```json {"tool": "name", "params": {...}} ```
        """
        # Try JSON format first
        import re
        json_match = re.search(r'```(?:json)?\s*({"tool"[^}]+})\s*```', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try Tool: pattern
        tool_match = re.search(r'Tool:\s*(\w+)\(([^)]*)\)', response)
        if tool_match:
            tool_name = tool_match.group(1)
            params_str = tool_match.group(2)
            
            # Parse parameters (simple key=value parsing)
            params = {}
            if params_str.strip():
                for param in re.findall(r'(\w+)=(?:"([^"]*)"|\'([^\']*)\'|(\d+))', params_str):
                    key = param[0]
                    value = param[1] or param[2] or param[3]
                    if value.isdigit():
                        value = int(value)
                    params[key] = value
            
            return {"tool": tool_name, "params": params}
        
        return None
    
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
            response = await self.llm.chat(full_prompt)
            
            self._log("DEBUG", f"LLM response: {response[:200]}...")
            
            # Check if response contains tool call
            tool_call = self._parse_tool_call(response)
            
            if tool_call:
                # Execute the tool
                tool_name = tool_call.get("tool")
                parameters = tool_call.get("params", {})
                
                self._log("INFO", f"Planning to call: {tool_name}", json.dumps(parameters))
                
                result = await self.execute_tool(tool_name, parameters)
                
                # Add tool interaction to history
                conversation_history.append(f"Assistant: Calling {tool_name}({parameters})")
                conversation_history.append(f"Tool Result: {result}")
                
                # Continue the loop to process next action
                continue
            else:
                # No tool call - this is the final response
                self._update_status(AgentStatus.IDLE)
                self._log("INFO", f"Response: {response[:200]}...")
                return response
        
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
