"""
Ollama LLM provider with async support.
"""
import ollama
from typing import List, Dict, AsyncGenerator, Optional, Any
import asyncio


class LLMProvider:
    """Async Ollama client for LLM interactions."""
    
    def __init__(self, model: str = "qwen2.5-coder:7b", 
                 base_url: str = "http://localhost:11434",
                 context_limit: int = 10):
        self.model = model
        self.base_url = base_url
        self.context_limit = context_limit
        self.client = ollama.AsyncClient(host=base_url)
        self.tools_supported: Optional[bool] = None
        
        # Conversation history management
        self.history: List[Dict[str, str]] = []
    
    def _truncate_history(self):
        """Keep only the last N turns of conversation."""
        if len(self.history) > self.context_limit * 2:  # *2 because each turn has user+assistant
            # Keep system message if exists, then last N turns
            system_msg = None
            if self.history and self.history[0].get('role') == 'system':
                system_msg = self.history[0]
            
            self.history = self.history[-self.context_limit * 2:]
            
            if system_msg:
                self.history.insert(0, system_msg)
    
    def set_system_prompt(self, prompt: str):
        """Set or update system prompt."""
        if self.history and self.history[0].get('role') == 'system':
            self.history[0]['content'] = prompt
        else:
            self.history.insert(0, {"role": "system", "content": prompt})
    
    async def chat(self, message: str, tools: List[Dict] = None) -> Dict[str, Any]:
        """
        Send a message and get a response.
        
        Args:
            message: User message
            tools: Optional list of tool definitions for function calling
        
        Returns:
            Dictionary containing assistant content and tool call metadata
        """
        # Add user message to history
        self.history.append({"role": "user", "content": message})
        self._truncate_history()
        
        try:
            # Prepare request
            kwargs = {
                'model': self.model,
                'messages': self.history.copy(),
                'stream': False,
            }
            
            if tools and self.tools_supported is not False:
                kwargs['tools'] = tools
            
            # Call Ollama API
            response = await self.client.chat(**kwargs)
            
            # Extract response
            assistant_data = response.get('message', {})
            assistant_message = assistant_data.get('content', '')
            tool_calls = assistant_data.get('tool_calls', []) or []
            
            # Add to history
            self.history.append({"role": "assistant", "content": assistant_message})
            
            return {
                "content": assistant_message,
                "tool_calls": tool_calls,
                "raw": response,
            }
            
        except Exception as e:
            error_text = str(e)

            if tools and self.tools_supported is not False and (
                "does not support tools" in error_text.lower()
                or "status code: 400" in error_text.lower()
            ):
                self.tools_supported = False

                try:
                    fallback_response = await self.client.chat(
                        model=self.model,
                        messages=self.history.copy(),
                        stream=False,
                    )

                    assistant_data = fallback_response.get('message', {})
                    assistant_message = assistant_data.get('content', '')

                    self.history.append({"role": "assistant", "content": assistant_message})

                    return {
                        "content": assistant_message,
                        "tool_calls": [],
                        "raw": fallback_response,
                    }
                except Exception as fallback_error:
                    error_msg = f"LLM Error: {str(fallback_error)}"
                    self.history.append({"role": "assistant", "content": error_msg})
                    return {
                        "content": error_msg,
                        "tool_calls": [],
                        "raw": None,
                    }

            error_msg = f"LLM Error: {str(e)}"
            self.history.append({"role": "assistant", "content": error_msg})
            return {
                "content": error_msg,
                "tool_calls": [],
                "raw": None,
            }
    
    async def chat_stream(self, message: str, tools: List[Dict] = None) -> AsyncGenerator[str, None]:
        """
        Stream a response token by token.
        
        Yields:
            Response tokens as they arrive
        """
        # Add user message to history
        self.history.append({"role": "user", "content": message})
        self._truncate_history()
        
        try:
            # Prepare request
            kwargs = {
                'model': self.model,
                'messages': self.history.copy(),
                'stream': True,
            }
            
            if tools:
                kwargs['tools'] = tools
            
            # Stream response
            full_response = ""
            async for chunk in await self.client.chat(**kwargs):
                content = chunk['message']['content']
                full_response += content
                yield content
            
            # Add complete response to history
            self.history.append({"role": "assistant", "content": full_response})
            
        except Exception as e:
            error_msg = f"LLM Error: {str(e)}"
            yield error_msg
            self.history.append({"role": "assistant", "content": error_msg})
    
    def clear_history(self):
        """Clear conversation history but keep system prompt."""
        system_msg = None
        if self.history and self.history[0].get('role') == 'system':
            system_msg = self.history[0]
        
        self.history = []
        
        if system_msg:
            self.history.append(system_msg)
    
    def get_history(self) -> List[Dict]:
        """Get current conversation history."""
        return self.history.copy()
