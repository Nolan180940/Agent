"""
Multi-provider LLM backend: Ollama (local) + SiliconFlow (cloud, OpenAI-compatible).

Supports:
- Text chat with tool calling (both providers)
- Vision chat with image input (SiliconFlow VLM models)
- Streaming responses
"""
import base64
import json
import os
from pathlib import Path
from typing import List, Dict, AsyncGenerator, Optional, Any, Union

import aiohttp


# ── SiliconFlow recommended models ──────────────────────────────────────────
# Vision (VLM):  Qwen/Qwen3-VL-32B-Instruct, Qwen/Qwen2.5-VL-72B-Instruct,
#                Qwen/Qwen2.5-VL-32B-Instruct, Qwen/Qwen2.5-VL-7B-Instruct
# Language (LLM): deepseek-ai/DeepSeek-V4-Pro, deepseek-ai/DeepSeek-V4-Flash,
#                 Pro/moonshotai/Kimi-K2.6, Pro/zai-org/GLM-5.1,
#                 Qwen/Qwen3-235B-A22B, MiniMax-M2.5, nex-agi/Nex-N2-Pro
# ────────────────────────────────────────────────────────────────────────────

SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"


class LLMProvider:
    """Multi-provider LLM client (Ollama local + SiliconFlow cloud)."""

    def __init__(
        self,
        model: str = "deepseek-ai/DeepSeek-V4-Flash",
        base_url: str = "http://localhost:11434",
        context_limit: int = 10,
        provider: str = "siliconflow",          # "ollama" | "siliconflow"
        api_key: str = "",
        vision_model: str = "Qwen/Qwen3-VL-32B-Instruct",
    ):
        self.model = model
        self.base_url = base_url
        self.context_limit = context_limit
        self.provider = provider
        self.api_key = api_key or os.getenv("SILICONFLOW_API_KEY", "")
        self.vision_model = vision_model
        self.tools_supported: Optional[bool] = None

        # Conversation history
        self.history: List[Dict[str, Any]] = []

        # Lazy Ollama client
        self._ollama_client = None

    # ── helpers ─────────────────────────────────────────────────────────────

    def _get_ollama_client(self):
        if self._ollama_client is None:
            import ollama
            self._ollama_client = ollama.AsyncClient(host=self.base_url)
        return self._ollama_client

    def _truncate_history(self):
        if len(self.history) > self.context_limit * 2:
            system_msg = None
            if self.history and self.history[0].get("role") == "system":
                system_msg = self.history[0]
            self.history = self.history[-self.context_limit * 2:]
            if system_msg:
                self.history.insert(0, system_msg)

    def set_system_prompt(self, prompt: str):
        if self.history and self.history[0].get("role") == "system":
            self.history[0]["content"] = prompt
        else:
            self.history.insert(0, {"role": "system", "content": prompt})

    def clear_history(self):
        system_msg = None
        if self.history and self.history[0].get("role") == "system":
            system_msg = self.history[0]
        self.history = []
        if system_msg:
            self.history.append(system_msg)

    def get_history(self) -> List[Dict]:
        return self.history.copy()

    # ── image helpers ───────────────────────────────────────────────────────

    @staticmethod
    def encode_image(image_path: str) -> str:
        """Read an image file and return a base64 data-URI string."""
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        raw = path.read_bytes()
        ext = path.suffix.lower().lstrip(".")
        mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                     "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}
        mime = mime_map.get(ext, "image/png")
        b64 = base64.b64encode(raw).decode("utf-8")
        return f"data:{mime};base64,{b64}"

    @staticmethod
    def encode_image_bytes(data: bytes, mime: str = "image/png") -> str:
        b64 = base64.b64encode(data).decode("utf-8")
        return f"data:{mime};base64,{b64}"

    # ── SiliconFlow (OpenAI-compatible) chat ────────────────────────────────

    async def _siliconflow_chat(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        stream: bool = False,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """Call SiliconFlow v1/chat/completions (OpenAI-compatible)."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = self._convert_tools_to_openai(tools)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{SILICONFLOW_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"SiliconFlow API error {resp.status}: {text}")
                return await resp.json()

    async def _siliconflow_chat_stream(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        """Stream from SiliconFlow v1/chat/completions."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = self._convert_tools_to_openai(tools)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{SILICONFLOW_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"SiliconFlow API error {resp.status}: {text}")
                async for line in resp.content:
                    line_str = line.decode("utf-8").strip()
                    if line_str.startswith("data: "):
                        data_str = line_str[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue

    @staticmethod
    def _convert_tools_to_openai(tools: List[Dict]) -> List[Dict]:
        """Convert internal tool schema to OpenAI function-calling format."""
        openai_tools = []
        for t in tools:
            func_def = t.get("function", t)
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": func_def.get("name", ""),
                    "description": func_def.get("description", ""),
                    "parameters": func_def.get("parameters", {}),
                },
            })
        return openai_tools

    # ── Ollama chat (fallback / local) ──────────────────────────────────────

    async def _ollama_chat(
        self, messages: List[Dict], tools: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        client = self._get_ollama_client()
        kwargs = {"model": self.model, "messages": messages, "stream": False}
        if tools and self.tools_supported is not False:
            kwargs["tools"] = tools
        response = await client.chat(**kwargs)
        assistant_data = response.get("message", {})
        return {
            "content": assistant_data.get("content", ""),
            "tool_calls": assistant_data.get("tool_calls", []) or [],
            "raw": response,
        }

    async def _ollama_chat_stream(
        self, messages: List[Dict], tools: Optional[List[Dict]] = None
    ) -> AsyncGenerator[str, None]:
        client = self._get_ollama_client()
        kwargs = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
        async for chunk in await client.chat(**kwargs):
            yield chunk["message"]["content"]

    # ── public API ──────────────────────────────────────────────────────────

    async def chat(
        self,
        message: str,
        tools: Optional[List[Dict]] = None,
        images: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Send a message and get a response.  Supports optional image list for VLM.

        Args:
            message: User message text.
            tools: Optional tool definitions for function calling.
            images: Optional list of image paths or base64 data-URIs.

        Returns:
            {"content": str, "tool_calls": list, "raw": dict}
        """
        # Build user message content (text-only or multimodal)
        if images:
            content_parts: List[Dict] = [{"type": "text", "text": message}]
            for img in images:
                if img.startswith("data:"):
                    data_uri = img
                else:
                    data_uri = self.encode_image(img)
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": data_uri},
                })
            user_msg: Dict[str, Any] = {"role": "user", "content": content_parts}
        else:
            user_msg = {"role": "user", "content": message}

        self.history.append(user_msg)
        self._truncate_history()

        try:
            if self.provider == "siliconflow":
                raw = await self._siliconflow_chat(
                    self.history.copy(), tools=tools
                )
                choice = raw.get("choices", [{}])[0]
                msg = choice.get("message", {})
                assistant_content = msg.get("content", "") or ""
                tool_calls_raw = msg.get("tool_calls", []) or []

                # Normalise tool_calls to internal format
                tool_calls = []
                for tc in tool_calls_raw:
                    fn = tc.get("function", {})
                    args = fn.get("arguments", "{}")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    tool_calls.append({
                        "function": {
                            "name": fn.get("name", ""),
                            "arguments": args,
                        }
                    })

                self.history.append({"role": "assistant", "content": assistant_content})
                return {"content": assistant_content, "tool_calls": tool_calls, "raw": raw}

            else:  # ollama
                result = await self._ollama_chat(self.history.copy(), tools=tools)
                self.history.append({"role": "assistant", "content": result["content"]})
                return result

        except Exception as e:
            error_text = str(e)

            # Ollama fallback when tools not supported
            if (
                self.provider == "ollama"
                and tools
                and self.tools_supported is not False
                and (
                    "does not support tools" in error_text.lower()
                    or "status code: 400" in error_text.lower()
                )
            ):
                self.tools_supported = False
                try:
                    result = await self._ollama_chat(self.history.copy())
                    self.history.append({"role": "assistant", "content": result["content"]})
                    return result
                except Exception as fallback_error:
                    error_msg = f"LLM Error: {fallback_error}"
                    self.history.append({"role": "assistant", "content": error_msg})
                    return {"content": error_msg, "tool_calls": [], "raw": None}

            error_msg = f"LLM Error: {error_text}"
            self.history.append({"role": "assistant", "content": error_msg})
            return {"content": error_msg, "tool_calls": [], "raw": None}

    async def chat_stream(
        self,
        message: str,
        tools: Optional[List[Dict]] = None,
        images: Optional[List[str]] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a response token by token."""
        if images:
            content_parts: List[Dict] = [{"type": "text", "text": message}]
            for img in images:
                data_uri = img if img.startswith("data:") else self.encode_image(img)
                content_parts.append({"type": "image_url", "image_url": {"url": data_uri}})
            user_msg = {"role": "user", "content": content_parts}
        else:
            user_msg = {"role": "user", "content": message}

        self.history.append(user_msg)
        self._truncate_history()

        try:
            if self.provider == "siliconflow":
                full = ""
                async for token in self._siliconflow_chat_stream(
                    self.history.copy(), tools=tools
                ):
                    full += token
                    yield token
                self.history.append({"role": "assistant", "content": full})
            else:
                full = ""
                async for token in self._ollama_chat_stream(
                    self.history.copy(), tools=tools
                ):
                    full += token
                    yield token
                self.history.append({"role": "assistant", "content": full})
        except Exception as e:
            error_msg = f"LLM Error: {str(e)}"
            yield error_msg
            self.history.append({"role": "assistant", "content": error_msg})

    async def chat_with_vision(
        self,
        message: str,
        images: List[str],
        tools: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        Dedicated vision chat — uses the configured vision_model.
        Falls back to the main model if provider is ollama (no native VLM).
        """
        if self.provider == "ollama":
            # Ollama multimodal models like llava can handle images
            return await self.chat(message, tools=tools, images=images)

        # SiliconFlow: swap in the vision model for this call
        saved_model = self.model
        self.model = self.vision_model
        try:
            return await self.chat(message, tools=tools, images=images)
        finally:
            self.model = saved_model
